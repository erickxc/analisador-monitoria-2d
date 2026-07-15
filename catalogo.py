"""
Catálogo de relatórios da aba "Relatório Padrão" (chaves, títulos, grupos de
parâmetros condicionais) e os dados/helpers de exportação compartilhados
pelos três formatos (Excel/PDF/Word): nomes de aba, rótulos amigáveis,
descrições de metodologia e colunas monetárias por análise.

Módulo intencionalmente sem dependências pesadas (nada de pandas/openpyxl) —
é importado no topo de app.py, então qualquer import pesado aqui atrasaria a
tela de splash (ver app.py, _passo_importar_* / construir_etapas_preparacao).
"""

COR_CABECALHO = "1F4E78"
COR_ACCENT = f"#{COR_CABECALHO}"  # mesma cor de destaque usada nos cabeçalhos do Excel

# Catálogo de relatórios prontos oferecidos na aba "Relatório Padrão", agrupados
# por categoria para facilitar a leitura. Cada item mapeia um título de negócio
# para as chaves internas já calculadas por analise_funil.gerar_analises_completas.
CATALOGO_RELATORIOS = [
    ("Relatórios Gerais", [
        ("top_produtos", "Venda por Produto (Top Produtos)"),
        ("evolucao_produtos", "Tendência de Produtos"),
        ("abc", "Faturamento e Segmentação de Clientes (ABC)"),
        ("migracao_abc", "Migração de Grupo (inclui resumo e score por cliente)"),
    ]),
    ("Relatórios Gerenciais", [
        ("alto_giro", "Alto Giro"),
        ("alertas_queda", "Alertas de Queda Consecutiva"),
        ("erosao_geral", "Erosão de Clientes (Geral)"),
        ("erosao_clientes", "Erosão de Clientes por Produto"),
        ("sem_venda", "Sem Venda"),
        ("poder_compra_clientes", "Poder de Compra por Cliente (3 maiores meses)"),
        ("produtos_em_alta", "Boletim: Produtos em Alta"),
        ("produtos_em_queda", "Boletim: Produtos em Queda"),
        ("clientes_queda_qtd", "Boletim: Clientes em Queda de Quantidade"),
        ("correlacao_produto_cliente", "Boletim: Correlação Produto x Cliente"),
        ("impacto_financeiro_churn", "Boletim: Impacto Financeiro do Churn"),
    ]),
]

# Nem todo relatório do catálogo tem parâmetro próprio (a maioria usa só os
# globais de Configurações: base, clientes/produtos, segmentação, período,
# granularidade). Os poucos que têm formam pequenos grupos N:1 — um mesmo
# campo (ex.: "Queda mínima em R$ p/ alerta") pode ser compartilhado por MAIS
# de um relatório do catálogo (evolucao_produtos e alertas_queda usam a mesma
# tendencia_produtos(); erosao_geral e erosao_clientes usam os mesmos pisos de
# erosão). Por isso isso é modelado como uma aresta N:1 (gatilhos -> campos),
# não como "1 relatório = 1 bloco de parâmetro": qualquer um dos gatilhos
# marcado já habilita o grupo inteiro. "apos" é só a chave do catálogo onde o
# bloco é desenhado (tem que estar na mesma categoria/coluna que os campos).
GRUPOS_PARAMETROS_RELATORIO = [
    {
        "gatilhos": ("evolucao_produtos", "alertas_queda"),
        "apos": "alertas_queda",
        "campos": [
            ("entrada_periodos_queda", "Períodos mínimos seguidos em queda:", "2", 6),
            ("entrada_queda_minima_alerta", "Queda mínima em R$ p/ alerta:", "3000", 8),
            ("entrada_top_n_produtos", "Produtos a exibir (top N por tendência):", "", 6),
        ],
        "legenda": "Vale para \"Tendência de Produtos\" e \"Alertas de Queda Consecutiva\".",
    },
    {
        "gatilhos": ("erosao_geral", "erosao_clientes"),
        "apos": "erosao_geral",
        "campos": [
            ("entrada_reducao_minima_erosao", "Redução mínima p/ erosão (%):", "50", 6),
            ("entrada_queda_minima_erosao", "Queda mínima em R$ p/ erosão:", "3000", 8),
        ],
        "legenda": "Vale para \"Erosão de Clientes (Geral)\" e \"Por Produto\".",
    },
    {
        "gatilhos": ("sem_venda",),
        "apos": "sem_venda",
        "campos": [
            ("entrada_reducao_minima_sem_venda", "Redução mínima p/ Sem Venda (%):", "90", 6),
        ],
        "legenda": "Sem piso de R$ de propósito — pega também clientes de baixo volume.",
    },
    {
        "gatilhos": ("poder_compra_clientes",),
        "apos": "poder_compra_clientes",
        "campos": [
            ("entrada_top_n_poder_compra", "Máximo de clientes a exibir:", "", 6),
        ],
        "legenda": "Maior Poder de Compra primeiro. Vazio = todos os clientes.",
    },
]

