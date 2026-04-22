# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import re
import urllib.parse
import json
import os
import io
import base64
from datetime import datetime
from google.cloud import bigquery
from google.oauth2 import service_account
import plotly.graph_objects as go # Importando Plotly
if 'processando_venda' not in st.session_state:
    st.session_state.processando_venda = False
from datetime import datetime, timedelta


# --- CONFIGURAÇÕES DE PÁGINA ---
st.set_page_config(
    page_title="D.L Online Store", 
    page_icon="🛒", # <--- ALTERE AQUI (Pode colar o emoji do carrinho)
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- ESTILIZAÇÃO CUSTOMIZADA ---
st.markdown("""
    <style>
    .stApp { background-color: white !important; }
    [data-testid="stSidebar"] { background-color: #f8f9fa !important; border-right: 1px solid #e6e6e6; }
    h1, h2, h3, p, span, label, .stMarkdown { color: #31333F !important; }
    
    /* Borda sutil nas tabelas padrão */
    .stTable, [data-testid="stTable"] {
        border: 1px solid #f0f0f0 !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }

    /* Borda sutil nos containers de gráficos/cards */
    .plot-container {
        border: 1px solid #e6e6e6 !important; 
        border-radius: 12px !important;
        padding: 15px !important;
        background-color: #ffffff !important;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
    }

    /* ESTILO DA TABELA DE HISTÓRICO (LATERAIS, ZEBRA, HOVER E SCROLL) */
    .historico-scroll-container {
        border: 1px solid #e6e6e6 !important; /* Bordas laterais e completas */
        border-radius: 10px !important;
        max-height: 800px !important; /* Altura aproximada para 20 itens */
        overflow-y: auto !important; /* Barra de rolagem se exceder */
        background-color: white;
    }
    
    .linha-historico {
        padding: 8px 15px;
        border-bottom: 1px solid #f0f0f0;
        transition: background-color 0.2s;
        display: flex;
        align-items: center;
    }
    
    /* Efeito Zebra: cores alternadas */
    .linha-historico:nth-child(odd) { background-color: #ffffff; }
    .linha-historico:nth-child(even) { background-color: #f9f9f9; }
    
    /* Efeito Hover: cor ao passar o mouse */
    .linha-historico:hover {
        background-color: #FFF9E6 !important;
    }

    section[data-testid="stSidebar"] .stButton button {
        width: 100% !important;
        border-radius: 10px !important;
        height: 3.5em !important;
        min-height: 3.5em !important;
        background-color: #ffffff !important;
        color: #31333F !important;
        border: 1px solid #e6e6e6 !important;
        text-align: left !important;
        padding-left: 20px !important;
        margin-bottom: 2px !important;
        display: block !important;
    }
    
    section[data-testid="stSidebar"] .stButton p {
        font-size: 14px !important;
        white-space: nowrap !important;
    }

    section[data-testid="stSidebar"] .stButton button:hover { 
        background-color: #FFF9E6 !important; 
        border: 1px solid #FFD700 !important; 
        color: #CC9900 !important; 
    }
    
    section[data-testid="stSidebar"] .stButton button[type="primary"] {
        background-color: #FFD700 !important; 
        color: black !important; 
        border: none !important; 
        text-align: center !important; 
        font-weight: bold !important;
        padding-left: 0px !important;
    }

    [data-testid="stImage"] img {
        height: auto; 
        object-fit: contain; 
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXÃO COM BIGQUERY (NOVO BANCO DO LEANDRO) ---

@st.cache_resource
def conectar_bigquery():
    from google.cloud import bigquery
    from google.oauth2 import service_account

    try:
        # 1. Busca os dados do segredo que você configurou
        info = st.secrets["gcp_service_account"]

        # 2. Transforma as informações em credenciais válidas
        creds = service_account.Credentials.from_service_account_info(info)

        # 3. Cria o cliente do BigQuery usando essas credenciais
        client = bigquery.Client(credentials=creds, project=info['project_id'])
        return client

    except Exception as e:
        st.error(f"Erro ao conectar no BigQuery: {e}")
        return None

# --- ATENÇÃO: Esta linha abaixo deve ficar fora da função (sem espaços no começo) ---
client_bq = conectar_bigquery()

#if client_bq:
#    st.success("Motor do BigQuery ligado com sucesso!")
#else:
#    st.error("O motor não ligou. Verifique os segredos.")

# Função para buscar dados (Substitui a buscar_dados_planilha)
@st.cache_data(ttl=60)
def buscar_dados_vendas(_client):
    query = "SELECT * FROM `leandro-marketplace.vendas_loja.vendas_realizadas` ORDER BY data DESC"
    return _client.query(query).to_dataframe()

@st.cache_data(ttl=60) # PROTEÇÃO: Lê os dados e segura na memória por 60 segundos
def buscar_dados_planilha(_planilha, nome_aba):
    try:
        if _planilha:
            return _planilha.worksheet(nome_aba).get_all_values()
        return None
    except:
        return None

def converter_custo_seguro(valor_raw):
    if valor_raw is None or valor_raw == "": 
        return 0.0
    s = str(valor_raw).replace('R$', '').replace(' ', '').strip()
    try:
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except (ValueError, TypeError):
        return 0.0

def calcular_venda_completo(custo_aquisicao, margem_percentual, mkt):
    imposto_tax = 0.06  # 6% de imposto fixo em todos
    margem_alvo = margem_percentual / 100
    custo_embalagem = 1.00  # R$ 1,00 fixo de embalagem
    
    if mkt == "shein":
        # SHEIN: 18% de comissão + R$ 5,00 fixos
        comissao_mkt, taxa_fixa = 0.18, 5.0
        divisor = 1 - (comissao_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_embalagem + taxa_fixa) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comissao_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_embalagem - taxa_fixa
        return preco, lucro
    
    elif mkt == "shopee":
        # SHOPEE: Lógica baseada no PREÇO DE VENDA FINAL (Estimativa por faixas)
        # Como as taxas dependem do preço final, testamos as faixas:
        
        def testar_faixa(comis, taxa):
            div = 1 - (comis + imposto_tax + margem_alvo)
            p = (custo_aquisicao + custo_embalagem + taxa) / div if div > 0 else 0
            return p

        # 1. Tentativa: Até R$ 79,99 (20% + R$ 4)
        p_venda = testar_faixa(0.20, 4.0)
        
        if p_venda > 79.99:
            # 2. Tentativa: R$ 80 a R$ 99,99 (14% + R$ 16)
            p_venda = testar_faixa(0.14, 16.0)
            
            if p_venda > 99.99:
                # 3. Tentativa: R$ 100 a R$ 199,99 (14% + R$ 20)
                p_venda = testar_faixa(0.14, 20.0)
                
                if p_venda > 199.99:
                    # 4. Tentativa: R$ 200 a R$ 499,99 (14% + R$ 26)
                    p_venda = testar_faixa(0.14, 26.0)

        # Cálculo do lucro real após definir a faixa de preço
        # Re-identificar comissão e taxa para o cálculo do lucro
        if p_venda <= 79.99: c_final, t_final = 0.20, 4.0
        elif p_venda <= 99.99: c_final, t_final = 0.14, 16.0
        elif p_venda <= 199.99: c_final, t_final = 0.14, 20.0
        else: c_final, t_final = 0.14, 26.0

        lucro = p_venda - (p_venda * c_final) - (p_venda * imposto_tax) - custo_aquisicao - custo_embalagem - t_final
        return p_venda, lucro

    elif mkt == "temu":
        # TEMU: Sem taxas de marketplace, apenas Imposto (6%) e Embalagem (R$ 1)
        divisor = 1 - (imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_embalagem) / divisor if divisor > 0 else 0
        lucro = preco - (preco * imposto_tax) - custo_aquisicao - custo_embalagem
        return preco, lucro
        
    return 0, 0

# --- ESTADO E NAVEGAÇÃO ---
if 'pg' not in st.session_state: st.session_state.pg = "Início"
if 'logado' not in st.session_state: st.session_state.logado = False

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3081/3081559.png", width=80)
    st.title("D.L Online Store")
    if st.button("🏠 Início"): st.session_state.pg = "Início"
    if st.button("👥 Quem Somos"): st.session_state.pg = "Quem Somos"
    if st.button("🛠️ Serviços"): st.session_state.pg = "Serviços"
    if st.button("✉️ Contato"): st.session_state.pg = "Contato"
    st.divider()
    
    if not st.session_state.logado:
        st.subheader("🔐 Área do Vendedor")
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.button("Entrar no Painel", type="primary"):
            if u == "leandro" and p == "123":
                st.session_state.logado = True
                st.session_state.pg = "Calculadora" 
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
    else:
        st.subheader(f"👋 Olá, Leandro")
        if st.button("📊 Comparativo de Preços"): st.session_state.pg = "Calculadora"
        if st.button("📝 Novo Item na Base"): st.session_state.pg = "Cadastro"
        if st.button("💰 Alterar Preços"):    st.session_state.pg = "Alterar Preco"
        if st.button("📈 Análise de Vendas"): st.session_state.pg = "Análise de Vendas"
        if st.button("📦 Gestão de Estoque"): st.session_state.pg = "Gestão de Estoque"
        if st.button("📉 Dashboard Financeiro"): st.session_state.pg = "Dashboard"

        st.write("")
        if st.button("🚪 Sair"):
            st.session_state.logado = False
            st.rerun()

# --- PÁGINA INÍCIO ---
if st.session_state.pg == "Início":
    caminho_local = r"C:\Users\Junior\Desktop\CodigosPython2\banner_inicio.jpg"
    if os.path.exists(caminho_local):
        st.image(caminho_local, use_container_width=True)
    elif os.path.exists("banner_inicio.jpg"):
        st.image("banner_inicio.jpg", use_container_width=True)
    else:
        st.image("https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=crop&w=1000&q=80", use_container_width=True)
    
    st.markdown("<h1 style='text-align: center;'>Bem-vindo à D.L Online Store</h1>", unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns([1,3,1])
    with col_b:
        st.markdown("""
        ### Sua Experiência de Compra Inteligente
        
        Na **D.L Online Store**, nossa missão vai além de vender produtos. Estamos focados em conectar você às melhores oportunidades dos maiores marketplaces do mundo, garantindo uma curadoria de qualidade e preços competitivos.
        
        #### Nosso Maior Compromisso: Você.
        
        Acreditamos que a verdadeira venda só termina quando você está satisfeito. Por isso, fundamentamos nossa operação em:
        
        1.  🌟 **Satisfação Garantida:** Trabalhamos incansavelmente para que sua experiência seja perfeita.
        2.  🛡️ **Qualidade e Confiança:** Selecionamos produtos com rigor para garantir que você receba o melhor.
        3.  🤝 **Suporte Ágil:** Nossa equipe está sempre pronta para ouvir e resolver suas dúvidas.
        
        Obrigado por escolher a **D.L Online Store**. Boas compras!
        """)

elif st.session_state.pg == "Quem Somos":
    st.header("👥 Quem Somos")
    st.write("Especialistas em e-commerce e curadoria de produtos de alta qualidade.")

elif st.session_state.pg == "Serviços":
    st.header("🛠️ Nossos Serviços")
    st.write("Vendas e logística eficiente em marketplaces globais.")

elif st.session_state.pg == "Contato":
    st.header("✉️ Central de Atendimento")
    whatsapp_url = "https://wa.me/5511960501826"
    st.markdown(f'<a href="{whatsapp_url}" target="_blank" style="text-decoration: none;"><div style="background-color: #25D366; color: white; padding: 15px; border-radius: 10px; display: inline-block; font-weight: bold; font-size: 18px;">Falar no WhatsApp: (11) 96050-1826</div></a>', unsafe_allow_html=True)
    st.divider()
    with st.form("form_contato"):
        nome = st.text_input("Nome")
        prod = st.text_input("Produto")
        tipo = st.selectbox("Assunto", ["Dúvida", "Elogio", "Reclamação"])
        msg = st.text_area("Mensagem")
        if st.form_submit_button("Gerar E-mail"):
            if nome and msg:
                mailto = f"mailto:vendas.dlonlinestore@gmail.com?subject={tipo}&body={msg}"
                st.markdown(f'<a href="{mailto}" style="background-color:#007bff; color:white; padding:10px; border-radius:5px; text-decoration:none;">📧 Abrir E-mail</a>', unsafe_allow_html=True)

# --- CONEXÃO COM BIGQUERY (LIGAR O MOTOR) ---
@st.cache_resource
def conectar_bigquery():
    from google.cloud import bigquery
    from google.oauth2 import service_account
    try:
        # Busca os dados do segredo configurado no secrets.toml
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(info)
        client = bigquery.Client(credentials=creds, project=info['project_id'])
        return client
    except Exception as e:
        st.error(f"Erro ao conectar no BigQuery: {e}")
        return None

# Ativa o cliente globalmente para ser usado pelas funções abaixo
client_bq = conectar_bigquery()

# --- FUNÇÕES DE BUSCA (DEFINIÇÃO DO MOTOR) ---

def buscar_produtos_bq():
    if client_bq:
        query = "SELECT * FROM `leandro-marketplace.DL_Store_Online.tb_produtos`"
        return client_bq.query(query).to_dataframe()
    return pd.DataFrame()

def buscar_vendas_resumo_bq():
    if client_bq:
        query = """
        SELECT 
            SUM(preco_venda * quantidade) as faturamento_total,
            SUM(Llcro_Total) as lucro_total,
            SUM(quantidade) as itens_vendidos
        FROM `leandro-marketplace.DL_Store_Online.tb_vendas_realizadas`
        """
        return client_bq.query(query).to_dataframe()
    return pd.DataFrame()

# --- ÁREA RESTRITA (EXECUÇÃO DA BUSCA) ---
df_base_completa = pd.DataFrame()

if st.session_state.logado and client_bq:
    try:
        # Agora o Python reconhece a função pois ela foi definida acima
        df_base_completa = buscar_produtos_bq()
        
        if not df_base_completa.empty:
            df_base_completa = df_base_completa.drop_duplicates(subset=['SKU'])
    except Exception as e:
        st.error(f"Erro ao acessar o BigQuery: {e}")

# --- NAVEGAÇÃO ENTRE PÁGINAS ---

# 1. PÁGINA CALCULADORA
if st.session_state.pg == "Calculadora":
    st.header("📊 Comparativo de Preços")
    if not df_base_completa.empty:
        df_geral = df_base_completa.copy()
        df_geral['Custo_aquisicao_num'] = df_geral['Custo_aquisicao'].apply(converter_custo_seguro)
        
        col_sel1, col_sel2 = st.columns(2)
        
        with col_sel1:
            opcoes_produtos = sorted([str(p) for p in df_geral['Produto'].unique()])
            prod_sel = st.selectbox("Pesquisar Produto", opcoes_produtos, index=None, placeholder="Digite o produto...")
            
        with col_sel2:
            opcoes_skus = sorted([str(s) for s in df_geral['SKU'].unique()])
            v_sku_sel = st.selectbox("Pesquisar por SKU", opcoes_skus, index=None, placeholder="Busque o SKU...")

        final_item = None
        if v_sku_sel: 
            final_item = df_geral[df_geral['SKU'] == v_sku_sel].iloc[0]
        elif prod_sel: 
            final_item = df_geral[df_geral['Produto'] == prod_sel].iloc[0]

        if final_item is not None:
            custo_aq = final_item['Custo_aquisicao_num']
            st.info(f"Selecionado: {final_item['Produto']} | SKU: {final_item['SKU']}")
            margem_input = st.number_input("Margem de Lucro Desejada (%)", min_value=1.0, value=15.0, step=1.0)
            
            p_shein, l_shein = calcular_venda_completo(custo_aq, margem_input, "shein")
            p_shopee, l_shopee = calcular_venda_completo(custo_aq, margem_input, "shopee")
            p_temu, l_temu = calcular_venda_completo(custo_aq, margem_input, "temu")
            
            st.divider()
            st.metric("Custo de Aquisição Base", f"R$ {custo_aq:.2f}")
            res = {
                "Canal": ["SHEIN", "SHOPEE", "TEMU"], 
                "Preço Sugerido": [f"R$ {p_shein:.2f}", f"R$ {p_shopee:.2f}", f"R$ {p_temu:.2f}"], 
                "Lucro Líquido Real": [f"R$ {l_shein:.2f}", f"R$ {l_shopee:.2f}", f"R$ {l_temu:.2f}"]
            }
            st.table(pd.DataFrame(res))

elif st.session_state.pg == "Análise de Vendas":
    st.header("📈 Análise de Vendas")
    if not df_base_completa.empty:
        df_rel = df_base_completa.copy()
        df_rel['Custo_num'] = df_rel['Custo_aquisicao'].apply(converter_custo_seguro)
        st.divider()
        st.subheader("🏆 Inteligência de Mercado (Melhor Margem)")
        m_alvo = st.slider("Margem para Análise (%)", 1.0, 50.0, 2.0)
        rank_data = []
        for _, r in df_rel.iterrows():
            _, l1 = calcular_venda_completo(r['Custo_num'], m_alvo, "shein")
            _, l2 = calcular_venda_completo(r['Custo_num'], m_alvo, "shopee")
            _, l3 = calcular_venda_completo(r['Custo_num'], m_alvo, "temu")
            max_l = max(l1, l2, l3)
            rank_data.append({"Produto": r['Produto'], "SKU": r['SKU'], "Lucro Estimado": round(max_l, 2)})
        
        df_rank = pd.DataFrame(rank_data).sort_values(by="Lucro Estimado", ascending=False)
        st.dataframe(df_rank, use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_rank.to_excel(writer, index=False, sheet_name='Ranking_Lucro')
            writer.close()
        
        st.download_button(
            label="📥 Exportar Ranking (xlsx)",
            data=buffer.getvalue(),
            file_name="ranking_lucro_dl_store.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# --- SEÇÃO DE CADASTRO ---
elif st.session_state.pg == "Cadastro":
    st.header("📝 Novo Item na Base")
    
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

    # --- CAMPOS REATIVOS (FORA DO FORM PARA VALIDAÇÃO EM TEMPO REAL) ---
    m = st.selectbox("Marketplace", ["shein", "shopee", "temu", "todos"])
    n = st.text_input("Nome Base do Produto")
    
    # Campo SKU Base
    s_base = st.text_input("SKU Base", help="Digite o SKU e aperte Enter ou clique fora para validar")
    
    # Coleta de Variantes fora do formulário
    lista_variantes = []
    if st.session_state.cont_var > 0:
        st.write("---")
        for i in range(st.session_state.cont_var):
            c1, c2 = st.columns(2)
            with c1:
                v_sku = st.text_input(f"SKU Variante {i+1}", key=f"vsku_{i}")
            with c2:
                v_char = st.text_input(f"Cor/Modelo {i+1}", key=f"vchar_{i}")
            if v_sku:
                lista_variantes.append({"nome": f"{n} {v_char}", "sku": v_sku.strip().upper()})

    # --- LÓGICA DE VALIDAÇÃO (BASE + VARIANTES) ---
    sku_bloqueado = False
    todos_skus_digitados = []
    
    if s_base:
        todos_skus_digitados.append(s_base.strip().upper())
    for v in lista_variantes:
        todos_skus_digitados.append(v['sku'])

    if todos_skus_digitados:
        try:
            # Formata a lista para o SQL: ('SKU1', 'SKU2')
            format_skus = ", ".join([f"'{s}'" for s in todos_skus_digitados])
            
            # Busca na coluna SKU (maiúscula) da tb_produtos
            q_verificacao = f"SELECT SKU FROM `leandro-marketplace.DL_Store_Online.tb_produtos` WHERE SKU IN ({format_skus})"
            verificacao_df = client_bq.query(q_verificacao).to_dataframe()
            
            if not verificacao_df.empty:
                # O .unique() garante que o SKU apareça apenas 1 vez no erro, mesmo que exista em vários marketplaces
                skus_conflito = verificacao_df['SKU'].unique().tolist()
                
                st.error(f"❌ ERRO: O(s) SKU(s) {skus_conflito} JÁ EXISTE(M)! Altere para salvar.")
                sku_bloqueado = True
            else:
                st.success("✅ Todos os SKUs informados estão disponíveis.")
                sku_bloqueado = False
        except Exception as e:
            st.caption("Conectando ao BigQuery para validar SKUs...")

    # --- FORMULÁRIO FINAL (CUSTO E BOTÃO SALVAR) ---
    with st.form("botao_salvar"):
        c = st.number_input("Custo Unitário (R$)", min_value=0.01, step=0.01)
        
        salvar_final = st.form_submit_button("🚀 Salvar Tudo no BigQuery", type="primary")

        if salvar_final:
            if sku_bloqueado:
                st.error("🚨 Gravação interrompida! Corrija os SKUs duplicados antes de salvar.")
            elif not n or not s_base:
                st.error("⚠️ Preencha os campos obrigatórios: Nome e SKU Base.")
            else:
                try:
                    mkt_list = ["shein", "shopee", "temu"] if m == "todos" else [m]
                    lote = []
                    
                    for aba in mkt_list:
                        # Adiciona SKU Base ao lote
                        lote.append({
                            "marketplace": aba, 
                            "SKU": str(s_base).strip().upper(), 
                            "produto": str(n), 
                            "custo_aquisicao": float(c)
                        })
                        # Adiciona cada Variante ao lote
                        for v in lista_variantes:
                            lote.append({
                                "marketplace": aba, 
                                "SKU": str(v['sku']), 
                                "produto": str(v['nome']), 
                                "custo_aquisicao": float(c)
                            })
                    
                    # Envio para o BigQuery
                    erros = client_bq.insert_rows_json("leandro-marketplace.DL_Store_Online.tb_produtos", lote)
                    
                    if not erros:
                        st.success("✅ Tudo pronto! Dados salvos com sucesso.")
                        st.cache_data.clear() # Limpa o cache para a próxima consulta ser atualizada
                        st.session_state.cont_var = 0 # Reseta variantes
                        st.rerun()
                    else:
                        st.error(f"Erro ao inserir no BigQuery: {erros}")
                except Exception as e:
                    st.error(f"Falha técnica na gravação: {e}")

elif st.session_state.pg == "Alterar Preco":
    st.header("📦 Atualização de Preços em Lote")

    # Inicializa a lista de alterações na sessão se não existir
    if 'lista_updates' not in st.session_state:
        st.session_state.lista_updates = []

    # 1. Busca os produtos para o Selectbox
    @st.cache_data(ttl=600)
    def listar_skus_disponiveis():
        query = "SELECT DISTINCT sku, produto, custo_aquisicao FROM `leandro-marketplace.DL_Store_Online.tb_produtos` ORDER BY produto"
        return client_bq.query(query).to_dataframe()

    df_produtos = listar_skus_disponiveis()

    # --- ÁREA DE ADIÇÃO ---
    with st.expander("➕ Adicionar Item para Alteração", expanded=True):
        opcoes = df_produtos.apply(lambda x: f"{x['sku']} - {x['produto']}", axis=1).tolist()
        
        # Campo agora permite digitar livremente e começa vazio
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
                # Adiciona à lista temporária na session_state
                st.session_state.lista_updates.append({
                    "sku": sku_ref,
                    "produto": dados_ref['produto'],
                    "novo_valor": novo_custo_bulk
                })
                st.rerun()
        else:
            st.info("Pesquise um produto acima para ajustar o valor.")

    # --- FILA DE PROCESSAMENTO ---
    if st.session_state.lista_updates:
        st.subheader("📋 Itens na Fila")
        
        # Exibe o que será alterado
        for i, item in enumerate(st.session_state.lista_updates):
            col_info, col_del = st.columns([4, 1])
            col_info.info(f"**SKU:** {item['sku']} | **Novo Valor:** R$ {item['novo_valor']:.2f}")
            if col_del.button("🗑️", key=f"del_{i}"):
                st.session_state.lista_updates.pop(i)
                st.rerun()

        st.divider()
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("🚀 Enviar Pacote ao BigQuery", type="primary"):
                try:
                    # Criamos um script único com múltiplos UPDATES
                    queries = []
                    for item in st.session_state.lista_updates:
                        q = f"UPDATE `leandro-marketplace.DL_Store_Online.tb_produtos` SET custo_aquisicao = {float(item['novo_valor'])} WHERE sku = '{item['sku']}';"
                        queries.append(q)
                    
                    full_query = "\n".join(queries)
                    
                    # Executa o pacote de uma vez
                    job = client_bq.query(full_query)
                    job.result()

                    st.success(f"✅ Sucesso! {len(st.session_state.lista_updates)} itens atualizados.")
                    st.session_state.lista_updates = [] # Limpa a fila
                    st.cache_data.clear()
                    st.balloons()
                except Exception as e:
                    st.error(f"Erro no processamento em lote: {e}")
        
        with col_btn2:
            if st.button("❌ Limpar Fila"):
                st.session_state.lista_updates = []
                st.rerun()
    else:
        st.write("") # Espaçador visual




# --- SEÇÃO DO DASHBOARD ---
elif st.session_state.pg == "Dashboard":
    from datetime import timedelta
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    st.header("📊 Dashboard Financeiro")
    
    if 'processando_venda' not in st.session_state:
        st.session_state.processando_venda = False

    # --- 1. REGISTRO DE NOVA VENDA (BIGQUERY) ---
    with st.expander("➕ Registrar Nova Venda", expanded=True):
        if not df_base_completa.empty:
            df_dash = df_base_completa.copy()
            df_dash['Custo_num'] = df_dash['Custo_aquisicao'].apply(converter_custo_seguro)
            
            col_p1, col_p2 = st.columns(2)
            
            with col_p1:
                v_prod_sel = st.selectbox("Pesquisar por Nome", sorted(df_dash['Produto'].unique()), index=None, placeholder="Busque o Produto...")
            with col_p2:
                v_sku_sel = st.selectbox("Pesquisar por SKU", sorted(df_dash['SKU'].unique()), index=None, placeholder="Busque o SKU...")

            item_venda = None
            if v_sku_sel: item_venda = df_dash[df_dash['SKU'] == v_sku_sel].iloc[0]
            elif v_prod_sel: item_venda = df_dash[df_dash['Produto'] == v_prod_sel].iloc[0]

            if item_venda is not None:
                v_nome_final, v_sku_final, v_custo_base = item_venda['Produto'], item_venda['SKU'], item_venda['Custo_num']
                st.success(f"✅ Item: **{v_nome_final}** | SKU: **{v_sku_final}** | Custo Base: **R$ {v_custo_base:.2f}**")
                
                c_v1, c_v2, c_v3 = st.columns(3)
                with c_v1:
                    mkt_venda = st.selectbox("Canal de Venda", ["shein", "shopee", "temu"])
                    v_qtd = st.number_input("Qtd Vendida", min_value=1, value=1)
                with c_v2:
                    v_preco_venda = st.number_input("Preço de Venda Praticado (R$)", min_value=0.0, step=0.01, value=0.0)
                    imp, c_fixo = 0.06, 1.00
                    if mkt_venda == "shein": com, tax = 0.18, 5.0
                    elif mkt_venda == "shopee": com, tax = 0.20, (4.0 if v_custo_base < 50 else 20.0)
                    else: com, tax = 0.0, 0.0
                    lucro_un_calc = v_preco_venda - (v_preco_venda * com) - (v_preco_venda * imp) - v_custo_base - c_fixo - tax
                    v_margem_auto = (lucro_un_calc / v_preco_venda * 100) if v_preco_venda > 0 else 0.0
                    st.write(f"Margem: **{v_margem_auto:.2f}%**")
                with c_v3:
                    v_data = st.date_input("Data da Venda", value=(datetime.utcnow() - timedelta(hours=3)))
                    lucro_total_dinamico = lucro_un_calc * v_qtd
                    st.metric("Lucro Total", f"R$ {lucro_total_dinamico:.2f}")

                if not st.session_state.processando_venda:
                    if st.button("🚀 Confirmar e Registrar Venda", type="primary"):
                        st.session_state.processando_venda = True
                        try:
                            table_id = "leandro-marketplace.DL_Store_Online.tb_vendas_realizadas"
                            v_data_formatada = v_data.strftime("%Y-%m-%d") 
                            row = [{
                                "produto": str(v_nome_final), "sku": str(v_sku_final), 
                                "preco_venda": float(v_preco_venda), "quantidade": int(v_qtd), 
                                "data": v_data_formatada, "lucro_total": float(round(lucro_total_dinamico, 2))
                            }]
                            errors = client_bq.insert_rows_json(table_id, row)
                            if not errors:
                                st.success("Venda registrada!"); st.cache_data.clear(); st.session_state.processando_venda = False; st.rerun()
                            else:
                                st.error(f"Erro BQ: {errors}"); st.session_state.processando_venda = False
                        except Exception as e:
                            st.error(f"Erro: {e}"); st.session_state.processando_venda = False

    # --- 2. SEÇÃO DE GRÁFICOS ---
    st.divider()
    try:
        query = "SELECT * FROM `leandro-marketplace.DL_Store_Online.tb_vendas_realizadas` ORDER BY data DESC"
        df_vendas = client_bq.query(query).to_dataframe()

        if not df_vendas.empty:
            df_vendas.columns = ['Produto', 'SKU', 'Preço Venda', 'Quantidade', 'Data', 'Lucro Total']
            df_vendas['Preço Venda'] = pd.to_numeric(df_vendas['Preço Venda'])
            df_vendas['Lucro Total'] = pd.to_numeric(df_vendas['Lucro Total'])
            df_vendas['Quantidade'] = pd.to_numeric(df_vendas['Quantidade'])
            df_vendas['Faturamento'] = df_vendas['Preço Venda'] * df_vendas['Quantidade']
            df_vendas['Data'] = pd.to_datetime(df_vendas['Data'])
            
            hoje = datetime.utcnow() - timedelta(hours=3)
            inicio_mes_atual = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # Agrupamento barras
            df_passado = df_vendas[df_vendas['Data'] < inicio_mes_atual].copy()
            barras_meses_fechados = pd.DataFrame()
            if not df_passado.empty:
                meses_map = {1:'Jan', 2:'Fev', 3:'Mar', 4:'Abr', 5:'Mai', 6:'Jun', 7:'Jul', 8:'Ago', 9:'Set', 10:'Out', 11:'Nov', 12:'Dez'}
                df_passado['Mes_Ano'] = df_passado['Data'].dt.month.map(meses_map) + "/" + df_passado['Data'].dt.year.astype(str).str[-2:]
                barras_meses_fechados = df_passado.groupby('Mes_Ano').agg({'Faturamento':'sum', 'Lucro Total':'sum', 'Quantidade':'sum'}).reset_index()
                barras_meses_fechados['Outros Custos'] = barras_meses_fechados['Faturamento'] - barras_meses_fechados['Lucro Total']
                barras_meses_fechados.rename(columns={'Mes_Ano': 'Data_Label'}, inplace=True)

            df_atual_full = df_vendas[df_vendas['Data'] >= inicio_mes_atual].copy()
            df_plot_atual = pd.DataFrame()
            if not df_atual_full.empty:
                total_atual = pd.DataFrame([{'Data_Label': 'Mês Atual', 'Faturamento': df_atual_full['Faturamento'].sum(), 'Lucro Total': df_atual_full['Lucro Total'].sum(), 'Quantidade': df_atual_full['Quantidade'].sum(), 'Outros Custos': df_atual_full['Faturamento'].sum() - df_atual_full['Lucro Total'].sum()}])
                df_diario = df_atual_full.groupby('Data').agg({'Faturamento':'sum', 'Lucro Total':'sum', 'Quantidade':'sum'}).reset_index()
                df_diario['Outros Custos'] = df_diario['Faturamento'] - df_diario['Lucro Total']
                df_diario['Data_Label'] = df_diario['Data'].dt.strftime('%d/%m')
                df_plot_atual = pd.concat([total_atual, df_diario], ignore_index=True)

            df_plot = pd.concat([barras_meses_fechados, df_plot_atual], ignore_index=True)

            # Criar DF específico para a linha (Removendo "Mês Atual" e meses passados se houver)
            df_linha = df_plot[~df_plot['Data_Label'].isin(['Mês Atual']) & df_plot['Data_Label'].str.contains('/')].copy()

            # --- GRÁFICO ---
            st.subheader("📈 Desempenho Mensal e Diário")
            with st.container():
                st.markdown('<div class="plot-container">', unsafe_allow_html=True)
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                
                # Barras
                fig.add_trace(go.Bar(x=df_plot['Data_Label'], y=df_plot['Outros Custos'], name='Outros Custos', marker_color='#FFF9E6', hovertemplate='R$ %{y:,.2f}<extra></extra>'), secondary_y=False)
                fig.add_trace(go.Bar(x=df_plot['Data_Label'], y=df_plot['Lucro Total'], name='Lucro Líquido', marker_color='#FFD700', hovertemplate='R$ %{y:,.2f}<extra></extra>', text=df_plot['Lucro Total'].apply(lambda x: f'R$ {x:,.2f}'), textposition='outside', textfont=dict(size=14, color='black', family="Arial Black")), secondary_y=False)
                
                # Linha Cinza Escuro (Desvinculada do Mês Atual)
                fig.add_trace(go.Scatter(
                    x=df_linha['Data_Label'], y=df_linha['Quantidade'], name='Qtd Vendas', mode='lines+markers+text',
                    line=dict(color='#333333', width=2), marker=dict(size=7, color='#333333'),
                    text=df_linha['Quantidade'], textposition="top center",
                    textfont=dict(size=12, color='#333333', family="Arial Black"),
                    hovertemplate='Vendas: %{y}<extra></extra>'
                ), secondary_y=True)

                fig.update_layout(
                    barmode='stack', paper_bgcolor='white', plot_bgcolor='white', 
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=True, range=[0, df_plot['Faturamento'].max() * 2.2]), 
                    yaxis2=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=True, range=[df_plot['Quantidade'].max() * -1.5, df_plot['Quantidade'].max() * 1.2]),
                    xaxis=dict(title="Competência / Dias", showgrid=False, showline=True, linecolor='black', tickfont=dict(color='black', size=13)), 
                    legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5, font=dict(color="black", size=14)), 
                    margin=dict(l=10, r=10, t=80, b=60), hovermode='x unified'
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                st.markdown('</div>', unsafe_allow_html=True)

            # Métricas
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento Total", f"R$ {df_vendas['Faturamento'].sum():.2f}")
            c2.metric("Lucro Líquido", f"R$ {df_vendas['Lucro Total'].sum():.2f}")
            c3.metric("Itens Vendidos", int(df_vendas['Quantidade'].sum()))

            st.divider()
            st.subheader("📋 Histórico de Vendas")
            st.markdown("""<div style="display: flex; font-weight: bold; background-color: #f8f9fa; padding: 10px 15px; border: 1px solid #e6e6e6; border-radius: 10px 10px 0 0;"><div style="flex: 3;">Produto</div><div style="flex: 2;">SKU</div><div style="flex: 1;">Qtd</div><div style="flex: 2;">Data</div><div style="flex: 2;">Lucro</div><div style="flex: 1;">Ação</div></div>""", unsafe_allow_html=True)
            for idx, row in df_vendas.iterrows():
                cols = st.columns([3, 2, 1, 2, 2, 1])
                cols[0].write(row['Produto']); cols[1].write(f"`{row['SKU']}`"); cols[2].write(str(int(row['Quantidade']))); cols[3].write(row['Data'].strftime('%d/%m/%Y')); cols[4].write(f"R$ {row['Lucro Total']:.2f}")
                if cols[5].button("❌", key=f"del_{idx}"):
                    client_bq.query(f"DELETE FROM `leandro-marketplace.DL_Store_Online.tb_vendas_realizadas` WHERE sku = '{row['SKU']}' AND data = '{row['Data'].strftime('%Y-%m-%d')}' AND lucro_total = {row['Lucro Total']}").result()
                    st.cache_data.clear(); st.rerun()
        else:
            st.info("Nenhuma venda registrada ainda.")
    except Exception as e:
        st.error(f"Erro no Dashboard: {e}")

# --- SEÇÃO DE ESTOQUE ---
elif st.session_state.pg == "Gestão de Estoque":
    st.header("📦 Gestão de Estoque")
    
    # IDs das Tabelas para referência
    table_id_viva = "leandro-marketplace.DL_Store_Online.tb_estoque"
    table_id_hist = "leandro-marketplace.DL_Store_Online.tb_estoque_historico"
    
    # --- 1. ENTRADA DE PRODUTO ---
    with st.expander("📥 Registrar Entrada de Mercadoria", expanded=True):
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
                st.info(f"📍 Selecionado: **{item_estoque['Produto']}** (SKU: {item_estoque['SKU']})")
                
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

    # --- 2. VISUALIZAÇÃO, GRÁFICO E GESTÃO ---
    st.divider()
    
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
                lucros = {"Shein": l_shein, "Shopee": l_shopee, "Temu": l_temu}
                melhor_canal = max(lucros, key=lucros.get)
                return melhor_canal, lucros[melhor_canal]

            total_investido_estoque = (df_raw['quantidade'] * df_raw['valor_pago']).sum()
            lucro_potencial_total = sum(df_raw.apply(lambda r: recomendar_canal(r['valor_pago'])[1] * r['quantidade'], axis=1))
            quantidade_total_itens = df_raw['quantidade'].sum()

            m1, m2, m3 = st.columns(3)
            with m1: st.metric("💰 Valor em Estoque", f"R$ {total_investido_estoque:,.2f}")
            with m2: st.metric("🚀 Lucro Potencial", f"R$ {lucro_potencial_total:,.2f}")
            with m3: st.metric("📦 Total de Itens", f"{int(quantidade_total_itens)} un")

            # --- GRÁFICO DE EVOLUÇÃO (PADRÃO FINANCEIRO) ---
            st.subheader("📈 Foto do Estoque (Saldo Final do Dia)")
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
                        marker_color='#FFD700', 
                        text=df_diario['saldo_final'], 
                        textposition='outside',
                        textfont=dict(size=12, color='black', family="Arial Black"),
                        cliponaxis=False,
                        width=0.4 
                    ))
                    
                    fig_foto.update_layout(
                        paper_bgcolor='white', 
                        plot_bgcolor='white', 
                        margin=dict(l=10, r=10, t=50, b=50), 
                        xaxis=dict(
                            visible=True,
                            showline=True,
                            linecolor='black',
                            linewidth=1,
                            showgrid=False,
                            showticklabels=True,
                            type='category',
                            tickfont=dict(size=10, color='black', family="Arial"),
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

            # --- TABELA DE GESTÃO POR SKU (FRAGMENTADA) ---
            st.subheader("📋 Gestão de Inventário por SKU")

            @st.fragment
            def tabela_sku_interativa(df_raw):
                df_visual_est = df_raw.groupby(['sku', 'produto']).agg({'quantidade': 'sum', 'valor_pago': 'mean'}).reset_index()
                
                st.markdown("""<div style="display: flex; font-weight: bold; background-color: #f8f9fa; padding: 10px 15px; border: 1px solid #e6e6e6; border-radius: 10px 10px 0 0;"><div style="flex: 2.5;">Produto</div><div style="flex: 1.2;">Melhor Canal</div><div style="flex: 1.2;">Lucro Total</div><div style="flex: 0.8;">Qtd</div><div style="flex: 1.5;">Ajustar (+/-)</div><div style="flex: 0.5;">Ação</div></div>""", unsafe_allow_html=True)

                for idx, r in df_visual_est.iterrows():
                    canal, lucro_un = recomendar_canal(r['valor_pago'])
                    cols = st.columns([2.5, 1.2, 1.2, 0.8, 1.5, 0.5])
                    
                    cols[0].markdown(f"{r['produto']}<br><small><code>{r['sku']}</code></small>", unsafe_allow_html=True)
                    cols[1].markdown(f"**{canal}**")
                    cols[2].write(f"R$ {lucro_un * r['quantidade']:.2f}")
                    cols[3].write(str(int(r['quantidade'])))
                    
                    ajuste = cols[4].number_input("Ajuste", step=1, value=0, key=f"adj_{idx}", label_visibility="collapsed")
                    
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

            # Chama a função fragmentada para exibir a tabela
            tabela_sku_interativa(df_raw)

        else:
            st.info("Estoque vazio no momento.")

    except Exception as e_geral:
        st.error(f"Erro ao carregar dados do estoque: {e_geral}")