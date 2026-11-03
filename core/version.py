# -*- coding: utf-8 -*-
"""Versão atual do app — fonte única, lida do arquivo VERSION na raiz do
projeto (mesmo arquivo que instalador.iss lê pra definir MyAppVersion), pra
nunca dessincronizar o número usado no updater (core/updater.py) do número
que vai no instalador de verdade.

Empacotado (PyInstaller 6+, --onedir): os arquivos declarados em `datas`
ficam dentro de _internal\\ (sys._MEIPASS), não ao lado do .exe — diferente
de settings.BASE_DIR, que aponta pra pasta do .exe de propósito (é onde o
app grava db.sqlite3/secrets, e isso não pode sumir numa atualização)."""
import sys
from pathlib import Path

from django.conf import settings


def _arquivo_version():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", settings.BASE_DIR)) / "VERSION"
    return settings.BASE_DIR / "VERSION"


APP_VERSION = "0.0.0"
try:
    APP_VERSION = _arquivo_version().read_text(encoding="utf-8").strip()
except Exception:
    pass
