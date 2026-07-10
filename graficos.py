"""
Gráficos do funil de vendas, usando matplotlib embutido no Tkinter.

Cada função `desenhar_*` recebe um objeto Axes do matplotlib e o DataFrame já
tratado, desenha o gráfico nele (permite reaproveitar a mesma figura ao
trocar de view na interface) e RETORNA o DataFrame agregado que usou pra
plotar — isso alimenta tanto a legenda/eixos quanto a exportação pra Excel
(mesma tabela que está no gráfico, não a base bruta). Também expõe funções
de exportação PNG/Excel.
"""

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd


def _mapa_cores_categorico(categorias):
    """
    N cores discretas de um colormap, pra colorir séries por categoria (ex.:
    fabricante). matplotlib removeu cm.get_cmap/plt.get_cmap nas versões mais
    recentes — o registro atual é matplotlib.colormaps.
    """
    return matplotlib.colormaps["tab20"].resampled(max(len(categorias), 1))

PALETA_FAIXAS = ["#2e7d32", "#1565c0", "#f9a825", "#8e24aa", "#00897b", "#c62828"]
COR_FAIXA_DEMAIS = "#9e9e9e"
COR_PADRAO = "#1565c0"


def _cores_por_faixa(faixas):
    """
    Monta um mapa {faixa: cor} de forma determinística e estável: as faixas
    "Grupo N" recebem cores fixas da paleta (por ordem de N) e "Demais"
    sempre fica cinza, independente de quantos grupos existirem.
    """
    faixas_grupo = sorted(
        [f for f in faixas if f != "Demais"],
        key=lambda nome: int(nome.split()[-1]) if nome.split()[-1].isdigit() else 99,
    )
    mapa = {nome: PALETA_FAIXAS[i % len(PALETA_FAIXAS)] for i, nome in enumerate(faixas_grupo)}
    if "Demais" in faixas:
        mapa["Demais"] = COR_FAIXA_DEMAIS
    return mapa


def _abc_do_cliente(df, abc_df):
    """
    Mapeia cada cliente para sua Faixa_ABC mais recente (última classificação
    disponível no abc_df), para poder colorir os gráficos por faixa.
    """
    if abc_df is None or abc_df.empty:
        return {}
    ultima_por_cliente = abc_df.sort_values("Periodo").groupby("Cliente").tail(1)
    return dict(zip(ultima_por_cliente["Cliente"], ultima_por_cliente["Faixa_ABC"]))


def _preparar_fatias_pizza(rotulos, valores, max_fatias=10):
    """
    Agrupa tudo além das (max_fatias - 1) maiores fatias numa fatia única
    "Outros" — uma pizza com dezenas de fatias finas é ilegível.
    """
    pares = sorted(zip(rotulos, valores), key=lambda par: par[1], reverse=True)
    if len(pares) <= max_fatias:
        return [p[0] for p in pares], [p[1] for p in pares]
    principais = pares[: max_fatias - 1]
    resto = sum(v for _, v in pares[max_fatias - 1 :])
    return [p[0] for p in principais] + ["Outros"], [p[1] for p in principais] + [resto]


