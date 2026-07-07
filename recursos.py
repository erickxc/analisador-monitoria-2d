"""
Resolução de caminhos usados em todo o sistema:

- recursos embutidos (logo) que funcionam tanto rodando `python app.py` em
  desenvolvimento quanto empacotado como .exe (PyInstaller extrai os dados
  para uma pasta temporária apontada por sys._MEIPASS);
- pasta de dados LOCAIS (perfil do usuário, logs) que fica ao lado do
  executável/script — cada instalação/cópia do .exe tem a sua própria,
  então compartilhar o executável com outra pessoa não compartilha o perfil.
"""

import os
import sys


def caminho_recurso(*partes_caminho):
    """Recurso embutido no pacote (ex.: assets/logo_2d.png). Somente leitura."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *partes_caminho)


def pasta_base_execucao():
    """Pasta onde o .exe (ou o script, em desenvolvimento) está rodando."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def caminho_dados_locais(*partes_caminho):
    """Arquivo de dados local (perfil, logs) — gravável, específico desta instalação."""
    pasta = os.path.join(pasta_base_execucao(), "dados_locais")
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, *partes_caminho)


NOME_SISTEMA = "Analisador Inteligente"
NOME_EMPRESA = "2D Consultores | Monitores"

# Versão embutida no executável — atualizada manualmente a cada release
# publicada no GitHub. Usada por atualizacoes.py para avisar o usuário
# quando existe uma versão mais nova disponível, e exibida na interface
# (título da janela, cabeçalho, "Sobre") para facilitar suporte.
VERSAO_ATUAL = "1.2.2"
REPOSITORIO_GITHUB = "erickxc/analisador-monitoria-2d"

TITULO_JANELA = f"{NOME_SISTEMA} v{VERSAO_ATUAL} - {NOME_EMPRESA}"

CAMINHO_LOGO = caminho_recurso("assets", "logo_2d.png")
CAMINHO_LOGO_ICO = caminho_recurso("assets", "logo_2d.ico")

# Só a marca (sem o texto "2D CONSULTORES"), quadrada — para usos pequenos
# (ícone da janela, logo inline no cabeçalho, logo por aba do Excel), onde
# o logo completo com texto fica ilegível/cortado ao ser reduzido.
CAMINHO_LOGO_ICONE = caminho_recurso("assets", "logo_2d_icone.png")
