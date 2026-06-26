# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import re
import urllib.parse
import json
import os
import io
import base64
import uuid
from datetime import datetime, timedelta
from google.cloud import bigquery
from google.oauth2 import service_account
import plotly.graph_objects as go

# --- CONFIGURAÇÕES DE INICIALIZAÇÃO ---

if 'processando_venda' not in st.session_state:
    st.session_state.processando_venda = False

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

def buscar_anotacoes_bq():
    if client_bq:
        try:
            query = "SELECT * FROM `leandro-marketplace.DL_Store_Online.tb_anotacoes` ORDER BY data_criacao DESC"
            return client_bq.query(query).to_dataframe()
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def inserir_anotacao_bq(texto):
    if client_bq:
        texto_seguro = str(texto).replace("'", "''")
        id_nota = str(uuid.uuid4())
        query = f"""
            INSERT INTO `leandro-marketplace.DL_Store_Online.tb_anotacoes` (id, anotacao, status_concluido, data_criacao)
            VALUES ('{id_nota}', '{texto_seguro}', false, CURRENT_TIMESTAMP())
        """
        client_bq.query(query).result()

def atualizar_status_bq(id_nota, status):
    if client_bq:
        st_sql = str(status).lower()
        query = f"UPDATE `leandro-marketplace.DL_Store_Online.tb_anotacoes` SET status_concluido = {st_sql} WHERE id = '{id_nota}'"
        client_bq.query(query).result()

def excluir_anotacao_bq(id_nota):
    if client_bq:
        query = f"DELETE FROM `leandro-marketplace.DL_Store_Online.tb_anotacoes` WHERE id = '{id_nota}'"
        client_bq.query(query).result()

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
def converter_custo_seguro(valor_raw):
    if valor_raw is None or valor_raw == "": 
        return 0.0
    
    if isinstance(valor_raw, (int, float)):
        return float(valor_raw)
        
    s = str(valor_raw).replace('R$', '').replace(' ', '').strip()
    try:
        if ',' in s and '.' in s:
            if s.find('.') < s.find(','):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except: 
        return 0.0

