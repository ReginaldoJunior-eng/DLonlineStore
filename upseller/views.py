# -*- coding: utf-8 -*-
"""Login e automação do Upseller — portado de widget_login_upseller em
modulo_upseller.py. Estado do driver fica em ESTADO (upseller/state.py, vivo
na memória do processo Django) em vez de st.session_state/st.cache_resource,
já que aqui não existe 'rerun' — o processo já fica de pé o tempo todo."""
import os
import tempfile
import threading
import time

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import JsonResponse

from core.bigquery import get_client
from . import driver as drv
from .state import ESTADO, reset_login


def status(request):
    """Tela de login/status do Upseller — GET simples, mostra a etapa atual."""
    client = get_client()
    if ESTADO["logado"] and not drv.driver_esta_vivo(ESTADO["driver"]):
        novo = _reconectar_via_cookies(client)
        if novo:
            ESTADO["driver"] = novo
            ESTADO["logado"] = True
            ESTADO["etapa"] = 3
        else:
            reset_login()
    elif ESTADO["etapa"] in (1, 2) and not drv.driver_esta_vivo(ESTADO["driver"]):
        # Se a pessoa fechar a aba/janela do robô sem querer no meio do
        # login (antes de logar de verdade), o driver morre mas a etapa
        # ficava travada em 1/2 pra sempre — nenhuma ação nessa tela
        # conseguia avançar (toda tentativa esbarrava numa exceção contra um
        # driver morto), sem nenhuma mensagem explicando o que aconteceu.
        reset_login()
        messages.error(request, "A janela do navegador foi fechada no meio do login — comece de novo.")

    tem_cookies = drv.existe_sessao_salva(client)
    return render(request, "upseller/status.html", {"estado": ESTADO, "tem_cookies": tem_cookies})


def _reconectar_via_cookies(client):
    if not drv.existe_sessao_salva(client):
        return None
    try:
        novo_driver = drv.criar_driver()
        if drv.login_por_cookies(novo_driver, client):
            drv.fechar_popup(novo_driver)
            drv._minimizar_janela(novo_driver)
            return novo_driver
        novo_driver.quit()
        return None
    except Exception:
        return None


def login_automatico(request):
    if request.method == "POST":
        client = get_client()
        driver = drv.criar_driver()
        if drv.login_por_cookies(driver, client):
            drv.fechar_popup(driver)
            drv._minimizar_janela(driver)
            ESTADO["driver"] = driver
            ESTADO["logado"] = True
            ESTADO["etapa"] = 3
        else:
            driver.quit()
            drv.deletar_cookies(client)
            messages.warning(request, "Sessão expirada. Faça login manual.")
    return redirect("upseller:status")


def login_manual_iniciar(request):
    if request.method == "POST":
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        driver = drv.criar_driver()
        driver.get(settings.UPSELLER_URL)
        time.sleep(3)
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, drv.SEL_EMAIL)))
            driver.find_element(By.CSS_SELECTOR, drv.SEL_EMAIL).send_keys(settings.UPSELLER_EMAIL)
            driver.find_element(By.CSS_SELECTOR, drv.SEL_SENHA).send_keys(settings.UPSELLER_SENHA)
        except Exception as e:
            messages.error(request, f"Erro: {e}")
            driver.quit()
            return redirect("upseller:status")

        ESTADO["driver"] = driver
        ESTADO["captcha_img_b64"] = drv.captura_captcha_b64(driver)
        ESTADO["etapa"] = 1
    return redirect("upseller:status")


