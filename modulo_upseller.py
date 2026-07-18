# -*- coding: utf-8 -*-
import io, base64, time, json, os
import streamlit as st
from PIL import Image, ImageFilter, ImageEnhance

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    TESSERACT_OK = True
except:
    TESSERACT_OK = False

UPSELLER_URL   = "https://app.upseller.com/pt/home"
UPSELLER_EMAIL = "vendas.dlonlinestore@gmail.com"
UPSELLER_SENHA = "@Gele1826"
COOKIES_FILE   = "upseller_cookies.json"

SEL_EMAIL    = "#app > div:nth-child(2) > div.page_layout > div.page_module_box > div.page_module > form > div:nth-child(2) > div > div > span > input"
SEL_SENHA    = "#app > div:nth-child(2) > div.page_layout > div.page_module_box > div.page_module > form > div:nth-child(3) > div > div > span > span.ant-input-affix-wrapper.ant-input-password > input"
SEL_CAPTCHA  = "#app > div:nth-child(2) > div.page_layout > div.page_module_box > div.page_module > form > div:nth-child(4) > div > div > span > input"
SEL_IMG_CAP  = "#app > div:nth-child(2) > div.page_layout > div.page_module_box > div.page_module > form > div:nth-child(4) > div > div > span > button > img"
SEL_BTN_LOG  = "#app > div:nth-child(2) > div.page_layout > div.page_module_box > div.page_module > form > div.mb_5.ant-row.ant-form-item > div > div > span > button"
SEL_BTN_LOG2    = "button.ant-btn-primary"
SEL_BTN_SEND_CODE = "#app > div.page_layout > div.page_module_box > div.page_module > form > div.code_item.ant-row.ant-form-item > div > div > span > button"
SEL_POPUP_CLOSE   = "body > div:nth-child(23) > div > div.ant-modal-wrap > div > div.ant-modal-content > button"
SEL_POPUP_AVISOS  = "body > div:nth-child(26) > div > div.ant-modal-wrap > div > div.ant-modal-content > button"

# ── COOKIES ──────────────────────────────────────────────────────────────────

def salvar_cookies(driver):
    try:
        with open(COOKIES_FILE, "w") as f:
            json.dump(driver.get_cookies(), f)
        return True
    except:
        return False

def login_por_cookies(driver):
    if not os.path.exists(COOKIES_FILE):
        return False
    try:
        driver.get(UPSELLER_URL)
        time.sleep(2)
        with open(COOKIES_FILE) as f:
            for cookie in json.load(f):
                try: driver.add_cookie(cookie)
                except: pass
        driver.refresh()
        time.sleep(3)
        return "login" not in driver.current_url
    except:
        return False

def deletar_cookies():
    try: os.remove(COOKIES_FILE)
    except: pass

# ── OCR ───────────────────────────────────────────────────────────────────────

def fechar_popup(driver):
    """Fecha qualquer popup/modal aberto."""
    from selenium.webdriver.common.by import By
    import time
    fechou = False
    
    # Lista de seletores para tentar fechar popups
    seletores = [
        # Botão X do modal de login
        SEL_POPUP_CLOSE,
        # Botão X do modal de avisos
        SEL_POPUP_AVISOS,
        # Qualquer botão X de modal ant-design
        "button[aria-label='Close'].ant-modal-close",
        "button.ant-modal-close",
        ".ant-modal-close",
        ".ant-modal-close-x",
        # Botão "Fechar" de texto
        "button.ant-btn:not(.ant-btn-primary)",
    ]
    
    # Tenta por seletores CSS
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
        except:
            continue
    
    # Tenta por texto do botão
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
        except:
            pass
    
    time.sleep(1)
    
    # Verifica se ainda tem modal e tenta de novo
    try:
        modais = driver.find_elements(By.CSS_SELECTOR, ".ant-modal-wrap:not([style*='display: none'])")
        if modais:
            for modal in modais:
                try:
                    close_btn = modal.find_element(By.CSS_SELECTOR, "button")
                    driver.execute_script("arguments[0].click();", close_btn)
                    time.sleep(0.5)
                except:
                    pass
    except:
        pass
    
    return fechou

def ler_captcha_ocr(driver):
    try:
        from selenium.webdriver.common.by import By

        # Tenta pegar src base64 da imagem
        try:
            img_elem = driver.find_element(By.CSS_SELECTOR, SEL_IMG_CAP)
            src = img_elem.get_attribute("src") or ""
            if src.startswith("data:image"):
                _, data = src.split(",", 1)
                img_bytes = base64.b64decode(data)
            else:
                # Screenshot do elemento
                img_bytes = img_elem.screenshot_as_png
        except:
            # Fallback: screenshot da página inteira e recorta área do captcha
            btn_imgs = driver.find_elements(By.CSS_SELECTOR, "button img, [class*=captcha] img, img[alt*='CAPTCHA']")
            if btn_imgs:
                img_bytes = btn_imgs[0].screenshot_as_png
            else:
                # Screenshot full page
                img_bytes = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(img_bytes))
        img = img.convert("L").resize((img.width*3, img.height*3), Image.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(2.5).filter(ImageFilter.SHARPEN)
        texto = pytesseract.image_to_string(img, config="--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789").strip() if TESSERACT_OK else ""
        return texto, img
    except:
        return "", None

# ── DRIVER ────────────────────────────────────────────────────────────────────

def criar_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def driver_esta_vivo(driver):
    """Confirma se a sessão do Chrome por trás do driver ainda existe (não foi
    fechada manualmente, não travou, não caiu). Sem essa checagem, o app pode achar
    que continua 'logado' apontando pra um navegador que já não existe mais, e
    qualquer ação (como Publicar) fica presa sem feedback claro."""
    if driver is None:
        return False
    try:
        _ = driver.title
        return True
    except Exception:
        return False

def _tentar_reconectar_via_cookies():
    """Recria o driver e loga de novo usando os cookies salvos, sem exigir login
    manual — usado quando a sessão anterior morreu (Chrome fechado, travado etc.)
    mas ainda temos uma sessão válida guardada. Retorna o novo driver ou None."""
    if not os.path.exists(COOKIES_FILE):
        return None
    try:
        novo_driver = criar_driver()
        if login_por_cookies(novo_driver):
            fechar_popup(novo_driver)
            novo_driver.minimize_window()
            return novo_driver
        novo_driver.quit()
        return None
    except Exception:
        return None

# ── ESTADO GLOBAL (sobrevive a F5) ─────────────────────────────────────────────
# st.session_state é resetado a cada F5 (nova sessão/websocket). Para manter o
# Chrome logado mesmo com refresh, guardamos o driver num cache compartilhado
# no processo do servidor, que só é perdido se o app/servidor reiniciar.

@st.cache_resource
def _ups_estado_global():
    return {"driver": None, "logado": False}

# ── WIDGET PRINCIPAL ──────────────────────────────────────────────────────────

def widget_login_upseller():
    st.markdown("#### 🔐 Login Upseller")

    estado_global = _ups_estado_global()

    for k, v in [("ups_etapa", 0), ("ups_driver", None),
                 ("ups_logado", False), ("ups_captcha_img", None), ("ups_captcha_ocr", "")]:
        if k not in st.session_state:
            st.session_state[k] = v

    # Se o cache global diz que está logado, mas o Chrome por trás morreu (fechado,
    # travou etc.), tenta reconectar sozinho com os cookies salvos — sem isso o app
    # fica "achando" que está logado e qualquer ação trava sem feedback (fica no limbo).
    if estado_global["logado"] and not driver_esta_vivo(estado_global["driver"]):
        with st.spinner("🍪 Sessão anterior foi perdida — reconectando com os cookies salvos..."):
            novo_driver = _tentar_reconectar_via_cookies()
        if novo_driver:
            estado_global["driver"] = novo_driver
            estado_global["logado"] = True
            st.session_state["ups_driver"] = novo_driver
            st.session_state["ups_logado"] = True
            st.session_state["ups_etapa"] = 3
            st.toast("🍪 Sessão do Upseller restaurada automaticamente!")
        else:
            estado_global["driver"] = None
            estado_global["logado"] = False
            st.session_state["ups_driver"] = None
            st.session_state["ups_logado"] = False
            st.session_state["ups_etapa"] = 0
            st.warning("⚠️ A sessão do Upseller foi perdida e não foi possível reconectar sozinho. Faça login novamente.")

    # Se já existe sessão logada compartilhada (sobreviveu a um F5), reaproveita
    elif estado_global["logado"] and estado_global["driver"] is not None and not st.session_state["ups_logado"]:
        st.session_state["ups_driver"] = estado_global["driver"]
        st.session_state["ups_logado"] = True
        st.session_state["ups_etapa"] = 3

    # Força manter na aba Publicar via query param
    st.query_params["tab"] = "publicar"

    etapa = st.session_state["ups_etapa"]

    # ── ETAPA 0: Inicial ─────────────────────────────────────────
    if etapa == 0:
        tem_cookies = os.path.exists(COOKIES_FILE)

        if tem_cookies:
            st.info("🍪 Sessão anterior encontrada!")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("⚡ Login Automático", type="primary", use_container_width=True):
                    with st.spinner("Restaurando sessão..."):
                        driver = criar_driver()
                        if login_por_cookies(driver):
                            fechar_popup(driver)
                            driver.minimize_window()
                            st.session_state["ups_driver"] = driver
                            st.session_state["ups_logado"] = True
                            st.session_state["ups_etapa"] = 3
                            estado_global["driver"] = driver
                            estado_global["logado"] = True
                            st.rerun()
                        else:
                            driver.quit()
                            deletar_cookies()
                            st.warning("⚠️ Sessão expirada. Faça login manual.")
                            st.rerun()
            with col2:
                if st.button("🌐 Login Manual", use_container_width=True):
                    deletar_cookies()
                    st.session_state["ups_etapa"] = 1
                    st.rerun()
        else:
            if st.button("🌐 Abrir Upseller", type="primary", use_container_width=True):
                st.session_state["ups_etapa"] = 1
                st.rerun()
        return None

    # ── ETAPA 1: Abre browser e preenche login ────────────────────
    if etapa == 1:
        # Abre browser se ainda não abriu
        if st.session_state["ups_driver"] is None:
            with st.spinner("Abrindo Upseller..."):
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                driver = criar_driver()
                driver.get(UPSELLER_URL)
                time.sleep(3)
                try:
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, SEL_EMAIL)))
                    driver.find_element(By.CSS_SELECTOR, SEL_EMAIL).send_keys(UPSELLER_EMAIL)
                    driver.find_element(By.CSS_SELECTOR, SEL_SENHA).send_keys(UPSELLER_SENHA)
                except Exception as e:
                    st.error(f"Erro: {e}")
                    driver.quit()
                    st.session_state["ups_etapa"] = 0
                    return None
                ocr_txt, img = ler_captcha_ocr(driver)
                st.session_state["ups_driver"] = driver
                st.session_state["ups_captcha_ocr"] = ocr_txt
                st.session_state["ups_captcha_img"] = img
                st.rerun()
            return None

        st.success("✅ Email e senha preenchidos. Digite o CAPTCHA:")
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.session_state["ups_captcha_img"]:
                st.image(st.session_state["ups_captcha_img"], width=150)
            else:
                st.warning("Sem imagem")
        with col2:
            cap = st.text_input("CAPTCHA:", value=st.session_state["ups_captcha_ocr"])
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔄 Recarregar", use_container_width=True):
                    ocr, img = ler_captcha_ocr(st.session_state["ups_driver"])
                    st.session_state["ups_captcha_ocr"] = ocr
                    st.session_state["ups_captcha_img"] = img
                    st.rerun()
            with c2:
                if st.button("🚀 Login", type="primary", use_container_width=True):
                    driver = st.session_state["ups_driver"]
                    from selenium.webdriver.common.by import By
                    try:
                        driver.find_element(By.CSS_SELECTOR, SEL_CAPTCHA).clear()
                        driver.find_element(By.CSS_SELECTOR, SEL_CAPTCHA).send_keys(cap)
                        # Tenta seletores alternativos para o botão
                        btn_clicado = False
                        for sel in [SEL_BTN_LOG, "form button[type='submit']", "form .ant-btn-primary", ".ant-btn-primary", "form button"]:
                            try:
                                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                                for b in btns:
                                    if b.is_displayed() and b.is_enabled():
                                        b.click()
                                        btn_clicado = True
                                        break
                                if btn_clicado:
                                    break
                            except:
                                continue
                        if not btn_clicado:
                            st.error("Não encontrou o botão Login.")
                            return None
                        time.sleep(4)
                        url = driver.current_url
                        if "login-code" in url or "verify" in url or "verificac" in url.lower():
                            st.session_state["ups_etapa"] = 2
                            st.rerun()
                        elif "login" not in url:
                            fechar_popup(driver)
                            salvar_cookies(driver)
                            driver.minimize_window()
                            st.session_state["ups_logado"] = True
                            st.session_state["ups_etapa"] = 3
                            estado_global["driver"] = driver
                            estado_global["logado"] = True
                            st.rerun()
                        else:
                            st.error("❌ CAPTCHA incorreto.")
                            ocr, img = ler_captcha_ocr(driver)
                            st.session_state["ups_captcha_ocr"] = ocr
                            st.session_state["ups_captcha_img"] = img
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
        return None

    # ── ETAPA 2: Código de verificação por email ──────────────────
    if etapa == 2:
        # Clica automaticamente no botão "Enviar Código" se ainda não clicou
        if not st.session_state.get("ups_code_enviado"):
            driver = st.session_state["ups_driver"]
            from selenium.webdriver.common.by import By
            try:
                btns = driver.find_elements(By.CSS_SELECTOR, SEL_BTN_SEND_CODE)
                if not btns:
                    btns = driver.find_elements(By.CSS_SELECTOR, "button.ant-btn-primary")
                for btn in btns:
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        st.session_state["ups_code_enviado"] = True
                        break
            except:
                pass

        st.warning("📧 Verifique seu email e insira o código abaixo.")
        st.caption(f"Email: `{UPSELLER_EMAIL}`")
        codigo = st.text_input("Código de verificação:", max_chars=10)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("↩️ Voltar", use_container_width=True):
                try: st.session_state["ups_driver"].quit()
                except: pass
                st.session_state["ups_driver"] = None
                st.session_state["ups_etapa"] = 0
                st.session_state["ups_code_enviado"] = False
                st.rerun()
        with c2:
            if st.button("✅ Confirmar", type="primary", use_container_width=True):
                driver = st.session_state["ups_driver"]
                from selenium.webdriver.common.by import By
                try:
                    for inp in driver.find_elements(By.CSS_SELECTOR, "input"):
                        ph = (inp.get_attribute("placeholder") or "").lower()
                        if any(x in ph for x in ["código", "code", "verif"]):
                            inp.clear(); inp.send_keys(codigo); break
                    else:
                        for inp in driver.find_elements(By.CSS_SELECTOR, "input"):
                            if inp.is_displayed() and inp.get_attribute("type") not in ["hidden","password"]:
                                inp.clear(); inp.send_keys(codigo); break
                    for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
                        if any(x in btn.text.lower() for x in ["continuar","continue","confirmar","submit"]):
                            btn.click(); break
                    time.sleep(4)
                    if "login" not in driver.current_url:
                        salvar_cookies(driver)
                        driver.minimize_window()
                        st.session_state["ups_logado"] = True
                        st.session_state["ups_etapa"] = 3
                        estado_global["driver"] = driver
                        estado_global["logado"] = True
                        st.rerun()
                    else:
                        st.error("❌ Código inválido.")
                except Exception as e:
                    st.error(f"Erro: {e}")
        return None

    # ── ETAPA 3: Logado ───────────────────────────────────────────
    if etapa == 3:
        st.success("✅ Upseller conectado! Chrome em background.")
        st.caption("🍪 Sessão salva — sobrevive a F5 e volta automático no próximo acesso!")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚪 Desconectar", use_container_width=True):
                try: st.session_state["ups_driver"].quit()
                except: pass
                deletar_cookies()
                st.session_state["ups_driver"] = None
                st.session_state["ups_logado"] = False
                st.session_state["ups_etapa"] = 0
                estado_global["driver"] = None
                estado_global["logado"] = False
                st.rerun()
        with c2:
            if st.button("🗑️ Limpar sessão salva", use_container_width=True):
                deletar_cookies()
                st.info("Cookies removidos.")
        return st.session_state["ups_driver"]

    return None