def desenhar_vendas_por_fabricante(ax, df, abc_df, colorir_por="Faixa_ABC", estilo="Dispersão", valor_minimo=0.0):
    """
    Vendas por fabricante. Dispersão: um ponto por combinação
    fabricante+cliente (QTD x Receita), colorido por Faixa_ABC do cliente OU
    pelo próprio fabricante. Barras: receita total por fabricante, ranking.
    """
    ax.clear()

    if estilo == "Barras":
        agrupado = df.groupby("NOME_FABRICANTE", as_index=False).agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
        agrupado = agrupado[agrupado["Receita"] >= valor_minimo]
        agrupado.sort_values("Receita", ascending=False, inplace=True)
        ax.bar(range(len(agrupado)), agrupado["Receita"], color=COR_PADRAO)
        ax.set_xticks(range(len(agrupado)))
        ax.set_xticklabels(agrupado["NOME_FABRICANTE"], rotation=90, fontsize=6)
        ax.set_ylabel("Receita (R$)")
        ax.set_title("Receita por Fabricante")
        return agrupado

    mapa_abc = _abc_do_cliente(df, abc_df)
    agrupado = df.groupby(["NOME_FABRICANTE", "Cliente"], as_index=False).agg(
        Receita=("Receita", "sum"), QTD=("QTD", "sum")
    )
    agrupado = agrupado[agrupado["Receita"] >= valor_minimo]

    if colorir_por == "Fabricante":
        agrupado["_cor_categoria"] = agrupado["NOME_FABRICANTE"]
    else:
        colorir_por = "Faixa_ABC"
        agrupado["_cor_categoria"] = agrupado["Cliente"].map(mapa_abc).fillna("Demais")

    if colorir_por == "Faixa_ABC":
        cores = _cores_por_faixa(agrupado["_cor_categoria"].unique())
        for categoria, cor in cores.items():
            subconjunto = agrupado[agrupado["_cor_categoria"] == categoria]
            ax.scatter(subconjunto["QTD"], subconjunto["Receita"], c=cor, label=categoria, alpha=0.6)
        ax.legend(title="Faixa ABC")
    else:
        categorias = agrupado["_cor_categoria"].unique()
        mapa_cores = _mapa_cores_categorico(categorias)
        for i, categoria in enumerate(categorias):
            subconjunto = agrupado[agrupado["_cor_categoria"] == categoria]
            ax.scatter(subconjunto["QTD"], subconjunto["Receita"], color=mapa_cores(i), label=categoria, alpha=0.6)
        ax.legend(title="Fabricante", fontsize="x-small", ncol=2)

    ax.set_xlabel("Quantidade Vendida")
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Vendas por Fabricante (cor = {colorir_por})")
    return agrupado.drop(columns=["_cor_categoria"])


def desenhar_vendas_por_produto(ax, df, abc_df, colorir_por="Faixa_ABC", estilo="Dispersão", valor_minimo=0.0):
    """View: dispersão QTD x Receita por produto, cor = fabricante ou Faixa_ABC; ou Barras (receita total por produto)."""
    ax.clear()

    if estilo == "Barras":
        agrupado = df.groupby("descricao", as_index=False).agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
        agrupado = agrupado[agrupado["Receita"] >= valor_minimo]
        agrupado.sort_values("Receita", ascending=False, inplace=True)
        ax.bar(range(len(agrupado)), agrupado["Receita"], color=COR_PADRAO)
        ax.set_xticks(range(len(agrupado)))
        ax.set_xticklabels(agrupado["descricao"], rotation=90, fontsize=6)
        ax.set_ylabel("Receita (R$)")
        ax.set_title("Receita por Produto")
        return agrupado

    if colorir_por == "Faixa_ABC":
        mapa_abc = _abc_do_cliente(df, abc_df)
        agrupado = df.groupby(["descricao", "Cliente"], as_index=False).agg(
            Receita=("Receita", "sum"), QTD=("QTD", "sum")
        )
        agrupado = agrupado[agrupado["Receita"] >= valor_minimo]
        agrupado["Faixa_ABC"] = agrupado["Cliente"].map(mapa_abc).fillna("Demais")
        cores = _cores_por_faixa(agrupado["Faixa_ABC"].unique())
        for faixa, cor in cores.items():
            subconjunto = agrupado[agrupado["Faixa_ABC"] == faixa]
            ax.scatter(subconjunto["QTD"], subconjunto["Receita"], c=cor, label=faixa, alpha=0.6)
        ax.legend(title="Faixa")
    else:
        agrupado = df.groupby(["descricao", "NOME_FABRICANTE"], as_index=False).agg(
            Receita=("Receita", "sum"), QTD=("QTD", "sum")
        )
        agrupado = agrupado[agrupado["Receita"] >= valor_minimo]
        fabricantes = agrupado["NOME_FABRICANTE"].unique()
        mapa_cores = _mapa_cores_categorico(fabricantes)
        for i, fabricante in enumerate(fabricantes):
            subconjunto = agrupado[agrupado["NOME_FABRICANTE"] == fabricante]
            ax.scatter(subconjunto["QTD"], subconjunto["Receita"], color=mapa_cores(i), label=fabricante, alpha=0.6)
        ax.legend(title="Fabricante", fontsize="x-small", ncol=2)

    ax.set_xlabel("Quantidade Vendida")
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Vendas por Produto (cor = {colorir_por})")
    return agrupado


