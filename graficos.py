"""
Gráficos de dispersão do funil de vendas, usando matplotlib embutido no Tkinter.

Cada função `desenhar_*` recebe um objeto Axes do matplotlib e o DataFrame já
tratado, e desenha o gráfico nele (permite reaproveitar a mesma figura ao
trocar de view na interface). Também expõe uma função de exportação PNG.
"""

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd

PALETA_FAIXAS = ["#2e7d32", "#1565c0", "#f9a825", "#8e24aa", "#00897b", "#c62828"]
COR_FAIXA_DEMAIS = "#9e9e9e"


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


def desenhar_vendas_por_fabricante(ax, df, abc_df):
    """View 1: dispersão QTD x Receita por fabricante, cor = Faixa_ABC do cliente."""
    ax.clear()
    mapa_abc = _abc_do_cliente(df, abc_df)

    agrupado = df.groupby(["NOME_FABRICANTE", "Cliente"], as_index=False).agg(
        Receita=("Receita", "sum"), QTD=("QTD", "sum")
    )
    agrupado["Faixa_ABC"] = agrupado["Cliente"].map(mapa_abc).fillna("Demais")

    cores = _cores_por_faixa(agrupado["Faixa_ABC"].unique())
    for faixa, cor in cores.items():
        subconjunto = agrupado[agrupado["Faixa_ABC"] == faixa]
        ax.scatter(subconjunto["QTD"], subconjunto["Receita"], c=cor, label=faixa, alpha=0.6)

    ax.set_xlabel("Quantidade Vendida")
    ax.set_ylabel("Receita (R$)")
    ax.set_title("Vendas por Fabricante (cor = Faixa ABC do cliente)")
    ax.legend(title="Faixa ABC")


def desenhar_vendas_por_produto(ax, df, abc_df, colorir_por="Faixa_ABC"):
    """View 2: dispersão QTD x Receita por produto, cor = fabricante ou Faixa_ABC."""
    ax.clear()

    if colorir_por == "Faixa_ABC":
        mapa_abc = _abc_do_cliente(df, abc_df)
        agrupado = df.groupby(["descricao", "Cliente"], as_index=False).agg(
            Receita=("Receita", "sum"), QTD=("QTD", "sum")
        )
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
        fabricantes = agrupado["NOME_FABRICANTE"].unique()
        mapa_cores = plt.cm.get_cmap("tab20", max(len(fabricantes), 1))
        for i, fabricante in enumerate(fabricantes):
            subconjunto = agrupado[agrupado["NOME_FABRICANTE"] == fabricante]
            ax.scatter(subconjunto["QTD"], subconjunto["Receita"], color=mapa_cores(i), label=fabricante, alpha=0.6)
        ax.legend(title="Fabricante", fontsize="x-small", ncol=2)

    ax.set_xlabel("Quantidade Vendida")
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Vendas por Produto (cor = {colorir_por})")


def desenhar_receita_agrupada(ax, df, agrupar_por="NOME_FABRICANTE"):
    """View 3: dispersão de receita agregada por fabricante ou por produto."""
    ax.clear()
    campo = "NOME_FABRICANTE" if agrupar_por == "Fabricante" else "descricao"
    agrupado = df.groupby(campo, as_index=False).agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
    agrupado.sort_values("Receita", ascending=False, inplace=True)

    ax.scatter(range(len(agrupado)), agrupado["Receita"], c="#1565c0", alpha=0.7)
    ax.set_xticks(range(len(agrupado)))
    ax.set_xticklabels(agrupado[campo], rotation=90, fontsize=6)
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Receita por {agrupar_por}")


def desenhar_top_clientes(ax, df, top_n=20):
    """
    View: os top_n clientes de maior receita (soma de todo o período
    carregado, sem cor por faixa) — substitui o antigo relatório "Venda por
    Cliente (Top Clientes)", removido do catálogo por falta de uso; como
    gráfico, dá pra ver de cara o degrau entre os maiores clientes.
    """
    ax.clear()
    agrupado = df.groupby("Cliente", as_index=False).agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
    agrupado.sort_values("Receita", ascending=False, inplace=True)
    agrupado = agrupado.head(top_n)

    ax.scatter(range(len(agrupado)), agrupado["Receita"], c="#1565c0", alpha=0.7)
    ax.set_xticks(range(len(agrupado)))
    ax.set_xticklabels(agrupado["Cliente"], rotation=90, fontsize=6)
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Top {top_n} Clientes por Receita")


def desenhar_top_fabricantes(ax, df, top_n=20):
    """
    View: os top_n fabricantes de maior receita (soma de todo o período
    carregado) — substitui o antigo relatório "Venda por Fabricante (Top
    Fabricantes)", removido do catálogo (mesmo tratamento do Top Clientes);
    como gráfico, dá pra ver de cara o degrau entre os maiores fabricantes.
    """
    ax.clear()
    agrupado = df.groupby("NOME_FABRICANTE", as_index=False).agg(Receita=("Receita", "sum"), QTD=("QTD", "sum"))
    agrupado.sort_values("Receita", ascending=False, inplace=True)
    agrupado = agrupado.head(top_n)

    ax.scatter(range(len(agrupado)), agrupado["Receita"], c="#1565c0", alpha=0.7)
    ax.set_xticks(range(len(agrupado)))
    ax.set_xticklabels(agrupado["NOME_FABRICANTE"], rotation=90, fontsize=6)
    ax.set_ylabel("Receita (R$)")
    ax.set_title(f"Top {top_n} Fabricantes por Receita")