NOMES_ANALISE = {
    "top_produtos": "Top_Produtos",
    "poder_compra_clientes": "Poder_Compra_Clientes",
    "evolucao_produtos": "Evolucao_Produtos",
    "alto_giro": "Alto_Giro",
    "alertas_queda": "Alertas_Queda",
    "erosao_geral": "Erosao_Geral",
    "erosao_clientes": "Erosao_Clientes",
    "sem_venda": "Sem_Venda",
    "abc": "ABC_Clientes",
    "abc_produtos": "ABC_Produtos",
    "migracao_abc": "Migracao_ABC",
    "migracao_resumo": "Migracao_Resumo",
    "migracao_score_clientes": "Migracao_Score_Clientes",
    "produtos_em_alta": "Produtos_Em_Alta",
    "produtos_em_queda": "Produtos_Em_Queda",
    "clientes_queda_qtd": "Clientes_Queda_Qtd",
    "correlacao_produto_cliente": "Correlacao_Prod_Cliente",
    "impacto_financeiro_churn": "Impacto_Financeiro_Churn",
}

# Título de seção em PDF/Word: diferente de NOMES_ANALISE (nome de aba do
# Excel — sem acento, com "_" — restrição de caracteres de aba, não de
# leitura), aqui é o mesmo texto descritivo que o usuário já vê nos
# checkboxes do catálogo (Relatório Padrão) e no combo do Visualizar
# Relatório. Antes, PDF/Word usavam NOMES_ANALISE.replace("_", " ") e
# mostravam títulos tipo "Erosao Geral"/"Migracao ABC" — sem acento e sem a
# descrição completa, uma inconsistência visível num documento pra cliente.
ROTULOS_RELATORIO_PDF_WORD = {
    chave: titulo for _categoria, itens in CATALOGO_RELATORIOS for chave, titulo in itens
}
ROTULOS_RELATORIO_PDF_WORD.update({
    "migracao_resumo": "Migração de Grupo — Resumo",
    "migracao_score_clientes": "Migração de Grupo — Score por Cliente",
})