# ============================================================
# PUBLICAÇÃO DE PRODUTO NO UPSELLER
# ============================================================

SKU_COUNTER_FILE = "upseller_sku_counter.json"

def get_proximo_sku():
    """Retorna próximo SKU no formato RJ-00001, RJ-00002..."""
    try:
        if os.path.exists(SKU_COUNTER_FILE):
            with open(SKU_COUNTER_FILE) as f:
                data = json.load(f)
                num = data.get("contador", 0) + 1
        else:
            num = 1
        with open(SKU_COUNTER_FILE, "w") as f:
            json.dump({"contador": num}, f)
        return f"RJ-{num:05d}"
    except:
        return "RJ-00001"

def titulo_case(texto):
    """Converte TEXTO EM MAIÚSCULO para Texto Com Primeiras Letras."""
    return texto.strip().title() if texto else ""

def extrair_dimensoes(tamanho_str):
    """Extrai comprimento, largura, altura de string como '25x17cm, 30x20cm'."""
    import re
    if not tamanho_str:
        return None, None, None
    nums = re.findall(r'\d+', tamanho_str)
    if len(nums) >= 3:
        return nums[0], nums[1], nums[2]
    elif len(nums) == 2:
        return nums[0], nums[1], None
    elif len(nums) == 1:
        return nums[0], None, None
    return None, None, None

def extrair_peso_gramas(peso_str):
    """Extrai peso em gramas e adiciona 50g de embalagem."""
    import re
    if not peso_str:
        return None
    nums = re.findall(r'\d+', peso_str)
    if nums:
        peso = int(nums[0])
        # Converte KG para gramas se necessário
        if 'kg' in peso_str.lower() or peso < 10:
            peso = peso * 1000
        return str(peso + 50)  # +50g embalagem
    return None

def montar_descricao(produto):
    """Monta descrição do produto com as informações capturadas."""
    campos = [
        ("Fabricante", produto.get("fabricante")),
        ("Caixa com", produto.get("caixa_com")),
        ("Tipo", produto.get("tipo") or produto.get("tipo_de_produto")),
        ("Cor", produto.get("cor") or produto.get("cores")),
        ("Validade", produto.get("validade")),
        ("Composição", produto.get("composicao")),
        ("Tamanho", produto.get("tamanho") or produto.get("tamanho_aproximado")),
        ("Peso", produto.get("peso") or produto.get("peso_aproximado")),
        ("Quantidade", produto.get("quantidade")),
        ("Caixa Master", produto.get("caixa_master")),
    ]
    linhas = []
    for label, valor in campos:
        if valor:
            linhas.append(f"{label}: {valor}")
    return "\n".join(linhas)

