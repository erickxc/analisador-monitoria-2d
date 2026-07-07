# Analisador Inteligente — 2D Consultores | Monitores

Sistema desktop para análise de vendas a partir de um CSV, com geração de relatórios em Excel (com a logo da empresa), construtor de tabelas dinâmicas (arrastar-e-soltar) e gráficos de dispersão.

## Estrutura

- `analise_funil.py` — motor de análise (sem GUI, testável isoladamente).
- `pivot_builder.py` — construtor de relatórios personalizados (pivot table com drag-and-drop).
- `graficos.py` — gráficos de dispersão embutidos (matplotlib).
- `app.py` — interface principal (Tkinter, com abas), ponto de entrada da aplicação.
- `splash.py` — tela inicial (logo + loader) exibida enquanto os módulos pesados carregam.
- `perfil.py` — perfil local do usuário (nome, tamanho de fonte), salvo em SQLite.
- `recursos.py` — resolução de caminhos (logo, pasta de dados locais) compatível com dev e `.exe`.
- `atualizacoes.py` — checagem de nova versão publicada como Release no GitHub.
- `assets/` — logo da empresa (`logo_2d.png` e `logo_2d.ico`).

Pastas geradas em tempo de execução (ao lado do executável, não versionadas):
- `logs/` — um arquivo de log por sessão.
- `dados_locais/perfil.db` — perfil do usuário desta instalação (não é embutido no `.exe`; se você compartilhar o executável, cada pessoa terá o próprio perfil).

## Instalação

```bash
pip install -r requirements.txt
```

## Rodando em modo desenvolvimento

```bash
python app.py
```

Ao abrir, uma tela de splash com a logo aparece enquanto os motores de análise são preparados; em seguida a janela principal abre com tema visual moderno ([sv-ttk](https://github.com/rdbende/Sun-Valley-ttk-theme), estilo Windows 11 — alterne para escuro em Exibir > Tema escuro ou `Ctrl+D`) e 5 abas:

**Atalhos de teclado:** `Ctrl+O` selecionar CSV, `Ctrl+G` gerar relatório padrão, `F5` atualizar prévia dos grupos, `Ctrl+D` alternar tema claro/escuro, `Ctrl+Q` sair, `F1` sobre.

1. **Configurações** — selecione o CSV de vendas, marque clientes a excluir e produtos a considerar (produtos sem descrição aparecem agrupados como "Não harmonizados"), ajuste os cortes de segmentação e as granularidades. Use "Sugerir cortes automaticamente" para limitar clientes por grupo, e "Atualizar prévia dos grupos" sempre que mudar alguma marcação (o botão avisa quando há mudança pendente).
2. **Relatório Padrão** — escolha, em um catálogo, quais relatórios prontos quer no Excel final (Venda por Cliente, por Fabricante, por Produto, Segmentação ABC, Poder de Compra, Migração, Tendências, Boletim de Churn etc.) e clique em "Gerar Relatório Padrão".
3. **Relatórios Personalizados** — arraste campos para Linhas/Colunas/Valores/Filtros (ou use os botões "➜"/"⟵") e clique em "Gerar". Esses relatórios também podem ser exportados como abas extras no próximo Excel gerado.
4. **Gráficos** — escolha o tipo de dispersão e clique em "Plotar"; "Exportar PNG" salva a imagem.
5. **Perfil** — nome e tamanho de fonte, salvos localmente nesta máquina.

O painel "Execução" (log + barra de progresso), na parte inferior da janela, é visível em qualquer aba.

## Testando o motor isoladamente

```bash
python -c "
import analise_funil as af
df = af.carregar_csv('caminho/para/vendas.csv')
print(af.top_produtos(df))
"
```

## Gerando o executável Windows (PyInstaller)

```bash
pyinstaller AnalisadorInteligente.spec
```

O spec já cobre os dados/hidden imports necessários (`assets/`, tema `sv-ttk`, `reportlab` para os relatórios em PDF). O executável final fica em `dist/AnalisadorInteligente.exe`. Na primeira execução em cada máquina, ele cria as pastas `logs/` e `dados_locais/` ao lado do `.exe`.

Para o processo completo de versionamento e publicação de uma release (que é o que aciona o aviso de atualização para quem já tem o `.exe`), veja [CONTRIBUTING.md](CONTRIBUTING.md).

## Formato esperado do CSV

Separador `;`, encoding `utf-8-sig`, colunas: `Loja`, `NOME_FABRICANTE`, `Cliente`, `descricao`, `Ano`, `Mês` (nome por extenso em português), `Código Interno`, `Código de referêcia`, `Receita Acumulada 11 Meses` (formato BR com vírgula decimal), `QTD`.
