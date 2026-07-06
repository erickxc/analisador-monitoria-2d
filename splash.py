"""
Tela inicial (splash) exibida ao abrir o sistema: mostra a logo da 2D
Consultores com um indicador de carregamento enquanto uma sequência de
verificações reais é executada (bibliotecas, banco de dados local, arquivos
de sistema, limpeza de logs antigos) — cada etapa aparece na tela por um
instante perceptível, então o usuário vê o que está de fato acontecendo em
vez de uma barra genérica.
"""

import tkinter as tk
from tkinter import ttk

from recursos import CAMINHO_LOGO, NOME_SISTEMA, NOME_EMPRESA

COR_FUNDO = "#0d0d0d"
COR_TEXTO_SECUNDARIO = "#b5b5b5"
ATRASO_ENTRE_ETAPAS_MS = 450


def exibir_splash_e_iniciar(etapas_preparacao, funcao_construir_janela_principal):
    """
    Mostra a splash e executa, em sequência, cada (texto_status, funcao) de
    etapas_preparacao — atualizando o texto na tela antes de rodar a função
    e aguardando um instante antes da próxima, para que a verificação seja
    visível (não é só teatro: cada função faz uma checagem real). Ao final,
    troca para a janela principal construída por funcao_construir_janela_principal.
    """
    splash = tk.Tk()
    splash.overrideredirect(True)
    largura, altura = 480, 380
    x = (splash.winfo_screenwidth() - largura) // 2
    y = (splash.winfo_screenheight() - altura) // 2
    splash.geometry(f"{largura}x{altura}+{x}+{y}")
    splash.configure(bg=COR_FUNDO)

    try:
        logo_imagem = tk.PhotoImage(file=CAMINHO_LOGO)
        fator = max(1, logo_imagem.width() // 260)
        if fator > 1:
            logo_imagem = logo_imagem.subsample(fator, fator)
        tk.Label(splash, image=logo_imagem, bg=COR_FUNDO).pack(pady=(36, 12))
        splash._logo_imagem_ref = logo_imagem  # evita coleta de lixo da imagem
    except tk.TclError:
        pass

    tk.Label(splash, text=NOME_SISTEMA, font=("Segoe UI", 17, "bold"), fg="white", bg=COR_FUNDO).pack()
    tk.Label(splash, text=NOME_EMPRESA, font=("Segoe UI", 10), fg=COR_TEXTO_SECUNDARIO, bg=COR_FUNDO).pack(pady=(2, 20))

    barra_progresso = ttk.Progressbar(splash, mode="determinate", length=300, maximum=max(len(etapas_preparacao), 1))
    barra_progresso.pack(pady=(0, 10))

    label_status = tk.Label(splash, text="Iniciando...", font=("Segoe UI", 9), fg=COR_TEXTO_SECUNDARIO, bg=COR_FUNDO)
    label_status.pack()

    contexto = {}

    def proxima_etapa(indice=0):
        if indice >= len(etapas_preparacao):
            label_status.config(text="Motores de análise prontos. Aguardando arquivo de base de dados...")
            splash.update_idletasks()
            splash.after(500, etapa_finalizar)
            return

        texto, funcao = etapas_preparacao[indice]
        label_status.config(text=texto)
        barra_progresso["value"] = indice
        splash.update_idletasks()
        try:
            funcao()
        except Exception as exc:
            label_status.config(text=f"Aviso: {texto} falhou ({exc}). Continuando...")
            splash.update_idletasks()
        splash.after(ATRASO_ENTRE_ETAPAS_MS, lambda: proxima_etapa(indice + 1))

    def etapa_finalizar():
        barra_progresso["value"] = len(etapas_preparacao)
        contexto["janela_principal"] = funcao_construir_janela_principal()
        splash.quit()
        splash.destroy()

    splash.after(300, lambda: proxima_etapa(0))
    splash.mainloop()

    contexto["janela_principal"].mainloop()
