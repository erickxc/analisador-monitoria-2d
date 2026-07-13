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
    "1.6.1": [
        "Corrige a janela principal cortada em telas menores (agora se adapta à resolução disponível).",
        "Corrige o ícone padrão do Tkinter aparecendo na tela de abertura em vez da logo da 2D.",
        "Corrige a exclusão de clientes: antes só valia para ABC e Poder de Compra — agora vale em todos os relatórios (Alertas de Queda, Erosão, Alto Giro, Top Produtos, etc.).",
        "Poder de Compra: corrige coluna 'Meses Muito Abaixo do Potencial' exportando como percentual em vez de número; remove o percentual acumulado do relatório.",
        "Migração de Grupo: ajusta a pontuação — queda de faixa agora pesa mais que subida (-3 / +2).",
    ],
    "1.6.2": [
        "Alto Giro: 'Cliente Destaque' nunca mais repete o mesmo cliente de 'Cliente em Queda' no mesmo produto.",
        "Corrige o painel de Execução (log/progresso) sumindo em janelas menores.",
        "Poder de Compra: descarta picos isolados (um mês fora da curva) antes de calcular o potencial do cliente; '% do Potencial Realizado' vira '% de Variação vs. Potencial'.",
        "Produtos considerados na análise: lista agora abre ordenada por frequência.",
        "Gráficos: novos tipos (Barras, Linha, Pizza, Histograma, Pirâmide), filtros de período/valor mínimo/fabricante/faixa ABC, exportar para Excel, e corrige 'Vendas por Fabricante' sem opção de colorir por Fabricante.",
    ],
    "1.6.3": [
        "Corrige produtos que não resincronizavam com o Grupo 1 ao aumentar o corte de produtos (ficavam travados por uma configuração salva anteriormente).",
        "Migração de Grupo: nova coluna 'Margem' (Qtd_Subiu - Qtd_Desceu) no resumo por transição de período.",
        "Migração de Grupo: nova coluna 'Grupo' no placar por cliente, mostrando a faixa ABC mais recente de cada um.",
    ],
    "1.6.5": [
        "Corrige um erro ao abrir o programa em algumas máquinas ('no default root window').",
        "Adiciona filtro de Lojas incluídas na análise.",
    ],
    "1.6.6": [
        "Nova aba 'Visualizar Relatório': pré-visualiza qualquer relatório sem precisar exportar, com filtro por categoria (Gerais/Gerenciais).",
        "PDF/Word: corrige títulos truncados e cabeçalhos crus; largura de coluna calculada pelo conteúdo real; índice agora traz o número da página.",
        "Parâmetros de Alertas de Queda/Erosão movidos para dentro do catálogo, junto do relatório correspondente; corrige coluna de Parâmetros sem rolagem cortando conteúdo no rodapé.",
        "Gráfico Top Fabricantes: novas colunas com Mês Atual e Mês Anterior.",
    ],
    "1.6.7": [
        "Corrige a causa raiz de atualizações que baixavam mas nunca terminavam de instalar: agora não é mais possível abrir duas janelas do programa ao mesmo tempo (a segunda janela travava o arquivo, impedindo a troca pela versão nova).",
        "Corrige uma falha ao tentar abrir uma segunda instância do programa.",
    ],
    "1.6.8": [
        "Gráfico 'Receita por Fabricante ou Produto': novo controle de ordem (crescente/decrescente) e opção de mostrar só os N maiores ou menores.",
        "Gráficos 'Top Clientes'/'Top Fabricantes': ordem crescente agora mostra os piores, não só os melhores.",
        "Corrige colunas de Mês Atual/Anterior faltando ao exportar 'Top Clientes' e o estilo Histograma para Excel.",
    ],
}
