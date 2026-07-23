# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import re
import urllib.parse
import json
import os
import io
import base64
from datetime import datetime, timedelta, date
from google.cloud import bigquery
from google.oauth2 import service_account
import plotly.graph_objects as go

# --- CONFIGURAÇÕES DE INICIALIZAÇÃO ---

if 'pg' not in st.session_state:
    st.session_state.pg = "Início"

if 'logado' not in st.session_state: 
    st.session_state.logado = False

# Garante que a variável do painel financeiro comece falsa caso não exista
if 'fin_acesso' not in st.session_state:
    st.session_state.fin_acesso = False

# --- CONFIGURAÇÕES DE PÁGINA ---
st.set_page_config(
    page_title="D.L Online Store", 
    page_icon="🛒", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- ESTILIZAÇÃO CUSTOMIZADA (DESIGN PROFISSIONAL) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');
    
    * {
        font-family: 'Inter', sans-serif !important;
    }
    
    .stApp { 
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fc 100%) !important; 
    }
    
    [data-testid="stSidebar"] { 
        background: linear-gradient(180deg, #1a1f3a 0%, #0d1225 100%) !important; 
        border-right: none;
    }
    
    h1, h2, h3 { 
        font-family: 'Playfair Display', serif !important;
        color: #1a1f3a !important;
        font-weight: 700 !important;
    }
    
    p, span, label, .stMarkdown { 
        color: #2d3748 !important;
        font-weight: 400;
    }
    
    .stTable, [data-testid="stTable"] {
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }

    .plot-container {
        border: 1px solid #e2e8f0 !important; 
        border-radius: 16px !important;
        padding: 20px !important;
        background: linear-gradient(135deg, #ffffff 0%, #f7fafc 100%) !important;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07);
    }

    .historico-scroll-container {
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        max-height: 800px !important;
        overflow-y: auto !important;
        background: white;
    }
    
    .linha-historico {
        padding: 12px 16px;
        border-bottom: 1px solid #f0f4f8;
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        background: white;
    }
    
    .linha-historico:nth-child(odd) { background: #fafbfc; }
    .linha-historico:hover { 
        background: #f0f4f8 !important;
        border-left: 4px solid #fbbf24;
    }

    section[data-testid="stSidebar"] .stButton button {
        width: 100% !important;
        border-radius: 10px !important;
        height: 3.2em !important;
        background-color: transparent !important;
        color: #e0e7ff !important;
        border: 1px solid rgba(224, 231, 255, 0.2) !important;
        text-align: left !important;
        padding-left: 18px !important;
        margin-bottom: 6px !important;
        display: block !important;
        font-weight: 500;
        transition: all 0.3s ease !important;
    }
    
    section[data-testid="stSidebar"] .stButton p { 
        font-size: 14px !important; 
        white-space: nowrap !important;
        color: #e0e7ff !important;
    }

    section[data-testid="stSidebar"] .stButton button:hover { 
        background-color: rgba(251, 191, 36, 0.15) !important; 
        border: 1px solid #fbbf24 !important; 
        color: #fbbf24 !important; 
    }
    
    section[data-testid="stSidebar"] .stButton button[type="primary"] {
        background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%) !important; 
        color: #1a1f3a !important; 
        border: none !important; 
        text-align: center !important; 
        font-weight: 600 !important;
        padding-left: 0px !important;
    }

    section[data-testid="stSidebar"] .stButton button[type="primary"]:hover {
        box-shadow: 0 8px 16px rgba(251, 191, 36, 0.3) !important;
        transform: translateY(-2px) !important;
    }

    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #fbbf24 !important;
        font-family: 'Inter', sans-serif !important;
    }

    section[data-testid="stSidebar"] .stSelectbox,
    section[data-testid="stSidebar"] .stTextInput {
        margin-bottom: 12px !important;
    }

    [data-testid="stImage"] img { 
        height: auto; 
        object-fit: contain; 
        width: 100%;
        border-radius: 8px;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] {
        background: transparent !important;
        border: 1px solid rgba(251, 191, 36, 0.2) !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] button {
        color: #e0e7ff !important;
        font-weight: 600 !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] button:hover {
        color: #fbbf24 !important;
        background: rgba(251, 191, 36, 0.1) !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] {
        background: rgba(15, 18, 37, 0.8) !important;
        border: 1px solid rgba(251, 191, 36, 0.2) !important;
        border-top: none;
    }

    .metric-card {
        background: linear-gradient(135deg, #ffffff 0%, #f7fafc 100%) !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        padding: 20px !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05) !important;
        transition: all 0.3s ease !important;
    }

    .metric-card:hover {
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1) !important;
        transform: translateY(-2px) !important;
    }

    .section-header {
        border-bottom: 3px solid #fbbf24;
        padding-bottom: 12px;
        margin-bottom: 20px;
    }

    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #ffffff 0%, #f7fafc 100%) !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        padding: 16px !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05) !important;
    }

    [data-testid="stExpander"] {
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05) !important;
    }

    .divider {
        border-bottom: 2px solid #e2e8f0;
        margin: 24px 0;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXÃO COM BIGQUERY ---
@st.cache_resource
def conectar_bigquery():
    try:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(info)
        client = bigquery.Client(credentials=creds, project=info['project_id'])
        return client
    except Exception as e:
        st.error(f"Erro ao conectar no BigQuery: {e}")
        return None

client_bq = conectar_bigquery()

# --- FUNÇÕES DE BUSCA ---
def buscar_produtos_bq():
    if client_bq:
        query = "SELECT * FROM `leandro-marketplace.DL_Store_Online.tb_produtos`"
        return client_bq.query(query).to_dataframe()
    return pd.DataFrame()

# --- INICIALIZAÇÃO DA BASE DE DADOS ---
df_base_completa = pd.DataFrame()

if st.session_state.logado and client_bq:
    try:
        df_base_completa = buscar_produtos_bq()
        if not df_base_completa.empty:
            df_base_completa = df_base_completa.drop_duplicates(subset=['SKU'])
    except Exception as e:
        st.error(f"Erro ao carregar base de produtos: {e}")

# --- FUNÇÕES DE CÁLCULO ---
# Cálculo de preço/lucro fica num módulo neutro compartilhado com modulo_campineira.py
# (ver calculos_marketplace.py — evita que um importe o outro como script principal).
from calculos_marketplace import converter_custo_seguro, calcular_venda_completo

# --- SIDEBAR PROFISSIONAL ---
with st.sidebar:
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h2 style="margin: 0; font-size: 24px; color: #fbbf24;">D.L Online Store</h2>
            <p style="margin: 4px 0 0 0; color: #9ca3af; font-size: 12px; letter-spacing: 1px;">MARKETPLACE MANAGER</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    
    # Navegação Pública
    st.markdown('<p style="color: #9ca3af; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-bottom: 12px;">Público</p>', unsafe_allow_html=True)
    if st.button("🏠 Início"): 
        st.session_state.pg = "Início"
        st.rerun()
    if st.button("👥 Quem Somos"): 
        st.session_state.pg = "Quem Somos"
        st.rerun()
    if st.button("🛠️ Serviços"): 
        st.session_state.pg = "Serviços"
        st.rerun()
    if st.button("✉️ Contato"): 
        st.session_state.pg = "Contato"
        st.rerun()
        
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    
    # --- FLUXO DE LOGIN ---
    if not st.session_state.logado:
        st.markdown('<p style="color: #fbbf24; font-size: 14px; font-weight: 600; margin-bottom: 16px;">🔐 Área do Vendedor</p>', unsafe_allow_html=True)
        u = st.text_input("Usuário", label_visibility="collapsed", placeholder="Usuário")
        p = st.text_input("Senha", type="password", label_visibility="collapsed", placeholder="Senha")
        if st.button("Entrar no Painel", type="primary", use_container_width=True):
            if u == "leandro" and p == "123":
                st.session_state.logado = True
                st.session_state.pg = "Calculadora" 
                st.rerun()
            else: 
                st.error("Usuário ou senha incorretos.")
    else:
        st.markdown(f'<p style="color: #fbbf24; font-size: 14px; font-weight: 600; margin-bottom: 16px;">👋 Bem-vindo, Leandro</p>', unsafe_allow_html=True)
        
        st.markdown('<p style="color: #9ca3af; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-bottom: 12px; margin-top: 20px;">Operações</p>', unsafe_allow_html=True)
        if st.button("📊 Comparativo de Preços"):
            st.session_state.pg = "Calculadora"
            st.rerun()
        if st.button("📝 Novo Item na Base"): 
            st.session_state.pg = "Cadastro"
            st.rerun()
        if st.button("💰 Alterar Preços"): 
            st.session_state.pg = "Alterar Preco"
            st.rerun()
        if st.button("📦 Gestão de Estoque"):
            st.session_state.pg = "Gestão de Estoque"
            st.rerun()
        if st.button("🏭 Campineira"):
            st.session_state.pg = "Campineira"
            st.rerun()
            
        if st.button("📉 Dashboard Financeiro"):
            st.session_state.fin_acesso = False
            st.session_state.pg = "Dashboard"
            st.rerun()

        if st.button("🔎 Validar Vendas"):
            st.session_state.pg = "Validar Vendas"
            st.rerun()

        # --- LOGOUT ---
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        if st.button("🚪 Sair", use_container_width=True):
            st.session_state.logado = False
            st.session_state.fin_acesso = False
            st.session_state.pg = "Início"
            st.rerun()

    # --- RODAPÉ ---
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="text-align: center; color: #6b7280; font-size: 11px; margin-top: 12px;">Desenvolvido por DataStream BI</p>',
        unsafe_allow_html=True
    )

