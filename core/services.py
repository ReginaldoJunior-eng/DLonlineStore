# -*- coding: utf-8 -*-
"""Consultas/gravações de tb_produtos, tb_vendas_realizadas e tb_estoque —
portado de LeMarketplace.py. Usado por Calculadora, Cadastro, Alterar Preço,
Validar Vendas e Gestão de Estoque."""
import pandas as pd
from django.core.cache import cache
from google.cloud import bigquery

from .calculos_marketplace import calcular_lucro_realizado, obter_sku_base

TABLE_PRODUTOS = "leandro-marketplace.DL_Store_Online.tb_produtos"
TABLE_VENDAS = "leandro-marketplace.DL_Store_Online.tb_vendas_realizadas"
TABLE_ESTOQUE = "leandro-marketplace.DL_Store_Online.tb_estoque"
TABLE_ESTOQUE_HIST = "leandro-marketplace.DL_Store_Online.tb_estoque_historico"

# Cache curto do catálogo de produtos (tb_produtos) — usado por Calculadora e
# Gestão de Estoque, as duas telas que mais sentiam a navegação lenta (medido:
# ~1,4-2,5s por clique, quase todo esse tempo é essa mesma consulta repetida
# do zero a cada troca de aba). 3 min é tempo suficiente pra sumir o atraso
# em uso normal (trocar de aba várias vezes seguidas) sem arriscar mostrar
# dado muito velho. Em cima disso, invalidar_cache_produtos() é chamado logo
# depois de qualquer gravação em tb_produtos (cadastro, variante nova,
# alterar preço, publicação pela Campineira) — então o próprio usuário NUNCA
# vê a tela antiga depois de uma ação dele mesmo; o TTL de 3 min só importa
# pra quando é outra pessoa/processo mudando o dado (ex: a versão na nuvem).
CACHE_KEY_PRODUTOS = "produtos_bq_df"
CACHE_TTL_PRODUTOS = 180  # segundos


def buscar_produtos_bq(client):
    df = cache.get(CACHE_KEY_PRODUTOS)
    if df is not None:
        return df
    if not client:
        return pd.DataFrame()
    df = client.query(f"SELECT * FROM `{TABLE_PRODUTOS}`").to_dataframe()
    if not df.empty:
        df = df.drop_duplicates(subset=["SKU"])
    cache.set(CACHE_KEY_PRODUTOS, df, CACHE_TTL_PRODUTOS)
    return df


# Duas outras telas também consultavam tb_produtos do zero a cada clique
# (achado numa auditoria de performance depois do cache acima): Cadastro
# (busca de produto-base pra variante nova) e Alterar Preços (lista de SKUs
# pra fila). Cada uma usa um "shape" de colunas diferente da consulta
# principal acima (maiúscula/minúscula e colunas extras não batem — testado
# e confirmado, reaproveitar o DataFrame de buscar_produtos_bq() direto
# quebraria com KeyError), por isso cada uma tem sua própria chave de cache
# em vez de tentar forçar um reaproveitamento arriscado.
CACHE_KEY_PRODUTOS_BASE = "produtos_base_bq_df"
CACHE_KEY_PRODUTOS_ALTERAR = "produtos_alterar_preco_bq_df"


def buscar_produtos_base_bq(client):
    """Um produto por SKU BASE + coluna marketplace — usado só pela busca de
    'Adicionar Variante a Produto Existente' no Cadastro."""
    df = cache.get(CACHE_KEY_PRODUTOS_BASE)
    if df is not None:
        return df
    if not client:
        return pd.DataFrame()
    try:
        df = client.query(
            f"SELECT SKU, Produto, marketplace, Custo_aquisicao FROM `{TABLE_PRODUTOS}`"
        ).to_dataframe()
    except Exception:
        return pd.DataFrame()
    if not df.empty:
        df["sku_base"] = df["SKU"].apply(obter_sku_base)
    cache.set(CACHE_KEY_PRODUTOS_BASE, df, CACHE_TTL_PRODUTOS)
    return df


