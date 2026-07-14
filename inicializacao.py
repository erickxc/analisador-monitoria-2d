"""
Sequência de inicialização do programa antes da janela principal existir:
logger, permissão de primeira execução, trava de instância única e DPI-
awareness. Nenhuma dessas funções depende de pandas/openpyxl/Tk já
construído — só stdlib + `recursos`/`perfil`, então importar este módulo no
topo de app.py não atrasa a splash (ver app.py, construir_etapas_preparacao).
"""

import ctypes
import logging
import os
import socket
import sys
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import perfil
import recursos
from recursos import CAMINHO_LOGO, NOME_SISTEMA, pasta_base_execucao


def _preparar_logger():
    pasta_logs = recursos.pasta_logs()
    nome_arquivo = f"analise_funil_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    caminho_log = os.path.join(pasta_logs, nome_arquivo)

    logger = logging.getLogger("analise_funil_app")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    manipulador = logging.FileHandler(caminho_log, encoding="utf-8")
    manipulador.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(manipulador)
    return logger, caminho_log


def _passo_verificar_banco_local():
    perfil.carregar_perfil()  # exercita criação/leitura real do banco SQLite local


def _passo_verificar_arquivos_sistema():
    if not os.path.exists(CAMINHO_LOGO):
        raise FileNotFoundError(f"logo não encontrada em {CAMINHO_LOGO}")


def _passo_limpar_logs_antigos(dias=30):
    pasta_logs = os.path.join(pasta_base_execucao(), "logs")
    if not os.path.isdir(pasta_logs):
        return
    limite = datetime.now().timestamp() - dias * 86400
    for nome_arquivo in os.listdir(pasta_logs):
        caminho = os.path.join(pasta_logs, nome_arquivo)
        try:
            if os.path.isfile(caminho) and os.path.getmtime(caminho) < limite:
                os.remove(caminho)
        except OSError:
            pass


def _pedir_permissao_primeira_execucao():
    """
    Na primeira vez que o programa roda nesta pasta (nem 'dados_locais' nem
    'logs' existem ainda ao lado do executável), pergunta ao usuário se pode
    criar essas pastas — perfil, configurações salvas e logs de execução.
    Se recusar, tudo isso vai para uma pasta temporária do Windows nesta
    sessão em vez de ficar ao lado do executável/script.
    """
    if recursos.pasta_dados_locais_ja_existe():
        return
    raiz_temporaria = tk.Tk()
    raiz_temporaria.withdraw()
    permitido = messagebox.askyesno(
        f"Primeira execução — {NOME_SISTEMA}",
        f"Esta é a primeira vez que o {NOME_SISTEMA} roda nesta pasta.\n\n"
        "Para funcionar, ele precisa criar, ao lado do programa:\n\n"
        "  •  uma pasta \"dados_locais\" — perfil do usuário e configurações salvas\n"
        "  •  uma pasta \"logs\" — registro de execução, para diagnóstico\n\n"
        "Nenhum dado sai desta máquina.\n\n"
        "Permitir a criação dessas pastas aqui?",
        icon="question",
    )
    raiz_temporaria.destroy()
    recursos.definir_permissao_dados_locais(permitido)


# Porta fixa, só localhost — dá bind nela funciona como trava de "instância
# única" (só um processo consegue reservar a mesma porta ao mesmo tempo) e
# dobra de canal de aviso pra outra instância (ver _enviar_comando_instancia_
# existente): mais simples que mutex nomeado via ctypes e não pede nenhuma
# biblioteca nova (pywin32, etc). Motivo de existir: com mais de uma janela
# do programa aberta, o arquivo do executável fica travado e a auto-
# atualização nunca consegue trocar o arquivo (reproduzido e confirmado —
# via logs, um Monitor2D_novo.exe baixado ficava órfão em %TEMP%, o script
# de troca esgotava as 90 tentativas e desistia, sempre, porque uma segunda
# janela ainda estava aberta e continuava travando o arquivo).
PORTA_INSTANCIA_UNICA = 51837


def _tentar_registrar_instancia_unica():
    """
    Socket TCP escutando em localhost, se essa for a primeira instância
    (bind bem-sucedido). None se a porta já está em uso por outra — ou
    seja, já tem uma instância do programa rodando.
    """
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        servidor.bind(("127.0.0.1", PORTA_INSTANCIA_UNICA))
    except OSError:
        servidor.close()
        return None
    servidor.listen(1)
    return servidor


def _enviar_comando_instancia_existente(comando, timeout=2):
    """Manda um comando curto ("ATIVAR"/"FECHAR") pra instância já aberta. True se entregou."""
    try:
        with socket.create_connection(("127.0.0.1", PORTA_INSTANCIA_UNICA), timeout=timeout) as cliente:
            cliente.sendall(comando.encode("utf-8"))
        return True
    except OSError:
        return False


def _perguntar_instancia_ja_aberta():
    """
    Diálogo mostrado ANTES da janela principal existir — outra instância do
    programa já está rodando, e o usuário decide o que fazer (mesmo padrão
    de raiz temporária de _pedir_permissao_primeira_execucao). Retorna
    "prosseguir", "fechar" ou "cancelar".
    """
    raiz_temporaria = tk.Tk()
    raiz_temporaria.withdraw()
    resultado = {"escolha": "cancelar"}

    janela = tk.Toplevel(raiz_temporaria)
    janela.title(NOME_SISTEMA)
    janela.resizable(False, False)
    janela.grab_set()

    tk.Label(
        janela, text=f"O {NOME_SISTEMA} já está aberto em outra janela.",
        font=("Segoe UI", 10, "bold"),
    ).pack(padx=24, pady=(22, 4))
    tk.Label(
        janela,
        text="Enquanto houver mais de uma instância aberta, a atualização automática\n"
             "não consegue trocar o arquivo do programa.",
        font=("Segoe UI", 9), fg="gray", justify="center",
    ).pack(padx=24, pady=(0, 18))

    def _escolher(valor):
        resultado["escolha"] = valor
        janela.destroy()

    linha_botoes = tk.Frame(janela)
    linha_botoes.pack(pady=(0, 22), padx=24)
    tk.Button(
        linha_botoes, text="Ir para a instância aberta", width=24, command=lambda: _escolher("prosseguir"),
    ).pack(side="left", padx=6)
    tk.Button(
        linha_botoes, text="Fechar a instância aberta", width=24, command=lambda: _escolher("fechar"),
    ).pack(side="left", padx=6)

    janela.protocol("WM_DELETE_WINDOW", lambda: _escolher("cancelar"))
    janela.update_idletasks()
    x = (janela.winfo_screenwidth() - janela.winfo_reqwidth()) // 2
    y = (janela.winfo_screenheight() - janela.winfo_reqheight()) // 2
    janela.geometry(f"+{x}+{y}")

    raiz_temporaria.wait_window(janela)
    raiz_temporaria.destroy()
    return resultado["escolha"]


def _declarar_dpi_aware():
    """
    Sem isso, o Windows não sabe que o programa lida com a escala de tela
    (DPI) sozinho e "finge" que a janela está em 100%, esticando o bitmap
    já renderizado (com ClearType) para a escala real (125%/150%/etc) —
    é isso que produz texto/botões com aparência fragmentada e franjas de
    cor. Precisa ser chamado ANTES de qualquer janela Tk ser criada.
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