def processar_e_enviar_imagem(driver, imagem_url):
    """
    Baixa a imagem, garante pelo menos 800x800px e no máximo 2MB (upscale/qualidade
    ajustados conforme necessário — requisitos da Shopee, doc
    https://www.upseller.com/pt/help-doc-article-750: imagem fora desses limites
    causa "Erro de API de imagem" ao publicar, mesmo o upload no Armazém "aceitando"
    silenciosamente) e sobe no campo de upload da tela atualmente aberta no driver.
    Usado tanto no cadastro novo (Armazém) quanto no reprocessamento de produtos já
    publicados que ficaram sem imagem — como Shein/Temu/TikTok copiam a imagem do
    Armazém, corrigir aqui corrige nas 4 lojas.
    Retorna uma string de status: "imagem enviada" em caso de sucesso, ou uma
    descrição do problema.
    """
    if not imagem_url:
        return "sem imagem"
    if not imagem_url.startswith("http"):
        imagem_url = "https://campineira.com.br" + imagem_url

    try:
        import requests
        import tempfile
        import uuid as _uuid
        from selenium.webdriver.common.by import By
        from PIL import Image as PILImage

        # Baixa a imagem localmente (contorna bloqueio CORS)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://campineira.com.br/"
        }
        resp = requests.get(imagem_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return f"falha ao baixar (HTTP {resp.status_code})"

        img_pil = PILImage.open(io.BytesIO(resp.content)).convert("RGB")

        # Garante pelo menos 800x800px (mínimo exigido pela Shopee) — escala pela
        # menor dimensão, então a outra dimensão fica proporcionalmente maior.
        MIN_LADO = 800
        largura, altura = img_pil.size
        escala = max(1.0, MIN_LADO / min(largura, altura))
        if escala > 1.0:
            img_pil = img_pil.resize(
                (int(largura * escala) + 1, int(altura * escala) + 1),
                PILImage.LANCZOS
            )

        # Caminho direto (sem tempfile.NamedTemporaryFile) — abrir dois handles pro
        # mesmo arquivo (o do NamedTemporaryFile + o do img_pil.save()) trava no
        # Windows por "arquivo em uso por outro processo".
        caminho_img = os.path.abspath(os.path.join(tempfile.gettempdir(), f"upseller_img_{_uuid.uuid4().hex}.jpg"))

        # Máximo de 2MB (limite da Shopee) — o upscale pra 800x800 pode gerar um
        # arquivo grande; reduz a qualidade em passos até caber, sem nunca sair do JPEG.
        MAX_BYTES = 2 * 1024 * 1024
        qualidade = 90
        img_pil.save(caminho_img, "JPEG", quality=qualidade)
        while os.path.getsize(caminho_img) > MAX_BYTES and qualidade > 40:
            qualidade -= 15
            img_pil.save(caminho_img, "JPEG", quality=qualidade)

        driver.execute_script("window.scrollTo(0, 2000);")
        time.sleep(1)

        # Procura input[type=file] oculto e envia o arquivo
        inputs_file = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        uploaded = False
        for inp in inputs_file:
            try:
                driver.execute_script("arguments[0].style.display='block';", inp)
                inp.send_keys(caminho_img)
                time.sleep(2)
                uploaded = True
                break
            except:
                continue

        try:
            os.unlink(caminho_img)
        except:
            pass

        return "imagem enviada" if uploaded else "campo de upload não encontrado"

    except Exception as e:
        return f"erro ao processar imagem: {str(e)[:80]}"

def publicar_produto_upseller(driver, produto):
    """
    Publica um produto no Upseller.
    Retorna (sucesso, mensagem)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    import time

    wait = WebDriverWait(driver, 15)

    try:
        # 1. Abre página de criar produto
        driver.get("https://app.upseller.com/pt/products/product-add?productType=single")
        time.sleep(3)

        # Fecha popup se aparecer
        fechar_popup(driver)
        time.sleep(1)

        # ── SKU ────────────────────────────────────────────────
        sku = get_proximo_sku()
        campo_sku = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
            "#basic > div.ant-card-body > div > form > div:nth-child(1) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > input"
        )))
        campo_sku.clear()
        campo_sku.send_keys(sku)

        # ── NOME ───────────────────────────────────────────────
        nome = titulo_case(produto.get("nome", ""))
        campo_nome = driver.find_element(By.CSS_SELECTOR,
            "#basic > div.ant-card-body > div > form > div:nth-child(2) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span.input_suffix_custom.ant-input-affix-wrapper > input"
        )
        campo_nome.clear()
        campo_nome.send_keys(nome)

        # ── CATEGORIA: mesmo esquema usado na publicação oficial (Shopee/Shein/
        # Temu/TikTok) — abre o seletor, aba "Recomendação", botão "Obter Categoria",
        # primeira sugestão que vier da própria plataforma. Só cai pro seletor por IA
        # (mais antigo) se isso não funcionar nesse formulário.
        try:
            ok_recomendada, _cat_armazem = usar_categoria_recomendada(driver)
            if not ok_recomendada:
                selecionar_categoria_armazem(driver, nome)
            time.sleep(1)
        except:
            pass

        # ── EAN ────────────────────────────────────────────────
        ean = produto.get("ean", "")
        if ean:
            campo_ean = driver.find_element(By.CSS_SELECTOR,
                "#basic > div.ant-card-body > div > form > div:nth-child(5) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div > div.pti_r > div > div > input[type=text]"
            )
            campo_ean.clear()
            campo_ean.send_keys(ean)

        # ── SCROLL para Info. de Venda ─────────────────────────
        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(1)

        # ── DESCRIÇÃO ──────────────────────────────────────────
        descricao = montar_descricao(produto)
        if descricao:
            try:
                campo_desc = driver.find_element(By.CSS_SELECTOR,
                    "#saleAddSpecification > div.ant-card-body > div > form > div.description_item.ant-row.ant-form-item > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > textarea"
                )
                campo_desc.clear()
                campo_desc.send_keys(descricao)
            except:
                pass

        # ── PESO (+50g embalagem) ──────────────────────────────
        peso_str = produto.get("peso") or produto.get("peso_aproximado")
        peso_final = extrair_peso_gramas(peso_str)
        if peso_final:
            try:
                campo_peso = driver.find_element(By.CSS_SELECTOR,
                    "#saleAddSpecification > div.ant-card-body > div > form > div:nth-child(6) > div.ant-col.ant-col-20.ant-form-item-control-wrapper > div > span > span > span > input"
                )
                campo_peso.clear()
                campo_peso.send_keys(peso_final)
            except:
                pass

        # ── TAMANHO ────────────────────────────────────────────
        tam_str = produto.get("tamanho") or produto.get("tamanho_aproximado")
        comp, larg, alt = extrair_dimensoes(tam_str)
        for sel, val in [
            ("#saleAddSpecification > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span:nth-child(1) > div > div.ant-input-number-input-wrap > input", comp),
            ("#saleAddSpecification > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span:nth-child(2) > div > div.ant-input-number-input-wrap > input", larg),
            ("#saleAddSpecification > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span:nth-child(3) > div > div.ant-input-number-input-wrap > input", alt),
        ]:
            if val:
                try:
                    campo = driver.find_element(By.CSS_SELECTOR, sel)
                    campo.clear()
                    campo.send_keys(val)
                except:
                    pass

        # ── MARCA (Fabricante) ─────────────────────────────────
        fabricante = produto.get("fabricante", "")
        if fabricante:
            try:
                campo_marca = driver.find_element(By.CSS_SELECTOR,
                    "#saleAddSpecification > div.ant-card-body > div > form > div:nth-child(5) > div.ant-col.ant-col-6.ant-form-item-control-wrapper > div > span > input"
                )
                campo_marca.clear()
                campo_marca.send_keys(fabricante)
            except:
                pass

        # ── QUANTIDADE (estoque do Armazém sempre entra como 100 unidades,
        # independente da quantidade capturada na descrição do produto) ──
        if not preencher_por_label(driver, "#saleAddSpecification", "Quantidade", "100"):
            preencher_por_label(driver, "#basic", "Quantidade", "100")

        # ── IMAGEM ─────────────────────────────────────────────
        imagem_status = processar_e_enviar_imagem(driver, produto.get("imagem", ""))

        # ── SALVAR ─────────────────────────────────────────────
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        btn_salvar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
            "#myEditBox > section.my_edit_head.ant-layout > div > div.head_r > div > button"
        )))
        btn_salvar.click()
        time.sleep(3)

        # Antes de reportar sucesso, checa se o Upseller recusou o salvamento (ex:
        # "Erro: 7899866278400 O código de barra já existe") — sem isso, o código
        # clicava Salvar, esperava 3s e SEMPRE retornava sucesso, mesmo quando o
        # produto não foi criado de verdade por causa de EAN/GTIN duplicado.
        erro_validacao = driver.execute_script("""
            var candidatos = document.querySelectorAll(
                '.ant-message-error, .ant-message-notice-content, .ant-notification-notice-description, ' +
                '.ant-form-item-explain, .ant-form-explain, [class*="error"]'
            );
            for (var el of candidatos) {
                var txt = (el.textContent || '').trim();
                if (txt && txt.toLowerCase().includes('já existe') && el.offsetParent !== null) {
                    return txt;
                }
            }
            return null;
        """)
        if erro_validacao:
            return False, f"❌ {erro_validacao}"

        aviso_imagem = "" if imagem_status == "imagem enviada" else f" ⚠️ Imagem: {imagem_status}."
        return True, f"✅ Produto '{nome}' publicado! SKU: {sku}.{aviso_imagem}"

    except Exception as e:
        return False, f"❌ Erro: {str(e)[:100]}"

def reprocessar_imagem_armazem(driver, sku, imagem_url):
    """
    Abre o anúncio JÁ EXISTENTE no Armazém pelo SKU (usando o campo de busca da
    lista, não cria um cadastro novo) e reenvia só a imagem, usando a mesma lógica
    de redimensionamento de publicar_produto_upseller(). Usado para corrigir
    produtos que já foram publicados mas ficaram sem foto ou com foto rejeitada.
    Retorna (sucesso: bool, mensagem: str).
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    import time

    wait = WebDriverWait(driver, 15)

    try:
        driver.get("https://app.upseller.com/pt/products/product-list?productType=single")
        time.sleep(3)
        fechar_popup(driver)

        # Usa o campo de busca da tela pra achar o SKU rápido (a lista pode ter
        # centenas/milhares de produtos)
        campo_busca = None
        for sel in [
            "input[placeholder*='múltiplas']",
            "input[placeholder*='SKU']",
            "input[placeholder*='sku']",
            ".ant-input-search input",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    campo_busca = el
                    break
            except:
                continue

        if campo_busca:
            campo_busca.click()
            campo_busca.send_keys(Keys.CONTROL + "a")
            campo_busca.send_keys(Keys.DELETE)
            campo_busca.send_keys(sku)
            campo_busca.send_keys(Keys.ENTER)
            time.sleep(2)

        # Localiza a linha do SKU em qualquer <tr> da página (mesma estratégia
        # usada na migração — não depende de um caminho de tabela fixo)
        linha = driver.execute_script("""
            var alvo = arguments[0].trim();
            var linhas = document.querySelectorAll('tr');
            for (var tr of linhas) {
                if (tr.textContent.includes(alvo)) return tr;
            }
            return null;
        """, sku)

        if not linha:
            return False, f"❌ SKU {sku} não encontrado no Armazém"

        # Clica no link "Editar" dentro dessa linha
        handles_antes = len(driver.window_handles)
        editou = driver.execute_script("""
            var linha = arguments[0];
            var links = linha.querySelectorAll('a');
            for (var a of links) {
                if (a.textContent.trim().toLowerCase() === 'editar') {
                    a.click();
                    return true;
                }
            }
            return false;
        """, linha)

        if not editou:
            return False, f"❌ Link 'Editar' não encontrado na linha do SKU {sku}"

        time.sleep(3)
        # Se abriu em aba nova, troca o foco pra ela
        if len(driver.window_handles) > handles_antes:
            driver.switch_to.window(driver.window_handles[-1])
        fechar_popup(driver)

        status_imagem = processar_e_enviar_imagem(driver, imagem_url)

        # Salva
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        try:
            btn_salvar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
                "#myEditBox > section.my_edit_head.ant-layout > div > div.head_r > div > button"
            )))
            btn_salvar.click()
            time.sleep(3)
        except Exception:
            if len(driver.window_handles) > handles_antes:
                driver.close()
                driver.switch_to.window(driver.window_handles[-1])
            return False, f"❌ Imagem processada ({status_imagem}) mas não achou o botão Salvar"

        if len(driver.window_handles) > handles_antes:
            driver.close()
            driver.switch_to.window(driver.window_handles[-1])

        if status_imagem != "imagem enviada":
            return False, f"⚠️ Reprocessado, mas imagem ainda com problema: {status_imagem}"
        return True, f"✅ Imagem reenviada para o SKU {sku}"

    except Exception as e:
        try:
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[-1])
        except:
            pass
        return False, f"❌ Erro ao reprocessar imagem: {str(e)[:100]}"

# ============================================================
# CONFIRMAÇÃO: A AUTOMAÇÃO REALMENTE PAROU?
# ============================================================

def pagina_rascunho_ainda_aberta(driver):
    """
    Confirma se ainda estamos na tela de edição do rascunho (formulário #myEditBox
    visível). Se sim, é sinal de que a automação parou no meio do caminho e nada foi
    publicado de fato — usado para deixar isso explícito na tela em vez de deixar
    a informação só escondida no log.
    Retorna True/False, ou None se não deu pra confirmar (ex: driver fechado).
    """
    from selenium.webdriver.common.by import By
    try:
        els = driver.find_elements(By.CSS_SELECTOR, "#myEditBox")
        return any(el.is_displayed() for el in els)
    except Exception:
        return None

# ============================================================
# ETAPA 2 — COPIAR PARA LOJAS
# ============================================================

MAPA_LOJA_CHECKBOX = {
    "shopee": "shopee",
    "shein": "shein",
    "temu": "temu",
    "tiktok": "tiktok shop",
}

