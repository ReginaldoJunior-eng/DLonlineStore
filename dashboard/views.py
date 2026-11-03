# -*- coding: utf-8 -*-
"""Dashboard Financeiro — portado de LeMarketplace.py (bloco `pg == "Dashboard"`).
Mesma consulta, mesmas contas, mesma regra de negócio; só a forma de guardar
estado que muda (session do Django em vez de st.session_state) e os gráficos
(Plotly gerado no servidor e embutido como HTML, em vez de st.plotly_chart).

O painel "Atualizar via Upseller" (login automático + exportar pedidos) ainda
não foi portado — depende da infraestrutura de tarefas em background, que é a
próxima grande etapa do plano. Por enquanto essa view só faz a parte de
LEITURA (todo o dashboard em si), que já reflete dados reais do BigQuery.
"""
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from django.shortcuts import render, redirect

from core import services
from core.bigquery import get_client

MESES_MAP = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
             7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}


def _ler_meta_mensal(client):
    try:
        dfm = client.query(
            "SELECT valor FROM `leandro-marketplace.DL_Store_Online.tb_config_dashboard` "
            "WHERE chave = 'meta_mensal'"
        ).to_dataframe()
        if not dfm.empty:
            return float(dfm['valor'].iloc[0])
    except Exception:
        pass
    return 0.0


def _salvar_meta_mensal(client, valor):
    try:
        client.query(
            "DELETE FROM `leandro-marketplace.DL_Store_Online.tb_config_dashboard` "
            "WHERE chave = 'meta_mensal'"
        ).result()
    except Exception:
        pass
    df_meta = pd.DataFrame([{"chave": "meta_mensal", "valor": float(valor)}])
    client.load_table_from_dataframe(
        df_meta, "leandro-marketplace.DL_Store_Online.tb_config_dashboard"
    ).result()


