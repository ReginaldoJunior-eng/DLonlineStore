# -*- coding: utf-8 -*-
"""Automação do Upseller — portado de modulo_upseller.py (CodigosPython2).

Diferenças de propósito em relação ao original:
- Tentou rodar headless (--headless=new) nessa migração, a pedido do usuário,
  pra não abrir uma janela de Chrome visível na máquina de quem for usar —
  mas voltou atrás no mesmo dia porque o menu "Exportar" (Pedidos > Enviado)
  parou de abrir em headless (depende de hover de mouse de verdade; ver
  actions.py:exportar_pedidos_shipped_upseller, que já tem 3 fallbacks de
  hover/clique e mesmo assim falhava). Hoje usa Chrome de verdade, só que
  posicionado fora da área visível da tela (--window-position bem negativo)
  — mantém hover funcionando sem aparecer pra quem estiver usando o PC.
- Sem OCR do captcha (pytesseract exigiria instalar o binário do Tesseract
  separado na máquina de quem for usar o instalável — frição grande pra um
  público não-técnico). A pessoa só lê e digita o captcha na tela; o campo
  já vem em foco, é rápido.
- Sem os fluxos de cópia pra Shopee/Shein/Temu/TikTok (etapa2/3 do original):
  não são usados pelas telas atuais (Campineira > Publicar só publica no
  Armazém). Podem ser portados depois se precisar.
"""
import base64
import io
import os
import time

from django.conf import settings

from .state import ESTADO

TABLE_SESSAO_UPSELLER = "leandro-marketplace.DL_Store_Online.tb_upseller_sessao"

SEL_EMAIL = "#app > div:nth-child(2) > div.page_layout > div.page_module_box > div.page_module > form > div:nth-child(2) > div > div > span > input"
SEL_SENHA = "#app > div:nth-child(2) > div.page_layout > div.page_module_box > div.page_module > form > div:nth-child(3) > div > div > span > span.ant-input-affix-wrapper.ant-input-password > input"
SEL_CAPTCHA = "#app > div:nth-child(2) > div.page_layout > div.page_module_box > div.page_module > form > div:nth-child(4) > div > div > span > input"
SEL_IMG_CAP = "#app > div:nth-child(2) > div.page_layout > div.page_module_box > div.page_module > form > div:nth-child(4) > div > div > span > button > img"
SEL_BTN_SEND_CODE = "#app > div.page_layout > div.page_module_box > div.page_module > form > div.code_item.ant-row.ant-form-item > div > div > span > button"


# ── COOKIES (BigQuery, compartilhado com a versão na nuvem) ────────────────

def _carregar_cookies_salvos(client):
    if client:
        try:
            df = client.query(
                f"SELECT cookies_json FROM `{TABLE_SESSAO_UPSELLER}` WHERE id = 'cookies'"
            ).to_dataframe()
            if not df.empty:
                import json
                return json.loads(df.iloc[0]["cookies_json"])
        except Exception:
            pass
    return None


def existe_sessao_salva(client):
    return _carregar_cookies_salvos(client) is not None


def salvar_cookies(driver, client):
    try:
        cookies = driver.get_cookies()
    except Exception:
        return False
    if client:
        try:
            import json
            import pandas as pd
            from google.cloud import bigquery
            from datetime import datetime
            df = pd.DataFrame([{
                "id": "cookies", "cookies_json": json.dumps(cookies),
                "data_atualizacao": datetime.utcnow().isoformat(),
            }])
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
            client.load_table_from_dataframe(df, TABLE_SESSAO_UPSELLER, job_config=job_config).result()
            return True
        except Exception:
            pass
    return False


def login_por_cookies(driver, client):
    cookies = _carregar_cookies_salvos(client)
    if cookies is None:
        return False
    try:
        driver.get(settings.UPSELLER_URL)
        time.sleep(2)
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        driver.refresh()
        time.sleep(3)
        return "login" not in driver.current_url
    except Exception:
        return False


def deletar_cookies(client):
    if client:
        try:
            client.query(f"DELETE FROM `{TABLE_SESSAO_UPSELLER}` WHERE id = 'cookies'").result()
        except Exception:
            pass


# ── DRIVER ────────────────────────────────────────────────────────────────

