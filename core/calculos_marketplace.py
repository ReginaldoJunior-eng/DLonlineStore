# -*- coding: utf-8 -*-
"""Funções de cálculo de preço/lucro compartilhadas entre dashboard/ e
campineira/. Portado sem alterações do CodigosPython2 (mesma regra de negócio,
mesmas taxas por plataforma) — só a nota do docstring original mudou: lá o
motivo de isolar essas funções num módulo neutro era evitar reexecutar o
script principal do Streamlit ao importar; aqui, sem Streamlit, isso não é
mais um risco, mas o módulo continua neutro (sem Django/views) porque faz
sentido por si só: são cálculos puros, testáveis sem precisar de request/DB.
"""

import re

MARGEM_PADRAO = 15.0


def calcular_precos_sugeridos(preco_str):
    """Preço/lucro sugeridos nas 4 plataformas a partir do custo (string tipo
    'R$ 12,90'), usando a margem padrão — mesma função usada em Resultados e
    Histórico da Campineira no app original."""
    try:
        custo = float(str(preco_str).replace("R$", "").replace(".", "").replace(",", ".").strip())
    except Exception:
        return {}
    precos = {}
    for mkt in ["shein", "shopee", "temu", "tiktok"]:
        p, l = calcular_venda_completo(custo, MARGEM_PADRAO, mkt)
        precos[f"preco_{mkt}"] = round(p, 2)
        precos[f"lucro_{mkt}"] = round(l, 2)
    return precos


def obter_sku_base(sku):
    """Extrai o SKU 'principal' de uma variante — ex: CP-784-AM (cor Âmbar) vira
    CP-784. Regra: PREFIXO-NÚMERO seguido de um hífen e mais alguma coisa (letra,
    cor, código) é sempre uma variante do produto PREFIXO-NÚMERO; tudo depois do
    segundo hífen é a parte variável e não define um custo próprio — o custo de
    aquisição é o mesmo do principal. SKU sem esse padrão (ex: sem segundo hífen)
    volta como veio. Usado como fallback quando a variante exata não tem custo
    cadastrado em tb_produtos, mas o principal tem."""
    if not sku:
        return sku
    m = re.match(r'^([A-Za-z]+-\d+)-.+$', sku.strip())
    return m.group(1) if m else sku.strip()


def converter_custo_seguro(valor_raw):
    if valor_raw is None or valor_raw == "":
        return 0.0

    if isinstance(valor_raw, (int, float)):
        return float(valor_raw)

    s = str(valor_raw).replace('R$', '').replace(' ', '').strip()
    try:
        if ',' in s and '.' in s:
            if s.find('.') < s.find(','):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0