def importar_pedidos_upseller_para_dashboard(client_bq, caminho_excel):
    """Lê o Excel exportado do Upseller (Pedidos > Enviado) e insere em
    tb_vendas_realizadas as vendas que ainda não estão lá (checa por
    numero_pedido, nunca duplica um pedido já importado). Lucro líquido = valor
    do pedido - custo de aquisição (via SKU em tb_produtos) - taxas da própria
    plataforma (calcular_lucro_realizado, mesmas taxas usadas no resto do app).
    Retorna (inseridas, duplicadas, erros, mensagens_de_erro)."""
    import pandas as pd
    from calculos_marketplace import calcular_lucro_realizado, obter_sku_base

    df = pd.read_excel(caminho_excel)

    def achar_coluna(nomes_exatos, *grupos_palavras_fallback):
        """Tenta achar a coluna por NOME EXATO primeiro (case-insensitive) — mais
        preciso que só palavra-chave, importante porque várias colunas do Excel da
        Upseller compartilham palavras (ex: "Plataformas" e "Nº de Pedido da
        Plataforma" ambas contêm "plataforma"; "quantidade mapeada" e "Quantidade
        de Produtos" ambas contêm "quantidade"). Só cai pro fallback por
        palavra-chave se nenhum nome exato bater (planilha com cabeçalho diferente)."""
        cols_low = {c: str(c).strip().lower() for c in df.columns}
        for nome in nomes_exatos:
            alvo = nome.strip().lower()
            for col, low in cols_low.items():
                if low == alvo:
                    return col
        for palavras in grupos_palavras_fallback:
            for col, low in cols_low.items():
                if all(p in low for p in palavras):
                    return col
        return None

    # Nomes confirmados no Excel real de "Pedidos > Enviado" do Upseller.
    col_pedido = achar_coluna(["Nº de Pedido", "N° de Pedido"], ("número", "pedido"), ("pedido", "id"))
    col_pagamento = achar_coluna(["Hora do Pagamento"], ("hora", "pagamento"), ("pagamento",))
    col_plataforma = achar_coluna(["Plataformas", "Plataforma"], ("plataforma",))
    # "SKU (Armazém)" costuma vir vazia pra boa parte das linhas do export — cai
    # pra coluna "SKU" (a da plataforma) quando a do armazém estiver em branco.
    col_sku_armazem = achar_coluna(["SKU (Armazém)", "SKU (Armazem)"], ("sku", "armaz"))
    col_sku_plain = achar_coluna(["SKU"], ("sku",))
    col_valor = achar_coluna(["Valor do Pedido"], ("valor", "pedido"))
    # Temu: "Valor do Pedido" vem com algo a mais embutido (não é só o produto,
    # provavelmente frete/logística cross-border) — pra essa plataforma usamos
    # "Valor Total de Produtos" em vez disso. As outras plataformas continuam
    # com "Valor do Pedido" normalmente.
    col_valor_produtos_temu = achar_coluna(["Valor Total de Produtos"], ("valor", "total", "produtos"))
    col_qtd = achar_coluna(["Qtd. do Produto", "Qtd do Produto", "Quantidade de Produtos"], ("qtd", "produto"))
    # Mesma lógica pro nome: "Nome do Produto" também costuma vir vazia — cai
    # pra "Nome do Anúncio" (nome usado no anúncio da plataforma).
    col_nome_produto = achar_coluna(["Nome do Produto"], ("nome", "produto"))
    col_nome_anuncio = achar_coluna(["Nome do Anúncio", "Nome do Anuncio"], ("nome", "anúncio"), ("nome", "anuncio"))

    faltando = [nome for nome, col in [
        ("Número do Pedido", col_pedido), ("Hora do Pagamento", col_pagamento),
        ("Plataforma", col_plataforma), ("Valor do Pedido", col_valor),
    ] if col is None]
    if col_sku_armazem is None and col_sku_plain is None:
        faltando.append("SKU")
    if faltando:
        return 0, 0, 0, [f"Não encontrei as colunas: {', '.join(faltando)}. "
                          f"Colunas disponíveis no Excel: {list(df.columns)}"]

    table_vendas = "leandro-marketplace.DL_Store_Online.tb_vendas_realizadas"
    table_produtos = "leandro-marketplace.DL_Store_Online.tb_produtos"

    # Pedidos já importados antes — carregado uma vez só (não 1 query por linha).
    pedidos_existentes = set()
    try:
        df_exist = client_bq.query(
            f"SELECT DISTINCT numero_pedido FROM `{table_vendas}` WHERE numero_pedido IS NOT NULL"
        ).to_dataframe()
        pedidos_existentes = set(df_exist["numero_pedido"].astype(str))
    except Exception:
        pass  # coluna numero_pedido pode ainda não existir na tabela (rode o ALTER TABLE)

    custos_por_sku = {}
    try:
        df_custos = client_bq.query(f"SELECT sku, custo_aquisicao FROM `{table_produtos}`").to_dataframe()
        custos_por_sku = df_custos.groupby("sku")["custo_aquisicao"].first().to_dict()
    except Exception:
        pass

    def _normalizar_plataforma(bruto):
        b = str(bruto or "").strip().lower()
        if "shopee" in b: return "shopee"
        if "shein" in b: return "shein"
        if "tiktok" in b or "tik tok" in b: return "tiktok"
        if "temu" in b: return "temu"
        return b

    inseridas, duplicadas, erros = 0, 0, 0
    msgs_erro = []
    linhas_novas = []

    for _, row in df.iterrows():
        try:
            numero_pedido = str(row[col_pedido]).strip()
            if not numero_pedido or numero_pedido.lower() == "nan":
                continue
            if numero_pedido in pedidos_existentes:
                duplicadas += 1
                continue

            plataforma = _normalizar_plataforma(row[col_plataforma])

            # Temu usa "Valor Total de Produtos" em vez de "Valor do Pedido"
            # ("Valor do Pedido" vem com algo a mais embutido nessa plataforma,
            # não é só o produto) — as outras plataformas seguem com "Valor do
            # Pedido" normalmente.
            col_valor_usar = col_valor_produtos_temu if (plataforma == "temu" and col_valor_produtos_temu is not None) else col_valor

            # Pedido com várias linhas de produto costuma repetir o Nº de Pedido e
            # só preencher o valor na linha principal — as outras vêm
            # zeradas/vazias pra não contar o valor do pedido mais de uma vez.
            # Ignora essas linhas "extras" (não é erro, só não é a linha certa).
            if pd.isna(row[col_valor_usar]) or float(row[col_valor_usar]) == 0:
                continue

            data_pagamento = pd.to_datetime(row[col_pagamento]).date()

            sku_armazem = str(row[col_sku_armazem]).strip() if col_sku_armazem and pd.notna(row[col_sku_armazem]) else ""
            sku_plain = str(row[col_sku_plain]).strip() if col_sku_plain and pd.notna(row[col_sku_plain]) else ""
            sku = sku_armazem or sku_plain

            valor_pedido = float(row[col_valor_usar])
            quantidade = int(row[col_qtd]) if col_qtd and pd.notna(row[col_qtd]) else 1

            nome_prod_val = str(row[col_nome_produto]).strip() if col_nome_produto and pd.notna(row[col_nome_produto]) else ""
            nome_anuncio_val = str(row[col_nome_anuncio]).strip() if col_nome_anuncio and pd.notna(row[col_nome_anuncio]) else ""
            nome_produto = nome_prod_val or nome_anuncio_val or sku

            # SKU exato sem custo cadastrado? cai pro custo do SKU principal (sem o
            # sufixo de variante/cor) — ex: CP-784-AM usa o custo de CP-784.
            custo_aquisicao = custos_por_sku.get(sku)
            if custo_aquisicao is None:
                custo_aquisicao = custos_por_sku.get(obter_sku_base(sku))
            custo_aquisicao = float(custo_aquisicao or 0)
            # Sem custo achado (nem exato, nem via SKU principal) = lucro calculado
            # às cegas (custo 0). Marca como pendente pra NÃO entrar no Dashboard
            # ainda — só sai de pendente quando o SKU for cadastrado na aba
            # Validar Vendas (que recalcula e desmarca essa flag).
            pendente = custo_aquisicao <= 0
            lucro = calcular_lucro_realizado(valor_pedido, custo_aquisicao, plataforma)

            linhas_novas.append({
                "produto": nome_produto,
                "sku": sku,
                "preco_venda": valor_pedido,
                "quantidade": quantidade,
                "data": data_pagamento.strftime("%Y-%m-%d"),
                "lucro_total": round(lucro, 2),
                "mkt_venda": plataforma,
                "numero_pedido": numero_pedido,
                "pendente": pendente,
            })
            pedidos_existentes.add(numero_pedido)  # evita duplicar dentro do mesmo arquivo
            inseridas += 1
        except Exception as e:
            erros += 1
            msgs_erro.append(f"Pedido {row.get(col_pedido, '?')}: {str(e)[:100]}")

    if linhas_novas:
        # load_table_from_dataframe (carga em lote) em vez de insert_rows_json
        # (streaming): linhas gravadas via streaming ficam presas no "streaming
        # buffer" por um tempo, bloqueando DELETE/UPDATE — mesmo problema já visto
        # em outras tabelas desse projeto.
        try:
            df_novas = pd.DataFrame(linhas_novas)
            # "data" precisa virar datetime64 de verdade (não string solta) — o
            # pandas guarda como coluna "object" e o pyarrow não consegue inferir
            # sozinho um tipo de data pra isso, e falha a conversão pro formato que
            # o BigQuery espera. O schema explícito também evita qualquer
            # autodetecção errada de outro campo.
            df_novas["data"] = pd.to_datetime(df_novas["data"]).dt.date
            job_config = bigquery.LoadJobConfig(schema=[
                bigquery.SchemaField("produto", "STRING"),
                bigquery.SchemaField("sku", "STRING"),
                bigquery.SchemaField("preco_venda", "FLOAT"),
                bigquery.SchemaField("quantidade", "INTEGER"),
                bigquery.SchemaField("data", "DATE"),
                bigquery.SchemaField("lucro_total", "FLOAT"),
                bigquery.SchemaField("mkt_venda", "STRING"),
                bigquery.SchemaField("numero_pedido", "STRING"),
                bigquery.SchemaField("pendente", "BOOLEAN"),
            ])
            client_bq.load_table_from_dataframe(df_novas, table_vendas, job_config=job_config).result()
        except Exception as e:
            erros += len(linhas_novas)
            inseridas = 0
            msgs_erro.append(f"Erro ao inserir no BigQuery: {str(e)[:300]}")

    return inseridas, duplicadas, erros, msgs_erro


