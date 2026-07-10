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

# ── WIDGET PRINCIPAL ──────────────────────────────────────────────────────────

def widget_login_upseller():
    st.markdown("#### 🔐 Login Upseller")

    for k, v in [("ups_etapa", 0), ("ups_driver", None),
                 ("ups_logado", False), ("ups_captcha_img", None), ("ups_captcha_ocr", "")]:
        if k not in st.session_state:
            st.session_state[k] = v

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
                        st.rerun()
                    else:
                        st.error("❌ Código inválido.")
                except Exception as e:
                    st.error(f"Erro: {e}")
        return None

    # ── ETAPA 3: Logado ───────────────────────────────────────────
    if etapa == 3:
        st.success("✅ Upseller conectado! Chrome em background.")
        st.caption("🍪 Sessão salva — próximo acesso será automático!")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚪 Desconectar", use_container_width=True):
                try: st.session_state["ups_driver"].quit()
                except: pass
                deletar_cookies()
                st.session_state["ups_driver"] = None
                st.session_state["ups_logado"] = False
                st.session_state["ups_etapa"] = 0
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

        # ── CATEGORIA via IA ───────────────────────────────────
        try:
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

        # ── IMAGEM ─────────────────────────────────────────────
        imagem = produto.get("imagem", "")
        if imagem and not imagem.startswith("http"):
            imagem = "https://campineira.com.br" + imagem

        if imagem and imagem.startswith("http"):
            try:
                import requests
                import tempfile

                # Baixa a imagem localmente (contorna bloqueio CORS)
                headers = {
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://campineira.com.br/"
                }
                resp = requests.get(imagem, headers=headers, timeout=10)

                if resp.status_code == 200:
                    # Salva temporariamente
                    ext = imagem.split(".")[-1].lower() or "jpg"
                    tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
                    tmp.write(resp.content)
                    tmp.close()
                    caminho_img = os.path.abspath(tmp.name)

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

                    # Remove arquivo temporário
                    try:
                        os.unlink(caminho_img)
                    except:
                        pass

            except Exception as e:
                pass  # Imagem não é crítica

        # ── SALVAR ─────────────────────────────────────────────
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        btn_salvar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
            "#myEditBox > section.my_edit_head.ant-layout > div > div.head_r > div > button"
        )))
        btn_salvar.click()
        time.sleep(3)

        return True, f"✅ Produto '{nome}' publicado! SKU: {sku}"

    except Exception as e:
        return False, f"❌ Erro: {str(e)[:100]}"

# ============================================================
# ETAPA 2 — COPIAR PARA LOJAS
# ============================================================

