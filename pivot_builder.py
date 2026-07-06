"""
Módulo de relatórios personalizados (pivot table) com arrastar-e-soltar.

Fornece:
  - a lógica de montagem da tabela dinâmica com pandas.pivot_table();
  - o widget de interface Tkinter com drag-and-drop (via tkinterdnd2, com
    fallback para botões Adicionar/Remover caso a biblioteca não esteja
    disponível);
  - salvar/carregar configurações de relatório em JSON.
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pandas as pd

try:
    from tkinterdnd2 import DND_TEXT, TkinterDnD
    DRAG_AND_DROP_DISPONIVEL = True
except ImportError:
    DRAG_AND_DROP_DISPONIVEL = False


AGREGACOES_DISPONIVEIS = {
    "Soma": "sum",
    "Contagem": "count",
    "Média": "mean",
    "Mínimo": "min",
    "Máximo": "max",
}

CAMPOS_BASE = [
    "Cliente", "descricao", "NOME_FABRICANTE", "Loja", "Receita", "QTD", "Data_Venda",
]

CAMPOS_CALCULADOS = [
    "Faixa_ABC", "Periodo_Mensal", "Periodo_Trimestral", "Periodo_Semestral", "Periodo_Anual",
]


def montar_pivot(df, linhas, colunas, valores, filtros=None):
    """
    Monta a tabela dinâmica com pandas.pivot_table().

    linhas: lista de nomes de campos.
    colunas: lista de nomes de campos.
    valores: lista de dicts {"campo": ..., "agregacao": "Soma"|"Contagem"|...}.
    filtros: lista de dicts {"campo": ..., "valores_incluidos": [...]}.
    """
    base = df.copy()

    if filtros:
        for filtro in filtros:
            campo = filtro.get("campo")
            valores_incluidos = filtro.get("valores_incluidos")
            if campo and valores_incluidos:
                base = base[base[campo].isin(valores_incluidos)]

    if not valores:
        raise ValueError("Selecione ao menos um campo para a área de Valores.")
    if not linhas and not colunas:
        raise ValueError("Selecione ao menos um campo para Linhas ou Colunas.")

    campos_valor = [v["campo"] for v in valores]
    agregacoes = {v["campo"]: AGREGACOES_DISPONIVEIS[v["agregacao"]] for v in valores}

    tabela = pd.pivot_table(
        base,
        index=linhas if linhas else None,
        columns=colunas if colunas else None,
        values=campos_valor,
        aggfunc=agregacoes,
        fill_value=0,
        margins=True,
        margins_name="Total Geral",
    )
    return tabela


def salvar_configuracao(caminho, nome_relatorio, linhas, colunas, valores, filtros):
    configuracao = {
        "nome": nome_relatorio,
        "linhas": linhas,
        "colunas": colunas,
        "valores": valores,
        "filtros": filtros,
    }
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(configuracao, arquivo, ensure_ascii=False, indent=2)


def carregar_configuracao(caminho):
    with open(caminho, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


class ConstrutorRelatorioFrame(ttk.Frame):
    """
    Frame Tkinter com a experiência de "tabela dinâmica": lista de campos
    disponíveis + quatro áreas de destino (Linhas, Colunas, Valores, Filtros).

    Usa drag-and-drop de verdade quando tkinterdnd2 está disponível;
    caso contrário, usa botões Adicionar/Remover como alternativa.
    """

    def __init__(self, master, obter_dataframe, relatorios_personalizados):
        super().__init__(master)
        self.obter_dataframe = obter_dataframe
        # dict compartilhado com o app principal: nome -> DataFrame gerado,
        # para poder exportar como abas extras no Excel.
        self.relatorios_personalizados = relatorios_personalizados

        self.linhas = []
        self.colunas = []
        self.valores = []  # lista de {"campo":..., "agregacao":...}
        self.filtros = []  # lista de {"campo":..., "valores_incluidos":...}

        self._montar_interface()

    # -- construção da interface -----------------------------------------

    def _montar_interface(self):
        painel_esquerdo = ttk.Frame(self)
        painel_esquerdo.pack(side="left", fill="y", padx=8, pady=8)

        ttk.Label(painel_esquerdo, text="Campos disponíveis", font=("", 10, "bold")).pack(anchor="w")
        self.lista_campos = tk.Listbox(painel_esquerdo, height=14, exportselection=False)
        for campo in CAMPOS_BASE + CAMPOS_CALCULADOS:
            self.lista_campos.insert("end", campo)
        self.lista_campos.pack(fill="y", pady=4)

        if DRAG_AND_DROP_DISPONIVEL:
            self.lista_campos.drag_source_register(1, DND_TEXT)
            self.lista_campos.dnd_bind("<<DragInitCmd>>", self._iniciar_arraste)
        else:
            ttk.Label(painel_esquerdo, text="(drag-and-drop indisponível\ninstale tkinterdnd2)",
                      foreground="gray").pack(anchor="w")

        botoes_frame = ttk.Frame(painel_esquerdo)
        botoes_frame.pack(fill="x", pady=4)
        ttk.Button(botoes_frame, text="➜ Linhas", command=lambda: self._adicionar_campo("linhas")).pack(fill="x")
        ttk.Button(botoes_frame, text="➜ Colunas", command=lambda: self._adicionar_campo("colunas")).pack(fill="x")
        ttk.Button(botoes_frame, text="➜ Valores", command=lambda: self._adicionar_campo("valores")).pack(fill="x")
        ttk.Button(botoes_frame, text="➜ Filtros", command=lambda: self._adicionar_campo("filtros")).pack(fill="x")

        painel_central = ttk.Frame(self)
        painel_central.pack(side="left", fill="both", expand=False, padx=8, pady=8)

        self.caixa_linhas = self._criar_area_destino(painel_central, "Linhas", "linhas")
        self.caixa_colunas = self._criar_area_destino(painel_central, "Colunas", "colunas")
        self.caixa_valores = self._criar_area_destino(painel_central, "Valores", "valores")
        self.caixa_filtros = self._criar_area_destino(painel_central, "Filtros", "filtros")

        controles_frame = ttk.Frame(painel_central)
        controles_frame.pack(fill="x", pady=8)
        ttk.Label(controles_frame, text="Nome do relatório:").pack(side="left")
        self.entrada_nome = ttk.Entry(controles_frame, width=25)
        self.entrada_nome.insert(0, "Relatório Personalizado")
        self.entrada_nome.pack(side="left", padx=4)

        ttk.Button(controles_frame, text="Gerar", command=self._gerar_pivot).pack(side="left", padx=4)
        ttk.Button(controles_frame, text="Salvar configuração", command=self._salvar_config).pack(side="left", padx=4)
        ttk.Button(controles_frame, text="Carregar configuração", command=self._carregar_config).pack(side="left", padx=4)

        painel_direito = ttk.Frame(self)
        painel_direito.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        ttk.Label(painel_direito, text="Resultado", font=("", 10, "bold")).pack(anchor="w")
        self.arvore_resultado = ttk.Treeview(painel_direito, show="headings")
        self.arvore_resultado.pack(fill="both", expand=True)

        self.status_label = ttk.Label(self, text="", foreground="blue")
        self.status_label.pack(side="bottom", fill="x", padx=8, pady=4)

    def _criar_area_destino(self, master, titulo, area_id):
        frame = ttk.LabelFrame(master, text=titulo)
        frame.pack(fill="x", pady=4)
        caixa = tk.Listbox(frame, height=4)
        caixa.pack(side="left", fill="x", expand=True)
        ttk.Button(frame, text="⟵", width=3, command=lambda: self._remover_campo(area_id, caixa)).pack(side="right")

        if DRAG_AND_DROP_DISPONIVEL:
            caixa.drop_target_register(DND_TEXT)
            caixa.dnd_bind("<<Drop>>", lambda evento, aid=area_id: self._receber_arraste(evento, aid))

        return caixa

    # -- drag and drop ------------------------------------------------------

    def _iniciar_arraste(self, evento):
        selecao = self.lista_campos.curselection()
        if not selecao:
            return None
        campo = self.lista_campos.get(selecao[0])
        return (evento.action, DND_TEXT, campo)

    def _receber_arraste(self, evento, area_id):
        campo = evento.data
        self._registrar_campo(area_id, campo)

    # -- botões adicionar/remover ---------------------------------------

    def _adicionar_campo(self, area_id):
        selecao = self.lista_campos.curselection()
        if not selecao:
            messagebox.showinfo("Campo", "Selecione um campo na lista antes de adicionar.")
            return
        campo = self.lista_campos.get(selecao[0])
        self._registrar_campo(area_id, campo)

    def _registrar_campo(self, area_id, campo):
        if area_id == "linhas":
            if campo not in self.linhas:
                self.linhas.append(campo)
                self.caixa_linhas.insert("end", campo)
        elif area_id == "colunas":
            if campo not in self.colunas:
                self.colunas.append(campo)
                self.caixa_colunas.insert("end", campo)
        elif area_id == "valores":
            agregacao = self._perguntar_agregacao()
            if agregacao:
                self.valores.append({"campo": campo, "agregacao": agregacao})
                self.caixa_valores.insert("end", f"{campo} ({agregacao})")
        elif area_id == "filtros":
            valores_disponiveis = self._valores_unicos_do_campo(campo)
            valores_incluidos = self._perguntar_valores_filtro(campo, valores_disponiveis)
            if valores_incluidos:
                self.filtros.append({"campo": campo, "valores_incluidos": valores_incluidos})
                self.caixa_filtros.insert("end", f"{campo} ({len(valores_incluidos)} valores)")

    def _remover_campo(self, area_id, caixa):
        selecao = caixa.curselection()
        if not selecao:
            return
        indice = selecao[0]
        caixa.delete(indice)
        if area_id == "linhas":
            del self.linhas[indice]
        elif area_id == "colunas":
            del self.colunas[indice]
        elif area_id == "valores":
            del self.valores[indice]
        elif area_id == "filtros":
            del self.filtros[indice]

    def _perguntar_agregacao(self):
        janela = tk.Toplevel(self)
        janela.title("Escolha a agregação")
        janela.grab_set()
        variavel = tk.StringVar(value="Soma")
        ttk.Label(janela, text="Agregação:").pack(padx=10, pady=6)
        combo = ttk.Combobox(janela, textvariable=variavel, values=list(AGREGACOES_DISPONIVEIS.keys()), state="readonly")
        combo.pack(padx=10, pady=6)
        resultado = {"valor": None}

        def confirmar():
            resultado["valor"] = variavel.get()
            janela.destroy()

        ttk.Button(janela, text="OK", command=confirmar).pack(pady=6)
        janela.wait_window()
        return resultado["valor"]

    def _valores_unicos_do_campo(self, campo):
        df = self.obter_dataframe()
        if df is None or campo not in df.columns:
            return []
        return sorted(df[campo].dropna().astype(str).unique().tolist())

    def _perguntar_valores_filtro(self, campo, valores_disponiveis):
        janela = tk.Toplevel(self)
        janela.title(f"Filtrar {campo}")
        janela.grab_set()
        lista = tk.Listbox(janela, selectmode="multiple", height=min(15, len(valores_disponiveis) or 1))
        for valor in valores_disponiveis:
            lista.insert("end", valor)
        lista.pack(padx=10, pady=6, fill="both", expand=True)
        resultado = {"valores": None}

        def confirmar():
            selecionados = [lista.get(i) for i in lista.curselection()]
            resultado["valores"] = selecionados
            janela.destroy()

        ttk.Button(janela, text="OK", command=confirmar).pack(pady=6)
        janela.wait_window()
        return resultado["valores"]

    # -- geração / exportação --------------------------------------------

    def _gerar_pivot(self):
        df = self.obter_dataframe()
        if df is None:
            messagebox.showwarning("Relatório Personalizado", "Carregue um CSV primeiro na aba Relatório Padrão.")
            return
        try:
            tabela = montar_pivot(df, self.linhas, self.colunas, self.valores, self.filtros)
        except Exception as exc:
            messagebox.showerror("Erro ao gerar relatório", str(exc))
            return

        self._exibir_tabela(tabela)

        nome = self.entrada_nome.get().strip() or "Relatório Personalizado"
        self.relatorios_personalizados[nome] = tabela
        self.status_label.config(text=f"Relatório '{nome}' gerado com sucesso.")

    def _exibir_tabela(self, tabela):
        for coluna in self.arvore_resultado.get_children():
            self.arvore_resultado.delete(coluna)

        tabela_exibicao = tabela.reset_index()
        colunas_exibicao = [str(c) for c in tabela_exibicao.columns]
        self.arvore_resultado["columns"] = colunas_exibicao
        for coluna in colunas_exibicao:
            self.arvore_resultado.heading(coluna, text=coluna)
            self.arvore_resultado.column(coluna, width=120, anchor="center")

        for _, linha in tabela_exibicao.iterrows():
            self.arvore_resultado.insert("", "end", values=list(linha))

    def _salvar_config(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not caminho:
            return
        nome = self.entrada_nome.get().strip() or "Relatório Personalizado"
        salvar_configuracao(caminho, nome, self.linhas, self.colunas, self.valores, self.filtros)
        self.status_label.config(text=f"Configuração salva em {caminho}")

    def _carregar_config(self):
        caminho = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not caminho:
            return
        try:
            configuracao = carregar_configuracao(caminho)
        except Exception as exc:
            messagebox.showerror("Erro ao carregar configuração", str(exc))
            return

        self.linhas = configuracao.get("linhas", [])
        self.colunas = configuracao.get("colunas", [])
        self.valores = configuracao.get("valores", [])
        self.filtros = configuracao.get("filtros", [])

        self.entrada_nome.delete(0, "end")
        self.entrada_nome.insert(0, configuracao.get("nome", "Relatório Personalizado"))

        self.caixa_linhas.delete(0, "end")
        for campo in self.linhas:
            self.caixa_linhas.insert("end", campo)
        self.caixa_colunas.delete(0, "end")
        for campo in self.colunas:
            self.caixa_colunas.insert("end", campo)
        self.caixa_valores.delete(0, "end")
        for valor in self.valores:
            self.caixa_valores.insert("end", f"{valor['campo']} ({valor['agregacao']})")
        self.caixa_filtros.delete(0, "end")
        for filtro in self.filtros:
            self.caixa_filtros.insert("end", f"{filtro['campo']} ({len(filtro['valores_incluidos'])} valores)")

        self.status_label.config(text=f"Configuração carregada de {caminho}")