def buscar_pendencias_validacao(client_bq):
    """Levanta os dois problemas que deixam o lucro calculado errado: SKU
    vendido que não tem cadastro em tb_produtos (custo vira 0), e SKU
    cadastrado com custo de aquisição divergente entre as linhas por
    marketplace (o sistema pega uma delas meio ao acaso na hora de calcular)."""
    table_vendas = "leandro-marketplace.DL_Store_Online.tb_vendas_realizadas"
    table_produtos = "leandro-marketplace.DL_Store_Online.tb_produtos"

    # Uma variante (CP-784-AM) não conta como "sem cadastro" se o SKU principal
    # dela (CP-784, sem o sufixo depois do 2º hífen) já tem custo cadastrado —
    # nesse caso o custo do principal é usado como fallback automaticamente
    # (ver obter_sku_base / importar_pedidos_upseller_para_dashboard).
    q_sem_cadastro = f"""
        SELECT v.sku, ANY_VALUE(v.produto) AS produto,
               COUNT(*) AS vendas, SUM(v.preco_venda) AS faturamento,
               MIN(v.data) AS data_min, MAX(v.data) AS data_max
        FROM `{table_vendas}` v
        LEFT JOIN (SELECT DISTINCT sku FROM `{table_produtos}`) p
          ON v.sku = p.sku
          OR REGEXP_EXTRACT(v.sku, r'^([A-Za-z]+-\\d+)-.+$') = p.sku
        WHERE p.sku IS NULL AND v.sku IS NOT NULL AND v.sku != ''
        GROUP BY v.sku
        ORDER BY faturamento DESC
    """
    df_sem_cadastro = client_bq.query(q_sem_cadastro).to_dataframe()

    # Traz também quantas vendas cada SKU divergente já teve — dá pra ver de
    # cara quais desses são urgentes (têm venda de verdade pendurada) e quais
    # são só inconsistência de catálogo sem impacto ainda.
    q_divergentes = f"""
        SELECT p.sku, ANY_VALUE(p.produto) AS produto,
               ARRAY_AGG(DISTINCT p.custo_aquisicao ORDER BY p.custo_aquisicao) AS valores,
               COUNT(v.numero_pedido) AS vendas
        FROM `{table_produtos}` p
        LEFT JOIN `{table_vendas}` v ON v.sku = p.sku
        GROUP BY p.sku
        HAVING COUNT(DISTINCT p.custo_aquisicao) > 1
        ORDER BY vendas DESC, p.sku
    """
    df_divergentes_raw = client_bq.query(q_divergentes).to_dataframe()
    df_divergentes = _agrupar_divergentes_por_sku_base(df_divergentes_raw)

    return df_sem_cadastro, df_divergentes


def _agrupar_divergentes_por_sku_base(df):
    """Uma variante (CP-209-RS, cor rosa) e sua irmã (CP-209-AZ, cor azul) são o
    MESMO produto físico — custo de aquisição não muda por cor/tamanho. Corrigir
    uma sem corrigir a outra deixa a divergência pela metade. Agrupa as linhas de
    SKU divergente pelo SKU principal (sem sufixo de variante) pra corrigir a
    família inteira de uma vez, com um custo só."""
    from calculos_marketplace import obter_sku_base

    if df.empty:
        return pd.DataFrame(columns=["sku_base", "skus", "produto", "valores", "vendas"])

    df = df.copy()
    df["sku_base"] = df["sku"].apply(obter_sku_base)

    linhas = []
    for base, grupo in df.groupby("sku_base"):
        grupo_ordenado = grupo.sort_values("vendas", ascending=False)
        valores_unicos = sorted({round(float(v), 2) for lista in grupo["valores"] for v in lista})
        linhas.append({
            "sku_base": base,
            "skus": grupo_ordenado["sku"].tolist(),
            "produto": grupo_ordenado["produto"].iloc[0],
            "valores": valores_unicos,
            "vendas": int(grupo["vendas"].sum()),
        })
    return pd.DataFrame(linhas).sort_values("vendas", ascending=False).reset_index(drop=True)


def _recalcular_lucro_por_sku(client_bq, sku, custo_aquisicao):
    """Depois de corrigir o custo de aquisição de um SKU (cadastro novo ou
    correção de divergência), as vendas JÁ importadas desse SKU ficaram com
    lucro_total calculado com o custo antigo (0 ou errado) — recalcula e
    atualiza essas linhas em tb_vendas_realizadas de uma vez, via UPDATE ...
    FROM UNNEST (sem precisar de tabela de staging)."""
    from calculos_marketplace import calcular_lucro_realizado

    table_vendas = "leandro-marketplace.DL_Store_Online.tb_vendas_realizadas"

    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("sku", "STRING", sku)
    ])
    df = client_bq.query(
        f"SELECT numero_pedido, preco_venda, mkt_venda FROM `{table_vendas}` "
        f"WHERE sku = @sku AND numero_pedido IS NOT NULL",
        job_config=job_config,
    ).to_dataframe()
    if df.empty:
        return 0

    structs = []
    for _, row in df.iterrows():
        novo_lucro = calcular_lucro_realizado(float(row["preco_venda"]), custo_aquisicao, row["mkt_venda"])
        structs.append(bigquery.StructQueryParameter(
            None,
            bigquery.ScalarQueryParameter("numero_pedido", "STRING", str(row["numero_pedido"])),
            bigquery.ScalarQueryParameter("lucro_total", "FLOAT64", round(float(novo_lucro), 2)),
        ))

    array_param = bigquery.ArrayQueryParameter("correcoes", "STRUCT", structs)
    update_sql = f"""
        UPDATE `{table_vendas}` v
        SET lucro_total = c.lucro_total, pendente = FALSE
        FROM UNNEST(@correcoes) AS c
        WHERE v.numero_pedido = c.numero_pedido
    """
    client_bq.query(update_sql, job_config=bigquery.QueryJobConfig(query_parameters=[array_param])).result()
    return len(structs)


def resolver_sku_sem_cadastro(client_bq, sku, produto, custo_aquisicao):
    """Cadastra um SKU novo em tb_produtos — uma linha por marketplace, mesmo
    custo pras 4 — e recalcula o lucro das vendas já importadas desse SKU."""
    table_produtos = "leandro-marketplace.DL_Store_Online.tb_produtos"
    lote = [{
        "marketplace": mkt, "sku": sku, "produto": produto, "custo_aquisicao": float(custo_aquisicao),
    } for mkt in ["shein", "shopee", "temu", "tiktok"]]
    client_bq.load_table_from_dataframe(pd.DataFrame(lote), table_produtos).result()
    return _recalcular_lucro_por_sku(client_bq, sku, float(custo_aquisicao))


def resolver_sku_divergente(client_bq, sku, novo_custo):
    """Unifica o custo_aquisicao de um SKU em todas as linhas (uma por
    marketplace) de tb_produtos e recalcula o lucro das vendas já importadas."""
    table_produtos = "leandro-marketplace.DL_Store_Online.tb_produtos"
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("novo_custo", "FLOAT64", float(novo_custo)),
        bigquery.ScalarQueryParameter("sku", "STRING", sku),
    ])
    client_bq.query(
        f"UPDATE `{table_produtos}` SET custo_aquisicao = @novo_custo WHERE sku = @sku",
        job_config=job_config,
    ).result()
    return _recalcular_lucro_por_sku(client_bq, sku, float(novo_custo))


def resolver_grupo_divergente(client_bq, skus, novo_custo):
    """Como resolver_sku_divergente, mas pra uma família inteira de variantes
    (mesmo SKU principal, cores/tamanhos diferentes) de uma vez — cor/tamanho
    não muda o custo de aquisição do produto, então corrigir só uma variante e
    deixar as irmãs com o valor velho não faz sentido."""
    table_produtos = "leandro-marketplace.DL_Store_Online.tb_produtos"
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("novo_custo", "FLOAT64", float(novo_custo)),
        bigquery.ArrayQueryParameter("skus", "STRING", list(skus)),
    ])
    client_bq.query(
        f"UPDATE `{table_produtos}` SET custo_aquisicao = @novo_custo WHERE sku IN UNNEST(@skus)",
        job_config=job_config,
    ).result()
    total_recalculadas = 0
    for sku in skus:
        total_recalculadas += _recalcular_lucro_por_sku(client_bq, sku, float(novo_custo))
    return total_recalculadas


def aplicar_fallback_sku_base(client_bq):
    """Recalcula de uma vez o lucro de todas as vendas já importadas cujo SKU
    exato não tem custo cadastrado, mas o SKU principal (sem o sufixo de
    variante/cor) tem — mesma regra usada na importação (obter_sku_base),
    aplicada retroativamente no histórico que ficou pra trás antes desse
    fallback existir. Não pede nada digitado: o custo já é conhecido via o
    principal."""
    from calculos_marketplace import calcular_lucro_realizado, obter_sku_base

    table_vendas = "leandro-marketplace.DL_Store_Online.tb_vendas_realizadas"
    table_produtos = "leandro-marketplace.DL_Store_Online.tb_produtos"

    df_prod = client_bq.query(f"SELECT DISTINCT sku, custo_aquisicao FROM `{table_produtos}`").to_dataframe()
    custos_por_sku = df_prod.groupby("sku")["custo_aquisicao"].first().to_dict()
    skus_cadastrados = set(custos_por_sku.keys())

    df_v = client_bq.query(
        f"SELECT numero_pedido, sku, preco_venda, mkt_venda FROM `{table_vendas}` "
        f"WHERE numero_pedido IS NOT NULL AND sku IS NOT NULL AND sku != ''"
    ).to_dataframe()
    if df_v.empty:
        return 0

    structs = []
    for _, row in df_v.iterrows():
        sku = row["sku"]
        if sku in skus_cadastrados:
            continue  # já tem custo próprio, não é caso de fallback
        base = obter_sku_base(sku)
        if base == sku or base not in skus_cadastrados:
            continue  # não é variante, ou nem o principal tem custo cadastrado
        custo = float(custos_por_sku[base] or 0)
        novo_lucro = calcular_lucro_realizado(float(row["preco_venda"]), custo, row["mkt_venda"])
        structs.append(bigquery.StructQueryParameter(
            None,
            bigquery.ScalarQueryParameter("numero_pedido", "STRING", str(row["numero_pedido"])),
            bigquery.ScalarQueryParameter("lucro_total", "FLOAT64", round(float(novo_lucro), 2)),
        ))

    if not structs:
        return 0

    array_param = bigquery.ArrayQueryParameter("correcoes", "STRUCT", structs)
    update_sql = f"""
        UPDATE `{table_vendas}` v
        SET lucro_total = c.lucro_total, pendente = FALSE
        FROM UNNEST(@correcoes) AS c
        WHERE v.numero_pedido = c.numero_pedido
    """
    client_bq.query(update_sql, job_config=bigquery.QueryJobConfig(query_parameters=[array_param])).result()
    return len(structs)


# --- LÓGICA DE PÁGINAS ---