def criar_driver(pasta_download=None):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    # Nem headless nem fora da tela de propósito — comparado com
    # CodigosPython2 (a versão original): lá, o Xvfb/display virtual e a
    # emulação de hover via CDP só existem pro deploy na nuvem (Streamlit
    # Cloud, Linux sem tela nenhuma); rodando local (nosso caso aqui), o
    # código original sempre abriu um Chrome comum, visível, sem nenhum
    # truque — e sempre funcionou. `--window-position` bem negativo (testado
    # antes) parecia dar conta, mas o Windows aparentemente ainda throttla a
    # renderização de janelas fora da área visível parecido com uma janela
    # minimizada, quebrando o hover de novo. Fica visível por padrão agora;
    # quem chama minimiza depois do login (ver _minimizar_janela) e restaura
    # antes de qualquer etapa que dependa de hover (ver
    # upseller/actions.py:exportar_pedidos_shipped_upseller).
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    if pasta_download:
        os.makedirs(pasta_download, exist_ok=True)
        opts.add_experimental_option("prefs", {
            "download.default_directory": os.path.abspath(pasta_download),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        })
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    if pasta_download:
        try:
            driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": os.path.abspath(pasta_download),
            })
        except Exception:
            pass
    # Sem isso, o Chrome pode reportar `hover: none` pro Upseller (site usa
    # @media (hover: hover) pra decidir se os dropdowns respondem a hover) —
    # o clique/hover acontece certinho no Selenium, mas a UI simplesmente
    # não abre o menu. Faltava na versão portada (CodigosPython2 já tinha
    # isso desde antes) — foi a causa real do menu "Exportar" travando,
    # achada só depois de comparar os dois projetos lado a lado.
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
    return driver


def driver_esta_vivo(driver):
    if driver is None:
        return False
    try:
        _ = driver.title
        return True
    except Exception:
        return False


def _minimizar_janela(driver):
    """Local roda com tela de verdade — minimizar é só pra não ficar atrapalhando
    o usuário enquanto a automação roda em segundo plano."""
    try:
        driver.minimize_window()
    except Exception:
        pass


def _restaurar_janela_discreta(driver):
    """Restaura a janela minimizada antes de qualquer interação que dependa
    de hover (janela minimizada tem a renderização jogada pelo Windows,
    quebrando hover — ver publicar_produto_upseller/
    exportar_pedidos_shipped_upseller em actions.py). Usa uma janela pequena
    num canto (não tela cheia em cima de tudo) — não elimina por completo a
    janela "estourando" na tela (não achamos um jeito de restaurar sem
    trazer pro primeiro plano, testando de verdade), mas fica bem menos
    invasivo que ocupar a tela toda."""
    try:
        largura_tela = driver.execute_script("return screen.width") or 1920
        altura_tela = driver.execute_script("return screen.height") or 1080
    except Exception:
        largura_tela, altura_tela = 1920, 1080
    LARGURA, ALTURA = 1000, 700
    x = max(0, largura_tela - LARGURA - 20)
    y = max(0, altura_tela - ALTURA - 60)
    try:
        driver.set_window_rect(x=x, y=y, width=LARGURA, height=ALTURA)
    except Exception:
        pass


