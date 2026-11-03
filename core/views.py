# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

import pandas as pd
from django.contrib import messages
from django.shortcuts import render, redirect

from . import services
from .bigquery import get_client
from .calculos_marketplace import calcular_venda_completo, converter_custo_seguro, obter_sku_base


def login_view(request):
    """Porta de entrada do sistema — tela de login em página inteira, sem
    menu/sidebar por trás (antes disso era uma 'página pública' institucional
    com uma caixinha de login enfiada na barra lateral; não fazia sentido
    pra uma ferramenta interna de uma pessoa só, então virou só isso: logo +
    usuário/senha). Quem já está logado nem vê essa tela, vai direto pro
    painel."""
    if request.session.get("logado"):
        return redirect("dashboard:financeiro")
    return render(request, "core/login.html")


def _buscar_item(df, coluna, termo):
    """Acha a primeira linha cujo campo bate exato (case-insensitive) com o
    termo digitado; se não achar, cai pra "contém" — pra poder pesquisar
    produto/SKU digitando só uma parte, sem precisar escolher de uma lista
    fixa (Gestão de Estoque, Comparativo de Preços)."""
    alvo = (termo or "").strip().upper()
    if not alvo:
        return None
    col = df[coluna].astype(str).str.upper()
    linhas = df[col == alvo]
    if linhas.empty:
        linhas = df[col.str.contains(alvo, na=False, regex=False)]
    return linhas.iloc[0] if not linhas.empty else None


def entrar(request):
    """Login geral que destrava o menu 'Operações' — mesma regra de hoje
    (usuário/senha fixos no código). Fraco de propósito, igual ao original:
    não é o ponto que estamos endurecendo aqui, só portando o comportamento
    existente sem mudar a superfície de risco."""
    if request.method == "POST":
        usuario = request.POST.get("usuario", "")
        senha = request.POST.get("senha", "")
        if usuario == "leandro" and senha == "123":
            request.session["logado"] = True
            return redirect("dashboard:financeiro")
        messages.error(request, "Usuário ou senha incorretos.")
    return redirect("core:login")


def sair(request):
    request.session["logado"] = False
    return redirect("core:login")


# ============================================================
# CALCULADORA (Comparativo de Preços)
# ============================================================

def calculadora(request):
    client = get_client()
    df = services.buscar_produtos_bq(client)
    ctx = {"tem_produtos": not df.empty}
    if df.empty:
        return render(request, "core/calculadora.html", ctx)

    df["Custo_num"] = df["Custo_aquisicao"].apply(converter_custo_seguro)
    ctx["produtos"] = sorted(str(p) for p in df["Produto"].unique())
    ctx["skus"] = sorted(str(s) for s in df["SKU"].unique())

    sku_sel = request.GET.get("sku") or ""
    prod_sel = request.GET.get("produto") or ""
    margem = float(request.GET.get("margem") or 15.0)
    ctx["sku_sel"], ctx["prod_sel"], ctx["margem"] = sku_sel, prod_sel, margem

    item = None
    if sku_sel:
        item = _buscar_item(df, "SKU", sku_sel)
        if item is None:
            ctx["nao_encontrado"] = sku_sel
    elif prod_sel:
        item = _buscar_item(df, "Produto", prod_sel)
        if item is None:
            ctx["nao_encontrado"] = prod_sel

    if item is not None:
        custo = item["Custo_num"]
        ctx["selecionado"] = {"produto": item["Produto"], "sku": item["SKU"], "custo": custo}
        ctx["resultado"] = [
            {"canal": nome, "preco": p, "lucro": l}
            for nome, (p, l) in {
                "SHEIN": calcular_venda_completo(custo, margem, "shein"),
                "SHOPEE": calcular_venda_completo(custo, margem, "shopee"),
                "TEMU": calcular_venda_completo(custo, margem, "temu", margem_livre_temu=True),
                "TIKTOK": calcular_venda_completo(custo, margem, "tiktok"),
                "D.LUN": calcular_venda_completo(custo, margem, "dlun"),
            }.items()
        ]
    return render(request, "core/calculadora.html", ctx)


# ============================================================
# CADASTRO (Novo Item na Base)
# ============================================================

