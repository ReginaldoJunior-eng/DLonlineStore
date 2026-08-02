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
#        pagina_campineira(client_bq)   # reaproveita a conexão BigQuery já aberta
#
# =============================================================================

import streamlit as st
import re

# Cálculo de preço/lucro fica num módulo neutro compartilhado com LeMarketplace.py —
# NUNCA importar de "LeMarketplace" diretamente aqui: é o script principal rodado
# pelo Streamlit, e importar dele re-executa o arquivo inteiro (sidebar, botões,
# tudo) como efeito colateral, causando erro de "multiple button elements with the
# same auto-generated ID" (e a sidebar/cabeçalho aparecendo duplicados na tela).
from calculos_marketplace import calcular_venda_completo, converter_custo_seguro
import pandas as pd
import json
import os
import threading
from datetime import datetime
from google.cloud import bigquery
from google.oauth2 import service_account

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
ARQUIVO_EXCLUIDOS  = "campineira_excluidos.json"
TABLE_CAMPINEIRA   = "leandro-marketplace.DL_Store_Online.tb_resultado_produtos_campineira"
TABLE_PIPELINE     = "leandro-marketplace.DL_Store_Online.tb_pipeline_publicacao_campineira"
TABLE_SKU_REGISTRO = "leandro-marketplace.DL_Store_Online.tb_sku_registrados"
TABLE_HISTORICO    = "leandro-marketplace.DL_Store_Online.tb_historico_produtos_campineira"
TABLE_HISTORICO_STAGE = "leandro-marketplace.DL_Store_Online.tb_stage_historico_campineira"
TABLE_EXCLUIDOS    = "leandro-marketplace.DL_Store_Online.tb_campineira_excluidos"

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

def _sem_nan(valor):
    """Converte NaN do pandas (é assim que to_dataframe() representa um NULL
    de uma coluna STRING) em None de verdade. NaN é "truthy" em Python
    (bool(nan) é True), então um `if not campo:` não pega esse caso — o valor
    NaN (float) vazava pra frente e quebrava funções que esperam string, tipo
    extrair_dimensoes/extrair_peso_gramas em modulo_upseller.py ("expected
    string or bytes-like object, got 'float'"). `valor != valor` só é True
    quando valor é NaN — funciona sem precisar checar tipo ou importar pandas."""
    return None if valor != valor else valor

def ler_resultados(client=None) -> list:
    """Lê o resultado da varredura mais recente. Prioriza o BigQuery
    (tb_resultado_produtos_campineira) — essa tabela já recebe cada produto em
    tempo real, um por um, durante a varredura (ver registrar_produto_bq), então
    sobrevive mesmo se a varredura travar/cair no meio: ao reabrir a tela, o que
    já foi capturado até o momento da queda continua lá. Cai pro arquivo JSON
    local só se o BigQuery estiver indisponível (fallback, não fonte principal)."""
    if client is not None:
        try:
            q = f"""
                SELECT * FROM `{TABLE_CAMPINEIRA}`
                WHERE id_captura = (SELECT MAX(id_captura) FROM `{TABLE_CAMPINEIRA}`)
            """
            df = client.query(q).to_dataframe()
            if not df.empty:
                produtos = []
                for _, row in df.iterrows():
                    produtos.append({
                        "id": _sem_nan(row.get("id_produto")),
                        "nome": _sem_nan(row.get("nome")),
                        "categoria": _sem_nan(row.get("categoria")),
                        "estoque": row.get("estoque"),
                        "preco": _sem_nan(row.get("custo_campineira")),
                        "ean": _sem_nan(row.get("ean")),
                        "fabricante": _sem_nan(row.get("fabricante")),
                        "caixa_com": _sem_nan(row.get("caixa_com")),
                        "quantidade": _sem_nan(row.get("quantidade")),
                        "cores": _sem_nan(row.get("cor_cores")),
                        "composicao": _sem_nan(row.get("composicao")),
                        "validade": _sem_nan(row.get("validade")),
                        "tamanho": _sem_nan(row.get("tamanho")),
                        "peso": _sem_nan(row.get("peso")),
                        "tipo": _sem_nan(row.get("tipo")),
                        "caixa_master": _sem_nan(row.get("caixa_master")),
                        "link": _sem_nan(row.get("link")),
                        "imagem": _sem_nan(row.get("imagem")),
                    })
                return produtos
        except Exception:
            pass
    if not os.path.exists(ARQUIVO_RESULTADOS):
        return []
    with open(ARQUIVO_RESULTADOS, encoding="utf-8") as f:
        return json.load(f)

