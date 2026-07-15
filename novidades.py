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
    "1.6.9": [
        "Corrige a descrição de Erosão de Clientes e Alertas de Queda exportada no Excel/PDF/Word: sempre mostrava os valores padrão (ex.: 'caiu 50%+'), mesmo quando você configurava outro valor — agora reflete o que foi realmente usado na geração.",
        "Esclarece o rótulo 'Períodos mínimos seguidos em queda' (antes só dizia 'Períodos seguidos em queda', dando a entender um valor exato em vez de um piso mínimo).",
    ],
    "1.6.10": [
        "Alertas de Queda: 'Queda em R$' agora soma a perda de cada mês da sequência (não só a diferença entre o primeiro e o último mês) — uma queda que persiste por vários meses passa a pesar mais.",
        "Novo relatório gerencial 'Sem Venda': clientes que já compraram mas praticamente pararam (queda de 90%+ do pico, sem piso de R$ — pega também clientes de baixo volume), com uma coluna de receita por mês para ver a trajetória completa.",
        "Corrige a prévia de 'Produtos considerados'/'Clientes' na tela de Configurações: estava calculando a % de receita a partir da base inteira, ignorando lojas desmarcadas e clientes excluídos.",
        "Corrige o rótulo das colunas 'Freq. Simples'/'Freq. Acumulado' na lista de produtos — nunca foram frequência de compra, sempre foram % de receita. Renomeadas para '% Receita'/'% Receita Acumulada'.",
        "Poder de Compra: novo campo para limitar o máximo de clientes exibidos, mantendo sempre os de maior Poder de Compra primeiro.",
        "Corrige o botão 'Gerar Relatório Padrão' (e outros elementos da tela) aparecendo fragmentado/borrado em telas com escala do Windows diferente de 100% — o programa agora avisa o Windows que lida com a escala sozinho, em vez de deixar o próprio Windows esticar a janela já desenhada.",
    ],
    "1.6.11": [
        "Corrige o tamanho da janela principal (e da tela de 'Novidades') em telas com escala do Windows diferente de 100%: a correção da v1.6.10 evitava o texto/botões borrados, mas o tamanho da janela ficou pequeno demais pro conteúdo, cortando o rodapé — inclusive o botão 'Gerar Relatório Padrão', que sumia de vista.",
    ],
    "1.6.12": [
        "Corrige de vez o botão 'Gerar Relatório Padrão' sumindo de vista: a causa real não era só o tamanho da janela (v1.6.11), e sim a ordem de montagem da tela — a lista de relatórios (que cresce bastante com vários relatórios/parâmetros marcados) tomava todo o espaço disponível antes do botão, deixando-o sem lugar quando a janela não tinha altura de sobra. Agora o botão sempre reserva seu espaço primeiro, e é a lista de relatórios que se ajusta ao espaço restante.",
    ],
    "1.6.13": [
        "Adiciona barra de rolagem à lista de relatórios da tela 'Relatório Padrão': a correção da v1.6.12 garantiu que o botão 'Gerar Relatório Padrão' nunca mais fique sem espaço, mas em janelas pequenas a lista em si podia ficar cortada, sem como ver os relatórios de baixo. Agora dá para rolar até todos eles.",
    ],
    "1.6.14": [
        "Alto Giro: novas colunas '% Variação do Cliente Destaque' e '% Variação do Cliente em Queda' — a variação de compra DAQUELE cliente específico nesse produto (mês atual vs. anterior), separado da variação % do produto como um todo.",
    ],
    "1.6.15": [
        "Alto Giro: receita, status, variação e clientes destaque/em queda agora consideram só clientes do Grupo 1 (a carteira principal) — um produto sem compra de nenhum cliente Grupo 1 nos 2 últimos meses deixa de aparecer no relatório.",
    ],
    "1.6.16": [
        "Corrige o filtro de Grupo 1 do Alto Giro (v1.6.15): a classificação estava sendo calculada sem o mês mais recente, podendo incluir por engano um cliente que é Grupo 2 na visão completa (a mesma que aparece em Configurações). Agora usa sempre a receita total do cliente, igual à prévia de Configurações.",
    ],
    "1.6.17": [
        "Alto Giro: 'Cliente em Queda' agora exige que o cliente tenha comprado algo no mês atual (não só reduzido) — um cliente que foi a zero deixa de contar como 'em queda' aqui (isso já é assunto de Erosão/Sem Venda).",
    ],
    "1.6.18": [
        "Alto Giro: 'Cliente Destaque' e 'Cliente em Queda' agora são quem mais CRESCEU e quem mais CAIU em % de compra do produto (não mais quem tem maior faturamento) — considerando clientes de todos os grupos, com prioridade Grupo 1 > Grupo 2 > Grupo 3 > demais. Receita/Status do produto continuam só com clientes Grupo 1.",
    ],
    "1.6.20": [
        "Corrige a atualização automática que baixava mas nunca terminava de instalar: quando a conexão caía no meio do download (rede instável, proxy ou antivírus), o arquivo incompleto era instalado por cima do programa atual, corrompendo-o. Agora o download é validado antes de instalar.",
        "Novo estilo 'Linha (%)' no gráfico 'Evolução no Tempo': participação de mercado por fabricante/produto/cliente ao longo do tempo, com 'Outros' agrupando quem fica fora do Top N.",
    ],
    "1.6.21": [
        "Corrige a classificação de Grupo (1/2/3/Demais) no relatório ABC e na Migração de Grupo: agora considera a receita acumulada do cliente/produto até aquele período (mesmo critério já usado em Poder de Compra/Alto Giro), não mais só a receita daquele mês isolado — um mês fraco pontual deixa de tirar do Grupo 1 quem tem histórico grande.",
    ],
    "1.6.22": [
        "Corrige uma falha silenciosa na atualização automática: se um antivírus apagasse o instalador baixado antes da troca do programa, a atualização era dada como concluída sem realmente trocar o executável, sem nenhum aviso. Agora o programa detecta essa falha e avisa claramente na próxima abertura, explicando o motivo.",
    ],
    "1.6.23": [
        "Corrige a classificação de Grupo (1/2/3/Demais): Migração de Grupo, ABC, Poder de Compra, Sem Venda, filtro 'Grupo 1' do Alto Giro e a prévia de Configurações agora usam sempre a receita TOTAL do cliente para decidir o grupo — antes, com 'somente produtos de alto giro' marcado, cada tela podia calcular um grupo diferente para o mesmo cliente, sem explicação visível.",
    ],
    "1.6.24": [
        "Sem Venda: novas colunas 'Grupo 11 Meses' (faixa do cliente no início da base) e 'Grupo no Pico' (faixa no mês do seu maior faturamento), para ver em que grupo o cliente já esteve antes de parar de comprar.",
    ],
}