def _redirect_variante(sku_base_sel, nome_base):
    """Volta pra tela de cadastro já com o mesmo produto base selecionado
    (query string montada com urlencode — direto em f-string quebraria com
    acento/espaço no nome do produto, ex: 'Pijama Feminino Canelado')."""
    from urllib.parse import urlencode
    from django.urls import reverse
    query = urlencode({"variante_base": f"{sku_base_sel} - {nome_base}"})
    return redirect(f"{reverse('core:cadastro')}?{query}")


def _buscar_produtos_base(client):
    """Um produto por SKU BASE (ex: AM-01), agrupando as variantes que já
    existem (AM-01-AZ, AM-01-BO...) — usado pra popular a busca de
    'Adicionar Variante a Produto Existente', pra não listar cada cor/
    tamanho já cadastrado como se fosse um produto novo."""
    return services.buscar_produtos_base_bq(client)


def cadastro(request):
    client = get_client()
    n_variantes = int(request.session.get("cadastro_n_variantes", 0))
    ctx = {"n_variantes": n_variantes, "variantes_range": range(n_variantes)}

    # ── Adicionar Variante a Produto Existente ──────────────────────────
    # Busca guiada (datalist), não campo livre: a pessoa digita/escolhe um
    # produto que JÁ existe na base, e só nesse caso o formulário de
    # variante nova aparece — evita criar produto "órfão" por SKU base
    # digitado errado.
    df_base_completo = _buscar_produtos_base(client)
    if not df_base_completo.empty:
        df_produtos_unicos = df_base_completo.groupby("sku_base").first().reset_index()
        ctx["opcoes_variante"] = [f"{r['sku_base']} - {r['Produto']}" for _, r in df_produtos_unicos.iterrows()]
    else:
        ctx["opcoes_variante"] = []

    sel_variante = request.GET.get("variante_base")
    if sel_variante:
        sku_base_sel = sel_variante.split(" - ")[0].strip().upper()
        linhas_base = df_base_completo[df_base_completo["sku_base"] == sku_base_sel] if not df_base_completo.empty else pd.DataFrame()
        if not linhas_base.empty:
            ctx["produto_base_selecionado"] = {
                "sku_base": sku_base_sel,
                "nome": linhas_base.iloc[0]["Produto"],
                "marketplaces": sorted(linhas_base["marketplace"].unique().tolist()),
                "custo_sugerido": float(linhas_base["Custo_aquisicao"].mode().iloc[0]),
                "variantes_existentes": sorted(linhas_base["SKU"].unique().tolist()),
            }

    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "add_variante":
            ctx["n_variantes"] += 1
            ctx["variantes_range"] = range(ctx["n_variantes"])
            request.session["cadastro_n_variantes"] = ctx["n_variantes"]
            return render(request, "core/cadastro.html", ctx)
        if acao == "limpar":
            request.session["cadastro_n_variantes"] = 0
            return redirect("core:cadastro")

        if acao == "salvar_variante":
            sku_base_sel = request.POST.get("sku_base_sel", "").strip().upper()
            nome_base = request.POST.get("nome_base", "").strip()
            marketplaces_csv = request.POST.get("marketplaces_sel", "")
            mkt_list = [m for m in marketplaces_csv.split(",") if m]
            v_sku = request.POST.get("v_sku", "").strip().upper()
            v_char = request.POST.get("v_char", "").strip()
            v_custo = request.POST.get("v_custo")

            if not sku_base_sel or not mkt_list:
                messages.error(request, "⚠️ Escolha um produto já cadastrado antes de adicionar a variante.")
                return redirect("core:cadastro")
            if not v_sku:
                messages.error(request, "⚠️ Preencha o SKU da nova variante.")
                return _redirect_variante(sku_base_sel, nome_base)

            try:
                from google.cloud import bigquery
                job_config = bigquery.QueryJobConfig(
                    query_parameters=[bigquery.ScalarQueryParameter("sku", "STRING", v_sku)]
                )
                df_v = client.query(
                    f"SELECT SKU FROM `{services.TABLE_PRODUTOS}` WHERE SKU = @sku", job_config=job_config
                ).to_dataframe()
            except Exception:
                df_v = pd.DataFrame()
            if not df_v.empty:
                messages.error(request, f"❌ SKU '{v_sku}' já existe.")
                return _redirect_variante(sku_base_sel, nome_base)

            try:
                custo_variante = float(v_custo) if v_custo else 0.01
                nome_completo = f"{nome_base} {v_char}" if v_char else nome_base
                lote = [{"marketplace": aba, "sku": v_sku, "produto": nome_completo, "custo_aquisicao": custo_variante}
                        for aba in mkt_list]
                client.load_table_from_dataframe(pd.DataFrame(lote), services.TABLE_PRODUTOS).result()
                services.invalidar_cache_produtos()
                messages.success(request, f"✅ Variante '{v_sku}' adicionada a {nome_base} ({len(lote)} registros).")
            except Exception as e:
                messages.error(request, f"Falha técnica: {e}")
            return redirect("core:cadastro")

        if acao == "salvar":
            marketplace = request.POST.get("marketplace", "todos")
            nome = request.POST.get("nome", "").strip()
            sku_base = request.POST.get("sku_base", "").strip().upper()
            custo_padrao = float(request.POST.get("custo_padrao") or 0.01)

            variantes = []
            for i in range(ctx["n_variantes"]):
                v_sku = request.POST.get(f"vsku_{i}", "").strip().upper()
                v_char = request.POST.get(f"vchar_{i}", "").strip()
                v_custo = request.POST.get(f"vcost_{i}")
                if v_sku:
                    variantes.append({
                        "nome_completo": f"{nome} {v_char}" if v_char else nome,
                        "sku_variante": v_sku,
                        "custo_variante": float(v_custo or custo_padrao),
                    })

            todos_skus = [sku_base] + [v["sku_variante"] for v in variantes] if sku_base else [v["sku_variante"] for v in variantes]
            if todos_skus:
                format_skus = ", ".join(f"'{s}'" for s in todos_skus)
                try:
                    df_v = client.query(
                        f"SELECT SKU FROM `{services.TABLE_PRODUTOS}` WHERE SKU IN ({format_skus})"
                    ).to_dataframe()
                except Exception:
                    df_v = pd.DataFrame()
                if not df_v.empty:
                    messages.error(request, f"❌ SKU(s) já existe(m): {', '.join(df_v['SKU'].unique().tolist())}")
                    ctx["bloqueado"] = True
                    return render(request, "core/cadastro.html", ctx)

            if not nome or not sku_base:
                messages.error(request, "⚠️ Preencha o Nome e o SKU Base.")
                return render(request, "core/cadastro.html", ctx)

            try:
                mkt_list = ["shein", "shopee", "temu", "tiktok"] if marketplace == "todos" else [marketplace]
                lote = []
                for aba in mkt_list:
                    lote.append({"marketplace": aba, "sku": sku_base, "produto": nome, "custo_aquisicao": custo_padrao})
                    for var in variantes:
                        lote.append({"marketplace": aba, "sku": var["sku_variante"], "produto": var["nome_completo"], "custo_aquisicao": var["custo_variante"]})
                client.load_table_from_dataframe(pd.DataFrame(lote), services.TABLE_PRODUTOS).result()
                services.invalidar_cache_produtos()
                messages.success(request, f"✅ Sucesso! {len(lote)} registros salvos.")
                request.session["cadastro_n_variantes"] = 0
            except Exception as e:
                messages.error(request, f"Falha técnica: {e}")
            return redirect("core:cadastro")

    return render(request, "core/cadastro.html", ctx)


