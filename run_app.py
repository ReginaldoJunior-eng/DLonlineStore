# -*- coding: utf-8 -*-
"""Ponto de entrada do instalável — o que a pessoa vai executar (via atalho).

Sobe o Django com um servidor de produção leve (waitress) e abre o navegador
padrão sozinho. Sem janela de console visível — em vez disso, um ícone na
bandeja do sistema (perto do relógio, canto inferior direito) com "Abrir
Painel" e "Sair", que é como a pessoa fecha o programa (antes era fechando a
janela preta do console; sem console, precisa desse jeito alternativo).

Erros não têm mais pra onde ir (sem console pra mostrar print/traceback), por
isso tudo fica registrado em app.log, na mesma pasta do programa — pra
depurar se algo não abrir."""
import logging
import os
import socket
import sys
import threading
import time
import webbrowser

# Porta arbitrária, só usada como trava de instância única (nada a ver com a
# porta 8000 do Django) — guardada numa variável de módulo pra não fechar
# sozinha quando sai de escopo (isso liberaria a trava mais cedo do que
# deveria, deixando o programa rodar de novo mesmo já aberto).
_PORTA_TRAVA_INSTANCIA = 58234
_socket_trava = None


def _ja_esta_rodando():
    """Se a pessoa clicar duas vezes no ícone (achando que não abriu, por
    exemplo — o app demora alguns segundos até abrir o navegador sozinho),
    sem essa trava sobem DOIS processos escutando a mesma porta 8000 ao
    mesmo tempo: o navegador então conversa ora com um, ora com outro
    (Windows deixa isso acontecer sem erro nenhum), e cada processo tem seu
    próprio login do Upseller separado — publicar/exportar "não inicia"
    porque a ação às vezes cai no processo que nunca fez login. Achado
    testando de verdade nessa migração."""
    global _socket_trava
    try:
        _socket_trava = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _socket_trava.bind(("127.0.0.1", _PORTA_TRAVA_INSTANCIA))
        _socket_trava.listen(1)
        return False
    except OSError:
        return True


def _base_dir():
    """Pasta onde o app GRAVA estado (db.sqlite3, secrets\\, logs) — precisa
    ficar ao lado do .exe de verdade, não dentro de _internal\\, senão some
    a cada atualização/reinstalação. Funciona tanto rodando via
    `python run_app.py` (dev) quanto dentro do .exe empacotado."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _dados_dir():
    """Pasta onde os arquivos empacotados via `datas` no .spec (app.ico,
    VERSION) realmente ficam — a partir do PyInstaller 6, isso é
    sys._MEIPASS (a pasta _internal\\), não a pasta do .exe. Diferente de
    _base_dir(): esses arquivos são só leitura, empacotados junto do app."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


_CAMINHOS_NAVEGADOR_APP = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _abrir_em_modo_app(url):
    """Abre o painel numa janela "de app" (Chrome/Edge com --app=URL) — sem
    barra de endereço, sem abas: fica parecendo um programa de verdade em
    vez de uma página com "127.0.0.1" visível. Se não achar Chrome nem Edge
    instalado (raro — Edge vem de fábrica no Windows), cai pro navegador
    padrão numa aba normal mesmo.

    Usado como FALLBACK caso a janela WebView2 (ver _webview2_disponivel) não
    dê certo — era o único modo antes de 16/10/2026, mantido intacto pra
    garantir que o app sempre abre de algum jeito."""
    import subprocess
    for caminho in _CAMINHOS_NAVEGADOR_APP:
        if os.path.exists(caminho):
            try:
                subprocess.Popen([caminho, f"--app={url}"])
                return
            except Exception:
                logging.exception("Falha ao abrir %s em modo app", caminho)
    webbrowser.open(url)


def _webview2_disponivel():
    """Checa a chave de registro do WebView2 Runtime ANTES de tentar criar a
    janela embutida — vem instalado de fábrica no Windows 11 e via Edge no
    Windows 10 atualizado, mas checar com antecedência evita descobrir que
    falta no meio da inicialização (bandeja/servidor já subindo) e permite
    cair pro modo antigo (_abrir_em_modo_app) de forma limpa, sem janela
    quebrada aparecendo."""
    import winreg
    guid = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for subkey in (f"SOFTWARE\\WOW6432Node\\{guid}", f"SOFTWARE\\{guid}"):
        try:
            winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey)
            return True
        except FileNotFoundError:
            continue
    return False


def _icone_bandeja(dados_dir):
    """Carrega o ícone do app (mesmo app.ico usado no instalador/atalho) pra
    mostrar na bandeja do sistema — pystray precisa de uma imagem PIL, não
    aceita .ico direto em todo formato, então abre via Pillow."""
    from PIL import Image
    caminho_ico = os.path.join(dados_dir, "app.ico")
    if os.path.exists(caminho_ico):
        return Image.open(caminho_ico)
    # Fallback bem simples caso o .ico não tenha sido empacotado por algum motivo.
    return Image.new("RGB", (64, 64), (31, 92, 82))


