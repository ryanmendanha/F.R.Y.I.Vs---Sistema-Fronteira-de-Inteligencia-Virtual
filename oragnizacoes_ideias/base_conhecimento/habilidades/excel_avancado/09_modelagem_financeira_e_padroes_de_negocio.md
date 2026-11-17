---
habilidade: excel_avancado
arquivo: modelagem_padroes_negocio
tags: modelagem financeira, fluxo de caixa, orcamento, cenarios, solver, analise de sensibilidade
idioma: pt-BR
---

# Modelagem Financeira e Padrões de Negócio

## Estrutura de um modelo
Premissas > Cálculos (mensal/anual) > Demonstrativos (DRE, Fluxo de Caixa, Balanço) > Indicadores > Dashboard. Fluxo de cálculo da esquerda para a direita e de cima para baixo. Linha do tempo no topo, mesma coluna = mesmo período em todas as abas. Fórmula idêntica na linha toda.

## Análise de cenários e sensibilidade
- **Seletor de cenário**: célula com lista (Base/Otimista/Pessimista) + `ESCOLHER` ou `PROCX` para trazer as premissas ativas.
- **Tabela de Dados** (Dados > Teste de Hipóteses > Tabela de Dados): sensibilidade de uma ou duas variáveis (ex.: VPL em função de taxa e crescimento).
- **Atingir Meta** (Goal Seek): descobrir o valor de entrada para atingir um resultado.
- **Solver** (suplemento): otimização com restrições (mix de produtos, alocação).
- Gerenciador de Cenários para guardar conjuntos de valores.

## Indicadores comuns
Margem bruta, margem líquida, EBITDA, ROI, payback, VPL/TIR, ponto de equilíbrio (`custos fixos / margem de contribuição unitária`), giro de estoque, DSO/DPO, churn, CAC, LTV, curva ABC (acumulado % ordenado: A até 80%, B até 95%, C restante).

## Padrões frequentes
- **Controle de estoque**: tabela de movimentações (entrada/saída) + `SOMASES` por produto, estoque mínimo com formatação condicional.
- **Fluxo de caixa**: realizado vs. projetado, saldo acumulado, alerta de saldo negativo.
- **Folha/escala/cronograma**: Gantt com formatação condicional (`=E(E$1>=$B2;E$1<=$C2)`).
- **Orçamento vs. realizado**: variação absoluta e %, semáforo.
- **CRM/pipeline**: funil por etapa, tabela dinâmica por vendedor e mês.
- **Amortização (Price/SAC)**: `PGTO`, `PGTOJURO`, `PGTOPRIN` por período.

## Regras de ouro
Totais verificados por soma cruzada, sinais consistentes (receitas positivas, custos negativos ou o inverso, sempre igual), unidades explícitas, sem plugs escondidos, aba de premissas auditável e versionamento (`modelo_v1.2_2026-10-20.xlsx`).