# ============================================================
# ALTERAR PREÇO (fila de atualização em lote)
# ============================================================

def alterar_preco(request):
    client = get_client()
    df_produtos = services.buscar_produtos_alterar_preco_bq(client)
    fila = request.session.get("alterar_preco_fila", [])
    ctx = {
        "opcoes": [f"{r['sku']} - {r['produto']}" for _, r in df_produtos.iterrows()],
        "fila": fila,
    }
    sel = request.GET.get("item")
    if sel:
        sku_ref = sel.split(" - ")[0]
        linha = df_produtos[df_produtos["sku"] == sku_ref]
        if not linha.empty:
            dados = linha.iloc[0]
            ctx["selecionado"] = {"sku": sku_ref, "produto": dados["produto"], "custo_atual": float(dados["custo_aquisicao"])}
    return render(request, "core/alterar_preco.html", ctx)


def alterar_preco_adicionar(request):
    if request.method == "POST":
        fila = request.session.get("alterar_preco_fila", [])
        fila.append({
            "sku": request.POST.get("sku"), "produto": request.POST.get("produto"),
            "novo_valor": float(request.POST.get("novo_valor") or 0),
        })
        request.session["alterar_preco_fila"] = fila
    return redirect("core:alterar_preco")


def alterar_preco_remover(request, idx):
    fila = request.session.get("alterar_preco_fila", [])
    if 0 <= idx < len(fila):
        fila.pop(idx)
        request.session["alterar_preco_fila"] = fila
    return redirect("core:alterar_preco")