def login_captcha(request):
    if request.method == "POST":
        from selenium.webdriver.common.by import By
        driver = ESTADO["driver"]
        cap = request.POST.get("captcha", "")
        client = get_client()
        try:
            driver.find_element(By.CSS_SELECTOR, drv.SEL_CAPTCHA).clear()
            driver.find_element(By.CSS_SELECTOR, drv.SEL_CAPTCHA).send_keys(cap)
            btn_clicado = False
            for sel in ["form button[type='submit']", "form .ant-btn-primary", ".ant-btn-primary", "form button"]:
                for b in driver.find_elements(By.CSS_SELECTOR, sel):
                    if b.is_displayed() and b.is_enabled():
                        b.click()
                        btn_clicado = True
                        break
                if btn_clicado:
                    break
            if not btn_clicado:
                messages.error(request, "Não encontrou o botão Login.")
                return redirect("upseller:status")

            # Espera de verdade a navegação acontecer, em vez de um sleep(4)
            # fixo — bug real visto em produção: quando a página demorava um
            # pouco mais que isso pra trocar de URL (rede mais lenta), a
            # checagem rodava cedo demais, via ainda a URL antiga de login e
            # concluía "CAPTCHA incorreto" mesmo o captcha tendo sido aceito
            # e a navegação real tendo acontecido logo em seguida — a pessoa
            # via com os próprios olhos a tela do robô avançar certinho
            # enquanto o app dizia o contrário.
            url_antes = driver.current_url
            for _ in range(20):  # até ~10s, checando a cada 0.5s
                time.sleep(0.5)
                if driver.current_url != url_antes:
                    break
            url = driver.current_url
            if "login-code" in url or "verify" in url or "verificac" in url.lower():
                # Dispara o clique em "Enviar Código" já aqui, assim que a
                # etapa 2 é detectada — não espera a pessoa submeter o
                # formulário do código primeiro (isso é o que causava o
                # código digitado sendo descartado, ver clicar_enviar_codigo).
                ESTADO["code_enviado"] = drv.clicar_enviar_codigo(driver)
                ESTADO["etapa"] = 2
            elif "login" not in url:
                drv.fechar_popup(driver)
                drv.salvar_cookies(driver, client)
                drv._minimizar_janela(driver)
                ESTADO["logado"] = True
                ESTADO["etapa"] = 3
            else:
                messages.error(request, "❌ CAPTCHA incorreto.")
                ESTADO["captcha_img_b64"] = drv.captura_captcha_b64(driver)
        except Exception as e:
            messages.error(request, f"Erro: {e}")
    return redirect("upseller:status")


def login_recarregar_captcha(request):
    if request.method == "POST" and ESTADO["driver"]:
        ESTADO["captcha_img_b64"] = drv.captura_captcha_b64(ESTADO["driver"])
    return redirect("upseller:status")


def login_reenviar_codigo(request):
    """Botão manual de reforço — o envio já é disparado automaticamente
    assim que a etapa 2 é detectada (login_captcha), mas se o e-mail não
    chegar (link do botão mudou nome de novo, demora, etc.) a pessoa não
    fica travada esperando sem nenhuma ação possível."""
    if request.method == "POST" and ESTADO.get("driver") and ESTADO.get("etapa") == 2:
        if drv.clicar_enviar_codigo(ESTADO["driver"]):
            ESTADO["code_enviado"] = True
            messages.success(request, "Código reenviado — confira o e-mail.")
        else:
            messages.error(request, "Não encontrou o botão de reenviar. Tente digitar o código mesmo assim.")
    return redirect("upseller:status")


def login_codigo(request):
    if request.method == "POST":
        from selenium.webdriver.common.by import By
        driver = ESTADO["driver"]
        codigo = request.POST.get("codigo", "").strip()
        client = get_client()

        if not codigo:
            messages.error(request, "Digite o código recebido por e-mail.")
            return redirect("upseller:status")

        if not ESTADO.get("code_enviado"):
            # O clique automático (login_captcha, assim que a etapa 2 é
            # detectada) pode ter falhado — tenta de novo aqui, mas sem
            # descartar o código que a pessoa já digitou: antes essa parte
            # dava return aqui e jogava o código fora, obrigando a pessoa a
            # submeter duas vezes (e a segunda também era descartada, porque
            # code_enviado nunca virava True de verdade — o código "sumia").
            ESTADO["code_enviado"] = drv.clicar_enviar_codigo(driver)

        try:
            for inp in driver.find_elements(By.CSS_SELECTOR, "input"):
                ph = (inp.get_attribute("placeholder") or "").lower()
                if any(x in ph for x in ["código", "code", "verif"]):
                    inp.clear()
                    inp.send_keys(codigo)
                    break
            else:
                for inp in driver.find_elements(By.CSS_SELECTOR, "input"):
                    if inp.is_displayed() and inp.get_attribute("type") not in ["hidden", "password"]:
                        inp.clear()
                        inp.send_keys(codigo)
                        break
            for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
                if any(x in btn.text.lower() for x in ["continuar", "continue", "confirmar", "submit"]):
                    btn.click()
                    break
            time.sleep(4)
            if "login" not in driver.current_url:
                drv.fechar_popup(driver)
                drv.salvar_cookies(driver, client)
                drv._minimizar_janela(driver)
                ESTADO["logado"] = True
                ESTADO["etapa"] = 3
            else:
                messages.error(request, "❌ Código inválido.")
        except Exception as e:
            messages.error(request, f"Erro: {e}")
    return redirect("upseller:status")