def _piramide_comparativa(ax, df, campo, top_n, valor_minimo, rotulo_campo):
    """
    Gráfico de pirâmide (estilo IBGE): barras horizontais espelhadas
    comparando a receita do período mais recente (direita) com a do período
    anterior (esquerda), por categoria — top_n maiores pela soma dos dois
    períodos. Dá pra ver de cara quem cresceu (barra da direita maior) ou
    caiu (barra da esquerda maior) entre os dois períodos mais recentes.
    """
    periodos = sorted(df["Periodo_Mensal"].dropna().unique().tolist())
    if len(periodos) < 2:
        raise ValueError("É preciso pelo menos 2 períodos na base para montar a pirâmide comparativa.")
    periodo_anterior, periodo_atual = periodos[-2], periodos[-1]

    base = df[df["Periodo_Mensal"].isin([periodo_anterior, periodo_atual])]
    pivot = base.groupby([campo, "Periodo_Mensal"])["Receita"].sum().unstack("Periodo_Mensal").fillna(0.0)
    for periodo in (periodo_anterior, periodo_atual):
        if periodo not in pivot.columns:
            pivot[periodo] = 0.0
    pivot["_total"] = pivot[periodo_anterior] + pivot[periodo_atual]
    pivot = pivot[pivot["_total"] >= valor_minimo]
    pivot.sort_values("_total", ascending=True, inplace=True)
    pivot = pivot.tail(top_n)

    posicoes = range(len(pivot))
    ax.barh(posicoes, -pivot[periodo_anterior], color="#c62828", label=str(periodo_anterior))
    ax.barh(posicoes, pivot[periodo_atual], color=COR_PADRAO, label=str(periodo_atual))
    ax.set_yticks(list(posicoes))
    ax.set_yticklabels(pivot.index, fontsize=7)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{abs(x):,.0f}"))
    ax.set_xlabel(f"Receita (R$) — {periodo_anterior} à esquerda, {periodo_atual} à direita")
    ax.set_title(f"Pirâmide comparativa de {rotulo_campo}: {periodo_anterior} vs {periodo_atual}")
    ax.legend()

    return pivot[[periodo_anterior, periodo_atual]].reset_index()


def desenhar_receita_agrupada(ax, df, agrupar_por="NOME_FABRICANTE", estilo="Dispersão", valor_minimo=0.0):
    """View: receita agregada por fabricante ou por produto — Dispersão, Barras, Pizza ou Pirâmide."""
    ax.clear()
    campo = "NOME_FABRICANTE" if agrupar_por == "Fabricante" else "descricao"

    if estilo == "Pirâmide":
        return _piramide_comparativa(ax, df, campo, top_n=15, valor_minimo=valor_minimo, rotulo_campo=agrupar_por)

    agrupado = df.groupby(campo, as_index=False).agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
    agrupado = agrupado[agrupado["Receita"] >= valor_minimo]
    agrupado.sort_values("Receita", ascending=False, inplace=True)

    if estilo == "Pizza":
        rotulos, valores = _preparar_fatias_pizza(agrupado[campo].tolist(), agrupado["Receita"].tolist())
        ax.pie(valores, labels=rotulos, autopct="%1.1f%%", textprops={"fontsize": 7})
        ax.set_title(f"Participação de Receita por {agrupar_por}")
        return agrupado

    if estilo == "Barras":
        ax.bar(range(len(agrupado)), agrupado["Receita"], color=COR_PADRAO)
    else:
        ax.scatter(range(len(agrupado)), agrupado["Receita"], c=COR_PADRAO, alpha=0.7)
    ax.set_xticks(range(len(agrupado)))
    ax.set_xticklabels(agrupado[campo], rotation=90, fontsize=6)
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Receita por {agrupar_por}")
    return agrupado