def etapa2_copiar_para_lojas(driver, sku):
    """
    Acessa lista de produtos, localiza pelo SKU,
    seleciona e copia para lojas (Shopee, TikTok etc).
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
        for sel_chk in [
            f"#app > div.app_box.appBox > section > section > div > main > section.my_content_body > div > div > div > table > tbody > tr:nth-child({linha_match}) > td.w_f_40.check_box_td > label > span > input",
            f"#app > div.app_box.appBox > section > section > div > main > section.my_content_body > div > div > div > table > tbody > tr:nth-child({linha_match}) > td:first-child input[type='checkbox']",
        ]:
            try:
                checkbox = driver.find_element(By.CSS_SELECTOR, sel_chk)
                driver.execute_script("arguments[0].click();", checkbox)
                time.sleep(1)
                break
            except:
                continue

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

        if btn_acoes:
            clique_robusto(btn_acoes)
            time.sleep(1.5)
            # Verifica se o dropdown abriu; se não, tenta de novo
            dropdown_aberto = driver.execute_script("""
                var els = document.querySelectorAll('li, .ant-dropdown-menu-item');
                for (var e of els) {
                    if (e.textContent.trim().toLowerCase().includes('copiar para lojas') && e.offsetParent !== null) {
                        return true;
                    }
                }
                return false;
            """)
            if not dropdown_aberto:
                clique_robusto(btn_acoes)
                time.sleep(1.5)
                # Verifica se o dropdown abriu; se não, tenta clique nativo direto
                dropdown_aberto = driver.execute_script("""
                var els = document.querySelectorAll('li, .ant-dropdown-menu-item');
                for (var e of els) {
                    if (e.textContent.trim().toLowerCase().includes('copiar para lojas') && e.offsetParent !== null) {
                        return true;
                    }
                }
                return false;
            """)
            if not dropdown_aberto:
                try:
                    btn_acoes.click()
                    time.sleep(1)
                except:
                    pass
        time.sleep(1)

        # 6. Clica em "Copiar para Lojas" — busca por texto é mais confiável aqui
        clicou_copiar = False
        for tentativa in range(2):
            try:
                itens_menu = driver.find_elements(By.CSS_SELECTOR, "li, .ant-dropdown-menu-item, div")
                for item in itens_menu:
                    txt = item.text.strip().lower()
                    if txt == "copiar para lojas" and item.is_displayed():
                        clique_robusto(item)
                        clicou_copiar = True
                        break
            except:
                pass
            if clicou_copiar:
                break
            time.sleep(1)

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
            return False, "❌ Não conseguiu abrir o modal 'Copiar para Lojas'. Tente clicar manualmente uma vez para destravar."

        # 7. Seleciona loja (apenas "Shopee" coluna esquerda, não "UP Shopee")
        loja_nome = "Desconhecida"
        try:
            checkboxes_loja = driver.find_elements(By.CSS_SELECTOR,
                ".checkbox_box .all_box label, .ant-modal-body .checkbox_box label, .ant-modal-body label"
            )
            for box in checkboxes_loja:
                try:
                    texto_box = box.text.strip().lower()
                    # Precisa ser exatamente "shopee", não "up shopee"
                    if texto_box == "shopee":
                        chk = box.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                        driver.execute_script("arguments[0].click();", chk)
                        loja_nome = box.text.strip()
                        time.sleep(1)
                        break
                except:
                    continue
        except:
            pass

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

        # 2. Valida SKU no rascunho
        try:
            sku_cell = driver.find_element(By.CSS_SELECTOR,
                "#app > div.app_box.appBox > section > section > main > section.my_content_body > div > div > div > table > tbody > tr > td:nth-child(4) > div > div:nth-child(1) > span"
            )
            if sku_cell.text.strip() != sku:
                return False, f"❌ SKU no rascunho ({sku_cell.text.strip()}) não confere com {sku}", None
        except:
            return False, "❌ Não encontrou rascunho", None

        # 3. Clica em Editar — seletor confirmado primeiro, depois fallbacks
        btn_editar = None
        for sel_edit in [
            "#app > div.app_box.appBox > section > section > div > main > section.my_content_body > div > div > div > table > tbody > tr:nth-child(1) > td.td_action.w_f_90 > div > div > div > a",
            "#app > div.app_box.appBox > section > section > main > section.my_content_body > div > div > div > table > tbody > tr > td.w_f_100 > div > div > div > a",
            "td.td_action a", "td.w_f_100 a", "table tbody tr:first-child a"
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel_edit)
                if el.is_displayed():
                    btn_editar = el
                    break
            except:
                continue

        if not btn_editar:
            return False, "❌ Botão Editar não encontrado no rascunho", None

        href = btn_editar.get_attribute("href")
        if href:
            driver.execute_script("window.open(arguments[0]);", href)
        else:
            driver.execute_script("arguments[0].click();", btn_editar)
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
        """Helper para preencher campo com retry."""
        try:
            campo = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, seletor)))
            driver.execute_script("arguments[0].scrollIntoView(true);", campo)
            time.sleep(0.3)
            if limpar:
                campo.click()
                campo.send_keys(Keys.CONTROL + "a")
                campo.send_keys(Keys.DELETE)
            campo.send_keys(str(valor))
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
            # Abre o seletor de categoria
            try:
                campo_cat = driver.find_element(By.CSS_SELECTOR,
                    "#basic input[placeholder*='Categoria'], #basic input[placeholder*='categoria'], .category_select_box"
                )
                driver.execute_script("arguments[0].click();", campo_cat)
                time.sleep(1)
            except:
                pass

            # Tenta usar "Recomendação" + "Obter Categoria" (sugestão da própria plataforma)
            ok_recomendada = usar_categoria_recomendada(driver)

            # Se não funcionou, usa categoria sugerida pela IA (capturada na etapa anterior)
            if not ok_recomendada and categoria_selecionada:
                selecionar_categoria_no_dropdown(driver, categoria_selecionada)
            time.sleep(1)

        # ── MARCA (Fabricante) ────────────────────────────────
        fabricante = produto.get("fabricante", "")
        if fabricante:
            preencher_campo(
                "#specification > div.ant-card-body > div > form:nth-child(1) > div > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div > div.input_box > input",
                fabricante
            )
            time.sleep(0.5)

        # ── PREÇO (Shopee = preco_shopee calculado) ───────────
        preco = produto.get("preco_shopee") or produto.get("preco_num", 0)
        if preco:
            try:
                campo_preco = driver.find_element(By.CSS_SELECTOR,
                    "#sales > div.ant-card-body > div > div > form > div:nth-child(1) > div.ant-col.ant-col-15, " +
                    "#sales input[type='text'], #sales input[type='number']"
                )
                campo_preco.click()
                campo_preco.send_keys(Keys.CONTROL + "a")
                campo_preco.send_keys(Keys.DELETE)
                campo_preco.send_keys(f"{float(preco):.2f}")
                time.sleep(0.5)
            except:
                pass

        # ── QUANTIDADE (fixo 100) ─────────────────────────────
        preencher_campo(
            "#sales > div.ant-card-body > div > div > form > div:nth-child(2) > div.ant-col.ant-col-20.ant-form-item-control-wrapper > div > span > div > div.ant-input-number-input-wrap > input",
            "100"
        )
        time.sleep(0.5)

        # ── PESO via IA (+50g embalagem) ───────────────────────
        descricao_peso = " ".join(filter(None, [
            produto.get("peso") or produto.get("peso_aproximado", ""),
            produto.get("composicao", ""),
            produto.get("tamanho") or produto.get("tamanho_aproximado", ""),
        ]))
        peso_final = extrair_peso_ia(descricao_peso, produto.get("nome", ""))
        if peso_final:
            try:
                campo_peso = driver.find_element(By.CSS_SELECTOR,
                    "#shopping > div.ant-card-body > div > form > div.weight_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15 input, " +
                    "#shopping input[placeholder*='Peso'], #shopping input[placeholder*='peso']"
                )
                # Só preenche se estiver vazio
                if not campo_peso.get_attribute("value"):
                    campo_peso.click()
                    campo_peso.send_keys(peso_final)
                    time.sleep(0.3)
            except:
                pass

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
        time.sleep(0.3)

        # Comprimento
        preencher_campo(
            "#shopping > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span.my_input_number_box.w_140.t_l.ml_12.show_addon_after.style_type1 > div > div.ant-input-number-input-wrap > input",
            dims["comprimento"]
        )
        time.sleep(0.3)

        # Altura
        preencher_campo(
            "#shopping > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span.my_input_number_box.t_r.w_140.ml_12.show_addon_after.style_type1 > div > div.ant-input-number-input-wrap > input",
            dims["altura"]
        )
        time.sleep(0.3)

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
    """Clica no botão Publicar do rascunho."""
    import time
    clicar(driver, "#myEditBox > section.my_edit_head.ant-layout > div > div.head_r > div:nth-child(2) > button")
    time.sleep(3)
    fechar_modais(driver)
    return True, "✅ Publicado na plataforma!"


# ============================================================
# ETAPA 4 — MIGRAR ANÚNCIO PARA SHEIN/TIKTOK/TEMU
# ============================================================

LOJAS_MAPA = {
    "shein":  {"nth": 3, "url_rascunho": "https://app.upseller.com/pt/products/shein/drafts"},
    "tiktok": {"nth": 5, "url_rascunho": "https://app.upseller.com/pt/products/tiktok/drafts"},
    "temu":   {"nth": 7, "url_rascunho": "https://app.upseller.com/pt/products/temu/drafts"},
}

def etapa4_migrar_para_lojas(driver, sku):
    """
    Acessa migração de anúncio Shopee → outras lojas.
    Seleciona Shein, TikTok e Temu se disponíveis.
    """
    from selenium.webdriver.common.by import By
    import time

    try:
        driver.get("https://app.upseller.com/pt/products/product-moving/shopee")
        time.sleep(3)
        fechar_popup(driver)

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

        # Valida SKU na linha
        linhas = driver.find_elements(By.CSS_SELECTOR,
            "#app > div.app_box.appBox > section > section > main > section.my_content_body > div > div > div > table > tbody > tr"
        )
        linha_match = None
        for i, linha in enumerate(linhas):
            try:
                sku_cell = linha.find_element(By.CSS_SELECTOR, "td.w_m_150 > div > div.line_overflow")
                if sku_cell.text.strip() == sku:
                    linha_match = i + 1
                    break
            except:
                continue

        if linha_match is None:
            return False, f"❌ SKU {sku} não encontrado na migração"

        # Flag na linha correta
        clicar(driver, f"#app > div.app_box.appBox > section > section > main > section.my_content_body > div > div > div > table > tbody > tr:nth-child({linha_match}) > td.w_f_40.check_box_td > label > span > input")
        time.sleep(0.5)

        # Clica "Copiar para Lojas"
        clicar(driver, "#productMovingStep1 > button")
        time.sleep(2)

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
                    clicar(driver, f"{base_sel} > div.ant-col.ant-col-5 > label > span.ant-checkbox > input")
                    lojas_selecionadas.append(nome_loja)
            except:
                continue

        # Confirma
        clicar(driver,
            "body > div:nth-child(26) > div > div.ant-modal-wrap > div > div.ant-modal-content > div.ant-modal-footer > div > div:nth-child(2) > div > div.ant-space.ant-space-horizontal.ant-space-align-center > div:nth-child(2) > button"
        )
        time.sleep(4)
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

        # Valida SKU no rascunho
        sel_sku_shein  = "#app > div.app_box.appBox > section > section > main > section.my_content_body > div > div > div > table > tbody > tr > td.w_m_160 > div > div.line_overflow.flex > span"
        sel_sku_outros = "#app > div.app_box.appBox > section > section > main > section.my_content_body > div > div > div > table > tbody > tr > td:nth-child(4) > div > div:nth-child(1) > span"

        sku_encontrado = False
        for sel in [sel_sku_shein, sel_sku_outros]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip() == sku:
                    sku_encontrado = True
                    break
            except:
                continue

        if not sku_encontrado:
            return False, f"❌ SKU {sku} não encontrado no rascunho {plataforma}"

        # Clica Editar
        btn_editar = driver.find_element(By.CSS_SELECTOR,
            "#app > div.app_box.appBox > section > section > main > section.my_content_body > div > div > div > table > tbody > tr > td.w_f_100 > div > div > div > a"
        )
        href = btn_editar.get_attribute("href")
        driver.execute_script("window.open(arguments[0]);", href)
        time.sleep(3)
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(2)
        fechar_popup(driver)

        # Categoria via IA
        categorias = capturar_categorias_disponiveis(driver)
        if categorias:
            cat_sugerida = sugerir_categoria_ia(produto.get("nome",""), categorias)
            if cat_sugerida:
                # Tenta digitar no campo de busca da categoria
                try:
                    campo_cat = driver.find_element(By.CSS_SELECTOR,
                        "#basic > div.ant-card-body > div > form > div:nth-child(3) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div.category_select_box > div > span > input"
                    )
                    campo_cat.click()
                    time.sleep(0.5)
                    campo_cat.send_keys(cat_sugerida[:20])
                    time.sleep(1)
                except:
                    pass

        # Monta descrição para IA
        desc = " ".join(filter(None, [
            produto.get("tamanho") or produto.get("tamanho_aproximado",""),
            produto.get("composicao",""),
            produto.get("peso") or produto.get("peso_aproximado",""),
        ]))

        # Peso via IA
        peso_ia = extrair_peso_ia(desc, produto.get("nome",""))
        # Dimensões via IA
        dims = extrair_dimensoes_ia(desc, produto.get("nome",""))

        # Preço da plataforma
        preco = produto.get(f"preco_{plataforma.lower()}", 0) or 0

        if plataforma.lower() == "shein":
            # Campos Shein (tabela variants)
            base = "#variants > div.ant-card-body > div.card_body > div.variation_list > div.variation_list_body > div > div.vxe-table--render-wrapper > div.vxe-table--main-wrapper > div.vxe-table--body-wrapper.body--wrapper > table > tbody > tr"

            if preco:
                preencher_input(driver, f"{base} > td.vxe-body--column.col_5.col--right > div > span > div > div.ant-input-number-input-wrap > input", f"{float(preco):.0f}")

            if peso_ia:
                preencher_input(driver, f"{base} > td.vxe-body--column.col_7.col--left > div > span > div > div.ant-input-number-input-wrap > input", peso_ia)

            preencher_input(driver, f"{base} > td.vxe-body--column.col_8.col--left > div > div > span:nth-child(1) > div > div.ant-input-number-input-wrap > input", dims["comprimento"])
            preencher_input(driver, f"{base} > td.vxe-body--column.col_8.col--left > div > div > span:nth-child(3) > div > div.ant-input-number-input-wrap > input", dims["largura"])
            preencher_input(driver, f"{base} > td.vxe-body--column.col_8.col--left > div > div > span:nth-child(5) > div > div.ant-input-number-input-wrap > input", dims["altura"])

        else:
            # Campos Temu/TikTok (similar ao Shopee)
            if preco:
                try:
                    campos_preco = driver.find_elements(By.CSS_SELECTOR, "#sales input[type='text'], #sales input[type='number']")
                    if campos_preco:
                        preencher_input(driver, None, f"{float(preco):.2f}")
                except:
                    pass

            if peso_ia:
                preencher_input(driver,
                    "#shopping > div.ant-card-body > div > form > div.weight_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15 input",
                    peso_ia
                )

            preencher_input(driver,
                "#shopping > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span:nth-child(1) > div > div.ant-input-number-input-wrap > input",
                dims["largura"]
            )
            preencher_input(driver,
                "#shopping > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span.my_input_number_box.w_140.t_l.ml_12.show_addon_after.style_type1 > div > div.ant-input-number-input-wrap > input",
                dims["comprimento"]
            )
            preencher_input(driver,
                "#shopping > div.ant-card-body > div > form > div.size_item.ant-row.ant-form-item.ant-form-item-with-help > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > span.my_input_number_box.t_r.w_140.ml_12.show_addon_after.style_type1 > div > div.ant-input-number-input-wrap > input",
                dims["altura"]
            )

            # Temu: tempo de envio + modelo automático + país de origem
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

        # Publicar
        time.sleep(1)
        clicar(driver, "#myEditBox > section.my_edit_head.ant-layout > div > div.head_r > div:nth-child(2) > button")
        time.sleep(3)
        fechar_modais(driver)

        # Fecha aba e volta para anterior
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[-1])

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

def usar_categoria_recomendada(driver):
    """
    Abre o seletor de categoria, clica na aba "Recomendação"
    e clica no botão "Obter Categoria" (sugestão automática da plataforma).
    Retorna True se conseguiu, False se não.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    import time

    try:
        # Clica na aba "Recomendação" (segunda aba do popover)
        clicou_aba = driver.execute_script("""
            var sels = [
                "#basic > div.ant-card-body > div > form > div:nth-child(3) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div.category_select_box > div > div > div > div > div > div.ant-popover-inner > div > div > div > div.ant-tabs-bar.ant-tabs-top-bar > div > div > div > div > div:nth-child(1) > div:nth-child(2)",
                "#basic > div.ant-card-body > div > form > div:nth-child(4) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div.category_select_box > div > div > div > div > div > div.ant-popover-inner > div > div > div > div.ant-tabs-bar.ant-tabs-top-bar > div > div > div > div > div:nth-child(1) > div:nth-child(2)"
            ];
            for (var s of sels) {
                var el = document.querySelector(s);
                if (el && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            // Fallback: busca por texto "Recomendação"
            var tabs = document.querySelectorAll('.ant-tabs-tab, [class*=tab]');
            for (var t of tabs) {
                if (t.textContent.trim().toLowerCase().includes('recomenda') && t.offsetParent !== null) {
                    t.click();
                    return true;
                }
            }
            return false;
        """)
        time.sleep(1)

        # Clica no botão "Obter Categoria"
        clicou_btn = driver.execute_script("""
            var sels = [
                "#basic > div.ant-card-body > div > form > div:nth-child(3) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div.category_select_box > div > div > div > div > div > div.ant-popover-inner > div > div > div > div.ant-tabs-content.ant-tabs-content-animated.ant-tabs-top-content > div.ant-tabs-tabpane.ant-tabs-tabpane-active > div.my_empty.mt_50.ant-empty.ant-empty-normal > div.ant-empty-footer > div > div > div > button",
                "#basic > div.ant-card-body > div > form > div:nth-child(4) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > div.category_select_box > div > div > div > div > div > div.ant-popover-inner > div > div > div > div.ant-tabs-content.ant-tabs-content-animated.ant-tabs-top-content > div.ant-tabs-tabpane.ant-tabs-tabpane-active > div.my_empty.mt_50.ant-empty.ant-empty-normal > div.ant-empty-footer > div > div > div > button"
            ];
            for (var s of sels) {
                var el = document.querySelector(s);
                if (el && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            // Fallback: busca por texto "Obter Categoria"
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                if (b.textContent.trim().toLowerCase().includes('obter categoria') && b.offsetParent !== null) {
                    b.click();
                    return true;
                }
            }
            return false;
        """)
        time.sleep(2)

        return clicou_btn

    except Exception as e:
        return False