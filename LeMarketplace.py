import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import urllib.parse
import json
import os
import io
import base64
from datetime import datetime
import plotly.graph_objects as go # Importando Plotly

# --- CONFIGURAÇÕES DE PÁGINA ---
st.set_page_config(page_title="Leandro Marketplace", layout="wide", initial_sidebar_state="expanded")

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

# --- CONEXÃO COM GOOGLE SHEETS ---
@st.cache_resource(ttl=600)
def conectar_google_sheets():
    from google.oauth2 import service_account
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    sheet_id = "1sWBnF83-z6yrEKxWoJ1IulHNkwSEU6Si6WzNuLxqW44"
    info = None

    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
            if 'private_key' in info and "BEGIN" not in info['private_key']:
                decoded_key = base64.b64decode(info['private_key']).decode("utf-8")
                info['private_key'] = decoded_key
            elif 'private_key' in info:
                info['private_key'] = info['private_key'].replace('\\n', '\n').strip()
    except:
        info = None

    if info is None:
        path_json = r'C:\Users\Junior\Desktop\CodigosPython2\.streamlit\secrets.toml.json'
        if os.path.exists(path_json):
            with open(path_json, 'r', encoding='utf-8') as f:
                info = json.load(f)

    if info:
        try:
            creds = service_account.Credentials.from_service_account_info(info, scopes=scope)
            client = gspread.authorize(creds)
            return client.open_by_key(sheet_id)
        except Exception as e:
            st.error(f"Erro na autenticação final: {e}")
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
    imposto_tax = 0.06 
    margem_alvo = margem_percentual / 100
    custo_fixo_invisivel = 1.00 
    
    if mkt == "shein":
        comissao_mkt, taxa_extra = 0.18, 5.0
        divisor = 1 - (comissao_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_fixo_invisivel + taxa_extra) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comissao_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_fixo_invisivel - taxa_extra
        return preco, lucro
    
    elif mkt == "shopee":
        taxa_plat = 4.0 if custo_aquisicao < 50 else 20.0 
        comis_mkt = 0.20 if custo_aquisicao < 50 else 0.14 
        divisor = 1 - (comis_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_fixo_invisivel + taxa_plat) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comis_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_fixo_invisivel - taxa_plat
        return preco, lucro

    elif mkt == "temu":
        divisor = 1 - (imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_fixo_invisivel) / divisor if divisor > 0 else 0
        lucro = preco - (preco * imposto_tax) - custo_aquisicao - custo_fixo_invisivel
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
        if st.button("📈 Análise de Vendas"): st.session_state.pg = "Análise de Vendas"
        if st.button("📉 Dashboard Financeiro"): st.session_state.pg = "Dashboard"
        st.write("")
        if st.button("🚪 Sair"):
            st.session_state.logado = False
            st.rerun()

planilha = conectar_google_sheets()

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

