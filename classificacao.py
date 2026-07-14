"""
Classificação de clientes/produtos em faixas por representatividade no
faturamento (curva de Pareto/ABC) — versão por período (a "oficial", usada
pelo relatório final e pela migração de grupo) e versões agregadas rápidas
(usadas na prévia da tela de Configurações).
"""

import numpy as np
import pandas as pd

from nucleo_analise import COLUNA_PERIODO, REGEX_BALCAO, _ordenar_periodos

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