def desconectar(request):
    if request.method == "POST":
        try:
            ESTADO["driver"].quit()
        except Exception:
            pass
        drv.deletar_cookies(get_client())
        reset_login()
    return redirect("upseller:status")


def limpar_sessao(request):
    if request.method == "POST":
        drv.deletar_cookies(get_client())
        messages.info(request, "Cookies removidos.")
    return redirect("upseller:status")


# ============================================================
# EXPORTAR PEDIDOS (roda em thread, com progresso pollável)
# ============================================================

def _rodar_exportacao():
    """Sem o try/except em volta de tudo, qualquer erro não previsto depois
    do download (ex: falha ao importar pro dashboard) matava a thread
    silenciosamente e ESTADO["tarefa"]["rodando"] nunca voltava pra False —
    o botão "Exportando..." ficava preso pra sempre mesmo com a exportação
    real já tendo terminado (visto num caso real: arquivo baixado com
    sucesso, status nunca atualizou). _rodar_publicacao já tinha essa
    proteção; essa função ficou de fora por descuido."""
    ESTADO["tarefa"] = {"tipo": "exportar", "rodando": True, "resultado": None}
    try:
        from .actions import exportar_pedidos_shipped_upseller
        from dashboard.services import importar_pedidos_upseller_para_dashboard

        client = get_client()
        pasta_download = os.path.join(tempfile.gettempdir(), "upseller_exports")
        ok_exp, resultado = exportar_pedidos_shipped_upseller(ESTADO["driver"], pasta_download)
        if not ok_exp:
            ESTADO["tarefa"] = {"tipo": "exportar", "rodando": False, "resultado": {"ok": False, "msg": resultado}}
            return

        inseridas, duplicadas, erros, msgs_erro = importar_pedidos_upseller_para_dashboard(client, resultado)
        try:
            os.remove(resultado)
        except Exception:
            pass
        ESTADO["tarefa"] = {"tipo": "exportar", "rodando": False, "resultado": {
            "ok": True, "inseridas": inseridas, "duplicadas": duplicadas, "erros": erros, "msgs_erro": msgs_erro,
        }}
    except Exception as e:
        ESTADO["tarefa"] = {"tipo": "exportar", "rodando": False,
                             "resultado": {"ok": False, "msg": f"❌ Erro inesperado: {e}"}}


def exportar_iniciar(request):
    if request.method == "POST" and ESTADO["logado"]:
        if not (ESTADO.get("tarefa") and ESTADO["tarefa"].get("rodando")):
            t = threading.Thread(target=_rodar_exportacao, daemon=True)
            t.start()
    return redirect("dashboard:financeiro")


def exportar_status(request):
    """Endpoint JSON pollado pelo template pra saber se a exportação terminou.
    Checa "tipo" pelo mesmo motivo de publicar_produto_status: publicar e
    exportar dividem o mesmo ESTADO["tarefa"] (de propósito, pra nunca rodar
    os dois ao mesmo tempo no mesmo navegador) — sem essa checagem, pollar
    aqui enquanto uma publicação estiver rodando/tiver acabado de rodar
    mostraria o resultado errado."""
    tarefa = ESTADO.get("tarefa") or {}
    if tarefa.get("tipo") not in (None, "exportar"):
        return JsonResponse({"rodando": False, "resultado": None, "screenshot_url": None})
    resultado = tarefa.get("resultado")
    screenshot_url = None
    if resultado and resultado.get("ok") is False:
        caminho = os.path.join(tempfile.gettempdir(), "upseller_exports", "ultimo_erro_screenshot.png")
        if os.path.exists(caminho):
            screenshot_url = "/upseller/exportar/screenshot/"
    return JsonResponse({
        "rodando": bool(tarefa.get("rodando")),
        "resultado": resultado,
        "screenshot_url": screenshot_url,
    })


