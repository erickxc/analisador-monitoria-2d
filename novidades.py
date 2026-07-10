"""
Registro do que mudou em cada versão publicada — mostrado numa janela
pequena e direta na primeira vez que o usuário abre uma versão nova (ver
_mostrar_novidades_versao em app.py). Nunca aparece na primeira execução
de uma instalação nova (não há versão anterior pra comparar).

Ao publicar uma release, adicionar uma entrada aqui com bullets curtos e
executivos (o que mudou, não como foi implementado).
"""

NOVIDADES_POR_VERSAO = {
    "1.4.0": [
        "Relatórios por período agora ignoram, por padrão, o mês/período mais recente (geralmente incompleto).",
        "Evolução de Produtos: meses em formato legível (ago/25) e ordenados por tendência real de crescimento.",
        "Evolução de Produtos e Alertas de Queda: novo campo para limitar quantos produtos aparecem.",
        "Erosão de Clientes: compara só o período mais recente, com filtro de queda mínima (50% por padrão).",
        "ABC de Clientes: mostra os 5 principais clientes de cada grupo; corrige a classificação de clientes balcão.",
        "Poder de Compra: recalculado com base nos 3 melhores meses de cada cliente, não mais por período.",
        "Migração de Grupo: causas mais diretas, resumo de altas x quedas, e placar de pontuação por cliente.",
    ],
    "1.4.1": [
        "Corrige uma falha ocasional ao reabrir automaticamente logo após uma atualização.",
    ],
    "1.5.0": [
        "Remove o relatório 'Venda por Cliente (Top Clientes)', sem uso — virou o gráfico 'Top Clientes por Receita'.",
        "Corrige a atualização automática: agora ela avisa pra reabrir manualmente em vez de tentar reabrir sozinha (o antivírus bloqueava essa reabertura em alguns computadores).",
    ],
    "1.6.0": [
        "Catálogo reorganizado em 'Relatórios Gerais' (detalhados, com histórico) e 'Relatórios Gerenciais' (foco no mês mais recente, ação rápida).",
        "Checkbox 'somente produtos de alto giro' agora vale em todos os relatórios, gráficos e personalizados, com padrão inteligente (Grupo 1) e sem esquecer sua escolha ao trocar de tela ou reabrir o programa.",
        "Alertas de Queda: sinaliza só quem está em queda AGORA (não um histórico antigo já recuperado), com quantidade vendida e piso mínimo de valor configurável, ordenado por maior impacto financeiro.",
        "Erosão de Clientes dividida em 'Geral' (cliente como um todo) e 'Por Produto', comparando sempre o último mês contra o pico histórico do cliente.",
        "Novo relatório 'Alto Giro': status do mês mais recente de cada produto de alto giro, com o cliente que mais comprou e o que mais reduziu a compra.",
        "Poder de Compra: nova comparação entre o potencial do cliente (pico) e o desempenho dos últimos 3 meses.",
        "Migração de Grupo: corrige o cálculo de % de permanência e uma falha ao gerar em algumas granularidades.",
        "Remove o relatório 'Venda por Fabricante (Top Fabricantes)', sem uso — vira o gráfico 'Top Fabricantes por Receita'.",
        "PDF: corrige cabeçalhos de tabela sobrepostos, visual renovado (capa e cabeçalhos em preto) e descrição curta de cada relatório.",
        "Excel: corrige colunas de percentual que multiplicavam errado ao formatar como %.",
    ],
}
