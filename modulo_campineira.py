# -*- coding: utf-8 -*-
# =============================================================================
# MÓDULO CAMPINEIRA - Varredura de Produtos
# Integrar no LeMarketplace.py na área logada
# =============================================================================
# COMO USAR:
# 1. Copie este arquivo para a mesma pasta do LeMarketplace.py
# 2. No LeMarketplace.py, adicione no menu lateral (dentro do if logado):
#
#    if st.sidebar.button("🏭 Campineira"):
#        st.session_state.pg = "Campineira"
#
# 3. Adicione a chamada da página:
#
#    elif st.session_state.pg == "Campineira":
#        from modulo_campineira import pagina_campineira
#        pagina_campineira()
#
# =============================================================================

import streamlit as st

# Importa calculadora do LeMarketplace
try:
    from LeMarketplace import calcular_venda_completo, converter_custo_seguro
except:
    # Fallback caso não consiga importar
    def converter_custo_seguro(valor_raw):
        if valor_raw is None or valor_raw == "": return 0.0
        if isinstance(valor_raw, (int, float)): return float(valor_raw)
        s = str(valor_raw).replace('R$','').replace(' ','').strip()
        try:
            if ',' in s and '.' in s:
                if s.find('.') < s.find(','): s = s.replace('.','').replace(',','.')
                else: s = s.replace(',','')
            elif ',' in s: s = s.replace(',','.')
            return float(s)
        except: return 0.0

    def calcular_venda_completo(custo_aquisicao, margem_percentual, mkt):
        imposto_tax = 0.06
        margem_alvo = margem_percentual / 100
        custo_embalagem = 1.00
        if mkt == "shein":
            comissao_mkt, taxa_fixa = 0.18, 5.0
        elif mkt == "shopee":
            comissao_mkt, taxa_fixa = 0.20, 4.0
        elif mkt == "temu":
            comissao_mkt, taxa_fixa = 0.0, 0.0
        elif mkt == "tiktok":
            comissao_mkt, taxa_fixa = 0.22, 4.0
        else:
            return 0, 0
        divisor = 1 - (comissao_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_embalagem + taxa_fixa) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comissao_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_embalagem - taxa_fixa
        return preco, lucro
import pandas as pd
import json
import os
import threading
from datetime import datetime

# ============================================================
# CONFIGURAÇÕES PADRÃO POR CATEGORIA
# ============================================================

CATEGORIAS = [
    "..:NATAL:..",
    ".: PROMOÇÕES :.",
    "AUTOMOTIVOS",
    "BRASIL",
    "BRINQUEDOS E JOGOS",
    "CAPAS E GUARDA-CHUVA",
    "CELULARES E INFORMÁTICA",
    "COMEMORATIVOS E SAZONAL",
    "CONFECÇÃO",
    "DECORAÇÃO/ORGANIZAÇÃO",
    "DIDÁTICOS/EDUCATIVOS",
    "DIVERSOS",
    "ELETRICOS/ELETRÔNICOS",
    "FERRAMENTAS/FERRAGENS",
    "FITNESS E FISIO",
    "HIGIENE E BELEZA",
    "JARDIM / CAÇA E PESCA",
    "LINHA BEBE",
    "MELAMINA",
    "MOCHILAS E ACESSÓRIOS",
    "PAPELARIA",
    "PET SHOP",
    "UD - ART. LIMPEZA",
    "UD - COPA/COZINHA",
    "UD - INOX",
    "UD - MADEIRA",
    "UD - PORCELANA",
    "UD - TÉRMICOS",
    "UD - VIDROS",
    "VERÃO INFLÁVEIS E PRAIA",
]

ARQUIVO_RESULTADOS = "campineira_resultados.json"
ARQUIVO_STATUS     = "campineira_status.json"

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def salvar_status(status: dict):
    with open(ARQUIVO_STATUS, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)

def ler_status() -> dict:
    if not os.path.exists(ARQUIVO_STATUS):
        return {"rodando": False, "progresso": "", "inicio": None, "fim": None}
    with open(ARQUIVO_STATUS, encoding="utf-8") as f:
        return json.load(f)

def ler_resultados() -> list:
    if not os.path.exists(ARQUIVO_RESULTADOS):
        return []
    with open(ARQUIVO_RESULTADOS, encoding="utf-8") as f:
        return json.load(f)

