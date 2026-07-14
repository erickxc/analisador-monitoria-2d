"""
Migração de clientes entre faixas ABC (mudança de grupo período a período),
placar de pontuação acumulado por cliente, boletim de mobilidade de carteira
e a heurística de "causa provável" que explica cada migração.
"""

import pandas as pd

from classificacao import classificar_faixas
from nucleo_analise import COLUNA_PERIODO, _ordenar_periodos

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

    Meses_No_Grupo_Atual: sequência de períodos MAIS RECENTES e CONSECUTIVOS
    (sem buraco no calendário) em que o cliente ficou na mesma faixa em que
    está agora — não é média/proporção do histórico inteiro (isso mistura
    fases completamente diferentes: um cliente que passou o ano oscilando
    entre Grupo 2/3/Demais e só emplacou no Grupo 1 nos 2 últimos meses deve
    mostrar "2", não uma média arrastando o passado). Para de contar no
    primeiro período com faixa diferente OU no primeiro buraco no calendário
    (cliente ausente numa transição) — o mesmo critério de "transição real"
    usado em Transicoes/migracao_abc.

    Grupo: faixa ABC do cliente no período mais recente em que aparece na
    base (não a faixa "no auge" nem a mais frequente — onde ele está AGORA).
    """
    colunas = ["Cliente", "Qtd_Subiu", "Qtd_Desceu", "Score", "Meses_No_Grupo_Atual", "Grupo"]
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

    def _meses_no_grupo_atual(sub_df):
        pares = sorted((ordem_periodo[p], f) for p, f in zip(sub_df["Periodo"], sub_df["Faixa_ABC"]))
        if not pares:
            return 0
        faixa_atual = pares[-1][1]
        indice_esperado = pares[-1][0]
        contagem = 0
        for indice, faixa in reversed(pares):
            if faixa != faixa_atual or indice != indice_esperado:
                break
            contagem += 1
            indice_esperado -= 1
        return contagem

    meses_no_grupo_atual = abc_df.groupby("Cliente")[["Periodo", "Faixa_ABC"]].apply(_meses_no_grupo_atual)

    resultado = transicoes_por_cliente.rename("Transicoes").reset_index()
    resultado = resultado.merge(
        contagem_migracoes[["Subiu", "Desceu"]].reset_index(), on="Cliente", how="left"
    )
    resultado[["Subiu", "Desceu"]] = resultado[["Subiu", "Desceu"]].fillna(0).astype(int)
    resultado["Score"] = resultado["Subiu"] * PONTOS_SUBIU_FAIXA + resultado["Desceu"] * PONTOS_DESCEU_FAIXA
    resultado["Meses_No_Grupo_Atual"] = resultado["Cliente"].map(meses_no_grupo_atual)

    resultado.rename(columns={"Subiu": "Qtd_Subiu", "Desceu": "Qtd_Desceu"}, inplace=True)

    faixa_mais_recente = abc_df.sort_values("Periodo").groupby("Cliente")["Faixa_ABC"].last()
    resultado["Grupo"] = resultado["Cliente"].map(faixa_mais_recente).fillna("-")

    resultado = resultado[colunas]
    resultado.sort_values("Score", ascending=False, inplace=True)
    resultado.reset_index(drop=True, inplace=True)
    return resultado


def mobilidade_carteira(df, granularidade="Mensal", clientes_excluidos=None, cortes=(30.0, 50.0, 60.0),
                         desconsiderar_balcao=False, meses_permanencia_alerta=3):
    """
    Boletim executivo de mobilidade — quem subiu, desceu ou ficou estável de
    faixa na transição mais recente (não o histórico acumulado inteiro).
    Reaproveita migracao_abc() (hierarquia de faixas com a guarda de Balcão)
    e pontuacao_migracao_clientes() (Meses_No_Grupo_Atual) em vez de
    recalcular a mesma lógica — uma fonte de verdade só, a mesma da aba de
    Migração.

    Diferente do Score de pontuacao_migracao_clientes (somado desde o início
    do histórico), "ascensao"/"recuando" aqui usam sempre a ÚLTIMA transição
    de período disponível: um cliente que caiu de faixa há 6 meses mas está
    estável desde então não deve aparecer como "recuando" hoje — score
    histórico negativo não é risco atual (bug identificado num relatório
    anterior que misturava os dois e citava clientes estáveis como "risco
    alto").

    "Demais" não é uma faixa que importa monitorar por si só (não é
    carteira relevante) — só entram clientes com alguma faixa (anterior OU
    atual) em Grupo 1/2/3. Cair de Grupo 1 pra Demais é o caso mais grave de
    "recuando" (perde-se um cliente relevante), não um caso a ignorar por
    "ter caído pra Demais".

    Retorna dict com 4 DataFrames:
      - "ascensao": subiu de faixa na última transição, faixa atual em
        Grupo 1/2/3. "Chegou_Ao_G1_Agora" = True quando a faixa atual é
        Grupo 1 (o destaque mais forte de crescimento).
      - "recuando": desceu de faixa na última transição, faixa anterior em
        Grupo 1/2/3. "Risco_Alto" = True quando saiu do Grupo 1 (perdeu o
        cliente mais valioso da carteira, prioridade de contato).
      - "estaveis": sem mudança de faixa na última transição, faixa atual
        em Grupo 1/2/3 (migracao_abc não inclui quem não mudou de faixa —
        calculado aqui direto contra as duas faixas do período).
      - "atencao_permanencia": clientes com Meses_No_Grupo_Atual >=
        meses_permanencia_alerta numa faixa intermediária (Grupo 2/3, não
        o topo) — presos, candidatos a um plano de conta pra subir, não uma
        queda recente.
    """
    vazio_mov = pd.DataFrame(columns=["Cliente", "Faixa_Anterior", "Faixa_Atual"])
    vazio_permanencia = pd.DataFrame(columns=["Cliente", "Faixa_Atual", "Meses_No_Grupo_Atual"])
    if len(cortes) < 1:
        return {"ascensao": vazio_mov, "recuando": vazio_mov, "estaveis": vazio_mov,
                "atencao_permanencia": vazio_permanencia}

    abc_df = classificar_faixas(
        df, granularidade, campo="Cliente", excluidos=clientes_excluidos,
        cortes=cortes, desconsiderar_balcao=desconsiderar_balcao,
    )
    if abc_df.empty:
        return {"ascensao": vazio_mov, "recuando": vazio_mov, "estaveis": vazio_mov,
                "atencao_permanencia": vazio_permanencia}

    periodos_ordenados = _ordenar_periodos(abc_df["Periodo"].unique(), granularidade)
    if len(periodos_ordenados) < 2:
        return {"ascensao": vazio_mov, "recuando": vazio_mov, "estaveis": vazio_mov,
                "atencao_permanencia": vazio_permanencia}
    periodo_anterior, periodo_atual = periodos_ordenados[-2], periodos_ordenados[-1]

    nomes_grupos = [f"Grupo {i + 1}" for i in range(len(cortes))] + ["Demais"]
    faixas_relevantes = set(nomes_grupos[:-1])  # Grupo 1/2/3 — sem "Demais"
    faixas_intermediarias = set(nomes_grupos[1:-1])  # Grupo 2/3 — sem Grupo 1 nem Demais

    migracao_df = migracao_abc(df, abc_df, granularidade)
    ultima_transicao = migracao_df[
        (migracao_df["Periodo_Anterior"] == periodo_anterior) & (migracao_df["Periodo_Atual"] == periodo_atual)
    ]

    ascensao = ultima_transicao[
        (ultima_transicao["Direcao"] == "Subiu") & ultima_transicao["Faixa_Atual"].isin(faixas_relevantes)
    ][["Cliente", "Faixa_Anterior", "Faixa_Atual"]].copy()
    ascensao["Chegou_Ao_G1_Agora"] = ascensao["Faixa_Atual"].eq("Grupo 1")
    ascensao.sort_values(["Chegou_Ao_G1_Agora", "Cliente"], ascending=[False, True], inplace=True)
    ascensao.reset_index(drop=True, inplace=True)

    recuando = ultima_transicao[
        (ultima_transicao["Direcao"] == "Desceu") & ultima_transicao["Faixa_Anterior"].isin(faixas_relevantes)
    ][["Cliente", "Faixa_Anterior", "Faixa_Atual"]].copy()
    recuando["Risco_Alto"] = recuando["Faixa_Anterior"].eq("Grupo 1")
    recuando.sort_values(["Risco_Alto", "Cliente"], ascending=[False, True], inplace=True)
    recuando.reset_index(drop=True, inplace=True)

    # "Estáveis" não aparece em migracao_abc por design (só lista quem
    # mudou) — calculado direto contra as duas faixas do período, com a
    # mesma guarda de Balcão (nunca conta como "estável" relevante).
    faixa_anterior_map = abc_df[abc_df["Periodo"] == periodo_anterior].set_index("Cliente")["Faixa_ABC"]
    faixa_atual_map = abc_df[abc_df["Periodo"] == periodo_atual].set_index("Cliente")["Faixa_ABC"]
    clientes_comuns = faixa_anterior_map.index.intersection(faixa_atual_map.index)
    estaveis = pd.DataFrame({
        "Cliente": clientes_comuns,
        "Faixa_Anterior": faixa_anterior_map[clientes_comuns].values,
        "Faixa_Atual": faixa_atual_map[clientes_comuns].values,
    })
    estaveis = estaveis[
        (estaveis["Faixa_Anterior"] == estaveis["Faixa_Atual"]) & estaveis["Faixa_Atual"].isin(faixas_relevantes)
    ].copy()
    estaveis.sort_values("Cliente", inplace=True)
    estaveis.reset_index(drop=True, inplace=True)

    # Presos numa faixa intermediária há muito tempo: reaproveita Meses_No_
    # Grupo_Atual/Grupo de pontuacao_migracao_clientes — mesma fonte de
    # verdade da aba de Migração, sem recalcular a mesma lógica duas vezes.
    pontuacao = pontuacao_migracao_clientes(migracao_df, abc_df, granularidade)
    atencao_permanencia = pontuacao[
        (pontuacao["Meses_No_Grupo_Atual"] >= meses_permanencia_alerta)
        & (pontuacao["Grupo"].isin(faixas_intermediarias))
    ][["Cliente", "Grupo", "Meses_No_Grupo_Atual"]].rename(columns={"Grupo": "Faixa_Atual"})
    atencao_permanencia.sort_values("Meses_No_Grupo_Atual", ascending=False, inplace=True)
    atencao_permanencia.reset_index(drop=True, inplace=True)

    return {
        "ascensao": ascensao, "recuando": recuando, "estaveis": estaveis,
        "atencao_permanencia": atencao_permanencia,
    }


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
