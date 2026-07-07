"""
Verificação de novas versões do sistema publicadas como Release no GitHub.

Consulta a API pública do GitHub por HTTPS (sem autenticação, sem
dependências externas — usa só a biblioteca padrão) e compara a tag da
release mais recente com a versão embutida no executável (VERSAO_ATUAL em
recursos.py).

Diferente de antes, aqui as falhas de rede/API NÃO são engolidas: quem
chamar essa função decide o que fazer com o erro (a checagem automática no
startup loga e ignora; a checagem manual, pelo menu, mostra o erro pro
usuário — sem isso não havia como diagnosticar por que a checagem "não
funcionava" numa rede com bloqueio/proxy, por exemplo).
"""

import json
import re
import urllib.error
import urllib.request

from recursos import REPOSITORIO_GITHUB, VERSAO_ATUAL

TIMEOUT_SEGUNDOS = 4


def _versao_para_tupla(versao):
    numeros = re.findall(r"\d+", versao)
    return tuple(int(n) for n in numeros) if numeros else (0,)


def verificar_nova_versao():
    """
    Consulta a release mais recente do repositório no GitHub.

    Retorna (tag, url_download) se ela for mais nova que VERSAO_ATUAL, ou
    None se a versão atual já é a mais recente (ou o repositório ainda não
    tem nenhuma release publicada). Levanta exceção em qualquer outra falha
    (sem internet, timeout, resposta inesperada da API).
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
    url_release = dados.get("html_url", url)
    if not tag:
        return None

    if _versao_para_tupla(tag) > _versao_para_tupla(VERSAO_ATUAL):
        return tag, url_release
    return None
