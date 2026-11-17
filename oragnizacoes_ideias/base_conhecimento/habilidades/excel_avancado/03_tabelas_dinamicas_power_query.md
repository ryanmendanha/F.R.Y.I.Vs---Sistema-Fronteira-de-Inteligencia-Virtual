---
habilidade: excel_avancado
arquivo: tabelas_dinamicas_power_query
tags: tabela dinamica, power query, power pivot, dax, etl, segmentacao
idioma: pt-BR
---

# Tabelas Dinâmicas, Power Query e Power Pivot

## Tabelas Dinâmicas (Pivot Tables)
Criar a partir de uma Tabela do Excel (Inserir > Tabela Dinâmica) para que o intervalo cresça sozinho. Áreas: Filtros, Colunas, Linhas, Valores.
- Configurações de campo de valor: Soma, Contagem, Média, "Mostrar valores como" (% do total, % da linha, diferença em relação ao anterior, total acumulado, classificação).
- Agrupar datas por mês/trimestre/ano e números por faixas.
- Campo calculado e item calculado (usar com cautela; preferir Power Pivot/DAX).
- **Segmentações** (Slicers) e **Linha do Tempo** para filtros visuais; conectar a várias tabelas dinâmicas (Relatório de Conexões).
- Layout: Formato tabular, repetir rótulos, sem subtotais desnecessários; desmarcar "Autoajustar largura" para manter formatação ao atualizar.
- Atualizar: Dados > Atualizar Tudo (Ctrl+Alt+F5). Usar `OBTERDADOSDINÂMICOS` / GETPIVOTDATA para buscar valores de uma dinâmica em relatórios.

## Power Query (Obter e Transformar Dados)
ETL sem código: Dados > Obter Dados. Fontes: Excel, CSV, pastas, PDF, web, SQL, SharePoint, APIs.
Transformações mais usadas:
- Promover cabeçalhos, alterar tipos, remover duplicatas/erros/linhas vazias.
- Dividir/mesclar colunas, extrair texto, substituir valores, preencher para baixo.
- **Despivotar colunas** (transformar colunas de meses em linhas): essencial para formato longo.
- **Mesclar consultas** (equivale a PROCV/JOIN: Interna, Externa Esquerda, Anti etc.).
- **Acrescentar consultas** (empilhar tabelas), **combinar arquivos de uma pasta** (consolidar dezenas de arquivos).
- Coluna personalizada (linguagem M), coluna condicional, agrupar por.
Boas práticas: nomear etapas, uma consulta por fonte (staging) + consulta final, desativar "carregar" para consultas intermediárias, usar parâmetros para caminhos de arquivo, manter dobramento de consulta (query folding) em fontes SQL.
Exemplo M simples:
```
let
  Fonte = Excel.CurrentWorkbook(){[Name="tbl_Vendas"]}[Content],
  Tipos = Table.TransformColumnTypes(Fonte,{{"Data", type date},{"Valor", type number}}),
  Filtrado = Table.SelectRows(Tipos, each [Valor] > 0)
in
  Filtrado
```

## Power Pivot e Modelo de Dados
Carregar tabelas ao Modelo de Dados e criar **relacionamentos** (esquema estrela: tabela fato no centro, tabelas dimensão ao redor: Calendário, Produtos, Clientes). Permite milhões de linhas e análises entre tabelas sem PROCV.
- Criar tabela Calendário e marcá-la como tabela de datas.
- **Medidas DAX** (calculam em contexto de filtro):
```
Total Vendas := SUM(Vendas[Valor])
Vendas Ano Anterior := CALCULATE([Total Vendas], SAMEPERIODLASTYEAR(Calendario[Data]))
Crescimento % := DIVIDE([Total Vendas] - [Vendas Ano Anterior], [Vendas Ano Anterior])
Vendas Acumuladas := TOTALYTD([Total Vendas], Calendario[Data])
```
- Funções-chave: CALCULATE, FILTER, ALL, DIVIDE, SUMX, RELATED, DISTINCTCOUNT, TOTALYTD, DATEADD.
- Preferir medidas a colunas calculadas (menor consumo de memória).