def _avisar_atualizando(versao):
    """Aviso rápido que fecha sozinho (sem precisar clicar) antes do app
    fechar pra aplicar a atualização — sem isso a pessoa só veria o programa
    sumir e reabrir do nada, sem entender por quê. MessageBoxTimeoutW não é
    documentado oficialmente pela Microsoft, mas existe e é estável no
    user32.dll desde sempre — uso comum pra caixa de aviso que some
    sozinha, sem precisar de biblioteca nova nenhuma."""
    import ctypes
    MB_OK = 0x0
    MB_ICONINFORMATION = 0x40
    MB_TOPMOST = 0x00040000
    try:
        ctypes.windll.user32.MessageBoxTimeoutW(
            0,
            f"Encontramos uma atualização (v{versao}).\n\nO programa vai fechar e abrir sozinho de novo em instantes...",
            "D.L Online Store — Atualizando",
            MB_OK | MB_ICONINFORMATION | MB_TOPMOST,
            0,
            4000,
        )
    except Exception:
        pass


def _checar_e_aplicar_atualizacao_automatica():
    """Checa por atualização nova e aplica sozinha, sem pedir clique — só é
    seguro fazer isso bem aqui, no comecinho do processo (antes do servidor
    subir, antes do navegador abrir, antes de qualquer varredura/publicação/
    exportação existir pra interromper). Se aplicar, essa função nunca
    retorna: dispara o instalador silencioso e mata o processo atual
    (ver run_app.py:_ja_esta_rodando — o reaproveitamento de porta já libera
    sozinho); quem relança o app depois de instalar é o próprio comando
    encadeado (start "" app.exe), não este processo."""
    import subprocess
    import tempfile

    try:
        from core.updater import verificar_atualizacao, baixar_instalador
        resultado = verificar_atualizacao()
    except Exception:
        logging.exception("Falha ao checar atualização automática")
        return
    if not resultado:
        return

    logging.info("Atualização %s encontrada — baixando pra aplicar automaticamente...", resultado["versao"])
    threading.Thread(target=_avisar_atualizando, args=(resultado["versao"],), daemon=True).start()
    destino = os.path.join(tempfile.gettempdir(), "DLOnlineStore-Instalador.exe")
    if not baixar_instalador(resultado["url_download"], destino):
        logging.warning("Falha ao baixar a atualização automática — abrindo a versão atual normalmente.")
        return

    log_update = os.path.join(tempfile.gettempdir(), "dlonlinestore_update.log")
    app_exe = sys.executable
    # ping (não timeout — timeout.exe falha sem console de verdade) dá tempo
    # deste processo morrer de vez antes do instalador checar arquivos em
    # uso; shell=True (não ["cmd","/c",str]) porque passar a string inteira
    # como item de lista faz o Python citar tudo errado quando já tem aspas
    # + redirecionamento juntos — os dois detalhes já custaram um ciclo de
    # depuração real cada um, ver upseller_export_bug no histórico.
    comando = (
        f'ping -n 4 127.0.0.1 >nul && '
        f'"{destino}" /VERYSILENT /NORESTART /SUPPRESSMSGBOXES /LOG="{log_update}" && '
        f'start "" "{app_exe}"'
    )
    subprocess.Popen(comando, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    logging.info("Instalador da atualização disparado — encerrando esta instância.")
    os._exit(0)


def _resetar_varredura_presa():
    """A varredura da Campineira roda numa thread em memória e guarda
    progresso num arquivo JSON (campineira_status.json). Se o processo
    morrer no meio de uma varredura — "Sair" pela bandeja ou a atualização
    automática, que mata o processo com os._exit(0) sem aviso pra nenhuma
    tarefa em segundo plano — o arquivo fica travado com "rodando: true"
    pra sempre, mesmo sem nada rodando de verdade: a tela de Configurar e
    Rodar mostraria "em andamento" eternamente, e o botão de retomar de
    onde parou nunca apareceria (só aparece quando o status diz que não tá
    rodando). Como nenhuma thread sobrevive a um restart do processo, se
    esse status ainda diz "rodando" bem aqui no comecinho — antes de
    qualquer varredura nova poder ter iniciado nesse processo — é sempre
    porque ficou preso de uma queda anterior."""
    try:
        from campineira.scraper import ler_status, salvar_status
        status = ler_status()
        if status.get("rodando"):
            status["rodando"] = False
            status["progresso"] = "⚠️ Varredura interrompida (o programa foi fechado ou atualizado antes de terminar)."
            salvar_status(status)
            logging.info("Status de varredura da Campineira estava travado em 'rodando' — resetado no início do app.")
    except Exception:
        logging.exception("Falha ao checar/resetar status de varredura pendente")


def _trazer_janela_existente_pra_frente():
    """Acha a janela nativa (WebView2) já aberta pelo título fixo e traz pra
    frente, restaurando se estiver minimizada/escondida — usado quando a
    pessoa clica no atalho com o app já rodando. Retorna True se achou e
    trouxe; False se não achou nenhuma janela com esse título (aí quem
    chamou cai pro fallback de navegador)."""
    import ctypes

    SW_RESTORE = 9
    hwnd = ctypes.windll.user32.FindWindowW(None, "D.L Online Store")
    if not hwnd:
        return False
    ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    return True


def main():
    # DPI-aware ANTES de qualquer janela existir — sem isso o Windows mente
    # pro processo que a tela sempre está a 96 DPI (100%) e faz um
    # "stretch" automático da janela depois, o que gera um descompasso
    # entre o tamanho que o código pede e o que renderiza de verdade na
    # tela (visto num teste real: pedia 1920x1080 e a janela saía menor,
    # sobrando uma faixa preta — era exatamente esse mentira de DPI).
    # PER_MONITOR_DPI_AWARE (2) é o mais correto; se a API não existir
    # (Windows bem antigo), cai pro básico (SetProcessDPIAware) e, na
    # pior hipótese, só segue sem nenhum dos dois — não é motivo pra
    # travar o app abrindo.
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    if _ja_esta_rodando():
        # Já tem uma instância aberta — leva a pessoa pra ela em vez de subir
        # processo novo. Antes isso SEMPRE abria uma aba de navegador nova
        # (bug real: clicar no atalho de novo com o app já rodando abria o
        # Chrome por cima da janela embutida, dando a impressão de que o
        # tema/visual tinha voltado ao modo antigo). Agora tenta primeiro
        # achar a janela nativa já aberta (pelo título) e só trazer ela pra
        # frente — só cai pro navegador se não achar nenhuma (sinal de que a
        # instância já rodando está, ela mesma, no modo antigo de fallback).
        if not _trazer_janela_existente_pra_frente():
            _abrir_em_modo_app("http://127.0.0.1:8000/")
        return

    base_dir = _base_dir()
    os.chdir(base_dir)
    sys.path.insert(0, base_dir)
    os.environ["DLSTORE_BASE_DIR"] = base_dir  # settings.py usa isso dentro do .exe empacotado
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dlstore.settings")

    logging.basicConfig(
        filename=os.path.join(base_dir, "app.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("waitress").setLevel(logging.WARNING)

    try:
        import django
        django.setup()

        from django.core.management import call_command
        call_command("migrate", verbosity=0, interactive=False)
    except Exception:
        logging.exception("Falha ao inicializar o Django/migrar o banco local")
        raise

    _resetar_varredura_presa()

    if getattr(sys, "frozen", False):
        _checar_e_aplicar_atualizacao_automatica()

    URL = "http://127.0.0.1:8000/"

    def rodar_servidor():
        try:
            from waitress import serve
            from dlstore.wsgi import application
            logging.info("Servindo em %s", URL)
            # threads=4 (padrão do waitress) satura fácil: a tela de
            # Publicar sozinha já dispara vários pedidos ao mesmo tempo
            # (a página em si, CSS/JS, o polling de status a cada 2s), e
            # navegar pra outra aba nesse meio tempo faz fila (visto num
            # teste real: "Task queue depth" subindo até 6 no log, com a
            # pessoa achando que a tela travou). 16 dá bastante folga pra
            # esse app local de uma pessoa só.
            serve(application, host="127.0.0.1", port=8000, threads=16)
        except Exception:
            logging.exception("Servidor caiu")

    threading.Thread(target=rodar_servidor, daemon=True).start()

    import pystray
    from pystray import MenuItem as Item

    # Referência da janela embutida (None se caiu pro modo navegador) —
    # mutável via dict pra ser visível de dentro das closures dos callbacks
    # da bandeja, que são definidas antes da janela existir.
    estado = {"janela": None}

    def _abrir(icon, item):
        if estado["janela"] is not None:
            estado["janela"].show()
        else:
            _abrir_em_modo_app(URL)

    def _sair(icon, item):
        logging.info("Encerrado pelo usuário via bandeja do sistema.")
        if estado["janela"] is not None:
            try:
                estado["janela"].destroy()
            except Exception:
                pass
        icon.stop()
        os._exit(0)

    icon = pystray.Icon(
        "DLOnlineStore",
        icon=_icone_bandeja(_dados_dir()),
        title="D.L Online Store",
        menu=pystray.Menu(
            Item("Abrir Painel", _abrir, default=True),
            Item("Sair", _sair),
        ),
    )

    # Janela embutida via WebView2 (sem barra de endereço, sem processo de
    # navegador separado) — com fallback pro modo antigo (Chrome/Edge em
    # --app=) se o runtime não estiver disponível, pra nunca deixar o app
    # sem abrir de jeito nenhum.
    if _webview2_disponivel():
        try:
            import webview

            # frameless tira a barra de título/janela do Windows (fica igual
            # um app nativo, sem aquela faixa escura com "D.L Online Store" +
            # minimizar/maximizar/fechar).
            #
            # O parâmetro width/height do create_window passa por uma conta
            # de escala DENTRO do pywebview (Size = width * scale, onde
            # scale = GetDpiForWindow/96) que, medindo de verdade com
            # GetWindowRect, deu resultado DIFERENTE a cada execução — não é
            # um desconto fixo nem uma % fixa (testei pedir o tamanho exato
            # da tela: sobrou uma faixa preta; testei pedir maior com
            # posição negativa pra compensar: sobrou de novo, só que com uma
            # proporção diferente da vez anterior). Já que não dá pra
            # confiar nesse cálculo interno, a saída é IGNORAR o
            # width/height do create_window pra decidir o tamanho final e,
            # assim que a janela aparece (evento "shown"), forçar o
            # tamanho/posição de verdade direto pela API do Windows
            # (SetWindowPos) — sem passar pela conta de escala da lib.
            # API exposta pro JS (pywebview.api.<metodo>()) — usada pela
            # barrinha de controle customizada (minimizar/fechar) que
            # substitui os botões nativos que sumiram junto com a barra de
            # título ao virar frameless.
            class _ApiJanela:
                def minimizar(self):
                    janela.minimize()

                def fechar(self):
                    # "Fechar" aqui sempre foi "esconder pra bandeja", igual
                    # já era o comportamento do X nativo antes — "Sair" de
                    # verdade continua só pelo ícone da bandeja.
                    janela.hide()

            janela = webview.create_window(
                "D.L Online Store", URL, frameless=True, min_size=(1000, 650),
                js_api=_ApiJanela(),
            )

            def _preencher_tela():
                import ctypes
                SWP_NOZORDER = 0x0004
                SWP_NOACTIVATE = 0x0010
                largura_tela = ctypes.windll.user32.GetSystemMetrics(0)
                altura_tela = ctypes.windll.user32.GetSystemMetrics(1)
                hwnd = ctypes.windll.user32.FindWindowW(None, "D.L Online Store")
                if hwnd:
                    ctypes.windll.user32.SetWindowPos(
                        hwnd, 0, 0, 0, largura_tela, altura_tela,
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    )

            def _preencher_tela_com_reforco():
                # A posição/tamanho aplicados no "shown" às vezes são
                # sobrescritos logo depois por alguma inicialização
                # assíncrona interna do WebView2 (mesma instabilidade já
                # vista nessa área — medido numa sessão de verdade: janela
                # abriu em left=-45, top=100 mesmo com o shown já tendo
                # rodado). Reforça de novo ~600ms depois, como rede de
                # segurança, sem custo nenhum se já estiver certo.
                _preencher_tela()
                threading.Timer(0.6, _preencher_tela).start()

            janela.events.shown += _preencher_tela_com_reforco
            estado["janela"] = janela

            def _ao_fechar():
                # Fechar a janela (X) só esconde — igual fechar a aba do
                # navegador no modo antigo não derrubava o app, que continua
                # vivo na bandeja até "Sair" de verdade. Retornar False
                # cancela o fechamento real (ver webview/event.py: só False
                # explícito cancela, não qualquer valor "falsy").
                janela.hide()
                return False

            janela.events.closing += _ao_fechar

            icon.run_detached()
            logging.info("Interface embutida (WebView2) iniciada em %s", URL)
            webview.start(gui="edgechromium", debug=False)
            return
        except Exception:
            logging.exception("Falha ao abrir a janela WebView2 — caindo pro modo navegador")
            estado["janela"] = None
            try:
                icon.stop()
            except Exception:
                pass
            icon = pystray.Icon(
                "DLOnlineStore",
                icon=_icone_bandeja(_dados_dir()),
                title="D.L Online Store",
                menu=pystray.Menu(
                    Item("Abrir Painel", _abrir, default=True),
                    Item("Sair", _sair),
                ),
            )

    # Fallback: modo antigo (navegador em --app=), igual era antes de
    # 16/10/2026 — roda se o WebView2 não estiver disponível ou se a janela
    # embutida falhou ao abrir por qualquer outro motivo.
    def abrir_navegador():
        time.sleep(1.5)
        _abrir_em_modo_app(URL)

    threading.Thread(target=abrir_navegador, daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
