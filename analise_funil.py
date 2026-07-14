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

import re

REGEX_BALCAO = re.compile(
    r"(?i)(?:cliente sem cadastro|cliente final|venda externa|consumidor.*|.*balc[aã]o.*)"
)

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

    df = df.copy()

    # Descarta linhas com Ano ou Mês vazio (comuns em CSVs exportados com uma
    # linha em branco no final, ex: ";;;;;;;;;") — contadas para avisar o
    # usuário, em vez de virarem "Mês" == NaN e quebrar a validação abaixo.
    linhas_antes = len(df)
    df = df.dropna(subset=["Ano", "Mês"])
    linhas_vazias = linhas_antes - len(df)

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

    return df, linhas_vazias


def contar_produtos_nao_harmonizados(df):
    """Quantidade de linhas cujo produto não tinha descrição no CSV original."""
    return int((df["descricao"] == DESCRICAO_NAO_HARMONIZADA).sum())


COLUNA_PERIODO = {
    "Mensal": "Periodo_Mensal",
    "Trimestral": "Periodo_Trimestral",
    "Semestral": "Periodo_Semestral",
    "Anual": "Periodo_Anual",
}

MESES_ABREV = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
}


def _formatar_rotulo_periodo(periodo, granularidade):
    """
    Rótulo legível de um período para exibição em relatórios (não usado para
    ordenação/agrupamento — isso continua sendo feito com o valor original de
    Periodo, via _ordenar_periodos/COLUNA_PERIODO).

    Mensal "2025-08" -> "ago/25" | Trimestral "2025-T3" -> "T3/25"
    Semestral "2025-S1" -> "S1/25" | Anual "2025" -> "2025"
    """
    if granularidade == "Mensal":
        ano, mes = periodo.split("-")
        return f"{MESES_ABREV[int(mes)]}/{ano[-2:]}"
    if granularidade == "Trimestral":
        ano, tri = periodo.split("-T")
        return f"T{tri}/{ano[-2:]}"
    if granularidade == "Semestral":
        ano, sem = periodo.split("-S")
        return f"S{sem}/{ano[-2:]}"
    return periodo  # Anual: já é só o ano


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
# Top produtos
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


def _media_top3_sem_outliers(linha_receita_mensal):
    """
    Média dos 3 maiores meses-calendário do cliente, descartando antes
    picos isolados (um mês fora da curva, não uma capacidade sustentada)
    pelo critério de Tukey: qualquer mês acima de Q3 + 1,5×IQR dos meses
    ATIVOS do cliente (meses sem compra, valor 0, não entram no cálculo do
    quartil — ausência de compra não é "mês fraco"). Com menos de 4 meses
    ativos não há dado suficiente pra um quartil confiável, usa todos.

    Sem isso, um cliente que compra tipicamente ~R$50-90/mês mas teve UM
    mês de R$1.500 (peça avulsa, pedido atípico) tinha seu "potencial"
    inflado pra ~R$780 (média bruta dos 3 maiores) — quase 10x o que ele
    realmente sustenta. Testado contra 4 bases reais: o corte por IQR pega
    esses picos isolados sem descartar clientes que têm vários meses bons
    de verdade (nesse caso, a diferença entre o maior mês e os seguintes
    não é grande o bastante pra passar do limite de Tukey).
    """
    valores = linha_receita_mensal[linha_receita_mensal > 0]
    if len(valores) == 0:
        return 0.0
    if len(valores) < 4:
        return valores.sort_values(ascending=False).head(3).mean()
    q1, q3 = valores.quantile(0.25), valores.quantile(0.75)
    limite = q3 + 1.5 * (q3 - q1)
    sem_outliers = valores[valores <= limite]
    return sem_outliers.sort_values(ascending=False).head(3).mean()


def poder_compra_agregado(df, clientes_excluidos=None, cortes=(30.0, 50.0, 60.0), desconsiderar_balcao=False, top_n=None):
    """
    Poder de compra "de pico" de cada cliente: média dos 3 meses-calendário
    de MAIOR receita, descartando primeiro picos isolados que não refletem
    capacidade sustentada (ver _media_top3_sem_outliers) — não é a média
    corrida, nem o total agregado; reflete a capacidade de compra do
    cliente no seu melhor momento, não o comportamento típico do dia a dia.
    Sempre por Periodo_Mensal, independente da granularidade escolhida na
    tela (um "pico" é um conceito mensal).

    Compara esse potencial contra o desempenho recente (média dos 3 meses-
    calendário mais recentes disponíveis na base, não os "3 melhores" —
    meses sem compra do cliente entram como 0): Receita_Media_Recente e
    Desempenho_Vs_Potencial_Pct — a VARIAÇÃO percentual do recente frente
    ao potencial ((recente - potencial) ÷ potencial × 100), não a razão
    bruta: 0% = comprando exatamente o potencial, negativo = abaixo,
    positivo = acima (mesma convenção de "% de Variação" usada no resto do
    sistema — 100%/104% de razão bruta lia como "quase o dobro", quando o
    cliente só estava 4% acima do potencial). Também conta,
    dentro desses mesmos 3 meses recentes, quantos tiveram receita ≤ 40% do
    potencial (ou seja, uma queda de 60%+ frente ao que o cliente já
    demonstrou ser capaz de comprar) — Meses_60pct_Abaixo_Potencial.
    Clientes sem poder de compra (0 — nunca compraram) não entram nessa
    contagem, sem base de comparação.

    Grupo e Percentual_Acumulado vêm de classificar_clientes_agregado — ou
    seja, do tamanho do cliente pela receita TOTAL, não pelo poder de compra.
    Decisão deliberada: a segmentação em grupos continua refletindo o
    cliente como um todo; poder de compra é uma métrica complementar, não
    substitui a segmentação por receita.

    top_n: se informado, mantém só os N clientes de maior Poder_De_Compra
    (None = todos — sem isso, a base completa vira uma lista gigante,
    pouco prática de revisar).

    Retorna (sem período, uma linha por cliente): Cliente, Poder_De_Compra,
    Receita_Media_Recente, Desempenho_Vs_Potencial_Pct,
    Meses_60pct_Abaixo_Potencial, Percentual_Acumulado, Grupo.
    """
    excluidos = set(clientes_excluidos or [])
    base = df[~df["Cliente"].isin(excluidos)] if excluidos else df

    receita_mensal = base.groupby(["Cliente", "Periodo_Mensal"], as_index=False)["Receita"].sum()
    pivot = receita_mensal.pivot(index="Cliente", columns="Periodo_Mensal", values="Receita").fillna(0.0)

    top3_por_cliente = pivot.apply(_media_top3_sem_outliers, axis=1)
    top3_por_cliente.name = "Poder_De_Compra"

    periodos_ordenados = _ordenar_periodos(pivot.columns, "Mensal")
    ultimos_3 = periodos_ordenados[-3:]
    colunas_recentes = pivot[ultimos_3]
    media_recente = colunas_recentes.mean(axis=1)
    media_recente.name = "Receita_Media_Recente"

    # "60% abaixo do potencial" = receita do mês ≤ 40% do Poder_De_Compra.
    limite_40pct = top3_por_cliente * 0.4
    meses_abaixo = colunas_recentes.le(limite_40pct, axis=0).sum(axis=1)
    meses_abaixo = meses_abaixo.where(top3_por_cliente > 0, 0)
    meses_abaixo.name = "Meses_60pct_Abaixo_Potencial"

    classificacao = classificar_clientes_agregado(df, clientes_excluidos, cortes, desconsiderar_balcao)
    resultado = classificacao[["Cliente", "Percentual_Acumulado", "Faixa"]].rename(columns={"Faixa": "Grupo"})
    resultado = resultado.merge(top3_por_cliente, on="Cliente", how="left")
    resultado = resultado.merge(media_recente, on="Cliente", how="left")
    resultado = resultado.merge(meses_abaixo, on="Cliente", how="left")
    resultado["Poder_De_Compra"] = resultado["Poder_De_Compra"].fillna(0.0)
    resultado["Receita_Media_Recente"] = resultado["Receita_Media_Recente"].fillna(0.0)
    resultado["Meses_60pct_Abaixo_Potencial"] = resultado["Meses_60pct_Abaixo_Potencial"].fillna(0).astype(int)

    resultado["Desempenho_Vs_Potencial_Pct"] = np.where(
        resultado["Poder_De_Compra"] > 0,
        (resultado["Receita_Media_Recente"] - resultado["Poder_De_Compra"]) / resultado["Poder_De_Compra"] * 100,
        np.nan,
    )

    resultado = resultado[["Cliente", "Poder_De_Compra", "Receita_Media_Recente", "Desempenho_Vs_Potencial_Pct",
                            "Meses_60pct_Abaixo_Potencial", "Percentual_Acumulado", "Grupo"]]
    resultado.sort_values("Poder_De_Compra", ascending=False, inplace=True)
    if top_n:
        resultado = resultado.head(top_n)
    resultado.reset_index(drop=True, inplace=True)
    return resultado


# ---------------------------------------------------------------------------
# Tendência de produtos
# ---------------------------------------------------------------------------

