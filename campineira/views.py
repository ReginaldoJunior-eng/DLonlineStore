# -*- coding: utf-8 -*-
"""Views da Campineira — portado de modulo_campineira.py (CodigosPython2).
A varredura de verdade (Selenium contra o site da Campineira) e a publicação
de verdade no Upseller ainda não foram portadas: dependem da infraestrutura
de tarefas em background, que é uma etapa separada do plano. Todo o resto
(fila de varredura, ler resultados, filtrar, excluir em massa, histórico) já
lê/escreve dados reais no BigQuery."""
import io
from datetime import datetime

import pandas as pd
from google.cloud import bigquery
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect

from core.bigquery import get_client
from core.calculos_marketplace import calcular_precos_sugeridos
from . import bq

ABAS = [
    ("configurar", "⚙️ Configurar e Rodar", "campineira:configurar"),
    ("resultados", "📦 Resultados", "campineira:resultados"),
    ("publicar", "🚀 Publicar", "campineira:publicar"),
    ("historico", "🗂️ Histórico", "campineira:historico"),
]


def _ctx_base(aba_atual):
    return {"abas": ABAS, "aba_atual": aba_atual}


def _lucro_max(p):
    return max((p.get(f"lucro_{m}") or 0) for m in ["shein", "shopee", "temu", "tiktok"])


# ============================================================
# ABA CONFIGURAR E RODAR
# ============================================================

def configurar(request):
    from . import scraper

    client = get_client()
    fila = request.session.get("campineira_fila", [])
    status = scraper.ler_status()
    progresso_anterior = None if status.get("rodando") else bq.buscar_progresso_varredura(client)
    resultados_brutos = bq.ler_resultados(client)

    ctx = _ctx_base("configurar")
    ctx.update({
        "categorias": bq.CATEGORIAS,
        "fila": fila,
        "progresso_anterior": progresso_anterior,
        "total_resultados": len(resultados_brutos),
        "status": status,
    })
    return render(request, "campineira/configurar.html", ctx)


def retomar_varredura(request):
    if request.method == "POST":
        from . import scraper
        if scraper.ler_status().get("rodando"):
            messages.warning(request, "Já tem uma varredura em andamento — aguarde terminar antes de retomar outra.")
            return redirect("campineira:configurar")
        client = get_client()
        progresso_anterior = bq.buscar_progresso_varredura(client)
        if progresso_anterior:
            import threading
            cats_lista = list(progresso_anterior["categorias"].keys())
            filtros_cat = {c: {"estoque_min": 70, "preco_min": 4.99} for c in cats_lista}
            t = threading.Thread(
                target=scraper.rodar_rpa_background,
                args=(filtros_cat, cats_lista, True),
                kwargs={"retomar_id_captura": progresso_anterior["id_captura"],
                        "paginas_ja_feitas": progresso_anterior["categorias"]},
                daemon=True,
            )
            t.start()
            messages.success(request, "Retomando varredura! Acompanhe o progresso aqui.")
    return redirect("campineira:configurar")


def varredura_status(request):
    """JSON pollado pela tela pra mostrar o progresso ao vivo."""
    from django.http import JsonResponse
    from . import scraper
    return JsonResponse(scraper.ler_status())


def fila_adicionar(request):
    if request.method == "POST":
        fila = request.session.get("campineira_fila", [])
        cat = request.POST.get("categoria", "Todas")
        try:
            estoque_min = float(request.POST.get("estoque_min", 70) or 70)
            preco_min = float(request.POST.get("preco_min", 4.99) or 4.99)
        except ValueError:
            estoque_min, preco_min = 70, 4.99

        if cat == "Todas":
            fila = [{"cat": c, "estoque_min": estoque_min, "preco_min": preco_min} for c in bq.CATEGORIAS]
            messages.success(request, "Todas as categorias adicionadas!")
        else:
            cats_na_fila = [f["cat"] for f in fila]
            if cat not in cats_na_fila:
                fila.append({"cat": cat, "estoque_min": estoque_min, "preco_min": preco_min})
            else:
                messages.warning(request, f"{cat} já está na fila!")
        request.session["campineira_fila"] = fila
    return redirect("campineira:configurar")


def fila_remover(request, idx):
    fila = request.session.get("campineira_fila", [])
    if 0 <= idx < len(fila):
        fila.pop(idx)
        request.session["campineira_fila"] = fila
    return redirect("campineira:configurar")


