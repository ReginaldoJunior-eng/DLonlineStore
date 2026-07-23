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
TABLE_SESSAO_UPSELLER = "leandro-marketplace.DL_Store_Online.tb_upseller_sessao"

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
# Sessão do Upseller salva pra sobreviver a F5 (login automático). Prioriza
# BigQuery (tb_upseller_sessao) — o arquivo local (COOKIES_FILE) é apagado toda
# vez que o Streamlit Cloud reinicia o container, o que forçava login manual de
# novo depois de qualquer redeploy/restart mesmo com a sessão ainda válida.
# O arquivo local só entra como fallback se o BigQuery estiver indisponível.

def _carregar_cookies_salvos(client=None):
    """Retorna a lista de cookies salva, ou None se não tiver nenhuma sessão."""
    if client:
        try:
            df = client.query(
                f"SELECT cookies_json FROM `{TABLE_SESSAO_UPSELLER}` WHERE id = 'cookies'"
            ).to_dataframe()
            if not df.empty:
                return json.loads(df.iloc[0]["cookies_json"])
        except Exception:
            pass
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return None

def existe_sessao_salva(client=None):
    return _carregar_cookies_salvos(client) is not None

def salvar_cookies(driver, client=None):
    try:
        cookies = driver.get_cookies()
    except Exception:
        return False
    if client:
        try:
            import pandas as pd
            from google.cloud import bigquery
            from datetime import datetime
            df = pd.DataFrame([{
                "id": "cookies",
                "cookies_json": json.dumps(cookies),
                "data_atualizacao": datetime.utcnow().isoformat(),
            }])
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
            client.load_table_from_dataframe(df, TABLE_SESSAO_UPSELLER, job_config=job_config).result()
            return True
        except Exception:
            pass
    try:
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f)
        return True
    except:
        return False

def login_por_cookies(driver, client=None):
    cookies = _carregar_cookies_salvos(client)
    if cookies is None:
        return False
    try:
        driver.get(UPSELLER_URL)
        time.sleep(2)
        for cookie in cookies:
            try: driver.add_cookie(cookie)
            except: pass
        driver.refresh()
        time.sleep(3)
        return "login" not in driver.current_url
    except:
        return False

def deletar_cookies(client=None):
    if client:
        try:
            client.query(f"DELETE FROM `{TABLE_SESSAO_UPSELLER}` WHERE id = 'cookies'").result()
        except Exception:
            pass
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

    # Modal "Avisos" (novidades/eventos, carrossel de vários slides) — não tem X,
    # só "Anterior"/"Próximo". Precisa clicar em "Próximo" até esgotar os slides
    # (o botão vira "Concluir"/"Entendi"/"OK" no último, ou o modal some sozinho).
    # Sem isso, o fallback abaixo (clicar no primeiro <button> do modal) clicava
    # em "Anterior" por engano — um no-op que deixava o modal aberto bloqueando
    # a tela inteira pros cliques seguintes (foi a causa real de o Exportar
    # nunca abrir: não era o botão em si, era esse popup por cima de tudo).
    try:
        for _ in range(10):
            avancou = False
            for txt in ["Próximo", "Next", "Concluir", "Entendi", "OK"]:
                btns = driver.find_elements(By.XPATH, f"//button[contains(., '{txt}')]")
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
                        avancou = True
                        fechou = True
                        break
                if avancou:
                    break
            if not avancou:
                break
    except:
        pass

    time.sleep(1)

    # Verifica se ainda tem modal — clica no botão mais à direita (geralmente
    # "Próximo"/"Fechar"/"OK", nunca "Anterior"/"Voltar", que é sempre o
    # primeiro e um no-op na tela em que o modal abre).
    try:
        modais = driver.find_elements(By.CSS_SELECTOR, ".ant-modal-wrap:not([style*='display: none'])")
        if modais:
            for modal in modais:
                try:
                    botoes = [b for b in modal.find_elements(By.CSS_SELECTOR, "button") if b.is_displayed()]
                    botoes = [b for b in botoes if b.text.strip().lower() not in ("anterior", "voltar", "back", "previous")]
                    if botoes:
                        driver.execute_script("arguments[0].click();", botoes[-1])
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

