# -*- coding: utf-8 -*-
"""Constantes de tabela e leituras do BigQuery pra Campineira — portado de
modulo_campineira.py (CodigosPython2). Mesmas tabelas, mesmo projeto —
compartilhadas com a versão na nuvem, que roda em paralelo (decisão do
usuário nessa migração)."""
import re
from datetime import datetime
import pandas as pd
from google.cloud import bigquery

CATEGORIAS = [
    "..:NATAL:..", ".: PROMOÇÕES :.", "AUTOMOTIVOS", "BRASIL", "BRINQUEDOS E JOGOS",
    "CAPAS E GUARDA-CHUVA", "CELULARES E INFORMÁTICA", "COMEMORATIVOS E SAZONAL",
    "CONFECÇÃO", "DECORAÇÃO/ORGANIZAÇÃO", "DIDÁTICOS/EDUCATIVOS", "DIVERSOS",
    "ELETRICOS/ELETRÔNICOS", "FERRAMENTAS/FERRAGENS", "FITNESS E FISIO",
    "HIGIENE E BELEZA", "JARDIM / CAÇA E PESCA", "LINHA BEBE", "MELAMINA",
    "MOCHILAS E ACESSÓRIOS", "PAPELARIA", "PET SHOP", "UD - ART. LIMPEZA",
    "UD - COPA/COZINHA", "UD - INOX", "UD - MADEIRA", "UD - PORCELANA",
    "UD - TÉRMICOS", "UD - VIDROS", "VERÃO INFLÁVEIS E PRAIA",
]

TABLE_CAMPINEIRA = "leandro-marketplace.DL_Store_Online.tb_resultado_produtos_campineira"
TABLE_PIPELINE = "leandro-marketplace.DL_Store_Online.tb_pipeline_publicacao_campineira"
TABLE_SKU_REGISTRO = "leandro-marketplace.DL_Store_Online.tb_sku_registrados"
TABLE_HISTORICO = "leandro-marketplace.DL_Store_Online.tb_historico_produtos_campineira"
TABLE_EXCLUIDOS = "leandro-marketplace.DL_Store_Online.tb_campineira_excluidos"


def _sem_nan(valor):
    return None if pd.isna(valor) else valor


def ler_resultados(client) -> list:
    """Lê o resultado da varredura mais recente (tb_resultado_produtos_campineira,
    filtrado pelo maior id_captura)."""
    if not client:
        return []
    try:
        q = f"""
            SELECT * FROM `{TABLE_CAMPINEIRA}`
            WHERE id_captura = (SELECT MAX(id_captura) FROM `{TABLE_CAMPINEIRA}`)
            ORDER BY data_captura
        """
        df = client.query(q).to_dataframe()
        if df.empty:
            return []
        # Salvaguarda contra duplicata: se a mesma página acabou sendo raspada
        # duas vezes na mesma varredura (ex: paginação ainda não tinha
        # atualizado a tela quando o código já tentou extrair de novo), o
        # mesmo id_produto pode ter mais de uma linha aqui — mantém só a mais
        # recente (ORDER BY data_captura acima + keep="last").
        df = df.drop_duplicates(subset="id_produto", keep="last")
        produtos = []
        for _, row in df.iterrows():
            produtos.append({
                "id": _sem_nan(row.get("id_produto")),
                "nome": _sem_nan(row.get("nome")),
                "categoria": _sem_nan(row.get("categoria")),
                "estoque": _sem_nan(row.get("estoque")),
                "preco": _sem_nan(row.get("custo_campineira")),
                "ean": _sem_nan(row.get("ean")),
                "fabricante": _sem_nan(row.get("fabricante")),
                "caixa_com": _sem_nan(row.get("caixa_com")),
                "quantidade": _sem_nan(row.get("quantidade")),
                "cores": _sem_nan(row.get("cor_cores")),
                "composicao": _sem_nan(row.get("composicao")),
                "validade": _sem_nan(row.get("validade")),
                "tamanho": _sem_nan(row.get("tamanho")),
                "peso": _sem_nan(row.get("peso")),
                "tipo": _sem_nan(row.get("tipo")),
                "caixa_master": _sem_nan(row.get("caixa_master")),
                "link": _sem_nan(row.get("link")),
                "imagem": _sem_nan(row.get("imagem")),
            })
        return produtos
    except Exception:
        return []