# --- PÁGINA INÍCIO ---
if st.session_state.pg == "Início":
    caminho_local = r"C:\Users\Junior\Desktop\CodigosPython2\banner_inicio.jpg"
    if os.path.exists(caminho_local):
        st.image(caminho_local, use_container_width=True)
    elif os.path.exists("banner_inicio.jpg"):
        st.image("banner_inicio.jpg", use_container_width=True)
    else:
        st.image("https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=crop&w=1000&q=80", use_container_width=True)
    
    st.markdown("""
    <h1 style="text-align: center; font-size: 42px; margin-bottom: 8px;">Bem-vindo à D.L Online Store</h1>
    <p style="text-align: center; color: #6b7280; font-size: 16px; margin-bottom: 40px;">Sua Experiência de Compra Inteligente</p>
    """, unsafe_allow_html=True)
    
    col_a, col_b, col_c = st.columns([1,3,1])
    with col_b:
        st.markdown("""
        ### Na D.L Online Store
        
        Nossa missão vai além de vender produtos. Estamos focados em conectar você às melhores oportunidades dos maiores marketplaces do mundo, garantindo uma curadoria de qualidade e preços competitivos.
        
        #### Nosso Maior Compromisso: Você
        
        Acreditamos que a verdadeira venda só termina quando você está satisfeito. Por isso, fundamentamos nossa operação em:
        
        **🌟 Satisfação Garantida** — Trabalhamos incansavelmente para que sua experiência seja perfeita.
        
        **🛡️ Qualidade e Confiança** — Selecionamos produtos com rigor para garantir que você receba o melhor.
        
        **🤝 Suporte Ágil** — Nossa equipe está sempre pronta para ouvir e resolver suas dúvidas.
        
        ---
        
        Obrigado por escolher a **D.L Online Store**. Boas compras!
        """)

elif st.session_state.pg == "Quem Somos":
    st.markdown('<h1>👥 Quem Somos</h1>', unsafe_allow_html=True)
    st.write("Especialistas em e-commerce e curadoria de produtos de alta qualidade.")

elif st.session_state.pg == "Serviços":
    st.markdown('<h1>🛠️ Nossos Serviços</h1>', unsafe_allow_html=True)
    st.write("Vendas e logística eficiente em marketplaces globais.")

elif st.session_state.pg == "Contato":
    st.markdown('<h1>✉️ Central de Atendimento</h1>', unsafe_allow_html=True)
    whatsapp_url = "https://wa.me/5511960501826"
    st.markdown(f'<a href="{whatsapp_url}" target="_blank" style="text-decoration: none;"><div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 16px; border-radius: 12px; display: inline-block; font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);">💬 Falar no WhatsApp: (11) 96050-1826</div></a>', unsafe_allow_html=True)
    st.divider()
    with st.form("form_contato"):
        nome = st.text_input("Nome")
        prod = st.text_input("Produto")
        tipo = st.selectbox("Assunto", ["Dúvida", "Elogio", "Reclamação"])
        msg = st.text_area("Mensagem")
        if st.form_submit_button("Gerar E-mail"):
            if nome and msg:
                mailto = f"mailto:vendas.dlonlinestore@gmail.com?subject={tipo}&body={msg}"
                st.markdown(f'<a href="{mailto}" style="background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; padding: 12px 20px; border-radius: 8px; text-decoration: none; font-weight: 600; display: inline-block; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);">📧 Abrir E-mail</a>', unsafe_allow_html=True)