def carregar_excluidos(client=None) -> set:
    """Carrega os produtos removidos manualmente da fila de publicação. Prioriza
    BigQuery (tb_campineira_excluidos) — session_state E arquivo local são
    perdidos a cada reinício do container no Streamlit Cloud, o que fazia um
    item removido "voltar sozinho" depois de qualquer restart/redeploy. Arquivo
    local só entra como fallback se o BigQuery estiver indisponível."""
    if client is not None:
        try:
            df = client.query(
                f"SELECT DISTINCT id_produto FROM `{TABLE_EXCLUIDOS}`"
            ).to_dataframe()
            return set(df["id_produto"].astype(str))
        except Exception:
            pass
    if not os.path.exists(ARQUIVO_EXCLUIDOS):
        return set()
    try:
        with open(ARQUIVO_EXCLUIDOS, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def salvar_excluidos(excluidos: set, client=None):
    if client is not None:
        try:
            import pandas as pd
            linhas = [{"id_produto": str(x), "data_exclusao": datetime.utcnow().isoformat()} for x in excluidos]
            df = pd.DataFrame(linhas, columns=["id_produto", "data_exclusao"])
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
            client.load_table_from_dataframe(df, TABLE_EXCLUIDOS, job_config=job_config).result()
            return
        except Exception:
            pass
    try:
        with open(ARQUIVO_EXCLUIDOS, "w", encoding="utf-8") as f:
            json.dump(list(excluidos), f, ensure_ascii=False)
    except Exception:
        pass

@st.cache_data(ttl=3600, show_spinner=False)
def carregar_imagem_bytes(url):
    """Baixa a imagem com o header Referer que a Campineira exige antes de mostrar
    no Streamlit. st.image(url) direto deixa o NAVEGADOR buscar a imagem, sem esse
    header — a Campineira bloqueia esse acesso (proteção contra hotlink) e a
    miniatura aparece quebrada mesmo com a URL certa. Cacheado por 1h pra não
    rebaixar a mesma imagem a cada rerun da tela.

    Usa curl_cffi (não requests) — confirmado em produção que a Campineira
    passou a bloquear pelo "fingerprint" TLS da conexão, não só pelos headers:
    a mesma URL, com os mesmos headers, funciona no PowerShell/.NET e é
    recusada (conexão derrubada sem resposta nenhuma) pela biblioteca requests
    do Python. curl_cffi imita o TLS de um Chrome de verdade e passa."""
    if not url:
        return None
    try:
        from curl_cffi import requests as cf_requests
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://campineira.com.br/"}
        resp = cf_requests.get(url, headers=headers, timeout=8, impersonate="chrome")
        if resp.status_code == 200:
            return resp.content
        # Guarda o motivo real da falha (não só um None mudo) — sem isso não
        # dava pra saber se o bloqueio era de TLS, IP do datacenter da nuvem,
        # timeout, etc. Só a ÚLTIMA falha da sessão (não empilha um log
        # gigante), mostrada na tela de quem chamar essa função.
        try:
            st.session_state["_ultimo_erro_imagem"] = f"HTTP {resp.status_code} — {url}"
        except Exception:
            pass
        return None
    except Exception as e:
        try:
            st.session_state["_ultimo_erro_imagem"] = f"{type(e).__name__}: {str(e)[:200]} — {url}"
        except Exception:
            pass
        return None

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

def conectar_bigquery_rpa():
    """Conexão BigQuery independente do st.cache_resource.
    O RPA roda em uma thread separada (threading.Thread), e funções decoradas
    com @st.cache_resource (como a conectar_bigquery() do LeMarketplace) dependem
    do ScriptRunContext do Streamlit, que não existe fora da thread principal —
    por isso retornam None silenciosamente quando chamadas daqui."""
    info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(credentials=creds, project=info["project_id"])

def checar_ean_duplicado_bq(client, ean):
    """Verifica se esse EAN já foi usado num SKU publicado antes — evita mandar pro
    Upseller um cadastro que vai ser recusado com 'código de barra já existe' (erro
    detectado tarde demais, depois de já ter tentado publicar). Retorna o SKU já
    registrado com esse EAN, ou None se não achou nenhum (ou client indisponível —
    nesse caso não bloqueia, só não valida)."""
    if not client or not ean:
        return None
    try:
        query = f"""
            SELECT sku FROM `{TABLE_SKU_REGISTRO}`
            WHERE ean = @ean
            ORDER BY data_criacao DESC
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("ean", "STRING", str(ean))]
        )
        resultado = list(client.query(query, job_config=job_config).result())
        return resultado[0]["sku"] if resultado else None
    except Exception:
        return None

def registrar_sku_bq(client, sku, ean, id_produto, nome):
    """Registra um SKU recém-criado (Armazém publicado com sucesso) na tabela de
    controle — usada depois pra checar_ean_duplicado_bq() detectar repetição antes
    de tentar publicar de novo. Retorna (sucesso, erro)."""
    if not client:
        return False, "client BigQuery não conectado"
    try:
        row = {
            "sku": sku,
            "ean": str(ean) if ean else None,
            "id_produto": id_produto,
            "nome": nome,
            "data_criacao": datetime.utcnow().isoformat(),
        }
        erros = client.insert_rows_json(TABLE_SKU_REGISTRO, [row])
        if erros:
            return False, str(erros)[:300]
        return True, None
    except Exception as e:
        return False, str(e)[:300]

def baixar_imagem_bytes_bruto(url):
    """Baixa os bytes de uma imagem da Campineira sem depender do Streamlit (sem
    st.cache_data, sem st.session_state) — usada tanto no checkpoint da varredura
    (que roda numa thread separada, ver conectar_bigquery_rpa) quanto no backfill.
    curl_cffi (não requests) pelo mesmo motivo de carregar_imagem_bytes: a
    Campineira bloqueia pelo fingerprint TLS da conexão, não só pelos headers.

    ATENÇÃO: confirmado que a Campineira reforçou a proteção pra um nível que
    nem o curl_cffi passa mais ("HTTP/2 stream reset by server" — visto tanto
    local quanto na nuvem). Preferir _baixar_imagem_via_driver() (usa o Chrome de
    verdade da varredura) sempre que houver um driver Selenium disponível; essa
    função aqui fica só como fallback pra quando não tem driver (ex: backfill
    standalone), útil se a Campineira afrouxar a proteção de novo no futuro.
    Retorna (bytes, erro) — erro None se deu certo."""
    if not url:
        return None, "sem URL"
    try:
        from curl_cffi import requests as cf_requests
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://campineira.com.br/"}
        resp = cf_requests.get(url, headers=headers, timeout=8, impersonate="chrome")
        if resp.status_code == 200 and resp.content:
            return resp.content, None
        return None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:150]}"

_SCRIPT_FETCH_IMAGEM = """
var callback = arguments[arguments.length - 1];
var url = arguments[0];
fetch(url, {credentials: "include"}).then(function(resp) {
    if (!resp.ok) { callback({erro: "HTTP " + resp.status}); return null; }
    return resp.blob();
}).then(function(blob) {
    if (!blob) return;
    var reader = new FileReader();
    reader.onloadend = function() { callback({dataurl: reader.result}); };
    reader.onerror = function() { callback({erro: "FileReader falhou"}); };
    reader.readAsDataURL(blob);
}).catch(function(e) { callback({erro: String(e)}); });
"""

def _baixar_imagem_via_driver(driver, url, timeout=10):
    """Baixa os bytes de uma imagem usando fetch() DENTRO do próprio navegador
    Selenium que já está navegando na Campineira — em vez de um cliente HTTP
    Python (requests/curl_cffi) tentando imitar um navegador. Como o pedido sai
    de um Chrome de verdade, na mesma aba/origem já carregada, passa em
    qualquer verificação de fingerprint TLS/HTTP2 e leva os cookies da sessão
    automaticamente (fetch same-origin). É a única forma que continuou
    funcionando depois que a Campineira reforçou a proteção contra hotlink/bot
    (curl_cffi passou a apanhar com 'HTTP/2 stream reset by server').
    Retorna (bytes, erro)."""
    if not driver or not url:
        return None, "sem driver ou URL"
    try:
        driver.set_script_timeout(timeout)
        resultado = driver.execute_async_script(_SCRIPT_FETCH_IMAGEM, url)
        if resultado and resultado.get("dataurl"):
            import base64
            b64 = resultado["dataurl"].split(",", 1)[1]
            return base64.b64decode(b64), None
        return None, (resultado or {}).get("erro", "sem resposta do navegador")
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:150]}"

def atualizar_historico_bq(client, produtos, driver=None):
    """Registra/atualiza o histórico PERMANENTE de produtos lidos da Campineira —
    diferente do 'Resultados' (que é só a foto da última varredura), esse histórico
    nunca é sobrescrito. Cada produto só tem estoque/preço ATUALIZADOS se algo
    realmente mudou desde a última leitura; senão fica intocado. Produto novo entra
    como linha nova. O SKU (quando publicado) nunca é tocado por essa função — só
    por marcar_sku_historico_bq(), então sobrevive de varredura em varredura.

    Também baixa e grava o BYTES da foto (coluna imagem_bytes) de cada produto do
    lote — antes só guardávamos a URL, e a Campineira passou a bloquear o acesso
    direto (hotlink) que a tela de Histórico fazia pelo navegador do usuário, além
    do bloqueio por TLS fingerprint que já pegava os downloads feitos em Python.
    Guardando os bytes de verdade uma vez, aqui, o produto nunca mais depende da
    Campineira liberar a imagem de novo pra continuar aparecendo.

    'driver' (opcional): se veio um driver Selenium (a varredura já está com o
    Chrome aberto na Campineira), baixa cada foto usando o PRÓPRIO navegador
    (_baixar_imagem_via_driver) em vez de um cliente HTTP em Python — confirmado
    que a Campineira reforçou a proteção a ponto do curl_cffi também apanhar
    ("HTTP/2 stream reset by server", tanto local quanto na nuvem); um Chrome de
    verdade passa porque não está imitando nada. Sequencial (não dá pra rodar o
    mesmo driver em paralelo). Sem driver, cai no download via curl_cffi
    (paralelo, poucos workers) — mantido como fallback caso a Campineira
    afrouxe a proteção de novo, e é o único caminho possível fora de uma
    varredura (ex: backfill). Best-effort: se a imagem falhar, guarda NULL e o
    MERGE abaixo preserva um valor já existente (não apaga uma foto boa por
    causa de uma falha passageira).

    Usa uma tabela de staging (sobrescrita a cada chamada, WRITE_TRUNCATE) + um
    único MERGE pra cuidar de tudo de uma vez, em vez de 1 query por produto —
    importante já que a lista só tende a crescer com o tempo.
    Retorna (sucesso, erro)."""
    if not client or not produtos:
        return False, "client BigQuery não conectado ou lista vazia"
    try:
        import pandas as pd
        from concurrent.futures import ThreadPoolExecutor

        linhas = []
        for p in produtos:
            preco_str = p.get("preco") or "R$ 0"
            try:
                preco_num = float(preco_str.replace("R$", "").replace(".", "").replace(",", ".").strip())
            except Exception:
                preco_num = 0.0
            if not p.get("id"):
                continue
            linhas.append({
                "id_produto": str(p.get("id")),
                "categoria": p.get("categoria"),
                "nome": p.get("nome"),
                "estoque": int(p.get("estoque") or 0),
                "preco": preco_str,
                "preco_num": preco_num,
                "ean": p.get("ean"),
                "fabricante": p.get("fabricante"),
                "imagem": p.get("imagem"),
                "link": p.get("link"),
            })
        if not linhas:
            return False, "nenhum produto com id válido"

        if driver is not None:
            for linha in linhas:
                img_bytes, _erro = _baixar_imagem_via_driver(driver, linha["imagem"])
                linha["imagem_bytes"] = img_bytes
        else:
            with ThreadPoolExecutor(max_workers=4) as pool:
                imagens_bytes = list(pool.map(
                    lambda l: baixar_imagem_bytes_bruto(l["imagem"])[0], linhas
                ))
            for linha, img_bytes in zip(linhas, imagens_bytes):
                linha["imagem_bytes"] = img_bytes

        df_stage = pd.DataFrame(linhas)
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_TRUNCATE",
            schema=[
                bigquery.SchemaField("id_produto", "STRING"),
                bigquery.SchemaField("categoria", "STRING"),
                bigquery.SchemaField("nome", "STRING"),
                bigquery.SchemaField("estoque", "INTEGER"),
                bigquery.SchemaField("preco", "STRING"),
                bigquery.SchemaField("preco_num", "FLOAT"),
                bigquery.SchemaField("ean", "STRING"),
                bigquery.SchemaField("fabricante", "STRING"),
                bigquery.SchemaField("imagem", "STRING"),
                bigquery.SchemaField("link", "STRING"),
                bigquery.SchemaField("imagem_bytes", "BYTES"),
            ],
        )
        client.load_table_from_dataframe(df_stage, TABLE_HISTORICO_STAGE, job_config=job_config).result()

        merge_sql = f"""
            MERGE `{TABLE_HISTORICO}` T
            USING `{TABLE_HISTORICO_STAGE}` S
            ON T.id_produto = S.id_produto
            WHEN MATCHED AND (
                T.estoque != S.estoque OR T.preco_num != S.preco_num
                OR (S.imagem_bytes IS NOT NULL AND T.imagem_bytes IS NULL)
            ) THEN
              UPDATE SET
                estoque = S.estoque,
                preco = S.preco,
                preco_num = S.preco_num,
                nome = S.nome,
                imagem = S.imagem,
                imagem_bytes = COALESCE(S.imagem_bytes, T.imagem_bytes),
                data_ultima_leitura = CURRENT_TIMESTAMP(),
                data_ultima_atualizacao = CURRENT_TIMESTAMP()
            WHEN MATCHED THEN
              UPDATE SET data_ultima_leitura = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN
              INSERT (id_produto, categoria, nome, estoque, preco, preco_num, ean, fabricante, imagem, imagem_bytes, link,
                      sku_upseller, data_primeira_leitura, data_ultima_leitura, data_ultima_atualizacao)
              VALUES (S.id_produto, S.categoria, S.nome, S.estoque, S.preco, S.preco_num, S.ean, S.fabricante,
                      S.imagem, S.imagem_bytes, S.link, NULL, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
        """
        client.query(merge_sql).result()
        return True, None
    except Exception as e:
        return False, str(e)[:300]

def marcar_sku_historico_bq(client, id_produto, sku):
    """Grava o SKU no histórico assim que o produto é publicado no Armazém — fica
    ali até a próxima varredura reler esse mesmo produto (que pode ou não mudar
    estoque/preço, mas nunca mexe no SKU). Retorna (sucesso, erro)."""
    if not client or not sku or not id_produto:
        return False, "client BigQuery não conectado, SKU ou id vazio"
    try:
        query = f"""
            UPDATE `{TABLE_HISTORICO}`
            SET sku_upseller = @sku
            WHERE id_produto = @id_produto
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("sku", "STRING", sku),
            bigquery.ScalarQueryParameter("id_produto", "STRING", str(id_produto)),
        ])
        client.query(query, job_config=job_config).result()
        return True, None
    except Exception as e:
        return False, str(e)[:300]

def registrar_produto_em_tb_produtos(client, sku, nome, custo):
    """Registra o produto recém-publicado no Armazém em `tb_produtos` — a mesma
    tabela que a aba Cadastro do LeMarketplace preenche manualmente. Cria uma linha
    por marketplace (shein/shopee/temu/tiktok), todas com o mesmo SKU do Upseller,
    pra esse produto virar rastreável no restante do sistema (preços, estoque,
    vendas) sem precisar cadastrar ele de novo à mão. Retorna (sucesso, erro)."""
    if not client:
        return False, "client BigQuery não conectado"
    try:
        import pandas as pd
        table_id = "leandro-marketplace.DL_Store_Online.tb_produtos"
        lote = [
            {"marketplace": mkt, "sku": sku, "produto": nome, "custo_aquisicao": float(custo or 0)}
            for mkt in ["shein", "shopee", "temu", "tiktok"]
        ]
        df_lote = pd.DataFrame(lote)
        client.load_table_from_dataframe(df_lote, table_id).result()
        return True, None
    except Exception as e:
        return False, str(e)[:300]

def registrar_produto_bq(client, id_captura, categoria, produto, pagina=None):
    """Grava o produto capturado na tb_resultado_produtos_campineira assim que é extraído,
    para não perder o resultado se o cache/disco local for limpo. Guarda também o número
    da página onde o produto foi encontrado — é isso que permite retomar uma varredura
    interrompida exatamente de onde parou (ver buscar_progresso_varredura e o parâmetro
    retomar_id_captura de rodar_rpa_background), sem precisar de tabela nova.
    Retorna (sucesso: bool, erro: str|None)."""
    if not client:
        return False, "client BigQuery não conectado (conectar_bigquery() retornou None)"
    try:
        preco_str = produto.get("preco") or "R$ 0"
        try:
            preco_num = float(preco_str.replace("R$", "").replace(".", "").replace(",", ".").strip())
        except:
            preco_num = 0.0

        sugeridos = calcular_precos_sugeridos(preco_str)

        row = {
            "id_captura": id_captura,
            "data_captura": datetime.utcnow().isoformat(),
            "id_produto": produto.get("id"),
            "categoria": categoria,
            "pagina": pagina,
            "nome": produto.get("nome"),
            "estoque": produto.get("estoque"),
            "custo_campineira": preco_str,
            "custo_campineira_num": preco_num,
            "preco_shein": sugeridos.get("preco_shein"),
            "lucro_shein": sugeridos.get("lucro_shein"),
            "preco_shopee": sugeridos.get("preco_shopee"),
            "lucro_shopee": sugeridos.get("lucro_shopee"),
            "preco_temu": sugeridos.get("preco_temu"),
            "lucro_temu": sugeridos.get("lucro_temu"),
            "preco_tiktok": sugeridos.get("preco_tiktok"),
            "lucro_tiktok": sugeridos.get("lucro_tiktok"),
            "ean": produto.get("ean"),
            "fabricante": produto.get("fabricante"),
            "caixa_com": produto.get("caixa_com"),
            "quantidade": produto.get("quantidade"),
            "cor_cores": produto.get("cores") or produto.get("cor"),
            "composicao": produto.get("composicao"),
            "validade": produto.get("validade"),
            "tamanho": produto.get("tamanho") or produto.get("tamanho_aproximado"),
            "peso": produto.get("peso") or produto.get("peso_aproximado"),
            "tipo": produto.get("tipo") or produto.get("tipo_de_produto"),
            "caixa_master": produto.get("caixa_master"),
            "link": produto.get("link"),
            "imagem": produto.get("imagem"),
        }
        erros = client.insert_rows_json(TABLE_CAMPINEIRA, [row])
        if erros:
            return False, str(erros)[:300]
        return True, None
    except Exception as e:
        return False, str(e)[:300]