def _chromium_do_sistema():
    """Detecta automaticamente o Chromium instalado via packages.txt (Streamlit
    Cloud/Debian) — em vez de depender de uma secret configurada manualmente
    (frágil: fácil esquecer, errar a ordem no TOML, ou não reiniciar o app depois).
    Retorna (caminho_binario, caminho_chromedriver) ou (None, None) se não achar."""
    import os
    for bin_path in ["/usr/bin/chromium", "/usr/bin/chromium-browser"]:
        if os.path.exists(bin_path):
            for drv_path in ["/usr/bin/chromedriver", "/usr/lib/chromium/chromedriver", "/usr/lib/chromium-browser/chromedriver"]:
                if os.path.exists(drv_path):
                    return bin_path, drv_path
    return None, None

def criar_driver(pasta_download=None):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    # Pasta de download fixa (em vez da pasta padrão do usuário) — usado pela
    # exportação de pedidos, pra sabermos exatamente onde o Excel baixado vai parar.
    if pasta_download:
        import os
        os.makedirs(pasta_download, exist_ok=True)
        opts.add_experimental_option("prefs", {
            "download.default_directory": os.path.abspath(pasta_download),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        })

    # Se existe um Chromium instalado no sistema (packages.txt no Streamlit Cloud),
    # usa ele direto e roda headless — é sinal de que estamos num servidor sem tela.
    # Localmente esse caminho não existe, então cai no Chrome normal (visível, via
    # webdriver_manager) sem precisar configurar nada.
    bin_path, drv_path = _chromium_do_sistema()
    if bin_path and drv_path:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.binary_location = bin_path
        driver = webdriver.Chrome(service=Service(drv_path), options=opts)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

    if pasta_download:
        # Chrome headless (novo modo) bloqueia download por segurança a não ser que
        # seja liberado explicitamente via CDP — as "prefs" sozinhas não bastam nesse modo.
        try:
            driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": os.path.abspath(pasta_download),
            })
        except Exception:
            pass
    return driver

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

def _tentar_reconectar_via_cookies(client=None):
    """Recria o driver e loga de novo usando os cookies salvos, sem exigir login
    manual — usado quando a sessão anterior morreu (Chrome fechado, travado etc.)
    mas ainda temos uma sessão válida guardada. Retorna o novo driver ou None."""
    if not existe_sessao_salva(client):
        return None
    try:
        novo_driver = criar_driver()
        if login_por_cookies(novo_driver, client):
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

def widget_login_upseller(client=None):
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
            novo_driver = _tentar_reconectar_via_cookies(client)
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
        tem_cookies = existe_sessao_salva(client)

        if tem_cookies:
            st.info("🍪 Sessão anterior encontrada!")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("⚡ Login Automático", type="primary", use_container_width=True):
                    with st.spinner("Restaurando sessão..."):
                        driver = criar_driver()
                        if login_por_cookies(driver, client):
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
                            deletar_cookies(client)
                            st.warning("⚠️ Sessão expirada. Faça login manual.")
                            st.rerun()
            with col2:
                if st.button("🌐 Login Manual", use_container_width=True):
                    deletar_cookies(client)
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
                            salvar_cookies(driver, client)
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
                        salvar_cookies(driver, client)
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
                deletar_cookies(client)
                st.session_state["ups_driver"] = None
                st.session_state["ups_logado"] = False
                st.session_state["ups_etapa"] = 0
                estado_global["driver"] = None
                estado_global["logado"] = False
                st.rerun()
        with c2:
            if st.button("🗑️ Limpar sessão salva", use_container_width=True):
                deletar_cookies(client)
                st.info("Cookies removidos.")
        return st.session_state["ups_driver"]

    return None

# ============================================================
# PUBLICAÇÃO DE PRODUTO NO UPSELLER
# ============================================================

SKU_COUNTER_FILE = "upseller_sku_counter.json"

def get_proximo_sku(client=None):
    """Retorna o próximo SKU no formato RJ-00001, RJ-00002... Consulta o maior
    número já registrado em tb_sku_registrados (BigQuery) em vez de um contador
    em arquivo local — o arquivo local é apagado toda vez que o Streamlit Cloud
    reinicia o container, o que fazia o contador "esquecer" a posição e reemitir
    SKUs que já tinham sido usados de verdade no Upseller (causa real do erro
    "SKU já existe" em produção, mesmo sem ninguém ter reaproveitado nada à mão).
    tb_sku_registrados nunca é limpa, então sempre reflete a realidade.
    Só cai pro arquivo local se o BigQuery estiver indisponível (fallback, não
    fonte principal — nesse caso o número pode ficar defasado de novo)."""
    if client:
        try:
            q = """
                SELECT MAX(CAST(SUBSTR(sku, 4) AS INT64)) AS max_num
                FROM `leandro-marketplace.DL_Store_Online.tb_sku_registrados`
                WHERE sku LIKE 'RJ-%'
            """
            df = client.query(q).to_dataframe()
            max_num = df["max_num"].iloc[0]
            num = int(max_num or 0) + 1
            return f"RJ-{num:05d}"
        except Exception:
            pass
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
    # `not tamanho_str` não pega NaN (float do pandas pra campo NULL) — NaN é
    # "truthy" em Python. Sem essa checagem de tipo, um produto sem tamanho
    # cadastrado quebrava aqui com "expected string or bytes-like object, got
    # 'float'" assim que a lista passou a vir do BigQuery (via pandas).
    if not tamanho_str or not isinstance(tamanho_str, str):
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
    # Mesmo caso de extrair_dimensoes: NaN (pandas/BigQuery) é truthy, `not
    # peso_str` sozinho não pega.
    if not peso_str or not isinstance(peso_str, str):
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

