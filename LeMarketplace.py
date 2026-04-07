import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import urllib.parse
import os

# --- CONFIGURAÇÕES DE PÁGINA ---
st.set_page_config(page_title="Leandro Marketplace", layout="wide", initial_sidebar_state="expanded")

# --- ESTILIZAÇÃO CUSTOMIZADA (PADRONIZAÇÃO TOTAL DA SIDEBAR E AJUSTE DO BANNER) ---
st.markdown("""
    <style>
    .stApp { background-color: white !important; }
    [data-testid="stSidebar"] { background-color: #f8f9fa !important; border-right: 1px solid #e6e6e6; }
    h1, h2, h3, p, span, label, .stMarkdown { color: #31333F !important; }
    
    /* FORÇAR LARGURA IGUAL EM TODOS OS BOTÕES DA SIDEBAR */
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

    /* AJUSTE DO BANNER (ALTURA AUTOMÁTICA CONFORME SOLICITADO) */
    [data-testid="stImage"] img {
        height: auto; 
        object-fit: contain; 
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXÃO COM GOOGLE SHEETS ---
@st.cache_resource
def conectar_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # Tenta carregar dos Secrets (Streamlit Cloud) para evitar erro de Padding
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            # Garante que as quebras de linha da private_key sejam lidas corretamente
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            # Caminho local para desenvolvimento
            path_json = r'C:\Users\Junior\Desktop\CodigosPython2\leandro-marketplace-db68edb58be7.json'
            creds = ServiceAccountCredentials.from_json_keyfile_name(path_json, scope)
            
        client = gspread.authorize(creds)
        sheet_id = "1sWBnF83-z6yrEKxWoJ1IulHNkwSEU6Si6WzNuLxqW44"
        return client.open_by_key(sheet_id)
    except Exception as e:
        st.error(f"Erro na conexão com o Google Sheets: {e}")
        return None

# --- FUNÇÃO DE CONVERSÃO DE MOEDA ---
def converter_custo_seguro(valor_raw):
    if not valor_raw or valor_raw == "": return 0.0
    s = str(valor_raw).replace('R$', '').replace(' ', '').strip()
    if ',' not in s and '.' not in s:
        try:
            val = float(s)
            return val / 100 if val > 1000 else val
        except: return 0.0
    if ',' in s:
        if '.' in s: s = s.replace('.', '')
        s = s.replace(',', '.')
    try: return float(s)
    except: return 0.0

# --- MOTOR DE CÁLCULO ---
def calcular_venda_completo(custo_aquisicao, margem_percentual, mkt):
    imposto_tax = 0.06 # Imposto fixo de 6%
    margem_alvo = margem_percentual / 100
    custo_fixo_invisivel = 1.00 # Custo fixo operacional
    
    if mkt == "shein":
        comissao_mkt, taxa_extra = 0.18, 5.0 # Comissão 18% + Taxa Extra R$ 5,00
        divisor = 1 - (comissao_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_fixo_invisivel + taxa_extra) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comissao_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_fixo_invisivel - taxa_extra
        return preco, lucro
    
    elif mkt == "shopee":
        taxa_plat = 4.0 if custo_aquisicao < 50 else 20.0 
        comis_mkt = 0.20 if custo_aquisicao < 50 else 0.14 # Comissão varia
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

# --- SIDEBAR (BARRA LATERAL) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3081/3081559.png", width=80)
    st.title("D.L Online Store")
    if st.button("🏠 Início"): st.session_state.pg = "Início"
    if st.button("👥 Quem Somos"): st.session_state.pg = "Quem Somos"
    if st.button("🛠️ Serviços"): st.session_state.pg = "Serviços"
    if st.button("✉️ Contato"): st.session_state.pg = "Contato"
    st.divider()
    
    # Lógica de Login
    if not st.session_state.logado:
        st.subheader("🔐 Área Logada - Vendedor")
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
        st.subheader(f"👋 Olá, {st.session_state.logado if isinstance(st.session_state.logado, str) else 'Admin'}")
        if st.button("📊 Comparativo de Preços"): st.session_state.pg = "Calculadora"
        if st.button("📝 Novo Item na Base"): st.session_state.pg = "Cadastro"
        if st.button("📈 Relatório de Vendas"): st.session_state.pg = "Relatórios"
        st.write("")
        if st.button("🚪 Sair"):
            st.session_state.logado = False
            st.rerun()

# --- CONEXÃO COM A PLANILHA ---
planilha = conectar_google_sheets()

# --- CONTEÚDO PÚBLICO (SEM LOGIN) ---
if st.session_state.pg == "Início":
    # Lógica para carregar imagem local ou na nuvem sem erro
    banner_path = r"C:\Users\Junior\Desktop\CodigosPython2\banner_inicio.jpg"
    if os.path.exists(banner_path):
        st.image(banner_path, use_container_width=True)
    else:
        # Se não achar o caminho C:, tenta carregar o arquivo direto da pasta do projeto
        st.image("banner_inicio.jpg", use_container_width=True)
    
    st.markdown("<h1 style='text-align: center;'>Bem-vindo à D.L Online Store</h1>", unsafe_allow_html=True)
    st.write("")
    
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
    st.write("Especialistas em gestão de e-commerce e atendimento ao cliente, focados em trazer a melhor experiência de compra.")

elif st.session_state.pg == "Serviços":
    st.header("🛠️ Nossos Serviços")
    st.write("Venda de Produtos em diversos nichos, Logística eficiente e garantia de atendimento humanizado através do nossos Marketplaces parceiros (Shein, Shopee, Temu).")

elif st.session_state.pg == "Contato":
    st.header("✉️ Central de Atendimento")
    
    whatsapp_url = "https://wa.me/5511960501826"
    st.markdown(f"""
        <a href="{whatsapp_url}" target="_blank" style="text-decoration: none;">
            <div style="background-color: #25D366; color: white; padding: 15px; border-radius: 10px; display: inline-block; font-weight: bold; font-size: 18px;">
                <img src="https://cdn-icons-png.flaticon.com/512/733/733585.png" width="25" style="vertical-align: middle; margin-right: 10px;">
                Falar no WhatsApp: (11) 96050-1826
            </div>
        </a>
    """, unsafe_allow_html=True)
    
    st.divider()
    st.subheader("Formulário de Suporte / Sugestão")
    st.write("Para outras dúvidas, e-mails comerciais ou feedback, use o formulário abaixo que gera um e-mail pronto.")
    
    with st.form("form_contato"):
        nome = st.text_input("Seu Nome")
        produto = st.text_input("Produto Adquirido")
        tipo = st.selectbox("Assunto", ["Elogio", "Sugestão", "Reclamação", "Dúvida"])
        mensagem = st.text_area("Sua Mensagem")
        
        enviar = st.form_submit_button("Gerar E-mail de Contato", type="primary")
        
        if enviar:
            if nome and mensagem:
                email_destino = "vendas.dlonlinestore@gmail.com"
                assunto = f"{tipo}: {produto} - {nome}"
                corpo = f"Nome: {nome}\nProduto: {produto}\n\nMensagem:\n{mensagem}"
                
                assunto_enc = urllib.parse.quote(assunto)
                corpo_enc = urllib.parse.quote(corpo)
                mailto_link = f"mailto:{email_destino}?subject={assunto_enc}&body={corpo_enc}"
                
                st.success("Tudo pronto! Clique no botão abaixo para abrir seu aplicativo de e-mail:")
                st.markdown(f"""<a href="{mailto_link}" style="background-color: #007bff; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none;">📧 Abrir E-mail</a>""", unsafe_allow_html=True)
            else:
                st.error("Por favor, preencha pelo menos o Nome e a Mensagem.")

# --- ÁREA RESTRITA (LOGADA) ---
if st.session_state.logado and planilha:
    
    if st.session_state.pg == "Calculadora":
        st.header("📊 Comparativo de Preços (Unitário)")
        
        lista_dfs = []
        for a in ["shein", "shopee", "temu"]:
            try:
                d = pd.DataFrame(planilha.worksheet(a).get_all_records())
                if not d.empty: 
                    lista_dfs.append(d[['Produto', 'Custo_aquisicao']])
            except: pass
        
        if lista_dfs:
            df_geral = pd.concat(lista_dfs).drop_duplicates(subset=['Produto'])
            prod_sel = st.selectbox("Selecione ou Digite o Produto", df_geral['Produto'].unique(), index=None, placeholder="Digite o nome do produto...")
            
            if prod_sel:
                row = df_geral[df_geral['Produto'] == prod_sel].iloc[0]
                custo_aq = converter_custo_seguro(row['Custo_aquisicao'])
                margem_input = st.number_input("Margem de Lucro Desejada (%)", min_value=1.0, value=2.0, step=1.0)
                
                p_shein, l_shein = calcular_venda_completo(custo_aq, margem_input, "shein")
                p_shopee, l_shopee = calcular_venda_completo(custo_aq, margem_input, "shopee")
                p_temu, l_temu = calcular_venda_completo(custo_aq, margem_input, "temu")
                
                st.divider()
                st.subheader(f"Análise de Preços Sugeridos: {prod_sel}")
                st.metric("Custo de Aquisição Base", f"R$ {custo_aq:.2f}")
                
                res = {
                    "Canal": ["SHEIN", "SHOPEE", "TEMU"],
                    "Custo Unitário": [f"R$ {custo_aq:.2f}", f"R$ {custo_aq:.2f}", f"R$ {custo_aq:.2f}"],
                    "Preço Sugerido": [f"R$ {p_shein:.2f}", f"R$ {p_shopee:.2f}", f"R$ {p_temu:.2f}"],
                    "Lucro Líquido Real": [f"R$ {l_shein:.2f}", f"R$ {l_shopee:.2f}", f"R$ {l_temu:.2f}"]
                }
                st.table(pd.DataFrame(res))

    elif st.session_state.pg == "Relatórios":
        st.header("📈 Relatório de Vendas")
        lista_rel = []
        for a in ["shein", "shopee", "temu"]:
            try: 
                d_aba = pd.DataFrame(planilha.worksheet(a).get_all_records())
                if not d_aba.empty: 
                    lista_rel.append(d_aba[['Produto', 'Custo_aquisicao']])
            except: pass
        
        if lista_rel:
            df_rel = pd.concat(lista_rel).drop_duplicates(subset=['Produto'])
            c1, c2, c3 = st.columns(3)
            with c1:
                prod_v = st.selectbox("Selecione o Produto", df_rel['Produto'].unique(), index=None, placeholder="Buscar produto...")
                qtd_v = st.number_input("Quantidade Vendida", min_value=1, value=1)
            with c2:
                mkt_v = st.selectbox("Marketplace", ["shein", "shopee", "temu"])
                vlr_un = st.number_input("Preço de Venda Praticado (Unitário)", min_value=0.01)
            
            if st.button("Calcular Lucro Real da Venda", type="primary") and prod_v:
                it = df_rel[df_rel['Produto'] == prod_v].iloc[0]
                c_aq = converter_custo_seguro(it['Custo_aquisicao'])
                faturamento = vlr_un * qtd_v
                custos_totais = (c_aq + 1.00) * qtd_v 
                imposto = faturamento * 0.06 
                
                if mkt_v == "shein": 
                    taxas = (faturamento * 0.18) + (5 * qtd_v)
                elif mkt_v == "shopee":
                    taxas = (faturamento * 0.20 + 4 * qtd_v) if vlr_un <= 79.99 else (faturamento * 0.14 + 20 * qtd_v)
                else: 
                    taxas = 0 
                
                lucro_final = faturamento - custos_totais - taxas - imposto
                st.divider()
                st.subheader(f"Resultado Financeiro Real: {prod_v}")
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Faturamento Total", f"R$ {faturamento:.2f}")
                r2.metric("Custo + Operacional", f"R$ {custos_totais:.2f}")
                r3.metric("Taxas + Impostos", f"R$ {taxas + imposto:.2f}")
                margem_real = ((lucro_final / faturamento) * 100) if faturamento > 0 else 0
                r4.metric("Lucro Líquido Real", f"R$ {lucro_final:.2f}", delta=f"{margem_real:.1f}%")

    elif st.session_state.pg == "Cadastro":
        st.header("📝 Novo Item na Base")
        with st.form("cad_final"):
            st.markdown("### Preencha as informações do novo produto")
            m = st.selectbox("Selecione o Marketplace", ["shein", "shopee", "temu"])
            n = st.text_input("Nome Completo do Produto")
            s = st.text_input("SKU / Referência Interna") 
            c = st.number_input("Custo Unitário de Aquisição (R$)", min_value=0.01)
            
            if st.form_submit_button("Salvar na Planilha", type="primary"):
                if n and s:
                    planilha.worksheet(m).append_row([n, s, str(c).replace('.', ',')])
                    st.success(f"Sucesso! Produto '{n}' salvo na base {m.upper()}.")
                else:
                    st.error("Por favor, preencha o Nome e o SKU.")