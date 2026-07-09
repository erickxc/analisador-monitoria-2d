# Relatórios do Monitor — como funcionam hoje

Documento de referência do estado atual de cada relatório/análise. Gerado lendo `analise_funil.py` (motor de cálculo), `app.py` (catálogo, exportação Excel) e `exportadores_pdf_word.py` (PDF/Word). Atualizado após a revisão de analista sênior (PRs #9 e #10) que refinou Evolução/Alertas/Erosão/ABC e redesenhou Poder de Compra/Migração de Grupo.

## Como o motor está organizado

- **Entrada:** um único CSV (`;`, `utf-8-sig`) carregado por `carregar_csv()` em `analise_funil.py`. Linhas com `Ano` ou `Mês` vazio são descartadas (contadas e avisadas ao usuário, não travam a importação).
- **Granularidade:** todo relatório baseado em período pode ser calculado em Mensal, Trimestral, Semestral ou Anual — é um parâmetro (`granularidade`) que quase toda função aceita, mudando qual coluna de período (`Periodo_Mensal`, `Periodo_Trimestral`, etc.) é usada para agrupar.
- **Período mais recente excluído por padrão:** `gerar_analises_completas(..., excluir_periodo_atual=True)` — o último período de cada granularidade (geralmente incompleto na base) é descartado antes de qualquer análise "por período". Não afeta `top_produtos`/`top_fabricantes` (somam a base inteira). Checkbox "Incluir período mais recente" na tela pra desligar isso.
- **Orquestração:** `gerar_analises_completas()` é o ponto único que roda tudo. Recebe `chaves_solicitadas` (quais relatórios o usuário marcou no catálogo) e resolve as dependências entre eles automaticamente — por exemplo, "Migração de Grupo" precisa da classificação ABC **completa** (sem o corte de top-5 usado na exibição do relatório "ABC"), então ele recalcula isso internamente mesmo que "ABC" não esteja marcado, mas só se algo pedido de fato precisar. Isso existe por performance: com centenas de milhares de linhas, calcular tudo sempre seria lento à toa.
- **Saída:** um dicionário `{ granularidade: { chave_do_relatorio: DataFrame } }`, que os três exportadores (Excel/PDF/Word) percorrem pra gerar uma aba/seção por combinação de relatório × granularidade.
- **Percentual no Excel:** internamente, toda coluna de percentual é um número "cru" (8.3 = 8,3%), do jeito mais fácil de usar em filtros/ordenação no motor. Na exportação Excel (`_escrever_dataframe` em `app.py`), qualquer coluna cujo nome contenha `%`, `Percentual` ou `Pct` é automaticamente detectada e convertida pra fração (0.083) com formato nativo `0.00%` — sem isso, o percentual do Excel multiplica por 100 na exibição e a célula mostra "830%" em vez de "8,30%". Cobre também os Relatórios Personalizados, que o usuário monta livremente.

## Catálogo de relatórios (aba "Relatório Padrão")

O catálogo tem duas categorias, em `CATALOGO_RELATORIOS` (`app.py`):

- **Relatórios Gerais**: detalhados, com histórico e granularidade selecionável (Mensal/Trimestral/Semestral/Anual) — para análise aprofundada.
- **Relatórios Gerenciais**: focados no estado atual/recente, a maioria sem granularidade (ou olhando só os 2 períodos mais recentes) — pensados pra leitura e ação rápida.

### Relatórios Gerais

| Chave | Rótulo | Função | O que é |
|---|---|---|---|
| `top_fabricantes` | Venda por Fabricante (Top Fabricantes) | `top_produtos`/`top_fabricantes` | Top 20 por Receita (soma de todo o período carregado, **não** respeita granularidade) |
| `top_produtos` | Venda por Produto (Top Produtos) | idem | idem, agrupado por `descricao` |
| `evolucao_produtos` | Tendência de Produtos | `tendencia_produtos()` | Receita/QTD por produto e período (rótulo legível: `ago/25`, `T3/25`, `S1/25`, `2025`), com variação % vs. período anterior. Ordenado por `Tendencia_Pct` (média dos últimos 3 períodos vs. média dos 3 primeiros — preferido a CAGR ponto-a-ponto ou regressão linear, testado contra `data.teste.csv`) descendente. Campo "Produtos a exibir" na tela limita a top N por tendência (vazio = todos). |
| `abc` | Faturamento e Segmentação de Clientes (ABC) | `classificar_abc` → `classificar_faixas` | Por período, ordena clientes por receita e divide em faixas por % acumulado (`Grupo 1/2/3/Demais`, cortes padrão 30/50/60%, mais faixa **"Balcão"** própria se o checkbox de balcão estiver marcado — com `Percentual_Individual` real, `Percentual_Acumulado` = NaN, nunca misturada com "Grupo 1"). Mostra só os **5 clientes de maior receita por (período, faixa)** — `top_clientes_por_grupo`, ajustável só via código. Traz `Renuncia*` (queda de receita vs. período anterior); **não** traz mais frequência (removida — não fazia sentido junto de um corte "top 5"). |
| `migracao_abc` | Migração de Grupo (inclui resumo e score por cliente) | `migracao_abc()` + `resumo_migracao()` + `pontuacao_migracao_clientes()` | Marcar esta chave gera **3 abas**: (1) `Migracao_ABC` — quem subiu/desceu de faixa entre períodos consecutivos, com causa quando uma heurística bate com folga (produto abandonado ≥70% da receita, frequência caiu pela metade+, ticket médio caiu 40%+, ou produto novo ≥50% da receita atual — célula fica **em branco** se nada bater, sem "estimativa" genérica); (2) `Migracao_Resumo` — `Qtd_Subiu`/`Qtd_Desceu` por transição de período; (3) `Migracao_Score_Clientes` — score acumulado por cliente em todo o histórico (+3 por subida, -2 por queda) e `Percentual_Permanencia` (% das transições sem migrar de faixa). A classificação ABC usada aqui é sempre a **completa** (sem o corte de top-5 do relatório "ABC"), senão a migração só enxergaria 5 clientes por grupo. |

`top_fabricantes`/`top_produtos` são as únicas do catálogo que **não variam por granularidade** — somam a base inteira, sempre.

> `top_clientes` ("Venda por Cliente / Top Clientes") foi removido do catálogo por falta de uso — virou o gráfico "Top Clientes por Receita" (ver seção Gráficos abaixo).

### Relatórios Gerenciais

| Chave | Rótulo | Função | O que é |
|---|---|---|---|
| `alertas_queda` | Alertas de Queda Consecutiva | `tendencia_produtos()` (segundo retorno) | Produtos com N períodos seguidos de queda **terminando no período mais recente** (queda atual, não um histórico antigo já recuperado), na granularidade escolhida (N = "Períodos seguidos em queda p/ alerta", padrão 2). Colunas: `Períodos Consecutivos em Queda`; `Período Anterior à Queda`/`Receita Precedente à Queda`/`Qtd Precedente à Queda` (rótulo legível, ex.: `fev/26`, e receita/quantidade no período-base antes da primeira queda da sequência); `Receita Atual`/`Qtd Atual` (fim da sequência — sempre o período mais recente; o rótulo do período em si não é uma coluna porque seria o mesmo valor em toda linha); `Queda em R$` (Receita Precedente à Queda − Receita Atual); `% Média de Queda` (média das variações percentuais dentro da própria sequência, magnitude positiva). Nada disso são os extremos de todo o histórico do produto, só da sequência detectada. Ordenado por `Queda em R$` descendente — prioriza impacto financeiro, não duração da sequência (um produto com R$50.000 de queda em 2 períodos é mais crítico que um com R$200 de queda em 5). Campo "Queda mínima em R$ p/ alerta" na tela (padrão 3000, ajustável — 0 = sem piso) filtra fora quedas pequenas antes de aplicar "Produtos a exibir". Meses/produtos com receita líquida negativa no período (devoluções/estornos que superam as vendas) não entram no cálculo de variação — o percentual perde sentido de magnitude quando a base de comparação é negativa. |
| `erosao_clientes` | Erosão de Clientes por Produto | `erosao_clientes_por_produto()` | **Sem granularidade** (sempre por mês-calendário, igual a `poder_compra_clientes`; a Radiobutton de granularidade na tela não afeta o resultado). Por cliente+produto, compara o **último mês completo** contra o **pico** (maior mês de receita em qualquer ponto anterior do histórico, não só o mês imediatamente anterior) — captura tanto uma queda recente quanto uma erosão mais lenta (comprava muito em jan/fev, praticamente parou depois). Período de referência é relativo a cada cliente+produto; como a comparação é sempre contra o último mês, quem já voltou a comprar no ritmo de antes não aparece. Colunas: `Cliente`, `descricao`, `Período do Pico`/`Receita no Pico`, `Período Atual`/`Receita Atual`, `Queda em R$`, `% de Queda`, `Parou de Comprar`. Ordenado por `Queda em R$` descendente (prioriza impacto financeiro, não percentual — evita que uma queda de R$50 "100%" apareça antes de uma queda de R$5.000 "60%"). Filtro "Redução mínima p/ erosão" na tela (padrão 50%, ajustável). Se "Alertas de Queda" foi calculado, restrita aos produtos já sinalizados lá (senão roda para todos) — junto com o checkbox de "produtos de alto giro" (quando ativo), é o que mantém a lista focada em produtos relevantes, sem piso de valor fixo em código. Receita do período atual negativa (devolução/estorno que superou a venda) fica de fora — não é uma redução de compra no sentido normal, e o percentual passaria de 100%. |
| `poder_compra_clientes` | Poder de Compra por Cliente (3 maiores meses) | `poder_compra_agregado()` | **Sem período** (uma linha por cliente). `Poder_De_Compra` = média dos 3 meses-calendário de MAIOR receita do cliente em toda a base (o pico, não a média corrida) — sempre mensal, independente da granularidade escolhida. `Grupo`/`Percentual_Acumulado` vêm de `classificar_clientes_agregado` (pela receita total, não pelo poder de compra). |
| `produtos_em_alta` / `produtos_em_queda` | Boletim: Produtos em Alta/Queda | `produtos_alta_e_queda()` | Compara só os **dois últimos períodos** da granularidade escolhida (não a série toda); top 10 por variação % positiva/negativa. |
| `clientes_queda_qtd` | Boletim: Clientes em Queda de Quantidade | `clientes_queda_quantidade()` | Idem, mas por cliente e por QTD (não receita); aponta o "produto crítico" que mais puxou a queda. |
| `correlacao_produto_cliente` | Boletim: Correlação Produto x Cliente | `correlacao_produto_cliente()` | Top eventos de erosão, classificados heuristicamente: "Abandono de Categoria" (≥3 clientes largaram o mesmo produto no mesmo período), "Fim de Ciclo" (produto já está em alerta de queda), "Ruptura Estratégica" (parou de comprar produto que era ≥70% do que comprava dele), ou "Caso Específico". |
| `impacto_financeiro_churn` | Boletim: Impacto Financeiro do Churn | `impacto_financeiro_churn()` | 3 KPIs agregados: maior retração individual (%), receita total sob risco (soma das reduções de erosão), variação global de receita entre os 2 últimos períodos. |

### Existe mas não aparece no catálogo

- `abc_produtos` (`classificar_produtos_por_receita`) — classificação de produtos por representatividade (Grupo 1 = top X% da receita, padrão 80%). A função existe e é usada pela prévia de "Corte de produtos" na tela de Configurações, mas foi removida do catálogo de relatórios prontos (decisão de um commit anterior) — hoje só é gerada se algo internamente pedir a chave `"abc_produtos"`.

## Parâmetros que afetam vários relatórios ao mesmo tempo

- **Excluir período mais recente** (checkbox, padrão ligado): ver seção acima — afeta todo relatório "por período", não os Top N.
- **Clientes excluídos** (lista marcada em Configurações): removidos da base antes de qualquer cálculo de ABC/frequência/renúncia — não aparecem em nenhum relatório dependente disso.
- **"Considerar somente produtos de alto giro"** (checkbox, padrão ligado) + lista "Produtos considerados na análise": com o checkbox marcado, os produtos desmarcados na lista são filtrados de **tudo** — Relatório Padrão, Gráficos e Relatórios Personalizados (um único ponto, `_dataframe_para_analise()`, usado pelos três). Desmarcado, todos os três voltam a usar a base inteira, sem filtro de produto nenhum. Antes desse checkbox existir, esse filtro só valia pro Relatório Padrão — Gráficos e Personalizados sempre usaram a base inteira, mesmo com produtos desmarcados. **Padrão inicial da lista** (ao carregar um CSV novo): marcado só quem está em "Grupo 1" pelo corte de produtos (`classificar_produtos_agregado`, padrão top 80% da receita) — os demais já entram desmarcados. É só o ponto de partida; o usuário pode marcar/desmarcar produtos individuais depois, e isso não é sobrescrito ao reclassificar (mudar o corte de produtos só atualiza a coluna "Grupo" exibida, não desfaz escolhas manuais).
- **Cortes de grupo (30/50/60%)** e **corte de produtos (80%)**: afetam ABC/Poder de Compra de clientes e a prévia de produtos, respectivamente.
- **"Desconsiderar clientes balcão da frequência"** (checkbox): desde o PR #9, a faixa "Balcão" é consistente entre a prévia da tela (`classificar_clientes_agregado`) e o relatório exportado (`classificar_faixas`/`classificar_abc`) — mesmo comportamento nos dois lugares.
- **"Produtos a exibir"** (Evolução/Alertas) e **"Redução mínima p/ erosão"**: ver tabela de Tendências e Alertas acima.
- **Nome da empresa analisada**: não afeta cálculo nenhum — só aparece na capa e no nome do arquivo exportado.

## Pendência conhecida: frequência de produto (prévia vs. relatório)

`classificar_produtos_agregado()` (prévia de "Corte de produtos" na tela) já calcula frequência como % de receita (`Freq_Simples`/`Freq_Acumulado`). `calcular_frequencia()` (usada por `classificar_faixas`/`classificar_produtos_por_receita`, o cálculo "oficial" por período) ainda conta nº de meses com compra — não foi migrado pra % de receita. Como `abc_produtos` não está no catálogo hoje (ver abaixo), isso não aparece em nenhum relatório gerado atualmente, mas vale ter em mente se essa chave voltar a ser usada.

## Relatórios Personalizados (`pivot_builder.py`)

Tabela dinâmica livre (`pandas.pivot_table`, com `margins=True` = linha/coluna de "Total Geral"): o usuário arrasta campos para Linhas / Colunas / Valores (com agregação: Soma, Contagem, Média, Mínimo, Máximo) / Filtros. Campos disponíveis: os brutos do CSV (`Cliente`, `descricao`, `NOME_FABRICANTE`, `Loja`, `Receita`, `QTD`, `Data_Venda`) mais os calculados (`Faixa_ABC`, `Periodo_Mensal/Trimestral/Semestral/Anual`). Configurações de relatório podem ser salvas/carregadas em JSON. Cada relatório personalizado nomeado vira uma aba extra (`Custom_<nome>`) no Excel exportado — não entra em PDF/Word.

## Gráficos (`graficos.py`)

Cinco visualizações de dispersão (scatter), sempre coloridas por `Faixa_ABC` do cliente (última classificação disponível), exceto onde indicado:

1. **Vendas por Fabricante** — QTD × Receita, um ponto por (fabricante, cliente).
2. **Vendas por Produto** — QTD × Receita por (produto, cliente); pode colorir por Faixa ABC **ou** por Fabricante.
3. **Receita Agrupada** — receita total por Fabricante ou por Produto, ordenado decrescente (sem cor por faixa).
4. **Afinidade Cliente × Fabricante** — % do faturamento do cliente que vem daquele fabricante (eixo X) × frequência de compra (eixo Y).
5. **Top Clientes por Receita** — receita total dos N clientes de maior faturamento (10/20/50/100, ajustável), ordenado decrescente, sem cor por faixa. Substitui o relatório `top_clientes` removido do catálogo.

Exportação: só PNG, um gráfico por vez (a view atualmente selecionada).

## Exportação — Excel, PDF, Word

Os três formatos recebem o mesmo dicionário de resultados e passam por uma "capa" antes das seções de dados:

- **Capa** (comum aos três): logo, nome do sistema, "Empresa analisada" (se preenchido), nome de quem gerou (perfil salvo), data/hora de geração, nome da empresa (2D Consultores).
- **Excel** (`exportar_relatorio_excel`, em `app.py`): uma aba por (relatório × granularidade), cabeçalho colorido, formato moeda BRL nas colunas configuradas em `COLUNAS_MOEDA_POR_ANALISE`, largura de coluna automática, logo (só a marca, sem texto) em miniatura em cada aba. Relatórios personalizados nomeados viram abas `Custom_<nome>` extras.
- **PDF/Word** (`exportadores_pdf_word.py`): pensados pra leitura/impressão, não manipulação — cada tabela é **limitada a 50 linhas** (`MAX_LINHAS_TABELA`), com aviso de corte quando aplicável. Uma seção por (relatório × granularidade), com o nome do relatório "bonito" vindo de `NOMES_ANALISE`.

## Mapa rápido de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `analise_funil.py` | Todo o cálculo (as funções desta tabela) — sem GUI, testável isolado |
| `app.py` | Catálogo (`CATALOGO_RELATORIOS`), nomes/colunas-moeda por relatório, exportação Excel, orquestração da geração via thread |
| `exportadores_pdf_word.py` | Exportação PDF e Word |
| `pivot_builder.py` | Relatórios Personalizados (pivot table) |
| `graficos.py` | As 4 views de dispersão |
