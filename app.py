"""
Interface principal do Monitor (2D Consultores | Monitores).

Integra o motor de análise (analise_funil.py), o construtor de relatórios
personalizados (pivot_builder.py) e os gráficos de dispersão (graficos.py)
em uma única janela Tkinter com abas:

  Configurações -> Relatório Padrão -> Relatórios Personalizados -> Gráficos -> Perfil
"""

import os
import re
import sys
import json
import queue
import socket
import logging
import threading
import traceback
import webbrowser
from datetime import datetime

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox

import recursos
from recursos import (
    CAMINHO_LOGO, CAMINHO_LOGO_ICO, CAMINHO_LOGO_ICONE, NOME_SISTEMA, NOME_EMPRESA, TITULO_JANELA,
    VERSAO_ATUAL, pasta_base_execucao,
)
import perfil
import atualizacoes
from novidades import NOVIDADES_POR_VERSAO
from catalogo import (
    CATALOGO_RELATORIOS, COLUNAS_MOEDA_POR_ANALISE, COR_ACCENT, COR_CABECALHO,
    DESCRICAO_ANALISE, GRUPOS_PARAMETROS_RELATORIO, NOMES_ANALISE, ROTULOS_RELATORIO_PDF_WORD,
    _colunas_moeda_efetivas, _construir_descricoes_dinamicas, _formatar_moeda_br,
)
from inicializacao import (
    _declarar_dpi_aware, _enviar_comando_instancia_existente,
    _passo_limpar_logs_antigos, _passo_verificar_arquivos_sistema, _passo_verificar_banco_local,
    _pedir_permissao_primeira_execucao, _perguntar_instancia_ja_aberta, _preparar_logger,
    _tentar_registrar_instancia_unica,
)

try:
    from tkinterdnd2 import TkinterDnD
    JANELA_BASE = TkinterDnD.Tk
except ImportError:
    JANELA_BASE = tk.Tk

# As dependências pesadas (pandas, matplotlib e os módulos do motor de
# análise) são importadas em _importar_dependencias_pesadas(), chamada pela
# tela de splash — assim a janela inicial aparece imediatamente, sem esperar
# essas bibliotecas carregarem. Os nomes abaixo são preenchidos nesse momento
# e usados pelo restante do arquivo (todos referenciados dentro de
# métodos/funções, nunca no corpo de uma classe, então a resolução do nome
# só acontece quando o código já rodou). openpyxl não entra aqui — mora em
# exportador_excel.py, importado sob demanda só na primeira exportação em
# Excel (mesmo padrão de exportadores_pdf_word.py para PDF/Word).
pd = None
af = pb = gf = None
sv_ttk = None


def _passo_importar_pandas():
    global pd
    import pandas as _pd
    pd = _pd


def _passo_importar_motor():
    global af
    import analise_funil as _af
    af = _af


def _passo_importar_construtor_relatorios():
    global pb
    import pivot_builder as _pb
    pb = _pb


def _passo_importar_graficos():
    global gf
    import graficos as _gf
    gf = _gf


def _passo_importar_tema_visual():
    global sv_ttk
    import sv_ttk as _sv_ttk
    sv_ttk = _sv_ttk


def construir_etapas_preparacao():
    """
    Sequência de verificações reais executadas pela splash antes de abrir a
    janela principal (cada etapa realmente faz o que o texto diz — não é só
    enfeite visual).
    """
    return [
        ("Verificando bibliotecas de dados (pandas)...", _passo_importar_pandas),
        ("Carregando motor de análise...", _passo_importar_motor),
        ("Carregando construtor de relatórios personalizados...", _passo_importar_construtor_relatorios),
        ("Verificando geração de gráficos (matplotlib)...", _passo_importar_graficos),
        ("Aplicando tema visual...", _passo_importar_tema_visual),
        ("Verificando banco de dados local (perfil)...", _passo_verificar_banco_local),
        ("Verificando arquivos de sistema (logo, ícones)...", _passo_verificar_arquivos_sistema),
        ("Limpando arquivos de log antigos (+30 dias)...", _passo_limpar_logs_antigos),
    ]