# Descrição curta (metodologia em 1-2 linhas) de cada relatório — único
# lugar mantido, reaproveitado pelos três exportadores (Excel/PDF/Word) pra
# não desalinhar entre formatos conforme a lógica muda.
DESCRICAO_ANALISE = {
    "top_produtos": "Top 20 produtos por receita, somando toda a base carregada — não varia por granularidade.",
    "poder_compra_clientes": "Capacidade de compra de cada cliente no seu melhor momento: média dos 3 meses-calendário de maior receita, não a média corrida (descarta antes picos isolados/atípicos). '% de Variação vs. Potencial' é a diferença percentual do desempenho recente frente a esse potencial (0% = comprando exatamente o potencial, negativo = abaixo, positivo = acima). 'Meses Muito Abaixo do Potencial' conta, dos últimos 3 meses, quantos tiveram receita com queda de 60% ou mais frente a esse potencial.",
    "evolucao_produtos": "Receita e quantidade por produto ao longo do tempo, ordenado pela tendência (média dos últimos 3 períodos vs. dos 3 primeiros).",
    "alto_giro": "Status do mês mais recente de cada produto de alto giro: receita e status (alta/queda) considerando só clientes do Grupo 1; Cliente Destaque/Cliente em Queda são quem mais cresceu e quem mais caiu em % de compra do produto (não quem tem maior faturamento), de todos os grupos, priorizando Grupo 1 > 2 > 3 > demais (nunca o mesmo cliente nos dois papéis). Some/entra sozinho conforme os produtos considerados mudam.",
    "alertas_queda": "Produtos com queda de receita que persiste até o período mais recente — não um histórico antigo já recuperado. Ordenado pelo maior impacto financeiro (Queda em R$).",
    "erosao_geral": "Clientes cuja receita total (somando todos os produtos) caiu 50%+ (ou zerou) em relação ao pico histórico, até o último mês — quem já voltou a comprar no ritmo de antes não aparece.",
    "erosao_clientes": "Clientes cuja compra de um produto caiu 50%+ (ou zerou) em relação ao pico histórico, até o último mês — quem já voltou a comprar no ritmo de antes não aparece.",
    "sem_venda": "Clientes que já compraram alguma vez, mas praticamente pararam — receita do mês mais recente caiu 90%+ frente ao pico histórico. Sem piso de R$ de propósito (diferente de Erosão de Clientes): pega também clientes de baixo volume. Uma coluna de receita por mês disponível na base, para ver a trajetória completa (comprava, parou), não só pico x atual.",
    "abc": "Segmentação de clientes por receita em faixas (Grupo 1/2/3/Demais), com os 5 clientes de maior receita por faixa e período.",
    "abc_produtos": "Segmentação de produtos por representatividade de receita (Grupo 1 = top X% da receita).",
    "migracao_abc": "Clientes que subiram ou desceram de faixa entre períodos consecutivos, com causa provável quando identificável com folga.",
    "migracao_resumo": "Quantidade de clientes que subiram vs. desceram de faixa, por transição de período. Margem = Qtd_Subiu - Qtd_Desceu.",
    "migracao_score_clientes": "Placar acumulado por cliente em todo o histórico de migrações entre faixas (+2 por subida, -3 por queda). Grupo = faixa ABC do cliente no período mais recente.",
    "produtos_em_alta": "Top 10 produtos com maior alta de receita entre os dois períodos mais recentes.",
    "produtos_em_queda": "Top 10 produtos com maior queda de receita entre os dois períodos mais recentes.",
    "clientes_queda_qtd": "Clientes com maior queda de quantidade comprada entre os dois períodos mais recentes.",
    "correlacao_produto_cliente": "Eventos de erosão classificados por padrão: abandono de categoria, fim de ciclo ou ruptura estratégica.",
    "impacto_financeiro_churn": "KPIs agregados do impacto financeiro da erosão de clientes: maior retração individual, receita total sob risco e variação global de receita.",
}


