# -*- coding: utf-8 -*-
"""Importar pedidos exportados do Upseller pro Dashboard Financeiro — portado
de LeMarketplace.py (importar_pedidos_upseller_para_dashboard)."""
import pandas as pd
from google.cloud import bigquery

from core.calculos_marketplace import calcular_lucro_realizado, obter_sku_base


def importar_pedidos_upseller_para_dashboard(client_bq, caminho_excel):
    """Lê o Excel exportado do Upseller (Pedidos > Enviado) e insere em
    tb_vendas_realizadas as vendas que ainda não estão lá (checa por
    numero_pedido, nunca duplica). Retorna (inseridas, duplicadas, erros, msgs_erro)."""
    df = pd.read_excel(caminho_excel)

    def achar_coluna(nomes_exatos, *grupos_palavras_fallback):
        cols_low = {c: str(c).strip().lower() for c in df.columns}
        for nome in nomes_exatos:
            alvo = nome.strip().lower()
            for col, low in cols_low.items():
                if low == alvo:
                    return col
        for palavras in grupos_palavras_fallback:
            for col, low in cols_low.items():
                if all(p in low for p in palavras):
                    return col
        return None

    col_pedido = achar_coluna(["Nº de Pedido", "N° de Pedido"], ("número", "pedido"), ("pedido", "id"))
    col_pagamento = achar_coluna(["Hora do Pagamento"], ("hora", "pagamento"), ("pagamento",))
    col_plataforma = achar_coluna(["Plataformas", "Plataforma"], ("plataforma",))
    col_sku_armazem = achar_coluna(["SKU (Armazém)", "SKU (Armazem)"], ("sku", "armaz"))
    col_sku_plain = achar_coluna(["SKU"], ("sku",))
    col_valor = achar_coluna(["Valor do Pedido"], ("valor", "pedido"))
    col_valor_produtos_temu = achar_coluna(["Valor Total de Produtos"], ("valor", "total", "produtos"))
    col_qtd = achar_coluna(["Qtd. do Produto", "Qtd do Produto", "Quantidade de Produtos"], ("qtd", "produto"))
    col_nome_produto = achar_coluna(["Nome do Produto"], ("nome", "produto"))
    col_nome_anuncio = achar_coluna(["Nome do Anúncio", "Nome do Anuncio"], ("nome", "anúncio"), ("nome", "anuncio"))

    faltando = [nome for nome, col in [
        ("Número do Pedido", col_pedido), ("Hora do Pagamento", col_pagamento),
        ("Plataforma", col_plataforma), ("Valor do Pedido", col_valor),
    ] if col is None]
    if col_sku_armazem is None and col_sku_plain is None:
        faltando.append("SKU")
    if faltando:
        return 0, 0, 0, [f"Não encontrei as colunas: {', '.join(faltando)}. "
                          f"Colunas disponíveis no Excel: {list(df.columns)}"]

    table_vendas = "leandro-marketplace.DL_Store_Online.tb_vendas_realizadas"
    table_produtos = "leandro-marketplace.DL_Store_Online.tb_produtos"

    pedidos_existentes = set()
    try:
        df_exist = client_bq.query(
            f"SELECT DISTINCT numero_pedido FROM `{table_vendas}` WHERE numero_pedido IS NOT NULL"
        ).to_dataframe()
        pedidos_existentes = set(df_exist["numero_pedido"].astype(str))
    except Exception:
        pass

    custos_por_sku = {}
    try:
        df_custos = client_bq.query(f"SELECT sku, custo_aquisicao FROM `{table_produtos}`").to_dataframe()
        custos_por_sku = df_custos.groupby("sku")["custo_aquisicao"].first().to_dict()
    except Exception:
        pass

    def _normalizar_plataforma(bruto):
        b = str(bruto or "").strip().lower()
        if "shopee" in b: return "shopee"
        if "shein" in b: return "shein"
        if "tiktok" in b or "tik tok" in b: return "tiktok"
        if "temu" in b: return "temu"
        return b

    inseridas, duplicadas, erros = 0, 0, 0
    msgs_erro = []
    linhas_novas = []

    for _, row in df.iterrows():
        try:
            numero_pedido = str(row[col_pedido]).strip()
            if not numero_pedido or numero_pedido.lower() == "nan":
                continue
            if numero_pedido in pedidos_existentes:
                duplicadas += 1
                continue

            plataforma = _normalizar_plataforma(row[col_plataforma])
            col_valor_usar = col_valor_produtos_temu if (plataforma == "temu" and col_valor_produtos_temu is not None) else col_valor

            if pd.isna(row[col_valor_usar]) or float(row[col_valor_usar]) == 0:
                continue

            data_pagamento = pd.to_datetime(row[col_pagamento]).date()

            sku_armazem = str(row[col_sku_armazem]).strip() if col_sku_armazem and pd.notna(row[col_sku_armazem]) else ""
            sku_plain = str(row[col_sku_plain]).strip() if col_sku_plain and pd.notna(row[col_sku_plain]) else ""
            sku = sku_armazem or sku_plain

            valor_pedido = float(row[col_valor_usar])
            quantidade = int(row[col_qtd]) if col_qtd and pd.notna(row[col_qtd]) else 1

            nome_prod_val = str(row[col_nome_produto]).strip() if col_nome_produto and pd.notna(row[col_nome_produto]) else ""
            nome_anuncio_val = str(row[col_nome_anuncio]).strip() if col_nome_anuncio and pd.notna(row[col_nome_anuncio]) else ""
            nome_produto = nome_prod_val or nome_anuncio_val or sku

            custo_aquisicao = custos_por_sku.get(sku)
            if custo_aquisicao is None:
                custo_aquisicao = custos_por_sku.get(obter_sku_base(sku))
            custo_aquisicao = float(custo_aquisicao or 0)
            pendente = custo_aquisicao <= 0
            lucro = calcular_lucro_realizado(valor_pedido, custo_aquisicao, plataforma)

            linhas_novas.append({
                "produto": nome_produto, "sku": sku, "preco_venda": valor_pedido,
                "quantidade": quantidade, "data": data_pagamento.strftime("%Y-%m-%d"),
                "lucro_total": round(lucro, 2), "mkt_venda": plataforma,
                "numero_pedido": numero_pedido, "pendente": pendente,
            })
            pedidos_existentes.add(numero_pedido)
            inseridas += 1
        except Exception as e:
            erros += 1
            msgs_erro.append(f"Pedido {row.get(col_pedido, '?')}: {str(e)[:100]}")

    if linhas_novas:
        try:
            df_novas = pd.DataFrame(linhas_novas)
            df_novas["data"] = pd.to_datetime(df_novas["data"]).dt.date
            job_config = bigquery.LoadJobConfig(schema=[
                bigquery.SchemaField("produto", "STRING"), bigquery.SchemaField("sku", "STRING"),
                bigquery.SchemaField("preco_venda", "FLOAT"), bigquery.SchemaField("quantidade", "INTEGER"),
                bigquery.SchemaField("data", "DATE"), bigquery.SchemaField("lucro_total", "FLOAT"),
                bigquery.SchemaField("mkt_venda", "STRING"), bigquery.SchemaField("numero_pedido", "STRING"),
                bigquery.SchemaField("pendente", "BOOLEAN"),
            ])
            client_bq.load_table_from_dataframe(df_novas, table_vendas, job_config=job_config).result()
            from core.services import invalidar_cache_vendas
            invalidar_cache_vendas()
        except Exception as e:
            erros += len(linhas_novas)
            inseridas = 0
            msgs_erro.append(f"Erro ao inserir no BigQuery: {str(e)[:300]}")

    return inseridas, duplicadas, erros, msgs_erro
