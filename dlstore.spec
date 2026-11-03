# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — empacota o app Django como pasta autocontida (--onedir,
não onefile: mais confiável com Selenium/Chrome e evita o app inteiro
descompactar num diretório temporário toda vez que abre).

Django carrega os apps (core/dashboard/campineira/upseller) por import
dinâmico via INSTALLED_APPS (string), que a análise estática do PyInstaller
não enxerga sozinha — por isso os hiddenimports explícitos abaixo."""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = []
for pkg in ["core", "dashboard", "campineira", "upseller", "django.contrib.admin",
            "django.contrib.auth", "django.contrib.sessions", "django.contrib.messages",
            "django.contrib.staticfiles", "selenium", "webdriver_manager",
            "pystray", "pystray._win32",
            # google-cloud-bigquery-storage: usado por baixo dos panos pelo
            # to_dataframe() do BigQuery pra baixar resultado bem mais rápido
            # (sem isso cai num fallback via REST bem mais lento — achado
            # medindo de verdade: 22s -> 9,6s só instalando isso). Import
            # condicional/interno da lib, a análise estática do PyInstaller
            # não pega sozinha — por isso precisa declarar aqui também.
            "google.cloud.bigquery_storage", "google.cloud.bigquery_storage_v1",
            # openpyxl: engine que o pandas usa por baixo dos panos pra ler
            # .xlsx (pd.read_excel), importado dinamicamente pelo pandas —
            # mesmo motivo do bigquery_storage acima, análise estática não
            # enxerga sozinha.
            "openpyxl",
            # pywebview (janela embutida via WebView2, ver run_app.py) +
            # pythonnet/clr_loader, que ele usa por baixo dos panos pra
            # hospedar o controle WebView2 via WinForms — import feito
            # dinamicamente a partir do SO detectado (webview.platforms.*),
            # análise estática não enxerga sozinha, mesmo motivo de sempre.
            "webview", "webview.platforms.winforms", "pythonnet", "clr_loader"]:
    hidden += collect_submodules(pkg)

datas = [
    ("core/templates", "core/templates"),
    ("core/static", "core/static"),
    ("dashboard/templates", "dashboard/templates"),
    ("dashboard/static", "dashboard/static"),  # plotly.min.js local (gráfico Financeiro)
    ("campineira/templates", "campineira/templates"),
    ("upseller/templates", "upseller/templates"),
    ("app.ico", "."),  # run_app.py abre isso pro ícone da bandeja do sistema
    ("VERSION", "."),  # core/version.py lê isso pra saber a própria versão
]
# Python.Runtime.dll: assembly .NET que o pythonnet carrega em tempo de
# execução pra hospedar o WebView2 — é um binário, não um .py, então a
# análise estática do PyInstaller não empacota sozinha (mesmo motivo dos
# hiddenimports acima, só que pra dado em vez de código).
datas += collect_data_files("pythonnet")

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DLOnlineStore",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # sem janela preta — a pessoa fecha o app pelo ícone na
                     # bandeja do sistema (menu "Sair"), não fechando console.
    icon="app.ico",
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="DLOnlineStore",
)
