# -*- coding: utf-8 -*-
"""Publicar produto + exportar pedidos — portado de modulo_upseller.py.

Simplificação assumida nessa migração: a seleção automática de categoria
(usar_categoria_recomendada / selecionar_categoria_armazem, ~200 linhas de
fallback no original) foi deixada de fora. No app antigo já era só
"melhor esforço" (chamada dentro de um try/except mudo — se falhasse, o
produto publicava sem categoria mesmo). A grande maioria dos produtos já
publicados hoje está como "Não Categorizado" de qualquer forma (visto nos
prints usados pra depurar o Exportar mais cedo), então essa simplificação
não muda o resultado prático — só corta complexidade de portar."""
import io
import json
import os
import time

from .driver import fechar_popup, preencher_por_label, _minimizar_janela, _restaurar_janela_discreta

SKU_COUNTER_FILE = "upseller_sku_counter.json"


def get_proximo_sku(client=None):
    if client:
        try:
            q = """
                SELECT MAX(CAST(SUBSTR(sku, 4) AS INT64)) AS max_num
                FROM `leandro-marketplace.DL_Store_Online.tb_sku_registrados`
                WHERE sku LIKE 'RJ-%'
            """
            df = client.query(q).to_dataframe()
            max_num = df["max_num"].iloc[0]
            num = int(max_num or 0) + 1
            return f"RJ-{num:05d}"
        except Exception:
            pass
    try:
        if os.path.exists(SKU_COUNTER_FILE):
            with open(SKU_COUNTER_FILE) as f:
                num = json.load(f).get("contador", 0) + 1
        else:
            num = 1
        with open(SKU_COUNTER_FILE, "w") as f:
            json.dump({"contador": num}, f)
        return f"RJ-{num:05d}"
    except Exception:
        return "RJ-00001"


def titulo_case(texto):
    return texto.strip().title() if texto else ""


def extrair_dimensoes(tamanho_str):
    import re
    if not tamanho_str or not isinstance(tamanho_str, str):
        return None, None, None
    nums = re.findall(r'\d+', tamanho_str)
    if len(nums) >= 3:
        return nums[0], nums[1], nums[2]
    elif len(nums) == 2:
        return nums[0], nums[1], None
    elif len(nums) == 1:
        return nums[0], None, None
    return None, None, None


def extrair_peso_gramas(peso_str):
    import re
    if not peso_str or not isinstance(peso_str, str):
        return None
    nums = re.findall(r'\d+', peso_str)
    if nums:
        peso = int(nums[0])
        if 'kg' in peso_str.lower() or peso < 10:
            peso = peso * 1000
        return str(peso + 50)
    return None


def montar_descricao(produto):
    campos = [
        ("Fabricante", produto.get("fabricante")), ("Caixa com", produto.get("caixa_com")),
        ("Tipo", produto.get("tipo") or produto.get("tipo_de_produto")),
        ("Cor", produto.get("cor") or produto.get("cores")), ("Validade", produto.get("validade")),
        ("Composição", produto.get("composicao")),
        ("Tamanho", produto.get("tamanho") or produto.get("tamanho_aproximado")),
        ("Peso", produto.get("peso") or produto.get("peso_aproximado")),
        ("Quantidade", produto.get("quantidade")), ("Caixa Master", produto.get("caixa_master")),
    ]
    linhas = [f"{label}: {valor}" for label, valor in campos if valor]
    return "\n".join(linhas)