def desenhar_top_clientes(ax, df, top_n=20, estilo="Barras", valor_minimo=0.0):
    """
    Os top_n clientes de maior receita (soma de todo o período carregado).
    Histograma ignora o corte top_n — mostra a distribuição de receita entre
    TODOS os clientes, não só os maiores.
    """
    ax.clear()
    if estilo == "Pirâmide":
        return _piramide_comparativa(ax, df, "Cliente", top_n=top_n, valor_minimo=valor_minimo, rotulo_campo="Clientes")

    agrupado_completo = df.groupby("Cliente", as_index=False).agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
    agrupado_completo = agrupado_completo[agrupado_completo["Receita"] >= valor_minimo]
    agrupado_completo.sort_values("Receita", ascending=False, inplace=True)

    if estilo == "Histograma":
        ax.hist(agrupado_completo["Receita"], bins=20, color=COR_PADRAO, edgecolor="white")
        ax.set_xlabel("Receita (R$)")
        ax.set_ylabel("Nº de clientes")
        ax.set_title("Distribuição de Receita entre Clientes")
        return agrupado_completo

    agrupado = agrupado_completo.head(top_n)
    if estilo == "Pizza":
        rotulos, valores = _preparar_fatias_pizza(agrupado["Cliente"].tolist(), agrupado["Receita"].tolist())
        ax.pie(valores, labels=rotulos, autopct="%1.1f%%", textprops={"fontsize": 7})
        ax.set_title(f"Participação dos Top {top_n} Clientes")
        return agrupado

    if estilo == "Dispersão":
        ax.scatter(range(len(agrupado)), agrupado["Receita"], c=COR_PADRAO, alpha=0.7)
    else:
        ax.bar(range(len(agrupado)), agrupado["Receita"], color=COR_PADRAO)
    ax.set_xticks(range(len(agrupado)))
    ax.set_xticklabels(agrupado["Cliente"], rotation=90, fontsize=6)
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Top {top_n} Clientes por Receita")
    return agrupado


def desenhar_top_fabricantes(ax, df, top_n=20, estilo="Barras", valor_minimo=0.0):
    """Mesmo tratamento de desenhar_top_clientes, por fabricante."""
    ax.clear()
    if estilo == "Pirâmide":
        return _piramide_comparativa(ax, df, "NOME_FABRICANTE", top_n=top_n, valor_minimo=valor_minimo, rotulo_campo="Fabricantes")

    agrupado_completo = df.groupby("NOME_FABRICANTE", as_index=False).agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
    agrupado_completo = agrupado_completo[agrupado_completo["Receita"] >= valor_minimo]
    agrupado_completo.sort_values("Receita", ascending=False, inplace=True)

    if estilo == "Histograma":
        ax.hist(agrupado_completo["Receita"], bins=20, color=COR_PADRAO, edgecolor="white")
        ax.set_xlabel("Receita (R$)")
        ax.set_ylabel("Nº de fabricantes")
        ax.set_title("Distribuição de Receita entre Fabricantes")
        return agrupado_completo

    agrupado = agrupado_completo.head(top_n)
    if estilo == "Pizza":
        rotulos, valores = _preparar_fatias_pizza(agrupado["NOME_FABRICANTE"].tolist(), agrupado["Receita"].tolist())
        ax.pie(valores, labels=rotulos, autopct="%1.1f%%", textprops={"fontsize": 7})
        ax.set_title(f"Participação dos Top {top_n} Fabricantes")
        return agrupado

    if estilo == "Dispersão":
        ax.scatter(range(len(agrupado)), agrupado["Receita"], c=COR_PADRAO, alpha=0.7)
    else:
        ax.bar(range(len(agrupado)), agrupado["Receita"], color=COR_PADRAO)
    ax.set_xticks(range(len(agrupado)))
    ax.set_xticklabels(agrupado["NOME_FABRICANTE"], rotation=90, fontsize=6)
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Top {top_n} Fabricantes por Receita")
    return agrupado


def desenhar_afinidade_cliente_fabricante(ax, df, abc_df, valor_minimo=0.0):
    """
    Por cliente, participação % de cada fabricante no faturamento do
    cliente (eixo X) x frequência de compra desse fabricante (eixo Y),
    colorido por Faixa_ABC. Só dispersão — são 2 eixos contínuos, não reduz
    bem a categorias (barras/pizza/histograma).
    """
    ax.clear()
    mapa_abc = _abc_do_cliente(df, abc_df)

    receita_cliente_fabricante = df.groupby(["Cliente", "NOME_FABRICANTE"], as_index=False).agg(
        Receita=("Receita", "sum"), Frequencia=("Data_Venda", "nunique")
    )
    receita_cliente_fabricante = receita_cliente_fabricante[receita_cliente_fabricante["Receita"] >= valor_minimo]
    receita_total_cliente = df.groupby("Cliente")["Receita"].sum().rename("Receita_Total_Cliente")
    receita_cliente_fabricante = receita_cliente_fabricante.merge(
        receita_total_cliente, on="Cliente", how="left"
    )
    receita_cliente_fabricante["Participacao_Percentual"] = (
        receita_cliente_fabricante["Receita"] / receita_cliente_fabricante["Receita_Total_Cliente"] * 100
    )
    receita_cliente_fabricante["Faixa_ABC"] = receita_cliente_fabricante["Cliente"].map(mapa_abc).fillna("Demais")

    cores = _cores_por_faixa(receita_cliente_fabricante["Faixa_ABC"].unique())
    for faixa, cor in cores.items():
        subconjunto = receita_cliente_fabricante[receita_cliente_fabricante["Faixa_ABC"] == faixa]
        ax.scatter(
            subconjunto["Participacao_Percentual"], subconjunto["Frequencia"],
            c=cor, label=faixa, alpha=0.6,
        )

    ax.set_xlabel("Participação do fabricante no faturamento do cliente (%)")
    ax.set_ylabel("Frequência de compra (nº de meses distintos)")
    ax.set_title("Afinidade Cliente x Fabricante (cor = Faixa)")
    ax.legend(title="Faixa")
    return receita_cliente_fabricante