def exportar_screenshot(request):
    from django.http import FileResponse, Http404
    caminho = os.path.join(tempfile.gettempdir(), "upseller_exports", "ultimo_erro_screenshot.png")
    if not os.path.exists(caminho):
        raise Http404
    return FileResponse(open(caminho, "rb"), content_type="image/png")


# ============================================================
# PUBLICAR UM PRODUTO (roda em background — ver ESTADO["tarefa"])
# ============================================================
# Antes rodava síncrono (bloqueava a requisição até terminar, ~20-50s reais
# medidos). Problema real visto em produção: o waitress tem um timeout de
# conexão padrão de 120s — se a publicação demorasse mais que isso (rede
# mais lenta, mais tentativas de SKU repetido), o waitress derrubava a
# conexão do navegador, mas o Python CONTINUAVA rodando até o fim sozinho
# (criava o produto de verdade — daí o SKU existir), só que o navegador
# nunca recebia resposta nenhuma e o botão "Publicando..." ficava preso pra
# sempre. Rodar em background (mesmo padrão de exportar_iniciar) elimina
# esse limite de tempo por completo.

def _rodar_publicacao(produto_id):
    from campineira import bq as campineira_bq
    from campineira.services import publicar_um_produto_armazem
    from core.calculos_marketplace import calcular_precos_sugeridos

    client = get_client()
    try:
        resultados_brutos = campineira_bq.ler_resultados(client)
        produto = next((p for p in resultados_brutos if str(p.get("id")) == str(produto_id)), None)
        if not produto:
            ESTADO["tarefa"] = {"tipo": "publicar", "rodando": False,
                                 "resultado": {"ok": False, "msg": "Produto não encontrado na última varredura."}}
            return

        produto.update(calcular_precos_sugeridos(produto.get("preco")))
        try:
            produto["preco_num"] = float(str(produto.get("preco") or "0").replace("R$", "").replace(".", "").replace(",", ".").strip())
        except Exception:
            produto["preco_num"] = 0

        sucesso, msg = publicar_um_produto_armazem(produto, ESTADO["driver"], client)
        ESTADO["tarefa"] = {"tipo": "publicar", "rodando": False, "resultado": {"ok": sucesso, "msg": msg}}
    except Exception as e:
        ESTADO["tarefa"] = {"tipo": "publicar", "rodando": False,
                             "resultado": {"ok": False, "msg": f"Erro inesperado: {e}"}}


def publicar_produto(request, produto_id):
    if request.method != "POST":
        return redirect("campineira:publicar")
    if not ESTADO["logado"]:
        return JsonResponse({"ok": False, "msg": "🔒 Faça login no Upseller primeiro."}, status=400)
    if ESTADO.get("tarefa") and ESTADO["tarefa"].get("rodando"):
        return JsonResponse({"ok": False, "msg": "⏳ Já tem uma publicação/exportação rodando — espera terminar."}, status=409)

    ESTADO["tarefa"] = {"tipo": "publicar", "rodando": True, "resultado": None}
    threading.Thread(target=_rodar_publicacao, args=(produto_id,), daemon=True).start()
    return JsonResponse({"ok": True})


def publicar_produto_status(request):
    """Endpoint JSON pollado pelo template pra saber se a publicação
    terminou — mesmo padrão de exportar_status."""
    tarefa = ESTADO.get("tarefa") or {}
    if tarefa.get("tipo") != "publicar":
        return JsonResponse({"rodando": False, "resultado": None})
    return JsonResponse({"rodando": bool(tarefa.get("rodando")), "resultado": tarefa.get("resultado")})


