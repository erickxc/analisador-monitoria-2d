"""
Erosão de clientes (por produto e geral), "Sem Venda", boletim de queda de
quantidade e os relatórios executivos de correlação/impacto financeiro de
churn que consomem os resultados de erosão.
"""

import numpy as np
import pandas as pd

from classificacao import classificar_clientes_agregado, classificar_faixas
from nucleo_analise import COLUNA_PERIODO, _formatar_rotulo_periodo, _ordenar_periodos

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


def _cortes_com_minimo_por_grupo(percentual_acumulado, cortes_iniciais, minimo_por_grupo, passo=0.5):
    """
    Alarga os cortes percentuais cumulativos (nunca reduz abaixo do
    configurado) até garantir pelo menos minimo_por_grupo entidades em cada
    faixa, usando um Percentual_Acumulado já calculado (de um período
    específico) — o inverso de sugerir_cortes_grupos (que reduz até um
    MÁXIMO por grupo); aqui é o piso mínimo que importa. Nunca ultrapassa
    99% (sempre sobra alguém pra "Demais"). Motivo de existir: aplicar os
    MESMOS cortes % configurados pro período atual a um período histórico
    muito diferente (poucos clientes ativos, receita concentrada de outro
    jeito) pode deixar uma faixa vazia ou com 1-2 clientes só — sem
    comparação nenhuma com "10 clientes no Grupo 1 de hoje".
    """
    cortes = []
    limite_inferior = 0.0
    for corte_original in cortes_iniciais:
        corte = max(corte_original, limite_inferior)
        while True:
            quantidade = int(((percentual_acumulado > limite_inferior) & (percentual_acumulado <= corte)).sum())
            if quantidade >= minimo_por_grupo or corte >= 99.0:
                break
            corte += passo
        corte = round(min(corte, 99.0), 1)
        cortes.append(corte)
        limite_inferior = corte
    return cortes


def _faixa_por_corte(percentual, cortes, nomes_grupos):
    for corte, nome in zip(cortes, nomes_grupos):
        if percentual <= corte:
            return nome
    return nomes_grupos[-1]