# --- PÁGINA PENDÊNCIAS ---
# --- PÁGINA CALCULADORA ---
elif st.session_state.pg == "Calculadora":
    st.markdown('<h1>📊 Comparativo de Preços</h1>', unsafe_allow_html=True)
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)
    
    if not df_base_completa.empty:
        df_geral = df_base_completa.copy()
        df_geral['Custo_aquisicao_num'] = df_geral['Custo_aquisicao'].apply(converter_custo_seguro)
        
        col_sel1, col_sel2 = st.columns(2)
        
        with col_sel1:
            opcoes_produtos = sorted([str(p) for p in df_geral['Produto'].unique()])
            prod_sel = st.selectbox("Pesquisar Produto", opcoes_produtos, index=None, placeholder="Digite o produto...", label_visibility="collapsed")
            
        with col_sel2:
            opcoes_skus = sorted([str(s) for s in df_geral['SKU'].unique()])
            v_sku_sel = st.selectbox("Pesquisar por SKU", opcoes_skus, index=None, placeholder="Busque o SKU...", label_visibility="collapsed")

        final_item = None
        if v_sku_sel: 
            final_item = df_geral[df_geral['SKU'] == v_sku_sel].iloc[0]
        elif prod_sel: 
            final_item = df_geral[df_geral['Produto'] == prod_sel].iloc[0]

        if final_item is not None:
            cust_aq = final_item['Custo_aquisicao_num']
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #dbeafe 0%, #e0f2fe 100%); border: 1px solid #7dd3fc; border-radius: 12px; padding: 16px; margin-bottom: 20px;">
            <p style="margin: 0; color: #0369a1;"><strong>✓ Selecionado:</strong> {final_item['Produto']} <code style="background: white; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">{final_item['SKU']}</code></p>
            </div>
            """, unsafe_allow_html=True)
            
            margem_input = st.number_input("Margem de Lucro Desejada (%)", min_value=1.0, value=15.0, step=1.0)
            
            p_shein, l_shein = calcular_venda_completo(cust_aq, margem_input, "shein")
            p_shopee, l_shopee = calcular_venda_completo(cust_aq, margem_input, "shopee")
            p_temu, l_temu = calcular_venda_completo(cust_aq, margem_input, "temu")
            p_tiktok, l_tiktok = calcular_venda_completo(cust_aq, margem_input, "tiktok")
            
            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
            
            col1, col2 = st.columns([1, 3])
            with col1:
                st.metric("💰 Custo Base", f"R$ {cust_aq:.2f}")
            
            res = {
                "Canal": ["SHEIN", "SHOPEE", "TEMU", "TIKTOK"], 
                "Preço Sugerido": [f"R$ {p_shein:.2f}", f"R$ {p_shopee:.2f}", f"R$ {p_temu:.2f}", f"R$ {p_tiktok:.2f}"], 
                "Lucro Líquido": [f"R$ {l_shein:.2f}", f"R$ {l_shopee:.2f}", f"R$ {l_temu:.2f}", f"R$ {l_tiktok:.2f}"]
            }
            
            df_resultado = pd.DataFrame(res)
            st.dataframe(df_resultado, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum produto cadastrado ainda.")

# --- PÁGINA ANÁLISE DE VENDAS ---
# --- PÁGINA CADASTRO ---
elif st.session_state.pg == "Cadastro":
    st.markdown('<h1>📝 Novo Item na Base</h1>', unsafe_allow_html=True)
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)
    
    if 'cont_var' not in st.session_state:
        st.session_state.cont_var = 0

    col_btn1, col_btn2, _ = st.columns([0.8, 0.8, 4])
    
    with col_btn1:
        if st.button("➕ Variante", type="secondary"):
            st.session_state.cont_var += 1
            st.rerun()
            
    with col_btn2:
        if st.button("🗑️ Limpar", type="secondary"):
            st.session_state.cont_var = 0
            st.rerun()

    m = st.selectbox("Marketplace", ["shein", "shopee", "temu", "tiktok", "todos"])
    n = st.text_input("Nome Base do Produto")
    s_base = st.text_input("SKU Base")
    c_padrao = st.number_input("Custo Unitário Base (R$)", min_value=0.01, step=0.01, value=0.01)
    
    lista_variantes = []
    
    if st.session_state.cont_var > 0:
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        for i in range(st.session_state.cont_var):
            c1, c2, c3 = st.columns([2, 2, 1])
            
            with c1:
                v_sku = st.text_input(f"SKU da Variante {i+1}", key=f"vsku_{i}")
            with c2:
                v_char = st.text_input(f"Cor/Tipo {i+1}", key=f"vchar_{i}")
            with c3:
                v_custo = st.number_input(
                    f"Custo {i+1}", 
                    min_value=0.01, 
                    step=0.01, 
                    value=c_padrao, 
                    key=f"vcost_{i}_{c_padrao}" 
                )
            
            if v_sku:
                lista_variantes.append({
                    "nome_completo": f"{n} {v_char}" if v_char else n, 
                    "sku_variante": v_sku.strip().upper(),
                    "custo_variante": v_custo
                })

    sku_bloqueado = False
    todos_skus_digitados = []
    
    if s_base:
        todos_skus_digitados.append(s_base.strip().upper())
    for v in lista_variantes:
        todos_skus_digitados.append(v['sku_variante'])

    if todos_skus_digitados:
        try:
            format_skus = ", ".join([f"'{s}'" for s in todos_skus_digitados])
            q_verificacao = f"SELECT SKU FROM `leandro-marketplace.DL_Store_Online.tb_produtos` WHERE SKU IN ({format_skus})"
            verificacao_df = client_bq.query(q_verificacao).to_dataframe()
            
            if not verificacao_df.empty:
                skus_conflito = verificacao_df['SKU'].unique().tolist()
                st.error(f"❌ ERRO: O(s) SKU(s) {skus_conflito} JÁ EXISTE(M) NO BIGQUERY!")
                sku_bloqueado = True
            else:
                st.success("✅ Todos os SKUs informados estão disponíveis.")
                sku_bloqueado = False
        except Exception as e:
            st.caption("Validando SKUs no banco de dados...")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    if st.button("🚀 Salvar Tudo no BigQuery", type="primary", use_container_width=True):
        if sku_bloqueado:
            st.error("🚨 Gravação interrompida! Existem SKUs duplicados.")
        elif not n or not s_base:
            st.error("⚠️ Preencha o Nome e o SKU Base.")
        else:
            try:
                table_id_produtos = "leandro-marketplace.DL_Store_Online.tb_produtos"
                mkt_list = ["shein", "shopee", "temu", "tiktok"] if m == "todos" else [m]
                
                lote_bq = []
                for aba in mkt_list:
                    lote_bq.append({
                        "marketplace": aba, 
                        "sku": str(s_base).strip().upper(),
                        "produto": str(n), 
                        "custo_aquisicao": float(c_padrao)
                    })
                    for var in lista_variantes:
                        lote_bq.append({
                            "marketplace": aba,
                            "sku": str(var['sku_variante']),
                            "produto": str(var['nome_completo']),
                            "custo_aquisicao": float(var['custo_variante'])
                        })
                
                # load_table_from_dataframe (carga em lote) em vez de insert_rows_json (streaming):
                # linhas gravadas via streaming ficam presas no "streaming buffer" por um tempo,
                # bloqueando UPDATE/DELETE (ex: na aba Alterar Preços) até o buffer esvaziar.
                df_lote = pd.DataFrame(lote_bq)
                client_bq.load_table_from_dataframe(df_lote, table_id_produtos).result()

                st.success(f"✅ Sucesso! {len(lote_bq)} registros salvos.")
                st.session_state.cont_var = 0
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Falha técnica: {e}")

# --- PÁGINA ALTERAR PREÇO ---
elif st.session_state.pg == "Alterar Preco":
    st.markdown('<h1>💰 Atualização de Preços em Lote</h1>', unsafe_allow_html=True)
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)

    if 'lista_updates' not in st.session_state:
        st.session_state.lista_updates = []

    @st.cache_data(ttl=600)
    def listar_skus_disponiveis():
        query = "SELECT DISTINCT sku, produto, custo_aquisicao FROM `leandro-marketplace.DL_Store_Online.tb_produtos` ORDER BY produto"
        return client_bq.query(query).to_dataframe()

    df_produtos = listar_skus_disponiveis()

    # st.container em vez de st.expander (sempre expanded=True aqui, e o expander
    # nativo depende de uma fonte de ícone externa pra desenhar a seta — quando
    # não carrega, sobrepõe o texto do título com o nome cru do ícone).
    with st.container(border=True):
        st.markdown("**➕ Adicionar Item para Alteração**")
        opcoes = df_produtos.apply(lambda x: f"{x['sku']} - {x['produto']}", axis=1).tolist()
        
        selecao_item = st.selectbox(
            "Busque o SKU ou Nome do Produto", 
            options=opcoes, 
            index=None, 
            placeholder="Digite para buscar...",
            key="sel_bulk"
        )
        
        if selecao_item:
            sku_ref = selecao_item.split(" - ")[0]
            dados_ref = df_produtos[df_produtos['sku'] == sku_ref].iloc[0]
            
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Custo Atual", f"R$ {float(dados_ref['custo_aquisicao']):.2f}")
            with c2:
                novo_custo_bulk = st.number_input(
                    "Novo Valor (R$)", 
                    min_value=0.01, 
                    step=0.01, 
                    value=float(dados_ref['custo_aquisicao']),
                    key="num_bulk"
                )

            if st.button("Adicionar à Fila", type="secondary"):
                st.session_state.lista_updates.append({
                    "sku": sku_ref,
                    "produto": dados_ref['produto'],
                    "novo_valor": novo_custo_bulk
                })
                st.rerun()
        else:
            st.info("Pesquise um produto acima para ajustar o valor.")

    if st.session_state.lista_updates:
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        st.markdown('<h3>📋 Itens na Fila de Processamento</h3>', unsafe_allow_html=True)
        
        for i, item in enumerate(st.session_state.lista_updates):
            col_info, col_del = st.columns([4, 1])
            with col_info:
                st.markdown(f"""
                <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; border-radius: 8px;">
                <p style="margin: 0; font-size: 14px;"><strong>{item['produto']}</strong></p>
                <p style="margin: 4px 0 0 0; font-size: 13px; color: #92400e;"><code>{item['sku']}</code> → <strong>R$ {item['novo_valor']:.2f}</strong></p>
                </div>
                """, unsafe_allow_html=True)
            if col_del.button("🗑️", key=f"del_{i}"):
                st.session_state.lista_updates.pop(i)
                st.rerun()

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("🚀 Enviar Pacote ao BigQuery", type="primary", use_container_width=True):
                try:
                    queries = []
                    for item in st.session_state.lista_updates:
                        q = f"UPDATE `leandro-marketplace.DL_Store_Online.tb_produtos` SET custo_aquisicao = {float(item['novo_valor'])} WHERE sku = '{item['sku']}';"
                        queries.append(q)
                    
                    full_query = "\n".join(queries)
                    job = client_bq.query(full_query)
                    job.result()

                    st.success(f"✅ Sucesso! {len(st.session_state.lista_updates)} itens atualizados.")
                    st.session_state.lista_updates = []
                    st.cache_data.clear()
                    st.balloons()
                except Exception as e:
                    st.error(f"Erro no processamento em lote: {e}")
        
        with col_btn2:
            if st.button("❌ Limpar Fila", use_container_width=True):
                st.session_state.lista_updates = []
                st.rerun()

# --- DASHBOARD FINANCEIRO ---
elif st.session_state.pg == "Dashboard":
    if 'fin_acesso' not in st.session_state:
        st.session_state.fin_acesso = False

    if not st.session_state.fin_acesso:
        st.markdown('<h1>🔐 Acesso Restrito</h1>', unsafe_allow_html=True)
        st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)
        col_senha, _ = st.columns([1, 2])
        with col_senha:
            senha_financeira = st.text_input("Digite a senha do Dashboard", type="password", placeholder="Senha")
            if st.button("Acessar Dados Sensíveis", type="primary", use_container_width=True):
                if senha_financeira == "D@niliz2026": 
                    st.session_state.fin_acesso = True
                    st.rerun()
                else:
                    st.error("Senha incorreta!")
        st.stop()
    
    from datetime import timedelta
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    col_titulo, col_atualizar = st.columns([4, 1])
    with col_titulo:
        st.markdown('<h1>📊 Dashboard Financeiro</h1>', unsafe_allow_html=True)
    with col_atualizar:
        st.markdown("<div style='padding-top:28px'></div>", unsafe_allow_html=True)
        if st.button("🔄 Atualizar", type="primary", use_container_width=True):
            st.session_state["dash_atualizar_aberto"] = True
            # Dispara a busca sozinha assim que o login estiver pronto — sem
            # precisar de um segundo clique num botão separado (era a mesma
            # coisa na prática, só um passo a mais). Se o login exigir CAPTCHA/
            # código manual, fica pendente até o rerun em que ups_logado virar True.
            st.session_state["dash_atualizar_executar"] = True
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)

    if st.session_state.get("dash_atualizar_aberto"):
        with st.container(border=True):
            st.markdown("#### 🔄 Atualizar Dashboard via Upseller")
            st.caption(
                "Faz login no Upseller (se precisar) e exporta automaticamente todos os pedidos "
                "de 'Pedidos > Enviado', registrando as vendas novas — pedidos já importados antes "
                "são ignorados (nunca duplica)."
            )
            from modulo_upseller import widget_login_upseller, exportar_pedidos_shipped_upseller
            widget_login_upseller(client_bq)

            # Mostra o resultado da ÚLTIMA tentativa de forma persistente — antes a
            # mensagem sumia na hora por causa do st.rerun() logo em seguida, dando
            # a impressão de que nada tinha acontecido (ou deixando sem saber o
            # resultado real, como aconteceu aqui).
            resultado_ant = st.session_state.get("dash_import_resultado")
            if resultado_ant:
                if resultado_ant.get("ok") is False:
                    st.error(resultado_ant["msg"])
                else:
                    if resultado_ant.get("inseridas"):
                        st.success(f"✅ {resultado_ant['inseridas']} venda(s) nova(s) registrada(s).")
                    if resultado_ant.get("duplicadas"):
                        st.info(f"↩️ {resultado_ant['duplicadas']} pedido(s) já estavam registrados (ignorados).")
                    if resultado_ant.get("erros"):
                        st.warning(f"⚠️ {resultado_ant['erros']} linha(s) com problema:")
                        for m in resultado_ant.get("msgs_erro", [])[:10]:
                            st.caption(f"- {m}")

            # Upload manual do Excel — mais simples e sem risco pra importar
            # histórico mais antigo: você exporta na mão no site (escolher datas
            # antigas é fácil pra pessoa, arriscado pro robô navegar o calendário
            # sozinho) e só sobe o arquivo aqui. Usa a mesma função de importação
            # de sempre, não precisa estar logado nem abrir o Chrome.
            with st.expander("📤 Já tenho o Excel exportado (upload manual)"):
                st.caption(
                    "Exportou o Excel direto no site do Upseller (Pedidos > Enviado)? Sobe o "
                    "arquivo aqui — funciona pra qualquer período, inclusive histórico antigo, "
                    "sem precisar automatizar o calendário. Pedidos já importados são ignorados."
                )
                arquivo_excel_manual = st.file_uploader(
                    "Arquivo Excel do Upseller", type=["xlsx", "xls"], key="upload_excel_manual"
                )
                if arquivo_excel_manual is not None:
                    if st.button("📥 Importar deste arquivo", key="btn_importar_excel_manual"):
                        import tempfile
                        caminho_tmp = os.path.join(
                            tempfile.gettempdir(), f"upseller_manual_{arquivo_excel_manual.name}"
                        )
                        with open(caminho_tmp, "wb") as f_tmp:
                            f_tmp.write(arquivo_excel_manual.getbuffer())
                        with st.spinner("Processando planilha e registrando vendas novas..."):
                            inseridas, duplicadas, erros, msgs_erro = importar_pedidos_upseller_para_dashboard(client_bq, caminho_tmp)
                        st.session_state["dash_import_resultado"] = {
                            "ok": True, "inseridas": inseridas, "duplicadas": duplicadas,
                            "erros": erros, "msgs_erro": msgs_erro,
                        }
                        try:
                            os.remove(caminho_tmp)
                        except Exception:
                            pass
                        st.cache_data.clear()
                        st.rerun()

            # Clicar em "Atualizar" já basta — se o login não estiver pronto
            # ainda (esperando CAPTCHA/código manual no widget acima), fica
            # pendente e roda sozinho assim que ups_logado virar True num
            # rerun seguinte. Substitui os antigos botões "Buscar Pedidos
            # Enviados do Upseller" e "Importar histórico mais antigo", que
            # eram passos redundantes pro mesmo resultado.
            if st.session_state.get("dash_atualizar_executar") and st.session_state.get("ups_logado"):
                st.session_state["dash_atualizar_executar"] = False
                import tempfile
                pasta_download = os.path.join(tempfile.gettempdir(), "upseller_exports")
                driver = st.session_state.get("ups_driver")
                with st.spinner("Exportando pedidos do Upseller (pode levar um tempinho com muitas páginas)..."):
                    ok_exp, resultado = exportar_pedidos_shipped_upseller(driver, pasta_download)
                if not ok_exp:
                    st.session_state["dash_import_resultado"] = {"ok": False, "msg": resultado}
                else:
                    with st.spinner("Processando planilha e registrando vendas novas..."):
                        inseridas, duplicadas, erros, msgs_erro = importar_pedidos_upseller_para_dashboard(client_bq, resultado)
                    st.session_state["dash_import_resultado"] = {
                        "ok": True, "inseridas": inseridas, "duplicadas": duplicadas,
                        "erros": erros, "msgs_erro": msgs_erro,
                    }
                    try:
                        os.remove(resultado)
                    except Exception:
                        pass
                    st.cache_data.clear()
                st.rerun()

    try:
        # Vendas "pendente = TRUE" (SKU sem custo cadastrado, lucro calculado com
        # custo 0) ficam de fora do Dashboard até serem resolvidas na aba Validar
        # Vendas — registro antigo sem essa coluna preenchida (NULL) conta como
        # não-pendente, pra não sumir histórico de antes dessa flag existir.
        query = ("SELECT produto, sku, preco_venda, quantidade, data, lucro_total, mkt_venda "
                  "FROM `leandro-marketplace.DL_Store_Online.tb_vendas_realizadas` "
                  "WHERE pendente IS NULL OR pendente = FALSE "
                  "ORDER BY data DESC")
        df_vendas = client_bq.query(query).to_dataframe()

        if not df_vendas.empty:
            df_vendas.columns = ['Produto', 'SKU', 'Preço Venda', 'Quantidade', 'Data', 'Lucro Total', 'Marketplace']
            df_vendas['Preço Venda'] = pd.to_numeric(df_vendas['Preço Venda'])
            df_vendas['Lucro Total'] = pd.to_numeric(df_vendas['Lucro Total'])
            df_vendas['Quantidade'] = pd.to_numeric(df_vendas['Quantidade'])
            # 'Preço Venda' já é o Valor do Pedido inteiro (não um preço unitário),
            # então o faturamento é o próprio valor — não multiplicar pela Quantidade
            # (senão infla o faturamento, e por tabela o Custo, em pedidos com mais
            # de 1 unidade do mesmo produto).
            df_vendas['Faturamento'] = df_vendas['Preço Venda']
            df_vendas['Custo'] = df_vendas['Faturamento'] - df_vendas['Lucro Total']
            df_vendas['Data'] = pd.to_datetime(df_vendas['Data'])
            df_vendas['Mes_Ref'] = df_vendas['Data'].dt.strftime('%Y-%m')

            meses_map = {1:'Jan', 2:'Fev', 3:'Mar', 4:'Abr', 5:'Mai', 6:'Jun', 7:'Jul', 8:'Ago', 9:'Set', 10:'Out', 11:'Nov', 12:'Dez'}

            hoje = datetime.utcnow() - timedelta(hours=3)
            mes_atual_ref = hoje.strftime('%Y-%m')
            df_mes_atual = df_vendas[df_vendas['Mes_Ref'] == mes_atual_ref]

            fat_mes = df_mes_atual['Faturamento'].sum()
            lucro_mes = df_mes_atual['Lucro Total'].sum()
            custo_mes = fat_mes - lucro_mes
            pct_lucro_mes = (lucro_mes / fat_mes * 100) if fat_mes else 0

            # ---------- LINHA 1: cards com seta (Faturamento → Custo → Lucro → %) ----------
            st.markdown("""
                <style>
                .arrow-row { display:flex; align-items:stretch; gap:0; margin-bottom:18px;
                             border:1px solid rgba(120,113,90,0.2); border-radius:12px; overflow:hidden; }
                .arrow-card { flex:1; padding:14px 18px; }
                .arrow-card .lbl { font-size:11px; color:#9ca3af; text-transform:uppercase; letter-spacing:.04em; margin-bottom:4px; }
                .arrow-card .val { font-size:21px; font-weight:700; }
                .arrow-sep { display:flex; align-items:center; justify-content:center; width:42px;
                             color:#9ca3af; font-size:17px; background:rgba(120,113,90,0.05); }
                </style>
            """, unsafe_allow_html=True)
            st.markdown(f"""
                <div class="arrow-row">
                  <div class="arrow-card"><div class="lbl">Faturamento (mês)</div><div class="val">R$ {fat_mes:,.2f}</div></div>
                  <div class="arrow-sep">→</div>
                  <div class="arrow-card"><div class="lbl">Custo</div><div class="val" style="color:#2a78d6">R$ {custo_mes:,.2f}</div></div>
                  <div class="arrow-sep">→</div>
                  <div class="arrow-card"><div class="lbl">Lucro Líquido</div><div class="val" style="color:#c98500">R$ {lucro_mes:,.2f}</div></div>
                  <div class="arrow-sep">=</div>
                  <div class="arrow-card"><div class="lbl">% Lucro</div><div class="val" style="color:#c98500">{pct_lucro_mes:.1f}%</div></div>
                </div>
            """, unsafe_allow_html=True)

            # ---------- Meta mensal (editável, guardada no BigQuery) ----------
            def _ler_meta_mensal():
                try:
                    dfm = client_bq.query(
                        "SELECT valor FROM `leandro-marketplace.DL_Store_Online.tb_config_dashboard` "
                        "WHERE chave = 'meta_mensal'"
                    ).to_dataframe()
                    if not dfm.empty:
                        return float(dfm['valor'].iloc[0])
                except Exception:
                    pass
                return 0.0

            def _salvar_meta_mensal(valor):
                try:
                    client_bq.query(
                        "DELETE FROM `leandro-marketplace.DL_Store_Online.tb_config_dashboard` "
                        "WHERE chave = 'meta_mensal'"
                    ).result()
                except Exception:
                    pass
                df_meta = pd.DataFrame([{"chave": "meta_mensal", "valor": float(valor)}])
                client_bq.load_table_from_dataframe(
                    df_meta, "leandro-marketplace.DL_Store_Online.tb_config_dashboard"
                ).result()

            meta_mensal = _ler_meta_mensal()

            col_meta, col_chart = st.columns([1, 3])
            with col_meta:
                st.markdown("**🎯 Meta do Mês**")
                if meta_mensal > 0:
                    pct_meta = min(100, fat_mes / meta_mensal * 100)
                    fig_meta = go.Figure(go.Pie(
                        values=[pct_meta, max(0, 100 - pct_meta)],
                        hole=0.75, sort=False, direction='clockwise',
                        marker=dict(colors=['#FBBF24', '#F3F1EA']),
                        textinfo='none', hoverinfo='skip',
                    ))
                    fig_meta.update_layout(
                        showlegend=False, margin=dict(l=0, r=0, t=0, b=0), height=150,
                        paper_bgcolor='rgba(0,0,0,0)',
                        annotations=[dict(text=f"{pct_meta:.0f}%", x=0.5, y=0.5, font_size=22, showarrow=False)]
                    )
                    st.plotly_chart(fig_meta, use_container_width=True, config={'displayModeBar': False})
                    st.caption(f"R$ {fat_mes:,.2f} de R$ {meta_mensal:,.2f}")
                else:
                    st.info("Meta não definida ainda.")

                if "dash_editar_meta" not in st.session_state:
                    st.session_state["dash_editar_meta"] = False
                if st.button("✏️ Editar meta", key="btn_editar_meta", use_container_width=True):
                    st.session_state["dash_editar_meta"] = not st.session_state["dash_editar_meta"]
                if st.session_state["dash_editar_meta"]:
                    nova_meta = st.number_input(
                        "Meta mensal (R$)", min_value=0.0, step=100.0,
                        value=float(meta_mensal), key="input_nova_meta"
                    )
                    if st.button("💾 Salvar meta", key="btn_salvar_meta", use_container_width=True):
                        _salvar_meta_mensal(nova_meta)
                        st.session_state["dash_editar_meta"] = False
                        st.rerun()

            with col_chart:
                st.markdown("**📈 Receita Operacional**")
                if "dash_visao" not in st.session_state:
                    st.session_state["dash_visao"] = "Mensal"
                cb1, cb2, _sp = st.columns([1, 1, 4])
                with cb1:
                    if st.button("Mensal", key="btn_visao_mensal", use_container_width=True,
                                 type="primary" if st.session_state["dash_visao"] == "Mensal" else "secondary"):
                        st.session_state["dash_visao"] = "Mensal"
                        st.rerun()
                with cb2:
                    if st.button("Diário", key="btn_visao_diario", use_container_width=True,
                                 type="primary" if st.session_state["dash_visao"] == "Diário" else "secondary"):
                        st.session_state["dash_visao"] = "Diário"
                        st.rerun()

                if st.session_state["dash_visao"] == "Mensal":
                    # Só os meses — poucos, cabe tudo com folga (sem misturar dia
                    # nenhum aqui, diferente do gráfico antigo).
                    df_plot = df_vendas.groupby('Mes_Ref').agg(
                        {'Faturamento': 'sum', 'Lucro Total': 'sum', 'Custo': 'sum', 'Quantidade': 'sum'}
                    ).reset_index().sort_values('Mes_Ref')
                    df_plot['Data_Label'] = df_plot['Mes_Ref'].apply(
                        lambda m: meses_map[int(m.split('-')[1])] + '/' + m.split('-')[0][-2:]
                    )
                else:
                    # Isola um mês por vez — só os dias dele, sem misturar mês fechado.
                    # Botões em vez de selectbox — mesmo visual de aba usado no resto do app.
                    opcoes_meses = sorted(df_vendas['Mes_Ref'].unique(), reverse=True)
                    if "dash_mes_diario" not in st.session_state or st.session_state["dash_mes_diario"] not in opcoes_meses:
                        st.session_state["dash_mes_diario"] = opcoes_meses[0]
                    cols_meses = st.columns(len(opcoes_meses))
                    for col_m, m in zip(cols_meses, opcoes_meses):
                        with col_m:
                            label_m = meses_map[int(m.split('-')[1])] + '/' + m.split('-')[0][-2:]
                            if st.button(label_m, key=f"btn_mes_{m}", use_container_width=True,
                                         type="primary" if st.session_state["dash_mes_diario"] == m else "secondary"):
                                st.session_state["dash_mes_diario"] = m
                                st.rerun()
                    mes_detalhe = st.session_state["dash_mes_diario"]
                    df_dia = df_vendas[df_vendas['Mes_Ref'] == mes_detalhe]
                    df_plot = df_dia.groupby('Data').agg(
                        {'Faturamento': 'sum', 'Lucro Total': 'sum', 'Custo': 'sum', 'Quantidade': 'sum'}
                    ).reset_index().sort_values('Data')
                    df_plot['Data_Label'] = df_plot['Data'].dt.strftime('%d/%m')

                fig = make_subplots(specs=[[{"secondary_y": True}]])
                fig.add_trace(go.Bar(
                    x=df_plot['Data_Label'], y=df_plot['Custo'], name='Custo',
                    marker_color='#FEF3C7', hovertemplate='R$ %{y:,.2f}<extra></extra>'
                ), secondary_y=False)
                fig.add_trace(go.Bar(
                    x=df_plot['Data_Label'], y=df_plot['Lucro Total'], name='Lucro Líquido',
                    marker_color='#FBBF24', hovertemplate='R$ %{y:,.2f}<extra></extra>',
                    text=df_plot['Lucro Total'].apply(lambda x: f'R$ {x:,.2f}'),
                    textposition='outside', textfont=dict(size=12, color='#92400E', family="Arial")
                ), secondary_y=False)
                # Qtd Vendas na escala PRÓPRIA (secondary_y independente, não a mesma
                # do R$) — é o que fazia a linha flutuar acima das barras antes, em
                # vez de ficar "colada" em cima (Faturamento é sempre = topo da
                # barra empilhada, então uma linha de Faturamento sempre encosta nela).
                fig.add_trace(go.Scatter(
                    x=df_plot['Data_Label'], y=df_plot['Quantidade'], name='Qtd Vendas',
                    mode='lines+markers+text',
                    line=dict(color='#6366F1', width=3), marker=dict(size=8, color='#6366F1'),
                    text=df_plot['Quantidade'], textposition="top center",
                    textfont=dict(size=11, color='#6366F1', family="Arial"),
                    hovertemplate='Vendas: %{y}<extra></extra>'
                ), secondary_y=True)

                fig.update_layout(
                    barmode='stack',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=True,
                               range=[0, df_plot['Faturamento'].max() * 2.2]),
                    yaxis2=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=True,
                                range=[df_plot['Quantidade'].max() * -1.5, df_plot['Quantidade'].max() * 1.2]),
                    xaxis=dict(title="Competência / Dias", showgrid=False, showline=True, linecolor='#E5E7EB',
                               tickfont=dict(color='#6B7280', size=12)),
                    legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5, font=dict(color="#374151", size=13)),
                    margin=dict(l=10, r=10, t=80, b=60),
                    hovermode='x unified',
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
            st.markdown('<h3>📊 Totais Acumulados</h3>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento Total", f"R$ {df_vendas['Faturamento'].sum():,.2f}")
            c2.metric("Lucro Líquido Geral", f"R$ {df_vendas['Lucro Total'].sum():,.2f}")
            c3.metric("Total Itens Vendidos", int(df_vendas['Quantidade'].sum()))

            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
            st.markdown('<h3>💎 Lucro Líquido por Plataforma</h3>', unsafe_allow_html=True)

            df_pizza = df_vendas.groupby('Marketplace')['Lucro Total'].sum().reset_index()
            cores_map = {'shein': '#FFD700', 'shopee': '#EE4D2D', 'temu': '#FF8C00', 'tiktok': '#000000'}
            cores_lista = [cores_map.get(m, '#6B7280') for m in df_pizza['Marketplace']]

            fig_pizza = go.Figure(data=[go.Pie(
                labels=df_pizza['Marketplace'].str.upper(),
                values=df_pizza['Lucro Total'],
                hole=.4,
                marker=dict(colors=cores_lista),
                textinfo='label+value+percent',
                texttemplate='<b>%{label}</b><br>R$ %{value:,.2f}<br>(%{percent:.1%})',
                hovertemplate='R$ %{value:,.2f}<extra></extra>'
            )])

            fig_pizza.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=20, r=20, t=30, b=20),
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.1,
                    xanchor="center",
                    x=0.5,
                    font=dict(color="#374151", size=12)
                )
            )

            st.plotly_chart(fig_pizza, use_container_width=True, config={'displayModeBar': False})

        else:
            st.info("Nenhuma venda registrada ainda.")
    except Exception as e:
        st.error(f"Erro no Dashboard: {e}")

# --- PÁGINA VALIDAR VENDAS ---
elif st.session_state.pg == "Validar Vendas":
    st.markdown('<h1>🔎 Validação de Vendas</h1>', unsafe_allow_html=True)
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)
    st.caption(
        "Corrige os dois problemas que deixam o lucro do Dashboard Financeiro errado: "
        "SKU vendido sem cadastro na base (custo vira R$0) e SKU cadastrado com custo "
        "divergente entre marketplaces. Ao salvar, o lucro das vendas já importadas "
        "desse SKU é recalculado automaticamente."
    )
    st.caption(
        "SKU de variante (ex: CP-784-AM) sem custo próprio cadastrado usa o custo do "
        "SKU principal (CP-784) automaticamente — não precisa cadastrar cada cor. "
        "O botão abaixo aplica isso no histórico de vendas já importado."
    )

    try:
        n_pendentes = client_bq.query(
            "SELECT COUNT(*) AS n FROM `leandro-marketplace.DL_Store_Online.tb_vendas_realizadas` WHERE pendente = TRUE"
        ).to_dataframe()["n"][0]
    except Exception:
        n_pendentes = None

    if n_pendentes:
        st.warning(
            f"⏸️ {int(n_pendentes)} venda(s) fora do Dashboard Financeiro por enquanto — SKU sem custo "
            f"cadastrado. Assim que você resolver o SKU abaixo, elas entram automaticamente."
        )
    elif n_pendentes == 0:
        st.success("Nenhuma venda represada esperando cadastro. Tudo que está registrado já entra no Dashboard.")

    if st.button("🔁 Aplicar custo do SKU principal nas vendas já importadas"):
        try:
            n_corrigidas = aplicar_fallback_sku_base(client_bq)
            st.session_state["validacao_resultado"] = {
                "ok": True,
                "msg": f"{n_corrigidas} venda(s) recalculada(s) usando o custo do SKU principal." if n_corrigidas
                       else "Nenhuma venda pendente pra esse tipo de correção.",
            }
            st.cache_data.clear()
        except Exception as e:
            st.session_state["validacao_resultado"] = {"ok": False, "msg": f"Erro ao aplicar fallback: {e}"}
        st.rerun()

    resultado_validacao = st.session_state.get("validacao_resultado")
    if resultado_validacao:
        if resultado_validacao["ok"]:
            st.success(resultado_validacao["msg"])
        else:
            st.error(resultado_validacao["msg"])
        st.session_state["validacao_resultado"] = None

    try:
        df_sem_cadastro, df_divergentes = buscar_pendencias_validacao(client_bq)
    except Exception as e:
        st.error(f"Erro ao buscar pendências: {e}")
        df_sem_cadastro, df_divergentes = pd.DataFrame(), pd.DataFrame()

    st.markdown(f'<h3>🚨 SKUs vendidos sem cadastro ({len(df_sem_cadastro)})</h3>', unsafe_allow_html=True)
    if df_sem_cadastro.empty:
        st.success("Nenhum SKU pendente. 🎉")
    else:
        for _, row in df_sem_cadastro.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.4, 2.6, 1.3, 1])
                with c1:
                    st.text_input("SKU", value=row["sku"], disabled=True, key=f"sc_sku_{row['sku']}")
                with c2:
                    nome_input = st.text_input("Produto", value=row["produto"] or "", key=f"sc_nome_{row['sku']}")
                with c3:
                    custo_input = st.number_input(
                        "Custo de aquisição (R$)", min_value=0.0, step=0.01, value=0.0, key=f"sc_custo_{row['sku']}"
                    )
                with c4:
                    d_min, d_max = row["data_min"], row["data_max"]
                    periodo = d_min.strftime("%d/%m") if d_min == d_max else f"{d_min.strftime('%d/%m')} a {d_max.strftime('%d/%m')}"
                    st.caption(f"📅 {periodo}")
                    st.caption(f"{int(row['vendas'])} venda(s)")
                    st.caption(f"R$ {row['faturamento']:,.2f}")
                    if st.button("💾 Salvar", key=f"sc_salvar_{row['sku']}", use_container_width=True):
                        if not nome_input.strip() or custo_input <= 0:
                            st.session_state["validacao_resultado"] = {
                                "ok": False, "msg": f"Preencha o nome e um custo maior que 0 pro SKU {row['sku']}."
                            }
                        else:
                            try:
                                n_venda = resolver_sku_sem_cadastro(client_bq, row["sku"], nome_input.strip(), custo_input)
                                st.session_state["validacao_resultado"] = {
                                    "ok": True,
                                    "msg": f"SKU {row['sku']} cadastrado. {n_venda} venda(s) recalculada(s).",
                                }
                                st.cache_data.clear()
                            except Exception as e:
                                st.session_state["validacao_resultado"] = {"ok": False, "msg": f"Erro ao salvar {row['sku']}: {e}"}
                        st.rerun()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    n_divergentes_com_venda = int((df_divergentes["vendas"] > 0).sum()) if not df_divergentes.empty else 0
    total_skus_variantes = int(df_divergentes["skus"].apply(len).sum()) if not df_divergentes.empty else 0
    st.markdown(
        f'<h3>⚠️ Produtos com custo divergente ({len(df_divergentes)} — {total_skus_variantes} SKU(s) no total) '
        f'— {n_divergentes_com_venda} com venda registrada</h3>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Variantes do mesmo produto (cores/tamanhos, ex: CP-209-AZ e CP-209-RS) são agrupadas — "
        "corrigir aplica o mesmo custo pra todas de uma vez, já que cor/tamanho não muda o que se paga pelo produto. "
        "Ordenado com os que já têm venda primeiro."
    )
    if df_divergentes.empty:
        st.success("Nenhuma divergência encontrada. 🎉")
    else:
        so_com_venda = st.checkbox("Mostrar só os que têm venda registrada", value=(n_divergentes_com_venda > 0))
        df_div_exibir = df_divergentes[df_divergentes["vendas"] > 0] if so_com_venda else df_divergentes
        for _, row in df_div_exibir.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.4, 2.6, 1.8, 1])
                with c1:
                    st.text_input(
                        "SKU principal", value=row["sku_base"], disabled=True, key=f"dv_sku_{row['sku_base']}"
                    )
                    if len(row["skus"]) > 1:
                        st.caption("Variantes: " + ", ".join(row["skus"]))
                with c2:
                    valores_fmt = " / ".join(f"R$ {float(v):,.2f}" for v in row["valores"])
                    st.caption(row["produto"] or "")
                    st.caption(f"Cadastrado hoje: {valores_fmt}")
                    if row["vendas"] > 0:
                        st.caption(f"🛒 {int(row['vendas'])} venda(s) registrada(s)")
                    else:
                        st.caption("Sem venda registrada ainda")
                with c3:
                    custo_correto = st.number_input(
                        "Custo correto (R$)", min_value=0.0, step=0.01,
                        value=float(row["valores"][0]), key=f"dv_custo_{row['sku_base']}"
                    )
                with c4:
                    st.write("")
                    if st.button("🛠️ Corrigir", key=f"dv_corrigir_{row['sku_base']}", use_container_width=True):
                        try:
                            n_venda = resolver_grupo_divergente(client_bq, row["skus"], custo_correto)
                            skus_txt = ", ".join(row["skus"])
                            st.session_state["validacao_resultado"] = {
                                "ok": True,
                                "msg": f"{skus_txt} corrigido(s) pra R$ {custo_correto:.2f}. {n_venda} venda(s) recalculada(s).",
                            }
                            st.cache_data.clear()
                        except Exception as e:
                            st.session_state["validacao_resultado"] = {"ok": False, "msg": f"Erro ao corrigir {row['sku_base']}: {e}"}
                        st.rerun()

# --- CAMPINEIRA ---
elif st.session_state.pg == "Campineira":
    from modulo_campineira import pagina_campineira
    pagina_campineira(client_bq)

# --- GESTÃO DE ESTOQUE ---
elif st.session_state.pg == "Gestão de Estoque":
    st.markdown('<h1>📦 Gestão de Estoque</h1>', unsafe_allow_html=True)
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)
    
    table_id_viva = "leandro-marketplace.DL_Store_Online.tb_estoque"
    table_id_hist = "leandro-marketplace.DL_Store_Online.tb_estoque_historico"
    
    with st.container(border=True):
        st.markdown("**📥 Registrar Entrada de Mercadoria**")
        if not df_base_completa.empty:
            df_est = df_base_completa.copy()
            df_est['Custo_num'] = df_est['Custo_aquisicao'].apply(converter_custo_seguro)
            
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                e_prod_sel = st.selectbox(
                    "Produto para Entrada", 
                    sorted(df_est['Produto'].unique()), 
                    index=None, 
                    placeholder="Escolha o Produto...",
                    key="estoque_prod"
                )
            with col_e2:
                e_sku_sel = st.selectbox(
                    "SKU para Entrada", 
                    sorted(df_est['SKU'].unique()), 
                    index=None, 
                    placeholder="Escolha o SKU...",
                    key="estoque_sku"
                )

            item_estoque = None
            if e_sku_sel: 
                item_estoque = df_est[df_est['SKU'] == e_sku_sel].iloc[0]
            elif e_prod_sel: 
                item_estoque = df_est[df_est['Produto'] == e_prod_sel].iloc[0]

            if item_estoque is not None:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #d1fae5 0%, #d1fae5 100%); border: 1px solid #6ee7b7; border-radius: 12px; padding: 16px; margin-bottom: 20px;">
                <p style="margin: 0; color: #059669;"><strong>📍</strong> {item_estoque['Produto']} <code style="background: white; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">{item_estoque['SKU']}</code></p>
                </div>
                """, unsafe_allow_html=True)
                
                c_in1, c_in2, c_in3 = st.columns(3)
                with c_in1:
                    qtd_in = st.number_input("Quantidade Comprada", min_value=1, value=1)
                with c_in2:
                    valor_pago_un = st.number_input("Valor Pago Unitário (R$)", min_value=0.01, step=0.01, value=item_estoque['Custo_num'])
                with c_in3:
                    valor_total_compra = qtd_in * valor_pago_un
                    st.metric("Total Investido", f"R$ {valor_total_compra:.2f}")

                if st.button("📥 Salvar Entrada no BQ", type="primary", use_container_width=True):
                    try:
                        from datetime import datetime, timedelta
                        data_brasilia = (datetime.utcnow() - timedelta(hours=3)).date()
                        
                        df_nova_entrada = pd.DataFrame([{
                            "produto": str(item_estoque['Produto']),
                            "sku": str(item_estoque['SKU']),
                            "quantidade": int(qtd_in),
                            "valor_pago": float(valor_pago_un),
                            "data_entrada": data_brasilia 
                        }])
                        job_config = bigquery.LoadJobConfig(
                            write_disposition="WRITE_APPEND",
                            schema=[bigquery.SchemaField("data_entrada", "DATE")]
                        )
                        client_bq.load_table_from_dataframe(df_nova_entrada, table_id_viva, job_config=job_config).result()

                        df_hist_entrada = pd.DataFrame([{
                            "produto": str(item_estoque['Produto']),
                            "sku": str(item_estoque['SKU']),
                            "quantidade": int(qtd_in),
                            "valor_pago": float(valor_pago_un),
                            "data_movimentacao": data_brasilia,
                            "tipo_movimentacao": "ENTRADA"
                        }])
                        client_bq.load_table_from_dataframe(df_hist_entrada, table_id_hist).result()

                        st.success("Estoque e Histórico atualizados!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e: 
                        st.error(f"Erro ao salvar: {e}")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    
    try:
        query_est = f"SELECT * FROM `{table_id_viva}`"
        df_raw = client_bq.query(query_est).to_dataframe()

        if not df_raw.empty:
            def recomendar_canal(custo):
                p_sugerido = custo * 1.35
                imp, c_fixo = 0.06, 1.00
                l_shein = p_sugerido - (p_sugerido * 0.18) - (p_sugerido * imp) - custo - c_fixo - 5.0
                tax_shopee = 4.0 if custo < 50 else 20.0
                l_shopee = p_sugerido - (p_sugerido * 0.20) - (p_sugerido * imp) - custo - c_fixo - tax_shopee
                l_temu = p_sugerido - (p_sugerido * imp) - custo - c_fixo
                l_tiktok = p_sugerido - (p_sugerido * 0.12) - (p_sugerido * imp) - custo - c_fixo - 4.0
                lucros = {"Shein": l_shein, "Shopee": l_shopee, "Temu": l_temu, "Tiktok": l_tiktok}
                melhor_canal = max(lucros, key=lucros.get)
                return melhor_canal, lucros[melhor_canal]

            total_investido_estoque = (df_raw['quantidade'] * df_raw['valor_pago']).sum()
            lucro_potencial_total = sum(df_raw.apply(lambda r: recomendar_canal(r['valor_pago'])[1] * r['quantidade'], axis=1))
            quantidade_total_itens = df_raw['quantidade'].sum()

            m1, m2, m3 = st.columns(3)
            with m1: st.metric("💰 Valor em Estoque", f"R$ {total_investido_estoque:,.2f}")
            with m2: st.metric("🚀 Lucro Potencial", f"R$ {lucro_potencial_total:,.2f}")
            with m3: st.metric("📦 Total de Itens", f"{int(quantidade_total_itens)} un")

            st.markdown('<h3>📈 Foto do Estoque (Saldo Final do Dia)</h3>', unsafe_allow_html=True)
            try:
                query_h = f"SELECT data_movimentacao, quantidade FROM `{table_id_hist}` ORDER BY data_movimentacao ASC"
                df_h_g = client_bq.query(query_h).to_dataframe()
                
                if not df_h_g.empty:
                    df_h_g['data_movimentacao'] = pd.to_datetime(df_h_g['data_movimentacao'])
                    df_h_g = df_h_g.sort_values('data_movimentacao')
                    df_diario = df_h_g.groupby(df_h_g['data_movimentacao'].dt.date)['quantidade'].sum().reset_index()
                    df_diario.columns = ['data_movimentacao', 'variacao_dia']
                    df_diario['saldo_final'] = df_diario['variacao_dia'].cumsum()
                    df_diario['label'] = pd.to_datetime(df_diario['data_movimentacao']).dt.strftime('%d/%m')

                    fig_foto = go.Figure(go.Bar(
                        x=df_diario['label'], 
                        y=df_diario['saldo_final'],
                        marker_color='#FBBF24', 
                        text=df_diario['saldo_final'], 
                        textposition='outside',
                        textfont=dict(size=11, color='#92400E', family="Arial"),
                        cliponaxis=False,
                        width=0.5
                    ))
                    
                    fig_foto.update_layout(
                        paper_bgcolor='white', 
                        plot_bgcolor='white', 
                        margin=dict(l=10, r=10, t=50, b=50), 
                        xaxis=dict(
                            visible=True,
                            showline=True,
                            linecolor='#E5E7EB',
                            linewidth=1,
                            showgrid=False,
                            showticklabels=True,
                            type='category',
                            tickfont=dict(size=10, color='#6B7280', family="Arial"),
                            tickangle=0
                        ),
                        yaxis=dict(
                            visible=False,
                            showgrid=False,
                            range=[0, df_diario['saldo_final'].max() * 1.5]
                        ),
                        showlegend=False,
                        bargap=0.1 
                    )
                    st.plotly_chart(fig_foto, use_container_width=True, config={'displayModeBar': False})
            except Exception as e_graph:
                st.error(f"Erro ao gerar gráfico: {e_graph}")

            st.markdown('<h3>📋 Gestão de Inventário por SKU</h3>', unsafe_allow_html=True)

            @st.fragment
            def tabela_sku_interativa(df_raw):
                df_visual_est = df_raw.groupby(['sku', 'produto']).agg({'quantidade': 'sum', 'valor_pago': 'mean'}).reset_index()
                
                st.markdown("""<div style="display: flex; font-weight: 600; background-color: #F3F4F6; padding: 12px 16px; border: 1px solid #E5E7EB; border-radius: 10px 10px 0 0; color: #374151; font-size: 13px;"><div style="flex: 2.5;">Produto</div><div style="flex: 1.2;">Melhor Canal</div><div style="flex: 1.2;">Lucro Total</div><div style="flex: 0.8;">Qtd</div><div style="flex: 1.5;">Ajustar (+/-)</div><div style="flex: 0.5;">Ação</div></div>""", unsafe_allow_html=True)

                for idx, r in df_visual_est.iterrows():
                    canal, lucro_un = recomendar_canal(r['valor_pago'])
                    cols = st.columns([2.5, 1.2, 1.2, 0.8, 1.5, 0.5])
                    
                    cols[0].markdown(f"<strong>{r['produto']}</strong><br/><small><code>{r['sku']}</code></small>", unsafe_allow_html=True)
                    cols[1].markdown(f"**{canal}**")
                    cols[2].write(f"R$ {lucro_un * r['quantidade']:.2f}")
                    cols[3].write(str(int(r['quantidade'])))
                    
                    ajuste = cols[4].number_input("", step=1, value=0, key=f"adj_{idx}", label_visibility="collapsed")
                    
                    if cols[5].button("💾", key=f"bt_{idx}"):
                        if ajuste != 0:
                            try:
                                from datetime import datetime, timedelta
                                dt_br = (datetime.utcnow() - timedelta(hours=3)).date()
                                n_saldo = int(r['quantidade']) + ajuste
                                
                                if n_saldo >= 0:
                                    client_bq.query(f"DELETE FROM `{table_id_viva}` WHERE sku = '{r['sku']}'").result()
                                    if n_saldo > 0:
                                        df_up = pd.DataFrame([{"produto": r['produto'], "sku": r['sku'], "quantidade": n_saldo, "valor_pago": float(r['valor_pago']), "data_entrada": dt_br}])
                                        client_bq.load_table_from_dataframe(df_up, table_id_viva).result()
                                    
                                    tipo_aj = "ENTRADA" if ajuste > 0 else "BAIXA"
                                    df_h = pd.DataFrame([{"produto": r['produto'], "sku": r['sku'], "quantidade": int(ajuste), "valor_pago": float(r['valor_pago']), "data_movimentacao": dt_br, "tipo_movimentacao": tipo_aj}])
                                    client_bq.load_table_from_dataframe(df_h, table_id_hist).result()
                                    
                                    st.success("Estoque atualizado!")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("Saldo insuficiente!")
                            except Exception as e_proc:
                                st.error(f"Erro: {e_proc}")
                    st.divider()

            tabela_sku_interativa(df_raw)

        else:
            st.info("Estoque vazio no momento.")

    except Exception as e_geral:
        st.error(f"Erro ao carregar dados do estoque: {e_geral}")