def etapa2_copiar_para_lojas(driver, sku, plataforma="shopee"):
    """
    Acessa a lista de Produtos do Armazém, localiza pelo SKU, marca o produto e
    usa "Ação em Massa > Copiar para Lojas" pra copiar DIRETO do Armazém pra
    plataforma pedida (Shopee, Shein, Temu ou TikTok) — o modal "Copiar para
    Lojas" tem checkbox pra qualquer uma delas, não só Shopee; não precisa
    passar pela Shopee primeiro pra depois "migrar" pras outras.
    Retorna (sucesso, mensagem)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time

    wait = WebDriverWait(driver, 15)

    try:
        # 1. Acessa lista de produtos
        driver.get("https://app.upseller.com/pt/products/product-list")
        time.sleep(3)
        fechar_popup(driver)

        # 2. Clica na aba "Único" — seletor confirmado + fallbacks
        try:
            clicou_unico = False
            for sel_unico in [
                "#app > div.app_box.appBox > section > section > div > main > div > section.mb_8 > div > div > div.ant-tabs-bar.ant-tabs-top-bar.ant-tabs-small-bar > div > div > div > div > div:nth-child(1) > div:nth-child(2) > span.tit",
                "#app > div.app_box.appBox > section > section > div > main > div > section.mb_8 > div > div > div.ant-tabs-bar.ant-tabs-top-bar.ant-tabs-small-bar > div > div > div > div > div:nth-child(1) > div.ant-tabs-tab-active.ant-tabs-tab",
            ]:
                try:
                    btn_unico = driver.find_element(By.CSS_SELECTOR, sel_unico)
                    driver.execute_script("arguments[0].click();", btn_unico)
                    clicou_unico = True
                    break
                except:
                    continue

            # Fallback: busca por texto "Único"
            if not clicou_unico:
                tabs = driver.find_elements(By.CSS_SELECTOR, ".ant-tabs-tab")
                for tab in tabs:
                    if "único" in tab.text.strip().lower():
                        driver.execute_script("arguments[0].click();", tab)
                        clicou_unico = True
                        break
            time.sleep(2)
        except:
            pass

        # Espera a tabela "assentar" antes de procurar linhas — a troca de aba dispara
        # uma busca assíncrona; procurar/marcar rápido demais pega a renderização
        # antiga, que é substituída (e reseta qualquer checkbox marcado) quando o
        # resultado novo chega alguns instantes depois.
        try:
            WebDriverWait(driver, 10).until(lambda d: len(d.find_elements(By.CSS_SELECTOR,
                "#app > div.app_box.appBox > section > section > div > main > section.my_content_body > div > div > div > table > tbody > tr"
            )) > 0)
        except:
            pass
        time.sleep(1.5)

        # 3. Localiza linha com o SKU correto e valida match
        linhas = driver.find_elements(By.CSS_SELECTOR,
            "#app > div.app_box.appBox > section > section > div > main > section.my_content_body > div > div > div > table > tbody > tr"
        )

        linha_match = None
        for i, linha in enumerate(linhas):
            try:
                # Tenta seletor principal
                sku_cell = linha.find_element(By.CSS_SELECTOR, "td.w_m_200 > div > div.flex.center_align > div > span")
                if sku_cell.text.strip() == sku:
                    linha_match = i + 1
                    break
            except:
                try:
                    # Fallback: qualquer td que tenha o texto do SKU
                    if sku in linha.text:
                        linha_match = i + 1
                        break
                except:
                    continue

        if linha_match is None:
            return False, f"❌ SKU {sku} não encontrado na lista!"

        # 4. Marca o checkbox da linha correta
        sel_chk_usado = None
        for sel_chk in [
            f"#app > div.app_box.appBox > section > section > div > main > section.my_content_body > div > div > div > table > tbody > tr:nth-child({linha_match}) > td.w_f_40.check_box_td > label > span > input",
            f"#app > div.app_box.appBox > section > section > div > main > section.my_content_body > div > div > div > table > tbody > tr:nth-child({linha_match}) > td:first-child input[type='checkbox']",
        ]:
            try:
                checkbox = driver.find_element(By.CSS_SELECTOR, sel_chk)
                driver.execute_script("arguments[0].click();", checkbox)
                sel_chk_usado = sel_chk
                time.sleep(1)
                break
            except:
                continue

        if not sel_chk_usado:
            return False, f"❌ Checkbox do SKU {sku} não encontrado na lista"

        # Confirma que o checkbox continua marcado — re-clica se detectar que
        # desmarcou sozinho.
        marcado_estavel = False
        for _tentativa in range(3):
            time.sleep(0.8)
            checado = driver.execute_script("""
                var el = document.querySelector(arguments[0]);
                return el ? el.checked : null;
            """, sel_chk_usado)
            if checado:
                marcado_estavel = True
                break
            try:
                checkbox = driver.find_element(By.CSS_SELECTOR, sel_chk_usado)
                driver.execute_script("arguments[0].click();", checkbox)
            except:
                pass

        if not marcado_estavel:
            return False, f"❌ Não conseguiu manter o SKU {sku} marcado na lista (a seleção reseta sozinha)"

        # 5. Clica em "Ações em Massa" — usa ActionChains (movimento real de mouse)
        from selenium.webdriver.common.action_chains import ActionChains

        def clique_robusto(elemento):
            """Tenta múltiplas estratégias de clique: ActionChains, nativo, JS."""
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
                time.sleep(0.3)
                ActionChains(driver).move_to_element(elemento).pause(0.2).click().perform()
                return True
            except:
                pass
            try:
                elemento.click()
                return True
            except:
                pass
            try:
                driver.execute_script("""
                    var el = arguments[0];
                    var evt = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});
                    el.dispatchEvent(evt);
                """, elemento)
                return True
            except:
                return False

        btn_acoes = None
        try:
            btn_acoes = driver.find_element(By.CSS_SELECTOR, "#inventory > button")
        except:
            for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
                if "ações em massa" in btn.text.strip().lower():
                    btn_acoes = btn
                    break

        def _dropdown_tem_copiar():
            return driver.execute_script("""
                var els = document.querySelectorAll('li, .ant-dropdown-menu-item, [role="menuitem"]');
                for (var e of els) {
                    if (e.textContent.trim().toLowerCase().includes('copiar para lojas') && e.offsetParent !== null) {
                        return true;
                    }
                }
                return false;
            """)

        dropdown_aberto = False
        if btn_acoes:
            # Clica só uma vez e ESPERA (poll) o dropdown renderizar — clicar de novo
            # enquanto ainda está abrindo pode FECHAR um menu que só demorou a
            # renderizar (é um botão toggle), então evitamos re-clicar sem necessidade.
            clique_robusto(btn_acoes)
            for _ in range(8):
                time.sleep(0.5)
                if _dropdown_tem_copiar():
                    dropdown_aberto = True
                    break

            if not dropdown_aberto:
                # Só clica de novo se realmente nunca abriu (não alterna abre/fecha)
                clique_robusto(btn_acoes)
                for _ in range(8):
                    time.sleep(0.5)
                    if _dropdown_tem_copiar():
                        dropdown_aberto = True
                        break

        # 6. Clica em "Copiar para Lojas" — busca por texto é mais confiável aqui
        clicou_copiar = False
        itens_vistos = []
        if dropdown_aberto:
            try:
                itens_menu = driver.find_elements(By.CSS_SELECTOR, "li, .ant-dropdown-menu-item, [role='menuitem']")
                for item in itens_menu:
                    try:
                        txt = item.text.strip()
                        if txt:
                            itens_vistos.append(txt)
                        if txt.lower() == "copiar para lojas" and item.is_displayed():
                            clique_robusto(item)
                            clicou_copiar = True
                            time.sleep(1)
                            break
                    except:
                        continue
            except:
                pass

        if not clicou_copiar:
            try:
                btn_copiar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
                    "body > div:nth-child(25) > div > div > ul > li:nth-child(2) > div"
                )))
                clique_robusto(btn_copiar)
                clicou_copiar = True
            except:
                pass
        time.sleep(2)

        # Se a Upseller recusou a ação por não ter registrado nenhuma seleção de
        # verdade, ela mostra esse toast — checkbox marcado no DOM não significa que
        # o app "sabe" disso. Se apareceu, já era: para aqui em vez de seguir tentando
        # abrir o modal (que nunca vai vir).
        erro_selecao = _erro_selecionar_produto(driver)
        if erro_selecao:
            return False, f"❌ {erro_selecao} (SKU {sku} estava marcado no DOM mas a Upseller não reconheceu a seleção)"

        # Verifica se o modal "Copiar para Lojas" realmente abriu
        modal_aberto = driver.execute_script("""
            var modais = document.querySelectorAll('.ant-modal-content');
            for (var m of modais) {
                if (m.offsetParent !== null && m.textContent.toLowerCase().includes('copiar para lojas')) {
                    return true;
                }
            }
            return false;
        """)
        if not clicou_copiar or not modal_aberto:
            diagnostico = f"dropdown_aberto={dropdown_aberto}"
            if itens_vistos:
                diagnostico += f", itens vistos no menu: {itens_vistos[:8]}"
            return False, f"❌ Não conseguiu abrir o modal 'Copiar para Lojas' ({diagnostico}). Tente clicar manualmente uma vez para destravar."

        # 7. Seleciona a loja pedida (coluna da esquerda, ex: "Shopee" — não a
        # variante "UP Shopee" da coluna da direita)
        loja_nome = "Desconhecida"
        try:
            checkboxes_loja = driver.find_elements(By.CSS_SELECTOR,
                ".checkbox_box .all_box label, .ant-modal-body .checkbox_box label, .ant-modal-body label"
            )
            for box in checkboxes_loja:
                try:
                    texto_box = box.text.strip().lower()
                    # Precisa ser exatamente o nome da loja (ex: "shopee"), não a
                    # variante "up shopee" — o modal tem as duas colunas lado a lado.
                    alvo = MAPA_LOJA_CHECKBOX.get(plataforma.lower(), plataforma.lower())
                    if texto_box == alvo:
                        chk = box.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                        driver.execute_script("arguments[0].click();", chk)
                        loja_nome = box.text.strip()
                        time.sleep(1)
                        break
                except:
                    continue
        except:
            pass

        if loja_nome == "Desconhecida":
            return False, f"❌ Checkbox da loja '{plataforma}' não encontrado no modal 'Copiar para Lojas'"

        # 8. Confirma — busca pelo botão "Confirmar" visível no modal aberto
        confirmado = False
        try:
            modais = driver.find_elements(By.CSS_SELECTOR, ".ant-modal-wrap")
            for modal in modais:
                if not modal.is_displayed():
                    continue
                try:
                    btns = modal.find_elements(By.CSS_SELECTOR, "button")
                    for btn in btns:
                        if any(x in btn.text.strip().lower() for x in ["confirmar", "confirm", "ok"]):
                            driver.execute_script("arguments[0].click();", btn)
                            confirmado = True
                            break
                    if confirmado:
                        break
                except:
                    continue
        except:
            pass

        if not confirmado:
            # Fallback: seletor original
            try:
                btn_confirmar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
                    "div.ant-modal-footer button.ant-btn-primary"
                )))
                btn_confirmar.click()
                confirmado = True
            except:
                pass

        time.sleep(4)

        # A validação real de "selecione pelo menos um produto" parece ser uma
        # chamada assíncrona disparada só quando clica em CONFIRMAR (o modal em si
        # sempre abre, isso não prova nada) — checa ANTES de fechar qualquer modal,
        # porque fechar_modais() poderia acabar descartando o próprio aviso de erro
        # antes da gente conseguir ver.
        erro_confirmacao = _erro_selecionar_produto(driver)
        if erro_confirmacao:
            fechar_modais(driver)
            return False, f"❌ {erro_confirmacao} (falhou ao confirmar a cópia pra {loja_nome})"

        # 9. Fecha modal de resultado (qualquer modal aberto, sem nth-child fixo)
        fechar_modais(driver)
        time.sleep(2)

        return True, f"✅ Produto {sku} copiado para {loja_nome}!"

    except Exception as e:
        return False, f"❌ Erro etapa 2: {str(e)[:100]}"


# ============================================================
# ETAPA 3 — CATEGORIA INTELIGENTE (Claude API)
# ============================================================

def capturar_categorias_disponiveis(driver):
    """Lê a lista de categorias visível no dropdown aberto no Upseller (formato 'A > B > C')."""
    from selenium.webdriver.common.by import By
    try:
        items = driver.execute_script("""
            var candidatos = document.querySelectorAll(
                '.category_select_pop *, .ant-popover *, [class*=category] *, [class*=dropdown] li, [class*=dropdown] div'
            );
            var vistos = new Set();
            var resultado = [];
            for (var el of candidatos) {
                if (el.children.length > 0) continue;
                var txt = el.textContent.trim();
                if (txt.includes('>') && txt.length > 5 && txt.length < 150 && !vistos.has(txt)) {
                    if (el.offsetParent !== null) {
                        vistos.add(txt);
                        resultado.push(txt);
                    }
                }
            }
            return resultado;
        """)
        return items or []
    except:
        return []


def selecionar_categoria_no_dropdown(driver, categoria_texto):
    """Clica no item da lista de categorias que corresponde exatamente ao texto dado."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    if not categoria_texto:
        return False
    try:
        clicou = driver.execute_script("""
            var alvo = arguments[0].trim();
            var candidatos = document.querySelectorAll(
                '.category_select_pop *, .ant-popover *, [class*=category] *, [class*=dropdown] li, [class*=dropdown] div'
            );
            for (var el of candidatos) {
                if (el.children.length > 0) continue;
                if (el.textContent.trim() === alvo && el.offsetParent !== null) {
                    el.scrollIntoView({block:'center'});
                    el.click();
                    return true;
                }
            }
            return false;
        """, categoria_texto)
        if not clicou:
            els = driver.find_elements(By.XPATH, f"//*[normalize-space(text())={repr(categoria_texto)}]")
            for el in els:
                if el.is_displayed():
                    ActionChains(driver).move_to_element(el).pause(0.2).click().perform()
                    return True
        return clicou
    except:
        return False