class AplicacaoAnaliseFunil(JANELA_BASE):
    def __init__(self, servidor_instancia_unica=None):
        super().__init__()
        self._servidor_instancia_unica = servidor_instancia_unica
        self.title(TITULO_JANELA)
        self._definir_geometria_janela()
        self._definir_icone_janela()
        sv_ttk.set_theme("light")
        self._aplicar_estilos_customizados()

        self.logger, self.caminho_log = _preparar_logger()
        self.logger.info("Aplicação iniciada.")
        self._verificar_status_ultima_atualizacao()

        self.perfil = perfil.carregar_perfil()

        # Estado compartilhado entre as abas
        self.df = None
        self.resultados_analise = None
        self.granularidade_referencia = "Mensal"
        self.relatorios_personalizados = {}
        self.estado_clientes = {}   # cliente -> True se EXCLUÍDO
        self.estado_produtos = {}   # produto -> True se CONSIDERADO
        self.vars_lojas = {}   # loja -> tk.BooleanVar (True = incluída na análise)
        self._produtos_manual = set()  # produtos com "Considerar?" alterado à mão — não são resincronizados com o Grupo 1
        self._caminho_csv_atual = None  # chave da configuração automática (ver _salvar/_carregar_configuracao_automatica)
        self.thread_em_execucao = False
        self._thread_geracao = None

        self.fila_eventos = queue.Queue()

        self.tamanho_fonte_base = self.perfil["tamanho_fonte"]
        self.fator_zoom = 1.0

        self._montar_interface()
        self._aplicar_zoom(None)
        self._id_after_fila = self.after(150, self._bombear_fila_eventos)
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar_janela)
        if self._servidor_instancia_unica is not None:
            threading.Thread(target=self._escutar_outras_instancias, daemon=True).start()

        self._mostrar_novidades_versao()
        threading.Thread(target=self._verificar_atualizacoes, daemon=True).start()

    def report_callback_exception(self, exc, val, tb):
        # O .exe roda sem console (modo janela) — sem isso, qualquer exceção
        # dentro de um comando de botão, trace de variável ou bind seria
        # descartada silenciosamente (o comportamento padrão do Tkinter é
        # imprimir em stderr, que não existe nesse modo). Aqui ela vira log
        # visível tanto no arquivo de log quanto no painel de Execução.
        mensagem = "".join(traceback.format_exception(exc, val, tb))
        try:
            self.logger.error(f"Exceção não tratada em callback da interface:\n{mensagem}")
        except Exception:
            pass
        try:
            self._registrar_log("Erro interno ao processar a última ação — veja o log para detalhes.", nivel="error")
        except Exception:
            pass

    def _ao_fechar_janela(self):
        try:
            self.after_cancel(self._id_after_fila)
        except (ValueError, tk.TclError):
            pass
        if self._thread_geracao is not None and self._thread_geracao.is_alive():
            self._thread_geracao.join(timeout=5)
        if self._servidor_instancia_unica is not None:
            try:
                self._servidor_instancia_unica.close()
            except OSError:
                pass
        self.logger.info("Aplicação encerrada pelo usuário.")
        self.quit()
        self.destroy()

    # ------------------------------------------------------------------
    # Montagem geral
    # ------------------------------------------------------------------

    def _definir_geometria_janela(self):
        """
        Tamanho ideal 1360x880 (em pixels a 100% de escala), mas nunca maior
        que a tela disponível — numa tela menor (notebook, resolução baixa),
        o tamanho fixo anterior cortava a parte de baixo da janela pra fora
        da área visível, atrás da barra de tarefas do Windows.

        Escalado pelo fator de DPI real (self.winfo_fpixels('1i') / 96) porque,
        desde que o processo passou a se declarar DPI-aware pro Windows (ver
        _declarar_dpi_aware), o Tk usa a resolução física de verdade pra
        winfo_screenwidth/height e pra desenhar fontes/paddings — sem esse
        ajuste, numa tela a 125%/150% a janela pedia o mesmo tanto de pixels
        físicos de sempre, só que agora sem o Windows esticando o resultado
        pra compensar, então o conteúdo (que cresce corretamente com a fonte)
        deixava de caber e cortava o rodapé da tela (ex.: botão "Gerar
        Relatório Padrão" sumindo de vista).
        """
        escala = self.winfo_fpixels("1i") / 96.0
        largura_ideal, altura_ideal = round(1360 * escala), round(880 * escala)
        margem_taskbar = round(60 * escala)
        largura = min(largura_ideal, self.winfo_screenwidth() - 20)
        altura = min(altura_ideal, self.winfo_screenheight() - margem_taskbar)
        x = max((self.winfo_screenwidth() - largura) // 2, 0)
        y = max((self.winfo_screenheight() - altura) // 2 - 10, 0)
        self.geometry(f"{largura}x{altura}+{x}+{y}")

    def _definir_icone_janela(self):
        try:
            if os.path.exists(CAMINHO_LOGO_ICO):
                self.iconbitmap(CAMINHO_LOGO_ICO)
                return
        except tk.TclError:
            pass
        try:
            self._icone_janela = tk.PhotoImage(file=CAMINHO_LOGO_ICONE)
            self.iconphoto(True, self._icone_janela)
        except tk.TclError:
            pass

    def _montar_cabecalho(self, master):
        cabecalho = ttk.Frame(master)
        cabecalho.pack(fill="x", side="top")

        try:
            # Só a marca (sem texto) — o logo completo, reduzido a essa
            # altura, deixava o texto "2D CONSULTORES" ilegível/cortado.
            logo_imagem = tk.PhotoImage(file=CAMINHO_LOGO_ICONE)
            fator = max(1, logo_imagem.height() // 44)
            if fator > 1:
                logo_imagem = logo_imagem.subsample(fator, fator)
            self._logo_cabecalho_ref = logo_imagem
            ttk.Label(cabecalho, image=logo_imagem).pack(side="left", padx=(10, 10), pady=8)
        except tk.TclError:
            pass

        bloco_titulo = ttk.Frame(cabecalho)
        bloco_titulo.pack(side="left", pady=8)
        ttk.Label(bloco_titulo, text=NOME_SISTEMA, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(bloco_titulo, text=f"{NOME_EMPRESA} · v{VERSAO_ATUAL}", font=("Segoe UI", 9), foreground="gray").pack(anchor="w")

        self.label_boas_vindas = ttk.Label(cabecalho, text="", font=("Segoe UI", 10), foreground="#1565c0")
        self.label_boas_vindas.pack(side="right", padx=12)
        self._atualizar_boas_vindas()

        ttk.Separator(master, orient="horizontal").pack(fill="x", side="top")

    def _atualizar_boas_vindas(self):
        nome = (self.perfil or {}).get("nome", "").strip()
        self.label_boas_vindas.config(text=f"Bem-vindo, {nome}" if nome else "")

    def _montar_menu(self):
        barra_menu = tk.Menu(self)

        menu_arquivo = tk.Menu(barra_menu, tearoff=False)
        menu_arquivo.add_command(label="Selecionar CSV de vendas...", accelerator="Ctrl+O", command=self._selecionar_csv)
        menu_arquivo.add_command(label="Limpar base", command=self._limpar_base)
        menu_arquivo.add_separator()
        menu_arquivo.add_command(label="Buscar atualizações...", command=self._buscar_atualizacoes_manual)
        menu_arquivo.add_separator()
        menu_arquivo.add_command(label="Sair", accelerator="Ctrl+Q", command=self._ao_fechar_janela)
        barra_menu.add_cascade(label="Arquivo", menu=menu_arquivo)

        menu_relatorios = tk.Menu(barra_menu, tearoff=False)
        menu_relatorios.add_command(label="Gerar Relatório Padrão", accelerator="Ctrl+G", command=self._gerar_relatorio_padrao)
        menu_relatorios.add_command(label="Atualizar prévia dos grupos", accelerator="F5", command=self._pre_visualizar_grupos)
        barra_menu.add_cascade(label="Relatórios", menu=menu_relatorios)

        menu_ajuda = tk.Menu(barra_menu, tearoff=False)
        menu_ajuda.add_command(label="Sobre", accelerator="F1", command=self._mostrar_sobre)
        barra_menu.add_cascade(label="Ajuda", menu=menu_ajuda)

        self.config(menu=barra_menu)

        self.bind_all("<Control-o>", lambda evento: self._selecionar_csv())
        self.bind_all("<Control-q>", lambda evento: self._ao_fechar_janela())
        self.bind_all("<Control-g>", lambda evento: self._gerar_relatorio_padrao())
        self.bind_all("<F5>", lambda evento: self._pre_visualizar_grupos())
        self.bind_all("<F1>", lambda evento: self._mostrar_sobre())

    def _aplicar_estilos_customizados(self):
        estilo = ttk.Style(self)
        estilo.configure("Treeview", rowheight=26, font=("Segoe UI", 9))
        estilo.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        estilo.map("Treeview", background=[("selected", COR_ACCENT)], foreground=[("selected", "white")])

    def _atualizar_zebra_arvores(self):
        cor_par = "#eef2f6"
        cor_impar = "#ffffff"
        for arvore in (self.arvore_clientes, self.arvore_produtos):
            arvore.tag_configure("par", background=cor_par)
            arvore.tag_configure("impar", background=cor_impar)

    def _mostrar_sobre(self):
        messagebox.showinfo(
            "Sobre",
            f"{NOME_SISTEMA} — versão {VERSAO_ATUAL}\n{NOME_EMPRESA}\n\n"
            "Análise de funil de vendas B2B: tendências de produtos, erosão de\n"
            "clientes, segmentação por faturamento e relatórios personalizados.",
        )

    def _mostrar_novidades_versao(self):
        """
        Janela pequena e direta com o que mudou nesta versão — só aparece na
        primeira vez que o usuário abre uma versão diferente da última
        registrada (nunca na primeira execução de uma instalação nova: não
        há versão anterior pra comparar, então só registra e sai em silêncio).
        """
        ultima_vista = perfil.obter_ultima_versao_vista()
        if ultima_vista == VERSAO_ATUAL:
            return
        perfil.definir_ultima_versao_vista(VERSAO_ATUAL)
        if ultima_vista is None:
            return

        itens = NOVIDADES_POR_VERSAO.get(VERSAO_ATUAL)
        if not itens:
            return

        escala = self.winfo_fpixels("1i") / 96.0
        janela = tk.Toplevel(self)
        janela.title(f"Novidades da versão {VERSAO_ATUAL}")
        janela.geometry(f"{round(440 * escala)}x{round(360 * escala)}")
        janela.resizable(False, False)
        janela.transient(self)
        janela.grab_set()

        ttk.Label(
            janela, text=f"O que mudou na v{VERSAO_ATUAL}", font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 2))
        ttk.Label(
            janela, text=f"(versão anterior: {ultima_vista})", foreground="gray",
        ).pack(anchor="w", padx=18, pady=(0, 10))

        texto = tk.Text(janela, wrap="word", borderwidth=0, font=("Segoe UI", 9), padx=2)
        texto.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        for item in itens:
            texto.insert("end", f"•  {item}\n\n")
        texto.config(state="disabled")

        ttk.Button(janela, text="Entendi", command=janela.destroy).pack(pady=(0, 16))
        janela.bind("<Return>", lambda evento: janela.destroy())

    def _montar_interface(self):
        self._montar_menu()
        self._montar_cabecalho(self)

        # Painel de Execução (log/progresso) e barra de status são empacotados
        # ANTES de corpo_principal, de propósito: o pack() do Tk reserva
        # espaço na ordem em que os widgets são empacotados, então quem vem
        # primeiro garante seu tamanho mínimo. Se corpo_principal (que tem
        # expand=True e pode pedir bastante altura, com todas as abas)
        # empacotasse primeiro, ele consumiria a cavidade toda em janelas
        # menores (notebook, telas de resolução baixa), deixando ZERO espaço
        # pro rodapé — o log de execução sumia da tela mesmo com a janela
        # aberta corretamente. Empacotando o rodapé primeiro, ele nunca é
        # espremido; é a área de conteúdo (com abas) que cede espaço quando
        # a janela é pequena.
        self._montar_painel_execucao(self)
        self.status_var = tk.StringVar(master=self, value="Pronto.")
        barra_status = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        barra_status.pack(fill="x", side="bottom")

        corpo_principal = ttk.Frame(self)
        corpo_principal.pack(fill="both", expand=True)

        self.barra_lateral = ttk.Frame(corpo_principal, width=200)
        self.barra_lateral.pack(side="left", fill="y")
        self.barra_lateral.pack_propagate(False)

        area_conteudo = ttk.Frame(corpo_principal)
        area_conteudo.pack(side="left", fill="both", expand=True)
        area_conteudo.columnconfigure(0, weight=1)
        area_conteudo.rowconfigure(0, weight=1)

        self.paginas = {}
        self.botoes_nav = {}
        self.pagina_ativa = "Configurações"

        self.aba_configuracoes = ttk.Frame(area_conteudo)
        self._montar_aba_configuracoes(self.aba_configuracoes)
        self._registrar_pagina_nav("Configurações", "⚙", self.aba_configuracoes, area_conteudo)
        self._atualizar_zebra_arvores()

        self.aba_padrao = ttk.Frame(area_conteudo)
        self._montar_aba_padrao(self.aba_padrao)
        self._registrar_pagina_nav("Relatório Padrão", "📄", self.aba_padrao, area_conteudo)

        self.aba_visualizar = ttk.Frame(area_conteudo)
        self._montar_aba_visualizar(self.aba_visualizar)
        self._registrar_pagina_nav("Visualizar Relatório", "👁", self.aba_visualizar, area_conteudo)

        self.aba_personalizados = pb.ConstrutorRelatorioFrame(
            area_conteudo, obter_dataframe=lambda: self._dataframe_para_analise(),
            relatorios_personalizados=self.relatorios_personalizados,
        )
        self._registrar_pagina_nav("Relatórios Personalizados", "📊", self.aba_personalizados, area_conteudo)

        self.aba_graficos = gf.PainelGraficosFrame(
            area_conteudo, obter_dataframe=lambda: self._dataframe_para_analise(),
            obter_abc_df=self._obter_abc_df_atual,
        )
        self._registrar_pagina_nav("Gráficos", "📈", self.aba_graficos, area_conteudo)

        self.aba_perfil = ttk.Frame(area_conteudo)
        self._montar_aba_perfil(self.aba_perfil)
        self._registrar_pagina_nav("Perfil", "👤", self.aba_perfil, area_conteudo)

        self._mostrar_pagina("Configurações")

    def _registrar_pagina_nav(self, nome, icone, frame_pagina, area_conteudo):
        frame_pagina.grid(in_=area_conteudo, row=0, column=0, sticky="nsew")
        self.paginas[nome] = frame_pagina

        rotulo = tk.Label(
            self.barra_lateral, text=f"   {icone}   {nome}", anchor="w",
            font=("Segoe UI", 10), padx=6, pady=12, cursor="hand2",
        )
        rotulo.pack(fill="x")
        rotulo.bind("<Button-1>", lambda evento: self._mostrar_pagina(nome))
        rotulo.bind("<Enter>", lambda evento: self._ao_passar_mouse_nav(nome, True))
        rotulo.bind("<Leave>", lambda evento: self._ao_passar_mouse_nav(nome, False))
        self.botoes_nav[nome] = rotulo

    def _mostrar_pagina(self, nome):
        self.pagina_ativa = nome
        self.paginas[nome].tkraise()
        self._atualizar_cores_nav()

    def _ao_passar_mouse_nav(self, nome, entrando):
        if nome == self.pagina_ativa:
            return
        rotulo = self.botoes_nav[nome]
        rotulo.configure(background=self._cor_hover_nav if entrando else self._cor_fundo_nav)

    def _atualizar_cores_nav(self):
        # Cores oficiais do tema sv_ttk claro (light.tcl) — o ttk.Style().lookup()
        # não retorna essas cores porque o tema é baseado em sprites de imagem,
        # não em "background" configurado por classe de estilo.
        self._cor_fundo_nav = "#fafafa"
        self._cor_texto_nav = "#1c1c1c"
        self._cor_hover_nav = "#d6e4f0"
        for nome, rotulo in self.botoes_nav.items():
            ativo = nome == self.pagina_ativa
            rotulo.configure(
                background=COR_ACCENT if ativo else self._cor_fundo_nav,
                foreground="white" if ativo else self._cor_texto_nav,
            )

    def _montar_painel_execucao(self, master):
        """
        Painel de log/progresso GLOBAL (visível em qualquer aba), não preso
        à aba Relatório Padrão — carregamento de CSV, geração de relatórios
        e qualquer outra tarefa de fundo aparecem aqui.
        """
        rodape = ttk.LabelFrame(master, text="Execução")
        rodape.pack(fill="x", side="bottom", padx=10, pady=(0, 4))

        self.progress = ttk.Progressbar(rodape, mode="indeterminate")
        self.progress.pack(fill="x", padx=8, pady=(8, 4))

        self.texto_log = tk.Text(rodape, height=6, state="disabled", wrap="word")
        self.texto_log.pack(fill="x", padx=8, pady=(0, 8))

    def _obter_abc_df_atual(self):
        if not self.resultados_analise:
            return None
        return self.resultados_analise.get(self.granularidade_referencia, {}).get("abc")

    def _definir_status(self, texto):
        self.status_var.set(texto)

    # ------------------------------------------------------------------
    # Zoom (aumenta/diminui a fonte padrão usada por toda a interface)
    # ------------------------------------------------------------------

    def _aplicar_zoom(self, delta=None):
        if delta is None:
            self.fator_zoom = 1.0
        else:
            self.fator_zoom = min(2.0, max(0.7, self.fator_zoom * delta))

        novo_tamanho = max(6, round(self.tamanho_fonte_base * self.fator_zoom))
        for nome_fonte in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont", "TkFixedFont"):
            try:
                # root=self evita "Too early to use font: no default root window":
                # o TkinterDnD.Tk (usado para permitir drag-and-drop) nem sempre se
                # registra como root padrão do tkinter, então é preciso apontar
                # explicitamente qual interpretador Tcl usar.
                fonte = tkfont.nametofont(nome_fonte, root=self)
                fonte.configure(size=novo_tamanho)
            except (tk.TclError, RuntimeError):
                pass
        if hasattr(self, "label_zoom"):
            self.label_zoom.config(text=f"{int(self.fator_zoom * 100)}%")

    # ------------------------------------------------------------------
    # Aba "Configurações": base de dados, clientes/produtos, parâmetros
    # ------------------------------------------------------------------

    def _montar_aba_configuracoes(self, master):
        topo = ttk.Frame(master)
        topo.pack(fill="x", padx=10, pady=8)

        grupo_base = ttk.LabelFrame(topo, text="Base de dados")
        grupo_base.pack(side="left", fill="y")
        linha_base = ttk.Frame(grupo_base)
        linha_base.pack(padx=8, pady=6)
        ttk.Button(linha_base, text="Selecionar CSV de vendas...", command=self._selecionar_csv).pack(side="left")
        self.botao_limpar_base = ttk.Button(linha_base, text="Limpar base", command=self._limpar_base, state="disabled")
        self.botao_limpar_base.pack(side="left", padx=(6, 0))
        self.label_arquivo = ttk.Label(grupo_base, text="Nenhum arquivo carregado", foreground="gray")
        self.label_arquivo.pack(anchor="w", padx=8, pady=(0, 6))

        grupo_lojas = ttk.LabelFrame(topo, text="Lojas incluídas na análise")
        grupo_lojas.pack(side="left", fill="y", padx=8)
        self.container_lojas = ttk.Frame(grupo_lojas)
        self.container_lojas.pack(padx=8, pady=6)
        self.label_lojas_vazio = ttk.Label(self.container_lojas, text="Carregue um CSV para escolher as lojas.", foreground="gray")
        self.label_lojas_vazio.pack(anchor="w")

        grupo_empresa = ttk.LabelFrame(topo, text="Empresa analisada")
        grupo_empresa.pack(side="left", fill="y", padx=8)
        self.entrada_nome_empresa = ttk.Entry(grupo_empresa, width=32)
        self.entrada_nome_empresa.pack(padx=8, pady=(6, 2))
        ttk.Label(
            grupo_empresa, text="Aparece na capa e no nome do arquivo", foreground="gray", font=("Segoe UI", 8),
        ).pack(padx=8, pady=(0, 6))

        grupo_config = ttk.LabelFrame(topo, text="Configuração da análise")
        grupo_config.pack(side="left", fill="y")
        linha_config = ttk.Frame(grupo_config)
        linha_config.pack(padx=8, pady=6)
        ttk.Button(linha_config, text="Salvar configuração...", command=self._salvar_configuracao_analise).pack(side="left")
        ttk.Button(linha_config, text="Carregar configuração...", command=self._carregar_configuracao_analise).pack(side="left", padx=(6, 0))

        grupo_zoom = ttk.LabelFrame(topo, text="Zoom")
        grupo_zoom.pack(side="right")
        linha_zoom = ttk.Frame(grupo_zoom)
        linha_zoom.pack(padx=8, pady=6)
        ttk.Button(linha_zoom, text="-", width=3, command=lambda: self._aplicar_zoom(1 / 1.1)).pack(side="left")
        self.label_zoom = ttk.Label(linha_zoom, text="100%", width=5, anchor="center")
        self.label_zoom.pack(side="left", padx=4)
        ttk.Button(linha_zoom, text="+", width=3, command=lambda: self._aplicar_zoom(1.1)).pack(side="left")
        ttk.Button(linha_zoom, text="Reset", command=lambda: self._aplicar_zoom(None)).pack(side="left", padx=(6, 0))

        corpo = ttk.Frame(master)
        corpo.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        coluna_parametros = self._montar_coluna_parametros(corpo)
        coluna_parametros.pack(side="left", fill="y", padx=(0, 8))

        coluna_clientes = self._montar_coluna_clientes(corpo)
        coluna_clientes.pack(side="left", fill="both", expand=True, padx=(0, 8))

        coluna_produtos = self._montar_coluna_produtos(corpo)
        coluna_produtos.pack(side="left", fill="both", expand=True)

    def _montar_coluna_parametros(self, master):
        """
        A coluna de parâmetros acumulou blocos demais (Segmentação, Evolução/
        alertas/erosão, Alertas e granularidade) pra caber sem cortar em
        janelas normais — sem scrollbar, o bloco "Alertas e granularidade"
        (e legendas do bloco anterior) ficava simplesmente inacessível abaixo
        do fim da janela. Canvas + Scrollbar clássico do Tkinter: o conteúdo
        real mora em `frame`, dentro do canvas; a roda do mouse só rola
        quando o cursor está sobre esta coluna (bind/unbind em Enter/Leave),
        senão ia capturar a rolagem das listas de Clientes/Produtos também.
        """
        container = ttk.Frame(master)
        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0, width=380)
        barra_rolagem = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=barra_rolagem.set)
        canvas.pack(side="left", fill="both", expand=True)
        barra_rolagem.pack(side="right", fill="y")

        def _ao_rolar_mouse(evento):
            canvas.yview_scroll(int(-1 * (evento.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _ao_rolar_mouse))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        frame = ttk.LabelFrame(canvas, text="Parâmetros (valem para todos os relatórios)")
        janela_frame = canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda evento: canvas.itemconfig(janela_frame, width=evento.width))

        LARGURA_ROTULO = 26

        # --- Bloco 1: Segmentação (todos os inputs relacionados juntos,
        # rótulo e campo sempre nas mesmas duas colunas) -------------------
        bloco_segmentacao = ttk.LabelFrame(frame, text="Segmentação")
        bloco_segmentacao.pack(fill="x", padx=6, pady=(6, 6))

        linha = 0
        ttk.Button(bloco_segmentacao, text="Sugerir cortes automaticamente", command=self._sugerir_cortes_automaticamente).grid(
            row=linha, column=0, columnspan=2, sticky="we", padx=6, pady=(6, 2)
        )
        linha += 1
        self.botao_atualizar_preview = ttk.Button(bloco_segmentacao, text="Atualizar prévia dos grupos", command=self._pre_visualizar_grupos)
        self.botao_atualizar_preview.grid(row=linha, column=0, columnspan=2, sticky="we", padx=6, pady=2)
        linha += 1
        self.label_contagens_grupos = ttk.Label(
            bloco_segmentacao, text="Contagens: clique em 'Atualizar prévia' para calcular.",
            wraplength=230, foreground="#1565c0",
        )
        self.label_contagens_grupos.grid(row=linha, column=0, columnspan=2, sticky="w", padx=6, pady=(2, 6))
        linha += 1
        ttk.Separator(bloco_segmentacao, orient="horizontal").grid(
            row=linha, column=0, columnspan=2, sticky="we", padx=6, pady=(2, 6)
        )
        linha += 1

        ttk.Label(bloco_segmentacao, text="Corte de produtos por receita (%):", width=LARGURA_ROTULO, anchor="w").grid(
            row=linha, column=0, sticky="w", padx=6, pady=4
        )
        self.entrada_corte_produtos = ttk.Entry(bloco_segmentacao, width=8)
        self.entrada_corte_produtos.insert(0, "80")
        self.entrada_corte_produtos.bind("<KeyRelease>", lambda evento: self._marcar_configuracao_alterada())
        self.entrada_corte_produtos.grid(row=linha, column=1, sticky="w", padx=6, pady=4)
        linha += 1
        ttk.Label(bloco_segmentacao, text="padrão 80% — ajustável", foreground="gray", font=("Segoe UI", 8)).grid(
            row=linha, column=0, columnspan=2, sticky="w", padx=6
        )
        linha += 1

        self.entradas_corte_grupo = []
        for i, valor_padrao in enumerate(("30", "50", "60")):
            ttk.Label(bloco_segmentacao, text=f"Grupo {i + 1} de clientes até (%):", width=LARGURA_ROTULO, anchor="w").grid(
                row=linha, column=0, sticky="w", padx=6, pady=4
            )
            entrada = ttk.Entry(bloco_segmentacao, width=8)
            entrada.insert(0, valor_padrao)
            entrada.bind("<KeyRelease>", lambda evento: self._marcar_configuracao_alterada())
            entrada.grid(row=linha, column=1, sticky="w", padx=6, pady=4)
            self.entradas_corte_grupo.append(entrada)
            linha += 1

        ttk.Label(bloco_segmentacao, text="Máx. clientes por grupo:", width=LARGURA_ROTULO, anchor="w").grid(
            row=linha, column=0, sticky="w", padx=6, pady=4
        )
        self.entrada_max_por_grupo = ttk.Entry(bloco_segmentacao, width=8)
        self.entrada_max_por_grupo.insert(0, "10")
        self.entrada_max_por_grupo.grid(row=linha, column=1, sticky="w", padx=6, pady=4)
        linha += 1

        self.check_balcao = ttk.Checkbutton(
            bloco_segmentacao, text="Desconsiderar clientes balcão da frequência",
            command=self._marcar_configuracao_alterada,
        )
        self.check_balcao.state(["selected", "!alternate"])
        self.check_balcao.grid(row=linha, column=0, columnspan=2, sticky="w", padx=6, pady=(2, 0))
        linha += 1
        ttk.Label(
            bloco_segmentacao,
            text="Marcado, eles saem dos grupos e viram faixa \"Balcão\" — não\nsomem: filtre por \"Balcão\" na lista de clientes pra vê-los.",
            foreground="gray", font=("Segoe UI", 8), justify="left",
        ).grid(row=linha, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))

        # --- Bloco 2: Período e granularidade -------------------------------
        # Os parâmetros específicos de Alertas de Queda e Erosão de Clientes
        # (períodos seguidos, pisos de queda em R$/%) NÃO ficam mais aqui —
        # moveram pra dentro do próprio item do catálogo, na aba Relatório
        # Padrão (ver GRUPOS_PARAMETROS_RELATORIO), habilitados só quando o
        # relatório correspondente está marcado. O que sobra aqui é
        # realmente global: vale pra toda análise "por período", não só
        # pra um relatório específico.
        bloco_periodo = ttk.LabelFrame(frame, text="Período e granularidade")
        bloco_periodo.pack(fill="x", padx=6, pady=(0, 6))

        self.check_incluir_periodo_atual = ttk.Checkbutton(
            bloco_periodo, text="Incluir período mais recente (geralmente incompleto)",
            command=self._marcar_configuracao_alterada,
        )
        self.check_incluir_periodo_atual.state(["!selected", "!alternate"])
        self.check_incluir_periodo_atual.grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(
            bloco_periodo, text="Desmarcado (padrão): o último período de cada relatório fica de fora.",
            foreground="gray", font=("Segoe UI", 8),
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))

        ttk.Label(bloco_periodo, text="Granularidade do relatório:", width=LARGURA_ROTULO, anchor="w").grid(
            row=2, column=0, sticky="w", padx=6, pady=(10, 4)
        )
        linha_granularidade = ttk.Frame(bloco_periodo)
        linha_granularidade.grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))
        self.var_granularidade = tk.StringVar(master=self, value="Mensal")
        for granularidade in af.GRANULARIDADES:
            ttk.Radiobutton(
                linha_granularidade, text=granularidade, value=granularidade, variable=self.var_granularidade,
                command=lambda g=granularidade: self.var_granularidade.set(g),
            ).pack(side="left", padx=(0, 10))

        # Garante a região de rolagem final: o <Configure> do frame pode
        # disparar antes de todos os blocos abaixo serem montados/ajustados
        # à largura do canvas, deixando a barra de rolagem "curta" (parava
        # antes do fim real do conteúdo).
        frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        return container

    def _montar_lista_com_filtro(self, master, titulo, colunas):
        """
        Cria um LabelFrame com campo de busca + filtro por grupo + Treeview
        (rola nativamente com a roda do mouse, ao contrário de uma lista de
        checkboxes).
        """
        frame = ttk.LabelFrame(master, text=titulo)

        barra_busca = ttk.Frame(frame)
        barra_busca.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(barra_busca, text="Buscar:").pack(side="left")
        entrada_busca = ttk.Entry(barra_busca)
        entrada_busca.pack(side="left", fill="x", expand=True, padx=4)

        ttk.Label(barra_busca, text="Grupo:").pack(side="left", padx=(8, 2))
        combo_grupo = ttk.Combobox(barra_busca, state="readonly", width=10, values=["Todos"])
        combo_grupo.set("Todos")
        combo_grupo.pack(side="left")

        container = ttk.Frame(frame)
        container.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        arvore = ttk.Treeview(container, columns=colunas, show="headings", selectmode="none")
        barra_rolagem = ttk.Scrollbar(container, orient="vertical", command=arvore.yview)
        arvore.configure(yscrollcommand=barra_rolagem.set)
        arvore.pack(side="left", fill="both", expand=True)
        barra_rolagem.pack(side="right", fill="y")

        return frame, entrada_busca, combo_grupo, arvore

    def _montar_coluna_clientes(self, master):
        frame, entrada_busca, combo_grupo, arvore = self._montar_lista_com_filtro(
            master, "Clientes a excluir das métricas", ("check", "cliente", "receita", "percentual", "grupo")
        )
        arvore.heading("check", text="Excluir?")
        arvore.heading("cliente", text="Cliente", command=lambda: self._ordenar_clientes("cliente"))
        arvore.heading("receita", text="Receita", command=lambda: self._ordenar_clientes("receita"))
        arvore.heading("percentual", text="% Receita", command=lambda: self._ordenar_clientes("percentual"))
        arvore.heading("grupo", text="Grupo")
        arvore.column("check", width=60, anchor="center")
        arvore.column("cliente", width=230, anchor="w")
        arvore.column("receita", width=100, anchor="e")
        arvore.column("percentual", width=75, anchor="e")
        arvore.column("grupo", width=75, anchor="center")

        arvore.bind("<Button-1>", lambda evento: self._alternar_checkbox_arvore(evento, arvore, self.estado_clientes))
        entrada_busca.bind("<KeyRelease>", lambda evento: self._buscar_clientes(entrada_busca.get()))
        combo_grupo.bind("<<ComboboxSelected>>", lambda evento: self._renderizar_clientes(entrada_busca.get()))

        self.arvore_clientes = arvore
        self.entrada_busca_clientes = entrada_busca
        self.combo_grupo_clientes = combo_grupo
        self.dados_clientes = []  # lista de dicts: cliente, receita, percentual, grupo
        return frame

    def _montar_coluna_produtos(self, master):
        frame, entrada_busca, combo_grupo, arvore = self._montar_lista_com_filtro(
            master, "Produtos considerados na análise", ("check", "produto", "grupo", "freq_simples", "freq_acumulado")
        )

        self.check_somente_alto_giro = ttk.Checkbutton(
            frame,
            text="Considerar somente produtos de alto giro (marcados abaixo) em todos os relatórios e gráficos",
            command=self._marcar_configuracao_alterada,
        )
        self.check_somente_alto_giro.state(["selected", "!alternate"])
        self.check_somente_alto_giro.pack(fill="x", padx=6, pady=(6, 0), before=frame.winfo_children()[0])

        arvore.heading("check", text="Considerar?")
        arvore.heading("produto", text="Produto", command=lambda: self._ordenar_produtos("rotulo"))
        arvore.heading("grupo", text="Grupo")
        arvore.heading("freq_simples", text="% Receita", command=lambda: self._ordenar_produtos("freq_simples"))
        arvore.heading("freq_acumulado", text="% Receita Acumulada", command=lambda: self._ordenar_produtos("freq_acumulado"))
        arvore.column("check", width=80, anchor="center")
        arvore.column("produto", width=230, anchor="w")
        arvore.column("grupo", width=70, anchor="center")
        arvore.column("freq_simples", width=90, anchor="e")
        arvore.column("freq_acumulado", width=100, anchor="e")

        arvore.bind("<Button-1>", lambda evento: self._alternar_checkbox_arvore(evento, arvore, self.estado_produtos))
        entrada_busca.bind("<KeyRelease>", lambda evento: self._buscar_produtos(entrada_busca.get()))
        combo_grupo.bind("<<ComboboxSelected>>", lambda evento: self._renderizar_produtos(entrada_busca.get()))

        self.arvore_produtos = arvore
        self.entrada_busca_produtos = entrada_busca
        self.combo_grupo_produtos = combo_grupo
        self.dados_produtos = []  # lista de dicts: chave, rotulo, grupo, freq_simples, freq_acumulado (% de receita)
        return frame

    def _alternar_checkbox_arvore(self, evento, arvore, dicionario_estado):
        if arvore.identify_region(evento.x, evento.y) != "cell":
            return
        coluna = arvore.identify_column(evento.x)
        linha = arvore.identify_row(evento.y)
        if not linha or coluna != "#1":
            return
        novo_valor = not dicionario_estado.get(linha, False)
        dicionario_estado[linha] = novo_valor
        if dicionario_estado is self.estado_produtos:
            # Marcado à mão — não é mais resincronizado com o Grupo 1 em
            # _recalcular_classificacoes(), senão o clique seria desfeito na
            # próxima vez que o corte de produtos for recalculado.
            self._produtos_manual.add(linha)
        valores = list(arvore.item(linha, "values"))
        valores[0] = "☑" if novo_valor else "☐"
        arvore.item(linha, values=valores)
        self._marcar_configuracao_alterada()

    def _marcar_configuracao_alterada(self):
        """Destaca visualmente o botão de prévia quando clientes/produtos mudam e a contagem fica desatualizada."""
        if hasattr(self, "botao_atualizar_preview"):
            self.botao_atualizar_preview.config(text="⚠ Atualizar prévia (parâmetros alterados)", style="Accent.TButton")
        self._salvar_configuracao_automatica()

    # ------------------------------------------------------------------
    # Carregamento e limpeza do CSV
    # ------------------------------------------------------------------

    def _selecionar_csv(self):
        caminho = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not caminho:
            return

        self._definir_status("Carregando CSV...")
        self._registrar_log(f"Carregando CSV: {caminho}")
        self.progress.start(10)
        self.update_idletasks()
        try:
            self.df, linhas_vazias = af.carregar_csv(caminho)
            if linhas_vazias > 0:
                messagebox.showinfo("Linhas vazias ignoradas", f"{linhas_vazias} linha(s) com Ano ou Mês vazio ignorada(s).")
        except af.ErroCarregamentoCSV as exc:
            self.progress.stop()
            messagebox.showerror("Erro ao carregar CSV", str(exc))
            self._registrar_log(f"Falha ao carregar CSV: {exc}", nivel="error")
            self._definir_status("Falha ao carregar CSV.")
            return
        except Exception as exc:
            self.progress.stop()
            messagebox.showerror("Erro inesperado", f"Falha inesperada ao carregar o CSV:\n{exc}")
            self._registrar_log(f"Falha inesperada ao carregar CSV: {exc}", nivel="error")
            self._definir_status("Falha ao carregar CSV.")
            return
        self.progress.stop()

        self._caminho_csv_atual = os.path.abspath(caminho)
        self.label_arquivo.config(text=os.path.basename(caminho))
        self.botao_limpar_base.config(state="normal")
        self._popular_lista_clientes()
        self._popular_lista_produtos()
        self._popular_lista_lojas()
        self._carregar_configuracao_automatica()
        self._registrar_log(f"CSV carregado com sucesso: {len(self.df)} linhas, "
                             f"{self.df['Cliente'].nunique()} clientes, {self.df['descricao'].nunique()} produtos.")
        self._definir_status(f"CSV carregado: {len(self.df)} linhas.")

    def _limpar_base(self):
        resposta = messagebox.askyesno("Limpar base", "Isso vai descartar o CSV carregado e todos os resultados. Continuar?")
        if not resposta:
            return

        self.df = None
        self.resultados_analise = None
        self.estado_clientes = {}
        self.estado_produtos = {}
        self._produtos_manual = set()
        self._caminho_csv_atual = None
        self.dados_clientes = []
        self.dados_produtos = []

        for filho in self.container_lojas.winfo_children():
            filho.destroy()
        self.vars_lojas = {}
        self.label_lojas_vazio = ttk.Label(self.container_lojas, text="Carregue um CSV para escolher as lojas.", foreground="gray")
        self.label_lojas_vazio.pack(anchor="w")

        for linha in self.arvore_clientes.get_children():
            self.arvore_clientes.delete(linha)
        for linha in self.arvore_produtos.get_children():
            self.arvore_produtos.delete(linha)

        self.entrada_busca_clientes.delete(0, "end")
        self.entrada_busca_produtos.delete(0, "end")
        self.combo_grupo_clientes.set("Todos")
        self.combo_grupo_clientes["values"] = ["Todos"]
        self.combo_grupo_produtos.set("Todos")
        self.combo_grupo_produtos["values"] = ["Todos"]

        self.label_arquivo.config(text="Nenhum arquivo carregado")
        self.botao_limpar_base.config(state="disabled")
        self.label_contagens_grupos.config(text="Contagens: clique em 'Atualizar prévia' para calcular.")
        self.botao_atualizar_preview.config(text="Atualizar prévia dos grupos", style="TButton")

        self.texto_log.config(state="normal")
        self.texto_log.delete("1.0", "end")
        self.texto_log.config(state="disabled")

        self._registrar_log("Base de dados limpa pelo usuário. Sistema pronto para novo arquivo.")
        self._definir_status("Base limpa. Selecione um novo CSV.")

    def _popular_lista_clientes(self):
        receita_cliente = self.df.groupby("Cliente")["Receita"].sum().sort_values(ascending=False)
        total = receita_cliente.sum() or 1
        self.dados_clientes = [
            {"cliente": cliente, "receita": receita, "percentual": receita / total * 100, "grupo": "-"}
            for cliente, receita in receita_cliente.items()
        ]
        self.estado_clientes = {item["cliente"]: False for item in self.dados_clientes}
        self._ordem_clientes = ("receita", True)
        self._renderizar_clientes("")

    def _buscar_clientes(self, texto):
        # Buscar por nome deve achar o cliente esteja ele em qualquer grupo —
        # senão, procurar alguém que não está no grupo filtrado no momento
        # simplesmente nunca aparece (parece que "sumiu"/não foi encontrado).
        if texto.strip() and self.combo_grupo_clientes.get() != "Todos":
            self.combo_grupo_clientes.set("Todos")
        self._renderizar_clientes(texto)

    def _ordenar_clientes(self, campo):
        campo_atual, decrescente_atual = getattr(self, "_ordem_clientes", (None, True))
        decrescente = (not decrescente_atual) if campo == campo_atual else True
        self._ordem_clientes = (campo, decrescente)
        self.dados_clientes.sort(key=lambda item: item[campo], reverse=decrescente)
        self._renderizar_clientes(self.entrada_busca_clientes.get())

    def _renderizar_clientes(self, filtro):
        arvore = self.arvore_clientes
        for linha in arvore.get_children():
            arvore.delete(linha)
        filtro_lower = filtro.strip().lower()
        filtro_grupo = getattr(self, "combo_grupo_clientes", None)
        filtro_grupo = filtro_grupo.get() if filtro_grupo else "Todos"
        posicao = 0
        for item in self.dados_clientes:
            if filtro_lower and filtro_lower not in item["cliente"].lower():
                continue
            if filtro_grupo != "Todos" and item["grupo"] != filtro_grupo:
                continue
            marcado = self.estado_clientes.get(item["cliente"], False)
            arvore.insert("", "end", iid=item["cliente"], tags=("par" if posicao % 2 == 0 else "impar",), values=(
                "☑" if marcado else "☐",
                item["cliente"],
                _formatar_moeda_br(item["receita"]),
                f"{item['percentual']:.2f}%",
                item["grupo"],
            ))
            posicao += 1

    def _popular_lista_produtos(self):
        qtd_nao_harmonizados = af.contar_produtos_nao_harmonizados(self.df)
        produtos = sorted(p for p in self.df["descricao"].unique() if p != af.DESCRICAO_NAO_HARMONIZADA)

        self.dados_produtos = []
        self._produtos_manual = set()  # csv novo — nenhuma escolha manual ainda
        if qtd_nao_harmonizados > 0:
            rotulo = f"⚠ {af.DESCRICAO_NAO_HARMONIZADA} ({qtd_nao_harmonizados} lançamentos sem descrição)"
            self.dados_produtos.append({"chave": af.DESCRICAO_NAO_HARMONIZADA, "rotulo": rotulo, "grupo": "-", "freq_simples": 0.0, "freq_acumulado": 0.0})
        self.dados_produtos.extend(
            {"chave": produto, "rotulo": produto, "grupo": "-", "freq_simples": 0.0, "freq_acumulado": 0.0}
            for produto in produtos
        )

        self._ordem_produtos = ("freq_simples", True)  # padrão: maior % de receita primeiro
        self._recalcular_classificacoes()

    def _buscar_produtos(self, texto):
        # Mesma lógica de _buscar_clientes: busca por nome ignora o filtro de
        # grupo ativo, senão um produto fora do grupo filtrado nunca aparece.
        if texto.strip() and self.combo_grupo_produtos.get() != "Todos":
            self.combo_grupo_produtos.set("Todos")
        self._renderizar_produtos(texto)

    def _ordenar_produtos(self, campo):
        campo_atual, decrescente_atual = getattr(self, "_ordem_produtos", (None, True))
        decrescente = (not decrescente_atual) if campo == campo_atual else True
        self._ordem_produtos = (campo, decrescente)
        chave = (lambda item: item["rotulo"].lower()) if campo == "rotulo" else (lambda item: item[campo])
        self.dados_produtos.sort(key=chave, reverse=decrescente)
        self._renderizar_produtos(self.entrada_busca_produtos.get())

    def _renderizar_produtos(self, filtro):
        arvore = self.arvore_produtos
        for linha in arvore.get_children():
            arvore.delete(linha)
        filtro_lower = filtro.strip().lower()
        filtro_grupo = getattr(self, "combo_grupo_produtos", None)
        filtro_grupo = filtro_grupo.get() if filtro_grupo else "Todos"
        posicao = 0
        for item in self.dados_produtos:
            if filtro_lower and filtro_lower not in item["rotulo"].lower():
                continue
            if filtro_grupo != "Todos" and item["grupo"] != filtro_grupo:
                continue
            marcado = self.estado_produtos.get(item["chave"], True)
            arvore.insert("", "end", iid=item["chave"], tags=("par" if posicao % 2 == 0 else "impar",), values=(
                "☑" if marcado else "☐", item["rotulo"], item["grupo"],
                f"{item['freq_simples']:.2f}%", f"{item['freq_acumulado']:.2f}%",
            ))
            posicao += 1

    def _clientes_excluidos(self):
        return [cliente for cliente, excluido in self.estado_clientes.items() if excluido]

    def _produtos_excluidos(self):
        return [produto for produto, considerado in self.estado_produtos.items() if not considerado]

    def _lojas_selecionadas(self):
        return [loja for loja, var in self.vars_lojas.items() if var.get()]

    def _popular_lista_lojas(self):
        """
        (Re)monta os checkboxes de loja a partir do CSV recém-carregado —
        as lojas variam de base pra base, então a lista não dá pra ser
        fixa: precisa ser reconstruída a cada _selecionar_csv/_limpar_base,
        igual às listas de clientes/produtos.
        """
        for filho in self.container_lojas.winfo_children():
            filho.destroy()
        self.vars_lojas = {}

        lojas = sorted(self.df["Loja"].dropna().unique())
        for loja in lojas:
            var = tk.BooleanVar(master=self, value=True)
            var.trace_add("write", lambda *_: self._marcar_configuracao_alterada())
            ttk.Checkbutton(self.container_lojas, text=loja, variable=var).pack(anchor="w")
            self.vars_lojas[loja] = var

    def _filtrar_por_lojas(self, df):
        """
        Filtra pelas lojas marcadas em "Lojas incluídas na análise" — extraído
        de _dataframe_para_analise pra ser reaproveitado também na prévia de
        classificação (_recalcular_classificacoes). Sem isso, a % de receita
        mostrada em "Produtos considerados"/"Clientes" na tela de Configurações
        vinha da base INTEIRA (todas as lojas), divergindo do que o relatório
        de verdade calcula quando alguma loja está desmarcada.
        """
        if not self.vars_lojas:
            return df
        lojas_selecionadas = self._lojas_selecionadas()
        if len(lojas_selecionadas) < len(self.vars_lojas):
            return df[df["Loja"].isin(lojas_selecionadas)]
        return df

    def _dataframe_para_analise(self):
        """
        DataFrame efetivo para qualquer consumidor (relatório padrão,
        gráficos, relatórios personalizados): filtra pelas lojas marcadas em
        "Lojas incluídas na análise" e, com o checkbox "Considerar somente
        produtos de alto giro" marcado (padrão), também filtra fora os
        produtos desmarcados na lista "Produtos considerados na análise" —
        senão usa a base inteira (sem filtro de produto). Um único ponto pra
        essas regras valerem igual em todo lugar, em vez de cada aba decidir
        sozinha se respeita ou não as listas de loja/produto.
        """
        if self.df is None:
            return None

        df_filtrado = self._filtrar_por_lojas(self.df)

        if self.check_somente_alto_giro.instate(["selected"]):
            produtos_excluidos = self._produtos_excluidos()
            if produtos_excluidos:
                df_filtrado = df_filtrado[~df_filtrado["descricao"].isin(produtos_excluidos)]

        return df_filtrado

    # ------------------------------------------------------------------
    # Salvar/carregar configuração da análise (parâmetros + exclusões) em JSON
    # ------------------------------------------------------------------

    def _construir_configuracao_atual(self):
        return {
            "corte_produtos": self.entrada_corte_produtos.get(),
            "cortes_grupo": [entrada.get() for entrada in self.entradas_corte_grupo],
            "max_por_grupo": self.entrada_max_por_grupo.get(),
            "periodos_queda": self.entrada_periodos_queda.get(),
            "granularidade": self.var_granularidade.get(),
            "clientes_excluidos": self._clientes_excluidos(),
            "lojas_selecionadas": self._lojas_selecionadas(),
            # Só os produtos que o usuário de fato clicou (_produtos_manual),
            # com o estado que ele escolheu — NÃO a lista inteira de
            # desmarcados (_produtos_excluidos()), que inclui produtos
            # desmarcados automaticamente só por não serem Grupo 1 no corte
            # atual. Salvar a lista inteira (formato antigo) fazia TODO
            # produto voltar marcado como "manual" ao recarregar, travando-o
            # pra sempre fora da resincronização automática — se o corte de
            # produtos mudasse depois e ele passasse a ser Grupo 1, o
            # checkbox nunca marcava sozinho (ver _aplicar_configuracao).
            "produtos_manual_estado": {
                produto: self.estado_produtos.get(produto, False) for produto in self._produtos_manual
            },
            "formato_exportacao": getattr(self, "var_formato_exportacao", None) and self.var_formato_exportacao.get(),
        }

    def _caminho_configuracao_automatica(self):
        return recursos.caminho_dados_locais("config_automatica.json")

    def _ler_configuracoes_automaticas(self):
        """Todas as configurações automáticas salvas, por CSV (ver _salvar_configuracao_automatica). {} se o arquivo não existir/estiver corrompido."""
        caminho = self._caminho_configuracao_automatica()
        if not os.path.exists(caminho):
            return {}
        try:
            with open(caminho, "r", encoding="utf-8") as arquivo:
                return json.load(arquivo)
        except (OSError, json.JSONDecodeError):
            return {}

    def _salvar_configuracao_automatica(self):
        """
        Persiste silenciosamente (sem diálogo) os parâmetros e exclusões
        atuais a cada mudança — sem isso, desmarcar um produto/cliente só
        vale pra sessão atual: fechar e reabrir o programa (ou só recarregar
        o CSV) volta tudo ao padrão automático (Grupo 1), obrigando a
        desmarcar de novo toda vez. Chamada de _marcar_configuracao_alterada.
        Diferente de "Salvar configuração" (ação explícita do usuário, para
        um arquivo escolhido por ele) — este arquivo é interno, recarregado
        sozinho em _selecionar_csv.

        Guardado por CSV (caminho absoluto como chave) num único arquivo —
        sem isso, a exclusão de produtos de uma base (ex.: gap.base.csv)
        vazava pra outra base com nomes de produto parecidos (ex.:
        data.teste.csv), já que os nomes batem mas os produtos "certos"
        pra cada base são diferentes.
        """
        if not self._caminho_csv_atual:
            return  # nenhum CSV carregado ainda — nada pra chavear
        try:
            configuracao = self._construir_configuracao_atual()
        except AttributeError:
            return  # interface ainda não terminou de montar — nada a salvar ainda
        todas = self._ler_configuracoes_automaticas()
        todas[self._caminho_csv_atual] = configuracao
        try:
            with open(self._caminho_configuracao_automatica(), "w", encoding="utf-8") as arquivo:
                json.dump(todas, arquivo, ensure_ascii=False, indent=2)
        except OSError:
            pass  # não impede o uso do programa se não puder gravar

    def _carregar_configuracao_automatica(self):
        """Restaura silenciosamente a última configuração salva automaticamente para o CSV atual, se existir (ver _salvar_configuracao_automatica)."""
        if not self._caminho_csv_atual:
            return
        configuracao = self._ler_configuracoes_automaticas().get(self._caminho_csv_atual)
        if configuracao is None:
            return
        self._aplicar_configuracao(configuracao)

    def _salvar_configuracao_analise(self):
        try:
            configuracao = self._construir_configuracao_atual()
        except AttributeError:
            messagebox.showwarning("Salvar configuração", "A interface ainda não terminou de carregar.")
            return

        caminho = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Configuração (JSON)", "*.json")])
        if not caminho:
            return
        with open(caminho, "w", encoding="utf-8") as arquivo:
            json.dump(configuracao, arquivo, ensure_ascii=False, indent=2)
        self._registrar_log(f"Configuração da análise salva em: {caminho}")
        messagebox.showinfo("Salvar configuração", "Configuração salva com sucesso.")

    def _carregar_configuracao_analise(self):
        caminho = filedialog.askopenfilename(filetypes=[("Configuração (JSON)", "*.json")])
        if not caminho:
            return
        try:
            with open(caminho, "r", encoding="utf-8") as arquivo:
                configuracao = json.load(arquivo)
        except Exception as exc:
            messagebox.showerror("Carregar configuração", f"Não foi possível ler o arquivo:\n{exc}")
            return

        self._aplicar_configuracao(configuracao)
        self._registrar_log(f"Configuração da análise carregada de: {caminho}")
        if self.df is not None:
            messagebox.showinfo("Carregar configuração", "Configuração carregada e aplicada com sucesso.")
        else:
            messagebox.showinfo(
                "Carregar configuração",
                "Parâmetros carregados. Selecione o CSV para também aplicar clientes/produtos excluídos salvos.",
            )

    def _aplicar_configuracao(self, configuracao):
        self.entrada_corte_produtos.delete(0, "end")
        self.entrada_corte_produtos.insert(0, configuracao.get("corte_produtos", "80"))
        self._escrever_cortes_grupos(configuracao.get("cortes_grupo", ["30", "50", "60"]))
        self.entrada_max_por_grupo.delete(0, "end")
        self.entrada_max_por_grupo.insert(0, configuracao.get("max_por_grupo", "10"))
        # ttk.Entry "disabled" bloqueia insert/delete programático em silêncio
        # (sem erro, mas sem efeito) -- se o relatório-gatilho estiver
        # desmarcado no momento de carregar a configuração, o campo fica
        # "travado" no valor antigo sem avisar. Habilita antes de escrever e
        # deixa o estado final por conta de _atualizar_estado_campos_condicionais_catalogo().
        self.entrada_periodos_queda.config(state="normal")
        self.entrada_periodos_queda.delete(0, "end")
        self.entrada_periodos_queda.insert(0, configuracao.get("periodos_queda", "2"))
        self._atualizar_estado_campos_condicionais_catalogo()

        self.var_granularidade.set(configuracao.get("granularidade", "Mensal"))

        if hasattr(self, "var_formato_exportacao") and configuracao.get("formato_exportacao"):
            self.var_formato_exportacao.set(configuracao["formato_exportacao"])

        if self.df is not None:
            clientes_excluidos_salvos = set(configuracao.get("clientes_excluidos", []))
            for cliente in self.estado_clientes:
                self.estado_clientes[cliente] = cliente in clientes_excluidos_salvos

            # None (chave ausente) = configuração salva antes desse recurso
            # existir — mantém o padrão (todas marcadas) em vez de desmarcar
            # tudo por engano.
            lojas_selecionadas_salvas = configuracao.get("lojas_selecionadas")
            if lojas_selecionadas_salvas is not None:
                lojas_selecionadas_salvas = set(lojas_selecionadas_salvas)
                for loja, var in self.vars_lojas.items():
                    var.set(loja in lojas_selecionadas_salvas)

            # _recalcular_classificacoes() já resincroniza "alto giro" com o
            # Grupo 1 do corte de produtos recém-carregado — precisa rodar
            # ANTES da lista salva, senão o passo abaixo (explícito) seria
            # sobrescrito pelo padrão de Grupo 1.
            self._recalcular_classificacoes()

            # None (chave ausente) = configuração salva antes desse recurso
            # existir — não sobrescreve o padrão (Grupo 1) recém-aplicado.
            # Dict vazio é uma escolha explícita do usuário (nenhuma exceção
            # manual) e é respeitado normalmente.
            produtos_manual_estado = configuracao.get("produtos_manual_estado")
            if produtos_manual_estado is not None:
                for produto, considerado in produtos_manual_estado.items():
                    if produto in self.estado_produtos:
                        self.estado_produtos[produto] = considerado
                        self._produtos_manual.add(produto)
            else:
                # Compatibilidade com configurações salvas no formato antigo
                # ("produtos_excluidos": lista inteira de desmarcados, sem
                # distinguir escolha manual de resultado automático do corte
                # de então). Aplica o estado salvo só nesta carga, mas SEM
                # marcar como manual — assim, na próxima reclassificação
                # (mudar o corte e clicar "Atualizar", por exemplo), esses
                # produtos voltam a resincronizar com o Grupo 1 normalmente,
                # em vez de ficarem travados fora da lista pra sempre.
                produtos_excluidos_salvos = configuracao.get("produtos_excluidos")
                if produtos_excluidos_salvos is not None:
                    produtos_excluidos_salvos = set(produtos_excluidos_salvos)
                    for produto in produtos_excluidos_salvos:
                        if produto in self.estado_produtos:
                            self.estado_produtos[produto] = False

    # ------------------------------------------------------------------
    # Parâmetros: sugestão e pré-visualização de grupos
    # ------------------------------------------------------------------

    def _ler_cortes_grupos(self):
        return [float(entrada.get().replace(",", ".")) for entrada in self.entradas_corte_grupo]

    def _escrever_cortes_grupos(self, cortes):
        for entrada, valor in zip(self.entradas_corte_grupo, cortes):
            entrada.delete(0, "end")
            entrada.insert(0, str(valor))

    def _sugerir_cortes_automaticamente(self):
        if self.df is None:
            messagebox.showwarning("Parâmetros", "Carregue um CSV antes de ajustar os parâmetros.")
            return
        try:
            cortes_iniciais = self._ler_cortes_grupos()
            max_por_grupo = int(self.entrada_max_por_grupo.get())
        except ValueError:
            messagebox.showerror("Parâmetros inválidos", "Verifique os campos numéricos dos grupos.")
            return

        cortes, contagens = af.sugerir_cortes_grupos(
            self.df, self._clientes_excluidos(), cortes_iniciais, max_por_grupo, desconsiderar_balcao=self.check_balcao.instate(["selected"])
        )
        self._escrever_cortes_grupos(cortes)
        self._registrar_log(f"Cortes sugeridos automaticamente: {cortes} (máx. {max_por_grupo} clientes/grupo).")
        self._recalcular_classificacoes()

        partes_resumo = "\n".join(
            f"  Grupo {i + 1}: até {corte}% da receita ({contagens[i]} clientes)"
            for i, corte in enumerate(cortes)
        )
        mudou = [round(a, 1) != round(b, 1) for a, b in zip(cortes_iniciais, cortes)]
        aviso_extra = ""
        if any(mudou):
            aviso_extra = (
                "\n\nOs percentuais foram reduzidos em relação ao que você tinha digitado —"
                " isso é esperado quando a receita está espalhada entre muitos clientes: para"
                " caber no máximo definido, o corte de % precisa ficar menor."
            )
        messagebox.showinfo(
            "Sugerir cortes automaticamente",
            f"Cortes ajustados para respeitar o máximo de {max_por_grupo} clientes por grupo:\n\n"
            f"{partes_resumo}\n  Demais: {contagens[-1]} clientes"
            f"{aviso_extra}",
        )

    def _pre_visualizar_grupos(self):
        self._recalcular_classificacoes()

    def _recalcular_classificacoes(self):
        """
        Recalcula, com os parâmetros ATUAIS da tela, a que grupo cada cliente
        e cada produto pertence (mais o % de receita de cada produto — a
        coluna se chama "% Receita" na tela, não frequência de compra), e
        atualiza as colunas "Grupo"/"% Receita" nas duas listas — é a mesma
        classificação que rege os relatórios de segmentação, mas em versão
        rápida (agregada, não por período) só para a prévia na tela.
        """
        if self.df is None:
            return
        try:
            cortes = self._ler_cortes_grupos()
            corte_produtos = float(self.entrada_corte_produtos.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Parâmetros inválidos", "Verifique os campos numéricos de parâmetros.")
            return
        if any(cortes[i] >= cortes[i + 1] for i in range(len(cortes) - 1)) or any(c <= 0 or c >= 100 for c in cortes):
            messagebox.showerror("Parâmetros inválidos", "Os cortes de grupo devem ser crescentes e estar entre 0 e 100.")
            return
        if not (0 < corte_produtos < 100):
            messagebox.showerror("Parâmetros inválidos", "O corte de produtos deve estar entre 0 e 100.")
            return

        clientes_excluidos = set(self._clientes_excluidos())
        # Mesma base usada pelo relatório de verdade (menos o corte de
        # produtos, que é justamente o que esta prévia está calculando) —
        # sem isso, a % de receita aqui vinha de TODAS as lojas, mesmo com
        # alguma desmarcada em "Lojas incluídas na análise", divergindo do
        # relatório gerado de fato.
        base_classificacao = self._filtrar_por_lojas(self.df)

        classificacao_clientes = af.classificar_clientes_agregado(base_classificacao, clientes_excluidos, cortes, desconsiderar_balcao=self.check_balcao.instate(["selected"]))
        mapa_grupo_cliente = dict(zip(classificacao_clientes["Cliente"], classificacao_clientes["Faixa"]))
        mapa_percentual_cliente = dict(zip(classificacao_clientes["Cliente"], classificacao_clientes["Percentual_Individual"]))
        for item in self.dados_clientes:
            if item["cliente"] in clientes_excluidos:
                item["grupo"] = "Excluído"
                item["percentual"] = 0.0
            else:
                item["grupo"] = mapa_grupo_cliente.get(item["cliente"], "-")
                item["percentual"] = mapa_percentual_cliente.get(item["cliente"], 0.0)

        classificacao_produtos = af.classificar_produtos_agregado(base_classificacao, corte_produtos, clientes_excluidos=clientes_excluidos)
        mapa_grupo_produto = dict(zip(classificacao_produtos["descricao"], classificacao_produtos["Faixa"]))
        mapa_freq_simples_produto = dict(zip(classificacao_produtos["descricao"], classificacao_produtos["Freq_Simples"]))
        mapa_freq_acumulado_produto = dict(zip(classificacao_produtos["descricao"], classificacao_produtos["Freq_Acumulado"]))
        for item in self.dados_produtos:
            item["grupo"] = mapa_grupo_produto.get(item["chave"], "-")
            item["freq_simples"] = mapa_freq_simples_produto.get(item["chave"], 0.0)
            item["freq_acumulado"] = mapa_freq_acumulado_produto.get(item["chave"], 0.0)
        # Reaplica o critério de ordenação atual (padrão: mais frequentes
        # primeiro) agora que freq_simples/freq_acumulado foram recalculados
        # — sem isso, a lista ficaria na ordem alfabética original até o
        # usuário clicar manualmente num cabeçalho.
        campo_ordem, decrescente_ordem = getattr(self, "_ordem_produtos", ("freq_simples", True))
        chave_ordem = (lambda item: item["rotulo"].lower()) if campo_ordem == "rotulo" else (lambda item: item[campo_ordem])
        self.dados_produtos.sort(key=chave_ordem, reverse=decrescente_ordem)
        # "Alto giro" = Grupo 1 pelo corte de receita ATUAL — recalculado
        # aqui (não só na primeira vez que o CSV carrega) pra não desalinhar
        # dos checkboxes quando o corte muda (ex.: ao carregar uma
        # configuração salva com um corte de produtos diferente). Produtos
        # marcados/desmarcados à mão (_produtos_manual) ficam de fora dessa
        # resincronização — senão um clique do usuário seria desfeito na
        # próxima reclassificação.
        for item in self.dados_produtos:
            if item["chave"] not in self._produtos_manual:
                self.estado_produtos[item["chave"]] = item["grupo"] == "Grupo 1"

        nomes_grupos_clientes = [f"Grupo {i + 1}" for i in range(len(cortes))] + ["Demais", "Balcão", "Excluído"]
        if hasattr(self, "combo_grupo_clientes"):
            self.combo_grupo_clientes["values"] = ["Todos"] + nomes_grupos_clientes
            # Só troca o filtro sozinho se o usuário ainda não escolheu nada
            # específico ("Todos" = nenhuma preferência) — assim "Atualizar"
            # já mostra os clientes relevantes de cara, sem esconder uma
            # escolha manual que o usuário já tenha feito.
            if self.combo_grupo_clientes.get() == "Todos":
                self.combo_grupo_clientes.set("Grupo 1")
        if hasattr(self, "combo_grupo_produtos"):
            self.combo_grupo_produtos["values"] = ["Todos", "Grupo 1", "Demais"]
            if self.combo_grupo_produtos.get() == "Todos":
                self.combo_grupo_produtos.set("Grupo 1")

        contagens = af.contar_clientes_por_grupo(self.df, clientes_excluidos, cortes, desconsiderar_balcao=self.check_balcao.instate(["selected"]))
        self._exibir_contagens_grupos(cortes, contagens)

        self._renderizar_clientes(self.entrada_busca_clientes.get())
        self._renderizar_produtos(self.entrada_busca_produtos.get())

        self.botao_atualizar_preview.config(text="Atualizar prévia dos grupos", style="TButton")
        self._registrar_log(f"Prévia atualizada: cortes de grupo={cortes}, corte de produtos={corte_produtos}%.")

    def _exibir_contagens_grupos(self, cortes, contagens):
        partes = [f"Grupo {i + 1} (até {corte}%): {contagens[i]} clientes" for i, corte in enumerate(cortes)]
        partes.append(f"Demais: {contagens[-1]} clientes")
        self.label_contagens_grupos.config(text="  |  ".join(partes))

    # ------------------------------------------------------------------
    # Log de execução (arquivo + painel global na interface)
    # ------------------------------------------------------------------

    def _registrar_log(self, mensagem, nivel="info"):
        if nivel == "error":
            self.logger.error(mensagem)
        else:
            self.logger.info(mensagem)
        self.fila_eventos.put(("log", mensagem))

    def _bombear_fila_eventos(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                # Um handler (ex.: fim de instalação de atualização) pode
                # fechar a janela no meio da leitura da fila — sem essa
                # checagem, o próximo item ainda seria processado contra
                # widgets já destruídos (TclError).
                if not self.winfo_exists():
                    return
                tipo, dados = self.fila_eventos.get_nowait()
                if tipo == "log":
                    self._anexar_log_ui(dados)
                elif tipo == "concluido":
                    self._ao_concluir_geracao(dados)
                elif tipo == "erro":
                    self._ao_falhar_geracao(dados)
                elif tipo == "atualizacao_checada":
                    self._ao_checar_atualizacao(dados)
                elif tipo == "atualizacao_progresso":
                    self._definir_status(f"Baixando atualização... {dados}%")
                elif tipo == "atualizacao_instalacao_erro":
                    self._ao_falhar_instalacao_atualizacao(dados)
                elif tipo == "atualizacao_instalacao_ok":
                    self._ao_concluir_instalacao_atualizacao()
                elif tipo == "comando_instancia_unica":
                    self._ao_receber_comando_instancia_unica(dados)
        except queue.Empty:
            pass
        self._id_after_fila = self.after(150, self._bombear_fila_eventos)

    def _escutar_outras_instancias(self):
        """
        Roda numa thread separada, bloqueada em accept() — quando o usuário
        tenta abrir uma segunda instância do programa, ela detecta que a
        porta já está em uso (ver _tentar_registrar_instancia_unica) e, em
        vez de abrir uma segunda janela, pergunta ao usuário e manda um
        comando curto pra ESSA instância através dessa conexão. Só posta na
        fila de eventos — quem manipula a janela de fato é sempre a thread
        principal (via _bombear_fila_eventos), nunca esta thread.
        """
        while True:
            try:
                conexao, _endereco = self._servidor_instancia_unica.accept()
            except OSError:
                return  # socket fechado (programa encerrando) — sai da thread
            try:
                dados = conexao.recv(64).decode("utf-8", errors="ignore").strip()
            finally:
                conexao.close()
            if dados:
                self.fila_eventos.put(("comando_instancia_unica", dados))

    def _ao_receber_comando_instancia_unica(self, comando):
        if comando == "ATIVAR":
            self.deiconify()
            self.lift()
            self.focus_force()
            self._registrar_log("Outra tentativa de abrir o programa foi redirecionada para esta janela.")
        elif comando == "FECHAR":
            self._registrar_log("Fechando a pedido de uma nova instância do programa.")
            # Adiado pra fora deste loop (_bombear_fila_eventos) de propósito:
            # _ao_fechar_janela() faz after_cancel(self._id_after_fila), mas
            # o id atual é exatamente o desta chamada em andamento — não dá
            # pra cancelar um "after" que já está executando. Chamado direto
            # aqui, a janela é destruída e o loop, ao voltar da função,
            # ainda reagenda um novo after(150, ...) na linha final (fora do
            # try/except) — que dispara 150ms depois contra uma janela já
            # destruída (TclError "application has been destroyed",
            # reproduzido e confirmado no log). self.after(0, ...) roda isso
            # num ciclo novo do event loop, depois que este já terminou (e
            # já reagendou o próprio after) — daí o cancel funciona de
            # verdade, contra um agendamento genuinamente pendente.
            self.after(0, self._ao_fechar_janela)

    def _verificar_status_ultima_atualizacao(self):
        # Lê o resultado de uma troca de arquivo agendada na execução
        # anterior (ver aplicar_atualizacao/verificar_status_ultima_
        # atualizacao em atualizacoes.py) — sem isso, uma falha na troca
        # (ex.: antivírus apagando o .exe baixado antes do "move" rodar)
        # era completamente silenciosa: o usuário reabria e via a mesma
        # versão de sempre, sem nenhuma pista do motivo.
        try:
            resultado = atualizacoes.verificar_status_ultima_atualizacao()
        except Exception as exc:
            self.logger.error(f"Falha ao verificar status da última atualização: {exc}")
            return
        if resultado is None:
            return
        sucesso, detalhe = resultado
        if sucesso:
            self._registrar_log("Atualização instalada com sucesso na abertura anterior.")
            return
        mensagem_detalhe = f"\n\nDetalhe técnico: {detalhe}" if detalhe else ""
        self._registrar_log(f"Falha ao concluir a troca do executável na última atualização.{mensagem_detalhe}", nivel="error")
        messagebox.showwarning(
            "Atualização não concluída",
            "A última tentativa de atualização automática baixou o arquivo, mas não "
            "conseguiu substituir o programa atual (o antivírus pode ter bloqueado ou "
            "removido o arquivo baixado antes da troca).\n\n"
            f"Você continua na versão {VERSAO_ATUAL}. Baixe manualmente pela página de "
            f"releases no GitHub, ou tente atualizar de novo pelo menu Arquivo."
            f"{mensagem_detalhe}",
        )

    def _verificar_atualizacoes(self, manual=False):
        # Roda em thread separada (chamada de rede) — nunca deve travar a
        # abertura do sistema. A checagem automática do startup só interrompe
        # o usuário se houver versão nova (falha vira só uma linha no log,
        # pra dar pra diagnosticar depois); a manual (menu Arquivo > Buscar
        # atualizações) sempre mostra o resultado, incluindo erro.
        try:
            resultado = atualizacoes.verificar_nova_versao()
        except Exception as exc:
            self.fila_eventos.put(("atualizacao_checada", ("erro", str(exc), manual)))
            return
        if resultado:
            self.fila_eventos.put(("atualizacao_checada", ("disponivel", resultado, manual)))
        else:
            self.fila_eventos.put(("atualizacao_checada", ("atualizado", None, manual)))

    def _buscar_atualizacoes_manual(self):
        self._registrar_log("Verificando atualizações...")
        threading.Thread(target=self._verificar_atualizacoes, args=(True,), daemon=True).start()

    def _ao_checar_atualizacao(self, dados):
        status, info, manual = dados
        if status == "disponivel":
            tag, url_pagina, url_download_exe = info
            self._registrar_log(f"Nova versão disponível no GitHub: {tag} (versão atual: {VERSAO_ATUAL}).")

            if getattr(sys, "frozen", False) and url_download_exe:
                instalar = messagebox.askyesno(
                    "Nova versão disponível",
                    f"Há uma nova versão do {NOME_SISTEMA} disponível ({tag}).\n"
                    f"Versão instalada: {VERSAO_ATUAL}.\n\n"
                    "Deseja baixar e instalar agora? O programa vai fechar sozinho ao final — "
                    "é só abrir de novo pra usar a versão nova.",
                )
                if instalar:
                    self._baixar_e_instalar_atualizacao(url_download_exe)
            else:
                abrir = messagebox.askyesno(
                    "Nova versão disponível",
                    f"Há uma nova versão do {NOME_SISTEMA} disponível ({tag}).\n"
                    f"Versão instalada: {VERSAO_ATUAL}.\n\n"
                    "Deseja abrir a página de download agora?",
                )
                if abrir:
                    webbrowser.open(url_pagina)
        elif status == "atualizado":
            self._registrar_log(f"Checagem de atualização: versão {VERSAO_ATUAL} já é a mais recente.")
            if manual:
                messagebox.showinfo("Buscar atualizações", f"Você já está na versão mais recente ({VERSAO_ATUAL}).")
        elif status == "erro":
            self._registrar_log(f"Falha ao checar atualizações: {info}", nivel="error")
            if manual:
                messagebox.showerror(
                    "Buscar atualizações",
                    f"Não foi possível verificar atualizações:\n{info}\n\n"
                    "Verifique a conexão com a internet (ou se há proxy/firewall bloqueando "
                    "acesso a api.github.com) e tente novamente.",
                )

    def _baixar_e_instalar_atualizacao(self, url_download_exe):
        self._registrar_log("Baixando atualização...")
        self._definir_status("Baixando atualização... 0%")
        threading.Thread(target=self._baixar_e_instalar_thread, args=(url_download_exe,), daemon=True).start()

    def _baixar_e_instalar_thread(self, url_download_exe):
        try:
            caminho_novo_exe = atualizacoes.baixar_atualizacao(
                url_download_exe,
                callback_progresso=lambda pct: self.fila_eventos.put(("atualizacao_progresso", pct)),
            )
            atualizacoes.aplicar_atualizacao(caminho_novo_exe)
        except Exception as exc:
            self.fila_eventos.put(("atualizacao_instalacao_erro", str(exc)))
            return
        self.fila_eventos.put(("atualizacao_instalacao_ok", None))

    def _ao_falhar_instalacao_atualizacao(self, erro):
        self._registrar_log(f"Falha ao instalar atualização automaticamente: {erro}", nivel="error")
        self._definir_status("Falha ao instalar atualização.")
        messagebox.showerror(
            "Atualização",
            f"Não foi possível instalar a atualização automaticamente:\n{erro}\n\n"
            "Baixe manualmente pela página de releases no GitHub.",
        )

    def _ao_concluir_instalacao_atualizacao(self):
        # "Agendada", não "instalada": a troca de arquivo só acontece depois
        # que este processo fechar (aplicar_atualizacao em atualizacoes.py
        # roda um .bat em segundo plano que tenta por ~90s) — dizer
        # "instalada" aqui era enganoso, o log dizia sucesso mesmo quando a
        # troca falhava (ex.: outra janela do programa ainda aberta travando
        # o arquivo — não confirmava nada, só que o download deu certo).
        self._registrar_log("Atualização baixada — troca do arquivo agendada. Feche TODAS as janelas do programa pra ela ser concluída.")
        self._definir_status("Atualização baixada — feche o programa pra concluir a troca.")
        # O programa não se reabre sozinho de propósito (ver aplicar_atualizacao
        # em atualizacoes.py) — o antivírus bloqueia essa reabertura automática.
        messagebox.showinfo(
            "Atualização baixada",
            "A nova versão foi baixada; a troca do arquivo está agendada.\n\n"
            "Feche TODAS as janelas do programa (não só esta) e abra de novo "
            "pra usar a versão nova — com qualquer janela aberta, o arquivo "
            "fica travado e a troca não é concluída.",
        )
        # Fecha em um ciclo separado do loop de eventos, não aqui direto:
        # destruir a janela no meio da leitura da fila (_bombear_fila_eventos)
        # faz o próximo item pendente (esse log, por exemplo) ser processado
        # contra widgets já destruídos.
        self.after(10, self._ao_fechar_janela)

    def _anexar_log_ui(self, mensagem):
        marca_horario = datetime.now().strftime("%H:%M:%S")
        self.texto_log.config(state="normal")
        self.texto_log.insert("end", f"[{marca_horario}] {mensagem}\n")
        self.texto_log.see("end")
        self.texto_log.config(state="disabled")

    # ------------------------------------------------------------------
    # Aba "Relatório Padrão": catálogo de relatórios prontos
    # ------------------------------------------------------------------

    def _montar_aba_padrao(self, master):
        ttk.Label(
            master, text="Selecione quais relatórios prontos deseja incluir no Excel final.",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=10, pady=(10, 0))
        ttk.Label(
            master,
            text="Parâmetros gerais (base de dados, clientes/produtos, segmentação, período, granularidade) ficam em "
                 "Configurações. Os específicos de Alertas de Queda/Tendência e Erosão de Clientes aparecem abaixo, "
                 "junto do relatório correspondente — só valem se o relatório estiver marcado.",
            foreground="gray", wraplength=900, justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        barra_selecao = ttk.Frame(master)
        barra_selecao.pack(fill="x", padx=10)
        ttk.Button(barra_selecao, text="Selecionar todos", command=lambda: self._marcar_catalogo(True)).pack(side="left")
        ttk.Button(barra_selecao, text="Limpar seleção", command=lambda: self._marcar_catalogo(False)).pack(side="left", padx=6)
        self.label_contagem_catalogo = ttk.Label(barra_selecao, foreground="#1565c0")
        self.label_contagem_catalogo.pack(side="right")

        # "Exportação" (com o botão "Gerar Relatório Padrão") é empacotado
        # ANTES do catálogo de relatórios e com side="bottom", de propósito
        # — mesmo motivo já documentado em _montar_interface pro painel de
        # execução: o catálogo (fill="both", expand=True, pode crescer
        # bastante com muitos relatórios/parâmetros condicionais marcados)
        # é o único widget aqui com expand=True. Se ele fosse empacotado
        # primeiro, tomaria a cavidade toda em janelas sem altura suficiente,
        # e a área de exportação — com o botão de gerar — ficaria sem espaço
        # nenhum e sumiria da tela (reproduzido: catálogo grande + janela sem
        # altura de sobra = botão inacessível, sem nem scrollbar pra chegar
        # nele). Empacotando a área de exportação primeiro, com side="bottom",
        # ela sempre reserva seu espaço primeiro; é o catálogo que cede
        # espaço (fica mais apertado) quando a janela é pequena.
        area_exportacao = ttk.LabelFrame(master, text="Exportação")
        area_exportacao.pack(fill="x", side="bottom", padx=10, pady=(0, 10))

        barra_formato = ttk.Frame(area_exportacao)
        barra_formato.pack(pady=(10, 0))
        ttk.Label(barra_formato, text="Formato de exportação:").pack(side="left", padx=(0, 8))
        self.var_formato_exportacao = tk.StringVar(master=self, value="Excel")
        for formato in ("Excel", "PDF", "Word"):
            ttk.Radiobutton(
                barra_formato, text=formato, value=formato, variable=self.var_formato_exportacao,
                # command explícito além da variável ligada — o clique no radio nem sempre
                # escreve na variável de forma confiável (mesmo problema visto nas checkboxes
                # do catálogo), então forçamos aqui como garantia.
                command=lambda f=formato: self.var_formato_exportacao.set(f),
            ).pack(side="left", padx=4)
        ttk.Label(
            area_exportacao, text="PDF/Word mostram no máximo 50 linhas por tabela (formato de leitura, não de dados).\n"
                                  "Para a base completa (ex.: todos os clientes da segmentação ABC), use Excel.",
            justify="center", foreground="gray", font=("Segoe UI", 8),
        ).pack(pady=(4, 0))

        self.botao_gerar = ttk.Button(area_exportacao, text="Gerar Relatório Padrão", command=self._gerar_relatorio_padrao)
        self.botao_gerar.pack(pady=14)

        # Canvas + Scrollbar clássico do Tkinter (mesmo padrão já usado na
        # coluna de parâmetros de Configurações) — com a área de exportação
        # agora reservando seu espaço primeiro (ver comentário acima), o
        # catálogo pode ficar mais apertado que sua altura natural em janelas
        # sem espaço de sobra; sem isso, os relatórios de baixo (Boletins)
        # ficavam simplesmente cortados, inacessíveis, sem como rolar até eles.
        container_lista = ttk.Frame(master)
        container_lista.pack(fill="both", expand=True, padx=10, pady=8)
        canvas_lista = tk.Canvas(container_lista, borderwidth=0, highlightthickness=0)
        barra_rolagem_lista = ttk.Scrollbar(container_lista, orient="vertical", command=canvas_lista.yview)
        canvas_lista.configure(yscrollcommand=barra_rolagem_lista.set)
        canvas_lista.pack(side="left", fill="both", expand=True)
        barra_rolagem_lista.pack(side="right", fill="y")

        def _ao_rolar_mouse_catalogo(evento):
            canvas_lista.yview_scroll(int(-1 * (evento.delta / 120)), "units")

        canvas_lista.bind("<Enter>", lambda _e: canvas_lista.bind_all("<MouseWheel>", _ao_rolar_mouse_catalogo))
        canvas_lista.bind("<Leave>", lambda _e: canvas_lista.unbind_all("<MouseWheel>"))

        lista_frame = ttk.Frame(canvas_lista)
        janela_lista_frame = canvas_lista.create_window((0, 0), window=lista_frame, anchor="nw")
        lista_frame.bind("<Configure>", lambda _e: canvas_lista.configure(scrollregion=canvas_lista.bbox("all")))
        canvas_lista.bind("<Configure>", lambda evento: canvas_lista.itemconfig(janela_lista_frame, width=evento.width))

        lista_frame.columnconfigure(0, weight=1, uniform="categoria")
        lista_frame.columnconfigure(1, weight=1, uniform="categoria")

        # O estado de cada relatório é o próprio estado ttk do Checkbutton
        # ("selected"/"!selected"), sem tk.BooleanVar/trace — usar variável
        # ligada se mostrou pouco confiável (o clique às vezes não disparava
        # a escrita na variável). command= nunca falhou nos testes.
        self.checkboxes_catalogo = {}
        self._campos_condicionais_catalogo = []
        grupos_por_apos = {grupo["apos"]: grupo for grupo in GRUPOS_PARAMETROS_RELATORIO}
        for i, (categoria, itens) in enumerate(CATALOGO_RELATORIOS):
            grupo = ttk.LabelFrame(lista_frame, text=categoria)
            grupo.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            linha = 0
            for chave, titulo in itens:
                caixa = ttk.Checkbutton(grupo, text=titulo, command=self._ao_alterar_catalogo)
                caixa.state(["selected", "!alternate"])
                caixa.grid(row=linha, column=0, sticky="w", padx=10, pady=4)
                self.checkboxes_catalogo[chave] = caixa
                linha += 1

                grupo_parametros = grupos_por_apos.get(chave)
                if grupo_parametros is not None:
                    linha = self._montar_campos_condicionais_catalogo(grupo, linha, grupo_parametros)
        self._atualizar_contagem_catalogo()
        self._atualizar_estado_campos_condicionais_catalogo()

    # ------------------------------------------------------------------
    # Visualizar Relatório: navega os DataFrames da última geração sem
    # precisar exportar pra Excel/PDF/Word e abrir o arquivo à parte.
    # ------------------------------------------------------------------

    def _montar_aba_visualizar(self, master):
        ttk.Label(
            master, text="Visualize aqui os relatórios da última geração (Relatório Padrão) — sem precisar exportar.",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=10, pady=(10, 0))

        barra = ttk.Frame(master)
        barra.pack(fill="x", padx=10, pady=8)

        ttk.Label(barra, text="Granularidade:").pack(side="left")
        self.combo_visualizar_granularidade = ttk.Combobox(barra, state="readonly", width=12, values=[])
        self.combo_visualizar_granularidade.pack(side="left", padx=(4, 12))
        self.combo_visualizar_granularidade.bind(
            "<<ComboboxSelected>>", lambda _evento: self._popular_combo_visualizar_categoria()
        )

        ttk.Label(barra, text="Categoria:").pack(side="left")
        self.combo_visualizar_categoria = ttk.Combobox(barra, state="readonly", width=18, values=[])
        self.combo_visualizar_categoria.pack(side="left", padx=(4, 12))
        self.combo_visualizar_categoria.bind(
            "<<ComboboxSelected>>", lambda _evento: self._popular_combo_visualizar_relatorio()
        )

        ttk.Label(barra, text="Relatório:").pack(side="left")
        self.combo_visualizar_relatorio = ttk.Combobox(barra, state="readonly", width=48, values=[])
        self.combo_visualizar_relatorio.pack(side="left", padx=4)
        self.combo_visualizar_relatorio.bind("<<ComboboxSelected>>", lambda _evento: self._exibir_tabela_visualizar())

        self.label_visualizar_contagem = ttk.Label(barra, text="Nenhum relatório gerado ainda.", foreground="gray")
        self.label_visualizar_contagem.pack(side="right")

        container = ttk.Frame(master)
        container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        self.arvore_visualizar = ttk.Treeview(container, show="headings")
        barra_v = ttk.Scrollbar(container, orient="vertical", command=self.arvore_visualizar.yview)
        barra_h = ttk.Scrollbar(container, orient="horizontal", command=self.arvore_visualizar.xview)
        self.arvore_visualizar.configure(yscrollcommand=barra_v.set, xscrollcommand=barra_h.set)
        self.arvore_visualizar.grid(row=0, column=0, sticky="nsew")
        barra_v.grid(row=0, column=1, sticky="ns")
        barra_h.grid(row=1, column=0, sticky="ew")

    # Sub-produtos automáticos (gerados junto de migracao_abc, sem checkbox
    # próprio no catálogo — ver gerar_analises_completas) não aparecem em
    # CATALOGO_RELATORIOS; herdam a categoria de quem os gera.
    CATEGORIA_EXTRA_POR_CHAVE = {
        "migracao_resumo": "Relatórios Gerais",
        "migracao_score_clientes": "Relatórios Gerais",
    }

    def _rotulo_amigavel_relatorio(self, chave):
        return ROTULOS_RELATORIO_PDF_WORD.get(chave, NOMES_ANALISE.get(chave, chave))

    def _categoria_do_relatorio(self, chave):
        for categoria, itens in CATALOGO_RELATORIOS:
            if any(chave_item == chave for chave_item, _titulo in itens):
                return categoria
        return self.CATEGORIA_EXTRA_POR_CHAVE.get(chave, "Outros")

    def _popular_visualizador_relatorio(self):
        """Chamado sempre que self.resultados_analise muda (nova geração concluída) -- repopula os combos."""
        if not self.resultados_analise:
            return
        granularidades = list(self.resultados_analise.keys())
        self.combo_visualizar_granularidade["values"] = granularidades
        if self.combo_visualizar_granularidade.get() not in granularidades:
            self.combo_visualizar_granularidade.set(granularidades[0])
        self._popular_combo_visualizar_categoria()

    def _popular_combo_visualizar_categoria(self):
        granularidade = self.combo_visualizar_granularidade.get()
        analises = self.resultados_analise.get(granularidade, {}) if self.resultados_analise else {}
        categorias_presentes = []
        for chave in analises.keys():
            categoria = self._categoria_do_relatorio(chave)
            if categoria not in categorias_presentes:
                categorias_presentes.append(categoria)
        # Sempre na mesma ordem do catálogo (Gerais antes de Gerenciais),
        # não a ordem de inserção do dict de resultados.
        ordem_catalogo = [categoria for categoria, _itens in CATALOGO_RELATORIOS]
        categorias = [c for c in ordem_catalogo if c in categorias_presentes]
        categorias += [c for c in categorias_presentes if c not in categorias]

        self.combo_visualizar_categoria["values"] = categorias
        if categorias and self.combo_visualizar_categoria.get() not in categorias:
            self.combo_visualizar_categoria.set(categorias[0])
        self._popular_combo_visualizar_relatorio()

    def _popular_combo_visualizar_relatorio(self):
        granularidade = self.combo_visualizar_granularidade.get()
        categoria = self.combo_visualizar_categoria.get()
        analises = self.resultados_analise.get(granularidade, {}) if self.resultados_analise else {}
        chaves = [chave for chave in analises.keys() if self._categoria_do_relatorio(chave) == categoria]
        rotulos = [self._rotulo_amigavel_relatorio(chave) for chave in chaves]
        self._mapa_visualizar_rotulo_para_chave = dict(zip(rotulos, chaves))
        self.combo_visualizar_relatorio["values"] = rotulos
        if rotulos and self.combo_visualizar_relatorio.get() not in rotulos:
            self.combo_visualizar_relatorio.set(rotulos[0])
        elif not rotulos:
            self.combo_visualizar_relatorio.set("")
        self._exibir_tabela_visualizar()

    def _formatar_celula_visualizar(self, nome_coluna, valor, eh_moeda):
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            return ""
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            if eh_moeda:
                return _formatar_moeda_br(valor)
            if any(marcador in nome_coluna for marcador in ("%", "Percentual", "Pct")):
                return f"{valor:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")
            if isinstance(valor, float) and not float(valor).is_integer():
                return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"{int(valor):,}".replace(",", ".")
        return str(valor)

    # Linhas exibidas de uma vez na Treeview — tabelas de centenas de milhares
    # de linhas (ex.: ABC sem corte) travariam a interface tentando desenhar
    # tudo; quem precisa da base completa já tem Excel/Relatórios Personalizados.
    LIMITE_LINHAS_VISUALIZAR = 500

    def _exibir_tabela_visualizar(self):
        arvore = self.arvore_visualizar
        arvore.delete(*arvore.get_children())
        arvore["columns"] = ()

        rotulo = self.combo_visualizar_relatorio.get()
        chave = getattr(self, "_mapa_visualizar_rotulo_para_chave", {}).get(rotulo)
        granularidade = self.combo_visualizar_granularidade.get()
        if not chave or not self.resultados_analise:
            self.label_visualizar_contagem.config(text="Nenhum relatório gerado ainda.")
            return

        df = self.resultados_analise.get(granularidade, {}).get(chave)
        if df is None or df.empty:
            self.label_visualizar_contagem.config(text="0 linhas.")
            return

        colunas_moeda = set(COLUNAS_MOEDA_POR_ANALISE.get(chave, []))
        colunas = list(df.columns)
        arvore["columns"] = colunas
        for coluna in colunas:
            arvore.heading(coluna, text=coluna)
            arvore.column(coluna, width=max(90, min(220, 10 * len(coluna))), anchor="w")

        for _, linha in df.head(self.LIMITE_LINHAS_VISUALIZAR).iterrows():
            valores = [
                self._formatar_celula_visualizar(coluna, linha[coluna], coluna in colunas_moeda)
                for coluna in colunas
            ]
            arvore.insert("", "end", values=valores)

        texto_contagem = f"{len(df)} linha(s)."
        if len(df) > self.LIMITE_LINHAS_VISUALIZAR:
            texto_contagem += f" Mostrando as {self.LIMITE_LINHAS_VISUALIZAR} primeiras — use Excel para a base completa."
        self.label_visualizar_contagem.config(text=texto_contagem)

    def _marcar_catalogo(self, valor):
        for caixa in self.checkboxes_catalogo.values():
            caixa.state(["selected", "!alternate"] if valor else ["!selected", "!alternate"])
        self._atualizar_contagem_catalogo()
        self._atualizar_estado_campos_condicionais_catalogo()

    def _montar_campos_condicionais_catalogo(self, master, linha, grupo_parametros):
        """Sub-bloco indentado com os campos de um grupo (ver GRUPOS_PARAMETROS_RELATORIO), logo abaixo do checkbox "apos"."""
        sub = ttk.Frame(master)
        sub.grid(row=linha, column=0, sticky="w", padx=(28, 6), pady=(0, 6))
        for i, (nome_atributo, rotulo, valor_padrao, largura) in enumerate(grupo_parametros["campos"]):
            ttk.Label(sub, text=rotulo).grid(row=i, column=0, sticky="w", pady=2)
            entrada = ttk.Entry(sub, width=largura)
            if valor_padrao:
                entrada.insert(0, valor_padrao)
            entrada.grid(row=i, column=1, sticky="w", padx=(6, 0), pady=2)
            setattr(self, nome_atributo, entrada)
        if grupo_parametros.get("legenda"):
            ttk.Label(
                sub, text=grupo_parametros["legenda"], foreground="gray", font=("Segoe UI", 8),
            ).grid(row=len(grupo_parametros["campos"]), column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._campos_condicionais_catalogo.append(grupo_parametros)
        return linha + 1

    def _ao_alterar_catalogo(self):
        self._atualizar_contagem_catalogo()
        self._atualizar_estado_campos_condicionais_catalogo()

    def _atualizar_estado_campos_condicionais_catalogo(self):
        """Habilita/desabilita cada grupo de campos conforme algum dos relatórios-gatilho está marcado."""
        for grupo_parametros in self._campos_condicionais_catalogo:
            ligado = any(
                self.checkboxes_catalogo[chave].instate(["selected"]) for chave in grupo_parametros["gatilhos"]
            )
            estado = "normal" if ligado else "disabled"
            for nome_atributo, *_ in grupo_parametros["campos"]:
                getattr(self, nome_atributo).config(state=estado)

    def _chaves_catalogo_selecionadas(self):
        return [chave for chave, caixa in self.checkboxes_catalogo.items() if caixa.instate(["selected"])]

    def _atualizar_contagem_catalogo(self):
        total = len(self.checkboxes_catalogo)
        selecionados = len(self._chaves_catalogo_selecionadas())
        self.label_contagem_catalogo.config(text=f"{selecionados} de {total} relatórios selecionados")

    # ------------------------------------------------------------------
    # Geração do relatório padrão (roda em thread para não travar a UI)
    # ------------------------------------------------------------------

    def _gerar_relatorio_padrao(self):
        if self.thread_em_execucao:
            messagebox.showinfo("Relatório", "Já existe um processamento em andamento.")
            return
        if self.df is None:
            messagebox.showwarning("Relatório", "Nenhuma base carregada. Vá em Configurações e selecione um CSV.")
            return

        chaves_selecionadas = self._chaves_catalogo_selecionadas()
        if not chaves_selecionadas:
            messagebox.showwarning("Relatório", "Selecione ao menos um relatório do catálogo.")
            return

        granularidades = [self.var_granularidade.get()]

        try:
            corte_produtos = float(self.entrada_corte_produtos.get().replace(",", "."))
            cortes_grupos = self._ler_cortes_grupos()
            periodos_queda = int(self.entrada_periodos_queda.get())
            texto_top_n = self.entrada_top_n_produtos.get().strip()
            top_n_produtos = int(texto_top_n) if texto_top_n else None
            reducao_minima_erosao = float(self.entrada_reducao_minima_erosao.get().replace(",", "."))
            queda_minima_alerta = float(self.entrada_queda_minima_alerta.get().replace(",", "."))
            queda_minima_erosao = float(self.entrada_queda_minima_erosao.get().replace(",", "."))
            reducao_minima_sem_venda = float(self.entrada_reducao_minima_sem_venda.get().replace(",", "."))
            texto_top_n_poder_compra = self.entrada_top_n_poder_compra.get().strip()
            top_n_poder_compra = int(texto_top_n_poder_compra) if texto_top_n_poder_compra else None
        except ValueError:
            messagebox.showerror("Parâmetros inválidos", "Verifique os campos numéricos em Configurações.")
            return

        if not (0 < corte_produtos < 100):
            messagebox.showerror("Parâmetros inválidos", "O corte de produtos deve estar entre 0 e 100.")
            return
        if any(cortes_grupos[i] >= cortes_grupos[i + 1] for i in range(len(cortes_grupos) - 1)) or \
           any(c <= 0 or c >= 100 for c in cortes_grupos):
            messagebox.showerror("Parâmetros inválidos", "Os cortes de grupo devem ser crescentes e estar entre 0 e 100.")
            return
        if top_n_produtos is not None and top_n_produtos <= 0:
            messagebox.showerror("Parâmetros inválidos", "Produtos a exibir deve ser um número positivo (ou em branco).")
            return
        if not (0 <= reducao_minima_erosao <= 100):
            messagebox.showerror("Parâmetros inválidos", "Redução mínima para erosão deve estar entre 0 e 100.")
            return
        if queda_minima_alerta < 0:
            messagebox.showerror("Parâmetros inválidos", "Queda mínima em R$ para alerta deve ser zero ou positiva.")
            return
        if queda_minima_erosao < 0:
            messagebox.showerror("Parâmetros inválidos", "Queda mínima em R$ para erosão deve ser zero ou positiva.")
            return
        if not (0 <= reducao_minima_sem_venda <= 100):
            messagebox.showerror("Parâmetros inválidos", "Redução mínima para Sem Venda deve estar entre 0 e 100.")
            return
        if top_n_poder_compra is not None and top_n_poder_compra <= 0:
            messagebox.showerror("Parâmetros inválidos", "Máximo de clientes a exibir (Poder de Compra) deve ser um número positivo (ou em branco).")
            return

        df_filtrado = self._dataframe_para_analise()
        if df_filtrado.empty:
            messagebox.showerror("Relatório", "Nenhuma linha restante após o filtro de lojas/produtos. Verifique se ao menos uma loja está marcada em Configurações.")
            return

        clientes_excluidos = self._clientes_excluidos()
        self.granularidade_referencia = granularidades[0]
        self._chaves_selecionadas_geracao = chaves_selecionadas
        self._formato_geracao = self.var_formato_exportacao.get()
        self._nome_empresa_geracao = self.entrada_nome_empresa.get().strip()
        # Guardado pra reconstruir as descrições dinâmicas na hora de exportar
        # (ver _construir_descricoes_dinamicas) — sem isso, a descrição de
        # Erosão/Alertas de Queda exportada sempre dizia os valores padrão
        # (ex.: "caiu 50%+"), mesmo quando o usuário configurava outro valor.
        self._parametros_geracao = {
            "reducao_minima_erosao": reducao_minima_erosao,
            "queda_minima_erosao": queda_minima_erosao,
            "queda_minima_alerta": queda_minima_alerta,
            "periodos_queda": periodos_queda,
            "reducao_minima_sem_venda": reducao_minima_sem_venda,
        }

        self.thread_em_execucao = True
        self.botao_gerar.config(state="disabled")
        self.progress.start(10)
        self._registrar_log(
            f"Iniciando geração do relatório. Granularidades: {granularidades}. "
            f"Relatórios selecionados: {len(chaves_selecionadas)}. "
            f"Clientes excluídos: {len(clientes_excluidos)}. Produtos excluídos: {len(self._produtos_excluidos())}. "
            f"Lojas incluídas: {len(self._lojas_selecionadas())}/{len(self.vars_lojas)}."
        )
        self._definir_status("Processando análises em segundo plano...")

        self._thread_geracao = threading.Thread(
            target=self._executar_geracao_em_thread,
            args=(df_filtrado, granularidades, clientes_excluidos, tuple(cortes_grupos), corte_produtos,
                  periodos_queda, set(chaves_selecionadas), self.check_balcao.instate(["selected"]),
                  not self.check_incluir_periodo_atual.instate(["selected"]), top_n_produtos, reducao_minima_erosao,
                  queda_minima_alerta, queda_minima_erosao, reducao_minima_sem_venda, top_n_poder_compra),
            daemon=True,
        )
        self._thread_geracao.start()

    def _executar_geracao_em_thread(self, df_filtrado, granularidades, clientes_excluidos,
                                     cortes_grupos, corte_produtos, periodos_queda, chaves_selecionadas, desconsiderar_balcao,
                                     excluir_periodo_atual, top_n_produtos, reducao_minima_erosao, queda_minima_alerta,
                                     queda_minima_erosao, reducao_minima_sem_venda, top_n_poder_compra):
        try:
            resultados = af.gerar_analises_completas(
                df_filtrado, granularidades,
                clientes_excluidos=clientes_excluidos,
                cortes_clientes=cortes_grupos,
                corte_produtos=corte_produtos,
                periodos_queda_consecutiva=periodos_queda,
                chaves_solicitadas=chaves_selecionadas,
                callback_log=lambda mensagem: self._registrar_log(mensagem),
                desconsiderar_balcao=desconsiderar_balcao,
                excluir_periodo_atual=excluir_periodo_atual,
                top_n_produtos=top_n_produtos,
                reducao_minima_erosao=reducao_minima_erosao,
                queda_minima_alerta=queda_minima_alerta,
                queda_minima_erosao_reais=queda_minima_erosao,
                reducao_minima_sem_venda=reducao_minima_sem_venda,
                top_n_poder_compra=top_n_poder_compra,
            )
            self.fila_eventos.put(("concluido", resultados))
        except Exception as exc:
            self.logger.exception("Falha ao processar análises")
            self.fila_eventos.put(("erro", str(exc)))

    def _ao_concluir_geracao(self, resultados):
        self.progress.stop()
        self.botao_gerar.config(state="normal")
        self.thread_em_execucao = False
        self.resultados_analise = resultados
        self._popular_visualizador_relatorio()
        self._registrar_log("Análises concluídas com sucesso.")

        formato = self._formato_geracao
        opcoes_formato = {
            "Excel": (".xlsx", [("Excel", "*.xlsx")]),
            "PDF": (".pdf", [("PDF", "*.pdf")]),
            "Word": (".docx", [("Word", "*.docx")]),
        }
        extensao, tipos_arquivo = opcoes_formato[formato]

        nome_empresa = self._nome_empresa_geracao
        nome_empresa_arquivo = re.sub(r'[\\/*?:"<>|]', "", nome_empresa).strip()
        prefixo = f"Relatorio_{nome_empresa_arquivo}" if nome_empresa_arquivo else "Relatorio"
        nome_sugerido = f"{prefixo}_{datetime.now().strftime('%Y-%m')}"

        self._definir_status(f"Análises concluídas. Escolha onde salvar o {formato}.")
        caminho_saida = filedialog.asksaveasfilename(
            parent=self, defaultextension=extensao, filetypes=tipos_arquivo, initialfile=nome_sugerido
        )
        if not caminho_saida:
            self._registrar_log("Exportação cancelada pelo usuário.")
            self._definir_status("Relatório calculado, mas não exportado (cancelado pelo usuário).")
            return

        # gerar_analises_completas já só calcula/retorna as chaves pedidas
        # (ver chaves_solicitadas em _gerar_relatorio_padrao), então resultados
        # aqui já vem filtrado — nada a recortar de novo.
        resultados_filtrados = resultados

        descricoes_geracao = _construir_descricoes_dinamicas(getattr(self, "_parametros_geracao", {}))

        # "sem_venda" tem uma coluna de receita por mês (nomes dinâmicos,
        # ex. "ago/25") — não dá pra listar em COLUNAS_MOEDA_POR_ANALISE de
        # antemão. Resolve aqui, uma vez, a partir do próprio resultado desta
        # geração (qualquer granularidade serve, as colunas são as mesmas).
        colunas_moeda_geracao = dict(COLUNAS_MOEDA_POR_ANALISE)
        for analises in resultados_filtrados.values():
            df_sem_venda = analises.get("sem_venda")
            if df_sem_venda is not None and not df_sem_venda.empty:
                colunas_moeda_geracao["sem_venda"] = _colunas_moeda_efetivas("sem_venda", df_sem_venda)
                break

        self._definir_status(f"Exportando {formato}...")
        self._registrar_log(f"Exportando {formato} para: {caminho_saida}")
        try:
            if formato == "Excel":
                import exportador_excel
                exportador_excel.exportar_relatorio_excel(
                    caminho_saida, resultados_filtrados, self.relatorios_personalizados,
                    nome_usuario=self.perfil.get("nome", ""), nome_empresa=nome_empresa,
                    descricao_analise=descricoes_geracao,
                )
            elif formato == "PDF":
                import exportadores_pdf_word
                exportadores_pdf_word.exportar_relatorio_pdf(
                    caminho_saida, resultados_filtrados, ROTULOS_RELATORIO_PDF_WORD, nome_usuario=self.perfil.get("nome", ""),
                    colunas_moeda_por_analise=colunas_moeda_geracao, nome_empresa=nome_empresa,
                    descricao_analise=descricoes_geracao,
                )
            else:
                import exportadores_pdf_word
                exportadores_pdf_word.exportar_relatorio_word(
                    caminho_saida, resultados_filtrados, ROTULOS_RELATORIO_PDF_WORD, nome_usuario=self.perfil.get("nome", ""),
                    colunas_moeda_por_analise=colunas_moeda_geracao, nome_empresa=nome_empresa,
                    descricao_analise=descricoes_geracao,
                )
        except Exception as exc:
            self.logger.exception(f"Falha ao exportar {formato}")
            messagebox.showerror(f"Erro ao exportar {formato}", str(exc))
            self._registrar_log(f"Falha ao exportar {formato}: {exc}", nivel="error")
            self._definir_status(f"Falha ao exportar {formato}.")
            return

        self._registrar_log("Relatório exportado com sucesso.")
        self._definir_status("Relatório gerado com sucesso.")
        messagebox.showinfo("Relatório", f"Relatório exportado com sucesso em:\n{caminho_saida}")

    def _ao_falhar_geracao(self, mensagem_erro):
        self.progress.stop()
        self.botao_gerar.config(state="normal")
        self.thread_em_execucao = False
        self._registrar_log(f"Falha ao processar análises: {mensagem_erro}", nivel="error")
        self._definir_status("Falha ao processar análises.")
        messagebox.showerror("Erro ao processar análises", mensagem_erro)

    # ------------------------------------------------------------------
    # Aba "Perfil": nome e preferências salvas localmente (SQLite)
    # ------------------------------------------------------------------

    def _montar_aba_perfil(self, master):
        frame = ttk.Frame(master)
        frame.pack(anchor="nw", padx=20, pady=20)

        ttk.Label(frame, text="Perfil do usuário", font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )

        ttk.Label(frame, text="Seu nome:").grid(row=1, column=0, sticky="w", pady=4)
        self.entrada_nome_perfil = ttk.Entry(frame, width=32)
        self.entrada_nome_perfil.insert(0, self.perfil.get("nome", ""))
        self.entrada_nome_perfil.grid(row=1, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(frame, text="Tamanho da fonte:").grid(row=2, column=0, sticky="w", pady=4)
        self.spin_tamanho_fonte = ttk.Spinbox(frame, from_=7, to=20, width=6)
        self.spin_tamanho_fonte.set(self.perfil.get("tamanho_fonte", perfil.TAMANHO_FONTE_PADRAO))
        self.spin_tamanho_fonte.grid(row=2, column=1, sticky="w", padx=8, pady=4)

        ttk.Button(frame, text="Salvar perfil", command=self._salvar_perfil).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(14, 4)
        )

        ttk.Label(
            frame,
            text="Estas preferências ficam salvas localmente (dados_locais/perfil.db), ao lado\n"
                 "do programa nesta máquina — não são incluídas se o executável for compartilhado.",
            foreground="gray", justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _salvar_perfil(self):
        nome = self.entrada_nome_perfil.get().strip()
        try:
            tamanho_fonte = int(self.spin_tamanho_fonte.get())
        except ValueError:
            messagebox.showerror("Perfil", "Tamanho de fonte inválido.")
            return

        perfil.salvar_perfil(nome, tamanho_fonte)
        self.perfil = {"nome": nome, "tamanho_fonte": tamanho_fonte}
        self.tamanho_fonte_base = tamanho_fonte
        self._aplicar_zoom(None)
        self._atualizar_boas_vindas()
        self._registrar_log(f"Perfil salvo: nome='{nome}', tamanho_fonte={tamanho_fonte}.")
        messagebox.showinfo("Perfil", "Perfil salvo com sucesso.")


if __name__ == "__main__":
    import time
    import splash

    _declarar_dpi_aware()

    _pedir_permissao_primeira_execucao()

    servidor_instancia = _tentar_registrar_instancia_unica()
    if servidor_instancia is None:
        escolha = _perguntar_instancia_ja_aberta()
        if escolha == "prosseguir":
            _enviar_comando_instancia_existente("ATIVAR")
            sys.exit(0)
        elif escolha == "fechar":
            _enviar_comando_instancia_existente("FECHAR")
            # A instância antiga leva um instante pra soltar a porta depois
            # de receber o comando — sem essa espera/novas tentativas, essa
            # instância nova desistiria cedo demais e cairia no erro abaixo
            # por pura diferença de tempo, não por falha real.
            for _ in range(20):
                time.sleep(0.3)
                servidor_instancia = _tentar_registrar_instancia_unica()
                if servidor_instancia is not None:
                    break
            if servidor_instancia is None:
                raiz_erro = tk.Tk()
                raiz_erro.withdraw()
                messagebox.showerror(
                    NOME_SISTEMA,
                    "Não foi possível fechar a instância aberta automaticamente.\n"
                    "Feche-a manualmente pela barra de tarefas e abra o programa de novo.",
                )
                raiz_erro.destroy()
                sys.exit(1)
        else:
            sys.exit(0)

    splash.exibir_splash_e_iniciar(
        etapas_preparacao=construir_etapas_preparacao(),
        funcao_construir_janela_principal=lambda: AplicacaoAnaliseFunil(servidor_instancia_unica=servidor_instancia),
    )
