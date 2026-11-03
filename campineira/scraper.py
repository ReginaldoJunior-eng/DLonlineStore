# -*- coding: utf-8 -*-
"""Varredura de produtos no site da Campineira — portado de
rodar_rpa_background em modulo_campineira.py. Roda em thread separada
(threading.Thread, disparada pela view) e comunica progresso via um arquivo
JSON local (mesmo mecanismo do original) que a tela de Configurar e Rodar
consulta a cada poll.

Site raspado aqui é o da Campineira (fornecedor), diferente do Upseller —
não tem relação com o bug de hover/headless que passamos o dia debugando
hoje; esse scraper já rodava headless no Streamlit original também."""
import json
import os
import time
from datetime import datetime

from django.conf import settings

from . import bq

ARQUIVO_STATUS = os.path.join(settings.BASE_DIR, "campineira_status.json")
ARQUIVO_RESULTADOS = os.path.join(settings.BASE_DIR, "campineira_resultados.json")
ARQUIVO_FILTROS = os.path.join(settings.BASE_DIR, "campineira_filtros.json")


def salvar_status(status: dict):
    with open(ARQUIVO_STATUS, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)


def ler_status() -> dict:
    if not os.path.exists(ARQUIVO_STATUS):
        return {"rodando": False, "progresso": "", "inicio": None, "fim": None}
    try:
        with open(ARQUIVO_STATUS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"rodando": False, "progresso": "", "inicio": None, "fim": None}


def salvar_filtros(filtros_cat: dict):
    """Guarda em arquivo o estoque_min/preco_min que a pessoa configurou pra
    cada categoria na fila, ao lado do status — pra essa regra valer de
    verdade na leitura (Resultados/Publicar) sem depender da sessão do
    navegador continuar exatamente igual entre configurar a varredura e ver
    o resultado (sessão pode, em teoria, resetar; arquivo não some)."""
    with open(ARQUIVO_FILTROS, "w", encoding="utf-8") as f:
        json.dump(filtros_cat, f, ensure_ascii=False)