def processar_e_enviar_imagem(driver, imagem_url):
    if not imagem_url:
        return "sem imagem"
    if not imagem_url.startswith("http"):
        imagem_url = "https://campineira.com.br" + imagem_url
    try:
        import requests
        import tempfile
        import uuid as _uuid
        from selenium.webdriver.common.by import By
        from PIL import Image as PILImage

        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://campineira.com.br/"}
        resp = requests.get(imagem_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return f"falha ao baixar (HTTP {resp.status_code})"

        img_pil = PILImage.open(io.BytesIO(resp.content)).convert("RGB")
        MIN_LADO = 800
        largura, altura = img_pil.size
        escala = max(1.0, MIN_LADO / min(largura, altura))
        if escala > 1.0:
            img_pil = img_pil.resize((int(largura * escala) + 1, int(altura * escala) + 1), PILImage.LANCZOS)

        caminho_img = os.path.abspath(os.path.join(tempfile.gettempdir(), f"upseller_img_{_uuid.uuid4().hex}.jpg"))
        MAX_BYTES = 2 * 1024 * 1024
        qualidade = 90
        img_pil.save(caminho_img, "JPEG", quality=qualidade)
        while os.path.getsize(caminho_img) > MAX_BYTES and qualidade > 40:
            qualidade -= 15
            img_pil.save(caminho_img, "JPEG", quality=qualidade)

        driver.execute_script("window.scrollTo(0, 2000);")
        time.sleep(1)
        inputs_file = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        uploaded = False
        for inp in inputs_file:
            try:
                driver.execute_script("arguments[0].style.display='block';", inp)
                inp.send_keys(caminho_img)
                time.sleep(2)
                uploaded = True
                break
            except Exception:
                continue
        try:
            os.unlink(caminho_img)
        except Exception:
            pass
        return "imagem enviada" if uploaded else "campo de upload não encontrado"
    except Exception as e:
        return f"erro ao processar imagem: {str(e)[:80]}"


def usar_categoria_recomendada(driver):
    """Abre o seletor de categoria, clica na aba "Recomendação", clica em
    "Obter Categoria" e seleciona a PRIMEIRA sugestão retornada pela própria
    plataforma. Retorna (sucesso: bool, categoria_texto: str|None).

    Diferente de selecionar_categoria_armazem (o outro caminho, que existia no
    original mas dependia de uma chamada à API da Anthropic SEM header de
    autenticação — sempre falhava silenciosamente e nunca escolhia nada, por
    isso não foi portada): esse aqui usa a sugestão da própria Upseller, sem
    depender de nenhum serviço externo."""
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        aberto = driver.execute_script("""
            var input = document.querySelector('#basic input[placeholder="Selecionar uma Categoria"]');
            if (!input) return false;
            input.click();
            return true;
        """)
        if not aberto:
            return False, None
        time.sleep(1)

        def _clicar_aba_recomendacao():
            return driver.execute_script("""
                var tabs = document.querySelectorAll('[role="tab"], .ant-tabs-tab');
                for (var t of tabs) {
                    if (t.textContent.trim().toLowerCase().includes('recomenda') && t.offsetParent !== null) {
                        t.click();
                        return true;
                    }
                }
                return false;
            """)

        aba_ativa = False
        for _tentativa in range(4):
            _clicar_aba_recomendacao()
            time.sleep(0.8)
            aba_ativa = driver.execute_script("""
                var tabs = document.querySelectorAll('[role="tab"]');
                for (var t of tabs) {
                    if (t.getAttribute('aria-selected') === 'true' &&
                        t.textContent.trim().toLowerCase().includes('recomenda')) {
                        return true;
                    }
                }
                var ativa = document.querySelector('.ant-tabs-tab-active');
                return !!(ativa && ativa.textContent.trim().toLowerCase().includes('recomenda'));
            """)
            if aba_ativa:
                break

        if not aba_ativa:
            driver.execute_script("document.body.click();")
            return False, None

        time.sleep(1.2)

        driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                if (b.textContent.trim().toLowerCase().includes('obter categoria') && b.offsetParent !== null) {
                    b.click();
                    return true;
                }
            }
            return false;
        """)

        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("""
                    var painel = document.querySelector('.ant-tabs-tabpane-active');
                    if (!painel) return false;
                    var els = painel.querySelectorAll('.category_title');
                    for (var el of els) { if (el.offsetParent !== null) return true; }
                    return false;
                """)
            )
        except Exception:
            pass
        time.sleep(1)

        categoria_texto = driver.execute_script("""
            var painel = document.querySelector('.ant-tabs-tabpane-active');
            if (!painel) return null;
            var els = painel.querySelectorAll('.category_title');
            for (var el of els) {
                if (el.offsetParent !== null) {
                    var texto = el.textContent.trim();
                    el.click();
                    return texto;
                }
            }
            return null;
        """)

        if categoria_texto:
            time.sleep(0.5)
            return True, categoria_texto

        driver.execute_script("document.body.click();")
        return False, None

    except Exception:
        try:
            driver.execute_script("document.body.click();")
        except Exception:
            pass
        return False, None


def _mensagem_erro_legivel(e):
    texto = str(e)
    if 'stacktrace' in texto.lower() or 'invalid session id' in texto.lower() or 'session deleted' in texto.lower():
        return "sessão do Chrome caiu/desconectou no meio da ação — desconecta e loga de novo no Upseller, depois tenta reprocessar"
    primeira_linha = texto.split('\n')[0].strip()
    if not primeira_linha or len(primeira_linha) < 3:
        return "erro desconhecido do navegador (a sessão pode ter caído) — tente reprocessar"
    return primeira_linha[:150]


def publicar_produto_upseller(driver, produto, client=None):
    """Retorna (sucesso, mensagem, sku_usado)."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    sku = None
    wait = WebDriverWait(driver, 15)

    # Restaura a janela minimizada (ver login_captcha/login_codigo) antes de
    # interagir — janela minimizada tem a renderização jogada pelo Windows,
    # quebrando a mesma coisa que quebrava a exportação de pedidos (ver
    # exportar_pedidos_shipped_upseller). Reminimiza no final (sucesso ou
    # falha, via finally).
    _restaurar_janela_discreta(driver)

    try:
        driver.get("https://app.upseller.com/pt/products/product-add?productType=single")
        time.sleep(3)
        fechar_popup(driver)
        time.sleep(1)

        sku = get_proximo_sku(client)
        campo_sku = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
            "#basic > div.ant-card-body > div > form > div:nth-child(1) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > input"
        )))
        campo_sku.clear()
        campo_sku.send_keys(sku)

        nome = titulo_case(produto.get("nome", ""))
        campo_nome = driver.find_element(By.CSS_SELECTOR,
            "#basic > div.ant-card-body > div > form > div:nth-child(2) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span.input_suffix_custom.ant-input-affix-wrapper > input"
        )
        campo_nome.clear()
        campo_nome.send_keys(nome)

        # Categoria: usa a sugestão da própria Upseller ("Obter Categoria" na
        # aba Recomendação) — melhor esforço, segue publicando sem categoria
        # se não conseguir (mesmo comportamento de hoje: produto vai como
        # "Não Categorizado").
        try:
            usar_categoria_recomendada(driver)
            time.sleep(1)
        except Exception:
            pass

        ean = produto.get("ean", "")
        if ean:
            try:
                campo_ean = driver.find_element(By.CSS_SELECTOR,
                    "#basic > div.ant-card-body > div > form > div:nth-child(5) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div > div.pti_r > div > div > input[type=text]"
                )
                campo_ean.clear()
                campo_ean.send_keys(ean)
            except Exception:
                pass

        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(1)

        descricao = montar_descricao(produto)
        if descricao:
            try:
                campo_desc = driver.find_element(By.CSS_SELECTOR,
                    "#saleAddSpecification > div.ant-card-body > div > form > div.description_item.ant-row.ant-form-item > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > textarea"
                )
                campo_desc.clear()
                campo_desc.send_keys(descricao)
            except Exception:
                pass

        peso_final = extrair_peso_gramas(produto.get("peso") or produto.get("peso_aproximado"))
        if peso_final:
            try:
                campo_peso = driver.find_element(By.CSS_SELECTOR,
                    "#saleAddSpecification > div.ant-card-body > div > form > div:nth-child(6) > div.ant-col.ant-col-20.ant-form-item-control-wrapper > div > span > span > span > input"
                )
                campo_peso.clear()
                campo_peso.send_keys(peso_final)
            except Exception:
                pass

        comp, larg, alt = extrair_dimensoes(produto.get("tamanho") or produto.get("tamanho_aproximado"))
        for sel, val in [
            ("#saleAddSpecification > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span:nth-child(1) > div > div.ant-input-number-input-wrap > input", comp),
            ("#saleAddSpecification > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span:nth-child(2) > div > div.ant-input-number-input-wrap > input", larg),
            ("#saleAddSpecification > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span:nth-child(3) > div > div.ant-input-number-input-wrap > input", alt),
        ]:
            if val:
                try:
                    campo = driver.find_element(By.CSS_SELECTOR, sel)
                    campo.clear()
                    campo.send_keys(val)
                except Exception:
                    pass

        fabricante = produto.get("fabricante", "")
        if fabricante:
            try:
                campo_marca = driver.find_element(By.CSS_SELECTOR,
                    "#saleAddSpecification > div.ant-card-body > div > form > div:nth-child(5) > div.ant-col.ant-col-6.ant-form-item-control-wrapper > div > span > input"
                )
                campo_marca.clear()
                campo_marca.send_keys(fabricante)
            except Exception:
                pass

        if not preencher_por_label(driver, "#saleAddSpecification", "Quantidade", "100"):
            preencher_por_label(driver, "#basic", "Quantidade", "100")

        imagem_status = processar_e_enviar_imagem(driver, produto.get("imagem", ""))

        erro_validacao = None
        MAX_TENTATIVAS_SKU = 5
        sku_num = int(sku.split('-')[1])
        for tentativa in range(MAX_TENTATIVAS_SKU):
            if tentativa > 0:
                sku_num += 1
                sku = f"RJ-{sku_num:05d}"
                campo_sku = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
                    "#basic > div.ant-card-body > div > form > div:nth-child(1) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > input"
                )))
                campo_sku.clear()
                campo_sku.send_keys(sku)

            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            btn_salvar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
                "#myEditBox > section.my_edit_head.ant-layout > div > div.head_r > div > button"
            )))
            btn_salvar.click()
            time.sleep(3)

            erro_validacao = driver.execute_script("""
                var candidatos = document.querySelectorAll(
                    '.ant-message-error, .ant-message-notice-content, .ant-notification-notice-description, ' +
                    '.ant-form-item-explain, .ant-form-explain, [class*="error"]'
                );
                for (var el of candidatos) {
                    var txt = (el.textContent || '').trim();
                    if (txt && txt.toLowerCase().includes('já existe') && el.getClientRects().length > 0) {
                        return txt;
                    }
                }
                return null;
            """)
            if erro_validacao and "product-add" not in driver.current_url:
                erro_validacao = None
            if not erro_validacao:
                break
            if 'sku' not in erro_validacao.lower():
                break

        if erro_validacao:
            return False, f"❌ {erro_validacao} (SKU tentado: {sku})", sku

        aviso_imagem = "" if imagem_status == "imagem enviada" else f" ⚠️ Imagem: {imagem_status}."
        return True, f"✅ Produto '{nome}' publicado! SKU: {sku}.{aviso_imagem}", sku

    except Exception as e:
        return False, f"❌ Erro: {_mensagem_erro_legivel(e)}", sku
    finally:
        try:
            _minimizar_janela(driver)
        except Exception:
            pass