def registrar_evento_pipeline_bq(client, id_produto, sku_upseller, nome, categoria, etapa, status, mensagem):
    """Grava um evento de etapa do pipeline de publicação (armazem/shopee/shein/temu/tiktok).
    Modelo de log append-only (uma linha por evento) para não depender de UPDATE no BigQuery,
    que não funciona em linhas ainda no buffer de streaming."""
    if not client:
        return False, "client BigQuery não conectado"
    try:
        row = {
            "id_produto": id_produto,
            "sku_upseller": sku_upseller,
            "nome": nome,
            "categoria": categoria,
            "etapa": etapa,
            "status": status,
            "mensagem": (mensagem or "")[:500],
            "data_evento": datetime.utcnow().isoformat(),
        }
        erros = client.insert_rows_json(TABLE_PIPELINE, [row])
        if erros:
            return False, str(erros)[:300]
        return True, None
    except Exception as e:
        return False, str(e)[:300]

def carregar_pipeline_bq(client):
    """Lê o status consolidado (última etapa concluída de cada tipo) de cada produto
    que já passou pelo menos pela etapa 'armazem'. Retorna dict indexado por id_produto."""
    if not client:
        return {}
    try:
        query = f"""
            SELECT
                id_produto,
                ARRAY_AGG(sku_upseller ORDER BY data_evento DESC LIMIT 1)[OFFSET(0)] AS sku_upseller,
                ARRAY_AGG(nome ORDER BY data_evento DESC LIMIT 1)[OFFSET(0)] AS nome,
                ARRAY_AGG(categoria ORDER BY data_evento DESC LIMIT 1)[OFFSET(0)] AS categoria,
                LOGICAL_OR(etapa = 'armazem' AND status = 'ok') AS armazem_ok,
                LOGICAL_OR(etapa = 'shopee'  AND status = 'ok') AS shopee_ok,
                LOGICAL_OR(etapa = 'shein'   AND status = 'ok') AS shein_ok,
                LOGICAL_OR(etapa = 'temu'    AND status = 'ok') AS temu_ok,
                LOGICAL_OR(etapa = 'tiktok'  AND status = 'ok') AS tiktok_ok
            FROM `{TABLE_PIPELINE}`
            GROUP BY id_produto
            HAVING armazem_ok
        """
        df = client.query(query).to_dataframe()
        resultado = {}
        for _, r in df.iterrows():
            resultado[r["id_produto"]] = {
                "sku_upseller": r["sku_upseller"],
                "nome": r["nome"],
                "categoria": r["categoria"],
                "armazem_ok": bool(r["armazem_ok"]),
                "shopee_ok": bool(r["shopee_ok"]),
                "shein_ok": bool(r["shein_ok"]),
                "temu_ok": bool(r["temu_ok"]),
                "tiktok_ok": bool(r["tiktok_ok"]),
            }
        return resultado
    except Exception:
        return {}

def listar_produtos_armazem_com_erro(client):
    """Lista produtos cuja ÚLTIMA tentativa de publicar no Armazém (Etapa 1) falhou
    — ou seja, nunca chegaram a ser criados de fato. Reconstrói o dict completo do
    produto a partir da captura mais recente da Campineira, pra dar pra tentar
    publicar de novo do zero (gera um SKU novo, já que o anterior nunca foi salvo)."""
    if not client:
        return []
    try:
        q1 = f"""
            SELECT id_produto, nome, categoria, mensagem, status
            FROM `{TABLE_PIPELINE}`
            WHERE etapa = 'armazem'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY id_produto ORDER BY data_evento DESC) = 1
        """
        df1 = client.query(q1).to_dataframe()
        if df1.empty:
            return []
        df1 = df1[df1["status"] == "erro"]
        if df1.empty:
            return []

        resultado = []
        for _, r in df1.iterrows():
            produto_completo = None
            try:
                q2 = f"""
                    SELECT * FROM `{TABLE_CAMPINEIRA}`
                    WHERE id_produto = @id_produto
                    ORDER BY data_captura DESC LIMIT 1
                """
                job_config = bigquery.QueryJobConfig(
                    query_parameters=[bigquery.ScalarQueryParameter("id_produto", "STRING", r["id_produto"])]
                )
                df2 = client.query(q2, job_config=job_config).to_dataframe()
                if not df2.empty:
                    cap = df2.iloc[0].to_dict()
                    produto_completo = {
                        "id": r["id_produto"],
                        "nome": _sem_nan(cap.get("nome")) or r["nome"],
                        "categoria": _sem_nan(cap.get("categoria")) or r["categoria"],
                        # Faltava isso — sem "preco"/"preco_num", registrar_produto_em_tb_produtos()
                        # recebia None e gravava custo_aquisicao = 0 no reprocessamento
                        # (causa real do RJ-00023 e de outros 106 produtos zerados em tb_produtos).
                        "preco": _sem_nan(cap.get("custo_campineira")),
                        "preco_num": _sem_nan(cap.get("custo_campineira_num")),
                        "ean": _sem_nan(cap.get("ean")),
                        "fabricante": _sem_nan(cap.get("fabricante")),
                        "caixa_com": _sem_nan(cap.get("caixa_com")),
                        "quantidade": _sem_nan(cap.get("quantidade")),
                        "cores": _sem_nan(cap.get("cor_cores")),
                        "composicao": _sem_nan(cap.get("composicao")),
                        "validade": _sem_nan(cap.get("validade")),
                        "tamanho": _sem_nan(cap.get("tamanho")),
                        "peso": _sem_nan(cap.get("peso")),
                        "tipo": _sem_nan(cap.get("tipo")),
                        "caixa_master": _sem_nan(cap.get("caixa_master")),
                        "link": _sem_nan(cap.get("link")),
                        "imagem": _sem_nan(cap.get("imagem")),
                    }
            except Exception:
                pass
            resultado.append({
                "id_produto": r["id_produto"],
                "nome": r["nome"],
                "categoria": r["categoria"],
                "mensagem": r["mensagem"],
                "produto": produto_completo,
            })
        return resultado
    except Exception:
        return []

def imagem_parece_valida(url):
    """Verifica se a URL de imagem segue o padrão real de foto de produto da
    Campineira (.../Imagens/produtos/##/foto######.jpg) — confirmado em várias
    capturas certas. Ícones de tamanho, selos e logos do site têm outro padrão
    de pasta/nome (ex: /Imagens/icones/icone_0157.jpg, images/Logo25AnosMenor.png)
    e às vezes acabam capturados por engano no lugar da foto real. Em vez de só
    checar se tem alguma URL, valida o padrão pra pegar essas capturas erradas."""
    if not url:
        return False
    return bool(re.search(r'/produtos/\d+/foto\d+\.\w+', url, re.IGNORECASE))

@st.cache_data(ttl=120, show_spinner=False)
def _ids_com_sku_no_historico(_client) -> set:
    """id_produto de tudo que já tem sku_upseller marcado no histórico — usado
    pra tirar da aba Publicar quem já foi publicado de verdade em qualquer
    sessão passada (não só nessa). '_client' com underscore de propósito:
    é a convenção do Streamlit pra st.cache_data pular esse argumento no
    hashing (client do BigQuery não é hasheável)."""
    if not _client:
        return set()
    try:
        df = _client.query(
            f"SELECT id_produto FROM `{TABLE_HISTORICO}` WHERE sku_upseller IS NOT NULL"
        ).to_dataframe()
        return set(df["id_produto"].astype(str))
    except Exception:
        return set()

def _buscar_imagens_bytes_historico(client, ids) -> dict:
    """Busca no histórico os bytes de imagem já salvos (ver atualizar_historico_bq)
    para uma lista de id_produto — usada na aba Publicar pra preferir a foto já
    baixada num checkpoint de varredura anterior em vez de tentar buscar ao vivo
    da Campineira de novo (sujeito a bloqueio de TLS/IP, e mais lento). Sem cache:
    a lista de ids muda a cada rerun/filtro da tela, e a query em si (WHERE IN
    com poucas centenas de ids) é rápida. Retorna dict id_produto (str) -> bytes,
    só com quem tem imagem_bytes salvo."""
    ids = [str(i) for i in ids if i]
    if not client or not ids:
        return {}
    try:
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ArrayQueryParameter("ids", "STRING", ids)
        ])
        df = client.query(
            f"SELECT id_produto, imagem_bytes FROM `{TABLE_HISTORICO}` "
            f"WHERE id_produto IN UNNEST(@ids) AND imagem_bytes IS NOT NULL",
            job_config=job_config,
        ).to_dataframe()
        return dict(zip(df["id_produto"].astype(str), df["imagem_bytes"]))
    except Exception:
        return {}

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

    # Ordena do maior pro menor lucro — usa o melhor lucro entre as 4 plataformas
    # de cada produto. Como Resultados, Galeria e Publicar usam essa mesma função,
    # a ordenação vale nas três telas de uma vez.
    resultado.sort(
        key=lambda p: max((p.get(f"lucro_{m}") or 0) for m in ["shein", "shopee", "temu", "tiktok"]),
        reverse=True
    )
    return resultado

def buscar_progresso_varredura(client):
    """Olha a captura mais recente em tb_resultado_produtos_campineira e monta um
    resumo de por onde ela parou — categoria por categoria, qual foi a última
    página capturada. Sobrevive a reinício do app (não depende de arquivo local
    nem de session_state, só do que já está gravado no BigQuery), então dá pra
    retomar uma varredura mesmo depois do Streamlit reiniciar do zero. Retorna
    None se não achar nenhuma captura, ou um dict:
    {"id_captura": ..., "ultima_atividade": ..., "categorias": {nome: pagina_max}, "total_produtos": N}"""
    if not client:
        return None
    try:
        q = f"""
            SELECT categoria, MAX(pagina) AS pagina_max, COUNT(*) AS produtos, MAX(data_captura) AS ultima_atividade
            FROM `{TABLE_CAMPINEIRA}`
            WHERE id_captura = (SELECT MAX(id_captura) FROM `{TABLE_CAMPINEIRA}`)
            GROUP BY categoria
        """
        df = client.query(q).to_dataframe()
        if df.empty:
            return None
        id_captura_df = client.query(f"SELECT MAX(id_captura) AS ult FROM `{TABLE_CAMPINEIRA}`").to_dataframe()
        id_captura = id_captura_df["ult"].iloc[0]
        categorias = {row["categoria"]: int(row["pagina_max"] or 1) for _, row in df.iterrows()}
        return {
            "id_captura": id_captura,
            "ultima_atividade": df["ultima_atividade"].max(),
            "categorias": categorias,
            "total_produtos": int(df["produtos"].sum()),
        }
    except Exception:
        return None

# ============================================================
# RPA EM BACKGROUND
# ============================================================