# --- ÁREA RESTRITA ---
if st.session_state.logado and planilha:
    
    lista_base_validacao = []
    for aba_nome in ["shein", "shopee", "temu"]:
        try:
            dados_aba_val = planilha.worksheet(aba_nome).get_all_values()
            if dados_aba_val:
                df_val = pd.DataFrame(dados_aba_val[1:], columns=dados_aba_val[0])
                lista_base_validacao.append(df_val)
        except: pass
    df_base_completa = pd.concat(lista_base_validacao).drop_duplicates(subset=['SKU']) if lista_base_validacao else pd.DataFrame()

    if st.session_state.pg == "Calculadora":
        st.header("📊 Comparativo de Preços")
        if not df_base_completa.empty:
            df_geral = df_base_completa.copy()
            df_geral['Custo_aquisicao_num'] = df_geral['Custo_aquisicao'].apply(converter_custo_seguro)
            
            col_sel1, col_sel2 = st.columns(2)
            with col_sel1:
                prod_sel = st.selectbox("Pesquisar Produto", df_geral['Produto'].unique(), index=None, placeholder="Digite o produto...")
            with col_sel2:
                sku_sel = st.selectbox("Pesquisar SKU", df_geral['SKU'].unique(), index=None, placeholder="Digite o SKU...")
            
            final_item = None
            if sku_sel: final_item = df_geral[df_geral['SKU'] == sku_sel].iloc[0]
            elif prod_sel: final_item = df_geral[df_geral['Produto'] == prod_sel].iloc[0]

            if final_item is not None:
                custo_aq = final_item['Custo_aquisicao_num']
                st.info(f"Selecionado: {final_item['Produto']} | SKU: {final_item['SKU']}")
                margem_input = st.number_input("Margem de Lucro Desejada (%)", min_value=1.0, value=2.0, step=1.0)
                p_shein, l_shein = calcular_venda_completo(custo_aq, margem_input, "shein")
                p_shopee, l_shopee = calcular_venda_completo(custo_aq, margem_input, "shopee")
                p_temu, l_temu = calcular_venda_completo(custo_aq, margem_input, "temu")
                st.divider()
                st.metric("Custo de Aquisição Base", f"R$ {custo_aq:.2f}")
                res = {"Canal": ["SHEIN", "SHOPEE", "TEMU"], "Preço Sugerido": [f"R$ {p_shein:.2f}", f"R$ {p_shopee:.2f}", f"R$ {p_temu:.2f}"], "Lucro Líquido Real": [f"R$ {l_shein:.2f}", f"R$ {l_shopee:.2f}", f"R$ {l_temu:.2f}"]}
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

    elif st.session_state.pg == "Cadastro":
        st.header("📝 Novo Item na Base")
        with st.form("cad_final"):
            m = st.selectbox("Marketplace", ["shein", "shopee", "temu", "todos"])
            n = st.text_input("Nome Completo do Produto")
            s = st.text_input("SKU / Referência Interna")
            c = st.number_input("Custo Unitário (R$)", min_value=0.01, step=0.01)
            if st.form_submit_button("Salvar na Planilha", type="primary"):
                if n and s:
                    valor_formatado = str(c).replace('.', ',')
                    if m == "todos":
                        for aba in ["shein", "shopee", "temu"]:
                            planilha.worksheet(aba).append_row([n, s, valor_formatado])
                        st.success(f"Produto '{n}' salvo em todas as abas!")
                    else:
                        planilha.worksheet(m).append_row([n, s, valor_formatado])
                        st.success(f"Produto '{n}' salvo na aba {m}!")
                else: st.error("Preencha Nome e SKU.")

    elif st.session_state.pg == "Dashboard":
        st.header("📊 Dashboard Financeiro")
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
                    st.success(f"✅ Item: **{v_nome_final}** | SKU: **{v_sku_final}** | Custo Base: R$ {v_custo_base:.2f}")

                    c_v1, c_v2, c_v3 = st.columns(3)
                    with c_v1:
                        mkt_venda = st.selectbox("Canal de Venda", ["shein", "shopee", "temu"])
                        v_qtd = st.number_input("Qtd Vendida", min_value=1, value=1)
                    with c_v2:
                        v_preco_venda = st.number_input("Preço de Venda Praticado (R$)", min_value=0.01, step=0.01)
                        v_margem_manual = st.number_input("Margem de Lucro Obtida (%)", min_value=0.1, value=2.0, step=0.1)
                    with c_v3:
                        v_data = st.date_input("Data da Venda", value=datetime.now())
                        lucro_un_calc = v_preco_venda * (v_margem_manual / 100)
                        lucro_total_dinamico = lucro_un_calc * v_qtd
                        st.metric("Lucro Estimado Total", f"R$ {lucro_total_dinamico:.2f}")

                    if st.button("🚀 Confirmar e Registrar Venda", type="primary"):
                        try:
                            aba_vendas = planilha.worksheet("vendas_realizadas")
                            data_str = v_data.strftime("%d/%m/%Y")
                            aba_vendas.append_row([
                                v_nome_final, v_sku_final, str(v_preco_venda).replace('.',','), 
                                int(v_qtd), data_str, str(round(lucro_total_dinamico,2)).replace('.',',')
                            ])
                            st.cache_resource.clear()
                            st.success(f"Venda registrada!")
                            st.rerun()
                        except Exception as e: st.error(f"Erro: {e}")
            else: st.warning("Nenhum produto cadastrado.")

        # --- SEÇÃO DO GRÁFICO ---
        st.divider()
        try:
            aba_inst_vendas = planilha.worksheet("vendas_realizadas")
            dados_vendas = aba_inst_vendas.get_all_values()
            if len(dados_vendas) > 1:
                df_vendas = pd.DataFrame(dados_vendas[1:], columns=dados_vendas[0])
                df_vendas['Preço Venda'] = df_vendas['Preço Venda'].apply(converter_custo_seguro)
                df_vendas['Lucro Total'] = df_vendas['Lucro Total'].apply(converter_custo_seguro)
                df_vendas['Quantidade'] = pd.to_numeric(df_vendas['Quantidade'])
                df_vendas['Faturamento'] = df_vendas['Preço Venda'] * df_vendas['Quantidade']
                df_vendas['Data'] = pd.to_datetime(df_vendas['Data'], dayfirst=True)
                
                df_diario = df_vendas.groupby('Data').agg({'Faturamento': 'sum', 'Lucro Total': 'sum'}).reset_index()
                df_diario['Outros Custos'] = df_diario['Faturamento'] - df_diario['Lucro Total']
                df_diario = df_diario.sort_values(by='Data')
                df_diario['Data_Label'] = df_diario['Data'].dt.strftime('%d/%m')

                st.subheader("📈 Faturamento vs Lucro Líquido (Por Dia)")

                # Container com Borda Real para o Gráfico
                with st.container():
                    st.markdown('<div class="plot-container">', unsafe_allow_html=True)
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=df_diario['Data_Label'], y=df_diario['Outros Custos'], name='Outros Custos',
                        marker_color='#FFF9E6', hovertemplate='<b>Outros Custos</b><br>Data: %{x}<br>Valor: R$ %{y:,.2f}<extra></extra>'
                    ))
                    fig.add_trace(go.Bar(
                        x=df_diario['Data_Label'], y=df_diario['Lucro Total'], name='Lucro Líquido',
                        marker_color='#FFD700', hovertemplate='<b>Lucro Líquido</b><br>Data: %{x}<br>Valor: R$ %{y:,.2f}<extra></extra>',
                        text=df_diario['Lucro Total'].apply(lambda x: f'R$ {x:,.2f}'), textposition='outside'
                    ))
                    fig.update_layout(
                        barmode='stack', paper_bgcolor='white', plot_bgcolor='white',
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
                        xaxis=dict(showgrid=False, zeroline=False),
                        margin=dict(l=10, r=10, t=40, b=10),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                        font=dict(color="#31333F"), hovermode='x'
                    )
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                    st.markdown('</div>', unsafe_allow_html=True)

                # Métricas e Histórico
                st.write("")
                c1, c2, c3 = st.columns(3)
                c1.metric("Faturamento Total", f"R$ {df_vendas['Faturamento'].sum():.2f}")
                margem_geral = (df_vendas['Lucro Total'].sum()/df_vendas['Faturamento'].sum()*100) if df_vendas['Faturamento'].sum() > 0 else 0
                c2.metric("Lucro Líquido Total", f"R$ {df_vendas['Lucro Total'].sum():.2f}", delta=f"{margem_geral:.1f}% margem")
                c3.metric("Itens Vendidos", int(df_vendas['Quantidade'].sum()))

                st.divider()
                st.subheader("📋 Histórico e Gerenciamento")
                
                # Cabeçalho Fixo (Fora do Scroll para ficar visível)
                st.markdown("""
                    <div style="display: flex; font-weight: bold; background-color: #f8f9fa; padding: 10px 15px; border: 1px solid #e6e6e6; border-bottom: 2px solid #e6e6e6; border-radius: 10px 10px 0 0;">
                        <div style="flex: 3;">Produto</div>
                        <div style="flex: 2;">SKU</div>
                        <div style="flex: 1;">Qtd</div>
                        <div style="flex: 2;">Data</div>
                        <div style="flex: 2;">Lucro</div>
                        <div style="flex: 1;">Ação</div>
                    </div>
                """, unsafe_allow_html=True)

                # --- TABELA DE HISTÓRICO COM SCROLL E LATERAIS ---
                st.markdown('<div class="historico-scroll-container">', unsafe_allow_html=True)
                
                df_exibicao = df_vendas.copy().reset_index()
                for idx, row in df_exibicao[::-1].iterrows():
                    st.markdown(f'<div class="linha-historico">', unsafe_allow_html=True)
                    cols = st.columns([3, 2, 1, 2, 2, 1])
                    cols[0].write(row['Produto'])
                    cols[1].write(f"`{row['SKU']}`")
                    cols[2].write(str(row['Quantidade']))
                    cols[3].write(row['Data'].strftime('%d/%m/%Y'))
                    cols[4].write(f"R$ {row['Lucro Total']:.2f}")
                    if cols[5].button("❌", key=f"del_{idx}"):
                        aba_inst_vendas.delete_rows(row['index'] + 2)
                        st.success("Venda removida!")
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
            else: st.info("Sem vendas registradas.")
        except Exception as e: st.warning(f"Erro ao carregar dados: {e}")