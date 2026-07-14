"""
Motor de análise do funil de vendas B2B.

Sem dependência de GUI - pode ser testado isoladamente via linha de comando
ou testes automatizados. Todas as funções recebem/retornam DataFrames do pandas.

Este módulo é a fachada pública do motor (o que `app.py`/`graficos.py`
importam como `import analise_funil as af`) mais o orquestrador
`gerar_analises_completas`. A implementação está dividida em módulos
menores, coesos por tema — todo símbolo abaixo é só re-exportado, não
reimplementado, para o motor caber num arquivo por assunto em vez de um
único arquivo monólito:

  - nucleo_analise: constantes de domínio, carregamento/limpeza do CSV,
    helpers de período.
  - classificacao: classificação ABC/faixas (por período e agregada).
  - relatorios_produtos: top produtos, poder de compra, tendência/alertas
    de queda, boletim de alta/queda, Alto Giro.
  - relatorios_erosao: erosão de clientes, Sem Venda, queda de quantidade,
    correlação produto x cliente, impacto financeiro de churn.
  - migracao: migração de faixa, placar de pontuação, mobilidade de
    carteira, causa provável.
"""

from classificacao import (
    _limitar_top_por_grupo,
    calcular_frequencia,
    calcular_renuncia,
    classificar_abc,
    classificar_clientes_agregado,
    classificar_faixas,
    classificar_produtos_agregado,
    classificar_produtos_por_receita,
    contar_clientes_por_grupo,
    sugerir_cortes_grupos,
)
from migracao import (
    PONTOS_DESCEU_FAIXA,
    PONTOS_SUBIU_FAIXA,
    _causa_provavel_migracao,
    _preparar_contexto_causa_provavel,
    migracao_abc,
    mobilidade_carteira,
    pontuacao_migracao_clientes,
    resumo_migracao,
)
from nucleo_analise import (
    COLUNA_PERIODO,
    COLUNAS_OBRIGATORIAS,
    DESCRICAO_NAO_HARMONIZADA,
    GRANULARIDADES,
    MESES_ABREV,
    MESES_PT,
    REGEX_BALCAO,
    ErroCarregamentoCSV,
    _formatar_rotulo_periodo,
    _ordenar_periodos,
    carregar_csv,
    contar_produtos_nao_harmonizados,
)
from relatorios_erosao import (
    _erosao_generico,
    clientes_queda_quantidade,
    correlacao_produto_cliente,
    erosao_clientes_geral,
    erosao_clientes_por_produto,
    impacto_financeiro_churn,
    sem_venda,
)
from relatorios_produtos import (
    _media_top3_sem_outliers,
    _tendencia_percentual,
    poder_compra_agregado,
    produtos_alta_e_queda,
    status_alto_giro,
    tendencia_produtos,
    top_produtos,
)

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