def clicar_enviar_codigo(driver):
    """Clica no link/botão "Enviar Código" da tela de verificação por e-mail.
    Antes usava só SEL_BTN_SEND_CODE, um seletor CSS super específico copiado
    do DevTools (caminho fixo na árvore) — bug real visto em produção: a
    pessoa ficava olhando a tela parada em "Enviar Código" nunca clicado, o
    e-mail nunca chegava, e o código que ela digitava era descartado (a view
    achava que ainda não tinha mandado o clique de envio). Busca por texto
    agora — sobrevive a mudança de estrutura/classe da página, só não pode
    mudar o texto do botão."""
    try:
        clicou = driver.execute_script("""
            function semAcento(s) {
                return (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
            }
            // Qualquer elemento (button, a, span, div, li...) cujo texto bata
            // é candidato — mas um elemento que só ENVOLVE outro candidato
            // (ex.: <span><button>Enviar Código</button></span>, comum em
            // Ant Design) não pode ser o escolhido: clicar nele não dispara
            // o onclick de quem está por dentro (clique só borbulha pra
            // cima, nunca desce). Por isso pega sempre o mais ESPECÍFICO —
            // o candidato que não tem nenhum outro candidato dentro dele.
            var candidatos = Array.from(document.querySelectorAll(
                'button, a, span, div, input[type="submit"], [role="button"]'
            )).filter(function(el) {
                var txt = semAcento(el.textContent).trim();
                // O texto explicativo da tela ("Para verificar sua
                // identidade, clique em Enviar Código...") também contém a
                // frase — o limite de tamanho descarta essa frase inteira e
                // só deixa passar o texto do botão/link de verdade, curto.
                return txt.indexOf('enviar codigo') !== -1 && txt.length < 40 && el.getClientRects().length > 0;
            });
            for (var el of candidatos) {
                var temFilhoCandidato = candidatos.some(function(outro) {
                    return outro !== el && el.contains(outro);
                });
                if (!temFilhoCandidato) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        if clicou:
            return True
    except Exception:
        pass
    # Fallback: seletor CSS antigo, só por garantia.
    from selenium.webdriver.common.by import By
    try:
        for btn in driver.find_elements(By.CSS_SELECTOR, SEL_BTN_SEND_CODE):
            if btn.is_displayed() and btn.is_enabled():
                driver.execute_script("arguments[0].click();", btn)
                return True
    except Exception:
        pass
    return False


def fechar_popup(driver):
    """Fecha qualquer popup/modal aberto — inclui o fix do modal 'Avisos'
    (carrossel hover/clique, sem X) descoberto na versão cloud: precisa clicar
    em 'Próximo' até esgotar os slides, nunca no primeiro botão às cegas
    (que é 'Anterior', um no-op que deixava o modal preso)."""
    from selenium.webdriver.common.by import By
    fechou = False
    seletores = [
        "button[aria-label='Close'].ant-modal-close", "button.ant-modal-close",
        ".ant-modal-close", ".ant-modal-close-x", "button.ant-btn:not(.ant-btn-primary)",
    ]
    for sel in seletores:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for btn in btns:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.5)
                    fechou = True
                    break
            if fechou:
                break
        except Exception:
            continue

    if not fechou:
        try:
            for txt in ["Fechar", "Close", "×", "X"]:
                btns = driver.find_elements(By.XPATH, f"//button[contains(text(),'{txt}')]")
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
                        fechou = True
                        break
                if fechou:
                    break
        except Exception:
            pass

    try:
        for _ in range(10):
            avancou = False
            for txt in ["Próximo", "Next", "Concluir", "Entendi", "OK"]:
                btns = driver.find_elements(By.XPATH, f"//button[contains(., '{txt}')]")
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
                        avancou = True
                        fechou = True
                        break
                if avancou:
                    break
            if not avancou:
                break
    except Exception:
        pass

    time.sleep(1)
    try:
        modais = driver.find_elements(By.CSS_SELECTOR, ".ant-modal-wrap:not([style*='display: none'])")
        for modal in modais:
            try:
                botoes = [b for b in modal.find_elements(By.CSS_SELECTOR, "button") if b.is_displayed()]
                botoes = [b for b in botoes if b.text.strip().lower() not in ("anterior", "voltar", "back", "previous")]
                if botoes:
                    driver.execute_script("arguments[0].click();", botoes[-1])
                    time.sleep(0.5)
            except Exception:
                pass
    except Exception:
        pass
    return fechou


def preencher_por_label(driver, form_selector, label_texto, valor):
    """Preenche um campo achando a linha do formulário pelo texto do <label>,
    em vez de nth-child (posição instável entre execuções)."""
    try:
        ok = driver.execute_script("""
            var form = document.querySelector(arguments[0]);
            if (!form) return false;
            var alvo = arguments[1].trim().toLowerCase();
            var labels = form.querySelectorAll('label');
            var linha = null;
            for (var lbl of labels) {
                var txt = lbl.textContent.replace('*','').trim().toLowerCase();
                if (txt === alvo) {
                    linha = lbl.closest('.ant-row') || lbl.closest('.ant-form-item') || lbl.parentElement;
                    break;
                }
            }
            if (!linha) return false;
            var input = linha.querySelector('input');
            if (!input) return false;
            var val = arguments[2];
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, val);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.blur();
            return true;
        """, form_selector, label_texto, str(valor))
        return bool(ok)
    except Exception:
        return False


def captura_captcha_b64(driver):
    """Tira a imagem do captcha como data URI base64, pra mostrar na tela sem
    precisar de OCR — a pessoa só lê e digita."""
    from selenium.webdriver.common.by import By
    try:
        img_elem = driver.find_element(By.CSS_SELECTOR, SEL_IMG_CAP)
        src = img_elem.get_attribute("src") or ""
        if src.startswith("data:image"):
            return src
        img_bytes = img_elem.screenshot_as_png
        return "data:image/png;base64," + base64.b64encode(img_bytes).decode()
    except Exception:
        return None