# ============================================================
# EXPORTAR PEDIDOS ENVIADOS (pra alimentar o Dashboard Financeiro)
# ============================================================

def exportar_pedidos_shipped_upseller(driver, pasta_download, data_inicio_custom=None, data_fim_custom=None):
    """Automatiza 'Pedidos > Enviado' > Exportar > Exportar Todos os Pedidos >
    captura o total de páginas > Exportar > espera processar > Baixar.

    Sem período customizado, cobre do 1º dia do mês anterior até o último dia
    do mês atual. Os dois painéis do calendário são sempre meses adjacentes —
    pra cobrir mais que isso, chame de novo com outra janela de 2 meses.

    Retorna (sucesso: bool, caminho_do_arquivo_ou_mensagem_de_erro: str)."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    import glob
    import datetime as _dt
    import calendar as _cal

    def _falha(msg):
        try:
            driver.save_screenshot(os.path.join(pasta_download, "ultimo_erro_screenshot.png"))
        except Exception:
            pass
        return False, msg

    # Se o driver ficou minimizado depois do login (ver _minimizar_janela em
    # upseller/views.py), restaura ele pra tela normal antes de qualquer
    # interação que dependa de hover — janela minimizada tem a renderização
    # jogada pelo Windows do mesmo jeito que uma fora da tela, quebrando o
    # dropdown "Exportar". Minimiza de novo no final (sucesso ou falha, via
    # finally), então essa janela só fica visível durante o tempo real da
    # exportação, não o resto do tempo.
    _restaurar_janela_discreta(driver)

    try:
        os.makedirs(pasta_download, exist_ok=True)
        try:
            driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": os.path.abspath(pasta_download),
            })
        except Exception:
            pass

        # Reforça aqui também (já é setado em criar_driver, mas por segurança
        # — essa emulação pode não sobreviver à navegação em alguma versão
        # do Chromium): sem isso, o Chrome reporta `hover: none` pro
        # Upseller e o dropdown "Exportar" não abre, mesmo com clique certo.
        try:
            driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {
                "features": [
                    {"name": "hover", "value": "hover"},
                    {"name": "pointer", "value": "fine"},
                    {"name": "any-hover", "value": "hover"},
                    {"name": "any-pointer", "value": "fine"},
                ]
            })
        except Exception:
            pass

        driver.get("https://app.upseller.com/pt/order/shipped")
        time.sleep(3)
        fechar_popup(driver)

        clicou_aba_enviado = driver.execute_script("""
            var candidatos = document.querySelectorAll('a, li, span, div');
            for (var el of candidatos) {
                if (el.children.length > 0) continue;
                if (el.textContent.trim() === 'Enviado' && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        if clicou_aba_enviado:
            time.sleep(2)

        # ── Filtro de data: "Hora do Pagamento", do 1º dia do mês anterior até
        # o último dia do mês atual (ou período customizado, ver docstring) ──
        hoje = _dt.date.today()
        primeiro_mes_atual = hoje.replace(day=1)
        ultimo_mes_atual = hoje.replace(day=_cal.monthrange(hoje.year, hoje.month)[1])
        mes_anterior_fim = primeiro_mes_atual - _dt.timedelta(days=1)
        primeiro_mes_anterior = mes_anterior_fim.replace(day=1)
        data_inicio, data_fim = primeiro_mes_anterior, ultimo_mes_atual
        if data_inicio_custom is not None:
            data_inicio = data_inicio_custom
        if data_fim_custom is not None:
            data_fim = data_fim_custom

        driver.execute_script("""
            var els = document.querySelectorAll('.ant-select-selection-selected-value');
            for (var el of els) {
                if (el.textContent.trim() === 'Hora de Envio' && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        time.sleep(1)
        driver.execute_script("""
            var itens = document.querySelectorAll('li, div, span');
            for (var el of itens) {
                if (el.textContent.trim() === 'Hora do Pagamento' && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        time.sleep(1)
        driver.execute_script("""
            var input = document.querySelector('input.ant-calendar-range-picker-input');
            if (input) { input.click(); return true; }
            return false;
        """)
        time.sleep(1)

        # Painéis do calendário são sempre adjacentes (esquerda = mês N, direita
        # = mês N+1); por padrão mostram mês anterior + mês atual. Se
        # data_inicio pedir um mês mais antigo, navega o painel esquerdo pra
        # trás um número EXATO de vezes (matemática de data, não "tenta até achar").
        meses_navegar_atras = (primeiro_mes_anterior.year - data_inicio.year) * 12 + (primeiro_mes_anterior.month - data_inicio.month)
        if meses_navegar_atras > 0:
            MAX_NAVEGACAO = 36
            for _ in range(min(meses_navegar_atras, MAX_NAVEGACAO)):
                try:
                    seta_prev = next((el for el in driver.find_elements(By.CSS_SELECTOR, "a.ant-calendar-prev-month-btn") if el.is_displayed()), None)
                    if not seta_prev:
                        break
                    ActionChains(driver).move_to_element(seta_prev).pause(0.1).click().perform()
                    time.sleep(0.4)
                except Exception:
                    break

        def _clicar_dia_sem_navegar(dia_numero, indice_painel):
            return driver.execute_script("""
                var alvoTexto = String(arguments[0]);
                var indicePainel = arguments[1];
                var paineis = document.querySelectorAll('table.ant-calendar-table');
                if (paineis.length <= indicePainel) return false;
                var painel = paineis[indicePainel];
                var celulas = painel.querySelectorAll('td');
                for (var i = 0; i < celulas.length; i++) {
                    var td = celulas[i];
                    var classe = td.className || '';
                    if (classe.indexOf('last-month') !== -1 || classe.indexOf('next-month') !== -1 ||
                        classe.indexOf('disabled') !== -1) continue;
                    var texto = td.textContent.trim();
                    if (texto === alvoTexto && td.offsetParent !== null) {
                        td.click();
                        return true;
                    }
                }
                return false;
            """, dia_numero, indice_painel)

        _clicar_dia_sem_navegar(data_inicio.day, 0)
        time.sleep(0.3)
        _clicar_dia_sem_navegar(data_fim.day, 1)
        time.sleep(0.3)

        def _calendario_ainda_aberto():
            # offsetParent NÃO serve aqui: o dropdown do calendário do Ant
            # Design é `position: fixed`, e offsetParent sempre retorna null
            # pra elementos fixed — independente de estarem visíveis ou não
            # (quirk documentado do DOM). Isso fazia essa função sempre
            # responder "fechado" mesmo com o calendário bem aberto na tela
            # (visto num teste real: nenhuma tentativa de fechar rodava,
            # porque o "if calendário aberto" nunca era verdadeiro).
            # getClientRects().length reflete o que está de fato renderizado.
            return driver.execute_script("""
                var els = document.querySelectorAll('.ant-calendar-table, .ant-calendar-ok-btn');
                for (var el of els) { if (el.getClientRects().length > 0) return true; }
                return false;
            """)

        def _clicar_ok_calendario():
            # O React re-renderiza o calendário depois de selecionar as duas
            # datas (visto num teste real: StaleElementReferenceException
            # não capturada aqui derrubava a exportação inteira) — por isso
            # busca o elemento de novo bem antes de cada tentativa de clique,
            # em vez de reaproveitar a mesma referência pras duas tentativas.
            def _achar_ok():
                return next((el for el in driver.find_elements(By.CSS_SELECTOR, ".ant-calendar-ok-btn, a[role='button']")
                             if el.text.strip() == "Ok" and el.is_displayed()), None)

            elemento = _achar_ok()
            if not elemento:
                return False
            try:
                ActionChains(driver).move_to_element(elemento).pause(0.2).click().perform()
                return True
            except Exception:
                pass
            try:
                elemento = _achar_ok()
                if not elemento:
                    return False
                driver.execute_script("arguments[0].click();", elemento)
                return True
            except Exception:
                return False

        for _tentativa_ok in range(3):
            if not _calendario_ainda_aberto():
                break
            _clicar_ok_calendario()
            for _ in range(6):
                time.sleep(0.4)
                if not _calendario_ainda_aberto():
                    break

        # Se o "Ok" não fechou o calendário nas 3 tentativas (visto num teste
        # real: o dropdown de "Hora do Pedido/Pagamento" fica sobreposto na
        # tela e trava o clique em Exportar depois), força o fechamento.
        # document.body.click() (evento sintético via JS) NÃO basta — o
        # Ant Design detecta "clique fora" escutando mousedown de verdade no
        # documento, então um clique simulado via JS não dispara isso (visto
        # num teste real: mesmo depois do .click() sintético, o dropdown
        # continuava visualmente aberto). Em vez disso, clica de verdade
        # (ActionChains) num ponto estável e neutro da página — o título
        # "Pedidos" do menu lateral.
        if _calendario_ainda_aberto():
            from selenium.webdriver.common.keys import Keys
            try:
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass
            try:
                ponto_neutro = next(
                    (el for el in driver.find_elements(By.XPATH, "//*[normalize-space(text())='Pedidos']") if el.is_displayed()),
                    None,
                )
                if ponto_neutro:
                    ActionChains(driver).move_to_element(ponto_neutro).click().perform()
            except Exception:
                pass
            time.sleep(0.5)
            for _ in range(6):
                time.sleep(0.4)
                if not _calendario_ainda_aberto():
                    break

        # Trocar o filtro de data recarrega a lista — espera o spinner sumir
        # antes de clicar em Exportar (senão cai num overlay/re-render).
        time.sleep(3)
        for _ in range(10):
            spinner_ativo = driver.execute_script("""
                var els = document.querySelectorAll('.ant-spin-spinning');
                for (var el of els) { if (el.offsetParent !== null) return true; }
                return false;
            """)
            if not spinner_ativo:
                break
            time.sleep(0.5)

        # ── Abrir o menu "Exportar" ──────────────────────────────────────
        def _menu_exportar_aberto():
            # offsetParent !== null não serve aqui pelo mesmo motivo de
            # _calendario_ainda_aberto() acima — o dropdown do Ant Design é
            # position: fixed.
            return driver.execute_script("""
                var candidatos = document.querySelectorAll('a, li, span, div');
                for (var el of candidatos) {
                    if (el.children.length > 0) continue;
                    if (el.closest('button')) continue;
                    var txt = el.textContent.replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (txt.indexOf('exportar') !== -1 && txt !== 'exportar' && txt.length < 60 && el.getClientRects().length > 0) {
                        return true;
                    }
                }
                return false;
            """)

        def _achar_elemento_e_trigger():
            for b in driver.find_elements(By.TAG_NAME, "button"):
                if b.text.strip() == "Exportar" and b.is_displayed():
                    trigger = driver.execute_script(
                        "return arguments[0].closest('.ant-dropdown-trigger') || arguments[0].parentElement;", b
                    )
                    return b, trigger
            return None, None

        def _hover_dropdown_trigger():
            try:
                elemento, trigger = _achar_elemento_e_trigger()
                if not elemento:
                    return False
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
                time.sleep(0.3)
                ActionChains(driver).move_to_element(elemento).pause(0.3).perform()
                driver.execute_script("""
                    function disparar(el) {
                        ['mouseenter', 'mouseover', 'mousemove'].forEach(function(tipo) {
                            el.dispatchEvent(new MouseEvent(tipo, {bubbles: true, cancelable: true, view: window}));
                        });
                    }
                    disparar(arguments[0]);
                    if (arguments[1]) disparar(arguments[1]);
                """, elemento, trigger)
                return True
            except Exception:
                return False

        def _clicar_botao_exportar(tentar_js_tambem=False):
            try:
                elemento, trigger = _achar_elemento_e_trigger()
                if not elemento:
                    return False
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
                time.sleep(0.3)
                ActionChains(driver).move_to_element(elemento).pause(0.2).click().perform()
                if tentar_js_tambem:
                    time.sleep(0.4)
                    driver.execute_script("""
                        arguments[0].click();
                        if (arguments[1]) arguments[1].click();
                    """, elemento, trigger)
                return True
            except Exception:
                return False

        if not _achar_elemento_e_trigger()[0]:
            return _falha("❌ Botão 'Exportar' não encontrado na tela de Pedidos Enviados")

        menu_aberto = False
        _hover_dropdown_trigger()
        for _ in range(6):
            time.sleep(0.6)
            if _menu_exportar_aberto():
                menu_aberto = True
                break
        if not menu_aberto:
            _clicar_botao_exportar()
            for _ in range(6):
                time.sleep(0.6)
                if _menu_exportar_aberto():
                    menu_aberto = True
                    break
        if not menu_aberto:
            _clicar_botao_exportar(tentar_js_tambem=True)
            for _ in range(6):
                time.sleep(0.6)
                if _menu_exportar_aberto():
                    menu_aberto = True
                    break
        if not menu_aberto:
            return _falha("❌ Menu 'Exportar' não abriu depois de tentar hover e clique.")

        # ── "Exportar Todos os Pedidos" ──────────────────────────────────
        clicou_todos = driver.execute_script("""
            var candidatos = document.querySelectorAll('a, li, span, div');
            var fallback = null;
            for (var el of candidatos) {
                if (el.children.length > 0) continue;
                if (el.offsetParent === null) continue;
                var txt = el.textContent.replace(/\\s+/g, ' ').trim().toLowerCase();
                if (txt.indexOf('exportar todos os pedidos') !== -1) {
                    el.click();
                    return true;
                }
                if (!fallback && txt.indexOf('exportar todos') !== -1) fallback = el;
            }
            if (fallback) { fallback.click(); return true; }
            return false;
        """)
        if not clicou_todos:
            return _falha("❌ 'Exportar Todos os Pedidos' não encontrado (mas o menu tinha aberto).")
        time.sleep(2)

        # ── Modal de configuração: garante os 3 checkboxes marcados ──────
        driver.execute_script("""
            var labels = document.querySelectorAll('.ant-checkbox-wrapper');
            var alvos = ['informação do produto', 'informação do pedido', 'sku (armazém)', 'sku armazém'];
            for (var lbl of labels) {
                var txt = lbl.textContent.trim().toLowerCase();
                for (var alvo of alvos) {
                    if (txt.indexOf(alvo) !== -1) {
                        var input = lbl.querySelector('input[type=checkbox]');
                        if (input && !input.checked) { lbl.click(); }
                    }
                }
            }
        """)
        time.sleep(1)

        clicou_exportar_modal = driver.execute_script("""
            var btns = document.querySelectorAll('.ant-modal-content button.ant-btn-primary, .ant-modal-content button');
            for (var b of btns) {
                if (b.textContent.trim() === 'Exportar' && b.offsetParent !== null) {
                    b.click();
                    return true;
                }
            }
            return false;
        """)
        if not clicou_exportar_modal:
            return _falha("❌ Botão 'Exportar' do modal de configuração não encontrado")
        time.sleep(2)

        # ── Total de páginas → segundo campo de página ───────────────────
        pagina_max = driver.execute_script("""
            var els = document.querySelectorAll('.fw_bold');
            for (var el of els) {
                var txt = el.textContent.trim();
                if (/^\\d+$/.test(txt)) return txt;
            }
            return null;
        """)
        if pagina_max:
            driver.execute_script("""
                var inputs = document.querySelectorAll('input.ant-input-number-input[role="spinbutton"]');
                if (inputs.length > 1) {
                    var input = inputs[1];
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, arguments[0]);
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                    input.blur();
                }
            """, pagina_max)
            time.sleep(0.5)

        clicou_exportar_final = driver.execute_script("""
            var btns = document.querySelectorAll('button.ant-btn-primary');
            for (var b of btns) {
                if (b.textContent.trim() === 'Exportar' && b.offsetParent !== null) {
                    b.click();
                    return true;
                }
            }
            return false;
        """)
        if not clicou_exportar_final:
            return _falha("❌ Botão 'Exportar' final não encontrado")

        time.sleep(8)  # tempo pra Upseller processar a exportação

        arquivos_antes = set(glob.glob(os.path.join(pasta_download, "*")))
        clicou_baixar = False
        for _ in range(10):
            clicou_baixar = driver.execute_script("""
                var btns = document.querySelectorAll('button.ant-btn-primary');
                for (var b of btns) {
                    if (b.textContent.trim() === 'Baixar' && b.offsetParent !== null) {
                        b.click();
                        return true;
                    }
                }
                return false;
            """)
            if clicou_baixar:
                break
            time.sleep(3)
        if not clicou_baixar:
            return _falha("❌ Botão 'Baixar' não encontrado — a exportação pode ainda estar processando, tente de novo em instantes")

        arquivo_novo = None
        for _ in range(30):
            time.sleep(1)
            arquivos_depois = set(glob.glob(os.path.join(pasta_download, "*")))
            novos = [f for f in (arquivos_depois - arquivos_antes) if not f.endswith(".crdownload")]
            if novos:
                arquivo_novo = max(novos, key=os.path.getmtime)
                break
        if not arquivo_novo:
            return _falha(f"❌ Arquivo não apareceu em {pasta_download} a tempo (clicou Baixar, mas o download não foi detectado)")

        return True, arquivo_novo

    except Exception as e:
        return _falha(f"❌ Erro ao exportar pedidos: {str(e)[:200]}")
    finally:
        try:
            _minimizar_janela(driver)
        except Exception:
            pass
