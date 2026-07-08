"""
Verificação e instalação de novas versões do sistema publicadas como
Release no GitHub.

Consulta a API pública do GitHub por HTTPS (sem autenticação, sem
dependências externas — usa só a biblioteca padrão) e compara a tag da
release mais recente com a versão embutida no executável (VERSAO_ATUAL em
recursos.py). Quando há versão nova E o programa está rodando como .exe
(frozen), baixa o executável novo e se substitui sozinho: como o Windows
não deixa sobrescrever um .exe em execução, a troca é feita por um script
.bat que espera este processo fechar, troca o arquivo e reabre o programa.

Diferente de antes, as falhas de rede/API NÃO são engolidas: quem chamar
verificar_nova_versao() decide o que fazer com o erro (a checagem
automática no startup loga e ignora; a checagem manual, pelo menu, mostra
o erro pro usuário — sem isso não havia como diagnosticar por que a
checagem "não funcionava" numa rede com bloqueio/proxy, por exemplo).
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from recursos import REPOSITORIO_GITHUB, VERSAO_ATUAL

TIMEOUT_SEGUNDOS = 4
TIMEOUT_DOWNLOAD_SEGUNDOS = 30
NOME_EXE_TEMPORARIO = "Monitor2D_novo.exe"


def _versao_para_tupla(versao):
    numeros = re.findall(r"\d+", versao)
    return tuple(int(n) for n in numeros) if numeros else (0,)


def verificar_nova_versao():
    """
    Consulta a release mais recente do repositório no GitHub.

    Retorna (tag, url_pagina, url_download_exe) se ela for mais nova que
    VERSAO_ATUAL, ou None se a versão atual já é a mais recente (ou o
    repositório ainda não tem nenhuma release publicada). url_download_exe
    é o link direto do primeiro asset ".exe" da release — usado para
    instalar automaticamente — e vem None se a release não tiver nenhum
    executável anexado. Levanta exceção em qualquer outra falha (sem
    internet, timeout, resposta inesperada da API).
    """
    url = f"https://api.github.com/repos/{REPOSITORIO_GITHUB}/releases/latest"
    requisicao = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_SEGUNDOS) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None  # repositório sem nenhuma release publicada ainda
        raise

    tag = dados.get("tag_name", "")
    if not tag or not (_versao_para_tupla(tag) > _versao_para_tupla(VERSAO_ATUAL)):
        return None

    url_pagina = dados.get("html_url", url)
    url_download_exe = next(
        (a.get("browser_download_url") for a in dados.get("assets", [])
         if a.get("name", "").lower().endswith(".exe")),
        None,
    )
    return tag, url_pagina, url_download_exe


def baixar_atualizacao(url_download_exe, callback_progresso=None):
    """
    Baixa o novo executável para um arquivo temporário e retorna o caminho.
    callback_progresso(percentual_int) é chamado periodicamente, se informado
    (percentual fica 0 se o servidor não informar o tamanho do arquivo).
    """
    destino = os.path.join(os.environ.get("TEMP", "."), NOME_EXE_TEMPORARIO)
    requisicao = urllib.request.Request(url_download_exe, headers={"User-Agent": "Monitor2D-updater"})
    with urllib.request.urlopen(requisicao, timeout=TIMEOUT_DOWNLOAD_SEGUNDOS) as resposta:
        total = int(resposta.headers.get("Content-Length", 0))
        baixado = 0
        with open(destino, "wb") as arquivo:
            while True:
                bloco = resposta.read(256 * 1024)
                if not bloco:
                    break
                arquivo.write(bloco)
                baixado += len(bloco)
                if callback_progresso:
                    callback_progresso(int(baixado * 100 / total) if total else 0)
    return destino


def aplicar_atualizacao_e_reiniciar(caminho_novo_exe):
    """
    Agenda a substituição do executável atual pelo baixado e finaliza o
    processo atual. A troca roda num script .bat separado (sobrevive ao
    fechamento deste processo) que tenta mover o arquivo novo por cima do
    atual a cada segundo — até o Windows liberar o arquivo, já que ele
    ainda está em uso enquanto este processo não terminar — e então reabre
    o programa. Só faz sentido rodando como .exe (frozen): em modo
    desenvolvimento não há um único arquivo pra substituir.

    Depois do move bem-sucedido, espera mais um instante antes de reabrir:
    sem essa folga, o antivírus (proteção em tempo real do Windows Defender,
    por exemplo) pode ainda estar varrendo o executável recém-escrito
    (não assinado) no exato momento do `start`, e o bootloader do
    PyInstaller falha com "Failed to load Python DLL" — visto na prática.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Instalação automática só é possível na versão empacotada (.exe), não em modo desenvolvimento.")

    caminho_atual = sys.executable
    caminho_bat = os.path.join(os.environ.get("TEMP", "."), "atualizar_analisador.bat")
    conteudo_bat = f"""@echo off
setlocal
set tentativas=0
:esperar
set /a tentativas+=1
ping -n 2 127.0.0.1 >nul
move /y "{caminho_novo_exe}" "{caminho_atual}" >nul 2>&1
if exist "{caminho_novo_exe}" (
    if %tentativas% lss 20 goto esperar
)
if not exist "{caminho_novo_exe}" (
    ping -n 4 127.0.0.1 >nul
    start "" "{caminho_atual}"
)
del "%~f0"
"""
    with open(caminho_bat, "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo_bat)

    subprocess.Popen(
        ["cmd", "/c", caminho_bat],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
