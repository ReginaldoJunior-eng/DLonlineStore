import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import urllib.parse
import json
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

# --- CONEXÃO COM GOOGLE SHEETS (HÍBRIDA BLINDADA) ---
@st.cache_resource(ttl=600)
def conectar_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    sheet_id = "1sWBnF83-z6yrEKxWoJ1IulHNkwSEU6Si6WzNuLxqW44"
    info = None

    # 1. TENTA PEGAR DOS SECRETS (MODO NUVEM)
    try:
        if "gcp_service_account" in st.secrets:
            # Se encontrar, transforma em dicionário comum
            info = dict(st.secrets["gcp_service_account"])
            if 'private_key' in info:
                info['private_key'] = info['private_key'].replace('\\n', '\n')
    except Exception:
        # Se der erro de "No secrets found", ele ignora e segue para o plano B
        info = None

    # 2. SE NÃO CONSEGUIU PELOS SECRETS, TENTA O ARQUIVO LOCAL (MODO DESENVOLVIMENTO)
    if info is None:
        try:
            path_json = r'C:\Users\Junior\Desktop\CodigosPython2\.streamlit\secrets.toml.json'
            with open(path_json, 'r') as f:
                info = json.load(f)
                # Garante que a chave privada funcione independente de como foi salva
                info['private_key'] = info['private_key'].replace('\\n', '\n')
        except FileNotFoundError:
            st.error("Erro: Arquivo JSON local não encontrado e Secrets da nuvem ausentes.")
            return None

    # 3. AUTENTICAÇÃO FINAL
    try:
        if info:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
            client = gspread.authorize(creds)
            return client.open_by_key(sheet_id)
    except Exception as e:
        st.error(f"Erro na autenticação com Google: {e}")
        return None