def desenhar_afinidade_cliente_fabricante(ax, df, abc_df):
    """
    View 4: por cliente, participação % de cada fabricante no faturamento do
    cliente (eixo X) x frequência de compra desse fabricante (eixo Y),
    colorido por Faixa_ABC.
    """
    ax.clear()
    mapa_abc = _abc_do_cliente(df, abc_df)

    receita_cliente_fabricante = df.groupby(["Cliente", "NOME_FABRICANTE"], as_index=False).agg(
        Receita=("Receita", "sum"), Frequencia=("Data_Venda", "nunique")
    )
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


class PainelGraficosFrame(ttk.Frame):
    """Aba de gráficos: seletor de view + área de plotagem embutida + exportar PNG."""

    VIEWS = [
        "Vendas por Fabricante",
        "Vendas por Produto",
        "Receita por Fabricante ou Produto",
        "Afinidade Cliente-Fabricante",
        "Top Clientes por Receita",
        "Top Fabricantes por Receita",
    ]

    def __init__(self, master, obter_dataframe, obter_abc_df):
        super().__init__(master)
        self.obter_dataframe = obter_dataframe
        self.obter_abc_df = obter_abc_df

        self._montar_interface()

    def _montar_interface(self):
        controles = ttk.Frame(self)
        controles.pack(fill="x", padx=8, pady=8)

        ttk.Label(controles, text="Tipo de gráfico:").pack(side="left")
        self.combo_view = ttk.Combobox(controles, values=self.VIEWS, state="readonly", width=32)
        self.combo_view.current(0)
        self.combo_view.pack(side="left", padx=4)
        self.combo_view.bind("<<ComboboxSelected>>", lambda evento: self._atualizar_opcoes())

        self.label_opcao = ttk.Label(controles, text="Colorir/Agrupar por:")
        self.label_opcao.pack(side="left", padx=(12, 0))
        self.combo_opcao = ttk.Combobox(controles, values=["Faixa_ABC", "Fabricante"], state="readonly", width=15)
        self.combo_opcao.current(0)
        self.combo_opcao.pack(side="left", padx=4)

        ttk.Button(controles, text="Plotar", command=self._plotar).pack(side="left", padx=8)
        ttk.Button(controles, text="Exportar PNG", command=self._exportar_png).pack(side="left", padx=4)

        self.figura, self.eixo = plt.subplots(figsize=(8, 5))
        self.canvas = FigureCanvasTkAgg(self.figura, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        barra_ferramentas = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        barra_ferramentas.pack(fill="x", padx=8)

        self._atualizar_opcoes()

    def _atualizar_opcoes(self):
        view = self.combo_view.get()
        self.label_opcao.config(text="Colorir/Agrupar por:")
        if view == "Vendas por Produto":
            self.combo_opcao["values"] = ["Faixa_ABC", "Fabricante"]
            self.combo_opcao.current(0)
        elif view == "Receita por Fabricante ou Produto":
            self.combo_opcao["values"] = ["Fabricante", "Produto"]
            self.combo_opcao.current(0)
        elif view == "Top Clientes por Receita":
            self.label_opcao.config(text="Quantidade de clientes:")
            self.combo_opcao["values"] = ["10", "20", "50", "100"]
            self.combo_opcao.current(1)
        elif view == "Top Fabricantes por Receita":
            self.label_opcao.config(text="Quantidade de fabricantes:")
            self.combo_opcao["values"] = ["10", "20", "50", "100"]
            self.combo_opcao.current(1)
        else:
            self.combo_opcao["values"] = []
            self.combo_opcao.set("")

    def _plotar(self):
        df = self.obter_dataframe()
        if df is None:
            messagebox.showwarning("Gráficos", "Carregue um CSV primeiro na aba Relatório Padrão.")
            return

        abc_df = self.obter_abc_df()
        view = self.combo_view.get()
        opcao = self.combo_opcao.get()

        try:
            if view == "Vendas por Fabricante":
                desenhar_vendas_por_fabricante(self.eixo, df, abc_df)
            elif view == "Vendas por Produto":
                desenhar_vendas_por_produto(self.eixo, df, abc_df, colorir_por=opcao or "Faixa_ABC")
            elif view == "Receita por Fabricante ou Produto":
                desenhar_receita_agrupada(self.eixo, df, agrupar_por=opcao or "Fabricante")
            elif view == "Afinidade Cliente-Fabricante":
                desenhar_afinidade_cliente_fabricante(self.eixo, df, abc_df)
            elif view == "Top Clientes por Receita":
                desenhar_top_clientes(self.eixo, df, top_n=int(opcao) if opcao else 20)
            elif view == "Top Fabricantes por Receita":
                desenhar_top_fabricantes(self.eixo, df, top_n=int(opcao) if opcao else 20)
        except Exception as exc:
            messagebox.showerror("Erro ao gerar gráfico", str(exc))
            return

        self.figura.tight_layout()
        self.canvas.draw()

    def _exportar_png(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not caminho:
            return
        self.figura.savefig(caminho, dpi=150, bbox_inches="tight")
        messagebox.showinfo("Exportar PNG", f"Gráfico salvo em {caminho}")
