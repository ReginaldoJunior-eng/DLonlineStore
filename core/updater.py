# -*- coding: utf-8 -*-
"""Checagem/download de atualização via GitHub Releases. Repositório é
público e usado só como canal de distribuição do instalador (.exe) — não tem
o código-fonte do projeto, então não precisa de nenhum token guardado no
app instalado.

Qualquer falha aqui (sem internet, GitHub fora do ar, release mal formado)
precisa ficar contida nesse módulo: nunca pode impedir o app de abrir."""
import logging
import os

import requests

from .version import APP_VERSION

logger = logging.getLogger(__name__)

GITHUB_REPO = "ReginaldoJunior-eng/dlonlinestore-releases"
NOME_ASSET = "DLOnlineStore-Instalador.exe"


def _versao_tupla(versao: str):
    partes = []
    for p in versao.strip().split("."):
        try:
            partes.append(int(p))
        except ValueError:
            partes.append(0)
    return tuple(partes)


def verificar_atualizacao():
    """Retorna um dict com a atualização disponível, ou None se já está na
    versão mais recente (ou se a checagem falhou por qualquer motivo)."""
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            timeout=10,
            headers={"Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        data = resp.json()

        tag = (data.get("tag_name") or "").lstrip("vV")
        if not tag:
            return None

        asset = next((a for a in data.get("assets", []) if a.get("name") == NOME_ASSET), None)
        if not asset:
            logger.warning("Release %s não tem o asset %s", tag, NOME_ASSET)
            return None

        if _versao_tupla(tag) <= _versao_tupla(APP_VERSION):
            return None

        return {
            "versao": tag,
            "url_download": asset["browser_download_url"],
            "notas": (data.get("body") or "").strip(),
        }
    except Exception:
        logger.exception("Falha ao checar atualização no GitHub")
        return None


def baixar_instalador(url: str, destino: str) -> bool:
    try:
        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            with open(destino, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    f.write(chunk)
        return os.path.getsize(destino) > 0
    except Exception:
        logger.exception("Falha ao baixar o instalador da atualização")
        return False