def desenhar_evolucao_temporal(ax, df, agrupar_por="Nenhum", top_n=5, estilo="Linha"):
    """
    Receita por Periodo_Mensal ao longo do tempo: "Nenhum" soma a base
    inteira numa única série; Fabricante/Produto/Cliente traça uma série por
    categoria, limitada aos top_n de maior receita total (senão o gráfico
    fica ilegível com dezenas de linhas/barras sobrepostas).
    """
    ax.clear()
    campo = {"Fabricante": "NOME_FABRICANTE", "Produto": "descricao", "Cliente": "Cliente"}.get(agrupar_por)

    if campo is None:
        agrupado = df.groupby("Periodo_Mensal", as_index=False)["Receita"].sum()
        agrupado.sort_values("Periodo_Mensal", inplace=True)
        if estilo == "Barras":
            ax.bar(agrupado["Periodo_Mensal"], agrupado["Receita"], color=COR_PADRAO)
        else:
            ax.plot(agrupado["Periodo_Mensal"], agrupado["Receita"], marker="o", color=COR_PADRAO)
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.set_ylabel("Receita (R$)")
        ax.set_title("Evolução de Receita no Tempo")
        return agrupado

    top_categorias = df.groupby(campo)["Receita"].sum().sort_values(ascending=False).head(top_n).index
    base = df[df[campo].isin(top_categorias)]
    pivot = base.groupby([campo, "Periodo_Mensal"])["Receita"].sum().unstack(campo).fillna(0.0)
    pivot.sort_index(inplace=True)

    if estilo == "Barras":
        pivot.plot(kind="bar", ax=ax)
    else:
        for categoria in pivot.columns:
            ax.plot(pivot.index, pivot[categoria], marker="o", label=categoria)
        ax.legend(fontsize="x-small")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Evolução de Receita por {agrupar_por} (Top {top_n})")
    return pivot.reset_index()


ESTILOS_POR_VIEW = {
    "Vendas por Fabricante": ["Dispersão", "Barras"],
    "Vendas por Produto": ["Dispersão", "Barras"],
    "Receita por Fabricante ou Produto": ["Barras", "Dispersão", "Pizza", "Pirâmide"],
    "Afinidade Cliente-Fabricante": ["Dispersão"],
    "Top Clientes por Receita": ["Barras", "Dispersão", "Pizza", "Histograma", "Pirâmide"],
    "Top Fabricantes por Receita": ["Barras", "Dispersão", "Pizza", "Histograma", "Pirâmide"],
    "Evolução no Tempo": ["Linha", "Barras"],
}