def ler_filtros():
    if not os.path.exists(ARQUIVO_FILTROS):
        return None
    try:
        with open(ARQUIVO_FILTROS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def rodar_rpa_background(filtros_cat, cats_varrer=None, buscar_detalhes=False,
                          retomar_id_captura=None, paginas_ja_feitas=None):
    """Roda o RPA numa thread separada. retomar_id_captura/paginas_ja_feitas:
    usados só ao retomar uma varredura interrompida (ver
    bq.buscar_progresso_varredura) — reaproveita o id_captura antigo e avança
    direto até a página onde parou em cada categoria antes de voltar a
    extrair/registrar produtos normalmente."""
    from core.bigquery import get_client

    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager

        inicio_dt = datetime.now()
        id_captura = retomar_id_captura or inicio_dt.strftime("%Y%m%d_%H%M%S")
        paginas_ja_feitas = paginas_ja_feitas or {}

        try:
            client_bq_camp = get_client()
        except Exception:
            client_bq_camp = None

        progresso_inicial = "Iniciando..." if client_bq_camp else "Iniciando... ⚠️ BigQuery indisponível — varredura pode falhar."
        bq_erro_reportado = [False]

        ids_ja_publicados = set()
        if client_bq_camp:
            try:
                df_publicados = client_bq_camp.query(
                    f"SELECT DISTINCT id_produto FROM `{bq.TABLE_PIPELINE}` WHERE etapa = 'armazem' AND status = 'ok'"
                ).to_dataframe()
                ids_ja_publicados = set(df_publicados["id_produto"].tolist())
            except Exception:
                ids_ja_publicados = set()

        salvar_status({"rodando": True, "progresso": progresso_inicial,
                        "inicio": inicio_dt.strftime("%d/%m/%Y %H:%M:%S"),
                        "inicio_ts": inicio_dt.timestamp(), "fim": None, "duracao": None})

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

        def atualizar(msg):
            status = ler_status()
            status["progresso"] = msg
            salvar_status(status)

        try:
            atualizar("Fazendo login...")
            driver.get("https://campineira.com.br/index.php")
            time.sleep(5)
            driver.find_element(By.CSS_SELECTOR, "input[name='usuario'].login-baixa").send_keys("DL")
            driver.find_element(By.CSS_SELECTOR, "input[name='senha'].login-baixa").send_keys("Gele1826")
            driver.find_elements(By.XPATH, "//button[normalize-space(text())='OK']")[1].click()
            time.sleep(5)

            atualizar("Coletando categorias...")
            cats_js = driver.execute_script("""
                var links = document.querySelectorAll("ul.menu-categorias-lateral > li > a[href*=categoria]");
                var r = [];
                for (var i=0; i<links.length; i++) {
                    var txt = links[i].textContent.trim();
                    var href = links[i].getAttribute('href');
                    if (txt && href) r.push({nome: txt, url: 'https://campineira.com.br/' + href});
                }
                return r;
            """)
            vistos = set()
            categorias = []
            for c in cats_js:
                if c['nome'] not in vistos:
                    vistos.add(c['nome'])
                    categorias.append(c)

            todos_produtos = []
            buffer_checkpoint = []
            paginas_desde_ultimo_checkpoint = [0]
            PAGINAS_POR_CHECKPOINT = 20
            # Salvaguarda contra duplicata: se a paginação não tiver atualizado
            # a tela a tempo (site lento, os 3s de espera não bastaram), o
            # laço de extração pode ler a mesma página duas vezes e gravar o
            # mesmo produto repetido nessa mesma varredura. Um id já visto
            # nessa execução nunca é gravado de novo.
            ids_capturados_nesta_execucao = set()

            def _gravar_checkpoint_historico():
                nonlocal buffer_checkpoint
                if not buffer_checkpoint:
                    return
                ok_hist, erro_hist = bq.atualizar_historico_bq(client_bq_camp, buffer_checkpoint)
                if not ok_hist:
                    atualizar(f"⚠️ Falha ao gravar checkpoint no histórico: {erro_hist}")
                buffer_checkpoint = []
                paginas_desde_ultimo_checkpoint[0] = 0

            SCRIPT_EXTRAI = """
            var boxes = document.querySelectorAll('div.box-produtos');
            var resultado = [];
            for (var i = 0; i < boxes.length; i++) {
                var box = boxes[i];
                var id = box.getAttribute('id');
                var nomeElem = box.querySelector('span.nome-produto');
                var nome = nomeElem ? nomeElem.textContent.trim() : '';
                var linkElem = box.querySelector('a');
                var linkHref = linkElem ? linkElem.getAttribute('href') : null;
                var link = linkHref ? 'https://campineira.com.br/' + linkHref : null;
                var naoIcone = ':not(.img_icone):not([src*="Imagens/icones"])';
                var imgElem = box.querySelector('figure img.img-responsive' + naoIcone) || box.querySelector('figure img' + naoIcone) || box.querySelector('.box-interno img' + naoIcone) || box.querySelector('img.img-responsive' + naoIcone) || box.querySelector('img' + naoIcone);
                var imagem = imgElem ? (
                    imgElem.getAttribute('data-src') || imgElem.getAttribute('data-lazy-src') ||
                    imgElem.getAttribute('data-original') || imgElem.getAttribute('data-lazy') ||
                    imgElem.getAttribute('src')
                ) : null;
                var form = null;
                var allForms = document.querySelectorAll('form');
                for (var j = 0; j < allForms.length; j++) {
                    var action = allForms[j].getAttribute('action') || '';
                    if (action.indexOf(id) !== -1) { form = allForms[j]; break; }
                }
                var estoque = null;
                var preco = null;
                if (form) {
                    var inp = form.querySelector('input[name="quantidade"]');
                    if (inp) { var max = inp.getAttribute('max'); estoque = max ? parseInt(max) : null; }
                    var precoElem = form.querySelector('span.col-lg-6.valor');
                    if (precoElem) { preco = precoElem.textContent.trim(); }
                }
                resultado.push({ id: id, nome: nome, preco: preco, estoque: estoque, link: link, imagem: imagem });
            }
            return resultado;
            """

            if cats_varrer:
                cats_upper = [c.upper() for c in cats_varrer]
                categorias = [c for c in categorias if c['nome'].upper() in cats_upper]

            for idx, cat in enumerate(categorias):
                nome_cat = cat['nome']
                atualizar(f"[{idx+1}/{len(categorias)}] {nome_cat}...")
                try:
                    driver.get(cat['url'])
                    time.sleep(3)
                    for link in driver.find_elements(By.TAG_NAME, "a"):
                        if link.text.strip().upper() == "TODAS":
                            driver.execute_script("arguments[0].click();", link)
                            break
                    time.sleep(4)

                    pagina = 1
                    pagina_alvo = paginas_ja_feitas.get(nome_cat)
                    if pagina_alvo:
                        categoria_ja_completa = False
                        atualizar(f"[{idx+1}/{len(categorias)}] {nome_cat} — retomando, avançando até a pág. {pagina_alvo + 1}...")
                        while pagina < pagina_alvo + 1:
                            pag_links_ff = driver.find_elements(By.CSS_SELECTOR, "ul.pagination a")
                            prox_ff = None
                            for link in pag_links_ff:
                                if link.text.strip() == ">":
                                    pai_ff = link.find_element(By.XPATH, "..")
                                    if "disabled" not in (pai_ff.get_attribute("class") or ""):
                                        prox_ff = link
                                        break
                            if not prox_ff:
                                categoria_ja_completa = True
                                break
                            url_antes_ff = driver.current_url
                            driver.execute_script("arguments[0].click();", prox_ff)
                            time.sleep(3)
                            if driver.current_url == url_antes_ff:
                                categoria_ja_completa = True
                                break
                            pagina += 1
                        if categoria_ja_completa:
                            continue

                    while True:
                        try:
                            produtos = driver.execute_script(SCRIPT_EXTRAI)
                        except Exception:
                            time.sleep(2)
                            produtos = driver.execute_script(SCRIPT_EXTRAI)

                        for p in produtos:
                            detalhes = {"fabricante": None, "ean": None,
                                        "tipo": None, "cor": None, "validade": None,
                                        "tamanho": None, "peso": None, "composicao": None}
                            if buscar_detalhes and p.get('link'):
                                try:
                                    driver.execute_script("window.open(arguments[0], '_blank');", p['link'])
                                    driver.switch_to.window(driver.window_handles[-1])
                                    time.sleep(1.5)
                                    detalhes = driver.execute_script("""
                                        var base = "div.col-lg-5.col-md-5.col-sm-12.col-xs-12.texto-produto";
                                        function getH2AposSpan(nthChild) {
                                            var spans = document.querySelectorAll(base + " span");
                                            var span = spans[nthChild];
                                            if (!span) return null;
                                            var next = span.nextElementSibling;
                                            while (next) {
                                                if (next.tagName === "H2") return next.textContent.trim();
                                                next = next.nextElementSibling;
                                            }
                                            return null;
                                        }
                                        var infos = {};
                                        var spans = document.querySelectorAll(base + " span");
                                        spans.forEach(function(span) {
                                            var txt = span.innerText || "";
                                            if (txt.includes("EAN:") || txt.includes("VALIDADE:") ||
                                                txt.includes("COMPOSIÇÃO:") || txt.includes("COR") ||
                                                txt.includes("QUANTIDADE") || txt.includes("TIPO") ||
                                                txt.includes("PESO") || txt.includes("TAMANHO") ||
                                                txt.includes("CAIXA MASTER")) {
                                                var linhas = txt.split("\\n");
                                                linhas.forEach(function(linha) {
                                                    linha = linha.trim();
                                                    if (linha.includes(":")) {
                                                        var idx2 = linha.indexOf(":");
                                                        var chave = linha.substring(0, idx2).trim().toLowerCase()
                                                            .replace(/ /g, "_")
                                                            .normalize("NFD").replace(/[\\u0300-\\u036f]/g, "");
                                                        var valor = linha.substring(idx2 + 1).trim();
                                                        if (chave && valor) infos[chave] = valor;
                                                    }
                                                });
                                            }
                                        });
                                        return {
                                            fabricante: getH2AposSpan(1),
                                            ...infos
                                        };
                                    """) or detalhes
                                    driver.close()
                                    driver.switch_to.window(driver.window_handles[0])
                                except Exception:
                                    try:
                                        while len(driver.window_handles) > 1:
                                            driver.switch_to.window(driver.window_handles[-1])
                                            driver.close()
                                        driver.switch_to.window(driver.window_handles[0])
                                    except Exception:
                                        pass

                            if buscar_detalhes and detalhes.get("imagem_produto"):
                                p["imagem"] = detalhes.pop("imagem_produto")
                            elif "imagem_produto" in detalhes:
                                detalhes.pop("imagem_produto")
                            produto_final = {**p, "categoria": nome_cat, **detalhes}
                            id_final = produto_final.get("id")

                            if id_final and id_final in ids_capturados_nesta_execucao:
                                continue  # mesma página relida por engano — já registrado nessa varredura
                            if id_final:
                                ids_capturados_nesta_execucao.add(id_final)

                            if id_final in ids_ja_publicados:
                                # Já publicado antes: não entra de novo na aba
                                # Publicar (por isso não chama registrar_produto_bq
                                # nem entra em todos_produtos), mas ainda passa
                                # pelo checkpoint pra atualizar estoque/custo no
                                # histórico se tiver mudado desde a publicação.
                                buffer_checkpoint.append(produto_final)
                                continue

                            todos_produtos.append(produto_final)
                            buffer_checkpoint.append(produto_final)
                            ok_bq, erro_bq = bq.registrar_produto_bq(client_bq_camp, id_captura, nome_cat, produto_final, pagina=pagina)
                            if not ok_bq and not bq_erro_reportado[0]:
                                bq_erro_reportado[0] = True
                                atualizar(f"⚠️ Falha ao gravar no BigQuery: {erro_bq}")

                        paginas_desde_ultimo_checkpoint[0] += 1
                        if paginas_desde_ultimo_checkpoint[0] >= PAGINAS_POR_CHECKPOINT:
                            atualizar(f"[{idx+1}/{len(categorias)}] {nome_cat} — pág. {pagina} "
                                      f"(checkpoint: gravando {len(buffer_checkpoint)} produtos no histórico)...")
                            _gravar_checkpoint_historico()
                        else:
                            atualizar(f"[{idx+1}/{len(categorias)}] {nome_cat} — pág. {pagina} "
                                      f"({len(todos_produtos)} produtos até agora)")

                        pag_links = driver.find_elements(By.CSS_SELECTOR, "ul.pagination a")
                        prox = None
                        for link in pag_links:
                            if link.text.strip() == ">":
                                pai = link.find_element(By.XPATH, "..")
                                if "disabled" not in (pai.get_attribute("class") or ""):
                                    prox = link
                                    break
                        if not prox:
                            break
                        url_antes = driver.current_url
                        driver.execute_script("arguments[0].click();", prox)
                        time.sleep(3)
                        if driver.current_url == url_antes:
                            break
                        pagina += 1

                except Exception as e:
                    atualizar(f"[{idx+1}/{len(categorias)}] ERRO em {nome_cat}: {str(e)[:50]}")
                    _gravar_checkpoint_historico()

            _gravar_checkpoint_historico()

            with open(ARQUIVO_RESULTADOS, "w", encoding="utf-8") as f:
                json.dump(todos_produtos, f, ensure_ascii=False)

            fim_dt = datetime.now()
            st_atual = ler_status()
            inicio_ts = st_atual.get("inicio_ts")
            duracao = None
            if inicio_ts:
                seg = int(fim_dt.timestamp() - inicio_ts)
                mins, segs = divmod(seg, 60)
                duracao = f"{mins}min {segs}s"
            salvar_status({
                "rodando": False, "progresso": f"Concluído! {len(todos_produtos)} produtos coletados.",
                "inicio": st_atual.get("inicio"), "inicio_ts": inicio_ts,
                "fim": fim_dt.strftime("%d/%m/%Y %H:%M:%S"), "duracao": duracao,
            })
        finally:
            driver.quit()

    except Exception as e:
        salvar_status({
            "rodando": False, "progresso": f"ERRO: {str(e)[:100]}",
            "inicio": None, "fim": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        })