# --- FUNÇÃO DE CONVERSÃO DE MOEDA ---
def converter_custo_seguro(valor_raw):
    if not valor_raw or valor_raw == "": return 0.0
    s = str(valor_raw).replace('R$', '').replace(' ', '').strip()
    if ',' not in s and '.' not in s:
        try:
            val = float(s)
            # Lógica simples para tratar valores que podem vir em centavos
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
        # Fórmula para preço de venda: P = (Custo_Aquisicao + Custo_Fixo + Taxa_Extra) / (1 - (Comissao + Imposto + Margem))
        divisor = 1 - (comissao_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_fixo_invisivel + taxa_extra) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comissao_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_fixo_invisivel - taxa_extra
        return preco, lucro
    
    elif mkt == "shopee":
        # Lógica de taxas da Shopee baseada no custo
        taxa_plat = 4.0 if custo_aquisicao < 50 else 20.0 
        comis_mkt = 0.20 if custo_aquisicao < 50 else 0.14 # Comissão varia
        divisor = 1 - (comis_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_fixo_invisivel + taxa_plat) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comis_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_fixo_invisivel - taxa_plat
        return preco, lucro

    elif mkt == "temu":
        # Temu com comissão 0%, apenas imposto e margem
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
        st.subheader("🔐 Área do Vendedor")
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.button("Entrar no Painel", type="primary"):
            if u == "leandro" and p == "123":
                st.session_state.logado = True
                st.session_state.pg = "Calculadora" # Redireciona para o painel restrito
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
    else:
        # Menus da Área Logada
        st.subheader(f"👋 Olá, {st.session_state.logado if isinstance(st.session_state.logado, str) else 'Leandro'}")
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
    # 1. DEFINE OS CAMINHOS
    caminho_local = r"C:\Users\Junior\Desktop\CodigosPython2\banner_inicio.jpg"
    nome_arquivo = "banner_inicio.jpg"

    # 2. LOGICA DA IMAGEM (HIBRIDA)
    if os.path.exists(caminho_local):
        st.image(caminho_local, use_container_width=True)
    else:
        st.image(nome_arquivo, use_container_width=True)
    
    # 3. TEXTOS (FORA DO IF/ELSE DA IMAGEM PARA APARECER SEMPRE)
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
    
    # WHATSAPP COM ÍCONE E LINK CLICÁVEL
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
                
                # Encode para URL
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
        
        if not planilha:
            st.error("Erro na conexão com o Google Sheets. Verifique o console ou tente novamente.")
            st.stop()
            
        lista_dfs = []
        for a in ["shein", "shopee", "temu"]:
            try:
                d = pd.DataFrame(planilha.worksheet(a).get_all_records())
                if not d.empty: 
                    # Filtra apenas as colunas necessárias para o seletor
                    lista_dfs.append(d[['Produto', 'Custo_aquisicao']])
            except: pass
        
        if lista_dfs:
            # Consolida todos os produtos para a busca
            df_geral = pd.concat(lista_dfs).drop_duplicates(subset=['Produto'])
            
            # Placeholder e index=None permitem que o usuário digite para buscar
            prod_sel = st.selectbox("Selecione ou Digite o Produto", df_geral['Produto'].unique(), index=None, placeholder="Digite o nome do produto...")
            
            if prod_sel:
                row = df_geral[df_geral['Produto'] == prod_sel].iloc[0]
                custo_aq = converter_custo_seguro(row['Custo_aquisicao'])
                margem_input = st.number_input("Margem de Lucro Desejada (%)", min_value=1.0, value=2.0, step=1.0)
                
                # Executa os cálculos para cada marketplace
                p_shein, l_shein = calcular_venda_completo(custo_aq, margem_input, "shein")
                p_shopee, l_shopee = calcular_venda_completo(custo_aq, margem_input, "shopee")
                p_temu, l_temu = calcular_venda_completo(custo_aq, margem_input, "temu")
                
                st.divider()
                st.subheader(f"Análise de Preços Sugeridos: {prod_sel}")
                st.metric("Custo de Aquisição Base", f"R$ {custo_aq:.2f}")
                
                # Monta a tabela de resultados com a coluna de Custo Unitário adicionada
                res = {
                    "Canal": ["SHEIN", "SHOPEE", "TEMU"],
                    "Custo Unitário": [f"R$ {custo_aq:.2f}", f"R$ {custo_aq:.2f}", f"R$ {custo_aq:.2f}"],
                    "Preço Sugerido": [f"R$ {p_shein:.2f}", f"R$ {p_shopee:.2f}", f"R$ {p_temu:.2f}"],
                    "Lucro Líquido Real": [f"R$ {l_shein:.2f}", f"R$ {l_shopee:.2f}", f"R$ {l_temu:.2f}"]
                }
                st.table(pd.DataFrame(res))

    elif st.session_state.pg == "Relatórios":
        st.header("📈 Relatório de Vendas")
        
        if not planilha:
            st.error("Erro na conexão com o Google Sheets.")
            st.stop()
            
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
                # Selectbox configurado para permitir digitação/busca
                prod_v = st.selectbox("Selecione o Produto", df_rel['Produto'].unique(), index=None, placeholder="Buscar produto...")
                qtd_v = st.number_input("Quantidade Vendida", min_value=1, value=1)
            with c2:
                mkt_v = st.selectbox("Marketplace", ["shein", "shopee", "temu"])
                vlr_un = st.number_input("Preço de Venda Praticado (Unitário)", min_value=0.01)
            
            if st.button("Calcular Lucro Real da Venda", type="primary") and prod_v:
                # Lógica de cálculo do lucro real baseada na venda praticada
                it = df_rel[df_rel['Produto'] == prod_v].iloc[0]
                c_aq = converter_custo_seguro(it['Custo_aquisicao'])
                
                faturamento = vlr_un * qtd_v
                # Inclui custo de aquisição e custo operacional
                custos_totais = (c_aq + 1.00) * qtd_v 
                imposto = faturamento * 0.06 # 6% fixo
                
                # Taxas baseadas nas regras de cada marketplace
                if mkt_v == "shein": 
                    taxas = (faturamento * 0.18) + (5 * qtd_v)
                elif mkt_v == "shopee":
                    # Regra simples da Shopee baseada no valor unitário
                    taxas = (faturamento * 0.20 + 4 * qtd_v) if vlr_un <= 79.99 else (faturamento * 0.14 + 20 * qtd_v)
                else: 
                    taxas = 0 # Temu 0% de taxas
                
                lucro_final = faturamento - custos_totais - taxas - imposto
                
                st.divider()
                st.subheader(f"Resultado Financeiro Real: {prod_v}")
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Faturamento Total", f"R$ {faturamento:.2f}")
                r2.metric("Custo + Operacional", f"R$ {custos_totais:.2f}")
                r3.metric("Taxas + Impostos", f"R$ {taxas + imposto:.2f}")
                
                # Margem percentual
                margem_real = ((lucro_final / faturamento) * 100) if faturamento > 0 else 0
                r4.metric("Lucro Líquido Real", f"R$ {lucro_final:.2f}", delta=f"{margem_real:.1f}%")

    elif st.session_state.pg == "Cadastro":
        st.header("📝 Novo Item na Base")
        
        if not planilha:
            st.error("Erro na conexão com o Google Sheets.")
            st.stop()
            
        with st.form("cad_final"):
            st.markdown("### Preencha as informações do novo produto")
            m = st.selectbox("Selecione o Marketplace", ["shein", "shopee", "temu"])
            n = st.text_input("Nome Completo do Produto")
            s = st.text_input("SKU / Referência Interna") # SKU incluído
            c = st.number_input("Custo Unitário de Aquisição (R$)", min_value=0.01)
            
            if st.form_submit_button("Salvar na Planilha", type="primary"):
                # Validação simples
                if n and s:
                    # Envia os dados para a aba correspondente na planilha Google
                    # Salva Nome, SKU e Custo (formatado com vírgula para o Sheets)
                    planilha.worksheet(m).append_row([n, s, str(c).replace('.', ',')])
                    st.success(f"Sucesso! Produto '{n}' salvo na base {m.upper()}.")
                else:
                    st.error("Por favor, preencha o Nome e o SKU.")