def calcular_venda_completo(custo_aquisicao, margem_percentual, mkt):
    imposto_tax = 0.06
    margem_alvo = margem_percentual / 100
    custo_embalagem = 1.00
    if mkt == "shein":
        comissao_mkt, taxa_fixa = 0.18, 5.0
        divisor = 1 - (comissao_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_embalagem + taxa_fixa) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comissao_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_embalagem - taxa_fixa
        return preco, lucro
    elif mkt == "shopee":
        def testar_faixa(comis, taxa):
            div = 1 - (comis + imposto_tax + margem_alvo)
            return (custo_aquisicao + custo_embalagem + taxa) / div if div > 0 else 0
        p_venda = testar_faixa(0.20, 4.0)
        if p_venda > 79.99:
            p_venda = testar_faixa(0.14, 16.0)
            if p_venda > 99.99:
                p_venda = testar_faixa(0.14, 20.0)
                if p_venda > 199.99: p_venda = testar_faixa(0.14, 26.0)
        if p_venda <= 79.99: c_final, t_final = 0.20, 4.0
        elif p_venda <= 99.99: c_final, t_final = 0.14, 16.0
        elif p_venda <= 199.99: c_final, t_final = 0.14, 20.0
        else: c_final, t_final = 0.14, 26.0
        lucro = p_venda - (p_venda * c_final) - (p_venda * imposto_tax) - custo_aquisicao - custo_embalagem - t_final
        return p_venda, lucro
    elif mkt == "temu":
        divisor = 1 - (imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_embalagem) / divisor if divisor > 0 else 0
        lucro = preco - (preco * imposto_tax) - custo_aquisicao - custo_embalagem
        return preco, lucro
    elif mkt == "tiktok":
        comissao_mkt, taxa_fixa = 0.22, 4.0
        divisor = 1 - (comissao_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_embalagem + taxa_fixa) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comissao_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_embalagem - taxa_fixa
        return preco, lucro
    return 0, 0

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
        if st.button("✅ Pendências"): 
            st.session_state.pg = "Pendencias"
            st.rerun()
        if st.button("📊 Comparativo de Preços"): 
            st.session_state.pg = "Calculadora"
            st.rerun()
        if st.button("📝 Novo Item na Base"): 
            st.session_state.pg = "Cadastro"
            st.rerun()
        if st.button("💰 Alterar Preços"): 
            st.session_state.pg = "Alterar Preco"
            st.rerun()
        if st.button("📈 Análise de Vendas"): 
            st.session_state.pg = "Análise de Vendas"
            st.rerun()
        if st.button("📦 Gestão de Estoque"): 
            st.session_state.pg = "Gestão de Estoque"
            st.rerun()
            
        if st.button("📉 Dashboard Financeiro"): 
            st.session_state.fin_acesso = False
            st.session_state.pg = "Dashboard"
            st.rerun()
            
        # --- BLOCO DE NOTAS ---
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        st.markdown('<p style="color: #9ca3af; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-bottom: 12px;">Produtividade</p>', unsafe_allow_html=True)
        with st.expander("📋 Bloco de Notas & Pendências", expanded=False):
            nova_nota_sb = st.text_input("Escreva uma nova nota:", key="input_nova_nota_sidebar", placeholder="Digite...")
            if st.button("📌 Adicionar Nota", use_container_width=True):
                if nova_nota_sb.strip() != "":
                    try:
                        inserir_anotacao_bq(nova_nota_sb)
                        st.toast("Nota adicionada com sucesso! 📌")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
                else:
                    st.warning("Digite algo antes de salvar.")
            
            st.markdown('<p style="color: #9ca3af; font-size: 11px; margin: 12px 0 8px 0;">Pendências Ativas</p>', unsafe_allow_html=True)
            
            try:
                df_apoio = buscar_anotacoes_bq()
                if not df_apoio.empty:
                    df_ativas = df_apoio[df_apoio['status_concluido'] == False]
                    
                    if not df_ativas.empty:
                        for idx, row in df_ativas.iterrows():
                            if st.checkbox(row['anotacao'], key=f"sb_chk_{row['id']}"):
                                try:
                                    atualizar_status_bq(row['id'], True)
                                    st.toast("Pendência concluída! 🎉")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e_up:
                                    st.error(f"Erro ao atualizar: {e_up}")
                    else:
                        st.info("Nenhuma nota ativa.")
                else:
                    st.info("Nenhuma nota criada.")
            except Exception as e:
                st.caption(f"Erro ao conectar: {e}")
        
        # --- LOGOUT ---
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        if st.button("🚪 Sair", use_container_width=True):
            st.session_state.logado = False
            st.session_state.fin_acesso = False
            st.session_state.pg = "Início"
            st.rerun()

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
elif st.session_state.pg == "Pendencias":
    st.markdown('<h1>📋 Pendências e Anotações</h1>', unsafe_allow_html=True)
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)
    
    with st.container(border=True):
        col_input, col_btn = st.columns([3, 1])
        with col_input:
            nova_nota = st.text_input("O que precisa ser feito?", placeholder="Ex: atualizar estoque...", key="txt_gcp", label_visibility="collapsed")
        with col_btn:
            st.markdown('<div style="padding-top: 7px;"></div>', unsafe_allow_html=True)
            if st.button("Adicionar", use_container_width=True, type="primary"):
                if nova_nota:
                    inserir_anotacao_bq(nova_nota)
                    st.rerun()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    df_notas = buscar_anotacoes_bq()
    if not df_notas.empty:
        for index, row in df_notas.iterrows():
            c_check, c_texto, c_del = st.columns([0.5, 8.5, 1])
            with c_check:
                check = st.checkbox(" ", value=row['status_concluido'], key=f"check_{row['id']}", label_visibility="collapsed")
                if check != row['status_concluido']:
                    atualizar_status_bq(row['id'], check)
                    st.rerun()
            with c_texto:
                if row['status_concluido']: 
                    st.markdown(f"<span style='text-decoration: line-through; color: #9ca3af;'>{row['anotacao']}</span>", unsafe_allow_html=True)
                else: 
                    st.write(row['anotacao'])
            with c_del:
                if st.button("❌", key=f"del_{row['id']}", help="Deletar"):
                    excluir_anotacao_bq(row['id'])
                    st.rerun()
    else:
        st.info("Nenhuma pendência no momento.")

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
elif st.session_state.pg == "Análise de Vendas":
    st.markdown('<h1>📈 Análise de Vendas</h1>', unsafe_allow_html=True)
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)
    
    if not df_base_completa.empty:
        df_rel = df_base_completa.copy()
        df_rel['Custo_num'] = df_rel['Custo_aquisicao'].apply(converter_custo_seguro)
        
        st.markdown('<h3>🏆 Inteligência de Mercado (Melhor Margem)</h3>', unsafe_allow_html=True)
        m_alvo = st.slider("Margem para Análise (%)", 1.0, 50.0, 2.0)
        rank_data = []
        for _, r in df_rel.iterrows():
            _, l1 = calcular_venda_completo(r['Custo_num'], m_alvo, "shein")
            _, l2 = calcular_venda_completo(r['Custo_num'], m_alvo, "shopee")
            _, l3 = calcular_venda_completo(r['Custo_num'], m_alvo, "temu")
            _, l4 = calcular_venda_completo(r['Custo_num'], m_alvo, "tiktok")
            max_l = max(l1, l2, l3, l4)
            rank_data.append({"Produto": r['Produto'], "SKU": r['SKU'], "Lucro Estimado": round(max_l, 2)})
        
        df_rank = pd.DataFrame(rank_data).sort_values(by="Lucro Estimado", ascending=False)
        st.dataframe(df_rank, use_container_width=True, hide_index=True)
        
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
    else:
        st.info("Nenhum produto cadastrado ainda.")

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
                
                errors = client_bq.insert_rows_json(table_id_produtos, lote_bq)
                
                if not errors:
                    st.success(f"✅ Sucesso! {len(lote_bq)} registros salvos.")
                    st.session_state.cont_var = 0
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Erro BigQuery: {errors}")
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

    with st.expander("➕ Adicionar Item para Alteração", expanded=True):
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
    st.markdown('<h1>📊 Dashboard Financeiro</h1>', unsafe_allow_html=True)
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)
    
    if 'processando_venda' not in st.session_state:
        st.session_state.processando_venda = False

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
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #dbeafe 0%, #e0f2fe 100%); border: 1px solid #7dd3fc; border-radius: 12px; padding: 16px; margin-bottom: 20px;">
                <p style="margin: 0; color: #0369a1;"><strong>✓</strong> {v_nome_final} | <code>{v_sku_final}</code> | Base: <strong>R$ {v_custo_base:.2f}</strong></p>
                </div>
                """, unsafe_allow_html=True)
                
                c_v1, c_v2, c_v3 = st.columns(3)
                with c_v1:
                    mkt_venda = st.selectbox("Canal de Venda", ["shein", "shopee", "temu", "tiktok"])
                    v_qtd = st.number_input("Qtd Vendida", min_value=1, value=1)
                with c_v2:
                    v_preco_venda = st.number_input("Preço de Venda Praticado (R$)", min_value=0.0, step=0.01, value=0.0)
                    imp, c_fixo = 0.06, 1.00
                    if mkt_venda == "shein": com, tax = 0.18, 5.0
                    elif mkt_venda == "shopee": com, tax = 0.20, (4.0 if v_custo_base < 50 else 20.0)
                    elif mkt_venda == "tiktok": com, tax = 0.22, 4.0
                    else: com, tax = 0.0, 0.0
                    lucro_un_calc = v_preco_venda - (v_preco_venda * com) - (v_preco_venda * imp) - v_custo_base - c_fixo - tax
                    v_margem_auto = (lucro_un_calc / v_preco_venda * 100) if v_preco_venda > 0 else 0.0
                    st.markdown(f"<p style='text-align: center; color: #059669; font-size: 14px; font-weight: 600; margin-top: 24px;'>📈 Margem: <strong>{v_margem_auto:.1f}%</strong></p>", unsafe_allow_html=True)
                with c_v3:
                    v_data = st.date_input("Data da Venda", value=(datetime.utcnow() - timedelta(hours=3)))
                    lucro_total_dinamico = lucro_un_calc * v_qtd
                    st.metric("Lucro Total", f"R$ {lucro_total_dinamico:.2f}")

                if not st.session_state.processando_venda:
                    if st.button("🚀 Confirmar e Registrar Venda", type="primary", use_container_width=True):
                        st.session_state.processando_venda = True
                        try:
                            table_id = "leandro-marketplace.DL_Store_Online.tb_vendas_realizadas"
                            v_data_formatada = v_data.strftime("%Y-%m-%d") 
                            row = [{
                                "produto": str(v_nome_final), "sku": str(v_sku_final), 
                                "preco_venda": float(v_preco_venda), "quantidade": int(v_qtd), 
                                "data": v_data_formatada, "lucro_total": float(round(lucro_total_dinamico, 2)),
                                "mkt_venda": str(mkt_venda)
                            }]
                            errors = client_bq.insert_rows_json(table_id, row)
                            if not errors:
                                st.success("Venda registrada!"); st.cache_data.clear(); st.session_state.processando_venda = False; st.rerun()
                            else:
                                st.error(f"Erro BQ: {errors}"); st.session_state.processando_venda = False
                        except Exception as e:
                            st.error(f"Erro: {e}"); st.session_state.processando_venda = False

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    try:
        query = "SELECT * FROM `leandro-marketplace.DL_Store_Online.tb_vendas_realizadas` ORDER BY data DESC"
        df_vendas = client_bq.query(query).to_dataframe()

        if not df_vendas.empty:
            df_vendas.columns = ['Produto', 'SKU', 'Preço Venda', 'Quantidade', 'Data', 'Lucro Total', 'Marketplace']
            df_vendas['Preço Venda'] = pd.to_numeric(df_vendas['Preço Venda'])
            df_vendas['Lucro Total'] = pd.to_numeric(df_vendas['Lucro Total'])
            df_vendas['Quantidade'] = pd.to_numeric(df_vendas['Quantidade'])
            df_vendas['Faturamento'] = df_vendas['Preço Venda'] * df_vendas['Quantidade']
            df_vendas['Data'] = pd.to_datetime(df_vendas['Data'])
            
            hoje = datetime.utcnow() - timedelta(hours=3)
            inicio_mes_atual = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

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
            df_linha = df_plot[~df_plot['Data_Label'].isin(['Mês Atual']) & df_plot['Data_Label'].str.contains('/')].copy()

            df_vendas['Mes_Ref'] = df_vendas['Data'].dt.strftime('%m/%Y')
            opcoes_meses = sorted(df_vendas['Mes_Ref'].unique(), reverse=True)
            
            col_f, _ = st.columns([2, 4])
            with col_f:
                mes_selecionado = st.selectbox("📅 Selecionar Mês para Detalhamento:", opcoes_meses)

            df_detalhe = df_vendas[df_vendas['Mes_Ref'] == mes_selecionado].copy()
            
            meses_fechados = df_vendas[df_vendas['Mes_Ref'] != mes_selecionado].copy()
            barras_hist = pd.DataFrame()
            if not meses_fechados.empty:
                meses_map = {1:'Jan', 2:'Fev', 3:'Mar', 4:'Abr', 5:'Mai', 6:'Jun', 7:'Jul', 8:'Ago', 9:'Set', 10:'Out', 11:'Nov', 12:'Dez'}
                meses_fechados['Label'] = meses_fechados['Data'].dt.month.map(meses_map) + "/" + meses_fechados['Data'].dt.year.astype(str).str[-2:]
                barras_hist = meses_fechados.groupby('Label').agg({'Faturamento':'sum', 'Lucro Total':'sum', 'Quantidade':'sum'}).reset_index()
                barras_hist['Outros Custos'] = barras_hist['Faturamento'] - barras_hist['Lucro Total']
                barras_hist.rename(columns={'Label': 'Data_Label'}, inplace=True)

            df_plot_mes = pd.DataFrame()
            if not df_detalhe.empty:
                total_mes = pd.DataFrame([{
                    'Data_Label': f'Total {mes_selecionado}', 
                    'Faturamento': df_detalhe['Faturamento'].sum(), 
                    'Lucro Total': df_detalhe['Lucro Total'].sum(), 
                    'Quantidade': df_detalhe['Quantidade'].sum(), 
                    'Outros Custos': df_detalhe['Faturamento'].sum() - df_detalhe['Lucro Total'].sum()
                }])
                
                df_dias = df_detalhe.groupby('Data').agg({'Faturamento':'sum', 'Lucro Total':'sum', 'Quantidade':'sum'}).reset_index()
                df_dias['Outros Custos'] = df_dias['Faturamento'] - df_dias['Lucro Total']
                df_dias['Data_Label'] = df_dias['Data'].dt.strftime('%d/%m')
                df_plot_mes = pd.concat([total_mes, df_dias], ignore_index=True)

            df_plot = pd.concat([barras_hist, df_plot_mes], ignore_index=True)
            df_linha = df_plot[~df_plot['Data_Label'].str.contains('Total')].copy()

            st.markdown('<h3>📈 Desempenho Mensal e Diário</h3>', unsafe_allow_html=True)
            with st.container():
                st.markdown('<div class="plot-container">', unsafe_allow_html=True)
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                
                fig.add_trace(go.Bar(
                    x=df_plot['Data_Label'], 
                    y=df_plot['Outros Custos'], 
                    name='Outros Custos', 
                    marker_color='#FEF3C7', 
                    hovertemplate='R$ %{y:,.2f}<extra></extra>'
                ), secondary_y=False)
                
                fig.add_trace(go.Bar(
                    x=df_plot['Data_Label'], 
                    y=df_plot['Lucro Total'], 
                    name='Lucro Líquido', 
                    marker_color='#FBBF24', 
                    hovertemplate='R$ %{y:,.2f}<extra></extra>', 
                    text=df_plot['Lucro Total'].apply(lambda x: f'R$ {x:,.2f}'), 
                    textposition='outside', 
                    textfont=dict(size=12, color='#92400E', family="Arial")
                ), secondary_y=False)
                
                fig.add_trace(go.Scatter(
                    x=df_linha['Data_Label'], 
                    y=df_linha['Quantidade'], 
                    name='Qtd Vendas', 
                    mode='lines+markers+text',
                    line=dict(color='#6366F1', width=3), 
                    marker=dict(size=8, color='#6366F1'),
                    text=df_linha['Quantidade'], 
                    textposition="top center",
                    textfont=dict(size=11, color='#6366F1', family="Arial"),
                    hovertemplate='Vendas: %{y}<extra></extra>'
                ), secondary_y=True)

                fig.update_layout(
                    barmode='stack', 
                    paper_bgcolor='white', 
                    plot_bgcolor='white', 
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=True, range=[0, df_plot['Faturamento'].max() * 2.2]), 
                    yaxis2=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=True, range=[df_plot['Quantidade'].max() * -1.5, df_plot['Quantidade'].max() * 1.2]),
                    xaxis=dict(title="Competência / Dias", showgrid=False, showline=True, linecolor='#E5E7EB', tickfont=dict(color='#6B7280', size=12)), 
                    legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5, font=dict(color="#374151", size=13)), 
                    margin=dict(l=10, r=10, t=80, b=60), 
                    hovermode='x unified'
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                st.markdown('</div>', unsafe_allow_html=True)

            hoje = datetime.utcnow() - timedelta(hours=3)
            inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            df_mes_atual = df_vendas[df_vendas['Data'] >= inicio_mes]

            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
            st.markdown('<h3>📊 Totais Acumulados</h3>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento Total", f"R$ {df_vendas['Faturamento'].sum():.2f}")
            c2.metric("Lucro Líquido Geral", f"R$ {df_vendas['Lucro Total'].sum():.2f}")
            c3.metric("Total Itens Vendidos", int(df_vendas['Quantidade'].sum()))

            st.markdown('<h3>📅 Performance do Mês Atual</h3>', unsafe_allow_html=True)
            m1, m2, m3 = st.columns(3)
            
            fat_mes = df_mes_atual['Faturamento'].sum()
            lucro_mes = df_mes_atual['Lucro Total'].sum()
            qtd_mes = int(df_mes_atual['Quantidade'].sum())

            m1.metric("Faturamento Mensal", f"R$ {fat_mes:,.2f}")
            m2.metric("Lucro Mensal", f"R$ {lucro_mes:,.2f}")
            m3.metric("Vendas no Mês", qtd_mes)

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
                paper_bgcolor='white', 
                plot_bgcolor='white',  
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
            
            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
            st.markdown('<h3>📋 Histórico de Vendas</h3>', unsafe_allow_html=True)
            
            st.markdown("""
                <div style="display: flex; font-weight: 600; background-color: #F3F4F6; padding: 12px 16px; border: 1px solid #E5E7EB; border-radius: 10px 10px 0 0; color: #374151; font-size: 13px;">
                    <div style="flex: 3;">Produto</div>
                    <div style="flex: 2;">SKU</div>
                    <div style="flex: 1;">Qtd</div>
                    <div style="flex: 2;">Data</div>
                    <div style="flex: 2;">Lucro</div>
                    <div style="flex: 1;">Ação</div>
                </div>
            """, unsafe_allow_html=True)
            
            with st.container(height=500):
                for idx, row in df_vendas.iterrows():
                    cols = st.columns([3, 2, 1, 2, 2, 1])
                    cols[0].write(row['Produto'])
                    cols[1].write(f"`{row['SKU']}`")
                    cols[2].write(str(int(row['Quantidade'])))
                    cols[3].write(row['Data'].strftime('%d/%m/%Y'))
                    cols[4].write(f"R$ {row['Lucro Total']:.2f}")
                    
                    if cols[5].button("❌", key=f"del_{idx}"):
                        client_bq.query(f"DELETE FROM `leandro-marketplace.DL_Store_Online.tb_vendas_realizadas` WHERE sku = '{row['SKU']}' AND data = '{row['Data'].strftime('%Y-%m-%d')}' AND lucro_total = {row['Lucro Total']}").result()
                        st.cache_data.clear()
                        st.rerun()
            
        else:
            st.info("Nenhuma venda registrada ainda.")
    except Exception as e:
        st.error(f"Erro no Dashboard: {e}")

# --- GESTÃO DE ESTOQUE ---
elif st.session_state.pg == "Gestão de Estoque":
    st.markdown('<h1>📦 Gestão de Estoque</h1>', unsafe_allow_html=True)
    st.markdown('<div class="section-header"></div>', unsafe_allow_html=True)
    
    table_id_viva = "leandro-marketplace.DL_Store_Online.tb_estoque"
    table_id_hist = "leandro-marketplace.DL_Store_Online.tb_estoque_historico"
    
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
                l_tiktok = p_sugerido - (p_sugerido * 0.22) - (p_sugerido * imp) - custo - c_fixo - 4.0
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