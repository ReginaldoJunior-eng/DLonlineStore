# -*- coding: utf-8 -*-
from .version import APP_VERSION


def versao_app(request):
    return {"app_version": APP_VERSION}
