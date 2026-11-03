# -*- coding: utf-8 -*-
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.login_view, name="login"),
    path("entrar/", views.entrar, name="entrar"),
    path("sair/", views.sair, name="sair"),

    path("calculadora/", views.calculadora, name="calculadora"),
    path("cadastro/", views.cadastro, name="cadastro"),
    path("alterar-preco/", views.alterar_preco, name="alterar_preco"),
    path("alterar-preco/adicionar/", views.alterar_preco_adicionar, name="alterar_preco_adicionar"),
    path("alterar-preco/remover/<int:idx>/", views.alterar_preco_remover, name="alterar_preco_remover"),
    path("alterar-preco/limpar/", views.alterar_preco_limpar, name="alterar_preco_limpar"),
    path("alterar-preco/enviar/", views.alterar_preco_enviar, name="alterar_preco_enviar"),
    path("estoque/", views.estoque, name="estoque"),
    path("estoque/entrada/", views.estoque_entrada, name="estoque_entrada"),
    path("estoque/saida/", views.estoque_saida, name="estoque_saida"),
    path("estoque/ajustar/", views.estoque_ajustar, name="estoque_ajustar"),
    path("validar-vendas/", views.validar_vendas, name="validar_vendas"),
    path("validar-vendas/fallback/", views.validar_vendas_fallback, name="validar_vendas_fallback"),
    path("validar-vendas/sem-cadastro/", views.validar_vendas_sem_cadastro, name="validar_vendas_sem_cadastro"),
    path("validar-vendas/divergente/", views.validar_vendas_divergente, name="validar_vendas_divergente"),
]
