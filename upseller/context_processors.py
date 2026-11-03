# -*- coding: utf-8 -*-
from .state import ESTADO


def upseller_status(request):
    return {"upseller_conectado": ESTADO["logado"]}
