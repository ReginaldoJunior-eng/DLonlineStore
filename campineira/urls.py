# -*- coding: utf-8 -*-
from django.urls import path
from . import views

app_name = "campineira"

urlpatterns = [
    path("", views.configurar, name="home"),
    path("configurar/", views.configurar, name="configurar"),
    path("configurar/adicionar/", views.fila_adicionar, name="fila_adicionar"),
    path("configurar/remover/<int:idx>/", views.fila_remover, name="fila_remover"),
    path("configurar/limpar/", views.fila_limpar, name="fila_limpar"),
    path("configurar/iniciar/", views.iniciar_varredura, name="iniciar_varredura"),
    path("configurar/retomar/", views.retomar_varredura, name="retomar_varredura"),
    path("configurar/status/", views.varredura_status, name="varredura_status"),
    path("resultados/", views.resultados, name="resultados"),
    path("resultados/excel/", views.resultados_excel, name="resultados_excel"),
    path("publicar/", views.publicar, name="publicar"),
    path("publicar/excluir/<str:produto_id>/", views.publicar_excluir, name="publicar_excluir"),
    path("publicar/excluir-selecionados/", views.publicar_excluir_selecionados, name="publicar_excluir_selecionados"),
    path("historico/", views.historico, name="historico"),
]