def rodar_rpa_background(filtros_cat, cats_varrer=None, buscar_detalhes=False,
                          retomar_id_captura=None, paginas_ja_feitas=None):
    """Roda o RPA em thread separada para não travar o Streamlit.

    retomar_id_captura / paginas_ja_feitas: usados só quando o usuário clica em
    "Retomar" uma varredura interrompida (ver buscar_progresso_varredura). Em vez
    de começar um id_captura novo do zero, reaproveita o antigo (os produtos já
    capturados continuam contando pra essa mesma varredura) e, categoria por
    categoria, avança direto até a página onde parou (paginas_ja_feitas é um
    dict {categoria: última página já capturada}) antes de voltar a extrair/
    registrar produtos normalmente."""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
        import time

        inicio_dt = datetime.now()
        id_captura = retomar_id_captura or inicio_dt.strftime("%Y%m%d_%H%M%S")
        paginas_ja_feitas = paginas_ja_feitas or {}
        bq_conn_erro = None
        try:
            client_bq_camp = conectar_bigquery_rpa()
        except Exception as e:
            client_bq_camp = None
            bq_conn_erro = str(e)[:200]

        progresso_inicial = "Iniciando..."
        if not client_bq_camp:
            progresso_inicial = (f"Iniciando... ⚠️ BigQuery indisponível "
                                  f"({bq_conn_erro or 'conectar_bigquery() retornou None'}) "
                                  f"— salvando apenas no JSON local.")
        bq_erro_reportado = [False]

        # IDs já publicados no Armazém — pulamos esses na captura pra não ficar
        # reprocessando/re-adicionando na fila quem já foi publicado. Produtos
        # ainda não publicados continuam sendo recapturados normalmente (atualiza
        # preço, estoque, imagem etc.). Pra corrigir dado de algo já publicado,
        # usa os botões "Reprocessar" na aba Publicar, não a varredura.
        ids_ja_publicados = set()
        if client_bq_camp:
            try:
                q_publicados = f"""
                    SELECT DISTINCT id_produto FROM `{TABLE_PIPELINE}`
                    WHERE etapa = 'armazem' AND status = 'ok'
                """
                df_publicados = client_bq_camp.query(q_publicados).to_dataframe()
                ids_ja_publicados = set(df_publicados["id_produto"].tolist())
            except Exception:
                ids_ja_publicados = set()

        salvar_status({"rodando": True, "progresso": progresso_inicial,
                       "inicio": inicio_dt.strftime("%d/%m/%Y %H:%M:%S"),
                       "inicio_ts": inicio_dt.timestamp(),
                       "fim": None, "duracao": None})

        # Chrome em modo headless
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")

        # Detecta automaticamente o Chromium do sistema (packages.txt no Streamlit
        # Cloud) — sem depender de secret configurada à mão. Local, esse caminho não
        # existe, então cai no webdriver_manager normal.
        from modulo_upseller import _chromium_do_sistema
        bin_path, drv_path = _chromium_do_sistema()
        if bin_path and drv_path:
            opts.binary_location = bin_path
            driver = webdriver.Chrome(service=Service(drv_path), options=opts)
        else:
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
            # Junta produtos aqui até completar 5 páginas, aí grava no histórico
            # PERMANENTE (tb_historico_produtos_campineira) e esvazia — assim, se a
            # varredura cair no meio de uma categoria grande, o que já foi lido até
            # ali (menos as últimas <5 páginas) já está salvo de verdade, não só na
            # memória da thread. O resultado por produto individual já ia direto pro
            # BigQuery de qualquer forma (registrar_produto_bq, tela Resultados lê de
            # lá) — esse buffer aqui é só pro histórico consolidado.
            buffer_checkpoint = []
            paginas_desde_ultimo_checkpoint = 0
            PAGINAS_POR_CHECKPOINT = 5

            def _gravar_checkpoint_historico():
                nonlocal buffer_checkpoint, paginas_desde_ultimo_checkpoint
                if not buffer_checkpoint:
                    return
                ok_hist, erro_hist = atualizar_historico_bq(client_bq_camp, buffer_checkpoint, driver=driver)
                if not ok_hist:
                    atualizar(f"⚠️ Falha ao gravar checkpoint no histórico: {erro_hist}")
                buffer_checkpoint = []
                paginas_desde_ultimo_checkpoint = 0

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
                // A foto REAL do produto fica dentro de um <figure> (confirmado no
                // HTML do site: <div class="box-interno"><figure><img class="img-
                // responsive" src=".../foto####.jpg">). O card também tem OUTROS <img
                // class="img-responsive img_icone"> (ícones de tamanho, ex: title=
                // "Tamanho Médio", src=".../icones/icone_0157.jpg") que casam com
                // seletores genéricos de ".img-responsive" — excluído via :not(.img_icone).
                var naoIcone = ':not(.img_icone):not([src*="Imagens/icones"])';
                var imgElem = box.querySelector('figure img.img-responsive' + naoIcone) || box.querySelector('figure img' + naoIcone) || box.querySelector('.box-interno img' + naoIcone) || box.querySelector('img.img-responsive' + naoIcone) || box.querySelector('img' + naoIcone);
                // Sites com lazy loading mostram um placeholder genérico no atributo
                // "src" até a imagem real carregar — a URL de verdade fica guardada
                // num atributo "data-*" enquanto isso. Prioriza esses antes do src puro.
                var imagem = imgElem ? (
                    imgElem.getAttribute('data-src') ||
                    imgElem.getAttribute('data-lazy-src') ||
                    imgElem.getAttribute('data-original') ||
                    imgElem.getAttribute('data-lazy') ||
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

                    # Retomando uma varredura interrompida? Avança direto até a
                    # página onde parou (clicando ">" sem extrair nada) antes de
                    # voltar ao fluxo normal — evita registrar de novo o que essa
                    # categoria já tinha capturado antes da queda.
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
                                # Não tem mais próxima página — essa categoria já
                                # tinha sido totalmente varrida antes da queda.
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
                        # Retry único em falha transitória de JS/DOM (a causa mais
                        # comum de perder uma categoria inteira no meio de uma
                        # varredura grande) — só desiste mesmo se falhar 2x seguidas.
                        try:
                            produtos = driver.execute_script(SCRIPT_EXTRAI)
                        except Exception:
                            time.sleep(2)
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
                                    # Se algo quebrou ENTRE abrir a aba nova e o driver.close()
                                    # de cima, essa aba fica órfã aberta — sozinha isso é
                                    # pouca coisa, mas em milhares de produtos numa categoria
                                    # grande vira um vazamento real de memória do Chrome
                                    # (cada aba é um processo renderer). Fecha qualquer aba
                                    # extra antes de voltar pra principal.
                                    try:
                                        while len(driver.window_handles) > 1:
                                            driver.switch_to.window(driver.window_handles[-1])
                                            driver.close()
                                        driver.switch_to.window(driver.window_handles[0])
                                    except:
                                        pass
                            # Se modo detalhado, usa imagem da página do produto (melhor qualidade)
                            if buscar_detalhes and detalhes.get("imagem_produto"):
                                p["imagem"] = detalhes.pop("imagem_produto")
                            elif "imagem_produto" in detalhes:
                                detalhes.pop("imagem_produto")
                            produto_final = {**p, "categoria": nome_cat, **detalhes}

                            # Pula produtos já publicados no Armazém — evita reprocessar/
                            # readicionar na fila quem já foi publicado (pra corrigir dados
                            # de um já publicado, usa "Reprocessar" na aba Publicar).
                            if produto_final.get("id") in ids_ja_publicados:
                                continue

                            todos_produtos.append(produto_final)
                            buffer_checkpoint.append(produto_final)
                            ok_bq, erro_bq = registrar_produto_bq(client_bq_camp, id_captura, nome_cat, produto_final, pagina=pagina)
                            if not ok_bq and not bq_erro_reportado[0]:
                                bq_erro_reportado[0] = True
                                atualizar(f"⚠️ Falha ao gravar no BigQuery: {erro_bq}")

                        paginas_desde_ultimo_checkpoint += 1
                        if paginas_desde_ultimo_checkpoint >= PAGINAS_POR_CHECKPOINT:
                            atualizar(f"[{idx+1}/{len(categorias)}] {nome_cat} — pág. {pagina} "
                                      f"(checkpoint: gravando {len(buffer_checkpoint)} produtos no histórico)...")
                            _gravar_checkpoint_historico()
                        else:
                            atualizar(f"[{idx+1}/{len(categorias)}] {nome_cat} — pág. {pagina} "
                                      f"({len(todos_produtos)} produtos até agora)")

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
                    # Não perde o que já leu dessa categoria até o erro acontecer —
                    # grava o buffer acumulado antes de seguir pra próxima categoria.
                    _gravar_checkpoint_historico()

            # Sobra de produtos das últimas <5 páginas que ainda não bateu checkpoint.
            _gravar_checkpoint_historico()

            # SALVA RESULTADOS (fallback local — a aba Resultados já lê direto do
            # BigQuery, tempo real; isso aqui só é usado se o BigQuery cair)
            with open(ARQUIVO_RESULTADOS, "w", encoding="utf-8") as f:
                json.dump(todos_produtos, f, ensure_ascii=False)

            # Histórico PERMANENTE já foi alimentado incrementalmente pelos
            # checkpoints a cada 5 páginas (_gravar_checkpoint_historico) — não
            # precisa mandar tudo de novo aqui no final.

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
# EXECUÇÃO DO PIPELINE DE PUBLICAÇÃO (Shopee/Shein/Temu/TikTok)
# ============================================================
# Funções de módulo (não fechadas sobre nada) — reutilizadas tanto pelos botões
# individuais quanto pelo botão "Todas as Lojas". Sem depender de a Shopee ter
# sido clicada manualmente antes: cada uma garante os pré-requisitos sozinha.

def _msg_parou(msg_final, driver_atual):
    """Monta uma mensagem de parada explícita, checando se o rascunho ainda está
    aberto na tela (confirmando que nada foi publicado)."""
    from modulo_upseller import pagina_rascunho_ainda_aberta
    ainda_aberta = pagina_rascunho_ainda_aberta(driver_atual)
    if ainda_aberta is True:
        return f"{msg_final} — página do rascunho ainda aberta, nada foi publicado."
    elif ainda_aberta is False:
        return f"{msg_final} — saiu da tela do rascunho, mas não há confirmação de publicação."
    return msg_final

def _rodar_shopee(driver, p, sku, nome, client_bq_pipeline, add_log):
    """Roda o fluxo completo da Shopee (copiar do Armazém → abrir rascunho →
    preencher → publicar). Se já estiver ok, não faz nada. Retorna True/False."""
    if st.session_state.get(f"shopee_ok_{sku}"):
        return True
    from modulo_upseller import etapa2_copiar_para_lojas, etapa3_editar_rascunho, preencher_rascunho_shopee, finalizar_rascunho
    add_log("🟠 Copiando para Shopee...")
    ok2, msg2 = etapa2_copiar_para_lojas(driver, sku)
    add_log(msg2)
    msg_final = msg2
    if ok2:
        add_log("→ Abrindo rascunho...")
        ok3, msg3, cat = etapa3_editar_rascunho(driver, sku, nome)
        add_log(msg3)
        msg_final = msg3
        if ok3:
            add_log("→ Preenchendo campos...")
            ok4, msg4 = preencher_rascunho_shopee(driver, p, sku, cat)
            add_log(msg4)
            msg_final = msg4
            if ok4:
                add_log("→ Publicando...")
                finalizar_rascunho(driver)
                st.session_state[f"shopee_ok_{sku}"] = True
                add_log("✅ Shopee publicado!")
                msg_final = "✅ Shopee publicado!"
    if not st.session_state.get(f"shopee_ok_{sku}"):
        msg_final = _msg_parou(msg_final, driver)
        st.session_state["shopee_erro_" + sku] = msg_final
        add_log(f"⛔ Automação parou: {msg_final}")
    registrar_evento_pipeline_bq(
        client_bq_pipeline, p.get('id'), sku, nome, p.get('categoria'),
        "shopee", "ok" if st.session_state.get(f"shopee_ok_{sku}") else "erro", msg_final
    )
    return st.session_state.get(f"shopee_ok_{sku}", False)

def _rodar_migracao(driver, p, sku, nome, client_bq_pipeline, add_log):
    """Roda 'Copiar para Lojas' a partir do anúncio JÁ PUBLICADO na Shopee (marca
    Shein+Temu+TikTok de uma vez só) — UMA ÚNICA VEZ por produto, reaproveitado
    pelos 3 botões. Retorna True/False."""
    if st.session_state.get(f"migracao_ok_{sku}"):
        return True
    from modulo_upseller import etapa4_migrar_para_lojas
    add_log("📋 Copiando anúncio da Shopee para Shein/Temu/TikTok...")
    ok4, msg4 = etapa4_migrar_para_lojas(driver, sku)
    add_log(msg4)
    st.session_state[f"migracao_ok_{sku}"] = ok4
    if not ok4:
        msg4 = _msg_parou(msg4, driver)
        st.session_state[f"migracao_erro_{sku}"] = msg4
        add_log(f"⛔ Cópia para as lojas parou: {msg4}")
    registrar_evento_pipeline_bq(
        client_bq_pipeline, p.get('id'), sku, nome, p.get('categoria'),
        "migracao", "ok" if ok4 else "erro", msg4
    )
    return ok4

def _rodar_loja(driver, p, sku, nome, client_bq_pipeline, add_log, plataforma):
    """Roda o fluxo completo de UMA loja (Shein/Temu/TikTok): garante que a Shopee
    já publicou, garante que a cópia (migração a partir da Shopee) já rodou, e só
    então preenche+publica o rascunho dessa loja. Chamado tanto pelo botão
    individual quanto pelo "Todas as Lojas"."""
    ok_key = f"{plataforma}_ok_{sku}"
    if st.session_state.get(ok_key):
        return True

    if not _rodar_shopee(driver, p, sku, nome, client_bq_pipeline, add_log):
        return False
    if not _rodar_migracao(driver, p, sku, nome, client_bq_pipeline, add_log):
        return False

    from modulo_upseller import editar_rascunho_plataforma
    add_log(f"→ Editando rascunho {plataforma.title()}...")
    ok5, msg5 = editar_rascunho_plataforma(driver, sku, p, plataforma)
    add_log(msg5)
    if ok5:
        st.session_state[ok_key] = True
        add_log(f"✅ {plataforma.title()} publicado!")
        msg5 = f"✅ {plataforma.title()} publicado!"
    else:
        msg5 = _msg_parou(msg5, driver)
        st.session_state[f"{plataforma}_erro_{sku}"] = msg5
        add_log(f"⛔ Automação parou: {msg5}")
    registrar_evento_pipeline_bq(
        client_bq_pipeline, p.get('id'), sku, nome, p.get('categoria'),
        plataforma, "ok" if st.session_state.get(ok_key) else "erro", msg5
    )
    return st.session_state.get(ok_key, False)

# ============================================================
# PUBLICAR UM PRODUTO NO ARMAZÉM (usado pelo botão individual e pela publicação em massa)
# ============================================================

def _publicar_um_produto_armazem(p, client_bq_pipeline):
    """Roda o fluxo completo de publicar UM produto no Armazém: checa EAN
    duplicado, publica no Upseller, gera SKU, registra em tb_sku_registrados,
    tb_produtos e no histórico permanente, e grava o evento do pipeline. Salva o
    resultado em st.session_state (mesmas chaves que o card usa pra mostrar
    sucesso/erro persistente) — chamada tanto pelo botão "🚀 Publicar" individual
    quanto pelo loop de "Publicar Selecionados" em massa. Retorna (sucesso, msg)."""
    from modulo_upseller import publicar_produto_upseller

    # Valida o EAN ANTES de tentar publicar — evita mandar pro Upseller um
    # cadastro que já sabemos que vai ser recusado com "código de barra já
    # existe" (erro só aparecia depois de já ter gasto o SKU e a tentativa inteira).
    sku_repetido = checar_ean_duplicado_bq(client_bq_pipeline, p.get('ean'))
    if sku_repetido:
        msg = f"❌ EAN {p.get('ean')} já usado no SKU {sku_repetido} — não publicado, pra evitar duplicidade."
        st.session_state[f"pub_{p.get('id')}"] = False
        st.session_state[f"pub_msg_{p.get('id')}"] = msg
        return False, msg

    driver = st.session_state.get("ups_driver")
    # client_bq_pipeline vai pra get_proximo_sku() (dentro de
    # publicar_produto_upseller) gerar o SKU a partir de tb_sku_registrados —
    # fonte confiável, não some com restart do app como um arquivo local sumia.
    sucesso, msg, sku_gerado = publicar_produto_upseller(driver, p, client_bq_pipeline)
    st.session_state[f"pub_{p.get('id')}"] = sucesso
    st.session_state[f"pub_msg_{p.get('id')}"] = msg

    avisos_bq = []
    if sucesso:
        st.session_state[f"pub_sku_{p.get('id')}"] = sku_gerado

        # Registra o novo SKU (+ EAN) na base de controle — é o que
        # checar_ean_duplicado_bq() consulta nas próximas publicações.
        ok_sku_bq, erro_sku_bq = registrar_sku_bq(client_bq_pipeline, sku_gerado, p.get('ean'), p.get('id'), p.get('nome'))
        if not ok_sku_bq:
            avisos_bq.append(f"SKU não registrado no BigQuery: {erro_sku_bq}")

        # Cria o produto em tb_produtos (mesma tabela do Cadastro manual) — uma
        # linha por marketplace, mesmo SKU do Upseller.
        ok_prod_bq, erro_prod_bq = registrar_produto_em_tb_produtos(
            client_bq_pipeline, sku_gerado, p.get('nome'), p.get('preco_num')
        )
        if not ok_prod_bq:
            avisos_bq.append(f"tb_produtos não atualizado: {erro_prod_bq}")

        # Marca o SKU no histórico permanente — fica registrado ali até a
        # próxima varredura reler esse produto.
        ok_hist_sku, erro_hist_sku = marcar_sku_historico_bq(client_bq_pipeline, p.get('id'), sku_gerado)
        if not ok_hist_sku:
            avisos_bq.append(f"SKU não marcado no histórico: {erro_hist_sku}")

    # Grava a etapa Armazém no BigQuery — garante que o produto continue
    # aparecendo em "Enviar para Lojas" mesmo após F5/cache limpo. Se essa
    # gravação falhar (ex: tabela não existe), avisa em vez de engolir
    # silenciosamente — foi assim que a tabela ficou vazia sem ninguém perceber.
    ok_evento_bq, erro_evento_bq = registrar_evento_pipeline_bq(
        client_bq_pipeline, p.get('id'), sku_gerado, p.get('nome'),
        p.get('categoria'), "armazem", "ok" if sucesso else "erro", msg
    )
    if not ok_evento_bq:
        avisos_bq.append(f"Evento do pipeline não registrado: {erro_evento_bq}")

    if avisos_bq:
        msg = msg + " ⚠️ " + " | ".join(avisos_bq)
        st.session_state[f"pub_msg_{p.get('id')}"] = msg

    return sucesso, msg

# ============================================================
# CARD DE PUBLICAÇÃO POR LOJA (Shopee/Shein/Temu/TikTok)
# ============================================================

def renderizar_card_publicacao(p, key_suffix, client_bq_pipeline):
    """Card com status das etapas e botões de publicação por loja para um produto que já
    está no Armazém do Upseller. Reutilizado tanto pela lista de produtos publicados na
    sessão (aba Enviar para Lojas) quanto pela busca independente por SKU."""
    sku = p.get("sku_upseller", "")
    nome = p.get("nome", "")
    etapa2_ok = st.session_state.get(f"etapa2_{sku}", False)
    etapa3_ok = st.session_state.get(f"etapa3_{sku}", False)

    with st.container(border=True):
        col_img, col_info, col_acoes = st.columns([1, 4, 2])

        with col_img:
            if p.get('imagem'):
                img_bytes = carregar_imagem_bytes(p['imagem'])
                if img_bytes:
                    st.image(img_bytes, use_container_width=True)
                else:
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
            else:
                # Log em tempo real
                log_key = f"log_{sku}"
                if log_key not in st.session_state:
                    st.session_state[log_key] = []

                def add_log(msg):
                    st.session_state[log_key].append(msg)

                # Mostra log — sempre aberto (expanded=True), então nem precisa de
                # expander (que dependeria da fonte de ícone quebrada pra seta);
                # mostra direto.
                if st.session_state[log_key]:
                    st.markdown("**📋 Log**")
                    for linha in st.session_state[log_key][-8:]:
                        st.caption(linha)

                st.markdown("**Publicar por plataforma:**")

                # As 4 lojas ficam liberadas ao mesmo tempo — não precisa clicar Shopee
                # primeiro manualmente. Por trás, Shein/Temu/TikTok garantem sozinhas que
                # a Shopee já publicou e que a cópia (migração a partir do anúncio da
                # Shopee, feita uma única vez e reaproveitada pelas 3) já rodou, antes de
                # preencher seu próprio rascunho.
                def _render_botao_loja(plataforma, emoji, executor):
                    ok_key = f"{plataforma}_ok_{sku}"
                    running_key = f"{plataforma}_running_{sku}"
                    erro_key = f"{plataforma}_erro_{sku}"
                    ok = st.session_state.get(ok_key, False)

                    if ok:
                        col_ok, col_reset = st.columns([4, 1])
                        col_ok.success(f"✅ {plataforma.title()}")
                        if col_reset.button("🔄", key=f"reset_{plataforma}_{key_suffix}",
                                             help="Resetar status e permitir forçar de novo — confirme manualmente no Upseller se já não está publicado, pra evitar duplicidade"):
                            st.session_state[ok_key] = False
                            st.session_state[erro_key] = None
                            st.session_state[running_key] = False
                            add_log(f"🔄 Status da {plataforma.title()} resetado manualmente.")
                            st.rerun()
                    else:
                        erro = st.session_state.get(erro_key)
                        if erro:
                            st.error(f"⛔ Parou: {erro}")
                        label = f"🔁 {plataforma.title()} (tentar de novo)" if erro else f"{emoji} {plataforma.title()}"
                        if st.button(label, key=f"{plataforma}_{key_suffix}", use_container_width=True):
                            st.session_state[running_key] = True
                            st.session_state[erro_key] = None
                            add_log(f"{emoji} Iniciando {plataforma.title()}...")
                            st.rerun()

                    if not ok and st.session_state.get(running_key):
                        executor()
                        st.session_state[running_key] = False
                        st.rerun()

                def _render_botao_combo(plataformas, emoji, rotulo, executores):
                    """Um botão só que roda várias lojas em sequência (Shein+Temu+TikTok
                    compartilham a mesma migração a partir da Shopee, então faz sentido
                    tratar as 3 como um bloco só na tela, em vez de 3 botões separados)."""
                    combo_id = "_".join(plataformas)
                    running_key = f"combo_{combo_id}_running_{sku}"
                    oks = {pl: st.session_state.get(f"{pl}_ok_{sku}", False) for pl in plataformas}
                    todas_ok = all(oks.values())

                    if todas_ok:
                        st.success(f"✅ {rotulo}")
                    else:
                        status_linha = "  ".join(
                            f"{'✅' if oks[pl] else '⏳'} {pl.title()}" for pl in plataformas
                        )
                        st.caption(status_linha)
                        for pl in plataformas:
                            erro = st.session_state.get(f"{pl}_erro_{sku}")
                            if erro and not oks[pl]:
                                st.error(f"⛔ {pl.title()}: {erro}")

                        algum_erro = any(st.session_state.get(f"{pl}_erro_{sku}") for pl in plataformas if not oks[pl])
                        label = f"🔁 {rotulo} (continuar)" if algum_erro else f"{emoji} {rotulo}"
                        if st.button(label, key=f"combo_{combo_id}_{key_suffix}", use_container_width=True):
                            st.session_state[running_key] = True
                            for pl in plataformas:
                                st.session_state[f"{pl}_erro_{sku}"] = None
                            add_log(f"{emoji} Iniciando {rotulo}...")
                            st.rerun()

                    if not todas_ok and st.session_state.get(running_key):
                        for pl in plataformas:
                            executores[pl]()
                        st.session_state[running_key] = False
                        st.rerun()

                _render_botao_loja("shopee", "🟠", lambda: _rodar_shopee(driver, p, sku, nome, client_bq_pipeline, add_log))
                _render_botao_combo(
                    ["shein", "temu", "tiktok"], "🛍️", "Shein + Temu + TikTok",
                    {
                        "shein": lambda: _rodar_loja(driver, p, sku, nome, client_bq_pipeline, add_log, "shein"),
                        "temu": lambda: _rodar_loja(driver, p, sku, nome, client_bq_pipeline, add_log, "temu"),
                        "tiktok": lambda: _rodar_loja(driver, p, sku, nome, client_bq_pipeline, add_log, "tiktok"),
                    }
                )

                # Status geral + botão "Todas as Lojas"
                shopee_ok = st.session_state.get(f"shopee_ok_{sku}", False)
                shein_ok = st.session_state.get(f"shein_ok_{sku}", False)
                temu_ok = st.session_state.get(f"temu_ok_{sku}", False)
                tiktok_ok = st.session_state.get(f"tiktok_ok_{sku}", False)
                total_ok = sum([shopee_ok, shein_ok, temu_ok, tiktok_ok])

                st.markdown("---")
                if total_ok == 4:
                    st.success("🎉 Publicado em todas!")
                else:
                    st.caption(f"✅ {total_ok}/4 plataformas")
                    todas_key = f"todas_running_{sku}"
                    if st.button("✅ Todas as Lojas", key=f"todas_{key_suffix}", use_container_width=True, type="primary"):
                        st.session_state[todas_key] = True
                        add_log("✅ Iniciando publicação em todas as lojas...")
                        st.rerun()
                    if st.session_state.get(todas_key):
                        _rodar_shopee(driver, p, sku, nome, client_bq_pipeline, add_log)
                        _rodar_loja(driver, p, sku, nome, client_bq_pipeline, add_log, "shein")
                        _rodar_loja(driver, p, sku, nome, client_bq_pipeline, add_log, "temu")
                        _rodar_loja(driver, p, sku, nome, client_bq_pipeline, add_log, "tiktok")
                        st.session_state[todas_key] = False
                        st.rerun()

            # Remove da lista "Enviar para Lojas" — o produto fica aqui indefinidamente
            # até publicar nas 4 (ele NÃO some sozinho), então esse botão é a única forma
            # de tirar um item daqui manualmente (ex: teste, duplicado). Reaproveita o
            # mesmo arquivo de exclusão da aba Publicar, pra sobreviver a restart.
            if st.button("🗑️ Remover desta lista", key=f"rem_envio_{key_suffix}", use_container_width=True):
                excluidos_envio = st.session_state.get("pub_excluidos", set())
                excluidos_envio.add(p.get('id'))
                st.session_state["pub_excluidos"] = excluidos_envio
                salvar_excluidos(excluidos_envio, client_bq_pipeline)
                st.rerun()

# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

def pagina_campineira(client_bq=None):
    """client_bq: conexão BigQuery já aberta, passada pelo LeMarketplace.py (reaproveita
    a mesma conexão do resto do app). NUNCA importar "LeMarketplace" daqui dentro pra
    conseguir uma conexão — é o script principal rodado pelo Streamlit, e importar dele
    a partir de outro módulo re-executa o arquivo inteiro (sidebar, botões, tudo) como
    efeito colateral, causando erro de IDs de widget duplicados e conteúdo duplicado
    na tela. Se ninguém passar uma conexão, abre uma própria (conectar_bigquery_rpa),
    que não depende de importar nada do LeMarketplace."""
    st.markdown("## 🏭 Campineira — Varredura de Produtos")
    st.markdown("---")

    if client_bq is not None:
        client_bq_pipeline = client_bq
    else:
        try:
            client_bq_pipeline = conectar_bigquery_rpa()
        except Exception as _erro_bq_conexao:
            client_bq_pipeline = None
            st.error(f"⚠️ Não conectou ao BigQuery nesta página: {str(_erro_bq_conexao)[:300]}")

    status = ler_status()
    resultados_brutos = ler_resultados(client_bq_pipeline)

    # ---- ABA DE CONFIGURAÇÃO ----
    if "pub_excluidos" not in st.session_state:
        # Carrega do BigQuery, não só um set() vazio — sem isso, um item removido
        # "voltava sozinho" depois de qualquer reinício do Streamlit/container,
        # porque st.session_state some.
        st.session_state["pub_excluidos"] = carregar_excluidos(client_bq_pipeline)

    # st.tabs() nativo do Streamlit sempre volta pra primeira aba a cada rerun
    # causado por QUALQUER clique dentro de uma aba diferente (comportamento do
    # próprio componente — todo mundo que usa acaba esbarrando nisso). Botões +
    # session_state resolvem: a aba ativa persiste entre reruns porque fica
    # guardada no estado da sessão, não na renderização do widget. Bônus: só o
    # conteúdo da aba ativa roda/renderiza (st.tabs() rodava as 5 sempre, mesmo
    # as invisíveis) — telas mais rápidas, principalmente Publicar e Histórico.
    # "🖼️ Galeria" retirada por enquanto (a pedido) — o código da página continua
    # logo abaixo, só não está na lista de abas, então é só adicionar de volta
    # aqui se precisar reativar.
    ABAS_CAMPINEIRA = ["⚙️ Configurar e Rodar", "📦 Resultados", "🚀 Publicar", "🗂️ Histórico"]
    if "campineira_aba_ativa" not in st.session_state:
        st.session_state["campineira_aba_ativa"] = ABAS_CAMPINEIRA[0]

    # st.container(key=...) gera uma classe CSS estável (.st-key-<key>) — jeito
    # oficialmente suportado (Streamlit 1.31+) de escopar CSS só nesse bloco,
    # bem mais confiável que tentar adivinhar a estrutura do DOM com seletor de
    # irmão (a primeira tentativa não pegou por causa disso).
    st.markdown("""
        <style>
        .st-key-campineira_tabs_row div[data-testid="stHorizontalBlock"] {
            gap: 0.3rem !important;
        }
        .st-key-campineira_tabs_row button {
            border-radius: 6px 6px 0 0 !important;
            border: none !important;
            border-bottom: 2px solid transparent !important;
            padding: 0.35rem 0.5rem !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            box-shadow: none !important;
            transition: background 0.15s ease, color 0.15s ease;
        }
        .st-key-campineira_tabs_row button[kind="secondary"] {
            background: transparent !important;
            color: #9ca3af !important;
        }
        .st-key-campineira_tabs_row button[kind="secondary"]:hover {
            color: #e5e7eb !important;
            background: rgba(255,255,255,0.05) !important;
        }
        .st-key-campineira_tabs_row button[kind="primary"] {
            background: rgba(251,191,36,0.08) !important;
            color: #fbbf24 !important;
            border-bottom: 2px solid #fbbf24 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    with st.container(key="campineira_tabs_row"):
        cols_abas = st.columns(len(ABAS_CAMPINEIRA))
        for col_aba, nome_aba in zip(cols_abas, ABAS_CAMPINEIRA):
            with col_aba:
                ativa = st.session_state["campineira_aba_ativa"] == nome_aba
                if st.button(nome_aba, key=f"btn_aba_{nome_aba}",
                             type="primary" if ativa else "secondary", use_container_width=True):
                    st.session_state["campineira_aba_ativa"] = nome_aba
                    st.rerun()
    aba_ativa = st.session_state["campineira_aba_ativa"]
    st.markdown('<div style="border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 1rem;"></div>', unsafe_allow_html=True)

    # ============================================================
    # ABA 1 — CONFIGURAÇÃO
    # ============================================================
    if aba_ativa == "⚙️ Configurar e Rodar":
        st.markdown("### Configurar Varredura")

        # Retomar varredura interrompida — olha só pro BigQuery (não depende de
        # arquivo local nem session_state), então funciona mesmo se o app tiver
        # reiniciado do zero depois da queda. Só mostra quando nada está rodando
        # agora, pra não competir com uma varredura em andamento.
        if not status.get("rodando"):
            progresso_anterior = buscar_progresso_varredura(client_bq_pipeline)
            if progresso_anterior:
                with st.container(border=True):
                    st.markdown("**📍 Última varredura encontrada**")
                    cats_resumo = ", ".join(
                        f"{nome} (pág. {pag})" for nome, pag in progresso_anterior["categorias"].items()
                    )
                    st.caption(
                        f"{progresso_anterior['total_produtos']} produto(s) capturado(s) — {cats_resumo}. "
                        f"Última atividade: {progresso_anterior['ultima_atividade']}"
                    )
                    if st.button("🔁 Retomar de onde parou", key="btn_retomar_varredura"):
                        cats_resumo_lista = list(progresso_anterior["categorias"].keys())
                        filtros_cat = {c: {"estoque_min": 70, "preco_min": 4.99} for c in cats_resumo_lista}
                        t = threading.Thread(
                            target=rodar_rpa_background,
                            args=(filtros_cat, cats_resumo_lista, True),
                            kwargs={
                                "retomar_id_captura": progresso_anterior["id_captura"],
                                "paginas_ja_feitas": progresso_anterior["categorias"],
                            },
                            daemon=True
                        )
                        t.start()
                        st.success("Retomando varredura! Acompanhe na aba Resultados.")
                        st.rerun()
            st.markdown("---")

        # Inicializa fila no session_state
        if "campineira_fila" not in st.session_state:
            st.session_state["campineira_fila"] = []

        # Seletor para adicionar categoria
        st.markdown("**Adicionar categoria à fila:**")
        col_a, col_b, col_c, col_d = st.columns([3, 1.5, 1.5, 1])

        with col_a:
            opcoes_cats = ["Todas"] + CATEGORIAS
            cat_sel = st.selectbox("Categoria", opcoes_cats)
        with col_b:
            est_input = st.number_input("Quantidade mínima", min_value=0, value=70, step=5)
        with col_c:
            preco_input = st.number_input("Preço >=", min_value=0.0, value=4.99, step=0.50)
        with col_d:
            # Rótulo invisível (mesma altura de um label real) só pra alinhar o botão
            # com a linha dos campos — sem isso ele ficava deslocado pra baixo.
            st.markdown("<div style='visibility:hidden;'>Ação</div>", unsafe_allow_html=True)
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

            # Varredura sempre no modo detalhado (EAN, Fabricante, Cor, Composição...)
            # — precisamos do máximo de informação populada nas tabelas, então não faz
            # sentido oferecer a opção de pular isso pra ganhar velocidade.
            st.session_state["campineira_buscar_detalhes"] = True

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
    # ABA 2 — RESULTADOS EM TABELA
    # ============================================================
    if aba_ativa == "📦 Resultados":
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
                ordem = st.selectbox("Ordenar por", [
                    "Lucro (maior)", "Lucro (menor)",
                    "Estoque (maior)", "Estoque (menor)",
                    "Preço (maior)", "Preço (menor)",
                ])

            # Aplica filtros
            if cat_sel != "Todas":
                validados = [p for p in validados if p['categoria'] == cat_sel]
            if busca:
                validados = [p for p in validados if busca.upper() in p['nome'].upper()]

            def _lucro_max(p):
                """Melhor lucro entre as 4 plataformas — mesmo critério usado como
                ordenação padrão em filtrar_resultados()."""
                return max((p.get(f"lucro_{m}") or 0) for m in ["shein", "shopee", "temu", "tiktok"])

            # Ordena — "Lucro (maior)" é a opção padrão (primeira da lista)
            if ordem == "Lucro (maior)":
                validados.sort(key=_lucro_max, reverse=True)
            elif ordem == "Lucro (menor)":
                validados.sort(key=_lucro_max)
            elif ordem == "Estoque (maior)":
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
                    "Lucro_Maior": _lucro_max(p),
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
                    "💰 Lucro": f"R$ {_lucro_max(p):.2f}",
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

                # Mesmo problema do Histórico: o ImageColumn com URL crua deixa o
                # NAVEGADOR buscar direto na Campineira, sem o Referer que ela exige
                # (bloqueio de hotlink) — a foto aparece quebrada mesmo com a URL
                # certa. Prefere o byte já salvo no histórico (checkpoint da
                # varredura); só cai pra URL crua (que pode ou não funcionar,
                # dependendo do navegador de quem está vendo) se ainda não tiver.
                import base64 as _base64
                import numpy as _np
                _imagens_hist_res = _buscar_imagens_bytes_historico(client_bq_pipeline, df_show["ID"].tolist())
                def _foto_datauri_ou_url(row):
                    b = _imagens_hist_res.get(str(row["ID"]))
                    if b:
                        return f"data:image/jpeg;base64,{_base64.b64encode(b).decode()}"
                    return row["Imagem"] if row["Imagem"] and str(row["Imagem"]).startswith("http") else _np.nan
                df_show["Imagem"] = df_show.apply(_foto_datauri_ou_url, axis=1)
                df_show = df_show.drop(columns=["ID"])
                st.dataframe(df_show, use_container_width=True, hide_index=True,
                             column_config={
                                 "Link": st.column_config.LinkColumn("Link"),
                                 "Imagem": st.column_config.ImageColumn("Foto", width="small"),
                             })

    # ============================================================
    # ABA 3 — GALERIA COM IMAGENS
    # ============================================================
    if aba_ativa == "🖼️ Galeria":
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

            cols_por_linha = 6
            for i in range(0, len(validados), cols_por_linha):
                cols = st.columns(cols_por_linha)
                for j, p in enumerate(validados[i:i+cols_por_linha]):
                    with cols[j]:
                        if p.get('imagem'):
                            img_bytes = carregar_imagem_bytes(p['imagem'])
                            if img_bytes:
                                st.image(img_bytes, use_container_width=True)
                            else:
                                st.markdown("🖼️", unsafe_allow_html=True)
                        st.markdown(f"**{p['nome'][:50]}**")
                        st.markdown(f"🏷️ {p.get('preco', 'N/A')}  |  📦 {p.get('estoque', '?')} un")
                        st.markdown(f"📁 *{p.get('categoria', '')}*")
                        if p.get('link'):
                            st.markdown(f"[Ver produto]({'https://campineira.com.br/' + p['link'] if not p['link'].startswith('http') else p['link']})")
                        st.markdown("---")

    # ============================================================
    # ABA 4 — PUBLICAR NO UPSELLER
    # ============================================================
    if aba_ativa == "🚀 Publicar":
        st.markdown("### 🚀 Publicar Produtos no Upseller")
        st.markdown("---")

        try:
            from modulo_upseller import widget_login_upseller
        except ImportError:
            st.error("❌ Arquivo `modulo_upseller.py` não encontrado na mesma pasta!")
            st.stop()

        widget_login_upseller(client_bq_pipeline)

        # Reaproveita a mesma conexão do resto da página (client_bq_pipeline) em vez
        # de abrir outra — ver nota em pagina_campineira() sobre nunca importar
        # "LeMarketplace" daqui de dentro.
        client_bq_img = client_bq_pipeline

        # ── REPROCESSAR PUBLICAÇÕES COM ERRO NO ARMAZÉM ─────────────
        # Produtos cuja última tentativa de publicar no Armazém (Etapa 1) falhou —
        # nunca chegaram a ser criados. Reconstrói os dados a partir do BigQuery e
        # tenta publicar de novo do zero (gera um SKU novo).
        produtos_armazem_com_erro = listar_produtos_armazem_com_erro(client_bq_img)
        if produtos_armazem_com_erro:
            if "reproc_arm_aberto" not in st.session_state:
                st.session_state["reproc_arm_aberto"] = False
            seta_arm = "▲" if st.session_state["reproc_arm_aberto"] else "▼"
            if st.button(f"🚀 Reprocessar Publicações com Erro no Armazém ({len(produtos_armazem_com_erro)}) {seta_arm}",
                         use_container_width=True, key="btn_toggle_reproc_arm"):
                st.session_state["reproc_arm_aberto"] = not st.session_state["reproc_arm_aberto"]
                st.rerun()
            if st.session_state["reproc_arm_aberto"]:
                for item in produtos_armazem_com_erro:
                    id_item = item["id_produto"]
                    with st.container(border=True):
                        col_info, col_btn = st.columns([4, 1])
                        with col_info:
                            st.markdown(f"**{item['nome']}**")
                            st.caption(f"{item.get('categoria', '')} — {item['mensagem']}")
                            if not item.get("produto"):
                                st.caption("⚠️ Não foi possível recuperar os dados completos do produto no BigQuery.")
                        with col_btn:
                            if not item.get("produto"):
                                st.button("🔄 Reprocessar", key=f"reproc_arm_{id_item}", disabled=True,
                                          use_container_width=True, help="Dados do produto não encontrados")
                            elif not st.session_state.get("ups_logado"):
                                st.button("🔒 Reprocessar", key=f"reproc_arm_{id_item}", disabled=True,
                                          use_container_width=True, help="Faça login no Upseller primeiro")
                            else:
                                if st.button("🔄 Reprocessar", key=f"reproc_arm_{id_item}", use_container_width=True):
                                    # Reusa a mesma função do fluxo normal de publicar (gera
                                    # SKU via tb_sku_registrados, registra em tb_produtos e no
                                    # histórico) — antes esse botão reimplementava uma versão
                                    # própria e incompleta, que nem chegava a registrar o SKU
                                    # gerado em lugar nenhum além do evento do pipeline.
                                    with st.spinner(f"Publicando '{item['nome']}' de novo..."):
                                        ok_arm, msg_arm = _publicar_um_produto_armazem(item["produto"], client_bq_img)
                                    if ok_arm:
                                        st.success(msg_arm)
                                    else:
                                        st.error(msg_arm)

        st.markdown("---")
        st.markdown("### 📦 Produtos Validados para Publicar")

        if not resultados_brutos:
            st.info("Nenhuma varredura realizada. Vá para ⚙️ Configurar e Rodar.")
        else:
            filtros = st.session_state.get("campineira_filtros", {
                cat: {"estoque_min": 70, "preco_min": 4.99} for cat in CATEGORIAS
            })
            validados = filtrar_resultados(resultados_brutos, filtros)

            # Remove quem já tem SKU marcado no histórico (já publicado de
            # verdade, em QUALQUER sessão passada) — antes essa tela só escondia
            # quem foi publicado NESSA sessão (via session_state), então um
            # produto publicado ontem, ou publicado agora mas que sobreviveu a
            # um F5/reinício do app, continuava aparecendo aqui pra publicar de
            # novo, mesmo já tendo SKU cravado no histórico.
            ids_ja_publicados = _ids_com_sku_no_historico(client_bq_pipeline)
            validados = [p for p in validados if str(p.get('id')) not in ids_ja_publicados]

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

            # Separa quem tem foto de verdade (padrão .../produtos/##/foto####.jpg)
            # de quem capturou algo errado (ícone, selo, logo do site) — produto sem
            # foto válida NÃO pode ser publicado no Armazém, fica isolado numa seção
            # à parte pra não travar/poluir a fila principal.
            validados_com_imagem = [p for p in validados if imagem_parece_valida(p.get('imagem'))]
            validados_sem_imagem = [p for p in validados if not imagem_parece_valida(p.get('imagem'))]

            # Some da lista quem já foi publicado com sucesso NESSA sessão — sem
            # isso a tela ficava poluída com cards "publicado" acumulando (o
            # produto publicado já aparece certinho na aba Histórico, não precisa
            # continuar ocupando espaço aqui). Quem falhou continua na lista.
            validados_com_imagem = [p for p in validados_com_imagem if not st.session_state.get(f"pub_{p.get('id')}")]

            # Produto recém-varrido já pode ter a foto salva no histórico (o
            # checkpoint da varredura, a cada 5 páginas, já baixa e guarda os
            # bytes — ver atualizar_historico_bq). Busca essa foto salva
            # PRIMEIRO, e só tenta baixar ao vivo da Campineira (carregar_imagem_bytes,
            # sujeito a bloqueio de TLS/IP dependendo de onde o app está rodando)
            # pra quem ainda não passou por um checkpoint.
            _imagens_historico = _buscar_imagens_bytes_historico(
                client_bq_pipeline, [p.get('id') for p in validados_com_imagem]
            )

            def _renderizar_card_pendente(p, idx, permitir_publicar):
                with st.container(border=True):
                    col_img, col_info, col_btn = st.columns([0.7, 4.3, 1.5])

                    with col_img:
                        img_bytes = _imagens_historico.get(str(p.get('id')))
                        if not img_bytes and p.get('imagem'):
                            img_bytes = carregar_imagem_bytes(p['imagem'])
                        if img_bytes:
                            st.image(img_bytes, use_container_width=True)
                        else:
                            st.markdown("🖼️")

                    with col_info:
                        st.markdown(f"**{p.get('nome', '')}**")
                        st.markdown(
                            f"📦 Estoque: **{p.get('estoque', '?')}** | "
                            f"💰 Custo: **{p.get('preco', 'N/A')}** | "
                            f"📁 {p.get('categoria', '')}"
                        )
                        if not permitir_publicar:
                            st.caption(f"⚠️ Imagem inválida capturada: `{p.get('imagem') or '(vazio)'}`")
                        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                        col_p1.metric("💛 Shein", f"R$ {p.get('preco_shein', 0):.2f}")
                        col_p2.metric("🟠 Shopee", f"R$ {p.get('preco_shopee', 0):.2f}")
                        col_p3.metric("🟡 Temu", f"R$ {p.get('preco_temu', 0):.2f}")
                        col_p4.metric("⚫ TikTok", f"R$ {p.get('preco_tiktok', 0):.2f}")

                    with col_btn:
                        publicado = st.session_state.get(f"pub_{p.get('id')}", False)
                        # Checkbox de seleção — usada tanto pra publicação em massa
                        # quanto pra exclusão em massa (por isso aparece mesmo pra
                        # quem tem imagem inválida e não pode ser publicado: dá pra
                        # selecionar e excluir vários de uma vez do mesmo jeito).
                        if not publicado:
                            st.checkbox("Selecionar", key=f"sel_pub_{p.get('id')}", label_visibility="visible")
                        else:
                            st.markdown("<div style='padding-top:20px'></div>", unsafe_allow_html=True)
                        if not permitir_publicar:
                            st.button("🔒 Publicar", key=f"btn_pub_dis_img_{idx}", disabled=True,
                                      use_container_width=True, help="Corrija a imagem antes de publicar")
                        elif st.session_state.get("ups_logado"):
                            # Mostra o erro da última tentativa de forma persistente — antes
                            # ficava só guardado em pub_msg_{id} sem nunca aparecer na tela
                            # quando a publicação falhava (ex: EAN/código de barra duplicado),
                            # dando a impressão de que nada tinha acontecido.
                            erro_anterior = st.session_state.get(f"pub_msg_{p.get('id')}")
                            if erro_anterior:
                                st.error(f"⛔ {erro_anterior}")
                            if st.button("🚀 Publicar", key=f"btn_pub_{idx}", use_container_width=True, type="primary"):
                                with st.spinner("Publicando..."):
                                    sucesso_pub, msg_pub = _publicar_um_produto_armazem(p, client_bq_pipeline)
                                # Sucesso: sai da lista sozinho no rerun (já filtrado acima)
                                # e o aviso vira um toast — sem card "publicado" acumulando
                                # aqui, já que o produto vai aparecer certinho no Histórico.
                                if sucesso_pub:
                                    st.toast(msg_pub, icon="✅")
                                st.rerun()
                        else:
                            st.button("🔒 Publicar", key=f"btn_pub_dis_{idx}", disabled=True,
                                      use_container_width=True, help="Faça login no Upseller primeiro")
                        # Botão excluir da lista
                        if not publicado:
                            if st.button("🗑️ Remover", key=f"btn_rem_{idx}", use_container_width=True):
                                st.session_state["pub_excluidos"].add(p.get('id'))
                                salvar_excluidos(st.session_state["pub_excluidos"], client_bq_pipeline)
                                st.rerun()

            if validados_sem_imagem:
                if "sem_imagem_aberto" not in st.session_state:
                    st.session_state["sem_imagem_aberto"] = False
                seta_semimg = "▲" if st.session_state["sem_imagem_aberto"] else "▼"
                if st.button(f"⚠️ Produtos Sem Imagem Válida — não publicáveis ({len(validados_sem_imagem)}) {seta_semimg}",
                             use_container_width=True, key="btn_toggle_sem_imagem"):
                    st.session_state["sem_imagem_aberto"] = not st.session_state["sem_imagem_aberto"]
                    st.rerun()
                if st.session_state["sem_imagem_aberto"]:
                    st.caption("Esses produtos capturaram algo errado no lugar da foto (ícone, selo ou logo do "
                               "site) e ficam bloqueados pra publicar até a imagem ser corrigida. Rode a varredura "
                               "dessa categoria de novo pra tentar recapturar a foto certa.")
                    for idx, p in enumerate(validados_sem_imagem):
                        _renderizar_card_pendente(p, f"semimg_{idx}", permitir_publicar=False)

            st.info(f"**{len(validados_com_imagem)}** produtos prontos para publicar")

            # Diagnóstico temporário: se alguma imagem falhou ao carregar nessa
            # tela, mostra o motivo exato (em vez de só a miniatura quebrada
            # muda) — ajuda a confirmar se ainda é bloqueio de TLS, se virou
            # bloqueio por IP (datacenter da nuvem), timeout, etc.
            _erro_img = st.session_state.get("_ultimo_erro_imagem")
            if _erro_img:
                st.caption(f"🩺 Diagnóstico da última falha ao carregar imagem: `{_erro_img}`")

            # Resultado da ÚLTIMA publicação em massa, de forma persistente — o
            # log ao vivo (linhas_log) some no rerun do final do laço, senão.
            resumo_massa = st.session_state.pop("pub_massa_resumo", None)
            if resumo_massa:
                st.success(f"✅ {resumo_massa['ok']} publicado(s) com sucesso, {resumo_massa['erro']} com erro.")

            # Exclusão em massa — mesma checkbox "Selecionar" usada pra publicar,
            # só que aqui considera as DUAS listas (com e sem imagem), já que dá
            # pra excluir independente de poder publicar ou não.
            selecionados_excluir = [
                p for p in (validados_com_imagem + validados_sem_imagem)
                if st.session_state.get(f"sel_pub_{p.get('id')}") and not st.session_state.get(f"pub_{p.get('id')}")
            ]
            if selecionados_excluir:
                if st.button(f"🗑️ Excluir Selecionados ({len(selecionados_excluir)})", use_container_width=True):
                    for p in selecionados_excluir:
                        st.session_state["pub_excluidos"].add(p.get('id'))
                        st.session_state[f"sel_pub_{p.get('id')}"] = False
                    salvar_excluidos(st.session_state["pub_excluidos"], client_bq_pipeline)
                    st.rerun()

            # Publicação em massa — marca "Selecionar" em vários cards e publica
            # todos de uma vez, um atrás do outro (mesma função do botão individual).
            selecionados = [
                p for p in validados_com_imagem
                if st.session_state.get(f"sel_pub_{p.get('id')}") and not st.session_state.get(f"pub_{p.get('id')}")
            ]
            if selecionados:
                if not st.session_state.get("ups_logado"):
                    st.warning(f"🔒 {len(selecionados)} selecionado(s) — faça login no Upseller pra publicar em massa.")
                elif st.button(f"🚀 Publicar Selecionados ({len(selecionados)})", type="primary", use_container_width=True):
                    progresso = st.progress(0.0)
                    log_massa = st.empty()
                    linhas_log = []
                    n_ok, n_erro = 0, 0
                    for i, p in enumerate(selecionados):
                        linhas_log.append(f"→ Publicando {p.get('nome', '')[:60]}...")
                        log_massa.markdown("  \n".join(linhas_log[-8:]))
                        sucesso, msg = _publicar_um_produto_armazem(p, client_bq_pipeline)
                        n_ok += 1 if sucesso else 0
                        n_erro += 0 if sucesso else 1
                        linhas_log[-1] = f"{'✅' if sucesso else '❌'} {p.get('nome', '')[:60]} — {msg[:100]}"
                        log_massa.markdown("  \n".join(linhas_log[-8:]))
                        st.session_state[f"sel_pub_{p.get('id')}"] = False
                        progresso.progress((i + 1) / len(selecionados))
                    st.session_state["pub_massa_resumo"] = {"ok": n_ok, "erro": n_erro}
                    st.rerun()

            for idx, p in enumerate(validados_com_imagem):
                _renderizar_card_pendente(p, idx, permitir_publicar=True)

    # ============================================================
    # ABA HISTÓRICO — ACERVO PERMANENTE DE PRODUTOS DA CAMPINEIRA
    # ============================================================
    if aba_ativa == "🗂️ Histórico":
        st.markdown("### 🗂️ Histórico de Produtos da Campineira")
        st.caption(
            "Diferente da aba **Resultados** (que mostra só a última varredura), este é um "
            "registro permanente — nunca é sobrescrito. Estoque e preço só são atualizados "
            "quando realmente mudam desde a última leitura; o SKU fica gravado assim que o "
            "produto é publicado no Armazém e permanece ali de varredura em varredura."
        )
        st.markdown("---")

        # Reaproveita a mesma conexão já usada no resto da página (a que salva em
        # tb_produtos/tb_sku_registrados ao publicar) em vez de abrir outra — evita
        # uma segunda tentativa de conexão que pode falhar por motivo diferente.
        client_bq_hist = client_bq_pipeline

        if not client_bq_hist:
            st.warning("Sem conexão com o BigQuery no momento — não dá pra consultar o histórico.")
        else:
            try:
                df_hist = client_bq_hist.query(f"""
                    SELECT * FROM `{TABLE_HISTORICO}`
                    ORDER BY data_ultima_leitura DESC
                """).to_dataframe()
            except Exception as e:
                df_hist = pd.DataFrame()
                st.error(f"Erro ao consultar o histórico: {str(e)[:250]}")

            if df_hist.empty:
                st.info("Histórico ainda vazio — rode uma varredura em ⚙️ Configurar e Rodar pra começar a popular.")
            else:
                # Monta a foto a partir dos BYTES armazenados (data URI) — não da URL
                # crua da Campineira. O st.column_config.ImageColumn, quando recebe uma
                # URL, deixa o NAVEGADOR do usuário buscar a imagem direto no site da
                # Campineira, sem o header Referer que ela exige (proteção contra
                # hotlink); por isso as fotos apareciam quebradas aqui mesmo com a URL
                # certa. Produto sem bytes ainda salvos (nunca varrido de novo desde
                # que passamos a guardar isso, ou falhou o download) fica sem foto em
                # vez de mostrar o ícone quebrado.
                import base64 as _base64
                import numpy as _np
                if "imagem_bytes" in df_hist.columns:
                    df_hist["Foto_datauri"] = df_hist["imagem_bytes"].apply(
                        lambda b: f"data:image/jpeg;base64,{_base64.b64encode(b).decode()}"
                        if isinstance(b, (bytes, bytearray)) and b else _np.nan
                    )
                else:
                    df_hist["Foto_datauri"] = _np.nan

                total = len(df_hist)
                publicados = int(df_hist["sku_upseller"].notna().sum())

                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("📦 Total no histórico", total)
                col_m2.metric("✅ Já publicados no Armazém", publicados)
                col_m3.metric("⏳ Aguardando publicação", total - publicados)

                st.markdown("---")

                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    cats_hist = ["Todas"] + sorted(df_hist["categoria"].dropna().unique().tolist())
                    cat_sel_hist = st.selectbox("Categoria", cats_hist, key="hist_cat")
                with col_f2:
                    busca_hist = st.text_input("Buscar por nome ou SKU", key="hist_busca")
                with col_f3:
                    status_hist = st.selectbox("Status", ["Todos", "✅ Publicados", "⏳ Não publicados"], key="hist_status")

                df_view = df_hist.copy()
                if cat_sel_hist != "Todas":
                    df_view = df_view[df_view["categoria"] == cat_sel_hist]
                if busca_hist:
                    alvo = busca_hist.strip().upper()
                    mask = (
                        df_view["nome"].fillna("").str.upper().str.contains(alvo)
                        | df_view["sku_upseller"].fillna("").str.upper().str.contains(alvo)
                    )
                    df_view = df_view[mask]
                if status_hist == "✅ Publicados":
                    df_view = df_view[df_view["sku_upseller"].notna()]
                elif status_hist == "⏳ Não publicados":
                    df_view = df_view[df_view["sku_upseller"].isna()]

                st.caption(f"**{len(df_view)}** produto(s) — ordenado pela leitura mais recente")

                # Preço sugerido por plataforma, calculado do custo (mesma
                # margem/regra usada em Resultados e Galeria — calcular_precos_sugeridos).
                precos_sugeridos = df_view["preco"].apply(calcular_precos_sugeridos).apply(pd.Series)
                df_view = pd.concat([df_view.reset_index(drop=True), precos_sugeridos.reset_index(drop=True)], axis=1)

                df_show_hist = df_view.rename(columns={
                    "nome": "Nome",
                    "categoria": "Categoria",
                    "estoque": "Estoque",
                    "preco": "Custo",
                    "sku_upseller": "SKU",
                    "Foto_datauri": "Foto",
                    "data_primeira_leitura": "1ª Leitura",
                    "data_ultima_leitura": "Última Leitura",
                    "data_ultima_atualizacao": "Última Atualização",
                    "preco_shein": "Shein",
                    "preco_shopee": "Shopee",
                    "preco_temu": "Temu",
                    "preco_tiktok": "TikTok",
                })
                colunas_exibir = [
                    "Foto", "Nome", "Categoria", "Estoque", "Custo",
                    "Shein", "Shopee", "Temu", "TikTok", "SKU",
                    "1ª Leitura", "Última Leitura", "Última Atualização",
                ]
                st.dataframe(
                    df_show_hist[colunas_exibir],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "Foto": st.column_config.ImageColumn("Foto", width="small"),
                        "SKU": st.column_config.TextColumn("SKU"),
                        "Shein": st.column_config.NumberColumn("Shein", format="R$ %.2f"),
                        "Shopee": st.column_config.NumberColumn("Shopee", format="R$ %.2f"),
                        "Temu": st.column_config.NumberColumn("Temu", format="R$ %.2f"),
                        "TikTok": st.column_config.NumberColumn("TikTok", format="R$ %.2f"),
                    }
                )