# -*- coding: utf-8 -*-
"""Conexão com o BigQuery compartilhada por todo o projeto.

Equivalente ao padrão @st.cache_resource do Streamlit original: lá, o cliente
BigQuery era criado uma vez e reaproveitado entre reruns da mesma sessão via
cache global do processo. Aqui não existe "rerun" — o processo do Django fica
de pé o tempo todo — então um singleton de módulo simples já resolve: a
primeira chamada cria o client, as próximas reaproveitam a mesma instância.
"""
from google.cloud import bigquery
from google.oauth2 import service_account
from django.conf import settings

_client = None


def get_client():
    global _client
    if _client is None:
        creds = service_account.Credentials.from_service_account_file(
            str(settings.BIGQUERY_CREDENTIALS_PATH)
        )
        _client = bigquery.Client(credentials=creds, project=settings.BIGQUERY_PROJECT_ID)
    return _client