MARGEM_PADRAO = 15.0

def calcular_precos_sugeridos(preco_str):
    try:
        custo = float(str(preco_str).replace("R$","").replace(".","").replace(",",".").strip())
    except:
        return {}
    precos = {}
    for mkt in ["shein", "shopee", "temu", "tiktok"]:
        p, l = calcular_venda_completo(custo, MARGEM_PADRAO, mkt)
        precos[f"preco_{mkt}"] = round(p, 2)
        precos[f"lucro_{mkt}"] = round(l, 2)
    return precos

def filtrar_resultados(dados, filtros_cat):
    resultado = []
    for p in dados:
        cat = p.get("categoria", "")
        cfg = filtros_cat.get(cat, {"estoque_min": 70, "preco_min": 4.99})
        est = p.get("estoque") or 0
        preco_str = p.get("preco") or "R$ 0"
        try:
            preco_num = float(preco_str.replace("R$","").replace(".","").replace(",",".").strip())
        except:
            preco_num = 0
        if est >= cfg["estoque_min"] and preco_num >= cfg["preco_min"]:
            sugeridos = calcular_precos_sugeridos(preco_str)
            resultado.append({**p, "preco_num": preco_num, **sugeridos})
    return resultado

# ============================================================
# RPA EM BACKGROUND
# ============================================================