def buscar_produtos_alterar_preco_bq(client):
    """SKU/produto/custo (minúsculo, DISTINCT) — usado só pela tela Alterar
    Preços pra checar SKU já na fila antes de adicionar."""
    df = cache.get(CACHE_KEY_PRODUTOS_ALTERAR)
    if df is not None:
        return df
    if not client:
        return pd.DataFrame()
    df = client.query(
        f"SELECT DISTINCT sku, produto, custo_aquisicao FROM `{TABLE_PRODUTOS}` ORDER BY produto"
    ).to_dataframe()
    cache.set(CACHE_KEY_PRODUTOS_ALTERAR, df, CACHE_TTL_PRODUTOS)
    return df


def invalidar_cache_produtos():
    """Chamar logo depois de qualquer INSERT/UPDATE em tb_produtos, pra essa
    mesma sessão já ver o dado novo no próximo clique, sem esperar o TTL —
    limpa as três chaves de cache que dependem dessa tabela."""
    cache.delete(CACHE_KEY_PRODUTOS)
    cache.delete(CACHE_KEY_PRODUTOS_BASE)
    cache.delete(CACHE_KEY_PRODUTOS_ALTERAR)


# Dashboard Financeiro era a tela mais lenta do sistema (medido: 3,51s na
# primeira visita, 2,31s mesmo numa segunda visita — nunca tinha cache
# nenhum) porque é logo pra onde o login manda a pessoa, e o usuário sentia
# isso como "o login tá lento". Mesmo padrão de cache das outras telas.
CACHE_KEY_VENDAS = "vendas_realizadas_bq_df"
CACHE_TTL_VENDAS = 180  # segundos


def buscar_vendas_realizadas_bq(client):
    df = cache.get(CACHE_KEY_VENDAS)
    if df is not None:
        return df
    if not client:
        return pd.DataFrame()
    query = (
        "SELECT produto, sku, preco_venda, quantidade, data, lucro_total, mkt_venda "
        f"FROM `{TABLE_VENDAS}` WHERE pendente IS NULL OR pendente = FALSE ORDER BY data DESC"
    )
    df = client.query(query).to_dataframe()
    cache.set(CACHE_KEY_VENDAS, df, CACHE_TTL_VENDAS)
    return df


def invalidar_cache_vendas():
    """Chamar logo depois de qualquer INSERT/UPDATE em tb_vendas_realizadas
    (importar pedidos do Upseller, corrigir lucro de SKU recém-cadastrado,
    fallback de SKU base) — mesmo raciocínio do invalidar_cache_produtos."""
    cache.delete(CACHE_KEY_VENDAS)


# Mesmo esquema de cache, agora pra tb_estoque (tela Gestão de Estoque) — era
# a outra metade do atraso que sobrava mesmo depois de cachear tb_produtos
# (medido: Calculadora caiu de 1,6s pra 0,04s com o cache acima, mas Estoque
# continuou em ~1,5s porque consulta essa tabela separada).
CACHE_KEY_ESTOQUE = "estoque_bq_df"
CACHE_TTL_ESTOQUE = 180  # segundos


def buscar_estoque_bq(client):
    df = cache.get(CACHE_KEY_ESTOQUE)
    if df is not None:
        return df
    if not client:
        return pd.DataFrame()
    df = client.query(f"SELECT * FROM `{TABLE_ESTOQUE}`").to_dataframe()
    cache.set(CACHE_KEY_ESTOQUE, df, CACHE_TTL_ESTOQUE)
    return df


def invalidar_cache_estoque():
    """Chamar logo depois de qualquer entrada/saída/ajuste em tb_estoque."""
    cache.delete(CACHE_KEY_ESTOQUE)


# ── Validar Vendas ───────────────────────────────────────────────────────

