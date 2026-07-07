"""
Verificação de novas versões do sistema publicadas como Release no GitHub.

Consulta a API pública do GitHub por HTTPS (sem autenticação, sem
dependências externas — usa só a biblioteca padrão) e compara a tag da
release mais recente com a versão embutida no executável (VERSAO_ATUAL em
recursos.py). Qualquer falha (sem internet, repositório ainda sem
releases, limite de requisições da API) é silenciosa: a checagem é um
bônus e nunca pode impedir o uso normal do sistema.
"""

import json
import re
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
    None se não houver release mais nova (ou a checagem falhar).
    """
    url = f"https://api.github.com/repos/{REPOSITORIO_GITHUB}/releases/latest"
    requisicao = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_SEGUNDOS) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except Exception:
        return None

    tag = dados.get("tag_name", "")
    url_release = dados.get("html_url", url)
    if not tag:
        return None

    if _versao_para_tupla(tag) > _versao_para_tupla(VERSAO_ATUAL):
        return tag, url_release
    return None