def calcular_venda_completo(custo_aquisicao, margem_percentual, mkt, margem_livre_temu=False):
    """margem_livre_temu=True faz o Temu também respeitar margem_percentual
    em vez do 30% fixo de sempre — só usado no Comparativo de Preços (tela
    de simulação livre); em todo o resto do app (sugestão automática de
    preço na Campineira etc.) o Temu continua fixo em 30%, sem mudar nada."""
    imposto_tax = 0.06
    margem_alvo = margem_percentual / 100
    custo_embalagem = 1.00
    if mkt == "shein":
        comissao_mkt, taxa_fixa = 0.18, 5.0
        divisor = 1 - (comissao_mkt + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_embalagem + taxa_fixa) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comissao_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_embalagem - taxa_fixa
        return preco, lucro
    elif mkt == "shopee":
        def testar_faixa(comis, taxa):
            div = 1 - (comis + imposto_tax + margem_alvo)
            return (custo_aquisicao + custo_embalagem + taxa) / div if div > 0 else 0
        p_venda = testar_faixa(0.20, 4.0)
        if p_venda > 79.99:
            p_venda = testar_faixa(0.14, 16.0)
            if p_venda > 99.99:
                p_venda = testar_faixa(0.14, 20.0)
                if p_venda > 199.99: p_venda = testar_faixa(0.14, 26.0)
        if p_venda <= 79.99: c_final, t_final = 0.20, 4.0
        elif p_venda <= 99.99: c_final, t_final = 0.14, 16.0
        elif p_venda <= 199.99: c_final, t_final = 0.14, 20.0
        else: c_final, t_final = 0.14, 26.0
        lucro = p_venda - (p_venda * c_final) - (p_venda * imposto_tax) - custo_aquisicao - custo_embalagem - t_final
        return p_venda, lucro
    elif mkt == "temu":
        # Margem do Temu é FIXA em 30% por padrão — ignora o margem_percentual
        # recebido (que continua valendo normalmente pras outras 3
        # plataformas), exceto quando margem_livre_temu=True (Comparativo de
        # Preços, ver docstring acima).
        margem_temu = margem_alvo if margem_livre_temu else 0.30
        divisor = 1 - (imposto_tax + margem_temu)
        preco = (custo_aquisicao + custo_embalagem) / divisor if divisor > 0 else 0
        lucro = preco - (preco * imposto_tax) - custo_aquisicao - custo_embalagem
        return preco, lucro
    elif mkt == "tiktok":
        # Por faixa de preço (igual ao Shopee acima): abaixo de R$50 é 16%+R$4,
        # a partir de R$50 (inclusive) é 12%+R$6. Testa a faixa baixa primeiro;
        # se o preço calculado estourar pra R$50 ou mais, recalcula com a faixa
        # de cima — sem isso um produto na fronteira podia ficar com a taxa da
        # faixa errada pro preço final sugerido.
        def testar_faixa_tiktok(comis, taxa):
            div = 1 - (comis + imposto_tax + margem_alvo)
            return (custo_aquisicao + custo_embalagem + taxa) / div if div > 0 else 0
        preco = testar_faixa_tiktok(0.16, 4.0)
        if preco >= 50.0:
            preco = testar_faixa_tiktok(0.12, 6.0)
        comissao_mkt, taxa_fixa = (0.12, 6.0) if preco >= 50.0 else (0.16, 4.0)
        lucro = preco - (preco * comissao_mkt) - (preco * imposto_tax) - custo_aquisicao - custo_embalagem - taxa_fixa
        return preco, lucro
    elif mkt == "dlun":
        # D.Lun é loja própria (site fora deste sistema) — sem comissão de
        # marketplace nem taxa fixa em R$. No lugar da comissão entram: 5%
        # de comissão do Junior + 5% de taxa de pagamento flat (atualizado
        # — antes era 3,89% específico do PicPay, agora 5% sem amarrar a
        # nenhum gateway). Frete fica de fora da conta, igual já é padrão
        # pros outros 4 canais (calculado à parte, por pedido). Os 6% de
        # imposto ainda não foram confirmados com o contador pro regime
        # fiscal real da D.Lun — é a mesma constante usada pros outros
        # canais por ora, ajustar depois se precisar.
        comissao_dlun = 0.05 + 0.05  # comissão Junior + taxa de pagamento
        divisor = 1 - (comissao_dlun + imposto_tax + margem_alvo)
        preco = (custo_aquisicao + custo_embalagem) / divisor if divisor > 0 else 0
        lucro = preco - (preco * comissao_dlun) - (preco * imposto_tax) - custo_aquisicao - custo_embalagem
        return preco, lucro
    return 0, 0


def calcular_lucro_realizado(preco_venda, custo_aquisicao, mkt):
    """Calcula o lucro líquido de uma venda JÁ REALIZADA, a partir do preço de
    venda de verdade — diferente de calcular_venda_completo (que resolve pra um
    preço-alvo dada uma margem desejada), aqui o preço já é conhecido (veio de um
    pedido de verdade, ex: importado do Upseller) e só precisamos descontar as
    mesmas taxas/comissões de cada plataforma. Retorna o lucro em R$.

    Sem custo de embalagem aqui (diferente de calcular_venda_completo, que
    ainda usa R$1 de embalagem pra SUGERIR preço) — conferido linha a linha
    contra uma tabela calculada à mão pelo usuário em 21/07/2026 pro dia
    17/07: a diferença era exatamente R$1,00 a menos em toda venda, e a
    referência manual não descontava embalagem."""
    imposto_tax = 0.06
    mkt = (mkt or "").lower()
    if mkt == "shein":
        comissao, taxa_fixa = 0.18, 5.0
    elif mkt == "shopee":
        if preco_venda <= 79.99: comissao, taxa_fixa = 0.20, 4.0
        elif preco_venda <= 99.99: comissao, taxa_fixa = 0.14, 16.0
        elif preco_venda <= 199.99: comissao, taxa_fixa = 0.14, 20.0
        else: comissao, taxa_fixa = 0.14, 26.0
    elif mkt == "tiktok":
        if preco_venda >= 50.0: comissao, taxa_fixa = 0.12, 6.0
        else: comissao, taxa_fixa = 0.16, 4.0
    elif mkt == "dlun":
        comissao, taxa_fixa = (0.05 + 0.05), 0.0
    else:
        # Temu (e qualquer plataforma não mapeada): sem comissão própria, só imposto.
        comissao, taxa_fixa = 0.0, 0.0
    custo_aquisicao = custo_aquisicao or 0
    return preco_venda - (preco_venda * comissao) - (preco_venda * imposto_tax) - custo_aquisicao - taxa_fixa
