"""
Relatórios de produto: top produtos, poder de compra, tendência de
produtos/alertas de queda consecutiva, boletim de alta/queda e Alto Giro.
"""

import numpy as np
import pandas as pd

from classificacao import classificar_clientes_agregado
from nucleo_analise import COLUNA_PERIODO, REGEX_BALCAO, _formatar_rotulo_periodo, _ordenar_periodos

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