def _formatar_moeda_br(valor):
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _construir_descricoes_dinamicas(parametros):
    """
    Cópia de DESCRICAO_ANALISE com as entradas de erosao_geral/erosao_clientes/
    alertas_queda reescritas com os valores REALMENTE configurados nesta
    geração (redução mínima %, queda mínima em R$, períodos consecutivos) —
    a versão estática sempre dizia "caiu 50%+" mesmo quando o usuário
    configurava um valor diferente (ex.: 80%), dando a falsa impressão de que
    o filtro não tinha efeito algum no relatório exportado.
    """
    descricoes = dict(DESCRICAO_ANALISE)
    reducao = parametros.get("reducao_minima_erosao", 50.0)
    queda_r_erosao = parametros.get("queda_minima_erosao", 0.0)
    piso_erosao = f" e queda de pelo menos {_formatar_moeda_br(queda_r_erosao)}" if queda_r_erosao > 0 else ""
    descricoes["erosao_geral"] = (
        f"Clientes cuja receita total (somando todos os produtos) caiu {reducao:.0f}%+ (ou zerou){piso_erosao} "
        "em relação ao pico histórico, até o último mês — quem já voltou a comprar no ritmo de antes não aparece."
    )
    descricoes["erosao_clientes"] = (
        f"Clientes cuja compra de um produto caiu {reducao:.0f}%+ (ou zerou){piso_erosao} "
        "em relação ao pico histórico, até o último mês — quem já voltou a comprar no ritmo de antes não aparece."
    )

    periodos_queda = parametros.get("periodos_queda", 2)
    queda_r_alerta = parametros.get("queda_minima_alerta", 0.0)
    piso_alerta = f", com queda de pelo menos {_formatar_moeda_br(queda_r_alerta)}" if queda_r_alerta > 0 else ""
    descricoes["alertas_queda"] = (
        f"Produtos com queda de receita em {periodos_queda}+ períodos consecutivos que persiste até o período "
        f"mais recente{piso_alerta} — não um histórico antigo já recuperado. Ordenado pelo maior impacto "
        "financeiro (Queda em R$)."
    )

    reducao_sem_venda = parametros.get("reducao_minima_sem_venda", 90.0)
    descricoes["sem_venda"] = (
        f"Clientes que já compraram alguma vez, mas praticamente pararam — receita do mês mais recente caiu "
        f"{reducao_sem_venda:.0f}%+ frente ao pico histórico (sobrou no máximo {100 - reducao_sem_venda:.0f}% do "
        "que já compraram no auge). Sem piso de R$ de propósito: pega também clientes de baixo volume. Uma "
        "coluna de receita por mês disponível na base, para ver a trajetória completa, não só pico x atual."
    )
    return descricoes


COLUNAS_MOEDA_POR_ANALISE = {
    "top_produtos": ["Receita"],
    "poder_compra_clientes": ["Poder_De_Compra", "Receita Média Recente (3 meses)"],
    "evolucao_produtos": ["Receita", "Receita_Periodo_Anterior"],
    "alto_giro": ["Receita Atual"],
    "alertas_queda": ["Receita Atual", "Receita Precedente à Queda", "Queda em R$"],
    "erosao_geral": ["Receita no Pico", "Receita Atual", "Queda em R$"],
    "erosao_clientes": ["Receita no Pico", "Receita Atual", "Queda em R$"],
    # "sem_venda" tem uma coluna de receita por mês disponível na base —
    # nomes dinâmicos (ex.: "ago/25"), não dá pra listar aqui de antemão.
    # Ver _colunas_moeda_efetivas: computado a partir do próprio DataFrame
    # na hora de exportar (tudo que não for Cliente/Grupo é moeda).
    "sem_venda": [],
    "abc": ["Receita", "Renuncia", "Renuncia_Acumulada"],
    "abc_produtos": ["Receita", "Renuncia", "Renuncia_Acumulada"],
    "migracao_abc": [],
    "migracao_resumo": [],
    "migracao_score_clientes": [],
    "produtos_em_alta": ["Receita_Periodo_Anterior", "Receita_Periodo_Atual", "Total_Ano_Atual"],
    "produtos_em_queda": ["Receita_Periodo_Anterior", "Receita_Periodo_Atual", "Total_Ano_Atual"],
    "clientes_queda_qtd": ["Perda_Receita"],
    "correlacao_produto_cliente": ["Reducao_Receita"],
    "impacto_financeiro_churn": ["Receita_Sob_Risco"],
}


def _colunas_moeda_efetivas(chave_analise, df_analise):
    """
    Lista de colunas monetárias pra formatar, resolvendo o caso especial de
    "sem_venda": as colunas são uma por mês disponível na base (nomes
    dinâmicos, ex. "ago/25"), impossível listar de antemão em
    COLUNAS_MOEDA_POR_ANALISE — aqui todas as colunas exceto Cliente/Grupo/
    Grupo 11 Meses/Grupo no Pico são receita, então tudo que sobra é moeda.
    """
    if chave_analise == "sem_venda":
        colunas_texto = ("Cliente", "Grupo", "Grupo 11 Meses", "Grupo no Pico")
        return [c for c in df_analise.columns if c not in colunas_texto]
    return COLUNAS_MOEDA_POR_ANALISE.get(chave_analise)
