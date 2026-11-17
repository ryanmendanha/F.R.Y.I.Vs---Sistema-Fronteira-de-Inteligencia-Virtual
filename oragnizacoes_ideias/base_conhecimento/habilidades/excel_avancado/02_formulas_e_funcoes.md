---
habilidade: excel_avancado
arquivo: formulas_funcoes
tags: formulas, funcoes, procx, indice, corresp, somases, matriz dinamica, let, lambda
idioma: pt-BR
---

# Fórmulas e Funções Essenciais

## Referências: relativa, absoluta e mista
`A1` relativa, `$A$1` absoluta, `$A1` e `A$1` mistas (F4 alterna). Usar absoluta para premissas, mista para tabelas de dupla entrada.

## Lógicas
- `SE(teste; verdadeiro; falso)` / IF
- `SES(teste1; res1; teste2; res2; ...)` / IFS (substitui SE aninhado)
- `E()`, `OU()`, `NÃO()` / AND, OR, NOT
- `SEERRO(valor; alternativa)` / IFERROR e `SENÃODISP` / IFNA (preferir IFNA para tratar só #N/D)
- `PARÂMETRO(expr; v1; r1; ...)` / SWITCH

## Busca e referência
- **PROCX / XLOOKUP** (preferida, Excel 365/2021): `=PROCX(chave; col_busca; col_retorno; "não achou"; 0)`. Busca em qualquer direção, correspondência exata por padrão, aceita retorno de várias colunas.
- **ÍNDICE + CORRESP** / INDEX + MATCH (compatível com versões antigas): `=ÍNDICE(retorno; CORRESP(chave; busca; 0))`. Busca bidirecional: `=ÍNDICE(tabela; CORRESP(linha;col_A;0); CORRESP(coluna;cabecalhos;0))`.
- **PROCV / VLOOKUP**: só busca à direita e quebra se inserir colunas; usar sempre com 4º argumento `FALSO`/0. Evitar em modelos novos.
- `ÍNDICE`, `DESLOC` (volátil, evitar), `INDIRETO` (volátil, evitar), `ESCOLHER`.

## Agregação condicional
- `SOMASES(soma; crit_rng1; crit1; ...)` / SUMIFS
- `CONT.SES`, `MÉDIASES`, `MAXIFS`, `MINIFS`
- `SOMARPRODUTO(a; b)` / SUMPRODUCT: soma ponderada e critérios complexos: `=SOMARPRODUTO((A2:A100="X")*(B2:B100>10)*C2:C100)`.
- `AGREGAR` / AGGREGATE: ignora erros e linhas ocultas. `SUBTOTAL(109; ...)` respeita filtros.
- Critérios: `">="&B1`, `"*texto*"` (curinga), `"<>"` (não vazio).

## Matrizes dinâmicas (Excel 365)
- `FILTRO(matriz; condição; "vazio")` / FILTER
- `CLASSIFICAR` / SORT, `CLASSIFICARPOR` / SORTBY
- `ÚNICO` / UNIQUE, `SEQUÊNCIA` / SEQUENCE
- `XCORRESP`, `PROCX` com retorno multi-coluna
- `ESCOLHERCOLS`, `EMPILHARV` (VSTACK), `EMPILHARH` (HSTACK), `TOMAR` (TAKE), `DESCARTAR` (DROP)
- Operador de derramamento: `A1#` referencia todo o intervalo derramado.
- Exemplo: Top 5 clientes: `=TOMAR(CLASSIFICARPOR(ÚNICO(tbl[Cliente]); SOMASES(tbl[Valor];tbl[Cliente];ÚNICO(tbl[Cliente])); -1); 5)`

## LET e LAMBDA
- `LET(nome; valor; ...; cálculo)`: nomeia valores dentro da fórmula, melhora leitura e desempenho.
  `=LET(v; SOMA(B2:B10); i; v*Taxa_Imposto; v-i)`
- `LAMBDA(parâmetros; cálculo)`: cria funções próprias, salvas no Gerenciador de Nomes.
- `MAP`, `REDUCE`, `SCAN`, `BYROW`, `BYCOL`, `MAKEARRAY` para processamento em lote.

## Texto
`ESQUERDA`, `DIREITA`, `EXT.TEXTO`, `LOCALIZAR`, `SUBSTITUIR`, `ARRUMAR` (TRIM), `TEXTO(valor;"dd/mm/aaaa")`, `CONCAT`, `UNIRTEXTO(sep; ignorar_vazio; rng)`, `DIVIDIRTEXTO` / TEXTSPLIT, `TEXTOANTES`, `TEXTODEPOIS`. Preenchimento Relâmpago: Ctrl+E.

## Data e hora
`HOJE`, `AGORA` (voláteis), `DATA(a;m;d)`, `FIMMÊS(data; n)`, `DATAM`, `DIATRABALHO`, `DIATRABALHOTOTAL` (dias úteis, aceita feriados), `DATADIF(ini;fim;"Y"|"M"|"D")`, `SEMANAANO`, `DIA.DA.SEMANA`. Primeiro dia do mês: `=FIMMÊS(A1;-1)+1`.

## Financeiras
`VP`, `VF`, `PGTO`, `TAXA`, `NPER`, `VPL` (NPV, fluxos a partir do período 1), `TIR` (IRR), `XVPL`/`XTIR` (datas irregulares), `TIRM`, `PGTOJURO`, `PGTOPRIN`.

## Estatística e análise
`MÉDIA`, `MED`, `MODO`, `DESVPAD.S`, `CORREL`, `PROJ.LIN`, `TENDÊNCIA`, `PREVISÃO.ETS`, `PERCENTIL.INC`, `ORDEM.EQ`, `QUARTIL.INC`.

## Desempenho
Evitar funções voláteis (DESLOC, INDIRETO, HOJE em excesso), referências a colunas inteiras em SOMARPRODUTO, e fórmulas matriciais pesadas em milhares de linhas. Preferir PROCX/ÍNDICE a PROCV repetido e usar colunas auxiliares ou Power Query para cálculos pesados. Cálculo manual (Fórmulas > Opções de Cálculo) em modelos muito grandes.

## Erros comuns
`#N/D` (não encontrado), `#VALOR!` (tipo errado), `#REF!` (referência apagada), `#DIV/0!` (divisão por zero: `=SE(B1=0;0;A1/B1)`), `#NOME?` (função/nome inexistente), `#DESPEJAR!`/`#SPILL!` (área de derramamento bloqueada), `#NÚM!`. Ferramentas: Avaliar Fórmula, Rastrear Precedentes/Dependentes (aba Fórmulas), F9 para avaliar parte da fórmula.