def _mensagem_erro_legivel(e):
    """Selenium às vezes lança uma exceção com uma stacktrace NATIVA do
    Chrome/chromedriver no lugar de uma mensagem normal (endereços de memória,
    frames "<unknown>") — geralmente sinal de que a sessão do navegador travou
    ou morreu no meio de uma ação (não é erro do nosso código). Em vez de
    despejar esse texto técnico na tela, detecta o padrão e devolve algo que
    a pessoa consegue entender e agir em cima."""
    texto = str(e)
    if 'stacktrace' in texto.lower() or 'invalid session id' in texto.lower() or 'session deleted' in texto.lower():
        return "sessão do Chrome caiu/desconectou no meio da ação — desconecta e loga de novo no Upseller, depois tenta reprocessar"
    primeira_linha = texto.split('\n')[0].strip()
    if not primeira_linha or len(primeira_linha) < 3:
        return "erro desconhecido do navegador (a sessão pode ter caído) — tente reprocessar"
    return primeira_linha[:150]

def publicar_produto_upseller(driver, produto, client=None):
    """
    Publica um produto no Upseller.
    client: conexão BigQuery, passada pra get_proximo_sku() gerar o SKU a partir
    de tb_sku_registrados (fonte confiável) em vez de um contador local.
    Retorna (sucesso, mensagem, sku_usado) — sku_usado é o mesmo valor que foi
    de fato digitado no formulário do Upseller (ou None se o erro aconteceu antes
    de gerar um), pra quem chamar não precisar reconsultar o contador por conta
    própria (fonte de uma divergência real vista em produção).
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    import time

    sku = None

    wait = WebDriverWait(driver, 15)

    try:
        # 1. Abre página de criar produto
        driver.get("https://app.upseller.com/pt/products/product-add?productType=single")
        time.sleep(3)

        # Fecha popup se aparecer
        fechar_popup(driver)
        time.sleep(1)

        # ── SKU ────────────────────────────────────────────────
        sku = get_proximo_sku(client)
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
        # tb_sku_registrados pode ter buracos (SKU criado de verdade no Upseller
        # em algum teste antigo, sem ficar registrado aqui — já aconteceu) — então
        # o próximo número "calculado" pode colidir mesmo estando certo pela nossa
        # conta. Em vez de desistir na primeira colisão de SKU (não de EAN/GTIN,
        # que reincidir não resolve), tenta de novo com o número seguinte, até
        # 5 vezes, só reenviando o campo de SKU e clicando Salvar de novo.
        erro_validacao = None
        MAX_TENTATIVAS_SKU = 5
        sku_num = int(sku.split('-')[1])
        for tentativa in range(MAX_TENTATIVAS_SKU):
            if tentativa > 0:
                sku_num += 1
                sku = f"RJ-{sku_num:05d}"
                # wait.until (não find_element cru) — a tela pode ainda estar se
                # ajustando logo depois do erro da tentativa anterior, e
                # find_element sem espera nenhuma quebra na hora com "no such
                # element" se o campo não estiver presente nesse exato instante.
                campo_sku = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
                    "#basic > div.ant-card-body > div > form > div:nth-child(1) > div.ant-col.ant-col-15.ant-form-item-control-wrapper > div > span > input"
                )))
                campo_sku.clear()
                campo_sku.send_keys(sku)

            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            btn_salvar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
                "#myEditBox > section.my_edit_head.ant-layout > div > div.head_r > div > button"
            )))
            btn_salvar.click()
            time.sleep(3)

            # Antes de reportar sucesso, checa se o Upseller recusou o salvamento
            # (ex: "Erro: 7899866278400 O código de barra já existe") — sem isso,
            # o código clicava Salvar, esperava 3s e SEMPRE retornava sucesso,
            # mesmo quando o produto não foi criado de verdade.
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
            if erro_validacao and "product-add" not in driver.current_url:
                # A URL mudou (saiu da tela de criar produto) — o produto foi
                # criado de verdade, o texto "já existe" que apareceu é sobra de
                # alguma notificação antiga ainda visível na tela, não um erro
                # desse envio específico. Confirmado: RJ-00027 a RJ-00031 saíram
                # "com erro" pra gente mas existem de verdade e ativos no
                # Upseller — cada tentativa criava o produto mesmo reportando
                # falha, e o retry consumia números à toa achando que precisava
                # tentar de novo.
                erro_validacao = None
            if not erro_validacao:
                break
            # Só vale re-tentar se for colisão de SKU — colisão de EAN/código de
            # barra não some trocando o SKU, é o mesmo produto de novo.
            if 'sku' not in erro_validacao.lower():
                break

        if erro_validacao:
            return False, f"❌ {erro_validacao} (SKU tentado: {sku})", sku

        aviso_imagem = "" if imagem_status == "imagem enviada" else f" ⚠️ Imagem: {imagem_status}."
        return True, f"✅ Produto '{nome}' publicado! SKU: {sku}.{aviso_imagem}", sku

    except Exception as e:
        return False, f"❌ Erro: {_mensagem_erro_legivel(e)}", sku

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


# ============================================================
# EXPORTAR PEDIDOS ENVIADOS (pra alimentar o Dashboard Financeiro)
# ============================================================

def exportar_pedidos_shipped_upseller(driver, pasta_download, data_inicio_custom=None, data_fim_custom=None):
    """Automatiza a exportação de TODOS os pedidos de 'Pedidos > Enviado' do
    Upseller pra Excel: Exportar > Exportar Todos os Pedidos > mantém os 3
    checkboxes (Informação do Produto/Pedido, SKU Armazém) marcados > Exportar >
    captura o número máximo de página > insere no campo de páginas > Exportar >
    espera processar > Baixar.

    Funciona com QUALQUER driver, mesmo um já aberto/logado antes (reaproveitado
    da sessão global do Upseller) — configura o comportamento de download via CDP
    aqui dentro, em vez de depender de ter sido criado com criar_driver(pasta_download=...)
    (que só configura no momento da criação, e o driver desse app geralmente já
    existe de um login anterior).

    data_inicio_custom / data_fim_custom (datetime.date, opcional): substitui o
    período padrão (1º dia do mês anterior até o último dia do mês atual) por um
    intervalo customizado — usado pra reimportar um histórico mais antigo (ex:
    voltar até 01/01). IMPORTANTE: os dois painéis do calendário são ligados e
    SEMPRE mostram meses adjacentes (esquerda = mês N, direita = mês N+1) — só
    dá pra selecionar um intervalo dentro do mesmo mês ou de dois meses
    seguidos. Pra cobrir um ano inteiro, chame essa função VÁRIAS VEZES com
    janelas de 2 meses adjacentes (jan-fev, mar-abr, ...) em vez de uma vez só
    com o ano inteiro — ver importar_historico_completo_upseller() em
    LeMarketplace.py, que já faz esse loop. Se data_inicio_custom pedir um mês
    mais antigo que o padrão (mês anterior ao atual), navega o painel esquerdo
    pra trás um número EXATO de vezes, calculado por matemática de data (não
    "tenta até achar" — foi assim que uma tentativa antiga desandou).

    Retorna (sucesso: bool, caminho_do_arquivo_ou_mensagem_de_erro: str).
    """
    from selenium.webdriver.common.by import By
    import glob

    try:
        os.makedirs(pasta_download, exist_ok=True)
        try:
            driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": os.path.abspath(pasta_download),
            })
        except Exception:
            pass

        driver.get("https://app.upseller.com/pt/order/shipped")
        time.sleep(3)
        fechar_popup(driver)

        # A URL direta às vezes cai numa tela geral de "Processando Pedidos" (com
        # abas Para Reservar/Emitir/Enviar/Imprimir/Retirada/Enviado/Outras/Anulado)
        # em vez de já abrir a lista filtrada de Enviados de verdade — clica na aba
        # "Enviado" pra garantir que caiu na tela certa (idempotente: se já estiver
        # nela, só recarrega a mesma lista).
        clicou_aba_enviado = driver.execute_script("""
            var candidatos = document.querySelectorAll('a, li, span, div');
            for (var el of candidatos) {
                if (el.children.length > 0) continue;
                if (el.textContent.trim() === 'Enviado' && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        if clicou_aba_enviado:
            time.sleep(2)

        # 0. Troca o filtro de data de "Hora de Envio" pra "Hora do Pagamento" e
        # seleciona sempre do 1º dia do mês ANTERIOR até o último dia do mês ATUAL —
        # cobre venda com pagamento confirmado atrasado, mesmo de pedido mais antigo.
        # Datas calculadas aqui (não é input manual, roda sozinho toda vez).
        import datetime as _dt
        import calendar as _cal
        hoje = _dt.date.today()
        primeiro_mes_atual = hoje.replace(day=1)
        ultimo_mes_atual = hoje.replace(day=_cal.monthrange(hoje.year, hoje.month)[1])
        mes_anterior_fim = primeiro_mes_atual - _dt.timedelta(days=1)
        primeiro_mes_anterior = mes_anterior_fim.replace(day=1)
        data_inicio, data_fim = primeiro_mes_anterior, ultimo_mes_atual
        if data_inicio_custom is not None:
            data_inicio = data_inicio_custom
        if data_fim_custom is not None:
            data_fim = data_fim_custom

        # Abre o dropdown que hoje mostra "Hora de Envio"
        driver.execute_script("""
            var els = document.querySelectorAll('.ant-select-selection-selected-value');
            for (var el of els) {
                if (el.textContent.trim() === 'Hora de Envio' && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        time.sleep(1)

        # Clica "Hora do Pagamento" na lista que abriu
        driver.execute_script("""
            var itens = document.querySelectorAll('li, div, span');
            for (var el of itens) {
                if (el.textContent.trim() === 'Hora do Pagamento' && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)
        time.sleep(1)

        # Abre o calendário de intervalo de datas
        driver.execute_script("""
            var input = document.querySelector('input.ant-calendar-range-picker-input');
            if (input) { input.click(); return true; }
            return false;
        """)
        time.sleep(1)

        # Os dois painéis do calendário são ligados (esquerda = mês N, direita =
        # mês N+1, sempre adjacentes) — por padrão mostram mês anterior + mês
        # atual. Se data_inicio pedir um mês mais antigo que isso (backfill de
        # histórico), navega o painel esquerdo pra trás um número EXATO de vezes
        # (calculado por matemática de data, não "tenta até achar" — foi assim
        # que uma tentativa antiga desandou e "foi parar em dezembro" sem querer).
        # Clique real do Selenium (mousedown/mouseup de verdade), não só JS —
        # mesmo motivo do botão Exportar: o listener do Vue pode não disparar
        # só com .click() sintético.
        meses_navegar_atras = (primeiro_mes_anterior.year - data_inicio.year) * 12 + (primeiro_mes_anterior.month - data_inicio.month)
        if meses_navegar_atras > 0:
            from selenium.webdriver.common.action_chains import ActionChains
            MAX_NAVEGACAO = 36  # 3 anos — teto de segurança, nunca passa disso
            cliques = min(meses_navegar_atras, MAX_NAVEGACAO)
            for _ in range(cliques):
                try:
                    seta_prev = None
                    for el in driver.find_elements(By.CSS_SELECTOR, "a.ant-calendar-prev-month-btn"):
                        if el.is_displayed():
                            seta_prev = el
                            break
                    if not seta_prev:
                        break
                    ActionChains(driver).move_to_element(seta_prev).pause(0.1).click().perform()
                    time.sleep(0.4)
                except Exception:
                    break

        def _clicar_dia_sem_navegar(dia_numero, indice_painel):
            """indice_painel: 0 = calendário da esquerda (mês anterior), 1 = da
            direita (mês atual) — os dois meses certos já aparecem por padrão nessa
            tela (mês atual + anterior), então NUNCA navega/troca de mês, só clica
            direto pelo número do dia dentro do painel certo. Ignora células cinzas
            de overflow do mês vizinho (ex: dia 31 aparecendo no início do painel
            do mês seguinte)."""
            return driver.execute_script("""
                var alvoTexto = String(arguments[0]);
                var indicePainel = arguments[1];
                var paineis = document.querySelectorAll('table.ant-calendar-table');
                if (paineis.length <= indicePainel) return false;
                var painel = paineis[indicePainel];
                var celulas = painel.querySelectorAll('td');
                for (var i = 0; i < celulas.length; i++) {
                    var td = celulas[i];
                    var classe = td.className || '';
                    if (classe.indexOf('last-month') !== -1 || classe.indexOf('next-month') !== -1 ||
                        classe.indexOf('disabled') !== -1) continue;
                    var texto = td.textContent.trim();
                    if (texto === alvoTexto && td.offsetParent !== null) {
                        td.click();
                        return true;
                    }
                }
                return false;
            """, dia_numero, indice_painel)

        _clicar_dia_sem_navegar(data_inicio.day, 0)
        time.sleep(0.3)
        _clicar_dia_sem_navegar(data_fim.day, 1)
        time.sleep(0.3)

        # Confirma o intervalo escolhido — é um <a class="ant-calendar-ok-btn">, não
        # um <button> comum. Mesmo problema já visto no botão "Exportar": um
        # .click() via JS pode não disparar o listener do Vue, e o calendário
        # fica aberto (ainda que sem parecer) por cima da tela — daí o clique
        # seguinte no "Exportar" cai nesse overlay em vez do botão de verdade,
        # e o dropdown nunca abre (foi exatamente o sintoma visto em produção:
        # botão "Exportar" visível, nenhum menu aparece). Por isso usa clique
        # REAL (ActionChains) e confirma que o painel do calendário sumiu antes
        # de seguir, re-tentando se ainda estiver aberto.
        def _calendario_ainda_aberto():
            return driver.execute_script("""
                var els = document.querySelectorAll('.ant-calendar-table, .ant-calendar-ok-btn');
                for (var el of els) { if (el.offsetParent !== null) return true; }
                return false;
            """)

        def _clicar_ok_calendario():
            from selenium.webdriver.common.action_chains import ActionChains
            elemento = None
            for el in driver.find_elements(By.CSS_SELECTOR, ".ant-calendar-ok-btn, a[role='button']"):
                if el.text.strip() == "Ok" and el.is_displayed():
                    elemento = el
                    break
            if not elemento:
                return False
            try:
                ActionChains(driver).move_to_element(elemento).pause(0.2).click().perform()
            except Exception:
                pass
            driver.execute_script("arguments[0].click();", elemento)
            return True

        for _tentativa_ok in range(3):
            if not _calendario_ainda_aberto():
                break
            _clicar_ok_calendario()
            for _ in range(6):
                time.sleep(0.4)
                if not _calendario_ainda_aberto():
                    break

        # Trocar o filtro de data dispara um recarregamento da lista de pedidos —
        # se a gente clicar em "Exportar" enquanto isso ainda está rodando, o
        # clique pode cair num overlay de loading (.ant-spin) ou num botão que
        # está sendo re-renderizado, e o dropdown simplesmente não abre (sem
        # erro nenhum). Espera o spinner sumir, com um piso de 3s de qualquer forma.
        time.sleep(3)
        for _ in range(10):
            spinner_ativo = driver.execute_script("""
                var els = document.querySelectorAll('.ant-spin-spinning');
                for (var el of els) { if (el.offsetParent !== null) return true; }
                return false;
            """)
            if not spinner_ativo:
                break
            time.sleep(0.5)

        # 1. Clica "Exportar" (dropdown) — confirma que o menu REALMENTE abriu antes
        # de seguir (poll), porque um clique pode "funcionar" no DOM e o menu ainda
        # assim não aparecer (ou fechar sozinho de novo). Se não abrir, tenta
        # clicar uma segunda vez (pode ter sido um toggle que fechou por acaso).
        def _menu_exportar_aberto():
            # Substring "exportar" (não frase exata) — tolera o texto do menu ter
            # mudado (ex: só "Exportar todos", sem "os pedidos"). MAS precisa
            # ignorar o texto de dentro do próprio botão-gatilho (closest('button'))
            # e não aceitar a palavra sozinha ("exportar") — senão bate com o
            # <span>Exportar</span> interno do botão, que está sempre visível
            # mesmo com o menu fechado, e dá falso positivo.
            return driver.execute_script("""
                var candidatos = document.querySelectorAll('a, li, span, div');
                for (var el of candidatos) {
                    if (el.children.length > 0) continue;
                    if (el.closest('button')) continue;
                    var txt = el.textContent.replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (txt.indexOf('exportar') !== -1 && txt !== 'exportar' && txt.length < 60 && el.offsetParent !== null) {
                        return true;
                    }
                }
                return false;
            """)

        def _clicar_botao_exportar(tentar_js_tambem=False):
            """Clique REAL do Selenium (mover o mouse + clicar), não .click() via JS —
            o gatilho do dropdown (classe ant-dropdown-trigger) fica no <div> pai do
            botão, e o listener do Vue pode depender de eventos de mouse de verdade
            (mousedown/mouseup) em vez de só um evento de clique sintético. Em
            retentativas (tentar_js_tambem=True) também dispara um .click() JS no
            botão e no <div> pai logo em seguida — cobre o caso do clique real ter
            sido "engolido" por um overlay/re-render que já sumiu quando o JS roda."""
            from selenium.webdriver.common.action_chains import ActionChains
            try:
                elemento = None
                for b in driver.find_elements(By.TAG_NAME, "button"):
                    if b.text.strip() == "Exportar" and b.is_displayed():
                        elemento = b
                        break
                if not elemento:
                    return False
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
                time.sleep(0.3)
                ActionChains(driver).move_to_element(elemento).pause(0.2).click().perform()
                if tentar_js_tambem:
                    time.sleep(0.4)
                    driver.execute_script("""
                        var el = arguments[0];
                        el.click();
                        var pai = el.closest('.ant-dropdown-trigger') || el.parentElement;
                        if (pai) { pai.click(); }
                    """, elemento)
                return True
            except Exception:
                return False

        if not _clicar_botao_exportar():
            return False, "❌ Botão 'Exportar' não encontrado na tela de Pedidos Enviados"

        menu_aberto = False
        for _tentativa in range(6):
            time.sleep(0.6)
            if _menu_exportar_aberto():
                menu_aberto = True
                break

        if not menu_aberto:
            _clicar_botao_exportar(tentar_js_tambem=True)
            for _tentativa in range(6):
                time.sleep(0.6)
                if _menu_exportar_aberto():
                    menu_aberto = True
                    break

        if not menu_aberto:
            # Diagnóstico rico: já sabíamos que o botão "Exportar" continua visível
            # mesmo quando o clique não abre nada — então o que falta ver é O QUE
            # existe no DOM perto/dentro dele (pode ter virado outro tipo de
            # componente, ex: não é mais um dropdown de verdade, ou tem mais de um
            # botão "Exportar" na tela e a gente clica no errado).
            diagnostico = driver.execute_script("""
                var out = {};
                var btns = [];
                document.querySelectorAll('button').forEach(function(b) {
                    if (b.textContent.trim() === 'Exportar') {
                        btns.push({
                            visivel: b.offsetParent !== null,
                            html: b.outerHTML.slice(0, 300),
                            pai_classe: b.parentElement ? b.parentElement.className : null,
                            aria_expanded: b.getAttribute('aria-expanded'),
                        });
                    }
                });
                out.botoes_exportar = btns;

                var dropdowns = [];
                document.querySelectorAll('[class*="dropdown"], [class*="menu"], [class*="popup"], [role="menu"]').forEach(function(el) {
                    var txt = el.textContent.trim();
                    if (txt.length < 200) {
                        dropdowns.push({classe: el.className, visivel: el.offsetParent !== null, texto: txt.slice(0, 120)});
                    }
                });
                out.elementos_dropdown_like = dropdowns.slice(0, 15);

                var textos = [];
                document.querySelectorAll('a, li, span, div, button').forEach(function(el) {
                    var txt = el.textContent.trim();
                    if (txt && txt.length < 40 && el.offsetParent !== null) textos.push(txt);
                });
                out.textos_visiveis = [...new Set(textos)].slice(0, 40);

                return out;
            """)
            return False, f"❌ Menu 'Exportar' não abriu. Diagnóstico: {diagnostico}"

        # 2. Clica "Exportar Todos os Pedidos" — tenta a frase completa primeiro,
        # cai pra "exportar todos" (sem "os pedidos") se o texto do menu mudou.
        clicou_todos = driver.execute_script("""
            var candidatos = document.querySelectorAll('a, li, span, div');
            var fallback = null;
            for (var el of candidatos) {
                if (el.children.length > 0) continue;
                if (el.offsetParent === null) continue;
                var txt = el.textContent.replace(/\\s+/g, ' ').trim().toLowerCase();
                if (txt.indexOf('exportar todos os pedidos') !== -1) {
                    el.click();
                    return true;
                }
                if (!fallback && txt.indexOf('exportar todos') !== -1) fallback = el;
            }
            if (fallback) { fallback.click(); return true; }
            return false;
        """)
        if not clicou_todos:
            diagnostico2 = driver.execute_script("""
                var textos = [];
                document.querySelectorAll('a, li, span, div').forEach(function(el) {
                    if (el.children.length > 0) return;
                    var txt = el.textContent.trim();
                    if (txt && txt.toLowerCase().indexOf('exportar') !== -1) {
                        textos.push({texto: txt, visivel: el.offsetParent !== null});
                    }
                });
                return textos;
            """)
            return False, f"❌ 'Exportar Todos os Pedidos' não encontrado (mas o menu tinha aberto). Itens com 'exportar' no menu: {diagnostico2}"
        time.sleep(2)

        # 3. Modal "Informações de Configuração" — garante que os 3 checkboxes
        # (Informação do Produto, Informação do Pedido, SKU (Armazém)) ficam
        # marcados, sem mexer nos outros que não fazem parte disso.
        driver.execute_script("""
            var alvos = ['informação do produto', 'informação do pedido', 'sku (armazém)', 'sku (armazem)'];
            var candidatos = document.querySelectorAll('label');
            for (var label of candidatos) {
                var txt = (label.textContent || '').trim().toLowerCase();
                if (alvos.indexOf(txt) !== -1) {
                    var input = label.querySelector('input[type="checkbox"]');
                    if (input && !input.checked) { input.click(); }
                }
            }
        """)
        time.sleep(0.5)

        # 4. Clica "Exportar" do modal
        clicou_exportar_modal = driver.execute_script("""
            var btns = document.querySelectorAll('button.ant-btn-primary');
            for (var b of btns) {
                if (b.textContent.trim() === 'Exportar' && b.offsetParent !== null) {
                    b.click();
                    return true;
                }
            }
            return false;
        """)
        if not clicou_exportar_modal:
            return False, "❌ Botão 'Exportar' do modal de configuração não encontrado"
        time.sleep(2)

        # 5. Captura o "Total de Páginas" (ex: <div class="fw_bold">17</div>) e insere
        # no SEGUNDO campo de página (o modal tem dois: "de" página 1 até página N —
        # o primeiro já vem certo como 1, só o segundo precisa virar o total).
        pagina_max = driver.execute_script("""
            var els = document.querySelectorAll('.fw_bold');
            for (var el of els) {
                var txt = el.textContent.trim();
                if (/^\\d+$/.test(txt)) return txt;
            }
            return null;
        """)
        if pagina_max:
            driver.execute_script("""
                var inputs = document.querySelectorAll('input.ant-input-number-input[role="spinbutton"]');
                if (inputs.length > 1) {
                    var input = inputs[1];
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, arguments[0]);
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                    input.blur();
                }
            """, pagina_max)
            time.sleep(0.5)

        # 6. Clica "Exportar" (final, gera o arquivo pra baixar)
        clicou_exportar_final = driver.execute_script("""
            var btns = document.querySelectorAll('button.ant-btn-primary');
            for (var b of btns) {
                if (b.textContent.trim() === 'Exportar' && b.offsetParent !== null) {
                    b.click();
                    return true;
                }
            }
            return false;
        """)
        if not clicou_exportar_final:
            return False, "❌ Botão 'Exportar' final não encontrado"

        # 7. Espera a Upseller processar a exportação antes de procurar "Baixar" —
        # com muitos pedidos (~11 páginas) isso não é instantâneo.
        time.sleep(8)

        # Captura o estado da pasta ANTES de clicar em "Baixar" — se isso rodasse
        # depois do clique (como estava antes), um download rápido já apareceria na
        # pasta antes da gente sequer começar a olhar, e nunca seria contado como
        # "arquivo novo".
        arquivos_antes = set(glob.glob(os.path.join(pasta_download, "*")))

        clicou_baixar = False
        for _tentativa in range(10):
            clicou_baixar = driver.execute_script("""
                var btns = document.querySelectorAll('button.ant-btn-primary');
                for (var b of btns) {
                    if (b.textContent.trim() === 'Baixar' && b.offsetParent !== null) {
                        b.click();
                        return true;
                    }
                }
                return false;
            """)
            if clicou_baixar:
                break
            time.sleep(3)

        if not clicou_baixar:
            return False, "❌ Botão 'Baixar' não encontrado — a exportação pode ainda estar processando, tente de novo em instantes"

        # 8. Espera o arquivo aparecer na pasta de download configurada no driver.
        arquivo_novo = None
        for _tentativa in range(30):
            time.sleep(1)
            arquivos_depois = set(glob.glob(os.path.join(pasta_download, "*")))
            novos = [f for f in (arquivos_depois - arquivos_antes) if not f.endswith(".crdownload")]
            if novos:
                arquivo_novo = max(novos, key=os.path.getmtime)
                break

        if not arquivo_novo:
            return False, f"❌ Arquivo não apareceu em {pasta_download} a tempo (clicou Baixar, mas o download não foi detectado)"

        return True, arquivo_novo

    except Exception as e:
        return False, f"❌ Erro ao exportar pedidos: {str(e)[:200]}"