def sugerir_categoria_ia(nome_produto, categorias):
    """
    Usa Claude API para sugerir a melhor categoria.
    Retorna string com o caminho da categoria.
    """
    import json
    try:
        import urllib.request
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 200,
            "messages": [{
                "role": "user",
                "content": f"""Você é um especialista em categorização de produtos para e-commerce.

Produto: "{nome_produto}"

Categorias disponíveis na plataforma:
{chr(10).join(f'- {c}' for c in categorias[:50])}

Responda APENAS com o texto exato de uma categoria da lista acima que melhor se encaixa neste produto.
Não explique, não adicione pontuação. Apenas o texto da categoria."""
            }]
        }

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"].strip()
    except:
        return None


def etapa3_editar_rascunho(driver, sku, nome_produto):
    """
    Acessa rascunho Shopee, valida SKU, abre editor,
    sugere categoria via IA e preenche.
    Retorna (sucesso, mensagem, categoria_sugerida)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time

    wait = WebDriverWait(driver, 15)

    try:
        # 1. Acessa rascunhos Shopee
        driver.get("https://app.upseller.com/pt/products/shopee/drafts")
        time.sleep(3)
        fechar_popup(driver)

        # O toast "Selecione pelo menos um produto" da etapa anterior (Copiar para
        # Lojas) às vezes só termina de renderizar depois que essa tela já carregou
        # (validação assíncrona do lado da Upseller) — não significa que o produto
        # não chegou aqui. Em vez de desistir, marca o checkbox da linha (reafirma a
        # seleção) e segue pra editar do mesmo jeito.
        erro_selecao = _erro_selecionar_produto(driver)

        # 2. Localiza a linha certa pelo SKU — busca em TODAS as linhas da tabela,
        # não só a primeira. Com mais de um rascunho parado na lista (de tentativas
        # anteriores), o seletor fixo antigo (sem nth-child, sempre pegava a 1ª
        # linha) só acertava o SKU por coincidência quando havia um único rascunho.
        linha_elemento = _localizar_linha_por_sku(driver, sku)
        if linha_elemento is None:
            msg_toast = f" ({erro_selecao})" if erro_selecao else ""
            return False, f"❌ SKU {sku} não encontrado nos rascunhos da Shopee{msg_toast}", None

        if erro_selecao:
            driver.execute_script("""
                var linha = arguments[0];
                var chk = linha.querySelector('input[type="checkbox"]');
                if (chk) chk.click();
            """, linha_elemento)
            time.sleep(1)

        # 3. Clica Editar dentro da linha encontrada
        href = driver.execute_script("""
            var linha = arguments[0];
            var links = linha.querySelectorAll('a');
            for (var a of links) {
                if (a.textContent.trim().toLowerCase() === 'editar') {
                    return a.getAttribute('href');
                }
            }
            return null;
        """, linha_elemento)

        if not href:
            return False, f"❌ Link 'Editar' não encontrado na linha do SKU {sku} (Shopee)", None
        driver.execute_script("window.open(arguments[0]);", href)
        time.sleep(3)

        # 4. Muda para nova aba
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(2)

        # Categoria será resolvida no preenchimento (botão "Obter Categoria" da plataforma)
        categoria_sugerida = None
        try:
            categorias = capturar_categorias_disponiveis(driver)
            if categorias:
                categoria_sugerida = sugerir_categoria_ia(nome_produto, categorias)
        except:
            pass

        # Fecha qualquer dropdown remanescente clicando fora
        try:
            driver.execute_script("document.body.click();")
        except:
            pass

        return True, f"✅ Rascunho aberto! Categoria sugerida: {categoria_sugerida}", categoria_sugerida

    except Exception as e:
        return False, f"❌ Erro etapa 3: {str(e)[:100]}", None


# ============================================================
# EXTRAÇÃO DE DIMENSÕES VIA IA
# ============================================================

def extrair_dimensoes_ia(descricao, nome_produto):
    """
    Usa Claude API para extrair dimensões da descrição.
    Retorna dict {largura, comprimento, altura} ou zeros.
    """
    import json, urllib.request
    if not descricao:
        return {"largura": "0", "comprimento": "0", "altura": "0"}
    try:
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 150,
            "messages": [{
                "role": "user",
                "content": f"""Analise a descrição abaixo e extraia as dimensões físicas (largura, comprimento/tamanho, altura).
Retorne APENAS um JSON válido no formato: {{"largura": "X", "comprimento": "X", "altura": "X"}}
Use apenas números em cm. Se não encontrar uma dimensão, use "0".

Produto: {nome_produto}
Descrição: {descricao}

Responda APENAS o JSON, nada mais."""
            }]
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            txt = data["content"][0]["text"].strip()
            # Limpa possível markdown
            txt = txt.replace("```json","").replace("```","").strip()
            dims = json.loads(txt)
            return {
                "largura": str(dims.get("largura", "0")),
                "comprimento": str(dims.get("comprimento", "0")),
                "altura": str(dims.get("altura", "0"))
            }
    except:
        return {"largura": "0", "comprimento": "0", "altura": "0"}


# ============================================================
# ETAPA 3 — PREENCHER RASCUNHO COMPLETO
# ============================================================

def preencher_rascunho_shopee(driver, produto, sku, categoria_selecionada=None):
    """
    Preenche todos os campos do rascunho Shopee:
    marca, preço, quantidade, peso, dimensões.
    Retorna (sucesso, mensagem)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    import time

    wait = WebDriverWait(driver, 15)

    def preencher_campo(seletor, valor, limpar=True):
        """Helper para preencher campo com retry. Se o clique nativo for interceptado
        (ex: por um popover que ficou aberto por cima), cai para preenchimento via JS."""
        try:
            campo = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor)))
            driver.execute_script("arguments[0].scrollIntoView(true);", campo)
            time.sleep(0.3)
            try:
                if limpar:
                    campo.click()
                    campo.send_keys(Keys.CONTROL + "a")
                    campo.send_keys(Keys.DELETE)
                campo.send_keys(str(valor))
            except Exception:
                # Fallback: seta o valor via JS e dispara os eventos que o React/Ant Design
                # escuta (setter nativo, senão o React ignora a mudança de .value direto).
                driver.execute_script("""
                    var el = arguments[0], val = arguments[1];
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, val);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                """, campo, str(valor))
            # Dispara "blur" — campos ant-input-number (Vue) só confirmam o valor
            # quando perdem o foco; sem isso o valor digitado fica visível mas não
            # é assumido pelo formulário até o usuário clicar em outro lugar.
            try:
                driver.execute_script("arguments[0].blur();", campo)
            except:
                pass
            return True
        except:
            return False

    try:
        # ── CATEGORIA: tenta recomendação automática da plataforma primeiro ──
        try:
            campo_cat_check = driver.find_element(By.CSS_SELECTOR,
                "#basic input[placeholder*='Categoria'], #basic input[placeholder*='categoria'], .category_select_box input"
            )
            valor_atual = campo_cat_check.get_attribute("value") or ""
        except:
            valor_atual = ""

        if not valor_atual:
            # Tenta usar "Recomendação" + "Obter Categoria" (sugestão da própria plataforma),
            # sempre selecionando a primeira opção retornada — a função já cuida de abrir
            # o seletor sozinha (não abrir aqui de novo, senão o clique duplo fecha o popover).
            ok_recomendada, _cat_obtida = usar_categoria_recomendada(driver)

            # Se não funcionou, usa categoria sugerida pela IA (capturada na etapa anterior)
            if not ok_recomendada and categoria_selecionada:
                selecionar_categoria_no_dropdown(driver, categoria_selecionada)
            time.sleep(1)

            # Fecha qualquer popover/dropdown de categoria que tenha ficado aberto —
            # se não fechar, ele fica sobreposto na tela e intercepta o clique nos
            # campos seguintes (Preço, Quantidade), fazendo o preenchimento falhar
            # mesmo com o seletor certo.
            try:
                driver.execute_script("document.body.click();")
                time.sleep(0.3)
            except:
                pass

        # ── MARCA (Fabricante) ────────────────────────────────
        fabricante = produto.get("fabricante", "")
        if fabricante:
            preencher_campo(
                "#specification > div.ant-card-body > div > form:nth-child(1) > div > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div > div.input_box > input",
                fabricante
            )
            time.sleep(0.5)

        # ── PREÇO (preço já calculado pelo sistema para o marketplace desta execução —
        # aqui é Shopee, então usa preco_shopee) — busca pela linha do label "Preço",
        # nunca por posição (GTIN e Quantidade já mostraram trocar de nth-child). ──
        preco = produto.get("preco_shopee") or produto.get("preco_num", 0)
        if preco:
            preencher_por_label(driver, "#sales", "Preço", f"{float(preco):.2f}")
            time.sleep(0.5)

        # ── QUANTIDADE: sempre 100 fixo, igual ao Armazém (mesma regra em todas
        # as lojas). NUNCA usa nth-child — GTIN e Quantidade não têm posição fixa
        # entre execuções, e GTIN não deve ser tocado. ────────────────────────
        preencher_por_label(driver, "#sales", "Quantidade", "100")
        time.sleep(0.5)

        # ── PESO via IA (+50g embalagem). O campo "Peso do Pacote" da Shopee é em KG,
        # mas extrair_peso_ia() retorna em GRAMAS — precisa converter. Se não achar
        # nada na descrição, usa 0,25 kg (250g) como padrão em vez de 0 (que a Shopee
        # não aceita como peso válido e travava o robô no campo obrigatório). ──
        descricao_peso = " ".join(filter(None, [
            produto.get("peso") or produto.get("peso_aproximado", ""),
            produto.get("composicao", ""),
            produto.get("tamanho") or produto.get("tamanho_aproximado", ""),
        ]))
        peso_gramas = extrair_peso_ia(descricao_peso, produto.get("nome", ""))
        peso_kg = f"{float(peso_gramas) / 1000:.2f}" if peso_gramas else "0.25"
        if not preencher_por_label(driver, "#shopping", "Peso do Pacote", peso_kg):
            preencher_campo(
                "#shopping > div.ant-card-body > div > form > div.weight_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span > div > div.ant-input-number-input-wrap > input",
                peso_kg
            )
        time.sleep(0.5)

        # ── DIMENSÕES via IA ──────────────────────────────────
        descricao = produto.get("descricao") or ""
        # Monta descrição a partir dos campos capturados
        campos_desc = [
            produto.get("tamanho") or produto.get("tamanho_aproximado", ""),
            produto.get("composicao", ""),
        ]
        descricao_completa = descricao + " " + " ".join(filter(None, campos_desc))

        dims = extrair_dimensoes_ia(descricao_completa, produto.get("nome", ""))

        # Largura
        preencher_campo(
            "#shopping > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span:nth-child(1) > div > div.ant-input-number-input-wrap > input",
            dims["largura"]
        )
        time.sleep(0.8)

        # Comprimento
        preencher_campo(
            "#shopping > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span.my_input_number_box.w_140.t_l.ml_12.show_addon_after.style_type1 > div > div.ant-input-number-input-wrap > input",
            dims["comprimento"]
        )
        time.sleep(0.8)

        # Altura
        preencher_campo(
            "#shopping > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span.my_input_number_box.t_r.w_140.ml_12.show_addon_after.style_type1 > div > div.ant-input-number-input-wrap > input",
            dims["altura"]
        )
        # Depois do último campo de dimensão, dá mais tempo pro Vue/Ant Design
        # processar a mudança antes de seguir — foi aqui que o 3º campo mostrou "0"
        # e só depois "corrigiu" pra "1", indicando que o preenchimento seguinte
        # começava antes da tela terminar de assimilar o valor anterior.
        time.sleep(1.2)

        # ── VALIDAÇÃO FINAL: garante que não sobrou campo obrigatório vazio
        # antes de deixar o finalizar_rascunho() clicar em Publicar ──────
        time.sleep(1)
        campos_faltando = verificar_campos_obrigatorios(driver)
        if campos_faltando:
            return False, f"⚠️ Campo(s) obrigatório(s) sem preencher: {'; '.join(campos_faltando)}"

        return True, f"✅ Rascunho preenchido! Dimensões: L{dims['largura']} x C{dims['comprimento']} x A{dims['altura']} cm"

    except Exception as e:
        return False, f"❌ Erro ao preencher rascunho: {str(e)[:100]}"