class PainelGraficosFrame(ttk.Frame):
    """Aba de gráficos: seletor de view/estilo + filtros + área de plotagem embutida + exportar PNG/Excel."""

    VIEWS = [
        "Vendas por Fabricante",
        "Vendas por Produto",
        "Receita por Fabricante ou Produto",
        "Afinidade Cliente-Fabricante",
        "Top Clientes por Receita",
        "Top Fabricantes por Receita",
        "Evolução no Tempo",
    ]

    def __init__(self, master, obter_dataframe, obter_abc_df):
        super().__init__(master)
        self.obter_dataframe = obter_dataframe
        self.obter_abc_df = obter_abc_df
        self._ultima_tabela = None

        self._montar_interface()

    def _montar_interface(self):
        linha1 = ttk.Frame(self)
        linha1.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(linha1, text="Tipo de gráfico:").pack(side="left")
        self.combo_view = ttk.Combobox(linha1, values=self.VIEWS, state="readonly", width=28)
        self.combo_view.current(0)
        self.combo_view.pack(side="left", padx=4)
        self.combo_view.bind("<<ComboboxSelected>>", lambda evento: self._atualizar_opcoes())

        ttk.Label(linha1, text="Estilo:").pack(side="left", padx=(12, 0))
        self.combo_estilo = ttk.Combobox(linha1, values=[], state="readonly", width=12)
        self.combo_estilo.pack(side="left", padx=4)
        self.combo_estilo.bind("<<ComboboxSelected>>", lambda evento: self._atualizar_opcoes())

        self.label_opcao = ttk.Label(linha1, text="Colorir/Agrupar por:")
        self.label_opcao.pack(side="left", padx=(12, 0))
        self.combo_opcao = ttk.Combobox(linha1, values=[], state="readonly", width=15)
        self.combo_opcao.pack(side="left", padx=4)

        self.label_opcao2 = ttk.Label(linha1, text="Quantidade de séries:")
        self.combo_opcao2 = ttk.Combobox(linha1, values=["3", "5", "10"], state="readonly", width=6)

        linha2 = ttk.Frame(self)
        linha2.pack(fill="x", padx=8, pady=(0, 4))

        ttk.Label(linha2, text="Período de:").pack(side="left")
        self.combo_periodo_de = ttk.Combobox(linha2, values=[], state="readonly", width=10)
        self.combo_periodo_de.pack(side="left", padx=4)
        ttk.Label(linha2, text="até:").pack(side="left")
        self.combo_periodo_ate = ttk.Combobox(linha2, values=[], state="readonly", width=10)
        self.combo_periodo_ate.pack(side="left", padx=4)

        ttk.Label(linha2, text="Valor mínimo (R$):").pack(side="left", padx=(12, 0))
        self.entrada_valor_minimo = ttk.Entry(linha2, width=10)
        self.entrada_valor_minimo.insert(0, "0")
        self.entrada_valor_minimo.pack(side="left", padx=4)

        ttk.Button(linha2, text="Plotar", command=self._plotar).pack(side="left", padx=(12, 4))
        ttk.Button(linha2, text="Exportar PNG", command=self._exportar_png).pack(side="left", padx=4)
        ttk.Button(linha2, text="Exportar Excel", command=self._exportar_excel).pack(side="left", padx=4)

        self.figura, self.eixo = plt.subplots(figsize=(8, 5))
        self.canvas = FigureCanvasTkAgg(self.figura, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        barra_ferramentas = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        barra_ferramentas.pack(fill="x", padx=8)

        self._atualizar_opcoes()

    def _mostrar_opcao2(self, mostrar):
        if mostrar:
            self.label_opcao2.pack(side="left", padx=(12, 0))
            self.combo_opcao2.pack(side="left", padx=4)
            if not self.combo_opcao2.get():
                self.combo_opcao2.current(1)
        else:
            self.label_opcao2.pack_forget()
            self.combo_opcao2.pack_forget()

    def _atualizar_opcoes(self):
        view = self.combo_view.get()
        estilos_disponiveis = ESTILOS_POR_VIEW.get(view, ["Dispersão"])
        self.combo_estilo["values"] = estilos_disponiveis
        if self.combo_estilo.get() not in estilos_disponiveis:
            self.combo_estilo.current(0)
        estilo = self.combo_estilo.get()

        self.label_opcao.config(text="Colorir/Agrupar por:")
        self._mostrar_opcao2(False)

        if view in ("Vendas por Fabricante", "Vendas por Produto") and estilo == "Dispersão":
            self.combo_opcao["values"] = ["Faixa_ABC", "Fabricante"]
            self.combo_opcao.current(0)
        elif view == "Receita por Fabricante ou Produto":
            self.combo_opcao["values"] = ["Fabricante", "Produto"]
            self.combo_opcao.current(0)
        elif view in ("Top Clientes por Receita", "Top Fabricantes por Receita") and estilo != "Histograma":
            entidade = "clientes" if view.startswith("Top Clientes") else "fabricantes"
            self.label_opcao.config(text=f"Quantidade de {entidade}:")
            self.combo_opcao["values"] = ["10", "20", "50", "100"]
            self.combo_opcao.current(1)
        elif view == "Evolução no Tempo":
            self.label_opcao.config(text="Agrupar por:")
            self.combo_opcao["values"] = ["Nenhum", "Fabricante", "Produto", "Cliente"]
            self.combo_opcao.current(0)
            self._mostrar_opcao2(True)
        else:
            self.combo_opcao["values"] = []
            self.combo_opcao.set("")

    def _atualizar_periodos_disponiveis(self, df):
        if "Periodo_Mensal" not in df.columns:
            return
        periodos = sorted(df["Periodo_Mensal"].dropna().unique().tolist())
        if not periodos or list(self.combo_periodo_de["values"]) == periodos:
            return
        self.combo_periodo_de["values"] = periodos
        self.combo_periodo_ate["values"] = periodos
        self.combo_periodo_de.set(periodos[0])
        self.combo_periodo_ate.set(periodos[-1])

    def _plotar(self):
        df = self.obter_dataframe()
        if df is None:
            messagebox.showwarning("Gráficos", "Carregue um CSV primeiro na aba Relatório Padrão.")
            return

        self._atualizar_periodos_disponiveis(df)
        periodo_de, periodo_ate = self.combo_periodo_de.get(), self.combo_periodo_ate.get()
        if periodo_de and periodo_ate:
            df = df[(df["Periodo_Mensal"] >= periodo_de) & (df["Periodo_Mensal"] <= periodo_ate)]
            if df.empty:
                messagebox.showwarning("Gráficos", "Nenhuma venda no período selecionado.")
                return

        try:
            valor_minimo = float(self.entrada_valor_minimo.get().replace(",", ".").strip() or 0)
        except ValueError:
            valor_minimo = 0.0

        abc_df = self.obter_abc_df()
        view = self.combo_view.get()
        estilo = self.combo_estilo.get()
        opcao = self.combo_opcao.get()

        try:
            if view == "Vendas por Fabricante":
                tabela = desenhar_vendas_por_fabricante(
                    self.eixo, df, abc_df, colorir_por=opcao or "Faixa_ABC", estilo=estilo, valor_minimo=valor_minimo
                )
            elif view == "Vendas por Produto":
                tabela = desenhar_vendas_por_produto(
                    self.eixo, df, abc_df, colorir_por=opcao or "Faixa_ABC", estilo=estilo, valor_minimo=valor_minimo
                )
            elif view == "Receita por Fabricante ou Produto":
                tabela = desenhar_receita_agrupada(
                    self.eixo, df, agrupar_por=opcao or "Fabricante", estilo=estilo, valor_minimo=valor_minimo
                )
            elif view == "Afinidade Cliente-Fabricante":
                tabela = desenhar_afinidade_cliente_fabricante(self.eixo, df, abc_df, valor_minimo=valor_minimo)
            elif view == "Top Clientes por Receita":
                tabela = desenhar_top_clientes(
                    self.eixo, df, top_n=int(opcao) if opcao else 20, estilo=estilo, valor_minimo=valor_minimo
                )
            elif view == "Top Fabricantes por Receita":
                tabela = desenhar_top_fabricantes(
                    self.eixo, df, top_n=int(opcao) if opcao else 20, estilo=estilo, valor_minimo=valor_minimo
                )
            elif view == "Evolução no Tempo":
                top_n = int(self.combo_opcao2.get()) if self.combo_opcao2.get() else 5
                tabela = desenhar_evolucao_temporal(self.eixo, df, agrupar_por=opcao or "Nenhum", top_n=top_n, estilo=estilo)
        except Exception as exc:
            messagebox.showerror("Erro ao gerar gráfico", str(exc))
            return

        self._ultima_tabela = tabela
        self.figura.tight_layout()
        self.canvas.draw()

    def _exportar_png(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not caminho:
            return
        self.figura.savefig(caminho, dpi=150, bbox_inches="tight")
        messagebox.showinfo("Exportar PNG", f"Gráfico salvo em {caminho}")

    def _exportar_excel(self):
        if self._ultima_tabela is None or self._ultima_tabela.empty:
            messagebox.showwarning("Exportar Excel", "Gere um gráfico primeiro.")
            return
        caminho = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if not caminho:
            return
        self._ultima_tabela.to_excel(caminho, index=False)
        messagebox.showinfo("Exportar Excel", f"Dados exportados para {caminho}")