def buscar_pendencias_validacao(client):
    q_sem_cadastro = f"""
        SELECT v.sku, ANY_VALUE(v.produto) AS produto,
               COUNT(*) AS vendas, SUM(v.preco_venda) AS faturamento,
               MIN(v.data) AS data_min, MAX(v.data) AS data_max
        FROM `{TABLE_VENDAS}` v
        LEFT JOIN (SELECT DISTINCT sku FROM `{TABLE_PRODUTOS}`) p
          ON v.sku = p.sku
          OR REGEXP_EXTRACT(v.sku, r'^([A-Za-z]+-\\d+)-.+$') = p.sku
        WHERE p.sku IS NULL AND v.sku IS NOT NULL AND v.sku != ''
        GROUP BY v.sku
        ORDER BY faturamento DESC
    """
    df_sem_cadastro = client.query(q_sem_cadastro).to_dataframe()

    q_divergentes = f"""
        SELECT p.sku, ANY_VALUE(p.produto) AS produto,
               ARRAY_AGG(DISTINCT p.custo_aquisicao ORDER BY p.custo_aquisicao) AS valores,
               COUNT(v.numero_pedido) AS vendas
        FROM `{TABLE_PRODUTOS}` p
        LEFT JOIN `{TABLE_VENDAS}` v ON v.sku = p.sku
        GROUP BY p.sku
        HAVING COUNT(DISTINCT p.custo_aquisicao) > 1
        ORDER BY vendas DESC, p.sku
    """
    df_divergentes_raw = client.query(q_divergentes).to_dataframe()
    df_divergentes = _agrupar_divergentes_por_sku_base(df_divergentes_raw)
    return df_sem_cadastro, df_divergentes


def _agrupar_divergentes_por_sku_base(df):
    if df.empty:
        return pd.DataFrame(columns=["sku_base", "skus", "produto", "valores", "vendas"])
    df = df.copy()
    df["sku_base"] = df["sku"].apply(obter_sku_base)
    linhas = []
    for base, grupo in df.groupby("sku_base"):
        grupo_ordenado = grupo.sort_values("vendas", ascending=False)
        valores_unicos = sorted({round(float(v), 2) for lista in grupo["valores"] for v in lista})
        linhas.append({
            "sku_base": base, "skus": grupo_ordenado["sku"].tolist(),
            "produto": grupo_ordenado["produto"].iloc[0],
            "valores": valores_unicos, "vendas": int(grupo["vendas"].sum()),
        })
    return pd.DataFrame(linhas).sort_values("vendas", ascending=False).reset_index(drop=True)


def _recalcular_lucro_por_sku(client, sku, custo_aquisicao):
    job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("sku", "STRING", sku)])
    df = client.query(
        f"SELECT numero_pedido, preco_venda, mkt_venda FROM `{TABLE_VENDAS}` WHERE sku = @sku AND numero_pedido IS NOT NULL",
        job_config=job_config,
    ).to_dataframe()
    if df.empty:
        return 0
    structs = []
    for _, row in df.iterrows():
        novo_lucro = calcular_lucro_realizado(float(row["preco_venda"]), custo_aquisicao, row["mkt_venda"])
        structs.append(bigquery.StructQueryParameter(
            None,
            bigquery.ScalarQueryParameter("numero_pedido", "STRING", str(row["numero_pedido"])),
            bigquery.ScalarQueryParameter("lucro_total", "FLOAT64", round(float(novo_lucro), 2)),
        ))
    array_param = bigquery.ArrayQueryParameter("correcoes", "STRUCT", structs)
    update_sql = f"""
        UPDATE `{TABLE_VENDAS}` v SET lucro_total = c.lucro_total, pendente = FALSE
        FROM UNNEST(@correcoes) AS c WHERE v.numero_pedido = c.numero_pedido
    """
    client.query(update_sql, job_config=bigquery.QueryJobConfig(query_parameters=[array_param])).result()
    invalidar_cache_vendas()
    return len(structs)