def rodar_rpa_background(filtros_cat, cats_varrer=None, buscar_detalhes=False):
    """Roda o RPA em thread separada para não travar o Streamlit"""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
        import time

        inicio_dt = datetime.now()
        salvar_status({"rodando": True, "progresso": "Iniciando...", 
                       "inicio": inicio_dt.strftime("%d/%m/%Y %H:%M:%S"),
                       "inicio_ts": inicio_dt.timestamp(),
                       "fim": None, "duracao": None})

        # Chrome em modo headless
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

        def atualizar(msg):
            status = ler_status()
            status["progresso"] = msg
            salvar_status(status)

        try:
            # LOGIN
            atualizar("Fazendo login...")
            driver.get("https://campineira.com.br/index.php")
            time.sleep(5)
            driver.find_element(By.CSS_SELECTOR, "input[name='usuario'].login-baixa").send_keys("DL")
            driver.find_element(By.CSS_SELECTOR, "input[name='senha'].login-baixa").send_keys("Gele1826")
            driver.find_elements(By.XPATH, "//button[normalize-space(text())='OK']")[1].click()
            time.sleep(5)

            # COLETA CATEGORIAS
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

            # Remove duplicados
            vistos = set()
            categorias = []
            for c in cats_js:
                if c['nome'] not in vistos:
                    vistos.add(c['nome'])
                    categorias.append(c)

            todos_produtos = []

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
                var imgElem = box.querySelector('img');
                var imagem = imgElem ? imgElem.getAttribute('src') : null;
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

            # Filtra categorias da fila (se especificadas)
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
                    url_anterior = ""

                    while True:
                        produtos = driver.execute_script(SCRIPT_EXTRAI)
                        for p in produtos:
                            # Busca detalhes completos (opcional)
                            detalhes = {"fabricante": None, "caixa_com": None, "ean": None,
                                        "tipo": None, "cor": None, "validade": None,
                                        "tamanho": None, "peso": None, "composicao": None}
                            if buscar_detalhes and p.get('link'):
                                try:
                                    driver.execute_script("window.open(arguments[0], '_blank');", p['link'])
                                    driver.switch_to.window(driver.window_handles[-1])
                                    import time as _time
                                    _time.sleep(1.5)
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
                                                        var idx = linha.indexOf(":");
                                                        var chave = linha.substring(0, idx).trim().toLowerCase()
                                                            .replace(/ /g, "_")
                                                            .normalize("NFD").replace(/[\\u0300-\\u036f]/g, "");
                                                        var valor = linha.substring(idx + 1).trim();
                                                        if (chave && valor) infos[chave] = valor;
                                                    }
                                                });
                                            }
                                        });
                                        return {
                                            fabricante: getH2AposSpan(1),
                                            caixa_com:  getH2AposSpan(2),
                                            ...infos
                                        };
                                    """) or detalhes
                                    driver.close()
                                    driver.switch_to.window(driver.window_handles[0])
                                except:
                                    try:
                                        driver.switch_to.window(driver.window_handles[0])
                                    except:
                                        pass
                            # Se modo detalhado, usa imagem da página do produto (melhor qualidade)
                            if buscar_detalhes and detalhes.get("imagem_produto"):
                                p["imagem"] = detalhes.pop("imagem_produto")
                            elif "imagem_produto" in detalhes:
                                detalhes.pop("imagem_produto")
                            todos_produtos.append({**p, "categoria": nome_cat, **detalhes})

                        # Próxima página
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

            # SALVA RESULTADOS
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
                "rodando": False,
                "progresso": f"Concluído! {len(todos_produtos)} produtos coletados.",
                "inicio": st_atual.get("inicio"),
                "inicio_ts": inicio_ts,
                "fim": fim_dt.strftime("%d/%m/%Y %H:%M:%S"),
                "duracao": duracao
            })

        finally:
            driver.quit()

    except Exception as e:
        salvar_status({
            "rodando": False,
            "progresso": f"ERRO: {str(e)[:100]}",
            "inicio": None,
            "fim": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        })

# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

def pagina_campineira():
    st.markdown("## 🏭 Campineira — Varredura de Produtos")
    st.markdown("---")

    status = ler_status()
    resultados_brutos = ler_resultados()

    # ---- ABA DE CONFIGURAÇÃO ----
    if "pub_excluidos" not in st.session_state:
        st.session_state["pub_excluidos"] = set()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚙️ Configurar e Rodar", "📦 Resultados", "🖼️ Galeria", "🚀 Publicar", "🏪 Enviar para Lojas"])

    # ============================================================
    # TAB 1 — CONFIGURAÇÃO
    # ============================================================
    with tab1:
        st.markdown("### Configurar Varredura")

        # Inicializa fila no session_state
        if "campineira_fila" not in st.session_state:
            st.session_state["campineira_fila"] = []

        # Seletor para adicionar categoria
        st.markdown("**Adicionar categoria à fila:**")
        col_a, col_b, col_c, col_d = st.columns([3, 1.5, 1.5, 1])

        with col_a:
            opcoes_cats = ["Todas"] + CATEGORIAS
            cat_sel = st.selectbox("Categoria", opcoes_cats, label_visibility="collapsed")
        with col_b:
            est_input = st.number_input("Estoque mín.", min_value=0, value=70, step=5, label_visibility="collapsed")
        with col_c:
            preco_input = st.number_input("Preço mín. R$", min_value=0.0, value=4.99, step=0.50, label_visibility="collapsed")
        with col_d:
            st.markdown("<div style='padding-top:26px'></div>", unsafe_allow_html=True)
            if st.button("➕", use_container_width=True):
                if cat_sel == "Todas":
                    # Adiciona todas as categorias de uma vez
                    st.session_state["campineira_fila"] = [
                        {"cat": c, "estoque_min": est_input, "preco_min": preco_input}
                        for c in CATEGORIAS
                    ]
                    st.success("Todas as categorias adicionadas!")
                else:
                    # Evita duplicata
                    cats_na_fila = [f["cat"] for f in st.session_state["campineira_fila"]]
                    if cat_sel not in cats_na_fila:
                        st.session_state["campineira_fila"].append({
                            "cat": cat_sel,
                            "estoque_min": est_input,
                            "preco_min": preco_input
                        })
                    else:
                        st.warning(f"{cat_sel} já está na fila!")
                st.rerun()

        # Mostra fila atual
        fila = st.session_state.get("campineira_fila", [])

        if fila:
            st.markdown("---")
            st.markdown(f"**Fila de varredura ({len(fila)} categoria(s)):**")

            for i, item in enumerate(fila):
                col1, col2, col3, col4 = st.columns([4, 1.5, 1.5, 0.5])
                col1.markdown(f"🗂️ **{item['cat']}**")
                col2.markdown(f"Est ≥ **{item['estoque_min']}**")
                col3.markdown(f"R$ ≥ **{item['preco_min']:.2f}**")
                if col4.button("❌", key=f"rm_{i}"):
                    st.session_state["campineira_fila"].pop(i)
                    st.rerun()

            st.markdown("---")

            # Checkbox detalhes — aparece sempre que há fila
            buscar_det = st.checkbox(
                "🔍 Buscar detalhes do produto (EAN, Fabricante, Cor, Composição...)",
                value=st.session_state.get("campineira_buscar_detalhes", False),
                key="chk_buscar_det",
                help="⚠️ Aumenta o tempo — acessa a página de cada produto individualmente."
            )
            st.session_state["campineira_buscar_detalhes"] = buscar_det
            if buscar_det:
                st.warning("⚠️ Modo detalhado ativo — a varredura será mais lenta (≈1.5s por produto).")

            st.markdown("---")

            col_btn1, col_btn2 = st.columns(2)

            with col_btn1:
                if status.get("rodando"):
                    st.warning(f"⏳ Varredura em andamento...\n\n**{status.get('progresso', '')}**")
                    st.info("🔄 Atualizando automaticamente a cada 5 segundos...")
                    import time as _t
                    _t.sleep(5)
                    st.rerun()
                else:
                    label_btn = f"🚀 Iniciar Varredura ({len(fila)} categoria(s))"
                    if st.button(label_btn, type="primary", use_container_width=True):
                        # Monta filtros e lista de categorias
                        filtros_cat = {
                            item["cat"]: {"estoque_min": item["estoque_min"], "preco_min": item["preco_min"]}
                            for item in fila
                        }
                        cats_varrer = [item["cat"] for item in fila]
                        st.session_state["campineira_filtros"] = filtros_cat

                        buscar_det = st.session_state.get("campineira_buscar_detalhes", False)
                        t = threading.Thread(
                            target=rodar_rpa_background,
                            args=(filtros_cat, cats_varrer, buscar_det),
                            daemon=True
                        )
                        t.start()
                        st.success("Varredura iniciada! Acompanhe na aba Resultados.")
                        st.rerun()

            with col_btn2:
                if resultados_brutos:
                    duracao_txt = status.get('duracao')
                    duracao_linha = f"\n\n⏱️ Duração: **{duracao_txt}**" if duracao_txt else ""
                    st.info(f"📊 Última varredura: **{len(resultados_brutos)}** produtos\n\n"
                            f"🕐 Início: {status.get('inicio', 'N/A')}\n\n"
                            f"✅ Fim: {status.get('fim', 'N/A')}"
                            f"{duracao_linha}")

            if st.button("🗑️ Limpar fila", use_container_width=False):
                st.session_state["campineira_fila"] = []
                st.rerun()
        else:
            st.info("Nenhuma categoria na fila. Selecione uma categoria e clique em ✅ OK.")

    # ============================================================
    # TAB 2 — RESULTADOS EM TABELA
    # ============================================================
    with tab2:
        st.markdown("### Produtos Validados")

        if not resultados_brutos:
            st.info("Nenhuma varredura realizada ainda. Vá para a aba ⚙️ e inicie uma varredura.")
        else:
            filtros = st.session_state.get("campineira_filtros", {
                cat: {"estoque_min": 70, "preco_min": 4.99} for cat in CATEGORIAS
            })

            validados = filtrar_resultados(resultados_brutos, filtros)

            # Filtros rápidos
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                cats_disp = ["Todas"] + sorted(set(p['categoria'] for p in validados))
                cat_sel = st.selectbox("Filtrar categoria", cats_disp)
            with col_f2:
                busca = st.text_input("Buscar produto", "")
            with col_f3:
                ordem = st.selectbox("Ordenar por", ["Estoque (maior)", "Estoque (menor)", "Preço (maior)", "Preço (menor)"])

            # Aplica filtros
            if cat_sel != "Todas":
                validados = [p for p in validados if p['categoria'] == cat_sel]
            if busca:
                validados = [p for p in validados if busca.upper() in p['nome'].upper()]

            # Ordena
            if ordem == "Estoque (maior)":
                validados.sort(key=lambda x: x.get('estoque') or 0, reverse=True)
            elif ordem == "Estoque (menor)":
                validados.sort(key=lambda x: x.get('estoque') or 0)
            elif ordem == "Preço (maior)":
                validados.sort(key=lambda x: x.get('preco_num') or 0, reverse=True)
            elif ordem == "Preço (menor)":
                validados.sort(key=lambda x: x.get('preco_num') or 0)

            st.success(f"✅ **{len(validados)}** produtos validados de **{len(resultados_brutos)}** coletados")

            # Exporta Excel
            if validados:
                df_exp = pd.DataFrame([{
                    "ID": p.get('id'),
                    "Categoria": p.get('categoria'),
                    "Nome": p.get('nome'),
                    "Estoque": p.get('estoque'),
                    "Custo_Campineira": p.get('preco'),
                    "Preco_Shein_15pct": p.get('preco_shein'),
                    "Preco_Shopee_15pct": p.get('preco_shopee'),
                    "Preco_Temu_15pct": p.get('preco_temu'),
                    "Preco_TikTok_15pct": p.get('preco_tiktok'),
                    "Lucro_Shein": p.get('lucro_shein'),
                    "Lucro_Shopee": p.get('lucro_shopee'),
                    "Lucro_Temu": p.get('lucro_temu'),
                    "Lucro_TikTok": p.get('lucro_tiktok'),
                    "EAN": p.get('ean'),
                    "Fabricante": p.get('fabricante'),
                    "Caixa_com": p.get('caixa_com'),
                    "Quantidade": p.get('quantidade'),
                    "Cor_Cores": p.get('cores') or p.get('cor'),
                    "Composicao": p.get('composicao'),
                    "Validade": p.get('validade'),
                    "Tamanho": p.get('tamanho') or p.get('tamanho_aproximado'),
                    "Peso": p.get('peso') or p.get('peso_aproximado'),
                    "Tipo": p.get('tipo') or p.get('tipo_de_produto'),
                    "Caixa_Master": p.get('caixa_master'),
                    "Link": p.get('link'),
                } for p in validados])
                excel_buf = __import__('io').BytesIO()
                df_exp.to_excel(excel_buf, index=False, engine='openpyxl')
                excel_buf.seek(0)
                st.download_button(
                    "📥 Baixar Excel",
                    data=excel_buf,
                    file_name=f"campineira_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            # Tabela
            if validados:
                df_show = pd.DataFrame([{
                    "ID": p.get('id'),
                    "Categoria": p.get('categoria'),
                    "Nome": p.get('nome'),
                    "Estoque": p.get('estoque'),
                    "Custo (Campineira)": p.get('preco'),
                    "💛 Shein": f"R$ {p.get('preco_shein', 0):.2f}",
                    "🟠 Shopee": f"R$ {p.get('preco_shopee', 0):.2f}",
                    "🟡 Temu": f"R$ {p.get('preco_temu', 0):.2f}",
                    "⚫ TikTok": f"R$ {p.get('preco_tiktok', 0):.2f}",
                    "EAN": p.get('ean'),
                    "Fabricante": p.get('fabricante'),
                    "Caixa com": p.get('caixa_com'),
                    "Quantidade": p.get('quantidade'),
                    "Cor/Cores": p.get('cores') or p.get('cor'),
                    "Composição": p.get('composicao'),
                    "Validade": p.get('validade'),
                    "Tamanho": p.get('tamanho') or p.get('tamanho_aproximado'),
                    "Peso": p.get('peso') or p.get('peso_aproximado'),
                    "Tipo": p.get('tipo') or p.get('tipo_de_produto'),
                    "Caixa Master": p.get('caixa_master'),
                    "Link": p.get('link'),
                    "Imagem": p.get('imagem'),
                } for p in validados])

                # Filtra imagens inválidas (caminhos locais)
                df_show["Imagem"] = df_show["Imagem"].apply(
                    lambda x: x if x and x.startswith("http") else None
                )
                st.dataframe(df_show, use_container_width=True, hide_index=True,
                             column_config={
                                 "Link": st.column_config.LinkColumn("Link"),
                                 "Imagem": st.column_config.ImageColumn("Foto", width="small"),
                             })

    # ============================================================
    # TAB 3 — GALERIA COM IMAGENS
    # ============================================================
    with tab3:
        st.markdown("### Galeria de Produtos")

        if not resultados_brutos:
            st.info("Nenhuma varredura realizada ainda.")
        else:
            filtros = st.session_state.get("campineira_filtros", {
                cat: {"estoque_min": 70, "preco_min": 4.99} for cat in CATEGORIAS
            })

            validados = filtrar_resultados(resultados_brutos, filtros)

            col_f1, col_f2 = st.columns(2)
            with col_f1:
                cats_disp = ["Todas"] + sorted(set(p['categoria'] for p in validados))
                cat_sel = st.selectbox("Filtrar categoria", cats_disp, key="gal_cat")
            with col_f2:
                busca = st.text_input("Buscar produto", "", key="gal_busca")

            if cat_sel != "Todas":
                validados = [p for p in validados if p['categoria'] == cat_sel]
            if busca:
                validados = [p for p in validados if busca.upper() in p['nome'].upper()]

            st.info(f"**{len(validados)}** produtos")

            cols_por_linha = 4
            for i in range(0, len(validados), cols_por_linha):
                cols = st.columns(cols_por_linha)
                for j, p in enumerate(validados[i:i+cols_por_linha]):
                    with cols[j]:
                        if p.get('imagem'):
                            try:
                                st.image(p['imagem'], use_container_width=True)
                            except:
                                st.markdown("🖼️", unsafe_allow_html=True)
                        st.markdown(f"**{p['nome'][:50]}**")
                        st.markdown(f"🏷️ {p.get('preco', 'N/A')}  |  📦 {p.get('estoque', '?')} un")
                        st.markdown(f"📁 *{p.get('categoria', '')}*")
                        if p.get('link'):
                            st.markdown(f"[Ver produto]({'https://campineira.com.br/' + p['link'] if not p['link'].startswith('http') else p['link']})")
                        st.markdown("---")

    # ============================================================
    # TAB 4 — PUBLICAR NO UPSELLER
    # ============================================================
    with tab4:
        st.markdown("### 🚀 Publicar Produtos no Upseller")
        st.markdown("---")

        try:
            from modulo_upseller import widget_login_upseller
        except ImportError:
            st.error("❌ Arquivo `modulo_upseller.py` não encontrado na mesma pasta!")
            st.stop()

        driver_ups = widget_login_upseller()

        st.markdown("---")
        st.markdown("### 📦 Produtos Validados para Publicar")

        if not resultados_brutos:
            st.info("Nenhuma varredura realizada. Vá para ⚙️ Configurar e Rodar.")
        else:
            filtros = st.session_state.get("campineira_filtros", {
                cat: {"estoque_min": 70, "preco_min": 4.99} for cat in CATEGORIAS
            })
            validados = filtrar_resultados(resultados_brutos, filtros)

            col_f1, col_f2 = st.columns(2)
            with col_f1:
                cats_disp = ["Todas"] + sorted(set(p['categoria'] for p in validados))
                cat_pub = st.selectbox("Filtrar categoria", cats_disp, key="pub_cat")
            with col_f2:
                busca_pub = st.text_input("Buscar produto", "", key="pub_busca")

            if cat_pub != "Todas":
                validados = [p for p in validados if p['categoria'] == cat_pub]
            if busca_pub:
                validados = [p for p in validados if busca_pub.upper() in p['nome'].upper()]

            # Remove produtos excluídos manualmente
            excluidos = st.session_state.get("pub_excluidos", set())
            validados = [p for p in validados if p.get('id') not in excluidos]

            col_inf, col_rest = st.columns([3,1])
            with col_inf:
                st.info(f"**{len(validados)}** produtos prontos para publicar")
            with col_rest:
                if excluidos and st.button("↩️ Restaurar removidos", use_container_width=True):
                    st.session_state["pub_excluidos"] = set()
                    st.rerun()

            for idx, p in enumerate(validados):
                with st.container(border=True):
                    col_img, col_info, col_btn = st.columns([1, 4, 1.5])

                    with col_img:
                        if p.get('imagem'):
                            try:
                                st.image(p['imagem'], use_container_width=True)
                            except:
                                st.markdown("🖼️")

                    with col_info:
                        st.markdown(f"**{p.get('nome', '')}**")
                        st.markdown(
                            f"📦 Estoque: **{p.get('estoque', '?')}** | "
                            f"💰 Custo: **{p.get('preco', 'N/A')}** | "
                            f"📁 {p.get('categoria', '')}"
                        )
                        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                        col_p1.metric("💛 Shein", f"R$ {p.get('preco_shein', 0):.2f}")
                        col_p2.metric("🟠 Shopee", f"R$ {p.get('preco_shopee', 0):.2f}")
                        col_p3.metric("🟡 Temu", f"R$ {p.get('preco_temu', 0):.2f}")
                        col_p4.metric("⚫ TikTok", f"R$ {p.get('preco_tiktok', 0):.2f}")

                    with col_btn:
                        st.markdown("<div style='padding-top:20px'></div>", unsafe_allow_html=True)
                        publicado = st.session_state.get(f"pub_{p.get('id')}", False)
                        if publicado:
                            msg = st.session_state.get(f"pub_msg_{p.get('id')}", "✅ Publicado!")
                            st.success(msg)
                        elif st.session_state.get("ups_logado"):
                            if st.button("🚀 Publicar", key=f"btn_pub_{idx}", use_container_width=True, type="primary"):
                                with st.spinner("Publicando..."):
                                    from modulo_upseller import publicar_produto_upseller, get_proximo_sku
                                    driver = st.session_state.get("ups_driver")
                                    sucesso, msg = publicar_produto_upseller(driver, p)
                                    st.session_state[f"pub_{p.get('id')}"] = sucesso
                                    st.session_state[f"pub_msg_{p.get('id')}"] = msg
                                    # Salva SKU gerado para usar na etapa 2
                                    if sucesso:
                                        import json, os
                                        f_sku = "upseller_sku_counter.json"
                                        if os.path.exists(f_sku):
                                            with open(f_sku) as f:
                                                num = json.load(f).get("contador", 1)
                                            st.session_state[f"pub_sku_{p.get('id')}"] = f"RJ-{num:05d}"
                                    st.rerun()
                        else:
                            st.button("🔒 Publicar", key=f"btn_pub_dis_{idx}", disabled=True,
                                      use_container_width=True, help="Faça login no Upseller primeiro")
                        # Botão excluir da lista
                        if not publicado:
                            if st.button("🗑️ Remover", key=f"btn_rem_{idx}", use_container_width=True):
                                st.session_state["pub_excluidos"].add(p.get('id'))
                                st.rerun()

    # ============================================================
    # TAB 5 — ENVIAR PARA LOJAS (PÓS-PUBLICAÇÃO)
    # ============================================================
    with tab5:
        st.markdown("### 🏪 Pipeline Completo de Publicação")

        # Status das etapas em legenda
        col_l1, col_l2, col_l3, col_l4, col_l5 = st.columns(5)
        col_l1.info("1️⃣ Armazém")
        col_l2.info("2️⃣ → Shopee")
        col_l3.info("3️⃣ Shopee OK")
        col_l4.info("4️⃣ → Shein/Temu/TikTok")
        col_l5.info("5️⃣ Todas OK")
        st.markdown("---")
        st.markdown("### 🏪 Enviar Produtos para as Lojas")
        st.info("Produtos que passaram pela Etapa 1 (Publicar) ficam aqui para as etapas seguintes.")
        st.markdown("---")

        # Lista produtos já publicados
        publicados = []
        for p in filtrar_resultados(resultados_brutos, st.session_state.get("campineira_filtros", {})):
            pid = p.get('id')
            if st.session_state.get(f"pub_{pid}") and st.session_state.get(f"pub_sku_{pid}"):
                publicados.append({
                    **p,
                    "sku_upseller": st.session_state.get(f"pub_sku_{pid}")
                })

        if not publicados:
            st.warning("Nenhum produto publicado ainda. Vá para a aba 🚀 Publicar primeiro.")
        else:
            st.success(f"**{len(publicados)}** produto(s) prontos para enviar às lojas")

            for idx, p in enumerate(publicados):
                sku = p.get("sku_upseller", "")
                nome = p.get("nome", "")
                etapa2_ok = st.session_state.get(f"etapa2_{sku}", False)
                etapa3_ok = st.session_state.get(f"etapa3_{sku}", False)

                with st.container(border=True):
                    col_img, col_info, col_acoes = st.columns([1, 4, 2])

                    with col_img:
                        if p.get('imagem'):
                            try:
                                st.image(p['imagem'], use_container_width=True)
                            except:
                                st.markdown("🖼️")

                    with col_info:
                        st.markdown(f"**{nome}**")
                        st.markdown(f"🏷️ SKU: `{sku}` | 📁 {p.get('categoria','')}")

                        # Status das etapas
                        col_s1, col_s2, col_s3 = st.columns(3)
                        col_s1.success("✅ Etapa 1")
                        col_s2.success("✅ Etapa 2") if etapa2_ok else col_s2.warning("⏳ Etapa 2")
                        col_s3.success("✅ Etapa 3") if etapa3_ok else col_s3.warning("⏳ Etapa 3")

                    with col_acoes:
                        st.markdown("<div style='padding-top:10px'></div>", unsafe_allow_html=True)
                        driver = st.session_state.get("ups_driver")

                        if not st.session_state.get("ups_logado"):
                            st.warning("Faça login na aba 🚀 Publicar")

                        # ── ETAPA 2: Copiar para Shopee ──────
                        elif not etapa2_ok:
                            if st.button("2️⃣ Enviar → Shopee", key=f"e2_{idx}", use_container_width=True, type="primary"):
                                with st.spinner("Enviando para Shopee..."):
                                    from modulo_upseller import etapa2_copiar_para_lojas
                                    sucesso, msg = etapa2_copiar_para_lojas(driver, sku)
                                    st.session_state[f"etapa2_{sku}"] = sucesso
                                    if sucesso: st.success(msg)
                                    else: st.error(msg)
                                    st.rerun()

                        # ── ETAPA 3: Rascunho Shopee ─────────
                        elif not etapa3_ok:
                            etapa3_aberto = st.session_state.get(f"etapa3_aberto_{sku}", False)
                            if not etapa3_aberto:
                                if st.button("3️⃣ Editar Rascunho Shopee", key=f"e3_{idx}", use_container_width=True, type="primary"):
                                    with st.spinner("Abrindo rascunho Shopee..."):
                                        from modulo_upseller import etapa3_editar_rascunho
                                        sucesso, msg, cat = etapa3_editar_rascunho(driver, sku, nome)
                                        if sucesso:
                                            st.session_state[f"etapa3_aberto_{sku}"] = True
                                            st.session_state[f"etapa3_cat_{sku}"] = cat
                                        else: st.error(msg)
                                        st.rerun()
                            else:
                                cat = st.session_state.get(f"etapa3_cat_{sku}", "")
                                if cat: st.info(f"🤖 **{cat}**")
                                if st.button("🚀 Preencher + Publicar Shopee", key=f"e3f_{idx}", use_container_width=True, type="primary"):
                                    with st.spinner("Publicando na Shopee..."):
                                        from modulo_upseller import preencher_rascunho_shopee, finalizar_rascunho
                                        sucesso, msg = preencher_rascunho_shopee(driver, p, sku, cat)
                                        if sucesso:
                                            finalizar_rascunho(driver)
                                            st.session_state[f"etapa3_{sku}"] = True
                                            st.success("✅ Publicado na Shopee!")
                                        else: st.error(msg)
                                        st.rerun()

                        # ── ETAPA 4: Migrar para Shein/Temu/TikTok ──
                        elif not st.session_state.get(f"etapa4_{sku}"):
                            if st.button("4️⃣ Migrar → Shein/Temu/TikTok", key=f"e4_{idx}", use_container_width=True, type="primary"):
                                with st.spinner("Migrando anúncio..."):
                                    from modulo_upseller import etapa4_migrar_para_lojas
                                    sucesso, msg = etapa4_migrar_para_lojas(driver, sku)
                                    st.session_state[f"etapa4_{sku}"] = sucesso
                                    if sucesso: st.success(msg)
                                    else: st.error(msg)
                                    st.rerun()

                        # ── ETAPA 5: Rascunhos por plataforma ──
                        else:
                            plataformas_ok = st.session_state.get(f"plataformas_ok_{sku}", [])
                            pendentes = [pl for pl in ["shein","temu","tiktok"] if pl not in plataformas_ok]

                            if pendentes:
                                pl = pendentes[0]
                                label_pl = {"shein":"Shein","temu":"Temu","tiktok":"TikTok"}[pl]
                                if st.button(f"5️⃣ Publicar {label_pl}", key=f"e5_{pl}_{idx}", use_container_width=True, type="primary"):
                                    with st.spinner(f"Publicando na {label_pl}..."):
                                        from modulo_upseller import editar_rascunho_plataforma
                                        sucesso, msg = editar_rascunho_plataforma(driver, sku, p, pl)
                                        if sucesso:
                                            ok_list = st.session_state.get(f"plataformas_ok_{sku}", [])
                                            ok_list.append(pl)
                                            st.session_state[f"plataformas_ok_{sku}"] = ok_list
                                            st.success(msg)
                                        else:
                                            st.error(msg)
                                        st.rerun()
                                if plataformas_ok:
                                    st.caption(f"✅ Já publicado: {', '.join(plataformas_ok)}")
                            else:
                                st.success("🎉 Publicado em todas as plataformas!")