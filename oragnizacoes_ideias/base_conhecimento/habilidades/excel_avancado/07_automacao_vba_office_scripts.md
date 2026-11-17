---
habilidade: excel_avancado
arquivo: automacao_vba_office_scripts
tags: vba, macro, office scripts, automacao, power automate
idioma: pt-BR
---

# Automação com VBA e Office Scripts

## Quando automatizar
Tarefa repetitiva, manual e com regras claras. Antes do VBA, tentar Power Query (importação/limpeza) e fórmulas. Salvar como `.xlsm`. Habilitar aba Desenvolvedor.

## Boas práticas em VBA
- `Option Explicit` no topo de todo módulo.
- Nunca usar `Select`/`Activate`: referenciar objetos diretamente.
- Desligar atualização de tela e cálculo durante o processamento e restaurar ao final (inclusive em caso de erro).
- Tratar erros com `On Error GoTo`.
- Trabalhar com arrays em memória para grandes volumes (muito mais rápido que célula a célula).
- Comentar, nomear variáveis com clareza, dividir em sub-rotinas pequenas.

## Modelo base de macro
```vba
Option Explicit

Sub AtualizarRelatorio()
    Dim ws As Worksheet
    Dim ultimaLinha As Long

    On Error GoTo Tratar
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual

    Set ws = ThisWorkbook.Worksheets("Dados")
    ultimaLinha = ws.Cells(ws.Rows.Count, "A").End(xlUp).Row

    ws.Range("E2:E" & ultimaLinha).Formula = "=C2*D2"

    ThisWorkbook.RefreshAll

Saida:
    Application.Calculation = xlCalculationAutomatic
    Application.ScreenUpdating = True
    Exit Sub
Tratar:
    MsgBox "Erro: " & Err.Description, vbCritical
    Resume Saida
End Sub
```

## Padrões úteis
- Loop em array: `arr = ws.Range("A1:D1000").Value` e processar `arr(i, j)`.
- Exportar aba para PDF: `ws.ExportAsFixedFormat xlTypePDF, caminho`.
- Evento de planilha: `Worksheet_Change` para reagir a edições (desativar `Application.EnableEvents` ao alterar células dentro do evento).
- Botão: Inserir > Formas > Atribuir Macro.
- Enviar e-mail via Outlook: objeto `Outlook.Application` com `CreateObject`.
- Dicionário para contar/agrupar: `CreateObject("Scripting.Dictionary")`.

## Office Scripts (Excel na web) e Power Automate
Automação em TypeScript, executável na nuvem e agendável via Power Automate (ex.: todo dia útil às 8h, atualizar e enviar relatório por e-mail).
```ts
function main(workbook: ExcelScript.Workbook) {
  const sheet = workbook.getWorksheet("Dados");
  const range = sheet.getUsedRange();
  range.getFormat().autofitColumns();
}
```

## Segurança
Macros só de fontes confiáveis; assinar digitalmente em ambiente corporativo; nunca gravar senhas no código.
