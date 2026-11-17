---
habilidade: excel_avancado
arquivo: automacao_python_excel
tags: python, openpyxl, xlsxwriter, pandas, gerar planilha, automacao
idioma: pt-BR
---

# Automação de Excel com Python

## Qual biblioteca usar
- **pandas**: ler/transformar dados (`read_excel`, `to_excel`), análise rápida.
- **openpyxl**: ler e **editar** .xlsx existentes (fórmulas, estilos, validação, formatação condicional, gráficos).
- **XlsxWriter**: **criar** arquivos novos com formatação rica, gráficos e tabelas (não edita existentes).
- **xlwings**: controla o Excel aberto (Windows/Mac), roda Python a partir do Excel.
- Para recalcular fórmulas e converter: LibreOffice em modo headless.

## Gerar planilha profissional com XlsxWriter
```python
import pandas as pd

df = pd.DataFrame({
    "Produto": ["A", "B", "C"],
    "Qtd": [10, 20, 15],
    "Preço": [5.5, 3.2, 8.0],
})

with pd.ExcelWriter("relatorio.xlsx", engine="xlsxwriter") as writer:
    df.to_excel(writer, sheet_name="Dados", index=False, startrow=1, header=False)
    wb, ws = writer.book, writer.sheets["Dados"]

    cab = wb.add_format({"bold": True, "bg_color": "#1F3864",
                         "font_color": "white", "border": 1})
    moeda = wb.add_format({"num_format": "R$ #,##0.00"})

    # Tabela do Excel com estilo
    ws.add_table(0, 0, len(df), len(df.columns),
        {"columns": [{"header": c} for c in df.columns],
         "style": "Table Style Medium 2", "name": "tbl_Dados"})

    ws.set_column("A:A", 18)
    ws.set_column("C:C", 12, moeda)
    ws.freeze_panes(1, 0)

    # Fórmula e gráfico
    ws.write_formula("D1", "=SUM(tbl_Dados[Qtd])")
    chart = wb.add_chart({"type": "column"})
    chart.add_series({"categories": "=Dados!$A$2:$A$4",
                      "values": "=Dados!$B$2:$B$4", "name": "Qtd"})
    chart.set_title({"name": "Quantidade por produto"})
    ws.insert_chart("F2", chart)
```

## Editar arquivo existente com openpyxl
```python
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

wb = load_workbook("modelo.xlsx")      # use data_only=True para ler valores calculados
ws = wb["Dados"]
ws["E2"] = "=C2*D2"                    # escreve a fórmula, não o resultado
ws["A1"].font = Font(bold=True, color="FFFFFF")
ws["A1"].fill = PatternFill("solid", fgColor="1F3864")

dv = DataValidation(type="list", formula1='"Aberto,Fechado"', allow_blank=False)
ws.add_data_validation(dv); dv.add("F2:F100")

wb.save("modelo_atualizado.xlsx")
```

## Regras importantes
- openpyxl **não calcula** fórmulas: ao abrir com `data_only=True` os valores só existem se o arquivo foi salvo pelo Excel. Para recalcular, abrir no Excel ou usar LibreOffice headless.
- Escrever fórmulas em **inglês** com separador vírgula via bibliotecas (o Excel traduz ao abrir).
- Não usar `df.to_excel` para planilhas finais sem estilizar depois.
- Preservar o modelo original: salvar com novo nome.
- Para volume alto, usar XlsxWriter com `constant_memory` ou gerar CSV.
- Validar o resultado: reabrir, checar erros (`#REF!`, `#DIV/0!`) e totais.

## Integração com este projeto (RAG)
A IA deve consultar esta base, decidir a estrutura (arquivo 01), escolher funções (02), gerar o código Python (este arquivo) e aplicar o checklist (10) antes de entregar.
