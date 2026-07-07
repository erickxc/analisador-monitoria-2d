"""
Motor de análise do funil de vendas B2B.

Sem dependência de GUI - pode ser testado isoladamente via linha de comando
ou testes automatizados. Todas as funções recebem/retornam DataFrames do pandas.
"""

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Constantes de domínio
# ---------------------------------------------------------------------------

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

COLUNAS_OBRIGATORIAS = [
    "Loja", "NOME_FABRICANTE", "Cliente", "descricao", "Ano", "Mês",
    "Código Interno", "Código de referêcia", "Receita Acumulada 11 Meses", "QTD",
]

GRANULARIDADES = ["Mensal", "Trimestral", "Semestral", "Anual"]

DESCRICAO_NAO_HARMONIZADA = "Não harmonizados"


class ErroCarregamentoCSV(Exception):
    """Erro amigável para falhas ao carregar/validar o CSV de vendas."""
    pass


# ---------------------------------------------------------------------------
# Carregamento e limpeza
# ---------------------------------------------------------------------------

def carregar_csv(caminho_arquivo):
    """
    Carrega o CSV de vendas, valida colunas obrigatórias, trata nulos,
    converte a receita (formato BR com vírgula) e constrói a coluna Data_Venda.

    Retorna um DataFrame limpo e pronto para análise.
    """
    try:
        df = pd.read_csv(caminho_arquivo, sep=";", encoding="utf-8-sig")
    except Exception as exc:
        raise ErroCarregamentoCSV(f"Não foi possível ler o arquivo CSV: {exc}") from exc

    colunas_faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if colunas_faltando:
        raise ErroCarregamentoCSV(
            "O CSV não tem as colunas esperadas. Faltando: "
            + ", ".join(colunas_faltando)
        )

    # Descarta linhas completamente vazias (comuns em CSVs exportados com uma
    # linha em branco no final, ex: ";;;;;;;;;"), que virariam "Mês" == NaN.
    df = df.dropna(how="all")

    df = df.copy()

    # Tratamento de nulos em texto. Produtos sem descrição ficam agrupados sob
    # um rótulo próprio ("Não harmonizados") para que o usuário decida, na
    # interface, se quer considerá-los na análise ou não.
    df["NOME_FABRICANTE"] = df["NOME_FABRICANTE"].fillna("Não informado")
    df["descricao"] = df["descricao"].fillna(DESCRICAO_NAO_HARMONIZADA)
    df["Código de referêcia"] = df["Código de referêcia"].fillna("")

    # Conversão da receita: formato BR com vírgula decimal.
    # CRÍTICO: usar .str.replace(',', '.') antes de to_numeric, senão
    # valores com centavos (ex: "33,65") viram 0 silenciosamente.
    receita_texto = df["Receita Acumulada 11 Meses"].astype(str).str.strip()
    receita_texto = receita_texto.str.replace(".", "", regex=False)  # milhar, se houver
    receita_texto = receita_texto.str.replace(",", ".", regex=False)
    df["Receita"] = pd.to_numeric(receita_texto, errors="coerce").fillna(0.0)

    df["QTD"] = pd.to_numeric(df["QTD"], errors="coerce").fillna(0).astype(int)

    # Construção da Data_Venda a partir de Ano + Mês (nome por extenso em PT-BR)
    mes_normalizado = (
        df["Mês"].astype(str).str.strip().str.lower()
        .str.replace("é", "e").str.replace("ê", "e")
    )
    df["_mes_num"] = mes_normalizado.map(MESES_PT)
    if df["_mes_num"].isnull().any():
        meses_invalidos = df.loc[df["_mes_num"].isnull(), "Mês"].unique()
        raise ErroCarregamentoCSV(
            "Valores de mês não reconhecidos: " + ", ".join(map(str, meses_invalidos))
        )

    df["Data_Venda"] = pd.to_datetime(
        dict(year=df["Ano"].astype(int), month=df["_mes_num"].astype(int), day=1)
    )
    df.drop(columns=["_mes_num"], inplace=True)

    # Campos de período (calculados) para todas as granularidades
    df["Periodo_Mensal"] = df["Data_Venda"].dt.to_period("M").astype(str)
    df["Periodo_Trimestral"] = (
        df["Data_Venda"].dt.year.astype(str) + "-T" + df["Data_Venda"].dt.quarter.astype(str)
    )
    semestre = np.where(df["Data_Venda"].dt.month <= 6, 1, 2)
    df["Periodo_Semestral"] = df["Data_Venda"].dt.year.astype(str) + "-S" + semestre.astype(str)
    df["Periodo_Anual"] = df["Data_Venda"].dt.year.astype(str)

    return df


def contar_produtos_nao_harmonizados(df):
    """Quantidade de linhas cujo produto não tinha descrição no CSV original."""
    return int((df["descricao"] == DESCRICAO_NAO_HARMONIZADA).sum())


COLUNA_PERIODO = {
    "Mensal": "Periodo_Mensal",
    "Trimestral": "Periodo_Trimestral",
    "Semestral": "Periodo_Semestral",
    "Anual": "Periodo_Anual",
}


def _ordenar_periodos(periodos, granularidade):
    """Ordena rótulos de período (strings) na ordem cronológica correta."""
    def chave(p):
        if granularidade == "Mensal":
            return p  # "YYYY-MM" já ordena lexicograficamente
        if granularidade == "Trimestral":
            ano, tri = p.split("-T")
            return (int(ano), int(tri))
        if granularidade == "Semestral":
            ano, sem = p.split("-S")
            return (int(ano), int(sem))
        return (int(p),)  # Anual
    return sorted(periodos, key=chave)


# ---------------------------------------------------------------------------
# Top produtos e top clientes
# ---------------------------------------------------------------------------