def filtrar_resultados(dados, filtros_cat):
    from core.calculos_marketplace import calcular_precos_sugeridos
    resultado = []
    for p in dados:
        cat = p.get("categoria", "")
        cfg = filtros_cat.get(cat, {"estoque_min": 70, "preco_min": 4.99})
        est = p.get("estoque") or 0
        preco_str = p.get("preco") or "R$ 0"
        try:
            preco_num = float(preco_str.replace("R$", "").replace(".", "").replace(",", ".").strip())
        except Exception:
            preco_num = 0
        if est >= cfg["estoque_min"] and preco_num >= cfg["preco_min"]:
            sugeridos = calcular_precos_sugeridos(preco_str)
            resultado.append({**p, "preco_num": preco_num, **sugeridos})
    resultado.sort(
        key=lambda p: max((p.get(f"lucro_{m}") or 0) for m in ["shein", "shopee", "temu", "tiktok"]),
        reverse=True
    )
    return resultado


def checar_ean_duplicado_bq(client, ean):
    """Verifica se esse EAN já foi usado num SKU publicado antes — evita mandar
    pro Upseller um cadastro que vai ser recusado com 'código de barra já
    existe'. Retorna o SKU já registrado com esse EAN, ou None."""
    if not client or not ean:
        return None
    try:
        query = f"SELECT sku FROM `{TABLE_SKU_REGISTRO}` WHERE ean = @ean ORDER BY data_criacao DESC LIMIT 1"
        job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("ean", "STRING", str(ean))])
        resultado = list(client.query(query, job_config=job_config).result())
        return resultado[0]["sku"] if resultado else None
    except Exception:
        return None


TABLE_HISTORICO_STAGE = "leandro-marketplace.DL_Store_Online.tb_stage_historico_campineira"


def atualizar_historico_bq(client, produtos):
    """Registra/atualiza o histórico PERMANENTE — nunca sobrescrito, só
    atualiza estoque/preço se realmente mudou. SKU nunca é tocado aqui, só
    por marcar_sku_historico_bq(). Usa staging (WRITE_TRUNCATE) + um MERGE só,
    em vez de 1 query por produto."""
    if not client or not produtos:
        return False, "client BigQuery não conectado ou lista vazia"
    try:
        linhas = []
        for p in produtos:
            preco_str = p.get("preco") or "R$ 0"
            try:
                preco_num = float(preco_str.replace("R$", "").replace(".", "").replace(",", ".").strip())
            except Exception:
                preco_num = 0.0
            if not p.get("id"):
                continue
            linhas.append({
                "id_produto": str(p.get("id")), "categoria": p.get("categoria"), "nome": p.get("nome"),
                "estoque": int(p.get("estoque") or 0), "preco": preco_str, "preco_num": preco_num,
                "ean": p.get("ean"), "fabricante": p.get("fabricante"),
                "imagem": p.get("imagem"), "link": p.get("link"),
            })
        if not linhas:
            return False, "nenhum produto com id válido"

        df_stage = pd.DataFrame(linhas)
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        client.load_table_from_dataframe(df_stage, TABLE_HISTORICO_STAGE, job_config=job_config).result()

        merge_sql = f"""
            MERGE `{TABLE_HISTORICO}` T
            USING `{TABLE_HISTORICO_STAGE}` S
            ON T.id_produto = S.id_produto
            WHEN MATCHED AND (T.estoque != S.estoque OR T.preco_num != S.preco_num) THEN
              UPDATE SET estoque = S.estoque, preco = S.preco, preco_num = S.preco_num,
                nome = S.nome, imagem = S.imagem, data_ultima_leitura = CURRENT_TIMESTAMP(),
                data_ultima_atualizacao = CURRENT_TIMESTAMP()
            WHEN MATCHED THEN
              UPDATE SET data_ultima_leitura = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN
              INSERT (id_produto, categoria, nome, estoque, preco, preco_num, ean, fabricante, imagem, link,
                      sku_upseller, data_primeira_leitura, data_ultima_leitura, data_ultima_atualizacao)
              VALUES (S.id_produto, S.categoria, S.nome, S.estoque, S.preco, S.preco_num, S.ean, S.fabricante,
                      S.imagem, S.link, NULL, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
        """
        client.query(merge_sql).result()
        return True, None
    except Exception as e:
        return False, str(e)[:300]