def alterar_preco_limpar(request):
    request.session["alterar_preco_fila"] = []
    return redirect("core:alterar_preco")


def alterar_preco_enviar(request):
    if request.method == "POST":
        from google.cloud import bigquery
        client = get_client()
        fila = request.session.get("alterar_preco_fila", [])
        try:
            for item in fila:
                job_config = bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("valor", "FLOAT64", float(item["novo_valor"])),
                    bigquery.ScalarQueryParameter("sku", "STRING", item["sku"]),
                ])
                client.query(
                    f"UPDATE `{services.TABLE_PRODUTOS}` SET custo_aquisicao = @valor WHERE sku = @sku",
                    job_config=job_config,
                ).result()
            services.invalidar_cache_produtos()
            messages.success(request, f"✅ Sucesso! {len(fila)} itens atualizados.")
            request.session["alterar_preco_fila"] = []
        except Exception as e:
            messages.error(request, f"Erro no processamento em lote: {e}")
    return redirect("core:alterar_preco")


# ============================================================
# GESTÃO DE ESTOQUE
# ============================================================

def estoque(request):
    client = get_client()
    df_base = services.buscar_produtos_bq(client)
    ctx = {"produtos": sorted(df_base["Produto"].unique()) if not df_base.empty else [],
           "skus": sorted(df_base["SKU"].unique()) if not df_base.empty else []}

    sku_busca = request.GET.get("sku_busca", "").strip()
    produto_busca = request.GET.get("produto_busca", "").strip()
    ctx["sku_busca"] = sku_busca
    ctx["produto_busca"] = produto_busca
    if not df_base.empty:
        df_base["Custo_num"] = df_base["Custo_aquisicao"].apply(converter_custo_seguro)
        item = None
        if sku_busca:
            item = _buscar_item(df_base, "SKU", sku_busca)
            if item is None:
                ctx["sku_nao_encontrado"] = sku_busca
        elif produto_busca:
            item = _buscar_item(df_base, "Produto", produto_busca)
            if item is None:
                ctx["produto_nao_encontrado"] = produto_busca
        if item is not None:
            ctx["item_selecionado"] = {"produto": item["Produto"], "sku": item["SKU"], "custo_num": float(item["Custo_num"])}

    try:
        df_raw = services.buscar_estoque_bq(client)
    except Exception as e:
        ctx["erro"] = str(e)[:250]
        return render(request, "core/estoque.html", ctx)

    if "item_selecionado" in ctx and not df_raw.empty:
        sku_item = ctx["item_selecionado"]["sku"]
        ctx["item_selecionado"]["quantidade_atual"] = int(df_raw[df_raw["sku"] == sku_item]["quantidade"].sum())
    elif "item_selecionado" in ctx:
        ctx["item_selecionado"]["quantidade_atual"] = 0

    if df_raw.empty:
        ctx["vazio"] = True
        return render(request, "core/estoque.html", ctx)

    total_investido = (df_raw["quantidade"] * df_raw["valor_pago"]).sum()
    lucro_potencial = sum(services.recomendar_canal(r["valor_pago"])[1] * r["quantidade"] for _, r in df_raw.iterrows())
    qtd_total = df_raw["quantidade"].sum()

    df_visual = df_raw.groupby(["sku", "produto"]).agg({"quantidade": "sum", "valor_pago": "mean"}).reset_index()
    linhas = []
    for idx, r in df_visual.iterrows():
        canal, lucro_un = services.recomendar_canal(r["valor_pago"])
        linhas.append({
            "idx": idx, "sku": r["sku"], "produto": r["produto"], "canal": canal,
            "lucro_total": lucro_un * r["quantidade"], "quantidade": int(r["quantidade"]),
            "valor_pago": float(r["valor_pago"]),
        })

    ctx.update({
        "total_investido": total_investido, "lucro_potencial": lucro_potencial, "qtd_total": int(qtd_total),
        "linhas": linhas,
    })
    return render(request, "core/estoque.html", ctx)