def top_produtos(df, n=20):
    resultado = (
        df.groupby("descricao", as_index=False)
        .agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
        .sort_values("Receita", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
    return resultado


def top_clientes(df, n=20):
    resultado = (
        df.groupby("Cliente", as_index=False)
        .agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
        .sort_values("Receita", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
    return resultado


def top_fabricantes(df, n=20):
    resultado = (
        df.groupby("NOME_FABRICANTE", as_index=False)
        .agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
        .sort_values("Receita", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
    return resultado


def poder_compra_clientes(abc_clientes_df):
    """
    Recorte do "Poder de Compra por Cliente": para cada cliente/período, a
    receita, a faixa de representatividade, a frequência de compra e a
    renúncia (poder de compra abandonado) — já calculados em classificar_abc.
    Só reorganiza/renomeia colunas para leitura direta em um relatório.
    """
    if abc_clientes_df.empty:
        return abc_clientes_df.copy()
    colunas = ["Cliente", "Periodo", "Receita", "Percentual_Acumulado", "Faixa_ABC",
               "Frequencia_Simples", "Frequencia_Acumulada",
               "Renuncia", "Renuncia_Acumulada", "Renuncia_Percentual"]
    return abc_clientes_df[colunas].rename(columns={"Faixa_ABC": "Faixa_Representatividade"})


# ---------------------------------------------------------------------------
# Tendência de produtos
# ---------------------------------------------------------------------------

def tendencia_produtos(df, granularidade="Mensal", periodos_queda_consecutiva=2):
    """
    Evolução de receita/quantidade por produto ao longo dos períodos.
    Sinaliza produtos com queda em N períodos consecutivos (parametrizável).

    Retorna (evolucao_df, alertas_df):
      - evolucao_df: uma linha por (produto, período) com receita, qtd e variação %.
      - alertas_df: uma linha por produto sinalizado em queda consistente.
    """
    col_periodo = COLUNA_PERIODO[granularidade]
    periodos_ordenados = _ordenar_periodos(df[col_periodo].unique(), granularidade)

    evolucao = (
        df.groupby(["descricao", col_periodo], as_index=False)
        .agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
        .rename(columns={col_periodo: "Periodo"})
    )
    ordem_periodo = {p: i for i, p in enumerate(periodos_ordenados)}
    evolucao["_ordem"] = evolucao["Periodo"].map(ordem_periodo)
    evolucao.sort_values(["descricao", "_ordem"], inplace=True)

    evolucao["Receita_Periodo_Anterior"] = evolucao.groupby("descricao")["Receita"].shift(1)
    evolucao["Variacao_Percentual"] = np.where(
        (evolucao["Receita_Periodo_Anterior"].notnull()) & (evolucao["Receita_Periodo_Anterior"] != 0),
        (evolucao["Receita"] - evolucao["Receita_Periodo_Anterior"]) / evolucao["Receita_Periodo_Anterior"] * 100,
        np.nan,
    )
    evolucao.drop(columns=["_ordem"], inplace=True)
    evolucao.reset_index(drop=True, inplace=True)

    # Detecta queda em N períodos consecutivos por produto
    alertas = []
    for produto, grupo in evolucao.groupby("descricao"):
        grupo = grupo.sort_values("Periodo", key=lambda s: s.map(ordem_periodo))
        quedas_seguidas = 0
        maior_sequencia = 0
        for variacao in grupo["Variacao_Percentual"]:
            if pd.notnull(variacao) and variacao < 0:
                quedas_seguidas += 1
                maior_sequencia = max(maior_sequencia, quedas_seguidas)
            else:
                quedas_seguidas = 0
        if maior_sequencia >= periodos_queda_consecutiva:
            alertas.append({
                "descricao": produto,
                "Periodos_Consecutivos_Em_Queda": maior_sequencia,
                "Receita_Ultimo_Periodo": grupo["Receita"].iloc[-1],
                "Receita_Primeiro_Periodo": grupo["Receita"].iloc[0],
            })

    alertas_df = pd.DataFrame(alertas)
    if not alertas_df.empty:
        alertas_df.sort_values("Periodos_Consecutivos_Em_Queda", ascending=False, inplace=True)
        alertas_df.reset_index(drop=True, inplace=True)

    return evolucao, alertas_df


def produtos_alta_e_queda(df, granularidade="Mensal", top_n=10):
    """
    Compara os dois períodos mais recentes da granularidade escolhida e monta
    duas listas (estilo "boletim executivo"): produtos em alta e em queda,
    com quantidade período anterior/atual, variação % e total acumulado no
    ano corrente (YTD).
    """
    col_periodo = COLUNA_PERIODO[granularidade]
    periodos_ordenados = _ordenar_periodos(df[col_periodo].unique(), granularidade)
    colunas_vazias = ["descricao", "QTD_Periodo_Anterior", "QTD_Periodo_Atual",
                       "Receita_Periodo_Anterior", "Receita_Periodo_Atual",
                       "Variacao_Percentual", "Total_Ano_Atual"]
    if len(periodos_ordenados) < 2:
        vazio = pd.DataFrame(columns=colunas_vazias)
        return vazio, vazio.copy()

    periodo_anterior, periodo_atual = periodos_ordenados[-2], periodos_ordenados[-1]

    agrupado = (
        df[df[col_periodo].isin([periodo_anterior, periodo_atual])]
        .groupby(["descricao", col_periodo], as_index=False)
        .agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
    )
    pivot_receita = agrupado.pivot(index="descricao", columns=col_periodo, values="Receita").fillna(0)
    pivot_qtd = agrupado.pivot(index="descricao", columns=col_periodo, values="QTD").fillna(0)

    ano_referencia = df.loc[df[col_periodo] == periodo_atual, "Data_Venda"].dt.year.max()
    total_ano = (
        df[df["Data_Venda"].dt.year == ano_referencia]
        .groupby("descricao")["Receita"].sum()
    )

    resultado = pd.DataFrame({
        "descricao": pivot_receita.index,
        "QTD_Periodo_Anterior": pivot_qtd.get(periodo_anterior, 0).values,
        "QTD_Periodo_Atual": pivot_qtd.get(periodo_atual, 0).values,
        "Receita_Periodo_Anterior": pivot_receita.get(periodo_anterior, 0).values,
        "Receita_Periodo_Atual": pivot_receita.get(periodo_atual, 0).values,
    })
    resultado["Variacao_Percentual"] = np.where(
        resultado["Receita_Periodo_Anterior"] > 0,
        (resultado["Receita_Periodo_Atual"] - resultado["Receita_Periodo_Anterior"])
        / resultado["Receita_Periodo_Anterior"] * 100,
        np.nan,
    )
    resultado["Total_Ano_Atual"] = resultado["descricao"].map(total_ano).fillna(0)

    em_alta = (
        resultado[resultado["Variacao_Percentual"] > 0]
        .sort_values("Variacao_Percentual", ascending=False)
        .head(top_n).reset_index(drop=True)
    )
    em_queda = (
        resultado[resultado["Variacao_Percentual"] < 0]
        .sort_values("Variacao_Percentual", ascending=True)
        .head(top_n).reset_index(drop=True)
    )
    return em_alta, em_queda


# ---------------------------------------------------------------------------
# Erosão de clientes por produto
# ---------------------------------------------------------------------------

def erosao_clientes_por_produto(df, granularidade="Mensal", produtos_alvo=None):
    """
    Para cada produto (ou apenas os informados em produtos_alvo), compara a
    receita/qtd de cada cliente entre períodos consecutivos e lista quem
    reduziu ou parou de comprar aquele produto.
    """
    col_periodo = COLUNA_PERIODO[granularidade]
    periodos_ordenados = _ordenar_periodos(df[col_periodo].unique(), granularidade)
    ordem_periodo = {p: i for i, p in enumerate(periodos_ordenados)}

    base = df
    if produtos_alvo:
        base = base[base["descricao"].isin(produtos_alvo)]

    agrupado = (
        base.groupby(["descricao", "Cliente", col_periodo], as_index=False)
        .agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
        .rename(columns={col_periodo: "Periodo"})
    )
    agrupado["_ordem"] = agrupado["Periodo"].map(ordem_periodo)
    agrupado.sort_values(["descricao", "Cliente", "_ordem"], inplace=True)

    agrupado["Receita_Periodo_Anterior"] = agrupado.groupby(["descricao", "Cliente"])["Receita"].shift(1)
    agrupado["QTD_Periodo_Anterior"] = agrupado.groupby(["descricao", "Cliente"])["QTD"].shift(1)

    erosao = agrupado[
        agrupado["Receita_Periodo_Anterior"].notnull()
        & (agrupado["Receita"] < agrupado["Receita_Periodo_Anterior"])
    ].copy()

    erosao["Reducao_Receita"] = erosao["Receita_Periodo_Anterior"] - erosao["Receita"]
    erosao["Reducao_Percentual"] = np.where(
        erosao["Receita_Periodo_Anterior"] != 0,
        erosao["Reducao_Receita"] / erosao["Receita_Periodo_Anterior"] * 100,
        np.nan,
    )
    erosao["Parou_De_Comprar"] = erosao["Receita"] == 0

    erosao.drop(columns=["_ordem"], inplace=True)
    erosao.sort_values("Reducao_Receita", ascending=False, inplace=True)
    erosao.reset_index(drop=True, inplace=True)

    return erosao


def clientes_queda_quantidade(df, granularidade="Mensal", top_n=10):
    """
    Compara os dois períodos mais recentes: para cada cliente, quantidade
    anterior/atual, variação %, perda financeira (receita atual - anterior,
    negativa) e o "produto crítico" (produto que mais contribuiu para a queda
    de quantidade daquele cliente na transição).
    """
    col_periodo = COLUNA_PERIODO[granularidade]
    periodos_ordenados = _ordenar_periodos(df[col_periodo].unique(), granularidade)
    if len(periodos_ordenados) < 2:
        return pd.DataFrame(columns=[
            "Cliente", "QTD_Periodo_Anterior", "QTD_Periodo_Atual", "Variacao_Percentual",
            "Perda_Receita", "Produto_Critico",
        ])

    periodo_anterior, periodo_atual = periodos_ordenados[-2], periodos_ordenados[-1]
    base = df[df[col_periodo].isin([periodo_anterior, periodo_atual])]

    por_cliente = (
        base.groupby(["Cliente", col_periodo], as_index=False)
        .agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
    )
    pivot_qtd = por_cliente.pivot(index="Cliente", columns=col_periodo, values="QTD").fillna(0)
    pivot_receita = por_cliente.pivot(index="Cliente", columns=col_periodo, values="Receita").fillna(0)

    resultado = pd.DataFrame({
        "Cliente": pivot_qtd.index,
        "QTD_Periodo_Anterior": pivot_qtd.get(periodo_anterior, 0).values,
        "QTD_Periodo_Atual": pivot_qtd.get(periodo_atual, 0).values,
    })
    resultado["Variacao_Percentual"] = np.where(
        resultado["QTD_Periodo_Anterior"] > 0,
        (resultado["QTD_Periodo_Atual"] - resultado["QTD_Periodo_Anterior"])
        / resultado["QTD_Periodo_Anterior"] * 100,
        np.nan,
    )
    resultado["Perda_Receita"] = (
        pivot_receita.get(periodo_atual, 0).values - pivot_receita.get(periodo_anterior, 0).values
    )

    por_produto = (
        base.groupby(["Cliente", "descricao", col_periodo], as_index=False)["QTD"].sum()
        .pivot_table(index=["Cliente", "descricao"], columns=col_periodo, values="QTD", fill_value=0)
    )
    if periodo_anterior in por_produto.columns and periodo_atual in por_produto.columns:
        por_produto["Queda_QTD"] = por_produto[periodo_anterior] - por_produto[periodo_atual]
        produto_critico = (
            por_produto.reset_index().sort_values("Queda_QTD", ascending=False)
            .groupby("Cliente").first()["descricao"]
        )
        resultado["Produto_Critico"] = resultado["Cliente"].map(produto_critico).fillna("-")
    else:
        resultado["Produto_Critico"] = "-"

    resultado = resultado[resultado["Variacao_Percentual"] < 0]
    resultado.sort_values("Variacao_Percentual", ascending=True, inplace=True)
    resultado = resultado.head(top_n).reset_index(drop=True)
    return resultado


def correlacao_produto_cliente(df, erosao_df, alertas_queda_df, granularidade="Mensal", top_n=15):
    """
    Classifica os principais eventos de erosão (cliente que reduziu compra de
    um produto) com um status heurístico e transparente, no estilo de um
    relatório executivo:

      - "Abandono de Categoria": vários clientes abandonaram o mesmo produto
        no mesmo período (queda sistêmica, não isolada).
      - "Ruptura Estratégica": o cliente parou de comprar um produto que
        respondia por boa parte do que ele comprava daquele produto.
      - "Fim de Ciclo": o produto já está listado entre os alertas de queda
        consecutiva (tendência estrutural, não pontual).
      - "Caso Específico": nenhum dos padrões acima foi identificado.
    """
    if erosao_df.empty:
        return pd.DataFrame(columns=["Cliente", "descricao", "Periodo", "Reducao_Percentual", "Status"])

    top_eventos = erosao_df.head(top_n).copy()

    contagem_clientes_por_produto_periodo = (
        erosao_df.groupby(["descricao", "Periodo"])["Cliente"].nunique()
    )
    produtos_em_alerta = set(alertas_queda_df["descricao"]) if not alertas_queda_df.empty else set()

    def classificar(linha):
        chave = (linha["descricao"], linha["Periodo"])
        clientes_afetados = contagem_clientes_por_produto_periodo.get(chave, 1)
        if clientes_afetados >= 3:
            return "Abandono de Categoria"
        if linha["descricao"] in produtos_em_alerta:
            return "Fim de Ciclo"
        if linha["Parou_De_Comprar"] and linha["Reducao_Percentual"] >= 70:
            return "Ruptura Estratégica"
        return "Caso Específico"

    top_eventos["Status"] = top_eventos.apply(classificar, axis=1)
    colunas = ["Cliente", "descricao", "Periodo", "Reducao_Receita", "Reducao_Percentual",
               "Parou_De_Comprar", "Status"]
    return top_eventos[colunas].reset_index(drop=True)


def impacto_financeiro_churn(df, erosao_df, granularidade="Mensal"):
    """
    KPIs resumidos de impacto financeiro da erosão/churn: maior retração
    individual (%), receita total sob risco (soma das reduções observadas) e
    a variação global de receita entre os dois últimos períodos.
    """
    col_periodo = COLUNA_PERIODO[granularidade]
    periodos_ordenados = _ordenar_periodos(df[col_periodo].unique(), granularidade)

    maior_retracao_percentual = (
        erosao_df["Reducao_Percentual"].max() if not erosao_df.empty else 0.0
    )
    receita_sob_risco = erosao_df["Reducao_Receita"].sum() if not erosao_df.empty else 0.0

    variacao_global = None
    if len(periodos_ordenados) >= 2:
        receita_anterior = df.loc[df[col_periodo] == periodos_ordenados[-2], "Receita"].sum()
        receita_atual = df.loc[df[col_periodo] == periodos_ordenados[-1], "Receita"].sum()
        if receita_anterior > 0:
            variacao_global = (receita_atual - receita_anterior) / receita_anterior * 100

    return pd.DataFrame([{
        "Maior_Retracao_Individual_Pct": maior_retracao_percentual,
        "Receita_Sob_Risco": receita_sob_risco,
        "Variacao_Global_Periodo_Pct": variacao_global,
    }])


# ---------------------------------------------------------------------------
# Frequência e Renúncia (poder de compra)
# ---------------------------------------------------------------------------

def calcular_frequencia(df, granularidade="Mensal", campo="Cliente"):
    """
    Frequência de compra por (campo, período):
      - Frequencia_Simples: nº de meses-calendário distintos com receita > 0
        dentro daquele período (para Mensal, é 0 ou 1).
      - Frequencia_Acumulada: soma cumulativa da Frequencia_Simples ao longo
        dos períodos, na ordem cronológica, por entidade (cliente/produto).
    """
    col_periodo = COLUNA_PERIODO[granularidade]
    periodos_ordenados = _ordenar_periodos(df[col_periodo].unique(), granularidade)
    ordem_periodo = {p: i for i, p in enumerate(periodos_ordenados)}

    vendas_positivas = df[df["Receita"] > 0]
    contagem_meses = (
        vendas_positivas.groupby([campo, col_periodo])["Periodo_Mensal"]
        .nunique().rename("Frequencia_Simples")
    )
    frequencia = contagem_meses.reset_index().rename(columns={col_periodo: "Periodo"})
    frequencia["_ordem"] = frequencia["Periodo"].map(ordem_periodo)
    frequencia.sort_values([campo, "_ordem"], inplace=True)
    frequencia["Frequencia_Acumulada"] = frequencia.groupby(campo)["Frequencia_Simples"].cumsum()
    frequencia.drop(columns=["_ordem"], inplace=True)
    frequencia.reset_index(drop=True, inplace=True)
    return frequencia


def calcular_renuncia(df, granularidade="Mensal", campo="Cliente"):
    """
    "Renúncia" mede o poder de compra que a entidade (cliente, tipicamente)
    abriu mão: soma das quedas de receita entre períodos consecutivos
    (aumentos não compensam quedas anteriores - é o total de receita
    efetivamente "deixado na mesa" ao longo do tempo).

      - Renuncia: valor da queda no período (0 se não houve queda).
      - Renuncia_Acumulada: soma cumulativa da renúncia por entidade.
      - Renuncia_Percentual: a queda do período como % da receita do período
        anterior.
    """
    col_periodo = COLUNA_PERIODO[granularidade]
    periodos_ordenados = _ordenar_periodos(df[col_periodo].unique(), granularidade)
    ordem_periodo = {p: i for i, p in enumerate(periodos_ordenados)}

    agrupado = (
        df.groupby([campo, col_periodo], as_index=False)["Receita"].sum()
        .rename(columns={col_periodo: "Periodo"})
    )
    agrupado["_ordem"] = agrupado["Periodo"].map(ordem_periodo)
    agrupado.sort_values([campo, "_ordem"], inplace=True)

    agrupado["Receita_Anterior"] = agrupado.groupby(campo)["Receita"].shift(1)
    agrupado["Renuncia"] = (agrupado["Receita_Anterior"] - agrupado["Receita"]).clip(lower=0).fillna(0)
    agrupado["Renuncia_Percentual"] = np.where(
        (agrupado["Receita_Anterior"].notnull()) & (agrupado["Receita_Anterior"] > 0),
        agrupado["Renuncia"] / agrupado["Receita_Anterior"] * 100,
        0.0,
    )
    agrupado["Renuncia_Acumulada"] = agrupado.groupby(campo)["Renuncia"].cumsum()

    agrupado.drop(columns=["_ordem", "Receita_Anterior"], inplace=True)
    agrupado.reset_index(drop=True, inplace=True)
    return agrupado


# ---------------------------------------------------------------------------
# Classificação em faixas por representatividade no faturamento (genérica)
# ---------------------------------------------------------------------------

def classificar_faixas(df, granularidade="Mensal", campo="Cliente", excluidos=None,
                        cortes=(30.0, 50.0, 60.0), nomes_grupos=None):
    """
    Classifica entidades (clientes ou produtos) em faixas por representatividade
    acumulada no faturamento, período a período.

    cortes: percentuais cumulativos crescentes (ex.: (30, 50, 60)). A última
    faixa (nome "Demais") recebe tudo que ultrapassar o último corte.
    excluidos: valores da entidade a remover do cálculo (ex.: clientes fora
    da análise). O faturamento de referência é recalculado sem eles.

    Retorna um DataFrame com: campo, Receita, Percentual_Acumulado, Periodo,
    Faixa, Frequencia_Simples, Frequencia_Acumulada, Renuncia,
    Renuncia_Acumulada, Renuncia_Percentual.
    """
    excluidos = set(excluidos or [])
    cortes = list(cortes)
    nomes_grupos = list(nomes_grupos) if nomes_grupos else [f"Grupo {i + 1}" for i in range(len(cortes))]
    nomes_grupos = nomes_grupos + ["Demais"]

    col_periodo = COLUNA_PERIODO[granularidade]
    base = df[~df[campo].isin(excluidos)] if excluidos else df

    resultados = []
    for periodo, grupo in base.groupby(col_periodo):
        receita_entidade = (
            grupo.groupby(campo, as_index=False)["Receita"].sum()
            .sort_values("Receita", ascending=False)
            .reset_index(drop=True)
        )
        receita_total = receita_entidade["Receita"].sum()
        if receita_total <= 0:
            receita_entidade["Percentual_Acumulado"] = 0.0
        else:
            receita_entidade["Percentual_Acumulado"] = (
                receita_entidade["Receita"].cumsum() / receita_total * 100
            )
        receita_entidade["Periodo"] = periodo

        def faixa(percentual_acumulado):
            for corte, nome in zip(cortes, nomes_grupos):
                if percentual_acumulado <= corte:
                    return nome
            return nomes_grupos[-1]

        receita_entidade["Faixa_ABC"] = receita_entidade["Percentual_Acumulado"].apply(faixa)
        resultados.append(receita_entidade)

    colunas_base = [campo, "Receita", "Percentual_Acumulado", "Periodo", "Faixa_ABC"]
    if not resultados:
        classificado = pd.DataFrame(columns=colunas_base)
    else:
        classificado = pd.concat(resultados, ignore_index=True)

    frequencia = calcular_frequencia(base, granularidade, campo)
    renuncia = calcular_renuncia(base, granularidade, campo)

    classificado = classificado.merge(frequencia, on=[campo, "Periodo"], how="left")
    classificado = classificado.merge(
        renuncia[[campo, "Periodo", "Renuncia", "Renuncia_Acumulada", "Renuncia_Percentual"]],
        on=[campo, "Periodo"], how="left",
    )
    classificado[["Frequencia_Simples", "Frequencia_Acumulada", "Renuncia",
                  "Renuncia_Acumulada", "Renuncia_Percentual"]] = classificado[[
        "Frequencia_Simples", "Frequencia_Acumulada", "Renuncia",
        "Renuncia_Acumulada", "Renuncia_Percentual",
    ]].fillna(0)

    periodos_ordenados = _ordenar_periodos(classificado["Periodo"].unique(), granularidade)
    ordem_periodo = {p: i for i, p in enumerate(periodos_ordenados)}
    classificado["_ordem"] = classificado["Periodo"].map(ordem_periodo)
    classificado.sort_values(["_ordem", "Receita"], ascending=[True, False], inplace=True)
    classificado.drop(columns=["_ordem"], inplace=True)
    classificado.reset_index(drop=True, inplace=True)
    return classificado


def classificar_abc(df, granularidade="Mensal", clientes_excluidos=None, cortes_clientes=(30.0, 50.0, 60.0)):
    """Classificação de clientes por representatividade no faturamento (ver classificar_faixas)."""
    return classificar_faixas(df, granularidade, campo="Cliente", excluidos=clientes_excluidos, cortes=cortes_clientes)


def classificar_produtos_por_receita(df, granularidade="Mensal", corte_percentual=80.0):
    """
    Classificação de produtos por representatividade no faturamento: faixa
    "Grupo 1" concentra o corte_percentual (padrão 80%) inicial de receita
    acumulada; o restante cai em "Demais" (cauda longa).
    """
    return classificar_faixas(df, granularidade, campo="descricao", excluidos=None,
                               cortes=(corte_percentual,), nomes_grupos=["Grupo 1"])


def classificar_clientes_agregado(df, clientes_excluidos=None, cortes=(30.0, 50.0, 60.0)):
    """
    Classificação RÁPIDA (não por período) de cada cliente em um grupo, usando
    a receita agregada de todo o CSV como referência — pensada para a prévia
    na interface (a classificação "oficial" do relatório, por período, é
    feita por classificar_faixas/classificar_abc).

    Retorna DataFrame: Cliente, Receita, Percentual_Acumulado, Faixa, Frequencia
    (Frequencia = nº de meses distintos em que o cliente comprou algo).
    """
    excluidos = set(clientes_excluidos or [])
    base = df[~df["Cliente"].isin(excluidos)] if excluidos else df

    receita_cliente = base.groupby("Cliente")["Receita"].sum().sort_values(ascending=False)
    resultado = receita_cliente.reset_index()
    resultado.columns = ["Cliente", "Receita"]
    total = resultado["Receita"].sum()
    resultado["Percentual_Acumulado"] = (resultado["Receita"].cumsum() / total * 100) if total > 0 else 0.0

    nomes_grupos = [f"Grupo {i + 1}" for i in range(len(cortes))] + ["Demais"]

    def faixa(percentual_acumulado):
        for corte, nome in zip(cortes, nomes_grupos):
            if percentual_acumulado <= corte:
                return nome
        return nomes_grupos[-1]

    resultado["Faixa"] = resultado["Percentual_Acumulado"].apply(faixa)

    frequencia = (
        base[base["Receita"] > 0].groupby("Cliente")["Periodo_Mensal"].nunique().rename("Frequencia")
    )
    resultado = resultado.merge(frequencia, on="Cliente", how="left")
    resultado["Frequencia"] = resultado["Frequencia"].fillna(0).astype(int)
    return resultado


def classificar_produtos_agregado(df, corte_percentual=80.0):
    """
    Classificação RÁPIDA (não por período) de cada produto em "Grupo 1"
    (top corte_percentual% da receita) ou "Demais", com a frequência de
    compra (nº de meses distintos com venda). Pensada para a prévia na
    interface — ver classificar_produtos_por_receita para a versão por
    período usada no relatório final.
    """
    receita_produto = df.groupby("descricao")["Receita"].sum().sort_values(ascending=False)
    resultado = receita_produto.reset_index()
    resultado.columns = ["descricao", "Receita"]
    total = resultado["Receita"].sum()
    resultado["Percentual_Acumulado"] = (resultado["Receita"].cumsum() / total * 100) if total > 0 else 0.0
    resultado["Faixa"] = resultado["Percentual_Acumulado"].apply(lambda p: "Grupo 1" if p <= corte_percentual else "Demais")

    frequencia = (
        df[df["Receita"] > 0].groupby("descricao")["Periodo_Mensal"].nunique().rename("Frequencia")
    )
    resultado = resultado.merge(frequencia, on="descricao", how="left")
    resultado["Frequencia"] = resultado["Frequencia"].fillna(0).astype(int)
    return resultado


def contar_clientes_por_grupo(df, clientes_excluidos=None, cortes=(30.0, 50.0, 60.0)):
    """
    Conta quantos clientes caem em cada grupo para os cortes informados
    (sem ajustar automaticamente), usando a receita agregada total como
    referência. Útil para pré-visualizar o efeito dos parâmetros antes de
    rodar o relatório completo.

    Retorna uma lista de contagens com um item a mais que `cortes` (o
    último item é a contagem do grupo "Demais").
    """
    excluidos = set(clientes_excluidos or [])
    base = df[~df["Cliente"].isin(excluidos)] if excluidos else df
    receita_cliente = base.groupby("Cliente")["Receita"].sum().sort_values(ascending=False)
    total = receita_cliente.sum()

    if total <= 0 or receita_cliente.empty:
        return [0] * (len(cortes) + 1)

    percentual_acumulado = receita_cliente.cumsum() / total * 100
    contagens = []
    limite_inferior = 0.0
    for corte in cortes:
        contagens.append(int(((percentual_acumulado > limite_inferior) & (percentual_acumulado <= corte)).sum()))
        limite_inferior = corte
    contagens.append(int((percentual_acumulado > limite_inferior).sum()))
    return contagens


def sugerir_cortes_grupos(df, clientes_excluidos=None, cortes_iniciais=(30.0, 50.0, 60.0),
                           max_por_grupo=10, passo=0.5):
    """
    Ajusta (reduz) os cortes percentuais cumulativos até que cada grupo não
    ultrapasse max_por_grupo clientes, usando a receita agregada total (soma
    de todos os períodos) como referência. Não altera a ordem/quantidade de
    grupos, apenas os percentuais de corte.

    Retorna (cortes_ajustados, contagens) onde contagens tem um item a mais
    que cortes_ajustados (o último é a contagem do grupo "Demais").
    """
    excluidos = set(clientes_excluidos or [])
    base = df[~df["Cliente"].isin(excluidos)] if excluidos else df
    receita_cliente = base.groupby("Cliente")["Receita"].sum().sort_values(ascending=False)
    total = receita_cliente.sum()

    cortes = list(cortes_iniciais)
    if total <= 0 or receita_cliente.empty:
        return cortes, [0] * (len(cortes) + 1)

    percentual_acumulado = receita_cliente.cumsum() / total * 100

    limite_inferior = 0.0
    for i, corte in enumerate(cortes):
        while True:
            quantidade = int(((percentual_acumulado > limite_inferior) & (percentual_acumulado <= corte)).sum())
            if quantidade <= max_por_grupo or corte <= limite_inferior + passo:
                break
            corte -= passo
        cortes[i] = round(corte, 1)
        limite_inferior = cortes[i]

    contagens = []
    limite_inferior = 0.0
    for corte in cortes:
        contagens.append(int(((percentual_acumulado > limite_inferior) & (percentual_acumulado <= corte)).sum()))
        limite_inferior = corte
    contagens.append(int((percentual_acumulado > limite_inferior).sum()))

    return cortes, contagens


# ---------------------------------------------------------------------------
# Migração de clientes entre grupos + causa provável
# ---------------------------------------------------------------------------

def migracao_abc(df, abc_df, granularidade="Mensal"):
    """
    Compara períodos consecutivos e identifica clientes que subiram ou
    desceram de faixa, com uma causa provável heurística e transparente.
    A ordem de "importância" das faixas é inferida pela ordem de aparição
    (a primeira faixa encontrada nos dados é a mais valiosa; "Demais" é
    sempre a menos valiosa).
    """
    col_periodo = COLUNA_PERIODO[granularidade]
    periodos_ordenados = _ordenar_periodos(abc_df["Periodo"].unique(), granularidade)

    faixas_em_ordem = [f for f in abc_df["Faixa_ABC"].unique() if f != "Demais"]
    faixas_em_ordem = sorted(faixas_em_ordem, key=lambda nome: int(nome.split()[-1]) if nome.split()[-1].isdigit() else 99)
    faixas_em_ordem.append("Demais")
    ordem_faixa = {nome: (len(faixas_em_ordem) - i) for i, nome in enumerate(faixas_em_ordem)}

    contexto = _preparar_contexto_causa_provavel(df, col_periodo)

    migracoes = []

    for periodo_anterior, periodo_atual in zip(periodos_ordenados, periodos_ordenados[1:]):
        faixa_anterior = abc_df[abc_df["Periodo"] == periodo_anterior].set_index("Cliente")["Faixa_ABC"]
        faixa_atual = abc_df[abc_df["Periodo"] == periodo_atual].set_index("Cliente")["Faixa_ABC"]

        clientes_comuns = faixa_anterior.index.intersection(faixa_atual.index)
        for cliente in clientes_comuns:
            de = faixa_anterior[cliente]
            para = faixa_atual[cliente]
            if de == para:
                continue

            direcao = "Subiu" if ordem_faixa.get(para, 0) > ordem_faixa.get(de, 0) else "Desceu"
            causa = _causa_provavel_migracao(contexto, cliente, periodo_anterior, periodo_atual, direcao)

            migracoes.append({
                "Cliente": cliente,
                "Periodo_Anterior": periodo_anterior,
                "Periodo_Atual": periodo_atual,
                "Faixa_Anterior": de,
                "Faixa_Atual": para,
                "Direcao": direcao,
                "Causa_Provavel": causa,
            })

    return pd.DataFrame(migracoes)


def _preparar_contexto_causa_provavel(df, col_periodo):
    """
    Pré-calcula, uma única vez para todo o DataFrame, os agregados por
    (Cliente, Período) usados pela heurística de causa provável. Sem isso,
    _causa_provavel_migracao precisaria refiltrar o DataFrame inteiro para
    cada cliente que migrou de faixa — com milhares de clientes e dezenas de
    milhares de linhas, isso é o gargalo de performance da geração de
    relatório (a etapa mais lenta, de longe).
    """
    vendas_positivas = df[df["Receita"] > 0]
    return {
        "receita": df.groupby(["Cliente", col_periodo])["Receita"].sum().to_dict(),
        "qtd": df.groupby(["Cliente", col_periodo])["QTD"].sum().to_dict(),
        "meses": vendas_positivas.groupby(["Cliente", col_periodo])["Periodo_Mensal"].nunique().to_dict(),
        "produtos": vendas_positivas.groupby(["Cliente", col_periodo])["descricao"].apply(set).to_dict(),
        "receita_produto": vendas_positivas.groupby(["Cliente", col_periodo, "descricao"])["Receita"].sum().to_dict(),
    }


def _causa_provavel_migracao(contexto, cliente, periodo_anterior, periodo_atual, direcao):
    """
    Heurísticas simples e transparentes para explicar a migração de faixa,
    usando os agregados pré-calculados em `contexto` (ver
    _preparar_contexto_causa_provavel) em vez de refiltrar o DataFrame.
    Sempre prefixa a explicação deixando claro que é uma estimativa, não uma
    certeza.
    """
    chave_anterior = (cliente, periodo_anterior)
    chave_atual = (cliente, periodo_atual)

    receita_anterior = contexto["receita"].get(chave_anterior, 0.0)
    receita_atual = contexto["receita"].get(chave_atual, 0.0)

    prefixo = "Provável causa (heurística, não é certeza): "

    if receita_atual == 0:
        return prefixo + "cliente parou de comprar no período atual."

    # Heurística 1: queda concentrada em um produto específico abandonado
    produtos_anterior = contexto["produtos"].get(chave_anterior, set())
    produtos_atual = contexto["produtos"].get(chave_atual, set())
    produtos_abandonados = produtos_anterior - produtos_atual
    if direcao == "Desceu" and produtos_abandonados:
        receita_produtos_abandonados = sum(
            contexto["receita_produto"].get((cliente, periodo_anterior, produto), 0.0)
            for produto in produtos_abandonados
        )
        if receita_anterior > 0 and receita_produtos_abandonados / receita_anterior >= 0.4:
            principal = ", ".join(list(produtos_abandonados)[:3])
            return prefixo + f"deixou de comprar produto(s) que respondiam por parte relevante da receita ({principal})."

    # Heurística 2: redução de frequência de compra (menos meses/períodos com compra)
    meses_anterior = contexto["meses"].get(chave_anterior, 0)
    meses_atual = contexto["meses"].get(chave_atual, 0)
    if direcao == "Desceu" and meses_atual < meses_anterior:
        return prefixo + f"redução na frequência de compra ({meses_anterior} período(s) com compra antes, {meses_atual} depois)."

    # Heurística 3: redução de ticket médio mantendo os mesmos produtos
    qtd_anterior = contexto["qtd"].get(chave_anterior, 0)
    qtd_atual = contexto["qtd"].get(chave_atual, 0)
    ticket_anterior = receita_anterior / qtd_anterior if qtd_anterior else 0
    ticket_atual = receita_atual / qtd_atual if qtd_atual else 0
    if direcao == "Desceu" and ticket_anterior > 0 and ticket_atual < ticket_anterior * 0.8:
        return prefixo + "redução do ticket médio mantendo os mesmos produtos."

    if direcao == "Subiu":
        produtos_novos = produtos_atual - produtos_anterior
        if produtos_novos:
            principal = ", ".join(list(produtos_novos)[:3])
            return prefixo + f"aumento de receita associado a novo(s) produto(s) comprado(s) ({principal})."
        return prefixo + "aumento geral de receita no período, sem produto específico identificado."

    return prefixo + "variação de receita sem padrão específico identificado pelas heurísticas atuais."


# ---------------------------------------------------------------------------
# Orquestração: gera todas as análises para um conjunto de granularidades
# ---------------------------------------------------------------------------

def gerar_analises_completas(df, granularidades, clientes_excluidos=None,
                              cortes_clientes=(30.0, 50.0, 60.0), corte_produtos=80.0,
                              periodos_queda_consecutiva=2, callback_log=None, chaves_solicitadas=None):
    """
    Roda as análises solicitadas para cada granularidade escolhida.

    chaves_solicitadas: conjunto/lista de chaves do catálogo a calcular (ex.:
    {"top_clientes", "migracao_abc"}). Se None, calcula tudo. Análises caras
    (como migração entre faixas, que precisa da segmentação ABC) só rodam se
    pedidas — ou se outra análise pedida depender delas — evitando gastar
    tempo em algo que não vai para o relatório final. Com bases grandes
    (centenas de milhares de linhas), isso faz diferença real no tempo total.

    callback_log: função opcional callback_log(mensagem) chamada a cada etapa
    concluída, para permitir feedback de progresso na interface.

    Retorna um dicionário: { granularidade: { nome_analise: DataFrame } }
    (só contém as chaves efetivamente calculadas).
    """
    def logar(mensagem):
        if callback_log:
            callback_log(mensagem)

    todas_as_chaves = {
        "top_produtos", "top_clientes", "top_fabricantes", "poder_compra_clientes",
        "evolucao_produtos", "alertas_queda", "erosao_clientes", "abc", "abc_produtos",
        "migracao_abc", "produtos_em_alta", "produtos_em_queda", "clientes_queda_qtd",
        "correlacao_produto_cliente", "impacto_financeiro_churn",
    }
    pedidas = todas_as_chaves if chaves_solicitadas is None else set(chaves_solicitadas)

    def precisa(*chaves):
        return any(chave in pedidas for chave in chaves)

    # Resolve dependências entre análises (ex.: migração e poder de compra
    # dependem da segmentação ABC; correlação e impacto de churn dependem da
    # erosão de clientes) para nunca pular um cálculo que outro item pedido
    # ainda precisa, mas também nunca calcular o que ninguém pediu.
    precisa_tendencia = precisa("evolucao_produtos", "alertas_queda", "erosao_clientes", "correlacao_produto_cliente")
    precisa_erosao = precisa("erosao_clientes", "correlacao_produto_cliente", "impacto_financeiro_churn")
    precisa_abc = precisa("abc", "poder_compra_clientes", "migracao_abc")

    resultados = {}
    for granularidade in granularidades:
        analises = {}

        evolucao, alertas = (None, None)
        if precisa_tendencia:
            logar(f"[{granularidade}] Calculando tendência de produtos...")
            evolucao, alertas = tendencia_produtos(df, granularidade, periodos_queda_consecutiva)
            if precisa("evolucao_produtos"):
                analises["evolucao_produtos"] = evolucao
            if precisa("alertas_queda"):
                analises["alertas_queda"] = alertas

        erosao = None
        if precisa_erosao:
            logar(f"[{granularidade}] Calculando erosão de clientes por produto...")
            produtos_em_queda = alertas["descricao"].tolist() if alertas is not None and not alertas.empty else None
            erosao = erosao_clientes_por_produto(df, granularidade, produtos_alvo=produtos_em_queda)
            if precisa("erosao_clientes"):
                analises["erosao_clientes"] = erosao

        abc = None
        if precisa_abc:
            logar(f"[{granularidade}] Classificando clientes por faixa de faturamento...")
            abc = classificar_abc(df, granularidade, clientes_excluidos, cortes_clientes)
            if precisa("abc"):
                analises["abc"] = abc
            if precisa("poder_compra_clientes"):
                analises["poder_compra_clientes"] = poder_compra_clientes(abc)

        if precisa("abc_produtos"):
            logar(f"[{granularidade}] Classificando produtos por faixa de faturamento...")
            analises["abc_produtos"] = classificar_produtos_por_receita(df, granularidade, corte_produtos)

        if precisa("migracao_abc"):
            logar(f"[{granularidade}] Calculando migração de clientes entre faixas...")
            analises["migracao_abc"] = migracao_abc(df, abc, granularidade)

        if precisa("produtos_em_alta", "produtos_em_queda"):
            logar(f"[{granularidade}] Montando boletim de produtos em alta/queda...")
            produtos_alta, produtos_queda = produtos_alta_e_queda(df, granularidade)
            if precisa("produtos_em_alta"):
                analises["produtos_em_alta"] = produtos_alta
            if precisa("produtos_em_queda"):
                analises["produtos_em_queda"] = produtos_queda

        if precisa("clientes_queda_qtd"):
            logar(f"[{granularidade}] Montando boletim de clientes em queda de quantidade...")
            analises["clientes_queda_qtd"] = clientes_queda_quantidade(df, granularidade)

        if precisa("correlacao_produto_cliente"):
            logar(f"[{granularidade}] Calculando correlação produto x cliente...")
            analises["correlacao_produto_cliente"] = correlacao_produto_cliente(df, erosao, alertas, granularidade)

        if precisa("impacto_financeiro_churn"):
            logar(f"[{granularidade}] Calculando impacto financeiro do churn...")
            analises["impacto_financeiro_churn"] = impacto_financeiro_churn(df, erosao, granularidade)

        if precisa("top_produtos"):
            analises["top_produtos"] = top_produtos(df)
        if precisa("top_clientes"):
            analises["top_clientes"] = top_clientes(df)
        if precisa("top_fabricantes"):
            analises["top_fabricantes"] = top_fabricantes(df)

        resultados[granularidade] = analises
        logar(f"[{granularidade}] Concluído.")
    return resultados