# ============================================================
# HELPERS COMUNS
# ============================================================

def preencher_input(driver, seletor, valor, limpar=True):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    import time
    try:
        el = driver.find_element(By.CSS_SELECTOR, seletor)
        driver.execute_script("arguments[0].scrollIntoView(true);", el)
        time.sleep(0.2)
        if limpar:
            el.click()
            el.send_keys(Keys.CONTROL + "a")
            el.send_keys(Keys.DELETE)
        el.send_keys(str(valor))
        return True
    except:
        return False

def preencher_por_label(driver, form_selector, label_texto, valor):
    """Preenche um campo achando a linha do formulário pelo texto do <label>, em vez de
    nth-child — a posição de campos como Quantidade/GTIN não é estável entre execuções.
    Seta o valor via JS (setter nativo + eventos input/change/blur) pra funcionar tanto
    com Vue quanto com React, e confirmar o valor (campos ant-input-number só assumem
    o valor digitado quando perdem o foco)."""
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

def clicar(driver, seletor, js=True):
    from selenium.webdriver.common.by import By
    import time
    try:
        el = driver.find_element(By.CSS_SELECTOR, seletor)
        if js:
            driver.execute_script("arguments[0].click();", el)
        else:
            el.click()
        time.sleep(0.5)
        return True
    except:
        return False

def _erro_selecionar_produto(driver):
    """Detecta o toast 'Selecione pelo menos um produto' — a Upseller mostra isso
    quando uma ação em massa (Copiar para Lojas) roda sem nenhuma linha REALMENTE
    selecionada no estado interno dela, mesmo que o checkbox pareça marcado no DOM.
    Esse toast pode demorar a renderizar (validação assíncrona) e só aparecer de
    fato depois que o robô já navegou pra tela seguinte — por isso essa checagem é
    repetida tanto logo após o clique em "Copiar para Lojas" quanto na abertura da
    tela de rascunhos da loja, pra pegar o erro onde quer que ele acabe aparecendo."""
    return driver.execute_script("""
        var candidatos = document.querySelectorAll(
            '.ant-message-error, .ant-message-notice-content, .ant-notification-notice-description, [class*="message"]'
        );
        for (var el of candidatos) {
            var txt = (el.textContent || '').trim();
            if (txt && txt.toLowerCase().includes('selecione') && txt.toLowerCase().includes('produto') && el.offsetParent !== null) {
                return txt;
            }
        }
        return null;
    """)

def fechar_tour_upseller(driver):
    """Fecha o tour de onboarding do Upseller (bolha 'Copiar para Lojas 1/2 ...
    Ignorar/Próximo') que aparece na primeira vez que a tela de migração é
    visitada na sessão e fica por cima do botão real, bloqueando o clique
    automatizado sem gerar erro nenhum (o clique "funciona" no DOM mas a tela
    visível continua presa no tour). Clica em 'Ignorar' pra pular de vez."""
    return driver.execute_script("""
        var els = document.querySelectorAll('button, span, a, div');
        for (var el of els) {
            var txt = (el.textContent || '').trim().toLowerCase();
            if ((txt === 'ignorar' || txt === 'pular') && el.offsetParent !== null) {
                el.click();
                return true;
            }
        }
        var fechar = document.querySelector('.ant-tour-close, .ant-tour-close-x, .driver-close-btn');
        if (fechar) { fechar.click(); return true; }
        return false;
    """)

def fechar_modais(driver):
    """Tenta fechar qualquer modal aberto."""
    import time
    seletores = [
        "body > div:nth-child(28) > div > div.ant-modal-wrap > div > div.ant-modal-content > button > span",
        "body > div:nth-child(28) > div > div.ant-modal-wrap > div > div.ant-modal-content > div.ant-modal-footer > div > div:nth-child(2) > div > div.ant-space.ant-space-horizontal.ant-space-align-center > div > button",
        "body > div:nth-child(29) > div > div.ant-modal-wrap > div > div.ant-modal-content > button > span",
        "body > div:nth-child(29) > div > div.ant-modal-wrap > div > div.ant-modal-content > div.ant-modal-footer > div > div:nth-child(2) > div > div.ant-space.ant-space-horizontal.ant-space-align-center > div > button",
        ".ant-modal-close", "button[aria-label='Close']"
    ]
    for sel in seletores:
        try:
            from selenium.webdriver.common.by import By
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.5)
        except:
            pass

def extrair_peso_ia(descricao, nome_produto):
    """Usa IA para extrair peso da descrição. Retorna valor em gramas + 50."""
    import json, urllib.request
    if not descricao:
        return None
    try:
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 100,
            "messages": [{
                "role": "user",
                "content": f"""Analise a descrição abaixo e extraia o peso do produto.
Retorne APENAS um número inteiro em gramas. Se não encontrar, retorne 0.
Exemplos: "500g" → 500, "1,5kg" → 1500, "1275G" → 1275

Produto: {nome_produto}
Descrição: {descricao}

Responda APENAS o número, nada mais."""
            }]
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            txt = data["content"][0]["text"].strip()
            peso = int(''.join(filter(str.isdigit, txt)) or 0)
            return str(peso + 50) if peso > 0 else None
    except:
        return None


# ============================================================
# ETAPA 3 — FINALIZAR RASCUNHO (BOTÃO PUBLICAR)
# ============================================================

def finalizar_rascunho(driver):
    """Clica no botão Publicar do rascunho, fecha o modal de confirmação e fecha a
    aba de edição, voltando pra aba principal. Sem fechar a aba, a Shopee parece
    invalidar essa janela sozinha depois de publicar, e o próximo passo (Shein/Temu/
    TikTok) trava com 'target window already closed' ao tentar usá-la."""
    from selenium.webdriver.common.by import By
    import time
    # Dá um tempo extra pra tela assimilar os últimos campos preenchidos (dimensões
    # em especial) antes de clicar em Publicar — clicar cedo demais deixava a
    # validação pegar campos que na verdade já tinham sido preenchidos.
    time.sleep(1)
    clicar(driver, "#myEditBox > section.my_edit_head.ant-layout > div > div.head_r > div:nth-child(2) > button")
    time.sleep(3)

    # Fecha o modal de confirmação "Publicar" (botão "Fechar")
    try:
        for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
            if btn.text.strip().lower() == "fechar" and btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
                break
    except:
        pass
    fechar_modais(driver)

    # Fecha a aba de edição e volta pra aba anterior
    try:
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[-1])
    except:
        pass

    return True, "✅ Publicado na plataforma!"


# ============================================================
# ETAPA 4 — MIGRAR ANÚNCIO PARA SHEIN/TIKTOK/TEMU
# ============================================================

LOJAS_MAPA = {
    "shein":  {"nth": 3, "url_rascunho": "https://app.upseller.com/pt/products/shein/drafts"},
    "tiktok": {"nth": 5, "url_rascunho": "https://app.upseller.com/pt/products/tiktok/drafts"},
    "temu":   {"nth": 7, "url_rascunho": "https://app.upseller.com/pt/products/temu/drafts"},
}

def _localizar_linha_por_sku(driver, sku):
    """Retorna o elemento <tr> cujo texto contém o SKU, buscando em TODAS as linhas
    da página — em vez de um caminho fixo de tabela, que já se mostrou instável
    nesse app (colunas e estruturas mudam entre telas)."""
    return driver.execute_script("""
        var alvo = arguments[0].trim();
        var linhas = document.querySelectorAll('tr');
        for (var tr of linhas) {
            if (tr.textContent.includes(alvo)) {
                return tr;
            }
        }
        return null;
    """, sku)

def _clicar_proxima_pagina(driver):
    """Avança pra próxima página de uma tabela paginada (Ant Design)."""
    return driver.execute_script("""
        var els = document.querySelectorAll('.ant-pagination-next, li.ant-pagination-next, [aria-label="right"]');
        for (var el of els) {
            if (el.offsetParent !== null && !(el.className || '').includes('disabled')) {
                var btn = el.querySelector('button') || el;
                btn.click();
                return true;
            }
        }
        return false;
    """)