def _tendencia_percentual(receitas_ordenadas):
    """
    Tendência de uma série de receitas (já em ordem cronológica): compara a
    média dos últimos períodos com a média dos primeiros. Usa 3 pontos de
    cada ponta; com menos de 6 pontos ao todo, divide a série ao meio (mínimo
    1 ponto de cada lado) em vez de deixar as duas janelas se sobreporem.

    Preferido a CAGR ponto-a-ponto (1º vs último) porque um único período
    fora da curva em qualquer ponta não distorce o resultado sozinho, e a
    regressão linear (outra opção avaliada) dá um número por período mais
    difícil de explicar num relatório do que "média dos últimos vs primeiros".
    """
    n = len(receitas_ordenadas)
    if n < 2:
        return 0.0
    tamanho_janela = 3 if n >= 6 else max(1, n // 2)
    primeiros = receitas_ordenadas[:tamanho_janela]
    ultimos = receitas_ordenadas[-tamanho_janela:]
    media_primeiros = primeiros.mean()
    media_ultimos = ultimos.mean()
    if media_primeiros == 0:
        return 0.0
    return (media_ultimos / media_primeiros - 1) * 100


def tendencia_produtos(df, granularidade="Mensal", periodos_queda_consecutiva=2, top_n=None, queda_minima_reais=0.0):
    """
    Evolução de receita/quantidade por produto ao longo dos períodos.
    Sinaliza produtos com queda em N períodos consecutivos (parametrizável).

    queda_minima_reais: só entram em alertas_df produtos cuja "Queda em R$"
    (Receita Precedente à Queda − Receita Atual) seja de pelo menos esse
    valor — evita alertar sobre quedas pequenas, sem relevância financeira
    (padrão 0 = qualquer queda, sem piso).

    top_n: se informado, mantém só os N produtos com maior tendência em
    evolucao_df (todos os períodos desses produtos) e as N linhas com maior
    "Queda em R$" em alertas_df (já respeitando queda_minima_reais).
    None = todos os produtos.

    Retorna (evolucao_df, alertas_df):
      - evolucao_df: uma linha por (produto, período), ordenada por tendência
        (Tendencia_Pct) descendente — ver _tendencia_percentual. "Periodo" é
        um rótulo legível (ex.: "ago/25"); a ordem cronológica já foi
        aplicada antes dessa conversão.
      - alertas_df: uma linha por produto em queda AGORA — a sequência de
        quedas precisa terminar no período mais recente (queda atual, não
        um histórico antigo já recuperado). "Receita Precedente à Queda"/
        "Receita Atual" se referem à janela dessa sequência (o período-base
        antes da primeira queda até o último período), não aos extremos de
        todo o histórico do produto — o período atual em si não aparece
        como coluna porque é sempre o mesmo valor em todas as linhas (o
        último período disponível). "Queda em R$" é a soma acumulada da
        perda em CADA período da sequência frente ao período-base (não só
        a diferença entre o primeiro e o último) — uma queda que persiste
        por vários períodos pesa mais do que uma queda pontual do mesmo
        tamanho no último período. Ordenado por "Queda em R$" descendente:
        ainda prioriza impacto financeiro acumulado, não só duração —um
        produto de alto volume caindo poucos períodos pode acumular mais
        perda que um de baixo volume caindo há muito mais tempo, e isso é
        esperado (o valor em R$ importa mais que a contagem de períodos).
        "% Média de Queda" é a média das variações percentuais dentro dessa
        janela (magnitude positiva).
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
    # Receita negativa (devoluções/estornos líquidos no mês) quebra a leitura
    # de "queda"/"alta" da variação percentual — período anterior negativo ou
    # zero já não entra no cálculo; período atual negativo também não, pois
    # o percentual resultante não tem leitura de magnitude coerente.
    anterior_valido = evolucao["Receita_Periodo_Anterior"].notnull() & (evolucao["Receita_Periodo_Anterior"] > 0)
    atual_valido = evolucao["Receita"] >= 0
    evolucao["Variacao_Percentual"] = np.where(
        anterior_valido & atual_valido,
        (evolucao["Receita"] - evolucao["Receita_Periodo_Anterior"]) / evolucao["Receita_Periodo_Anterior"] * 100,
        np.nan,
    )

    # Detecta queda em N períodos consecutivos terminando no período mais
    # recente (queda atual) e calcula a tendência geral (mesma passada pelos
    # grupos, evita repetir o groupby).
    alertas = []
    tendencia_por_produto = {}
    for produto, grupo in evolucao.groupby("descricao"):
        grupo = grupo.sort_values("_ordem")
        tendencia_por_produto[produto] = _tendencia_percentual(grupo["Receita"].to_numpy())

        quedas_seguidas = 0
        for variacao in grupo["Variacao_Percentual"]:
            if pd.notnull(variacao) and variacao < 0:
                quedas_seguidas += 1
            else:
                quedas_seguidas = 0
        if quedas_seguidas >= periodos_queda_consecutiva:
            janela = grupo.tail(quedas_seguidas + 1)
            media_queda_pct = -grupo["Variacao_Percentual"].tail(quedas_seguidas).mean()
            receita_anterior = janela["Receita"].iloc[0]
            receita_atual = grupo["Receita"].iloc[-1]
            # Soma acumulada da perda mês a mês (baseline fixo = receita
            # ANTES da primeira queda da sequência, comparado contra CADA um
            # dos "quedas_seguidas" meses seguintes) — não só a diferença
            # entre o primeiro e o último mês. Uma queda longa e constante
            # deveria pesar mais que uma queda curta e única do mesmo
            # tamanho pontual; início-vs-fim ignorava isso por completo.
            queda_acumulada = (receita_anterior - janela["Receita"].iloc[1:]).sum()
            alertas.append({
                "descricao": produto,
                "Períodos Consecutivos em Queda": quedas_seguidas,
                "Período Anterior à Queda": _formatar_rotulo_periodo(janela["Periodo"].iloc[0], granularidade),
                "Receita Precedente à Queda": receita_anterior,
                "Qtd Precedente à Queda": janela["QTD"].iloc[0],
                "Receita Atual": receita_atual,
                "Qtd Atual": grupo["QTD"].iloc[-1],
                "Queda em R$": queda_acumulada,
                "% Média de Queda": media_queda_pct,
            })

    evolucao["Tendencia_Pct"] = evolucao["descricao"].map(tendencia_por_produto)

    if top_n is not None:
        produtos_top = (
            evolucao[["descricao", "Tendencia_Pct"]].drop_duplicates("descricao")
            .sort_values("Tendencia_Pct", ascending=False).head(top_n)["descricao"]
        )
        evolucao = evolucao[evolucao["descricao"].isin(produtos_top)]

    evolucao.sort_values(["Tendencia_Pct", "descricao", "_ordem"], ascending=[False, True, True], inplace=True)
    evolucao["Periodo"] = evolucao["Periodo"].apply(lambda p: _formatar_rotulo_periodo(p, granularidade))
    evolucao.drop(columns=["_ordem"], inplace=True)
    evolucao.reset_index(drop=True, inplace=True)

    alertas_df = pd.DataFrame(alertas)
    if not alertas_df.empty:
        if queda_minima_reais > 0:
            alertas_df = alertas_df[alertas_df["Queda em R$"] >= queda_minima_reais]
        alertas_df.sort_values("Queda em R$", ascending=False, inplace=True)
        if top_n is not None:
            alertas_df = alertas_df.head(top_n)
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


def status_alto_giro(df, desconsiderar_balcao=False, clientes_grupo1=None, mapa_faixa_cliente=None):
    """
    Relatório executivo, sem granularidade (sempre por mês-calendário):
    para cada produto presente em df (o chamador já filtra pra só os de
    alto giro — esta função não faz corte de produto nenhum, só reflete o
    que recebe; desmarcar um produto na tela some com ele daqui
    automaticamente, sem precisar de lógica de "substituição"), mostra a
    receita do último mês completo e se está em alta ou queda (variação %
    vs. o mês anterior) — isso sim considerando só clientes do Grupo 1
    (clientes_grupo1, se informado; None = todos os clientes).

    Cliente_Destaque e Cliente_Em_Queda são outra métrica: não é quem tem
    maior faturamento, é quem mais CRESCEU (Destaque) e quem mais CAIU
    (Em Queda) em % de variação da própria compra desse produto (mês atual
    vs. anterior) — por isso consideram clientes de TODOS os grupos, não só
    Grupo 1 (o corte de grupo vale pra receita/status do produto, não pra
    essa comparação de crescimento/queda individual). Exigem compra > 0 nos
    DOIS períodos (desconsidera quem apareceu do zero ou sumiu de vez — isso
    é assunto de Erosão/Sem Venda, não de crescimento/queda comparável) e
    Destaque exige variação positiva / Em Queda exige variação negativa
    ("—" quando ninguém se encaixa). Cliente_Destaque nunca repete o mesmo
    nome de Cliente_Em_Queda no mesmo produto.

    mapa_faixa_cliente (dict Cliente -> Faixa, de classificar_clientes_
    agregado): quando informado, prioriza Grupo 1 > Grupo 2 > Grupo 3 >
    demais na escolha de Destaque/Em Queda — só usa um cliente de faixa
    "pior" quando não há nenhum candidato válido na faixa melhor para
    aquele produto. Dentro da mesma faixa, desempate por maior % de
    variação. None = ordena só por % de variação, sem prioridade de faixa.

    desconsiderar_balcao exclui clientes-balcão (venda de balcão/consumidor
    final, ver REGEX_BALCAO) da escolha desses dois clientes — sem isso,
    "BALCAO AVULSO" domina como destaque/queda na maioria dos produtos, sem
    ser um cliente real e endereçável.
    """
    colunas_vazias = ["descricao", "Receita_Atual", "Status", "Variacao_Percentual",
                       "Cliente_Destaque", "Variacao_Percentual_Cliente_Destaque",
                       "Cliente_Em_Queda", "Variacao_Percentual_Cliente_Em_Queda"]
    periodos_ordenados = _ordenar_periodos(df["Periodo_Mensal"].unique(), "Mensal")
    if len(periodos_ordenados) < 2:
        return pd.DataFrame(columns=colunas_vazias)

    periodo_anterior, periodo_atual = periodos_ordenados[-2], periodos_ordenados[-1]
    base = df[df["Periodo_Mensal"].isin([periodo_anterior, periodo_atual])]

    base_produto = base if clientes_grupo1 is None else base[base["Cliente"].isin(clientes_grupo1)]
    por_produto = base_produto.groupby(["descricao", "Periodo_Mensal"], as_index=False)["Receita"].sum()
    pivot_produto = por_produto.pivot(index="descricao", columns="Periodo_Mensal", values="Receita").fillna(0)
    receita_atual = pivot_produto.get(periodo_atual, pd.Series(0.0, index=pivot_produto.index))
    receita_anterior = pivot_produto.get(periodo_anterior, pd.Series(0.0, index=pivot_produto.index))

    resultado = pd.DataFrame({
        "descricao": pivot_produto.index,
        "Receita_Atual": receita_atual.values,
        "Receita_Anterior": receita_anterior.values,
    })
    resultado["Variacao_Percentual"] = np.where(
        resultado["Receita_Anterior"] > 0,
        (resultado["Receita_Atual"] - resultado["Receita_Anterior"]) / resultado["Receita_Anterior"] * 100,
        np.nan,
    )
    resultado["Status"] = np.select(
        [resultado["Variacao_Percentual"] > 0, resultado["Variacao_Percentual"] < 0],
        ["Em alta", "Em queda"],
        default="Estável",
    )

    # Cliente destaque/em queda usam TODOS os clientes (todos os grupos),
    # não só base_produto (Grupo 1) — ver docstring.
    por_produto_cliente = base.groupby(["descricao", "Cliente", "Periodo_Mensal"], as_index=False)["Receita"].sum()
    pivot_cliente = por_produto_cliente.pivot_table(
        index=["descricao", "Cliente"], columns="Periodo_Mensal", values="Receita", fill_value=0,
    )
    tabela_cliente = pivot_cliente.get(periodo_atual, pd.Series(0.0, index=pivot_cliente.index)).reset_index(name="Receita_Atual_Cliente")
    tabela_cliente["Receita_Anterior_Cliente"] = pivot_cliente.get(
        periodo_anterior, pd.Series(0.0, index=pivot_cliente.index)
    ).values
    # Variação % DO CLIENTE nesse produto (não confundir com a variação % do
    # produto como um todo, já calculada acima em resultado["Variacao_Percentual"]
    # — aqui é só a compra desse cliente específico, mês atual vs. anterior).
    tabela_cliente["Variacao_Percentual_Cliente"] = np.where(
        tabela_cliente["Receita_Anterior_Cliente"] > 0,
        (tabela_cliente["Receita_Atual_Cliente"] - tabela_cliente["Receita_Anterior_Cliente"])
        / tabela_cliente["Receita_Anterior_Cliente"] * 100,
        np.nan,
    )
    if desconsiderar_balcao:
        tabela_cliente = tabela_cliente[~tabela_cliente["Cliente"].str.contains(REGEX_BALCAO, na=False)]

    # Só entram candidatos com compra > 0 nos DOIS períodos — desconsidera
    # quem apareceu do zero ou sumiu de vez (sem base de comparação real).
    comparaveis = tabela_cliente[
        (tabela_cliente["Receita_Anterior_Cliente"] > 0) & (tabela_cliente["Receita_Atual_Cliente"] > 0)
    ].copy()

    # Prioridade de faixa (Grupo 1 > Grupo 2 > Grupo 3 > demais): número menor
    # = mais prioridade. "Grupo N" -> N; qualquer outra coisa (Demais, Balcão,
    # cliente fora da classificação) ou mapa_faixa_cliente=None -> sem
    # prioridade nenhuma (todo mundo empata, desempate cai 100% no % de
    # variação, mesmo comportamento de antes desse parâmetro existir).
    def _prioridade_faixa(faixa):
        if isinstance(faixa, str) and faixa.startswith("Grupo "):
            try:
                return int(faixa.split(" ")[1])
            except ValueError:
                return 999
        return 999

    if mapa_faixa_cliente:
        comparaveis["_prioridade_grupo"] = comparaveis["Cliente"].map(mapa_faixa_cliente).apply(_prioridade_faixa)
    else:
        comparaveis["_prioridade_grupo"] = 999

    # Cliente_Em_Queda: prioriza faixa (Grupo 1 primeiro), desempate por
    # maior queda %. Exige variação negativa — "—" se ninguém realmente caiu.
    em_queda_ordenado = (
        comparaveis[comparaveis["Variacao_Percentual_Cliente"] < 0]
        .sort_values(["_prioridade_grupo", "Variacao_Percentual_Cliente"], ascending=[True, True])
        .drop_duplicates("descricao")
        .set_index("descricao")
    )
    em_queda_cliente = em_queda_ordenado["Cliente"]
    variacao_em_queda = em_queda_ordenado["Variacao_Percentual_Cliente"]

    # Cliente_Destaque: mesma prioridade de faixa, desempate por maior
    # crescimento %. Exige variação positiva. Um cliente em queda não pode
    # ser também o "destaque" do mesmo produto — o posto passa pro próximo
    # candidato que não esteja em queda nesse produto.
    comparaveis["_em_queda_do_produto"] = comparaveis["descricao"].map(em_queda_cliente)
    candidatos_destaque = comparaveis[
        (comparaveis["Variacao_Percentual_Cliente"] > 0)
        & (comparaveis["Cliente"] != comparaveis["_em_queda_do_produto"])
    ]
    destaque_ordenado = (
        candidatos_destaque
        .sort_values(["_prioridade_grupo", "Variacao_Percentual_Cliente"], ascending=[True, False])
        .drop_duplicates("descricao")
        .set_index("descricao")
    )
    destaque = destaque_ordenado["Cliente"]
    variacao_destaque = destaque_ordenado["Variacao_Percentual_Cliente"]

    resultado["Cliente_Destaque"] = resultado["descricao"].map(destaque).fillna("—")
    resultado["Variacao_Percentual_Cliente_Destaque"] = resultado["descricao"].map(variacao_destaque)
    resultado["Cliente_Em_Queda"] = resultado["descricao"].map(em_queda_cliente).fillna("—")
    resultado["Variacao_Percentual_Cliente_Em_Queda"] = resultado["descricao"].map(variacao_em_queda)

    resultado = resultado[["descricao", "Receita_Atual", "Status", "Variacao_Percentual",
                            "Cliente_Destaque", "Variacao_Percentual_Cliente_Destaque",
                            "Cliente_Em_Queda", "Variacao_Percentual_Cliente_Em_Queda"]]
    resultado.sort_values("Receita_Atual", ascending=False, inplace=True)
    resultado.reset_index(drop=True, inplace=True)
    return resultado


# ---------------------------------------------------------------------------
# Erosão de clientes por produto
# ---------------------------------------------------------------------------

def _erosao_generico(df, chaves_agrupamento, reducao_minima_percentual, queda_minima_reais):
    """
    Núcleo comum de erosao_clientes_por_produto/erosao_clientes_geral: por
    chaves_agrupamento (ex.: ["descricao", "Cliente"] ou só ["Cliente"]),
    compara a receita do último mês completo contra o "pico" (maior mês de
    receita em qualquer ponto anterior do histórico, não só o mês
    imediatamente anterior). Ver docstring de erosao_clientes_por_produto
    para o raciocínio completo (janela relativa, sem granularidade, etc.).
    """
    colunas_vazias = chaves_agrupamento + ["Periodo_Pico", "Receita_Periodo_Anterior",
                                           "Periodo", "Receita", "Reducao_Receita",
                                           "Reducao_Percentual", "Parou_De_Comprar"]
    periodos_ordenados = _ordenar_periodos(df["Periodo_Mensal"].unique(), "Mensal")
    if len(periodos_ordenados) < 2:
        return pd.DataFrame(columns=colunas_vazias)

    ultimo_periodo = periodos_ordenados[-1]
    mensal = df.groupby(chaves_agrupamento + ["Periodo_Mensal"], as_index=False)["Receita"].sum()

    # Pico: maior receita mensal em QUALQUER mês anterior ao último (não só
    # o mês imediatamente anterior) — meses com receita negativa
    # (devolução/estorno) não contam como "pico".
    anteriores = mensal[(mensal["Periodo_Mensal"] != ultimo_periodo) & (mensal["Receita"] > 0)]
    if anteriores.empty:
        return pd.DataFrame(columns=colunas_vazias)
    indices_pico = anteriores.groupby(chaves_agrupamento)["Receita"].idxmax()
    pico = anteriores.loc[indices_pico, chaves_agrupamento + ["Periodo_Mensal", "Receita"]]
    pico = pico.rename(columns={"Periodo_Mensal": "Periodo_Pico", "Receita": "Receita_Periodo_Anterior"})

    atual = mensal[mensal["Periodo_Mensal"] == ultimo_periodo][chaves_agrupamento + ["Receita"]]

    erosao = pico.merge(atual, on=chaves_agrupamento, how="left")
    erosao["Receita"] = erosao["Receita"].fillna(0.0)
    erosao["Periodo"] = ultimo_periodo

    # Receita atual negativa (devolução/estorno que superou a venda do
    # período) não é uma redução de compra no sentido normal — o percentual
    # de queda passaria de 100% (ex.: caiu de R$1.129 para -R$360 = "134% de
    # redução", sem leitura de negócio). Esses casos ficam fora do relatório.
    erosao = erosao[
        (erosao["Receita"] >= 0) & (erosao["Receita"] < erosao["Receita_Periodo_Anterior"])
    ].copy()

    erosao["Reducao_Receita"] = erosao["Receita_Periodo_Anterior"] - erosao["Receita"]
    erosao["Reducao_Percentual"] = erosao["Reducao_Receita"] / erosao["Receita_Periodo_Anterior"] * 100
    erosao["Parou_De_Comprar"] = erosao["Receita"] == 0

    erosao = erosao[erosao["Reducao_Percentual"] >= reducao_minima_percentual]
    if queda_minima_reais > 0:
        erosao = erosao[erosao["Reducao_Receita"] >= queda_minima_reais]
    erosao["Periodo_Pico"] = erosao["Periodo_Pico"].apply(lambda p: _formatar_rotulo_periodo(p, "Mensal"))
    erosao["Periodo"] = erosao["Periodo"].apply(lambda p: _formatar_rotulo_periodo(p, "Mensal"))
    return erosao.reset_index(drop=True)


def erosao_clientes_por_produto(df, produtos_alvo=None, reducao_minima_percentual=50.0, queda_minima_reais=0.0):
    """
    Relatório executivo, sem granularidade (sempre por Periodo_Mensal — mesmo
    padrão de poder_compra_agregado): para cada cliente+produto, compara a
    receita do último mês completo disponível contra o "pico" (maior mês
    de receita em qualquer ponto anterior do histórico, não só o mês
    imediatamente anterior). Captura tanto uma queda recente (mês passado
    vs. este) quanto uma erosão mais lenta (ex.: comprava muito em jan/fev,
    praticamente parou de mar a jun) — o período de referência é relativo a
    cada cliente+produto, não um par fixo de períodos.

    Como a comparação é sempre feita contra o ÚLTIMO mês disponível, um
    cliente que caiu e já voltou a comprar no ritmo de antes não aparece —
    só entra quem ainda está em queda agora.

    reducao_minima_percentual: só entram no resultado clientes cuja queda,
    do pico até o último mês, foi de pelo menos esse percentual (padrão
    50% — ajustável; use 0 para ver toda e qualquer redução).

    queda_minima_reais: além do percentual, a queda em R$ (Receita_Periodo_
    Anterior − Receita) também precisa ser de pelo menos esse valor (padrão
    0 = sem piso) — os dois critérios precisam ser atingidos juntos.
    """
    base = df
    if produtos_alvo:
        base = base[base["descricao"].isin(produtos_alvo)]
    erosao = _erosao_generico(base, ["descricao", "Cliente"], reducao_minima_percentual, queda_minima_reais)
    erosao = erosao[["Cliente", "descricao", "Periodo_Pico", "Receita_Periodo_Anterior",
                      "Periodo", "Receita", "Reducao_Receita", "Reducao_Percentual", "Parou_De_Comprar"]]
    erosao.sort_values(["Cliente", "Reducao_Receita"], ascending=[True, False], inplace=True)
    erosao.reset_index(drop=True, inplace=True)
    return erosao


def erosao_clientes_geral(df, reducao_minima_percentual=50.0, queda_minima_reais=0.0):
    """
    Igual a erosao_clientes_por_produto, mas agregado por CLIENTE (soma de
    todos os produtos que ele compra), não por cliente+produto — mostra
    quem está comprando muito menos no geral, mesmo que nenhum produto
    específico isolado pareça uma queda tão grande. Mesmas métricas e
    critérios (pico vs. último mês completo, piso % e piso em R$).
    """
    erosao = _erosao_generico(df, ["Cliente"], reducao_minima_percentual, queda_minima_reais)
    erosao = erosao[["Cliente", "Periodo_Pico", "Receita_Periodo_Anterior",
                      "Periodo", "Receita", "Reducao_Receita", "Reducao_Percentual", "Parou_De_Comprar"]]
    erosao.sort_values("Reducao_Receita", ascending=False, inplace=True)
    erosao.reset_index(drop=True, inplace=True)
    return erosao


def sem_venda(df, reducao_minima_percentual=90.0, cortes=(30.0, 50.0, 60.0), desconsiderar_balcao=False):
    """
    Relatório executivo, sem granularidade (sempre por Periodo_Mensal):
    clientes que já compraram alguma vez, mas praticamente pararam — a
    receita do mês mais recente caiu reducao_minima_percentual% ou mais
    frente ao pico histórico (padrão 90%, ou seja, sobrou no máximo 10% do
    que o cliente já demonstrou comprar no auge). Reaproveita o mesmo
    motor de erosao_clientes_geral (_erosao_generico), mas DE PROPÓSITO
    sem piso de R$ — diferente de Erosão de Clientes (piso padrão de
    R$3000), aqui o objetivo é justamente pegar clientes de baixo volume
    que a Erosão descarta pelo piso financeiro, mas que mesmo assim
    pararam de comprar de verdade (ex.: um cliente Grupo 3 que comprou
    bem por 2 meses e nunca mais voltou).

    Ao contrário dos relatórios de erosão (que só mostram pico x atual),
    a tabela aqui é "larga": uma coluna de receita por MÊS disponível na
    base inteira, pra ver a trajetória completa (comprava, parou) de cada
    cliente de uma vez, em vez de só os dois extremos.

    Retorna: Cliente, Grupo (faixa ABC pela receita total — ver
    classificar_clientes_agregado — não pelo poder de compra), Receita no
    Pico, e uma coluna por mês disponível na base (rótulo legível, ex.
    "ago/25") — ordenado por Receita no Pico descendente (maior potencial
    perdido primeiro).
    """
    colunas_vazias = ["Cliente", "Grupo", "Receita no Pico"]
    clientes_erosao = _erosao_generico(df, ["Cliente"], reducao_minima_percentual, queda_minima_reais=0.0)
    if clientes_erosao.empty:
        return pd.DataFrame(columns=colunas_vazias)

    clientes_alvo = set(clientes_erosao["Cliente"])
    periodos_ordenados = _ordenar_periodos(df["Periodo_Mensal"].unique(), "Mensal")

    receita_mensal = (
        df[df["Cliente"].isin(clientes_alvo)]
        .groupby(["Cliente", "Periodo_Mensal"], as_index=False)["Receita"].sum()
    )
    pivot = receita_mensal.pivot(index="Cliente", columns="Periodo_Mensal", values="Receita")
    pivot = pivot.reindex(columns=periodos_ordenados).fillna(0.0)
    pivot.columns = [_formatar_rotulo_periodo(p, "Mensal") for p in pivot.columns]

    classificacao = classificar_clientes_agregado(df, cortes=cortes, desconsiderar_balcao=desconsiderar_balcao)
    mapa_grupo = dict(zip(classificacao["Cliente"], classificacao["Faixa"]))
    mapa_pico = clientes_erosao.set_index("Cliente")["Receita_Periodo_Anterior"]

    resultado = pivot.reset_index()
    resultado.insert(1, "Grupo", resultado["Cliente"].map(mapa_grupo).fillna("-"))
    resultado.insert(2, "Receita no Pico", resultado["Cliente"].map(mapa_pico))
    resultado.sort_values("Receita no Pico", ascending=False, inplace=True)
    resultado.reset_index(drop=True, inplace=True)
    return resultado


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

def calcular_frequencia(df, granularidade="Mensal", campo="Cliente", desconsiderar_balcao=False):
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
    
    if desconsiderar_balcao and campo == "Cliente":
        mascara = frequencia[campo].str.contains(REGEX_BALCAO, na=False)
        frequencia.loc[mascara, "Frequencia_Simples"] = 0
        
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
                        cortes=(30.0, 50.0, 60.0), nomes_grupos=None, desconsiderar_balcao=False):
    """
    Classifica entidades (clientes ou produtos) em faixas por representatividade
    acumulada no faturamento, período a período.

    cortes: percentuais cumulativos crescentes (ex.: (30, 50, 60)). A última
    faixa (nome "Demais") recebe tudo que ultrapassar o último corte.
    excluidos: valores da entidade a remover do cálculo (ex.: clientes fora
    da análise). O faturamento de referência é recalculado sem eles.

    Clientes balcão (quando desconsiderar_balcao=True e campo="Cliente")
    saem do cálculo de grupos/percentual acumulado e ficam numa faixa
    "Balcão" própria, com Percentual_Individual real (não zerado) — mesma
    regra usada na prévia da tela (classificar_clientes_agregado).

    Retorna um DataFrame com: campo, Receita, Percentual_Acumulado,
    Percentual_Individual, Periodo, Faixa_ABC, Frequencia_Simples,
    Frequencia_Acumulada, Renuncia, Renuncia_Acumulada, Renuncia_Percentual.
    """
    excluidos = set(excluidos or [])
    cortes = list(cortes)
    nomes_grupos = list(nomes_grupos) if nomes_grupos else [f"Grupo {i + 1}" for i in range(len(cortes))]
    nomes_grupos = nomes_grupos + ["Demais"]

    col_periodo = COLUNA_PERIODO[granularidade]
    base = df[~df[campo].isin(excluidos)] if excluidos else df

    resultados = []
    for periodo, grupo in base.groupby(col_periodo):
        if desconsiderar_balcao and campo == "Cliente":
            mascara_balcao = grupo[campo].str.contains(REGEX_BALCAO, na=False)
            grupo_normal = grupo[~mascara_balcao]
            grupo_balcao = grupo[mascara_balcao]
        else:
            grupo_normal = grupo
            grupo_balcao = pd.DataFrame(columns=grupo.columns)

        receita_entidade = (
            grupo_normal.groupby(campo, as_index=False)["Receita"].sum()
            .sort_values("Receita", ascending=False)
            .reset_index(drop=True)
        )
        receita_total = receita_entidade["Receita"].sum()
        if receita_total <= 0:
            receita_entidade["Percentual_Acumulado"] = 0.0
            receita_entidade["Percentual_Individual"] = 0.0
        else:
            receita_entidade["Percentual_Acumulado"] = (
                receita_entidade["Receita"].cumsum() / receita_total * 100
            )
            receita_entidade["Percentual_Individual"] = receita_entidade["Receita"] / receita_total * 100
        receita_entidade["Periodo"] = periodo

        def faixa(percentual_acumulado):
            for corte, nome in zip(cortes, nomes_grupos):
                if percentual_acumulado <= corte:
                    return nome
            return nomes_grupos[-1]

        receita_entidade["Faixa_ABC"] = receita_entidade["Percentual_Acumulado"].apply(faixa)

        if not grupo_balcao.empty:
            # Balcão fica de fora da classificação em grupos (o corte acima
            # é calculado só com grupo_normal), mas o % individual mostrado
            # é real — não faz sentido excluir da conta E mostrar receita
            # zerada. Fica sempre em faixa "Balcão" própria, nunca misturado
            # com "Grupo 1" (que deve refletir só quem participa de fato da
            # segmentação por receita).
            receita_balcao = (
                grupo_balcao.groupby(campo, as_index=False)["Receita"].sum()
                .sort_values("Receita", ascending=False)
                .reset_index(drop=True)
            )
            receita_balcao["Percentual_Acumulado"] = float("nan")
            receita_balcao["Percentual_Individual"] = (
                receita_balcao["Receita"] / receita_total * 100 if receita_total > 0 else 0.0
            )
            receita_balcao["Periodo"] = periodo
            receita_balcao["Faixa_ABC"] = "Balcão"
            receita_entidade = pd.concat([receita_balcao, receita_entidade], ignore_index=True)

        resultados.append(receita_entidade)

    colunas_base = [campo, "Receita", "Percentual_Acumulado", "Percentual_Individual", "Periodo", "Faixa_ABC"]
    if not resultados:
        classificado = pd.DataFrame(columns=colunas_base)
    else:
        classificado = pd.concat(resultados, ignore_index=True)

    frequencia = calcular_frequencia(base, granularidade, campo, desconsiderar_balcao=desconsiderar_balcao)
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
    classificado.sort_values(["_ordem", "Percentual_Acumulado", "Receita"], ascending=[True, True, False], inplace=True)
    classificado.drop(columns=["_ordem"], inplace=True)
    classificado.reset_index(drop=True, inplace=True)
    return classificado


def _limitar_top_por_grupo(classificado, top_por_grupo):
    """Mantém só as `top_por_grupo` linhas de maior Receita em cada (Periodo, Faixa_ABC). None = sem corte."""
    if top_por_grupo is None or classificado.empty:
        return classificado
    limitado = (
        classificado.sort_values("Receita", ascending=False)
        .groupby(["Periodo", "Faixa_ABC"], group_keys=False)
        .head(top_por_grupo)
    )
    limitado.sort_values(["Periodo", "Faixa_ABC", "Receita"], ascending=[True, True, False], inplace=True)
    limitado.reset_index(drop=True, inplace=True)
    return limitado


def classificar_abc(df, granularidade="Mensal", clientes_excluidos=None, cortes_clientes=(30.0, 50.0, 60.0),
                     desconsiderar_balcao=False, top_clientes_por_grupo=5):
    """
    Classificação de clientes por representatividade no faturamento (ver
    classificar_faixas) — recorte "executivo" pro relatório final:

      - mantém só os `top_clientes_por_grupo` clientes de maior receita em
        cada (Período, Faixa) — None mantém todos, sem corte. IMPORTANTE:
        quem depende da classificação COMPLETA (migração de faixa, poder de
        compra) deve chamar com top_clientes_por_grupo=None — um corte de
        top 5 aqui faria a migração só enxergar 5 clientes por grupo.
      - descarta Frequencia_Simples/Frequencia_Acumulada: não fazem sentido
        junto de um corte "top N por grupo" (a frequência de compra do
        cliente não muda por causa do corte, e a coluna ao lado de "top 5"
        sugere o contrário).
    """
    classificado = classificar_faixas(
        df, granularidade, campo="Cliente", excluidos=clientes_excluidos,
        cortes=cortes_clientes, desconsiderar_balcao=desconsiderar_balcao,
    )
    classificado = classificado.drop(columns=["Frequencia_Simples", "Frequencia_Acumulada"])
    return _limitar_top_por_grupo(classificado, top_clientes_por_grupo)


def classificar_produtos_por_receita(df, granularidade="Mensal", corte_percentual=80.0):
    """
    Classificação de produtos por representatividade no faturamento: faixa
    "Grupo 1" concentra o corte_percentual (padrão 80%) inicial de receita
    acumulada; o restante cai em "Demais" (cauda longa).
    """
    return classificar_faixas(df, granularidade, campo="descricao", excluidos=None,
                               cortes=(corte_percentual,), nomes_grupos=["Grupo 1"])


def classificar_clientes_agregado(df, clientes_excluidos=None, cortes=(30.0, 50.0, 60.0), desconsiderar_balcao=False):
    """
    Classificação RÁPIDA (não por período) de cada cliente em um grupo, usando
    a receita agregada de todo o CSV como referência — pensada para a prévia
    na interface (a classificação "oficial" do relatório, por período, é
    feita por classificar_faixas/classificar_abc).

    Se desconsiderar_balcao=True, clientes tipo "consumidor final"/"balcão"
    (ver REGEX_BALCAO) ficam de fora do cálculo dos grupos e da curva
    acumulada, mas continuam na lista com Faixa="Balcão" e o % real de
    receita (não zerado) — só não entram na classificação Grupo 1/2/3/Demais.

    Retorna DataFrame: Cliente, Receita, Percentual_Individual,
    Percentual_Acumulado (NaN para linhas de Balcão), Faixa.
    """
    excluidos = set(clientes_excluidos or [])
    base = df[~df["Cliente"].isin(excluidos)] if excluidos else df

    if desconsiderar_balcao:
        mascara_balcao = base["Cliente"].str.contains(REGEX_BALCAO, na=False)
        base_normal = base[~mascara_balcao]
        base_balcao = base[mascara_balcao]
    else:
        base_normal = base
        base_balcao = pd.DataFrame(columns=base.columns)

    receita_normal = base_normal.groupby("Cliente")["Receita"].sum().sort_values(ascending=False)
    resultado = receita_normal.reset_index()
    resultado.columns = ["Cliente", "Receita"]
    total = resultado["Receita"].sum()
    resultado["Percentual_Individual"] = (resultado["Receita"] / total * 100) if total > 0 else 0.0
    resultado["Percentual_Acumulado"] = (resultado["Receita"].cumsum() / total * 100) if total > 0 else 0.0

    nomes_grupos = [f"Grupo {i + 1}" for i in range(len(cortes))] + ["Demais"]

    def faixa(percentual_acumulado):
        for corte, nome in zip(cortes, nomes_grupos):
            if percentual_acumulado <= corte:
                return nome
        return nomes_grupos[-1]

    resultado["Faixa"] = resultado["Percentual_Acumulado"].apply(faixa)

    frequencia_normal = (
        base_normal[base_normal["Receita"] > 0].groupby("Cliente")["Periodo_Mensal"].nunique().rename("Frequencia")
    )
    resultado = resultado.merge(frequencia_normal, on="Cliente", how="left")
    resultado["Frequencia"] = resultado["Frequencia"].fillna(0).astype(int)

    if not base_balcao.empty:
        # Balcão fica de fora da classificação em grupos (por isso o corte é
        # calculado só com base_normal), mas o % individual mostrado é real
        # — não faz sentido excluir da conta E mentir que a receita é 0.
        # Fica sempre na faixa "Balcão", nunca misturado com "Grupo 1" (que
        # deve refletir só quem participa de fato da segmentação por receita).
        receita_balcao = base_balcao.groupby("Cliente")["Receita"].sum().sort_values(ascending=False).reset_index()
        receita_balcao.columns = ["Cliente", "Receita"]
        receita_balcao["Percentual_Individual"] = (receita_balcao["Receita"] / total * 100) if total > 0 else 0.0
        receita_balcao["Percentual_Acumulado"] = float("nan")
        receita_balcao["Faixa"] = "Balcão"
        receita_balcao["Frequencia"] = 0
        resultado = pd.concat([receita_balcao, resultado], ignore_index=True)

    return resultado


def classificar_produtos_agregado(df, corte_percentual=80.0, clientes_excluidos=None):
    """
    Classificação RÁPIDA (não por período) de cada produto em "Grupo 1"
    (top corte_percentual% da receita) ou "Demais", com a participação na
    receita: apesar do nome das colunas (Freq_Simples/Freq_Acumulado,
    mantidos por compatibilidade — a tela já mostra "% Receita"/"% Receita
    Acumulada", os rótulos certos), NÃO é frequência de compra nenhuma —
    Freq_Simples é o % individual daquele produto na receita total,
    Freq_Acumulado é o % acumulado (curva de Pareto/ABC — mesmo valor que
    decide a Faixa). Pensada para a prévia na interface — ver
    classificar_produtos_por_receita para a versão por período usada no
    relatório final.

    clientes_excluidos: mesma lista de "Clientes a excluir das métricas" da
    tela — sem isso, a % de receita de cada produto incluía a compra de
    clientes que o usuário já tirou da análise em todo o resto do sistema.
    """
    base = df[~df["Cliente"].isin(set(clientes_excluidos))] if clientes_excluidos else df
    receita_produto = base.groupby("descricao")["Receita"].sum().sort_values(ascending=False)
    resultado = receita_produto.reset_index()
    resultado.columns = ["descricao", "Receita"]
    total = resultado["Receita"].sum()
    resultado["Freq_Simples"] = (resultado["Receita"] / total * 100) if total > 0 else 0.0
    resultado["Freq_Acumulado"] = resultado["Freq_Simples"].cumsum() if total > 0 else 0.0
    resultado["Faixa"] = resultado["Freq_Acumulado"].apply(lambda p: "Grupo 1" if p <= corte_percentual else "Demais")
    return resultado


def contar_clientes_por_grupo(df, clientes_excluidos=None, cortes=(30.0, 50.0, 60.0), desconsiderar_balcao=False):
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

    if desconsiderar_balcao:
        mascara_balcao = base["Cliente"].str.contains(REGEX_BALCAO, na=False)
        base_normal = base[~mascara_balcao]
    else:
        base_normal = base

    receita_cliente = base_normal.groupby("Cliente")["Receita"].sum().sort_values(ascending=False)
    total = receita_cliente.sum()

    if total <= 0 or receita_cliente.empty:
        contagens = [0] * (len(cortes) + 1)
    else:
        percentual_acumulado = receita_cliente.cumsum() / total * 100
        contagens = []
        limite_inferior = 0.0
        for corte in cortes:
            contagens.append(int(((percentual_acumulado > limite_inferior) & (percentual_acumulado <= corte)).sum()))
            limite_inferior = corte
        contagens.append(int((percentual_acumulado > limite_inferior).sum()))

    return contagens


def sugerir_cortes_grupos(df, clientes_excluidos=None, cortes_iniciais=(30.0, 50.0, 60.0),
                           max_por_grupo=10, passo=0.5, desconsiderar_balcao=False):
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

    if desconsiderar_balcao:
        mascara_balcao = base["Cliente"].str.contains(REGEX_BALCAO, na=False)
        base_normal = base[~mascara_balcao]
    else:
        base_normal = base

    receita_cliente = base_normal.groupby("Cliente")["Receita"].sum().sort_values(ascending=False)
    total = receita_cliente.sum()

    cortes = list(cortes_iniciais)
    if total <= 0 or receita_cliente.empty:
        contagens = [0] * (len(cortes) + 1)
        return cortes, contagens

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

    # "Balcão" nunca entra nessa hierarquia: é uma categoria à parte (fora da
    # segmentação por Pareto — ver classificar_faixas), não um degrau entre
    # Grupo 3 e Demais. Sem excluir aqui, "Balcão" ganhava uma posição na
    # ordem_faixa (entre Demais e o último Grupo) — na prática inofensivo,
    # porque a condição de balcão de um cliente não muda de período pra
    # período (então nunca aparece um "de"/"para" misturando Balcão com
    # outra faixa), mas conceitualmente errado e um risco se isso um dia
    # deixar de ser verdade.
    faixas_em_ordem = [f for f in abc_df["Faixa_ABC"].unique() if f not in ("Demais", "Balcão")]
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
            if de == para or de == "Balcão" or para == "Balcão":
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


def resumo_migracao(migracao_df):
    """
    Uma linha por transição de período, com a contagem de clientes que
    subiram vs. desceram de faixa nela — visão executiva rápida (ver
    migracao_abc para o detalhe por cliente). Margem = Qtd_Subiu -
    Qtd_Desceu: positiva quando mais clientes subiram do que desceram
    nessa transição, negativa no caso contrário.
    """
    colunas = ["Periodo_Anterior", "Periodo_Atual", "Qtd_Subiu", "Qtd_Desceu", "Margem"]
    if migracao_df.empty:
        return pd.DataFrame(columns=colunas)

    resumo = (
        migracao_df.groupby(["Periodo_Anterior", "Periodo_Atual", "Direcao"])
        .size().unstack(fill_value=0).reset_index()
    )
    for direcao in ("Subiu", "Desceu"):
        if direcao not in resumo.columns:
            resumo[direcao] = 0
    resumo.rename(columns={"Subiu": "Qtd_Subiu", "Desceu": "Qtd_Desceu"}, inplace=True)
    resumo["Margem"] = resumo["Qtd_Subiu"] - resumo["Qtd_Desceu"]
    return resumo[colunas]


PONTOS_SUBIU_FAIXA = 2
PONTOS_DESCEU_FAIXA = -3


def pontuacao_migracao_clientes(migracao_df, abc_df, granularidade="Mensal"):
    """
    Score de migração por cliente, acumulado ao longo de TODO o histórico de
    transições disponível (não só a mais recente): +2 por subida de faixa,
    -3 por queda — queda pesa mais que subida, então clientes que oscilam
    (sobe e cai) tendem a score negativo, não neutro.

    Percentual_Permanencia: das transições de período em que o cliente
    aparece nos dois lados (a mesma base contada por migracao_abc), qual %
    ele NÃO migrou de faixa. 100% = nunca mudou de faixa desde que aparece
    na base.

    Grupo: faixa ABC do cliente no período mais recente em que aparece na
    base (não a faixa "no auge" nem a mais frequente — onde ele está AGORA).
    """
    colunas = ["Cliente", "Qtd_Subiu", "Qtd_Desceu", "Score", "Percentual_Permanencia", "Grupo"]
    if abc_df.empty:
        return pd.DataFrame(columns=colunas)

    if migracao_df.empty:
        # Índice nomeado "Cliente" mesmo vazio — sem isso, o merge abaixo
        # (on="Cliente") quebra com KeyError quando não há NENHUMA migração
        # no período (comum em granularidades com poucos pontos, ex.: Anual).
        contagem_migracoes = pd.DataFrame(columns=["Subiu", "Desceu"], index=pd.Index([], name="Cliente"))
    else:
        contagem_migracoes = migracao_df.groupby(["Cliente", "Direcao"]).size().unstack(fill_value=0)
    for direcao in ("Subiu", "Desceu"):
        if direcao not in contagem_migracoes.columns:
            contagem_migracoes[direcao] = 0

    # "Oportunidades de migrar" por cliente = nº de PARES DE PERÍODOS
    # CONSECUTIVOS (na ordem cronológica) em que ele aparece nos dois lados
    # — a mesma regra usada por migracao_abc. Não é simplesmente "nº de
    # períodos em que aparece menos 1": um cliente que compra em ago/25 e só
    # volta em dez/25 (pulando set/out/nov) tem 2 períodos, mas ZERO pares
    # consecutivos reais — "nunique - 1" superestimaria as oportunidades e
    # inflaria Percentual_Permanencia pra quem tem histórico "com buracos".
    periodos_ordenados = _ordenar_periodos(abc_df["Periodo"].unique(), granularidade)
    ordem_periodo = {periodo: indice for indice, periodo in enumerate(periodos_ordenados)}

    def _pares_consecutivos(periodos_do_cliente):
        indices = sorted(ordem_periodo[p] for p in periodos_do_cliente)
        return sum(1 for anterior, atual in zip(indices, indices[1:]) if atual - anterior == 1)

    transicoes_por_cliente = abc_df.groupby("Cliente")["Periodo"].apply(
        lambda serie: _pares_consecutivos(serie.unique())
    )

    resultado = transicoes_por_cliente.rename("Transicoes").reset_index()
    resultado = resultado.merge(
        contagem_migracoes[["Subiu", "Desceu"]].reset_index(), on="Cliente", how="left"
    )
    resultado[["Subiu", "Desceu"]] = resultado[["Subiu", "Desceu"]].fillna(0).astype(int)
    resultado["Score"] = resultado["Subiu"] * PONTOS_SUBIU_FAIXA + resultado["Desceu"] * PONTOS_DESCEU_FAIXA

    migracoes_totais = resultado["Subiu"] + resultado["Desceu"]
    resultado["Percentual_Permanencia"] = np.where(
        resultado["Transicoes"] > 0,
        (resultado["Transicoes"] - migracoes_totais) / resultado["Transicoes"] * 100,
        100.0,
    )

    resultado.rename(columns={"Subiu": "Qtd_Subiu", "Desceu": "Qtd_Desceu"}, inplace=True)

    faixa_mais_recente = abc_df.sort_values("Periodo").groupby("Cliente")["Faixa_ABC"].last()
    resultado["Grupo"] = resultado["Cliente"].map(faixa_mais_recente).fillna("-")

    resultado = resultado[colunas]
    resultado.sort_values("Score", ascending=False, inplace=True)
    resultado.reset_index(drop=True, inplace=True)
    return resultado


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
    Heurísticas para explicar a migração de faixa, usando os agregados
    pré-calculados em `contexto` (ver _preparar_contexto_causa_provavel) em
    vez de refiltrar o DataFrame. Critérios propositalmente rígidos: só
    retorna uma causa quando uma regra bate com folga (limiares bem acima do
    "só um pouco mais que zero"); caso contrário retorna string vazia — não
    força um "Caso Específico"/genérico só para preencher a célula. Sem
    linguagem de "estimativa": o que aparece aqui é apresentado como fato,
    não como palpite hedgeado.
    """
    chave_anterior = (cliente, periodo_anterior)
    chave_atual = (cliente, periodo_atual)

    receita_anterior = contexto["receita"].get(chave_anterior, 0.0)
    receita_atual = contexto["receita"].get(chave_atual, 0.0)

    if receita_atual == 0:
        return "Cliente parou de comprar no período atual."

    # Produto abandonado respondia por boa parte da receita (>=70%, não 40%)
    produtos_anterior = contexto["produtos"].get(chave_anterior, set())
    produtos_atual = contexto["produtos"].get(chave_atual, set())
    produtos_abandonados = produtos_anterior - produtos_atual
    if direcao == "Desceu" and produtos_abandonados:
        receita_produtos_abandonados = sum(
            contexto["receita_produto"].get((cliente, periodo_anterior, produto), 0.0)
            for produto in produtos_abandonados
        )
        if receita_anterior > 0 and receita_produtos_abandonados / receita_anterior >= 0.7:
            principal = ", ".join(list(produtos_abandonados)[:3])
            return f"Deixou de comprar produto(s) que respondiam por {receita_produtos_abandonados / receita_anterior * 100:.0f}% da receita anterior ({principal})."

    # Frequência de compra caiu pela metade ou mais (não só "caiu um pouco")
    meses_anterior = contexto["meses"].get(chave_anterior, 0)
    meses_atual = contexto["meses"].get(chave_atual, 0)
    if direcao == "Desceu" and meses_anterior > 0 and (meses_anterior - meses_atual) / meses_anterior >= 0.5:
        return f"Redução de pelo menos metade na frequência de compra ({meses_anterior} período(s) com compra antes, {meses_atual} depois)."

    # Ticket médio caiu 40%+ mantendo os mesmos produtos (não só 20%)
    qtd_anterior = contexto["qtd"].get(chave_anterior, 0)
    qtd_atual = contexto["qtd"].get(chave_atual, 0)
    ticket_anterior = receita_anterior / qtd_anterior if qtd_anterior else 0
    ticket_atual = receita_atual / qtd_atual if qtd_atual else 0
    if direcao == "Desceu" and ticket_anterior > 0 and ticket_atual <= ticket_anterior * 0.6:
        return f"Redução de {(1 - ticket_atual / ticket_anterior) * 100:.0f}% no ticket médio mantendo os mesmos produtos."

    if direcao == "Subiu":
        produtos_novos = produtos_atual - produtos_anterior
        if produtos_novos:
            receita_produtos_novos = sum(
                contexto["receita_produto"].get((cliente, periodo_atual, produto), 0.0)
                for produto in produtos_novos
            )
            if receita_atual > 0 and receita_produtos_novos / receita_atual >= 0.5:
                principal = ", ".join(list(produtos_novos)[:3])
                return f"Novo(s) produto(s) já respondem por {receita_produtos_novos / receita_atual * 100:.0f}% da receita atual ({principal})."

    return ""


# ---------------------------------------------------------------------------
# Orquestração: gera todas as análises para um conjunto de granularidades
# ---------------------------------------------------------------------------

def gerar_analises_completas(df, granularidades, clientes_excluidos=None,
                              cortes_clientes=(30.0, 50.0, 60.0), corte_produtos=80.0,
                              periodos_queda_consecutiva=2, callback_log=None, chaves_solicitadas=None,
                              desconsiderar_balcao=False, excluir_periodo_atual=True,
                              top_n_produtos=None, reducao_minima_erosao=50.0, queda_minima_alerta=0.0,
                              queda_minima_erosao_reais=0.0, reducao_minima_sem_venda=90.0, top_n_poder_compra=None):
    """
    Roda as análises solicitadas para cada granularidade escolhida.

    chaves_solicitadas: conjunto/lista de chaves do catálogo a calcular (ex.:
    {"top_produtos", "migracao_abc"}). Se None, calcula tudo. Análises caras
    (como migração entre faixas, que precisa da segmentação ABC) só rodam se
    pedidas — ou se outra análise pedida depender delas — evitando gastar
    tempo em algo que não vai para o relatório final. Com bases grandes
    (centenas de milhares de linhas), isso faz diferença real no tempo total.

    excluir_periodo_atual: por padrão, o período mais recente de cada
    granularidade é descartado antes de rodar qualquer análise "por
    período" (o mês/trimestre/etc. corrente costuma estar incompleto na
    base). Não afeta top_produtos/top_fabricantes, que somam a base inteira
    e não fatiam por período.

    top_n_produtos: limite de produtos em alertas_queda
    (None = todos — ver tendencia_produtos). reducao_minima_erosao: % mínimo
    de queda para um cliente aparecer em erosao_clientes (ver
    erosao_clientes_por_produto).

    callback_log: função opcional callback_log(mensagem) chamada a cada etapa
    concluída, para permitir feedback de progresso na interface.

    Retorna um dicionário: { granularidade: { nome_analise: DataFrame } }
    (só contém as chaves efetivamente calculadas).
    """
    def logar(mensagem):
        if callback_log:
            callback_log(mensagem)

    todas_as_chaves = {
        "top_produtos", "poder_compra_clientes",
        "alertas_queda", "erosao_clientes", "erosao_geral", "sem_venda", "alto_giro", "abc", "abc_produtos",
        "migracao_abc", "migracao_resumo", "migracao_score_clientes",
        "produtos_em_alta", "produtos_em_queda", "clientes_queda_qtd",
        "correlacao_produto_cliente", "impacto_financeiro_churn",
    }
    pedidas = todas_as_chaves if chaves_solicitadas is None else set(chaves_solicitadas)

    def precisa(*chaves):
        return any(chave in pedidas for chave in chaves)

    # Resolve dependências entre análises (ex.: migração depende da
    # segmentação ABC completa, não do recorte top-5 exibido no relatório;
    # correlação e impacto de churn dependem da erosão de clientes) para
    # nunca pular um cálculo que outro item pedido ainda precisa, mas também
    # nunca calcular o que ninguém pediu.
    precisa_tendencia = precisa("alertas_queda", "erosao_clientes", "correlacao_produto_cliente")
    precisa_erosao = precisa("erosao_clientes", "correlacao_produto_cliente", "impacto_financeiro_churn")
    precisa_migracao = precisa("migracao_abc", "migracao_resumo", "migracao_score_clientes")
    precisa_abc = precisa("abc") or precisa_migracao

    # Ponto único de exclusão de clientes: antes, só classificar_abc e
    # poder_compra_agregado recebiam clientes_excluidos — todo o resto
    # (Alertas de Queda, Erosão, Alto Giro, Top Produtos, etc.) usava o df
    # inteiro, então um cliente excluído "das métricas" continuava aparecendo
    # (ex.: como Cliente Destaque no Alto Giro, ou puxando receita no Top
    # Produtos). Filtrar aqui, uma única vez, garante que a exclusão valha
    # igual em toda análise gerada a partir de df/df_periodo.
    if clientes_excluidos:
        df = df[~df["Cliente"].isin(set(clientes_excluidos))]

    resultados = {}
    for granularidade in granularidades:
        analises = {}

        col_periodo = COLUNA_PERIODO[granularidade]
        periodos_ordenados = _ordenar_periodos(df[col_periodo].unique(), granularidade)
        if excluir_periodo_atual and len(periodos_ordenados) > 1:
            df_periodo = df[df[col_periodo] != periodos_ordenados[-1]]
            logar(f"[{granularidade}] Período mais recente ({periodos_ordenados[-1]}) excluído por padrão (provavelmente incompleto).")
        else:
            df_periodo = df

        evolucao, alertas = (None, None)
        if precisa_tendencia:
            logar(f"[{granularidade}] Calculando tendência de produtos...")
            evolucao, alertas = tendencia_produtos(
                df_periodo, granularidade, periodos_queda_consecutiva, top_n=top_n_produtos,
                queda_minima_reais=queda_minima_alerta,
            )
            if precisa("alertas_queda"):
                analises["alertas_queda"] = alertas

        erosao = None
        if precisa_erosao:
            logar(f"[{granularidade}] Calculando erosão de clientes por produto...")
            erosao = erosao_clientes_por_produto(
                df_periodo,
                reducao_minima_percentual=reducao_minima_erosao,
                queda_minima_reais=queda_minima_erosao_reais,
            )
            if precisa("erosao_clientes"):
                # "Periodo" (mês atual) é sempre o mesmo valor em toda linha
                # — não é uma coluna útil aqui, mesmo motivo de Alertas de
                # Queda não ter "Período Atual". Fica só internamente (usado
                # por correlacao_produto_cliente pra agrupar por período).
                analises["erosao_clientes"] = erosao.rename(columns={
                    "Periodo_Pico": "Período do Pico",
                    "Receita_Periodo_Anterior": "Receita no Pico",
                    "Receita": "Receita Atual",
                    "Reducao_Receita": "Queda em R$",
                    "Reducao_Percentual": "% de Queda",
                    "Parou_De_Comprar": "Parou de Comprar",
                }).drop(columns=["Periodo"])

        if precisa("erosao_geral"):
            logar(f"[{granularidade}] Calculando erosão geral de clientes (todos os produtos)...")
            erosao_geral = erosao_clientes_geral(
                df_periodo,
                reducao_minima_percentual=reducao_minima_erosao,
                queda_minima_reais=queda_minima_erosao_reais,
            )
            # Mesmo motivo de erosao_clientes: "Periodo" é sempre o mesmo
            # valor em toda linha, não é uma coluna útil aqui.
            analises["erosao_geral"] = erosao_geral.rename(columns={
                "Periodo_Pico": "Período do Pico",
                "Receita_Periodo_Anterior": "Receita no Pico",
                "Receita": "Receita Atual",
                "Reducao_Receita": "Queda em R$",
                "Reducao_Percentual": "% de Queda",
                "Parou_De_Comprar": "Parou de Comprar",
            }).drop(columns=["Periodo"])

        if precisa("sem_venda"):
            logar(f"[{granularidade}] Calculando clientes sem venda (praticamente pararam de comprar)...")
            analises["sem_venda"] = sem_venda(
                df_periodo,
                reducao_minima_percentual=reducao_minima_sem_venda,
                cortes=cortes_clientes,
                desconsiderar_balcao=desconsiderar_balcao,
            )

        if precisa("alto_giro"):
            logar(f"[{granularidade}] Calculando status de alto giro...")
            # Alto Giro reflete só o comportamento dos clientes mais importantes
            # (Grupo 1 da classificação agregada, mesmo corte usado em Poder de
            # Compra/Sem Venda/prévia de Configurações) — um produto de alto giro
            # sustentado por clientes menores não deve aparecer "em alta" por
            # causa deles; o que importa aqui é a carteira principal.
            #
            # A classificação usa SEMPRE o "df" completo (todo o histórico, sem
            # excluir o período mais recente) — não o "df_periodo" já filtrado
            # logo abaixo — porque quem é Grupo 1 é uma pergunta sobre a receita
            # TOTAL do cliente, igual à prévia de Configurações; calcular sobre
            # uma fatia menor (sem o último mês) muda o ranking e pode incluir/
            # excluir cliente perto do corte por pouco, divergindo do que o
            # usuário vê e valida na tela de Configurações.
            classificacao_grupo1 = classificar_clientes_agregado(
                df, cortes=cortes_clientes, desconsiderar_balcao=desconsiderar_balcao,
            )
            clientes_grupo1 = set(classificacao_grupo1.loc[classificacao_grupo1["Faixa"] == "Grupo 1", "Cliente"])
            mapa_faixa_cliente = dict(zip(classificacao_grupo1["Cliente"], classificacao_grupo1["Faixa"]))
            # Grupo 1 vale pra receita/status do produto — Cliente Destaque/Em
            # Queda usam todos os clientes, priorizando Grupo 1 > 2 > 3 > demais
            # (ver docstring de status_alto_giro).
            analises["alto_giro"] = status_alto_giro(
                df_periodo, desconsiderar_balcao=desconsiderar_balcao,
                clientes_grupo1=clientes_grupo1, mapa_faixa_cliente=mapa_faixa_cliente,
            ).rename(columns={
                "Receita_Atual": "Receita Atual",
                "Variacao_Percentual": "% de Variação",
                "Cliente_Destaque": "Cliente Destaque",
                "Variacao_Percentual_Cliente_Destaque": "% Variação do Cliente Destaque",
                "Cliente_Em_Queda": "Cliente em Queda",
                "Variacao_Percentual_Cliente_Em_Queda": "% Variação do Cliente em Queda",
            })

        abc = None
        if precisa_abc:
            logar(f"[{granularidade}] Classificando clientes por faixa de faturamento...")
            # Sempre sem corte aqui (top_clientes_por_grupo=None): migração
            # precisa ver TODOS os clientes pra detectar corretamente quem
            # mudou de faixa. O corte "top 5" é aplicado só na hora de expor
            # a chave "abc" do relatório, não na classificação em si.
            abc = classificar_abc(
                df_periodo, granularidade, clientes_excluidos, cortes_clientes,
                desconsiderar_balcao=desconsiderar_balcao, top_clientes_por_grupo=None,
            )
            if precisa("abc"):
                analises["abc"] = _limitar_top_por_grupo(abc, 5)

        if precisa("poder_compra_clientes"):
            logar(f"[{granularidade}] Calculando poder de compra agregado dos clientes...")
            analises["poder_compra_clientes"] = poder_compra_agregado(
                df_periodo, clientes_excluidos, cortes_clientes, desconsiderar_balcao=desconsiderar_balcao,
                top_n=top_n_poder_compra,
            ).drop(columns=["Percentual_Acumulado"]).rename(columns={
                "Receita_Media_Recente": "Receita Média Recente (3 meses)",
                "Desempenho_Vs_Potencial_Pct": "% de Variação vs. Potencial",
                "Meses_60pct_Abaixo_Potencial": "Meses Muito Abaixo do Potencial",
            })

        if precisa("abc_produtos"):
            logar(f"[{granularidade}] Classificando produtos por faixa de faturamento...")
            analises["abc_produtos"] = classificar_produtos_por_receita(df_periodo, granularidade, corte_produtos)

        if precisa_migracao:
            logar(f"[{granularidade}] Calculando migração de clientes entre faixas...")
            migracao = migracao_abc(df_periodo, abc, granularidade)
            if precisa("migracao_abc"):
                analises["migracao_abc"] = migracao
                # Resumo e score não têm checkbox próprio no catálogo — são
                # subprodutos automáticos sempre que "migracao_abc" é pedido.
                analises["migracao_resumo"] = resumo_migracao(migracao)
                analises["migracao_score_clientes"] = pontuacao_migracao_clientes(migracao, abc, granularidade)

        if precisa("produtos_em_alta", "produtos_em_queda"):
            logar(f"[{granularidade}] Montando boletim de produtos em alta/queda...")
            produtos_alta, produtos_queda = produtos_alta_e_queda(df_periodo, granularidade)
            if precisa("produtos_em_alta"):
                analises["produtos_em_alta"] = produtos_alta
            if precisa("produtos_em_queda"):
                analises["produtos_em_queda"] = produtos_queda

        if precisa("clientes_queda_qtd"):
            logar(f"[{granularidade}] Montando boletim de clientes em queda de quantidade...")
            analises["clientes_queda_qtd"] = clientes_queda_quantidade(df_periodo, granularidade)

        if precisa("correlacao_produto_cliente"):
            logar(f"[{granularidade}] Calculando correlação produto x cliente...")
            analises["correlacao_produto_cliente"] = correlacao_produto_cliente(df_periodo, erosao, alertas, granularidade)

        if precisa("impacto_financeiro_churn"):
            logar(f"[{granularidade}] Calculando impacto financeiro do churn...")
            analises["impacto_financeiro_churn"] = impacto_financeiro_churn(df_periodo, erosao, granularidade)

        if precisa("top_produtos"):
            analises["top_produtos"] = top_produtos(df)

        resultados[granularidade] = analises
        logar(f"[{granularidade}] Concluído.")
    return resultados
