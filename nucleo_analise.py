"""
Núcleo do motor de análise: constantes de domínio, carregamento/limpeza do
CSV e helpers de período usados por todos os outros módulos de análise.

Sem dependência de GUI - pode ser testado isoladamente via linha de comando
ou testes automatizados. Todas as funções recebem/retornam DataFrames do pandas.
"""

import re

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constantes de domínio
# ---------------------------------------------------------------------------

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