def estoque_entrada(request):
    if request.method == "POST":
        from google.cloud import bigquery
        client = get_client()
        try:
            produto = request.POST.get("produto")
            sku = request.POST.get("sku")
            qtd = int(request.POST.get("quantidade") or 1)
            valor_pago = float(request.POST.get("valor_pago") or 0)
            data_brasilia = (datetime.utcnow() - timedelta(hours=3)).date()

            df_entrada = pd.DataFrame([{"produto": produto, "sku": sku, "quantidade": qtd,
                                         "valor_pago": valor_pago, "data_entrada": data_brasilia}])
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND",
                                                 schema=[bigquery.SchemaField("data_entrada", "DATE")])
            client.load_table_from_dataframe(df_entrada, services.TABLE_ESTOQUE, job_config=job_config).result()

            df_hist = pd.DataFrame([{"produto": produto, "sku": sku, "quantidade": qtd, "valor_pago": valor_pago,
                                      "data_movimentacao": data_brasilia, "tipo_movimentacao": "ENTRADA"}])
            client.load_table_from_dataframe(df_hist, services.TABLE_ESTOQUE_HIST).result()
            services.invalidar_cache_estoque()
            messages.success(request, "Estoque e Histórico atualizados!")
        except Exception as e:
            messages.error(request, f"Erro ao salvar: {e}")
    return redirect("core:estoque")


def _mover_estoque(client, produto, sku, valor_pago, quantidade_atual, ajuste):
    """Núcleo compartilhado por estoque_ajustar (+/- livre) e estoque_saida
    (sempre negativo): recalcula o saldo, substitui a linha viva do SKU em
    tb_estoque e registra o movimento no histórico. Retorna (ok, erro)."""
    from google.cloud import bigquery
    if ajuste == 0:
        return True, None
    dt_br = (datetime.utcnow() - timedelta(hours=3)).date()
    n_saldo = quantidade_atual + ajuste
    if n_saldo < 0:
        return False, "Saldo insuficiente!"
    job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("sku", "STRING", sku)])
    client.query(f"DELETE FROM `{services.TABLE_ESTOQUE}` WHERE sku = @sku", job_config=job_config).result()
    if n_saldo > 0:
        df_up = pd.DataFrame([{"produto": produto, "sku": sku, "quantidade": n_saldo,
                                "valor_pago": valor_pago, "data_entrada": dt_br}])
        client.load_table_from_dataframe(df_up, services.TABLE_ESTOQUE).result()
    tipo_aj = "ENTRADA" if ajuste > 0 else "BAIXA"
    df_h = pd.DataFrame([{"produto": produto, "sku": sku, "quantidade": ajuste, "valor_pago": valor_pago,
                           "data_movimentacao": dt_br, "tipo_movimentacao": tipo_aj}])
    client.load_table_from_dataframe(df_h, services.TABLE_ESTOQUE_HIST).result()
    services.invalidar_cache_estoque()
    return True, None


def estoque_ajustar(request):
    if request.method == "POST":
        client = get_client()
        try:
            sku = request.POST.get("sku")
            produto = request.POST.get("produto")
            valor_pago = float(request.POST.get("valor_pago"))
            quantidade_atual = int(request.POST.get("quantidade_atual"))
            ajuste = int(request.POST.get("ajuste") or 0)
            ok, erro = _mover_estoque(client, produto, sku, valor_pago, quantidade_atual, ajuste)
            if not ok:
                messages.error(request, erro)
            elif ajuste != 0:
                messages.success(request, "Estoque atualizado!")
        except Exception as e:
            messages.error(request, f"Erro: {e}")
    return redirect("core:estoque")