def registrar_produto_bq(client, id_captura, categoria, produto, pagina=None):
    """Grava o produto capturado assim que é extraído (tb_resultado_produtos_campineira)."""
    if not client:
        return False, "client BigQuery não conectado"
    try:
        from core.calculos_marketplace import calcular_precos_sugeridos
        preco_str = produto.get("preco") or "R$ 0"
        try:
            preco_num = float(preco_str.replace("R$", "").replace(".", "").replace(",", ".").strip())
        except Exception:
            preco_num = 0.0
        sugeridos = calcular_precos_sugeridos(preco_str)
        row = {
            "id_captura": id_captura, "data_captura": datetime.utcnow().isoformat(),
            "id_produto": produto.get("id"), "categoria": categoria, "pagina": pagina,
            "nome": produto.get("nome"), "estoque": produto.get("estoque"),
            "custo_campineira": preco_str, "custo_campineira_num": preco_num,
            "preco_shein": sugeridos.get("preco_shein"), "lucro_shein": sugeridos.get("lucro_shein"),
            "preco_shopee": sugeridos.get("preco_shopee"), "lucro_shopee": sugeridos.get("lucro_shopee"),
            "preco_temu": sugeridos.get("preco_temu"), "lucro_temu": sugeridos.get("lucro_temu"),
            "preco_tiktok": sugeridos.get("preco_tiktok"), "lucro_tiktok": sugeridos.get("lucro_tiktok"),
            "ean": produto.get("ean"), "fabricante": produto.get("fabricante"),
            "caixa_com": produto.get("caixa_com"), "quantidade": produto.get("quantidade"),
            "cor_cores": produto.get("cores") or produto.get("cor"), "composicao": produto.get("composicao"),
            "validade": produto.get("validade"),
            "tamanho": produto.get("tamanho") or produto.get("tamanho_aproximado"),
            "peso": produto.get("peso") or produto.get("peso_aproximado"),
            "tipo": produto.get("tipo") or produto.get("tipo_de_produto"),
            "caixa_master": produto.get("caixa_master"), "link": produto.get("link"), "imagem": produto.get("imagem"),
        }
        erros = client.insert_rows_json(TABLE_CAMPINEIRA, [row])
        return (False, str(erros)[:300]) if erros else (True, None)
    except Exception as e:
        return False, str(e)[:300]


def registrar_sku_bq(client, sku, ean, id_produto, nome):
    if not client:
        return False, "client BigQuery não conectado"
    try:
        row = {"sku": sku, "ean": str(ean) if ean else None, "id_produto": id_produto,
               "nome": nome, "data_criacao": datetime.utcnow().isoformat()}
        erros = client.insert_rows_json(TABLE_SKU_REGISTRO, [row])
        return (False, str(erros)[:300]) if erros else (True, None)
    except Exception as e:
        return False, str(e)[:300]


def marcar_sku_historico_bq(client, id_produto, sku):
    if not client or not sku or not id_produto:
        return False, "client BigQuery não conectado, SKU ou id vazio"
    try:
        query = f"UPDATE `{TABLE_HISTORICO}` SET sku_upseller = @sku WHERE id_produto = @id_produto"
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("sku", "STRING", sku),
            bigquery.ScalarQueryParameter("id_produto", "STRING", str(id_produto)),
        ])
        client.query(query, job_config=job_config).result()
        return True, None
    except Exception as e:
        return False, str(e)[:300]


def registrar_produto_em_tb_produtos(client, sku, nome, custo):
    if not client:
        return False, "client BigQuery não conectado"
    try:
        table_id = "leandro-marketplace.DL_Store_Online.tb_produtos"
        lote = [{"marketplace": mkt, "sku": sku, "produto": nome, "custo_aquisicao": float(custo or 0)}
                for mkt in ["shein", "shopee", "temu", "tiktok"]]
        client.load_table_from_dataframe(pd.DataFrame(lote), table_id).result()
        from core.services import invalidar_cache_produtos
        invalidar_cache_produtos()
        return True, None
    except Exception as e:
        return False, str(e)[:300]


def registrar_evento_pipeline_bq(client, id_produto, sku_upseller, nome, categoria, etapa, status, mensagem):
    if not client:
        return False, "client BigQuery não conectado"
    try:
        row = {"id_produto": id_produto, "sku_upseller": sku_upseller, "nome": nome, "categoria": categoria,
               "etapa": etapa, "status": status, "mensagem": (mensagem or "")[:500],
               "data_evento": datetime.utcnow().isoformat()}
        erros = client.insert_rows_json(TABLE_PIPELINE, [row])
        return (False, str(erros)[:300]) if erros else (True, None)
    except Exception as e:
        return False, str(e)[:300]


def imagem_parece_valida(url):
    """Verifica se a URL segue o padrão real de foto de produto da Campineira
    (.../produtos/##/foto######.jpg) — ícones/selos/logos capturados por
    engano têm outro padrão de pasta e ficam de fora."""
    if not url:
        return False
    return bool(re.search(r'/produtos/\d+/foto\d+\.\w+', url, re.IGNORECASE))


def carregar_excluidos(client) -> set:
    if not client:
        return set()
    try:
        df = client.query(f"SELECT DISTINCT id_produto FROM `{TABLE_EXCLUIDOS}`").to_dataframe()
        return set(df["id_produto"].astype(str))
    except Exception:
        return set()


