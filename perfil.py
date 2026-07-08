"""
Perfil local do usuário (nome, tamanho de fonte preferido), persistido em um
banco SQLite dentro da pasta dados_locais/, ao lado do executável.

Fica de propósito FORA do executável: se o .exe for compartilhado com outra
pessoa, cada instalação cria o próprio arquivo de perfil na primeira vez que
rodar — os dados nunca "vazam" de uma máquina para outra dentro do .exe.
"""

import sqlite3

from recursos import caminho_dados_locais

TAMANHO_FONTE_PADRAO = 9


def _conexao():
    caminho_banco = caminho_dados_locais("perfil.db")
    conexao = sqlite3.connect(caminho_banco)
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS perfil (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nome TEXT NOT NULL DEFAULT '',
            tamanho_fonte INTEGER NOT NULL DEFAULT %d,
            ultima_versao_vista TEXT
        )
        """ % TAMANHO_FONTE_PADRAO
    )
    # Migração pra quem já tinha o banco antes desta coluna existir —
    # CREATE TABLE IF NOT EXISTS não adiciona coluna em tabela já criada.
    try:
        conexao.execute("ALTER TABLE perfil ADD COLUMN ultima_versao_vista TEXT")
    except sqlite3.OperationalError:
        pass  # coluna já existe
    conexao.commit()
    return conexao


def carregar_perfil():
    """Retorna {'nome': str, 'tamanho_fonte': int}. Se não existir, retorna os padrões."""
    with _conexao() as conexao:
        linha = conexao.execute("SELECT nome, tamanho_fonte FROM perfil WHERE id = 1").fetchone()
    if linha is None:
        return {"nome": "", "tamanho_fonte": TAMANHO_FONTE_PADRAO}
    nome, tamanho_fonte = linha
    return {"nome": nome or "", "tamanho_fonte": tamanho_fonte or TAMANHO_FONTE_PADRAO}


def salvar_perfil(nome, tamanho_fonte):
    with _conexao() as conexao:
        conexao.execute(
            """
            INSERT INTO perfil (id, nome, tamanho_fonte) VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET nome = excluded.nome, tamanho_fonte = excluded.tamanho_fonte
            """,
            (nome, tamanho_fonte),
        )
        conexao.commit()


def obter_ultima_versao_vista():
    """Última versão para a qual a tela de novidades já foi exibida nesta instalação, ou None."""
    with _conexao() as conexao:
        linha = conexao.execute("SELECT ultima_versao_vista FROM perfil WHERE id = 1").fetchone()
    return linha[0] if linha and linha[0] else None


def definir_ultima_versao_vista(versao):
    with _conexao() as conexao:
        conexao.execute(
            """
            INSERT INTO perfil (id, ultima_versao_vista) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET ultima_versao_vista = excluded.ultima_versao_vista
            """,
            (versao,),
        )
        conexao.commit()