def sem_venda(df, reducao_minima_percentual=90.0, cortes=(30.0, 50.0, 60.0), desconsiderar_balcao=False,
              df_para_grupo=None, minimo_clientes_por_grupo=10):
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
    classificar_clientes_agregado — não pelo poder de compra), Grupo 11
    Meses (faixa do cliente no primeiro período disponível na base — a base
    é sempre uma janela corrida dos últimos 11 meses, então este é
    literalmente "de onde ele partiu"), Grupo no Pico (faixa do cliente no
    mês do seu próprio pico de receita — não um período fixo, varia por
    cliente), Receita no Pico, e uma coluna por mês disponível na base
    (rótulo legível, ex. "ago/25") — ordenado por Receita no Pico
    descendente (maior potencial perdido primeiro).

    Grupo vem de classificar_clientes_agregado (percentuais fixos
    configurados, igual a todo o resto do sistema). Grupo 11 Meses/Grupo no
    Pico vêm de uma classificação POR PERÍODO (classificar_faixas) com os
    cortes % ALARGADOS especificamente pra aquele período — ver
    _cortes_com_minimo_por_grupo — pra garantir pelo menos
    minimo_clientes_por_grupo entidades em cada faixa mesmo quando a
    receita daquele período histórico não se parece em nada com a atual
    (poucos clientes ativos, receita concentrada diferente). "-" quando o
    cliente não tem uma linha classificada no período em questão.

    df_para_grupo: base alternativa usada SÓ para calcular Grupo/Grupo 11
    Meses/Grupo no Pico (None = usa o próprio `df`). Existe porque `df` pode
    já vir filtrado por "somente produtos de alto giro" — Grupo deve
    refletir a receita total do cliente independente desse filtro.
    """
    colunas_vazias = ["Cliente", "Grupo", "Grupo 11 Meses", "Grupo no Pico", "Receita no Pico"]
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

    base_grupo = df_para_grupo if df_para_grupo is not None else df
    classificacao = classificar_clientes_agregado(base_grupo, cortes=cortes, desconsiderar_balcao=desconsiderar_balcao)
    mapa_grupo = dict(zip(classificacao["Cliente"], classificacao["Faixa"]))
    mapa_pico = clientes_erosao.set_index("Cliente")["Receita_Periodo_Anterior"]

    # Grupo 11 Meses/Grupo no Pico: precisam da classificação POR PERÍODO
    # (classificar_faixas), não da agregada — "Grupo" sozinho só sabe o
    # presente; aqui é olhar pra trás, período a período.
    nomes_grupos = [f"Grupo {i + 1}" for i in range(len(cortes))] + ["Demais"]
    faixas_periodo = classificar_faixas(base_grupo, "Mensal", campo="Cliente", cortes=cortes, desconsiderar_balcao=desconsiderar_balcao)

    def faixas_do_periodo_com_minimo(periodo_raw):
        """Reclassifica todo mundo daquele período com cortes alargados pra
        garantir minimo_clientes_por_grupo — retorna {Cliente: Faixa_ABC}."""
        linhas = faixas_periodo[faixas_periodo["Periodo"] == periodo_raw]
        if linhas.empty:
            return {}
        cortes_ajustados = _cortes_com_minimo_por_grupo(
            linhas["Percentual_Acumulado"], cortes, minimo_clientes_por_grupo,
        )
        faixas_ajustadas = linhas["Percentual_Acumulado"].apply(
            lambda p: _faixa_por_corte(p, cortes_ajustados, nomes_grupos)
        )
        return dict(zip(linhas["Cliente"], faixas_ajustadas))

    # "Primeiro período" tem que vir da MESMA base usada pro Grupo atual
    # (base_grupo — a base carregada na análise, sem o corte de alto giro),
    # não de `periodos_ordenados` (que é sobre `df`, podendo já estar
    # filtrado por alto giro): só a base carregada sabe de verdade qual foi
    # o primeiro mês da janela de 11 meses — um filtro de produto pode
    # começar depois do início real dos dados, dando um "primeiro período"
    # que não é o primeiro de verdade.
    periodos_ordenados_grupo = _ordenar_periodos(base_grupo["Periodo_Mensal"].unique(), "Mensal")
    mapa_grupo_11_meses = (
        faixas_do_periodo_com_minimo(periodos_ordenados_grupo[0]) if periodos_ordenados_grupo else {}
    )

    # Periodo_Pico (em clientes_erosao) já vem formatado como rótulo (ex.
    # "ago/25"); precisa do período BRUTO correspondente pra reclassificar
    # com cortes alargados naquele período específico — os rótulos são
    # únicos dentro da janela de ~11 meses (sem repetir mês/ano), então dá
    # pra inverter o mapa rótulo->bruto com segurança.
    rotulo_para_periodo_raw = {
        _formatar_rotulo_periodo(p, "Mensal"): p for p in periodos_ordenados_grupo
    }
    mapa_periodo_pico = clientes_erosao.set_index("Cliente")["Periodo_Pico"]
    cache_faixas_por_periodo = {}

    def grupo_no_pico(cliente):
        periodo_pico_rotulo = mapa_periodo_pico.get(cliente)
        periodo_pico_raw = rotulo_para_periodo_raw.get(periodo_pico_rotulo) if periodo_pico_rotulo else None
        if periodo_pico_raw is None:
            return "-"
        if periodo_pico_raw not in cache_faixas_por_periodo:
            cache_faixas_por_periodo[periodo_pico_raw] = faixas_do_periodo_com_minimo(periodo_pico_raw)
        return cache_faixas_por_periodo[periodo_pico_raw].get(cliente, "-")

    resultado = pivot.reset_index()
    resultado.insert(1, "Grupo", resultado["Cliente"].map(mapa_grupo).fillna("-"))
    resultado.insert(2, "Grupo 11 Meses", resultado["Cliente"].map(mapa_grupo_11_meses).fillna("-"))
    resultado.insert(3, "Grupo no Pico", resultado["Cliente"].map(grupo_no_pico))
    resultado.insert(4, "Receita no Pico", resultado["Cliente"].map(mapa_pico))
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