def salvar_excluidos(client, excluidos: set):
    """WRITE_TRUNCATE substitui a tabela inteira pelo conjunto atual — inclusive
    quando excluidos está vazio (zera a tabela), que é como 'Restaurar
    removidos' funciona."""
    if not client:
        return
    from google.cloud import bigquery
    from datetime import datetime
    linhas = [{"id_produto": str(x), "data_exclusao": datetime.utcnow().isoformat()} for x in excluidos]
    df = pd.DataFrame(linhas, columns=["id_produto", "data_exclusao"])
    try:
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        client.load_table_from_dataframe(df, TABLE_EXCLUIDOS, job_config=job_config).result()
    except Exception:
        pass


TABLE_LOCK_PUBLICACAO = "leandro-marketplace.DL_Store_Online.tb_publish_lock"
LOCK_TIMEOUT_SEGUNDOS = 120  # trava "emperrada" (processo caiu no meio) libera sozinha depois disso


def adquirir_trava_publicacao(client, titular):
    """Trava de melhor esforço (BigQuery não tem lock de linha de verdade) pra
    evitar as duas instâncias (nuvem + local, rodando em paralelo) gerarem o
    mesmo próximo SKU ao mesmo tempo — foi exatamente o bug corrigido hoje
    mais cedo (RJ-00027 a RJ-00031), só que lá a causa era diferente (um
    falso-negativo de erro); aqui a causa seria duas instâncias publicando ao
    mesmo tempo. Não é 100% infalível (não existe compare-and-swap atômico no
    BigQuery), mas reduz bastante a janela de colisão. Retorna True se
    conseguiu a trava."""
    if not client:
        return True  # sem BigQuery, não tem como coordenar — deixa passar
    from datetime import datetime, timedelta
    try:
        df = client.query(f"SELECT titular, adquirido_em FROM `{TABLE_LOCK_PUBLICACAO}` WHERE id = 'lock'").to_dataframe()
        if not df.empty:
            adquirido_em = df.iloc[0]["adquirido_em"]
            if adquirido_em and (datetime.utcnow().replace(tzinfo=adquirido_em.tzinfo) - adquirido_em) < timedelta(seconds=LOCK_TIMEOUT_SEGUNDOS):
                return False  # alguém segurando a trava de verdade agora
        client.query(f"DELETE FROM `{TABLE_LOCK_PUBLICACAO}` WHERE id = 'lock'").result()
        row = {"id": "lock", "titular": titular, "adquirido_em": datetime.utcnow().isoformat()}
        client.insert_rows_json(TABLE_LOCK_PUBLICACAO, [row])
        return True
    except Exception:
        return True  # tabela pode nem existir ainda — não bloqueia o fluxo por causa disso


def liberar_trava_publicacao(client, titular):
    if not client:
        return
    try:
        job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("titular", "STRING", titular)])
        client.query(f"DELETE FROM `{TABLE_LOCK_PUBLICACAO}` WHERE id = 'lock' AND titular = @titular", job_config=job_config).result()
    except Exception:
        pass


def buscar_progresso_varredura(client):
    """Olha a captura mais recente em tb_resultado_produtos_campineira e monta
    um resumo de por onde ela parou — categoria por categoria, qual foi a
    última página capturada. Retorna None se não achar nenhuma captura."""
    if not client:
        return None
    try:
        q = f"""
            SELECT categoria, MAX(pagina) AS pagina_max, COUNT(*) AS produtos, MAX(data_captura) AS ultima_atividade
            FROM `{TABLE_CAMPINEIRA}`
            WHERE id_captura = (SELECT MAX(id_captura) FROM `{TABLE_CAMPINEIRA}`)
            GROUP BY categoria
        """
        df = client.query(q).to_dataframe()
        if df.empty:
            return None
        id_captura_df = client.query(f"SELECT MAX(id_captura) AS ult FROM `{TABLE_CAMPINEIRA}`").to_dataframe()
        id_captura = id_captura_df["ult"].iloc[0]
        categorias = {row["categoria"]: int(row["pagina_max"] or 1) for _, row in df.iterrows()}
        return {
            "id_captura": id_captura,
            "ultima_atividade": df["ultima_atividade"].max(),
            "categorias": categorias,
            "total_produtos": int(df["produtos"].sum()),
        }
    except Exception:
        return None


def ids_com_sku_no_historico(client) -> set:
    if not client:
        return set()
    try:
        df = client.query(
            f"SELECT id_produto FROM `{TABLE_HISTORICO}` WHERE sku_upseller IS NOT NULL"
        ).to_dataframe()
        return set(df["id_produto"].astype(str))
    except Exception:
        return set()
