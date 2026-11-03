# -*- coding: utf-8 -*-
from django.urls import path
from . import views

app_name = "upseller"

urlpatterns = [
    path("", views.status, name="status"),
    path("login/automatico/", views.login_automatico, name="login_automatico"),
    path("login/manual/", views.login_manual_iniciar, name="login_manual_iniciar"),
    path("login/captcha/", views.login_captcha, name="login_captcha"),
    path("login/captcha/recarregar/", views.login_recarregar_captcha, name="login_recarregar_captcha"),
    path("login/codigo/", views.login_codigo, name="login_codigo"),
    path("login/codigo/reenviar/", views.login_reenviar_codigo, name="login_reenviar_codigo"),
    path("desconectar/", views.desconectar, name="desconectar"),
    path("limpar-sessao/", views.limpar_sessao, name="limpar_sessao"),
    path("exportar/iniciar/", views.exportar_iniciar, name="exportar_iniciar"),
    path("exportar/status/", views.exportar_status, name="exportar_status"),
    path("exportar/screenshot/", views.exportar_screenshot, name="exportar_screenshot"),
    # "publicar/status/", "publicar/lote/..." precisam vir ANTES de
    # "publicar/<str:produto_id>/" — senão o padrão genérico casa "status"/
    # "lote" como se fosse um produto_id e essas rotas nunca são alcançadas
    # (bug real, achado testando de verdade).
    path("publicar/status/", views.publicar_produto_status, name="publicar_produto_status"),
    path("publicar/lote/iniciar/", views.publicar_lote_iniciar, name="publicar_lote_iniciar"),
    path("publicar/lote/status/", views.publicar_lote_status, name="publicar_lote_status"),
    path("publicar/<str:produto_id>/", views.publicar_produto, name="publicar_produto"),
]