def etapa4_migrar_para_lojas(driver, sku):
    """
    Acessa migração de anúncio Shopee → outras lojas.
    Seleciona Shein, TikTok e Temu se disponíveis.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    import time

    try:
        driver.get("https://app.upseller.com/pt/products/product-moving/shopee")
        time.sleep(3)
        fechar_popup(driver)
        fechar_tour_upseller(driver)

        # Verifica se a URL realmente carregou a tela de migração; se não, navega pelo menu
        if "product-moving" not in driver.current_url:
            try:
                menu_produtos = driver.find_element(By.CSS_SELECTOR,
                    "#myNav > header > div.my_nav_l > ul > li.ant-menu-submenu.ant-menu-submenu-horizontal.ant-menu-submenu-selected > div.ant-menu-submenu-title > span"
                )
                driver.execute_script("arguments[0].click();", menu_produtos)
                time.sleep(1)
                for link in driver.find_elements(By.CSS_SELECTOR, "a, li"):
                    if "migração de anúncios" in link.text.strip().lower():
                        driver.execute_script("arguments[0].click();", link)
                        break
                time.sleep(3)
            except:
                pass

        # Espera a tabela carregar de verdade antes de procurar (lista grande, pode
        # levar um instante) — sem isso a busca roda numa tabela ainda vazia.
        try:
            WebDriverWait(driver, 10).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "tr")) > 1)
        except:
            pass

        # Procura o SKU na página atual. A Shopee processa a publicação de forma
        # ASSÍNCRONA (ela mesma avisa "verifique o anúncio mais tarde") — o item pode
        # ainda não ter aparecido na lista de migração mesmo já "publicado" do nosso
        # lado. Por isso espera e recarrega algumas vezes antes de partir pra paginação.
        linha_elemento = _localizar_linha_por_sku(driver, sku)
        tentativas_espera = 0
        while linha_elemento is None and tentativas_espera < 3:
            time.sleep(4)
            driver.refresh()
            time.sleep(3)
            fechar_popup(driver)
            fechar_tour_upseller(driver)
            linha_elemento = _localizar_linha_por_sku(driver, sku)
            tentativas_espera += 1

        # Se ainda não achou, tenta avançar até 5 páginas (a lista de migração pode
        # ter várias dezenas de páginas — o item recém-publicado geralmente fica
        # perto do topo, mas não sempre).
        paginas_tentadas = 0
        while linha_elemento is None and paginas_tentadas < 5:
            if not _clicar_proxima_pagina(driver):
                break
            time.sleep(2)
            linha_elemento = _localizar_linha_por_sku(driver, sku)
            paginas_tentadas += 1

        if linha_elemento is None:
            return False, (f"❌ SKU {sku} não encontrado na migração após esperar "
                            f"~{tentativas_espera * 7}s e procurar em até {paginas_tentadas + 1} página(s). "
                            f"A Shopee pode ainda estar processando a publicação — espere um pouco e clique em Shein de novo.")

        # Marca o checkbox dentro da própria linha encontrada — não depende de nth-child
        marcado = driver.execute_script("""
            var linha = arguments[0];
            var chk = linha.querySelector('input[type="checkbox"]');
            if (!chk) return false;
            chk.click();
            return true;
        """, linha_elemento)
        if not marcado:
            return False, f"❌ SKU {sku} encontrado na migração, mas sem checkbox na linha"

        # Confirma que o checkbox continua marcado antes de seguir — o DOM ("checked")
        # atualiza na hora, mas o estado interno da Upseller (o que realmente conta
        # pra "Copiar para Lojas" reconhecer a seleção) pode demorar mais que isso ou
        # nem registrar o clique. Sem essa confirmação, o código seguia em frente e só
        # descobria o problema tarde demais (toast "Selecione pelo menos um produto"
        # já na tela de rascunhos da loja seguinte).
        marcado_estavel = False
        for _tentativa in range(3):
            time.sleep(0.8)
            checado = driver.execute_script("""
                var linha = arguments[0];
                var chk = linha.querySelector('input[type="checkbox"]');
                return chk ? chk.checked : null;
            """, linha_elemento)
            if checado:
                marcado_estavel = True
                break
            driver.execute_script("""
                var linha = arguments[0];
                var chk = linha.querySelector('input[type="checkbox"]');
                if (chk) chk.click();
            """, linha_elemento)
        if not marcado_estavel:
            return False, f"❌ Não conseguiu manter o SKU {sku} marcado na migração (a seleção reseta sozinha)"

        # Fecha o tour de onboarding antes de clicar — se ele estiver aberto por cima
        # do botão real, o clique abaixo não abre o modal de verdade.
        fechar_tour_upseller(driver)
        time.sleep(0.3)

        # Clica "Copiar para Lojas"
        clicar(driver, "#productMovingStep1 > button")
        time.sleep(2)
        fechar_tour_upseller(driver)

        erro_selecao = _erro_selecionar_produto(driver)
        if erro_selecao:
            return False, f"❌ {erro_selecao} (SKU {sku} estava marcado no DOM mas a Upseller não reconheceu a seleção)"

        # Seleciona plataformas disponíveis (Shein, TikTok, Temu)
        lojas_selecionadas = []
        plataformas = [
            (3, "body > div:nth-child(26) > div > div.ant-modal-wrap > div > div.ant-modal-content > div.ant-modal-body > div.checkbox_box > div:nth-child(3)"),
            (5, "body > div:nth-child(26) > div > div.ant-modal-wrap > div > div.ant-modal-content > div.ant-modal-body > div.checkbox_box > div:nth-child(5)"),
            (7, "body > div:nth-child(26) > div > div.ant-modal-wrap > div > div.ant-modal-content > div.ant-modal-body > div.checkbox_box > div:nth-child(7)"),
        ]

        for nth, base_sel in plataformas:
            try:
                nome_el = driver.find_element(By.CSS_SELECTOR, f"{base_sel} > div.ant-col.ant-col-5 > label > span:nth-child(2)")
                nome_loja = nome_el.text.strip().lower()
                if any(x in nome_loja for x in ["shein", "tiktok", "tik tok", "temu"]):
                    # Marca os dois checkboxes da linha (loja à esquerda + conta "UP X"
                    # à direita) — confirmado que só marcar a esquerda não é suficiente.
                    checkboxes_linha = driver.find_elements(By.CSS_SELECTOR, f"{base_sel} input[type='checkbox']")
                    for chk in checkboxes_linha:
                        driver.execute_script("arguments[0].click();", chk)
                    lojas_selecionadas.append(nome_loja)
            except:
                continue

        # Confirma
        clicar(driver,
            "body > div:nth-child(26) > div > div.ant-modal-wrap > div > div.ant-modal-content > div.ant-modal-footer > div > div:nth-child(2) > div > div.ant-space.ant-space-horizontal.ant-space-align-center > div:nth-child(2) > button"
        )
        time.sleep(4)

        # Checa o erro ANTES de fechar qualquer modal — fechar_modais() poderia
        # descartar o próprio aviso de erro antes da gente conseguir ver.
        erro_confirmacao = _erro_selecionar_produto(driver)
        if erro_confirmacao:
            fechar_modais(driver)
            return False, f"❌ {erro_confirmacao} (falhou ao confirmar a migração do SKU {sku})"

        fechar_modais(driver)

        return True, f"✅ Migrado para: {', '.join(lojas_selecionadas)}"

    except Exception as e:
        return False, f"❌ Erro migração: {str(e)[:100]}"


# ============================================================
# ETAPA 5 — EDITAR RASCUNHO POR PLATAFORMA (SHEIN/TEMU/TIKTOK)
# ============================================================

def editar_rascunho_plataforma(driver, sku, produto, plataforma):
    """
    Acessa rascunho da plataforma, valida SKU,
    preenche categoria (IA), preço, peso, dimensões e publica.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time

    wait = WebDriverWait(driver, 15)
    info = LOJAS_MAPA.get(plataforma.lower())
    if not info:
        return False, f"Plataforma {plataforma} não mapeada"

    try:
        driver.get(info["url_rascunho"])
        time.sleep(3)
        fechar_popup(driver)

        # Recarrega do zero (mesma ideia da Shopee: começar numa página "limpa") —
        # o job assíncrono de "Copiar para Lojas" às vezes ainda não terminou do lado
        # da Upseller quando essa tela carrega pela primeira vez, e o toast "Selecione
        # pelo menos um produto" fica preso na tela / a linha do rascunho ainda não
        # apareceu. Um segundo carregamento dá tempo do job terminar de verdade antes
        # da gente procurar a linha, em vez de já entrar tentando recuperar de um erro.
        driver.get(info["url_rascunho"])
        time.sleep(3)
        fechar_popup(driver)

        # Se mesmo assim o toast ainda estiver na tela, não significa que o produto
        # não chegou aqui — em vez de desistir, marca o checkbox da linha (reafirma a
        # seleção) e segue pra editar do mesmo jeito.
        erro_selecao = _erro_selecionar_produto(driver)

        # Localiza a linha certa pelo SKU — busca em TODAS as linhas da tabela (não só
        # a primeira). Com mais de um rascunho na lista (rascunhos de tentativas
        # anteriores ficam parados ali, ex: RJ-00051 e RJ-00050 juntos), o seletor
        # fixo antigo (sem nth-child, sempre pegava a 1ª linha) só validava o SKU
        # certo por coincidência quando havia um único rascunho na tela.
        linha_elemento = _localizar_linha_por_sku(driver, sku)
        if linha_elemento is None:
            msg_toast = f" ({erro_selecao})" if erro_selecao else ""
            return False, f"❌ SKU {sku} não encontrado no rascunho {plataforma}{msg_toast}"

        if erro_selecao:
            driver.execute_script("""
                var linha = arguments[0];
                var chk = linha.querySelector('input[type="checkbox"]');
                if (chk) chk.click();
            """, linha_elemento)
            time.sleep(1)

        # Clica Editar dentro da linha encontrada
        href = driver.execute_script("""
            var linha = arguments[0];
            var links = linha.querySelectorAll('a');
            for (var a of links) {
                if (a.textContent.trim().toLowerCase() === 'editar') {
                    return a.getAttribute('href');
                }
            }
            return null;
        """, linha_elemento)
        if not href:
            return False, f"❌ Link 'Editar' não encontrado na linha do SKU {sku} ({plataforma})"

        driver.execute_script("window.open(arguments[0]);", href)
        time.sleep(3)
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(2)
        fechar_popup(driver)

        # A Shein (e possivelmente Temu/TikTok) mostra um modal "Corresponder à
        # Categoria" na PRIMEIRA vez que edita um produto de uma categoria de origem
        # ainda não mapeada nela — resolve isso antes de seguir com o preenchimento
        # normal (categorias da mesma origem já ficam mapeadas depois, então isso não
        # se repete pra produtos futuros da mesma categoria).
        _resolver_correspondencia_categoria(driver)

        # ── CATEGORIA: mesma estratégia que já funciona na Shopee — aba "Recomendação"
        # + "Obter Categoria" da própria plataforma, primeira opção. A versão antiga
        # aqui só DIGITAVA o texto no campo de busca sem nunca clicar numa opção da
        # lista — o campo ficava com texto visível mas nenhuma categoria de fato
        # selecionada, por isso "Selecionar Categoria" sempre aparecia como campo
        # obrigatório faltando na validação antes de publicar.
        ok_recomendada, _cat_obtida = usar_categoria_recomendada(driver)
        if not ok_recomendada:
            categorias = capturar_categorias_disponiveis(driver)
            if categorias:
                cat_sugerida = sugerir_categoria_ia(produto.get("nome",""), categorias)
                if cat_sugerida:
                    selecionar_categoria_no_dropdown(driver, cat_sugerida)
        try:
            driver.execute_script("document.body.click();")
            time.sleep(0.3)
        except:
            pass

        # Preço da plataforma — a ÚNICA coisa que muda de verdade entre as lojas.
        # Quantidade/peso/dimensões já vêm preenchidos porque a migração ("Copiar
        # para Lojas" a partir do anúncio da Shopee) copia o rascunho inteiro, já
        # preenchido, da Shopee — não precisa (e não deve) re-preencher esses campos
        # aqui, só ajustar o preço específico de cada plataforma.
        preco = produto.get(f"preco_{plataforma.lower()}", 0) or 0

        if plataforma.lower() == "shein":
            # Campo Preço na tabela de variantes (vxe-table) da Shein
            base = "#variants > div.ant-card-body > div.card_body > div.variation_list > div.variation_list_body > div > div.vxe-table--render-wrapper > div.vxe-table--main-wrapper > div.vxe-table--body-wrapper.body--wrapper > table > tbody > tr"
            if preco:
                preencher_input(driver, f"{base} > td.vxe-body--column.col_5.col--right > div > span > div > div.ant-input-number-input-wrap > input", f"{float(preco):.0f}")

        else:
            # Campo Preço da Temu/TikTok (similar ao da Shopee)
            if preco:
                try:
                    campos_preco = driver.find_elements(By.CSS_SELECTOR, "#sales input[type='text'], #sales input[type='number']")
                    if campos_preco:
                        preencher_input(driver, None, f"{float(preco):.2f}")
                except:
                    pass

            # Temu: tempo de envio + modelo automático + país de origem — campos que
            # não existem na Shopee, então não vêm preenchidos pela cópia; continuam
            # precisando ser preenchidos aqui.
            if plataforma.lower() == "temu":
                clicar(driver, "#shipping > div.ant-card-body > div > form > div:nth-child(1) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div > div > label:nth-child(1) > span.ant-radio > input")
                time.sleep(0.5)
                clicar(driver, "#shipping > div.ant-card-body > div > form > div:nth-child(2) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div > div > div > div.ant-select-selection__placeholder")
                time.sleep(0.5)
                # País de origem: Brasil
                try:
                    campo_pais = driver.find_element(By.CSS_SELECTOR,
                        "#safety > div.ant-card-body > div > form > div:nth-child(2) > div.ant-col.ant-col-20.ant-form-item-control-wrapper > div > span > div > div:nth-child(1) > div > div > span > div > div > div > div.ant-select-selection-selected-value"
                    )
                    if not campo_pais.text.strip():
                        campo_pais.click()
                        time.sleep(0.5)
                        from selenium.webdriver.common.keys import Keys
                        campo_pais.send_keys("Brasil")
                        time.sleep(1)
                except:
                    pass

        # Verifica se sobrou campo obrigatório vazio ANTES de publicar. Sem isso, a
        # plataforma pode rejeitar a publicação (mantendo como rascunho) e o código
        # reportava sucesso mesmo assim — foi o caso de Shein/Temu ficarem em
        # "Rascunho" mesmo com o robô dizendo "publicado".
        campos_faltando = verificar_campos_obrigatorios(driver)
        if campos_faltando:
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[-1])
            return False, f"⚠️ Campo(s) obrigatório(s) sem preencher em {plataforma.title()}: {'; '.join(campos_faltando)}"

        # Publicar
        time.sleep(1)
        clicou_publicar = clicar(driver, "#myEditBox > section.my_edit_head.ant-layout > div > div.head_r > div:nth-child(2) > button")
        time.sleep(3)

        # Fecha o modal de confirmação "Publicar" (botão "Fechar"), igual à Shopee
        try:
            for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
                if btn.text.strip().lower() == "fechar" and btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
                    break
        except:
            pass
        fechar_modais(driver)

        # Fecha aba e volta para anterior
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[-1])

        if not clicou_publicar:
            return False, f"❌ Não encontrou/clicou o botão Publicar em {plataforma.title()}"

        return True, f"✅ Publicado na {plataforma.title()}!"

    except Exception as e:
        try:
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[-1])
        except:
            pass
        return False, f"❌ Erro {plataforma}: {str(e)[:100]}"