def financeiro(request):
    client = get_client()

    if request.method == "POST" and "nova_meta" in request.POST:
        try:
            _salvar_meta_mensal(client, float(request.POST.get("nova_meta", 0) or 0))
        except ValueError:
            pass
        return redirect("dashboard:financeiro")

    from upseller.state import ESTADO
    ctx = {"upseller_logado": ESTADO["logado"]}
    try:
        df_vendas = services.buscar_vendas_realizadas_bq(client)
    except Exception as e:
        ctx["erro"] = f"Erro no Dashboard: {e}"
        return render(request, "dashboard/financeiro.html", ctx)

    if df_vendas.empty:
        ctx["sem_vendas"] = True
        return render(request, "dashboard/financeiro.html", ctx)

    df_vendas.columns = ['Produto', 'SKU', 'Preço Venda', 'Quantidade', 'Data', 'Lucro Total', 'Marketplace']
    df_vendas['Preço Venda'] = pd.to_numeric(df_vendas['Preço Venda'])
    df_vendas['Lucro Total'] = pd.to_numeric(df_vendas['Lucro Total'])
    df_vendas['Quantidade'] = pd.to_numeric(df_vendas['Quantidade'])
    # 'Preço Venda' já é o Valor do Pedido inteiro (não um preço unitário), então
    # o faturamento é o próprio valor — não multiplicar pela Quantidade (senão
    # infla o faturamento, e por tabela o Custo, em pedidos com mais de 1
    # unidade do mesmo produto).
    df_vendas['Faturamento'] = df_vendas['Preço Venda']
    df_vendas['Custo'] = df_vendas['Faturamento'] - df_vendas['Lucro Total']
    df_vendas['Data'] = pd.to_datetime(df_vendas['Data'])
    df_vendas['Mes_Ref'] = df_vendas['Data'].dt.strftime('%Y-%m')

    hoje = datetime.utcnow() - timedelta(hours=3)
    mes_atual_ref = hoje.strftime('%Y-%m')
    df_mes_atual = df_vendas[df_vendas['Mes_Ref'] == mes_atual_ref]

    fat_mes = df_mes_atual['Faturamento'].sum()
    lucro_mes = df_mes_atual['Lucro Total'].sum()
    custo_mes = fat_mes - lucro_mes
    pct_lucro_mes = (lucro_mes / fat_mes * 100) if fat_mes else 0

    meta_mensal = _ler_meta_mensal(client)
    pct_meta = min(100, (fat_mes / meta_mensal * 100)) if meta_mensal else 0
    circunferencia_meta = 138.2  # 2 * pi * raio(22) do anel svg no template
    # String formatada em Python puro (ponto decimal), não pelo template — um
    # atributo SVG (stroke-dashoffset) quebra se vier com vírgula, e o filtro
    # floatformat do Django usa vírgula por causa do LANGUAGE_CODE 'pt-br'.
    offset_meta_svg = f"{circunferencia_meta * (1 - pct_meta / 100):.2f}"

    # ── Gráfico Receita Operacional (Mensal ou Diário de um mês) ────────
    visao = request.GET.get("visao", "Mensal")
    opcoes_meses = sorted(df_vendas['Mes_Ref'].unique(), reverse=True)
    mes_diario = request.GET.get("mes") or (opcoes_meses[0] if opcoes_meses else mes_atual_ref)

    if visao == "Diário" and mes_diario in opcoes_meses:
        df_dia = df_vendas[df_vendas['Mes_Ref'] == mes_diario]
        df_plot = df_dia.groupby('Data').agg(
            {'Faturamento': 'sum', 'Lucro Total': 'sum', 'Custo': 'sum', 'Quantidade': 'sum'}
        ).reset_index().sort_values('Data')
        df_plot['Data_Label'] = df_plot['Data'].dt.strftime('%d/%m')
    else:
        visao = "Mensal"
        df_plot = df_vendas.groupby('Mes_Ref').agg(
            {'Faturamento': 'sum', 'Lucro Total': 'sum', 'Custo': 'sum', 'Quantidade': 'sum'}
        ).reset_index().sort_values('Mes_Ref')
        df_plot['Data_Label'] = df_plot['Mes_Ref'].apply(
            lambda m: MESES_MAP[int(m.split('-')[1])] + '/' + m.split('-')[0][-2:]
        )

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=df_plot['Data_Label'], y=df_plot['Custo'], name='Custo',
        marker_color='#bfdcf7', hovertemplate='R$ %{y:,.2f}<extra></extra>'
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=df_plot['Data_Label'], y=df_plot['Lucro Total'], name='Lucro Líquido',
        marker_color='#0a66c2', hovertemplate='R$ %{y:,.2f}<extra></extra>',
        text=df_plot['Lucro Total'].apply(lambda x: f'R$ {x:,.2f}'),
        textposition='outside', textfont=dict(size=15, color='#08306b', family="Arial")
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=df_plot['Data_Label'], y=df_plot['Quantidade'], name='Qtd Vendas',
        mode='lines+markers+text',
        line=dict(color='#0d3f8a', width=3), marker=dict(size=8, color='#0d3f8a'),
        text=df_plot['Quantidade'], textposition="top center",
        textfont=dict(size=14, color='#0d3f8a', family="Arial"),
        hovertemplate='Vendas: %{y}<extra></extra>'
    ), secondary_y=True)
    fig.update_layout(
        barmode='stack',
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=True,
                   range=[0, df_plot['Faturamento'].max() * 2.2]),
        yaxis2=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=True,
                    range=[df_plot['Quantidade'].max() * -1.5, df_plot['Quantidade'].max() * 1.2]),
        xaxis=dict(title="Competência / Dias", showgrid=False, showline=True, linecolor='#E5E7EB',
                   tickfont=dict(color='#6B7280', size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5, font=dict(color="#374151", size=13)),
        margin=dict(l=10, r=10, t=80, b=60),
        hovermode='x unified',
    )
    # include_plotlyjs=False: a lib já é carregada 1x via <script> local
    # (dashboard/static/dashboard/plotly.min.js, mesma versão instalada) no
    # <head> do financeiro.html — antes carregava via CDN a cada navegação
    # Mensal/Diário (full page reload), baixando ~3-5MB da internet toda
    # vez, o que deixava a troca entre as visões lenta/travada. Local
    # resolve isso e também funciona offline.
    grafico_receita_html = fig.to_html(full_html=False, include_plotlyjs=False, config={'displayModeBar': False})

    # ── Pizza: Lucro Líquido por Plataforma ──────────────────────────────
    df_pizza = df_vendas.groupby('Marketplace')['Lucro Total'].sum().reset_index()
    cores_map = {'shein': '#FFD700', 'shopee': '#EE4D2D', 'temu': '#FF8C00', 'tiktok': '#000000'}
    cores_lista = [cores_map.get(m, '#6B7280') for m in df_pizza['Marketplace']]
    fig_pizza = go.Figure(data=[go.Pie(
        labels=df_pizza['Marketplace'].str.upper(), values=df_pizza['Lucro Total'], hole=.4,
        marker=dict(colors=cores_lista), textinfo='label+value+percent',
        texttemplate='<b>%{label}</b><br>R$ %{value:,.2f}<br>(%{percent:.1%})',
        hovertemplate='R$ %{value:,.2f}<extra></extra>'
    )])
    fig_pizza.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=30, b=20), showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5, font=dict(color="#374151", size=12)),
    )
    grafico_pizza_html = fig_pizza.to_html(full_html=False, include_plotlyjs=False, config={'displayModeBar': False})

    ctx.update({
        "fat_mes": fat_mes, "custo_mes": custo_mes, "lucro_mes": lucro_mes, "pct_lucro_mes": pct_lucro_mes,
        "meta_mensal": meta_mensal, "pct_meta": pct_meta, "offset_meta_svg": offset_meta_svg,
        "visao": visao, "opcoes_meses": [(m, MESES_MAP[int(m.split('-')[1])] + '/' + m.split('-')[0][-2:]) for m in opcoes_meses],
        "mes_diario": mes_diario,
        "grafico_receita_html": grafico_receita_html,
        "grafico_pizza_html": grafico_pizza_html,
        "faturamento_total": df_vendas['Faturamento'].sum(),
        "lucro_total_geral": df_vendas['Lucro Total'].sum(),
        "itens_vendidos": int(df_vendas['Quantidade'].sum()),
    })
    return render(request, "dashboard/financeiro.html", ctx)
