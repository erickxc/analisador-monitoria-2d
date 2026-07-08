"""
Registro do que mudou em cada versão publicada — mostrado numa janela
pequena e direta na primeira vez que o usuário abre uma versão nova (ver
_mostrar_novidades_versao em app.py). Nunca aparece na primeira execução
de uma instalação nova (não há versão anterior pra comparar).

Ao publicar uma release, adicionar uma entrada aqui com bullets curtos e
executivos (o que mudou, não como foi implementado).
"""

NOVIDADES_POR_VERSAO = {
    "1.4.0": [
        "Relatórios por período agora ignoram, por padrão, o mês/período mais recente (geralmente incompleto).",
        "Evolução de Produtos: meses em formato legível (ago/25) e ordenados por tendência real de crescimento.",
        "Evolução de Produtos e Alertas de Queda: novo campo para limitar quantos produtos aparecem.",
        "Erosão de Clientes: compara só o período mais recente, com filtro de queda mínima (50% por padrão).",
        "ABC de Clientes: mostra os 5 principais clientes de cada grupo; corrige a classificação de clientes balcão.",
        "Poder de Compra: recalculado com base nos 3 melhores meses de cada cliente, não mais por período.",
        "Migração de Grupo: causas mais diretas, resumo de altas x quedas, e placar de pontuação por cliente.",
    ],
}