# ============================================================
# PUBLICAR EM MASSA (fila de vários produtos selecionados, um por vez —
# mesmo ESTADO["tarefa"] das outras tarefas de fundo, pra nunca rodar duas
# coisas ao mesmo tempo. Roda tudo em segundo plano: a pessoa pode navegar
# pra qualquer outra tela que a fila continua avançando sozinha; a barra de
# progresso aparece em qualquer página, ver base.html.)
# ============================================================

def _rodar_publicacao_lote(produto_ids):
    from campineira import bq as campineira_bq
    from campineira.services import publicar_um_produto_armazem
    from core.calculos_marketplace import calcular_precos_sugeridos

    tarefa = ESTADO["tarefa"]  # mesmo dict setado em publicar_lote_iniciar — só mutado daqui em diante
    try:
        client = get_client()
        resultados_brutos = campineira_bq.ler_resultados(client)
        produtos_por_id = {str(p.get("id")): p for p in resultados_brutos}

        for produto_id in produto_ids:
            produto = produtos_por_id.get(str(produto_id))
            if not produto:
                tarefa["resultados"].append({"produto_id": produto_id, "nome": None,
                                              "ok": False, "msg": "Produto não encontrado na última varredura."})
                tarefa["concluidos"] += 1
                continue

            tarefa["atual_nome"] = produto.get("nome")
            produto.update(calcular_precos_sugeridos(produto.get("preco")))
            try:
                produto["preco_num"] = float(str(produto.get("preco") or "0").replace("R$", "").replace(".", "").replace(",", ".").strip())
            except Exception:
                produto["preco_num"] = 0

            try:
                sucesso, msg = publicar_um_produto_armazem(produto, ESTADO["driver"], client)
            except Exception as e:
                # Um produto dando erro (SKU repetido, campo faltando etc.) não
                # pode derrubar a fila inteira — segue pro próximo.
                sucesso, msg = False, f"Erro inesperado: {e}"

            tarefa["resultados"].append({"produto_id": produto_id, "nome": produto.get("nome"),
                                          "ok": sucesso, "msg": msg})
            tarefa["concluidos"] += 1
    except Exception as e:
        tarefa["resultados"].append({"produto_id": None, "nome": None, "ok": False,
                                      "msg": f"❌ Erro inesperado na fila: {e}"})
    finally:
        tarefa["rodando"] = False
        tarefa["atual_nome"] = None


def publicar_lote_iniciar(request):
    if request.method != "POST":
        return redirect("campineira:publicar")
    if not ESTADO["logado"]:
        return JsonResponse({"ok": False, "msg": "🔒 Faça login no Upseller primeiro."}, status=400)
    if ESTADO.get("tarefa") and ESTADO["tarefa"].get("rodando"):
        return JsonResponse({"ok": False, "msg": "⏳ Já tem uma publicação/exportação rodando — espera terminar."}, status=409)

    produto_ids = request.POST.getlist("selecionados")
    if not produto_ids:
        return JsonResponse({"ok": False, "msg": "Selecione ao menos um produto."}, status=400)

    ESTADO["tarefa"] = {"tipo": "publicar_lote", "rodando": True, "total": len(produto_ids),
                         "concluidos": 0, "atual_nome": None, "resultados": []}
    threading.Thread(target=_rodar_publicacao_lote, args=(produto_ids,), daemon=True).start()
    return JsonResponse({"ok": True, "total": len(produto_ids)})


def publicar_lote_status(request):
    """Pollado tanto pela aba Publicar quanto pela barra flutuante em
    base.html (visível em qualquer página — a fila roda solta no servidor,
    independente de pra onde a pessoa navegar)."""
    tarefa = ESTADO.get("tarefa") or {}
    if tarefa.get("tipo") != "publicar_lote":
        return JsonResponse({"rodando": False})
    return JsonResponse({
        "rodando": bool(tarefa.get("rodando")),
        "total": tarefa.get("total", 0),
        "concluidos": tarefa.get("concluidos", 0),
        "atual_nome": tarefa.get("atual_nome"),
        "resultados": tarefa.get("resultados", []),
    })