# ============================================================
# CATEGORIA NO ARMAZÉM (ETAPA 1) VIA IA
# ============================================================

def selecionar_categoria_armazem(driver, nome_produto):
    """
    Abre o seletor de categoria no formulário do armazém,
    captura opções disponíveis, usa IA para sugerir e clica.
    Retorna (sucesso, categoria_escolhida)
    """
    from selenium.webdriver.common.by import By
    import time

    try:
        # Clica para abrir o dropdown de categoria
        campo_cat = driver.find_element(By.CSS_SELECTOR,
            "#basic > div.ant-card-body > div > form > div:nth-child(4) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div > div.inp_box.ant-select-selection.ant-select-selection--multiple.has_clear > div"
        )
        driver.execute_script("arguments[0].click();", campo_cat)
        time.sleep(1)

        # Captura itens visíveis da árvore de categorias
        categorias = driver.execute_script("""
            var sels = [
                '.content .flex div span',
                '.ant-select-tree-node-content-wrapper',
                '.ant-cascader-menu-item',
                'li.ant-select-dropdown-menu-item'
            ];
            for (var s of sels) {
                var els = document.querySelectorAll(s);
                if (els.length > 3) {
                    return Array.from(els).map(e => e.textContent.trim()).filter(t => t.length > 0 && t.length < 60);
                }
            }
            return [];
        """)

        if not categorias:
            return False, None

        # IA escolhe a melhor categoria
        categoria_sugerida = sugerir_categoria_ia(nome_produto, categorias)

        if not categoria_sugerida:
            return False, None

        # Procura e clica no elemento que corresponde à sugestão
        clicou = driver.execute_script("""
            var alvo = arguments[0].trim().toLowerCase();
            var sels = ['.content .flex div span', '.ant-select-tree-node-content-wrapper',
                        '.ant-cascader-menu-item', 'li.ant-select-dropdown-menu-item'];
            for (var s of sels) {
                var els = document.querySelectorAll(s);
                for (var el of els) {
                    if (el.textContent.trim().toLowerCase() === alvo) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
        """, categoria_sugerida)

        time.sleep(1)
        return clicou, categoria_sugerida

    except Exception as e:
        return False, None


# ============================================================
# CATEGORIA VIA ABA "RECOMENDAÇÃO" + BOTÃO "OBTER CATEGORIA"
# ============================================================

def _resolver_correspondencia_categoria(driver):
    """Lida com o modal "Corresponder à Categoria" que a Shein (e possivelmente
    outras lojas) mostra na primeira vez que se edita um produto de uma categoria
    de origem ainda não mapeada nela — depois de mapeada uma vez, categorias da
    mesma origem são correspondidas automaticamente (segundo o próprio aviso do
    modal), então isso só acontece nos primeiros produtos de cada categoria.

    Sempre escolhe a PRIMEIRA opção em cada nível da categoria em cascata (3
    níveis: ex. Automotivo > Acessórios Externos Automotivos > Acessórios
    decorativos para área externa) e a primeira opção de Variação, se pedida —
    não existe uma escolha "certa" do lado da Campineira pra isso, o objetivo é só
    destravar o fluxo pra seguir editando o produto de verdade depois.

    Retorna True se encontrou e tratou o modal, False se ele não estava presente
    (nesse caso não faz nada, e o fluxo normal de edição segue)."""
    import time

    modal_presente = driver.execute_script("""
        var modais = document.querySelectorAll('.ant-modal-content');
        for (var m of modais) {
            if (m.offsetParent !== null && m.textContent.toLowerCase().includes('corresponder')) {
                return true;
            }
        }
        return false;
    """)
    if not modal_presente:
        return False

    # Abre o seletor de categoria em cascata
    driver.execute_script("""
        var btns = document.querySelectorAll('button');
        for (var b of btns) {
            if (b.textContent.trim().toLowerCase() === 'selecionar categoria' && b.offsetParent !== null) {
                b.click();
                return true;
            }
        }
        return false;
    """)
    time.sleep(1)

    def _categorias_visiveis():
        return driver.execute_script("""
            var out = [];
            document.querySelectorAll('.category_name').forEach(function(el){
                if (el.offsetParent !== null) out.push(el.textContent.trim());
            });
            return out;
        """)

    # Clica sempre a primeira opção NOVA que aparece a cada nível — depois de
    # clicar o 1º nível, a coluna do 2º nível populada com opções que ainda não
    # existiam antes (comparação por texto), evitando reclicar sempre a mesma
    # coluna já selecionada.
    visiveis = set(_categorias_visiveis())
    for _nivel in range(3):
        clicado = driver.execute_script("""
            var antes = new Set(arguments[0]);
            var els = document.querySelectorAll('.category_name');
            for (var el of els) {
                if (el.offsetParent !== null && !antes.has(el.textContent.trim())) {
                    el.click();
                    return el.textContent.trim();
                }
            }
            return null;
        """, list(visiveis))
        if not clicado:
            break
        time.sleep(0.8)
        visiveis = set(_categorias_visiveis())

    # Confirma a categoria escolhida
    driver.execute_script("""
        var btns = document.querySelectorAll('button.ant-btn-primary');
        for (var b of btns) {
            if (b.textContent.trim().toLowerCase() === 'selecionar' && b.offsetParent !== null) {
                b.click();
                return true;
            }
        }
        return false;
    """)
    time.sleep(1)

    # Variação: se aparecer um select vazio (ex: "Padrão: Cor"), sem informação
    # real vinda da Campineira pra isso, escolhe a primeira opção só pra não travar.
    driver.execute_script("""
        var selects = document.querySelectorAll('.ant-select');
        for (var s of selects) {
            if (s.offsetParent !== null && s.className.indexOf('ant-select-disabled') === -1) {
                s.click();
                break;
            }
        }
    """)
    time.sleep(0.6)
    driver.execute_script("""
        var opts = document.querySelectorAll('.ant-select-dropdown-menu-item, .ant-select-item-option, li[role="option"]');
        for (var o of opts) {
            if (o.offsetParent !== null) {
                o.click();
                return true;
            }
        }
        return false;
    """)
    time.sleep(0.5)

    # Salva e avança pra próxima etapa (a tela de edição normal do produto)
    driver.execute_script("""
        var btns = document.querySelectorAll('button');
        for (var b of btns) {
            var txt = b.textContent.trim().toLowerCase();
            if (txt.indexOf('salvar') !== -1 && txt.indexOf('próxima') !== -1 && b.offsetParent !== null) {
                b.click();
                return true;
            }
        }
        return false;
    """)
    time.sleep(2)
    return True

def usar_categoria_recomendada(driver):
    """
    Abre o seletor de categoria, clica na aba "Recomendação", clica em "Obter Categoria"
    e seleciona a PRIMEIRA sugestão retornada pela plataforma (elementos .category_title).
    A lista de sugestões é sempre variável (depende do produto sendo publicado), por isso
    usamos a posição (primeiro item visível), não o texto.

    Esse app é Vue.js (atributos data-v-*) — o popover de categoria é renderizado fora da
    linha do formulário (não é filho dela no DOM), por isso as buscas aqui são globais no
    documento, não restritas a um container pai.
    Retorna (sucesso: bool, categoria_texto: str|None).
    """
    from selenium.webdriver.support.ui import WebDriverWait
    import time

    try:
        # 1. Abre o seletor de categoria — input identificado pelo placeholder exato
        aberto = driver.execute_script("""
            var input = document.querySelector('#basic input[placeholder="Selecionar uma Categoria"]');
            if (!input) return false;
            input.click();
            return true;
        """)
        if not aberto:
            return False, None
        time.sleep(1)

        # 2. Clica na aba "Recomendação" (busca global — o popover não é filho da linha
        # do formulário) e CONFIRMA que ela ficou ativa antes de seguir.
        def _clicar_aba_recomendacao():
            return driver.execute_script("""
                var tabs = document.querySelectorAll('[role="tab"], .ant-tabs-tab');
                for (var t of tabs) {
                    if (t.textContent.trim().toLowerCase().includes('recomenda') && t.offsetParent !== null) {
                        t.click();
                        return true;
                    }
                }
                return false;
            """)

        aba_ativa = False
        for _tentativa in range(4):
            _clicar_aba_recomendacao()
            time.sleep(0.8)
            aba_ativa = driver.execute_script("""
                var tabs = document.querySelectorAll('[role="tab"]');
                for (var t of tabs) {
                    if (t.getAttribute('aria-selected') === 'true' &&
                        t.textContent.trim().toLowerCase().includes('recomenda')) {
                        return true;
                    }
                }
                var ativa = document.querySelector('.ant-tabs-tab-active');
                return !!(ativa && ativa.textContent.trim().toLowerCase().includes('recomenda'));
            """)
            if aba_ativa:
                break

        if not aba_ativa:
            # Não conseguiu ativar a aba — fecha o popover pra não deixar bloqueando
            # os campos seguintes (Preço, Quantidade) e desiste dessa via.
            driver.execute_script("document.body.click();")
            return False, None

        # Deixa a aba "pensar" (carregar o conteúdo) antes de procurar o botão —
        # a troca de aba fica marcada como ativa antes do conteúdo terminar de renderizar.
        time.sleep(1.2)

        # 3. Clica em "Obter Categoria"
        driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                if (b.textContent.trim().toLowerCase().includes('obter categoria') && b.offsetParent !== null) {
                    b.click();
                    return true;
                }
            }
            return false;
        """)

        # 4. Espera a lista de sugestões carregar dentro da aba ATIVA (.category_title —
        # chamada assíncrona). Restringe a busca à .ant-tabs-tabpane-active porque a
        # aba "Usado Recentemente" também tem .category_title, e sem esse escopo o
        # código clicava no primeiro item dela em vez do primeiro da Recomendação.
        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("""
                    var painel = document.querySelector('.ant-tabs-tabpane-active');
                    if (!painel) return false;
                    var els = painel.querySelectorAll('.category_title');
                    for (var el of els) { if (el.offsetParent !== null) return true; }
                    return false;
                """)
            )
        except:
            pass
        time.sleep(1)

        # 5. Clica no PRIMEIRO resultado visível DENTRO DA ABA ATIVA — a lista é sempre
        # variável (depende do produto), por isso usamos a posição, não o texto.
        categoria_texto = driver.execute_script("""
            var painel = document.querySelector('.ant-tabs-tabpane-active');
            if (!painel) return null;
            var els = painel.querySelectorAll('.category_title');
            for (var el of els) {
                if (el.offsetParent !== null) {
                    var texto = el.textContent.trim();
                    el.click();
                    return texto;
                }
            }
            return null;
        """)

        if categoria_texto:
            time.sleep(0.5)
            return True, categoria_texto

        driver.execute_script("document.body.click();")
        return False, None

    except Exception:
        try:
            driver.execute_script("document.body.click();")
        except:
            pass
        return False, None


def verificar_campos_obrigatorios(driver):
    """
    Varre a tela em busca de mensagens de validação tipo "Campo obrigatório em falta"
    ainda visíveis. Retorna a lista de textos de erro encontrados (vazia se estiver tudo ok).
    """
    try:
        erros = driver.execute_script("""
            var termos = ['obrigatório', 'obrigatoria', 'obrigatório em falta', 'required'];
            var els = document.querySelectorAll(
                '.ant-form-explain, .ant-form-item-explain, .ant-form-item-explain-error, [class*=error]'
            );
            var vistos = new Set();
            var resultado = [];
            for (var el of els) {
                if (el.offsetParent === null) continue;
                var txt = el.textContent.trim();
                if (!txt || vistos.has(txt)) continue;
                var lower = txt.toLowerCase();
                for (var t of termos) {
                    if (lower.includes(t)) {
                        vistos.add(txt);
                        resultado.push(txt);
                        break;
                    }
                }
            }
            return resultado;
        """)
        return erros or []
    except Exception:
        return []