def resolver_sku_sem_cadastro(client, sku, produto, custo_aquisicao):
    lote = [{"marketplace": mkt, "sku": sku, "produto": produto, "custo_aquisicao": float(custo_aquisicao)}
            for mkt in ["shein", "shopee", "temu", "tiktok"]]
    client.load_table_from_dataframe(pd.DataFrame(lote), TABLE_PRODUTOS).result()
    invalidar_cache_produtos()
    return _recalcular_lucro_por_sku(client, sku, float(custo_aquisicao))


def resolver_grupo_divergente(client, skus, novo_custo):
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("novo_custo", "FLOAT64", float(novo_custo)),
        bigquery.ArrayQueryParameter("skus", "STRING", list(skus)),
    ])
    client.query(f"UPDATE `{TABLE_PRODUTOS}` SET custo_aquisicao = @novo_custo WHERE sku IN UNNEST(@skus)",
                 job_config=job_config).result()
    invalidar_cache_produtos()
    total = 0
    for sku in skus:
        total += _recalcular_lucro_por_sku(client, sku, float(novo_custo))
    return total


def aplicar_fallback_sku_base(client):
    df_prod = client.query(f"SELECT DISTINCT sku, custo_aquisicao FROM `{TABLE_PRODUTOS}`").to_dataframe()
    custos_por_sku = df_prod.groupby("sku")["custo_aquisicao"].first().to_dict()
    skus_cadastrados = set(custos_por_sku.keys())

    df_v = client.query(
        f"SELECT numero_pedido, sku, preco_venda, mkt_venda FROM `{TABLE_VENDAS}` "
        f"WHERE numero_pedido IS NOT NULL AND sku IS NOT NULL AND sku != ''"
    ).to_dataframe()
    if df_v.empty:
        return 0

    structs = []
    for _, row in df_v.iterrows():
        sku = row["sku"]
        if sku in skus_cadastrados:
            continue
        base = obter_sku_base(sku)
        if base == sku or base not in skus_cadastrados:
            continue
        custo = float(custos_por_sku[base] or 0)
        novo_lucro = calcular_lucro_realizado(float(row["preco_venda"]), custo, row["mkt_venda"])
        structs.append(bigquery.StructQueryParameter(
            None,
            bigquery.ScalarQueryParameter("numero_pedido", "STRING", str(row["numero_pedido"])),
            bigquery.ScalarQueryParameter("lucro_total", "FLOAT64", round(float(novo_lucro), 2)),
        ))
    if not structs:
        return 0
    array_param = bigquery.ArrayQueryParameter("correcoes", "STRUCT", structs)
    update_sql = f"""
        UPDATE `{TABLE_VENDAS}` v SET lucro_total = c.lucro_total, pendente = FALSE
        FROM UNNEST(@correcoes) AS c WHERE v.numero_pedido = c.numero_pedido
    """
    client.query(update_sql, job_config=bigquery.QueryJobConfig(query_parameters=[array_param])).result()
    invalidar_cache_vendas()
    return len(structs)


# ── Gestão de Estoque ────────────────────────────────────────────────────

def recomendar_canal(custo):
    p_sugerido = custo * 1.35
    imp, c_fixo = 0.06, 1.00
    l_shein = p_sugerido - (p_sugerido * 0.18) - (p_sugerido * imp) - custo - c_fixo - 5.0
    tax_shopee = 4.0 if custo < 50 else 20.0
    l_shopee = p_sugerido - (p_sugerido * 0.20) - (p_sugerido * imp) - custo - c_fixo - tax_shopee
    l_temu = p_sugerido - (p_sugerido * imp) - custo - c_fixo
    l_tiktok = p_sugerido - (p_sugerido * 0.12) - (p_sugerido * imp) - custo - c_fixo - 4.0
    lucros = {"Shein": l_shein, "Shopee": l_shopee, "Temu": l_temu, "Tiktok": l_tiktok}
    melhor = max(lucros, key=lucros.get)
    return melhor, lucros[melhor]
