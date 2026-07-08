# Relatórios do Monitor — como funcionam hoje

Documento de referência do estado atual de cada relatório/análise, antes de começarmos a mexer neles. Gerado lendo `analise_funil.py` (motor de cálculo), `app.py` (catálogo, exportação Excel) e `exportadores_pdf_word.py` (PDF/Word).

## Como o motor está organizado

- **Entrada:** um único CSV (`;`, `utf-8-sig`) carregado por `carregar_csv()` em `analise_funil.py`. Linhas com `Ano` ou `Mês` vazio são descartadas (contadas e avisadas ao usuário, não travam a importação).
- **Granularidade:** todo relatório baseado em período pode ser calculado em Mensal, Trimestral, Semestral ou Anual — é um parâmetro (`granularidade`) que quase toda função aceita, mudando qual coluna de período (`Periodo_Mensal`, `Periodo_Trimestral`, etc.) é usada para agrupar.
- **Orquestração:** `gerar_analises_completas()` é o ponto único que roda tudo. Recebe `chaves_solicitadas` (quais relatórios o usuário marcou no catálogo) e resolve as dependências entre eles automaticamente — por exemplo, "Poder de Compra" e "Migração" dependem do cálculo de ABC, então ele roda o ABC mesmo que o usuário não tenha marcado "ABC" explicitamente, mas só se algo que pediu de fato precisar. Isso existe por performance: com centenas de milhares de linhas, calcular tudo sempre seria lento à toa.
- **Saída:** um dicionário `{ granularidade: { chave_do_relatorio: DataFrame } }`, que os três exportadores (Excel/PDF/Word) percorrem pra gerar uma aba/seção por combinação de relatório × granularidade.

## Catálogo de relatórios (aba "Relatório Padrão")

O que aparece marcável na interface, em `CATALOGO_RELATORIOS` (`app.py`):

### Vendas

| Chave | Rótulo | Função | O que é |
|---|---|---|---|
| `top_clientes` | Venda por Cliente (Top Clientes) | `top_produtos`/`top_clientes`/`top_fabricantes` | Top 20 por Receita (soma de todo o período carregado, **não** respeita granularidade) |
| `top_fabricantes` | Venda por Fabricante (Top Fabricantes) | idem | idem, agrupado por `NOME_FABRICANTE` |
| `top_produtos` | Venda por Produto (Top Produtos) | idem | idem, agrupado por `descricao` |

Essas três são as únicas do catálogo que **não variam por granularidade** — somam a base inteira, sempre.

### Segmentação e Poder de Compra

| Chave | Rótulo | Função | O que é |
|---|---|---|---|
| `abc` | Faturamento e Segmentação de Clientes (ABC) | `classificar_abc` → `classificar_faixas` | Por período, ordena clientes por receita e divide em faixas por % acumulado (`Grupo 1/2/3/Demais`, cortes padrão 30/50/60%). Cada linha também traz `Frequencia_Simples/Acumulada` (nº de meses com compra) e `Renuncia*` (queda de receita vs. período anterior). |
| `poder_compra_clientes` | Poder de Compra por Cliente (Renúncia) | `poder_compra_clientes()` | Recorte de colunas do ABC (mesma base), focado em frequência + renúncia. |
| `migracao_abc` | Migração de Clientes entre Faixas | `migracao_abc()` | Compara faixa ABC de um período pro próximo; lista quem subiu/desceu, com uma "causa provável" heurística (produto abandonado, queda de frequência, queda de ticket médio, produto novo). |

### Tendências e Alertas

| Chave | Rótulo | Função | O que é |
|---|---|---|---|
| `evolucao_produtos` | Tendência de Produtos | `tendencia_produtos()` | Receita/QTD por produto e período, com variação % vs. período anterior. |
| `alertas_queda` | Alertas de Queda Consecutiva | idem (segundo retorno) | Produtos com N períodos seguidos de queda (N = "Períodos seguidos em queda p/ alerta" na interface, padrão 2). |
| `erosao_clientes` | Erosão de Clientes por Produto | `erosao_clientes_por_produto()` | Por produto+cliente, quem reduziu ou zerou a compra entre períodos consecutivos. Se "Alertas de Queda" foi calculado, essa análise é restrita aos produtos já sinalizados lá (senão roda para todos). |

### Boletins