def fila_limpar(request):
    request.session["campineira_fila"] = []
    return redirect("campineira:configurar")


def iniciar_varredura(request):
    if request.method != "POST":
        return redirect("campineira:configurar")
    from . import scraper
    import threading

    if scraper.ler_status().get("rodando"):
        # Clique duplo (ou a pessoa clicando de novo achando que não iniciou)
        # sem essa checagem sobe duas threads raspando a mesma categoria ao
        # mesmo tempo — como o id_captura de cada uma é gerado por horário,
        # se começarem no mesmo segundo as duas gravam os mesmos produtos
        # duas vezes sob a mesma captura. Achado direto no BigQuery: ~210
        # produtos duplicados numa varredura de 1 categoria só.
        messages.warning(request, "Já tem uma varredura em andamento — aguarde terminar antes de iniciar outra.")
        return redirect("campineira:configurar")

    fila = request.session.get("campineira_fila", [])
    if not fila:
        return redirect("campineira:configurar")

    filtros_cat = {item["cat"]: {"estoque_min": item["estoque_min"], "preco_min": item["preco_min"]} for item in fila}
    cats_varrer = [item["cat"] for item in fila]
    request.session["campineira_filtros"] = filtros_cat
    scraper.salvar_filtros(filtros_cat)

    t = threading.Thread(target=scraper.rodar_rpa_background, args=(filtros_cat, cats_varrer, True), daemon=True)
    t.start()
    messages.success(request, "Varredura iniciada! Acompanhe o progresso aqui.")
    return redirect("campineira:configurar")


# ============================================================
# ABA RESULTADOS
# ============================================================

ORDENS = ["Lucro (maior)", "Lucro (menor)", "Estoque (maior)", "Estoque (menor)", "Preço (maior)", "Preço (menor)"]


def _resultados_filtrados(request, client):
    resultados_brutos = bq.ler_resultados(client)
    from . import scraper
    filtros = (scraper.ler_filtros() or request.session.get("campineira_filtros")
               or {c: {"estoque_min": 70, "preco_min": 4.99} for c in bq.CATEGORIAS})
    validados = bq.filtrar_resultados(resultados_brutos, filtros)

    cat_sel = request.GET.get("categoria", "Todas")
    busca = request.GET.get("busca", "")
    ordem = request.GET.get("ordem", "Lucro (maior)")

    if cat_sel != "Todas":
        validados = [p for p in validados if p["categoria"] == cat_sel]
    if busca:
        validados = [p for p in validados if busca.upper() in (p.get("nome") or "").upper()]

    if ordem == "Lucro (maior)":
        validados.sort(key=_lucro_max, reverse=True)
    elif ordem == "Lucro (menor)":
        validados.sort(key=_lucro_max)
    elif ordem == "Estoque (maior)":
        validados.sort(key=lambda x: x.get("estoque") or 0, reverse=True)
    elif ordem == "Estoque (menor)":
        validados.sort(key=lambda x: x.get("estoque") or 0)
    elif ordem == "Preço (maior)":
        validados.sort(key=lambda x: x.get("preco_num") or 0, reverse=True)
    elif ordem == "Preço (menor)":
        validados.sort(key=lambda x: x.get("preco_num") or 0)

    return resultados_brutos, validados, cat_sel, busca, ordem


def resultados(request):
    client = get_client()
    resultados_brutos, validados, cat_sel, busca, ordem = _resultados_filtrados(request, client)
    cats_disp = ["Todas"] + sorted(set(p["categoria"] for p in validados if p.get("categoria")))

    validados_pagina = validados[:150]
    for p in validados_pagina:
        p["lucro_max"] = _lucro_max(p)

    ctx = _ctx_base("resultados")
    ctx.update({
        "total_brutos": len(resultados_brutos),
        "total_validados": len(validados),
        "validados": validados_pagina,  # tela não pesa com milhares de linhas
        "truncado": len(validados) > 150,
        "cats_disp": cats_disp,
        "cat_sel": cat_sel, "busca": busca, "ordem": ordem, "ordens": ORDENS,
    })
    return render(request, "campineira/resultados.html", ctx)


