"""
Exportação dos relatórios em PDF e Word, como alternativa ao Excel.

Diferença importante e proposital: PDF e Word são formatos de LEITURA (um
relatório para imprimir, assinar ou enviar por e-mail), não de manipulação de
dados. Por isso cada tabela é limitada a um número máximo de linhas — a base
completa, com milhares de linhas (ex.: segmentação ABC de 7 mil clientes),
só faz sentido consultar em Excel. O relatório em PDF/Word avisa quando uma
tabela foi cortada.
"""

import os
from datetime import datetime

from recursos import CAMINHO_LOGO, NOME_SISTEMA, NOME_EMPRESA

MAX_LINHAS_TABELA = 50


def _limitar(df):
    if df is None or df.empty:
        return df, 0
    total = len(df)
    if total > MAX_LINHAS_TABELA:
        return df.head(MAX_LINHAS_TABELA), total
    return df, total


def exportar_relatorio_pdf(caminho_saida, resultados_analise, nomes_analise, nome_usuario=""):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak

    estilos = getSampleStyleSheet()
    doc = SimpleDocTemplate(caminho_saida, pagesize=landscape(A4), topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    elementos = []

    if os.path.exists(CAMINHO_LOGO):
        elementos.append(Image(CAMINHO_LOGO, width=4 * cm, height=4 * cm * 306 / 572))
    elementos.append(Spacer(1, 12))
    elementos.append(Paragraph(NOME_SISTEMA, estilos["Title"]))
    elementos.append(Paragraph(NOME_EMPRESA, estilos["Normal"]))
    if nome_usuario:
        elementos.append(Paragraph(f"Gerado por: {nome_usuario}", estilos["Normal"]))
    elementos.append(Paragraph(f"Relatório gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}", estilos["Normal"]))
    elementos.append(PageBreak())

    for granularidade, analises in resultados_analise.items():
        for chave, df in analises.items():
            titulo = nomes_analise.get(chave, chave).replace("_", " ")
            elementos.append(Paragraph(f"{titulo} — {granularidade}", estilos["Heading2"]))
            if df is None or df.empty:
                elementos.append(Paragraph("Sem dados para esta análise/granularidade.", estilos["Normal"]))
            else:
                df_limitado, total = _limitar(df)
                dados_tabela = [list(map(str, df_limitado.columns))] + df_limitado.astype(str).values.tolist()
                tabela = Table(dados_tabela, repeatRows=1)
                tabela.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
                ]))
                elementos.append(tabela)
                if total > MAX_LINHAS_TABELA:
                    elementos.append(Spacer(1, 4))
                    elementos.append(Paragraph(
                        f"Mostrando {MAX_LINHAS_TABELA} de {total} registros — para a base completa, exporte em Excel.",
                        estilos["Italic"],
                    ))
            elementos.append(Spacer(1, 18))

    doc.build(elementos)


def exportar_relatorio_word(caminho_saida, resultados_analise, nomes_analise, nome_usuario=""):
    import docx
    from docx.shared import Cm

    documento = docx.Document()

    if os.path.exists(CAMINHO_LOGO):
        documento.add_picture(CAMINHO_LOGO, width=Cm(4))
    documento.add_heading(NOME_SISTEMA, level=0)
    documento.add_paragraph(NOME_EMPRESA)
    if nome_usuario:
        documento.add_paragraph(f"Gerado por: {nome_usuario}")
    documento.add_paragraph(f"Relatório gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}")
    documento.add_page_break()

    for granularidade, analises in resultados_analise.items():
        for chave, df in analises.items():
            titulo_analise = nomes_analise.get(chave, chave).replace("_", " ")
            documento.add_heading(f"{titulo_analise} — {granularidade}", level=2)
            if df is None or df.empty:
                documento.add_paragraph("Sem dados para esta análise/granularidade.")
                continue

            df_limitado, total = _limitar(df)
            tabela = documento.add_table(rows=1, cols=len(df_limitado.columns))
            try:
                tabela.style = "Light Grid Accent 1"
            except KeyError:
                pass
            celulas_cabecalho = tabela.rows[0].cells
            for i, coluna in enumerate(df_limitado.columns):
                celulas_cabecalho[i].text = str(coluna)
            for _, linha in df_limitado.iterrows():
                celulas = tabela.add_row().cells
                for i, valor in enumerate(linha):
                    celulas[i].text = str(valor)

            if total > MAX_LINHAS_TABELA:
                paragrafo = documento.add_paragraph(
                    f"Mostrando {MAX_LINHAS_TABELA} de {total} registros — para a base completa, exporte em Excel."
                )
                paragrafo.runs[0].italic = True

    documento.save(caminho_saida)