def estoque_saida(request):
    """Registrar Saída de Mercadoria — mesma ideia da Entrada, só que
    sempre subtrai do saldo atual (venda fora do marketplace, perda,
    quebra etc.). Reaproveita a mesma lógica de _mover_estoque/estoque_ajustar,
    só com o sinal já invertido antes de chamar."""
    if request.method == "POST":
        client = get_client()
        try:
            sku = request.POST.get("sku")
            produto = request.POST.get("produto")
            valor_pago = float(request.POST.get("valor_pago") or 0)
            quantidade_atual = int(request.POST.get("quantidade_atual") or 0)
            quantidade_saida = int(request.POST.get("quantidade_saida") or 0)
            if quantidade_saida <= 0:
                messages.error(request, "Informe uma quantidade de saída maior que 0.")
            else:
                ok, erro = _mover_estoque(client, produto, sku, valor_pago, quantidade_atual, -quantidade_saida)
                if ok:
                    messages.success(request, f"Saída de {quantidade_saida} un. registrada!")
                else:
                    messages.error(request, erro)
        except Exception as e:
            messages.error(request, f"Erro ao registrar saída: {e}")
    return redirect("core:estoque")


# ============================================================
# VALIDAR VENDAS
# ============================================================

def validar_vendas(request):
    client = get_client()
    ctx = {}
    try:
        n_pendentes = client.query(
            f"SELECT COUNT(*) AS n FROM `{services.TABLE_VENDAS}` WHERE pendente = TRUE"
        ).to_dataframe()["n"][0]
    except Exception:
        n_pendentes = None
    ctx["n_pendentes"] = n_pendentes

    try:
        df_sem_cadastro, df_divergentes = services.buscar_pendencias_validacao(client)
    except Exception as e:
        messages.error(request, f"Erro ao buscar pendências: {e}")
        df_sem_cadastro, df_divergentes = pd.DataFrame(), pd.DataFrame()

    ctx["sem_cadastro"] = df_sem_cadastro.to_dict("records") if not df_sem_cadastro.empty else []
    so_com_venda = request.GET.get("so_com_venda") == "1"
    df_div_exibir = df_divergentes[df_divergentes["vendas"] > 0] if (so_com_venda and not df_divergentes.empty) else df_divergentes
    ctx["divergentes"] = df_div_exibir.to_dict("records") if not df_div_exibir.empty else []
    ctx["total_divergentes"] = len(df_divergentes)
    ctx["n_divergentes_com_venda"] = int((df_divergentes["vendas"] > 0).sum()) if not df_divergentes.empty else 0
    ctx["so_com_venda"] = so_com_venda
    return render(request, "core/validar_vendas.html", ctx)


def validar_vendas_fallback(request):
    if request.method == "POST":
        client = get_client()
        try:
            n = services.aplicar_fallback_sku_base(client)
            messages.success(request, f"{n} venda(s) recalculada(s) usando o custo do SKU principal." if n else "Nenhuma venda pendente pra esse tipo de correção.")
        except Exception as e:
            messages.error(request, f"Erro ao aplicar fallback: {e}")
    return redirect("core:validar_vendas")


def validar_vendas_sem_cadastro(request):
    if request.method == "POST":
        client = get_client()
        sku = request.POST.get("sku")
        nome = request.POST.get("nome", "").strip()
        custo = float(request.POST.get("custo") or 0)
        if not nome or custo <= 0:
            messages.error(request, f"Preencha o nome e um custo maior que 0 pro SKU {sku}.")
        else:
            try:
                n = services.resolver_sku_sem_cadastro(client, sku, nome, custo)
                messages.success(request, f"SKU {sku} cadastrado. {n} venda(s) recalculada(s).")
            except Exception as e:
                messages.error(request, f"Erro ao salvar {sku}: {e}")
    return redirect("core:validar_vendas")


def validar_vendas_divergente(request):
    if request.method == "POST":
        client = get_client()
        skus = request.POST.get("skus", "").split(",")
        custo = float(request.POST.get("custo") or 0)
        try:
            n = services.resolver_grupo_divergente(client, skus, custo)
            messages.success(request, f"{', '.join(skus)} corrigido(s) pra R$ {custo:.2f}. {n} venda(s) recalculada(s).")
        except Exception as e:
            messages.error(request, f"Erro ao corrigir: {e}")
    return redirect("core:validar_vendas")