def resultados_excel(request):
    client = get_client()
    _, validados, *_ = _resultados_filtrados(request, client)
    df_exp = pd.DataFrame([{
        "ID": p.get("id"), "Categoria": p.get("categoria"), "Nome": p.get("nome"),
        "Estoque": p.get("estoque"), "Custo_Campineira": p.get("preco"), "Lucro_Maior": _lucro_max(p),
        "Preco_Shein": p.get("preco_shein"), "Preco_Shopee": p.get("preco_shopee"),
        "Preco_Temu": p.get("preco_temu"), "Preco_TikTok": p.get("preco_tiktok"),
        "EAN": p.get("ean"), "Fabricante": p.get("fabricante"), "Link": p.get("link"),
    } for p in validados])
    buf = io.BytesIO()
    df_exp.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    resp = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="campineira_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx"'
    return resp


# ============================================================
# ABA PUBLICAR
# ============================================================

def publicar(request):
    client = get_client()
    resultados_brutos = bq.ler_resultados(client)
    from . import scraper
    filtros = (scraper.ler_filtros() or request.session.get("campineira_filtros")
               or {c: {"estoque_min": 70, "preco_min": 4.99} for c in bq.CATEGORIAS})
    validados = bq.filtrar_resultados(resultados_brutos, filtros)

    if "pub_excluidos" not in request.session:
        request.session["pub_excluidos"] = list(bq.carregar_excluidos(client))
    excluidos = set(request.session["pub_excluidos"])
    validados = [p for p in validados if str(p.get("id")) not in excluidos]

    ids_ja_publicados = bq.ids_com_sku_no_historico(client)
    validados = [p for p in validados if str(p.get("id")) not in ids_ja_publicados]

    com_imagem = [p for p in validados if bq.imagem_parece_valida(p.get("imagem"))]
    sem_imagem = [p for p in validados if not bq.imagem_parece_valida(p.get("imagem"))]

    from upseller.state import ESTADO
    from . import scraper

    # Paginação — antes só mostrava os 100 primeiros e escondia o resto sem
    # nenhum jeito de ver a página seguinte (bug real: 150 produtos prontos,
    # só dava pra publicar os 100 primeiros pela tela). PAGINA_TAMANHO igual
    # ao limite antigo, só que agora com navegação de verdade.
    PAGINA_TAMANHO = 100
    try:
        pagina = int(request.GET.get("pagina") or 1)
    except ValueError:
        pagina = 1
    total_paginas = max(1, -(-len(com_imagem) // PAGINA_TAMANHO))  # ceil sem importar math
    pagina = min(max(pagina, 1), total_paginas)
    inicio = (pagina - 1) * PAGINA_TAMANHO
    com_imagem_pagina = com_imagem[inicio:inicio + PAGINA_TAMANHO]

    ctx = _ctx_base("publicar")
    ctx.update({
        "com_imagem": com_imagem_pagina,
        "sem_imagem": sem_imagem[:50],
        "total_prontos": len(com_imagem),
        "total_sem_imagem": len(sem_imagem),
        "pagina_atual": pagina,
        "total_paginas": total_paginas,
        "paginas_range": range(1, total_paginas + 1),
        "inicio_intervalo": inicio + 1 if com_imagem_pagina else 0,
        "fim_intervalo": inicio + len(com_imagem_pagina),
        "upseller_logado": ESTADO["logado"],
        "varredura_rodando": scraper.ler_status().get("rodando", False),
    })
    return render(request, "campineira/publicar.html", ctx)


def publicar_excluir(request, produto_id):
    if request.method == "POST":
        client = get_client()
        excluidos = set(request.session.get("pub_excluidos", []))
        excluidos.add(produto_id)
        request.session["pub_excluidos"] = list(excluidos)
        bq.salvar_excluidos(client, excluidos)
    return redirect("campineira:publicar")


def publicar_excluir_selecionados(request):
    if request.method == "POST":
        client = get_client()
        ids = request.POST.getlist("selecionados")
        excluidos = set(request.session.get("pub_excluidos", []))
        excluidos.update(ids)
        request.session["pub_excluidos"] = list(excluidos)
        bq.salvar_excluidos(client, excluidos)
        if ids:
            messages.success(request, f"{len(ids)} produto(s) removido(s) da fila de publicação.")
    return redirect("campineira:publicar")


# ============================================================
# ABA HISTÓRICO
# ============================================================

def historico(request):
    """Antes baixava a tabela de histórico INTEIRA (SELECT * sem LIMIT) pra
    memória a cada carregamento — com a tabela já na casa de dezenas de
    milhares de linhas, isso segurava uma thread do servidor por muito
    tempo (achado testando de verdade: travava a página e enfileirava as
    outras requisições atrás dela, parecendo o app inteiro travado). Agora
    os agregados (total, publicados, categorias) e a lista mostrada (só 200
    linhas) são calculados no próprio BigQuery, nunca baixando mais que o
    necessário."""
    client = get_client()
    ctx = _ctx_base("historico")

    cat_sel = request.GET.get("categoria", "Todas")
    busca = request.GET.get("busca", "")
    status_sel = request.GET.get("status", "Todos")

    try:
        stats_df = client.query(
            f"SELECT COUNT(*) AS total, COUNTIF(sku_upseller IS NOT NULL) AS publicados "
            f"FROM `{bq.TABLE_HISTORICO}`"
        ).to_dataframe()
    except Exception as e:
        ctx["erro"] = str(e)[:250]
        return render(request, "campineira/historico.html", ctx)

    total = int(stats_df.iloc[0]["total"]) if not stats_df.empty else 0
    if total == 0:
        ctx["vazio"] = True
        return render(request, "campineira/historico.html", ctx)
    publicados = int(stats_df.iloc[0]["publicados"])

    cats_df = client.query(
        f"SELECT DISTINCT categoria FROM `{bq.TABLE_HISTORICO}` "
        f"WHERE categoria IS NOT NULL ORDER BY categoria"
    ).to_dataframe()
    cats_hist = ["Todas"] + cats_df["categoria"].tolist()

    # WHERE dinâmico, sempre com parâmetros — "busca" vem de request.GET,
    # nunca concatenar texto de usuário direto numa query.
    condicoes = []
    params = []
    if cat_sel != "Todas":
        condicoes.append("categoria = @categoria")
        params.append(bigquery.ScalarQueryParameter("categoria", "STRING", cat_sel))
    if busca:
        condicoes.append("(UPPER(IFNULL(nome, '')) LIKE @busca OR UPPER(IFNULL(sku_upseller, '')) LIKE @busca)")
        params.append(bigquery.ScalarQueryParameter("busca", "STRING", f"%{busca.strip().upper()}%"))
    if status_sel == "Publicados":
        condicoes.append("sku_upseller IS NOT NULL")
    elif status_sel == "Não publicados":
        condicoes.append("sku_upseller IS NULL")
    where_sql = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    job_config = bigquery.QueryJobConfig(query_parameters=params) if params else None

    # COUNT(*) OVER() traz o total de linhas que bateram no filtro (antes do
    # LIMIT) como uma coluna a mais em cada linha — uma query BigQuery a
    # menos do que fazer COUNT(*) separado e depois buscar as linhas.
    df_view = client.query(
        f"SELECT *, COUNT(*) OVER() AS total_filtrado_col FROM `{bq.TABLE_HISTORICO}` "
        f"{where_sql} ORDER BY data_ultima_leitura DESC LIMIT 200",
        job_config=job_config,
    ).to_dataframe()

    total_filtrado = int(df_view.iloc[0]["total_filtrado_col"]) if not df_view.empty else 0

    linhas = []
    for _, row in df_view.iterrows():
        precos = calcular_precos_sugeridos(row.get("preco"))
        linhas.append({
            "foto": row.get("imagem"), "nome": row.get("nome"), "categoria": row.get("categoria"),
            "estoque": row.get("estoque"), "custo": row.get("preco"), "sku": row.get("sku_upseller"),
            "shein": precos.get("preco_shein"), "shopee": precos.get("preco_shopee"),
            "temu": precos.get("preco_temu"), "tiktok": precos.get("preco_tiktok"),
            "primeira_leitura": row.get("data_primeira_leitura"),
            "ultima_leitura": row.get("data_ultima_leitura"),
        })

    ctx.update({
        "total": total, "publicados": publicados, "aguardando": total - publicados,
        "cats_hist": cats_hist,
        "cat_sel": cat_sel, "busca": busca, "status_sel": status_sel,
        "total_filtrado": total_filtrado, "linhas": linhas,
        "truncado": total_filtrado > 200,
    })
    return render(request, "campineira/historico.html", ctx)
