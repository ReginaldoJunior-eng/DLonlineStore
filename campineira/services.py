# -*- coding: utf-8 -*-
"""Publicar um produto no Armazém (Upseller) + registrar tudo no BigQuery —
portado de _publicar_um_produto_armazem em modulo_campineira.py."""
import socket
import time
import uuid

from . import bq

_TITULAR_TRAVA = f"CodigosPython3@{socket.gethostname()}@{uuid.uuid4().hex[:8]}"


def publicar_um_produto_armazem(produto, driver, client_bq):
    """Roda o fluxo completo: checa EAN duplicado, publica no Upseller, gera
    SKU, registra em tb_sku_registrados, tb_produtos e no histórico
    permanente, grava o evento do pipeline. Retorna (sucesso, msg).

    Adquire a trava de publicação antes de gerar o SKU (ver bq.py) — essa
    versão local roda em paralelo com a versão na nuvem, então sem isso as
    duas poderiam calcular o mesmo "próximo SKU livre" ao mesmo tempo."""
    sku_repetido = bq.checar_ean_duplicado_bq(client_bq, produto.get("ean"))
    if sku_repetido:
        return False, f"❌ EAN {produto.get('ean')} já usado no SKU {sku_repetido} — não publicado, pra evitar duplicidade."

    conseguiu_trava = False
    for _ in range(10):
        if bq.adquirir_trava_publicacao(client_bq, _TITULAR_TRAVA):
            conseguiu_trava = True
            break
        time.sleep(2)  # outra instância (talvez a da nuvem) está publicando agora — espera a vez
    if not conseguiu_trava:
        return False, "❌ Não deu pra publicar agora: a outra instância (nuvem) está publicando ao mesmo tempo. Tente de novo em instantes."

    try:
        from upseller.actions import publicar_produto_upseller
        sucesso, msg, sku_gerado = publicar_produto_upseller(driver, produto, client_bq)

        avisos = []
        if sucesso:
            ok_sku, erro_sku = bq.registrar_sku_bq(client_bq, sku_gerado, produto.get("ean"), produto.get("id"), produto.get("nome"))
            if not ok_sku:
                avisos.append(f"SKU não registrado no BigQuery: {erro_sku}")

            ok_prod, erro_prod = bq.registrar_produto_em_tb_produtos(client_bq, sku_gerado, produto.get("nome"), produto.get("preco_num"))
            if not ok_prod:
                avisos.append(f"tb_produtos não atualizado: {erro_prod}")

            ok_hist, erro_hist = bq.marcar_sku_historico_bq(client_bq, produto.get("id"), sku_gerado)
            if not ok_hist:
                avisos.append(f"SKU não marcado no histórico: {erro_hist}")

        ok_evento, erro_evento = bq.registrar_evento_pipeline_bq(
            client_bq, produto.get("id"), sku_gerado, produto.get("nome"),
            produto.get("categoria"), "armazem", "ok" if sucesso else "erro", msg
        )
        if not ok_evento:
            avisos.append(f"Evento do pipeline não registrado: {erro_evento}")

        if avisos:
            msg = msg + " ⚠️ " + " | ".join(avisos)
        return sucesso, msg
    finally:
        bq.liberar_trava_publicacao(client_bq, _TITULAR_TRAVA)