| Chave | Rótulo | Função | O que é |
|---|---|---|---|
| `produtos_em_alta` / `produtos_em_queda` | Boletim: Produtos em Alta/Queda | `produtos_alta_e_queda()` | Compara só os **dois últimos períodos** da granularidade escolhida (não a série toda); top 10 por variação % positiva/negativa. |
| `clientes_queda_qtd` | Boletim: Clientes em Queda de Quantidade | `clientes_queda_quantidade()` | Idem, mas por cliente e por QTD (não receita); aponta o "produto crítico" que mais puxou a queda. |
| `correlacao_produto_cliente` | Boletim: Correlação Produto x Cliente | `correlacao_produto_cliente()` | Top eventos de erosão, classificados heuristicamente: "Abandono de Categoria" (≥3 clientes largaram o mesmo produto no mesmo período), "Fim de Ciclo" (produto já está em alerta de queda), "Ruptura Estratégica" (parou de comprar produto que era ≥70% do que comprava dele), ou "Caso Específico". |
| `impacto_financeiro_churn` | Boletim: Impacto Financeiro do Churn | `impacto_financeiro_churn()` | 3 KPIs agregados: maior retração individual (%), receita total sob risco (soma das reduções de erosão), variação global de receita entre os 2 últimos períodos. |

### Existe mas não aparece no catálogo

- `abc_produtos` (`classificar_produtos_por_receita`) — classificação de produtos por representatividade (Grupo 1 = top X% da receita, padrão 80%). A função existe e é usada pela prévia de "Corte de produtos" na tela de Configurações, mas foi removida do catálogo de relatórios prontos (decisão de um commit anterior) — hoje só é gerada se algo internamente pedir a chave `"abc_produtos"`.

## Parâmetros que afetam vários relatórios ao mesmo tempo

- **Clientes excluídos** (lista marcada em Configurações): removidos da base antes de qualquer cálculo de ABC/frequência/renúncia — não aparecem em nenhum relatório dependente disso.
- **Produtos considerados** (lista de Configurações): filtra o DataFrame inteiro antes de rodar `gerar_analises_completas` — afeta literalmente todos os relatórios, não só os de produto.
- **Cortes de grupo (30/50/60%)** e **corte de produtos (80%)**: só afetam ABC de clientes e a prévia de produtos, respectivamente.
- **"Desconsiderar clientes balcão da frequência"** (checkbox): ver seção de inconsistência conhecida abaixo — hoje só funciona de verdade na prévia da tela, não no relatório exportado.
- **Nome da empresa analisada**: não afeta cálculo nenhum — só aparece na capa e no nome do arquivo exportado.

## ⚠️ Inconsistência conhecida: prévia vs. relatório oficial

Existem hoje **duas versões** da mesma lógica de classificação, e só uma delas foi corrigida recentemente:

| Lógica | Função "prévia" (tela de Configurações) | Função "oficial" (relatório exportado) |
|---|---|---|
| Faixa de cliente balcão | `classificar_clientes_agregado()` — ✅ corrigido: fica em faixa **"Balcão"** própria, com % real de receita | `classificar_faixas()` (usada por `classificar_abc`, que alimenta o relatório **ABC** de verdade) — ❌ ainda com o comportamento antigo: zera `Percentual_Acumulado` e força pra dentro de **"Grupo 1"** |
| Frequência de produto | `classificar_produtos_agregado()` — ✅ já é % de receita (`Freq_Simples`/`Freq_Acumulado`) | `calcular_frequencia()` (usada por `classificar_faixas`/`classificar_produtos_por_receita`) — ❌ ainda conta nº de meses com compra, não % de receita |

Ou seja: quem olhar a prévia na tela vê um número/comportamento; quem abrir o Excel/PDF gerado pode ver outro, pro mesmo cliente/produto. Vale decidir, ao mexer nisso, se a correção deve ser propagada pra `classificar_faixas`/`calcular_frequencia` (usadas pelo relatório de verdade) também.

## Relatórios Personalizados (`pivot_builder.py`)

Tabela dinâmica livre (`pandas.pivot_table`, com `margins=True` = linha/coluna de "Total Geral"): o usuário arrasta campos para Linhas / Colunas / Valores (com agregação: Soma, Contagem, Média, Mínimo, Máximo) / Filtros. Campos disponíveis: os brutos do CSV (`Cliente`, `descricao`, `NOME_FABRICANTE`, `Loja`, `Receita`, `QTD`, `Data_Venda`) mais os calculados (`Faixa_ABC`, `Periodo_Mensal/Trimestral/Semestral/Anual`). Configurações de relatório podem ser salvas/carregadas em JSON. Cada relatório personalizado nomeado vira uma aba extra (`Custom_<nome>`) no Excel exportado — não entra em PDF/Word.

## Gráficos (`graficos.py`)

Quatro visualizações de dispersão (scatter), sempre coloridas por `Faixa_ABC` do cliente (última classificação disponível), exceto onde indicado:

1. **Vendas por Fabricante** — QTD × Receita, um ponto por (fabricante, cliente).
2. **Vendas por Produto** — QTD × Receita por (produto, cliente); pode colorir por Faixa ABC **ou** por Fabricante.
3. **Receita Agrupada** — receita total por Fabricante ou por Produto, ordenado decrescente (sem cor por faixa).
4. **Afinidade Cliente × Fabricante** — % do faturamento do cliente que vem daquele fabricante (eixo X) × frequência de compra (eixo Y).

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
