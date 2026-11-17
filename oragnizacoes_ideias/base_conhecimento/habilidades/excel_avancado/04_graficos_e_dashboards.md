---
habilidade: excel_avancado
arquivo: graficos_dashboards
tags: graficos, dashboard, kpi, visualizacao, formatacao condicional
idioma: pt-BR
---

# Gráficos e Dashboards

## Escolha do gráfico
- Comparação entre categorias: colunas/barras (barras horizontais para rótulos longos), ordenar valores.
- Evolução no tempo: linhas (ou colunas para poucos períodos).
- Composição: colunas empilhadas 100% ou pizza só com até 4–5 fatias; evitar 3D.
- Relação entre variáveis: dispersão (scatter) e bolhas.
- Meta vs. realizado: colunas + linha de meta, gráfico de bullet, termômetro.
- Variação/ponte (resultado): gráfico de cascata (waterfall).
- Distribuição: histograma, caixa e bigode.
- Combinação: colunas + linha com eixo secundário (usar com moderação e rotular eixos).

## Princípios de visualização
1. Título que responde uma pergunta ou comunica a conclusão ("Vendas cresceram 12% no 3º trimestre").
2. Remover ruído: gridlines, bordas, legendas redundantes; rotular dados diretamente.
3. Uma cor de destaque e cinzas para o restante; paleta consistente (máx. 5 cores).
4. Eixo de colunas sempre começa em zero.
5. Ordenar categorias por valor (exceto tempo).

## Gráficos dinâmicos
Usar Tabelas e Tabelas Dinâmicas como fonte. Para gráficos controlados por lista suspensa: fórmula `PROCX`/`ÍNDICE` alimenta uma série auxiliar; ou segmentações ligadas a gráficos dinâmicos.

## Estrutura de um dashboard profissional
- Aba separada, gridlines ocultas, largura fixa para caber em uma tela (~1366 px).
- Topo: título, período, data de atualização.
- Linha de **KPIs** (cartões grandes com valor, variação % e seta/ícone).
- Meio: 2 a 4 gráficos principais alinhados em grade.
- Rodapé: tabela de detalhe ou notas e fonte dos dados.
- Controles: segmentações e listas de validação no topo ou lateral.
- Alinhar objetos (Formato > Alinhar) e agrupar (Ctrl+G).

## Formatação condicional
Início > Formatação Condicional: barras de dados, escalas de cor, conjuntos de ícones, regras por fórmula. Exemplo de linha inteira destacada: regra com `=$E2="Atrasado"` aplicada em `=$A$2:$H$100`. Usar com critério (no máximo 2–3 regras visíveis por tabela).

## Minigráficos (Sparklines)
Inserir > Minigráficos (linha, coluna, ganho/perda) para tendência dentro de células.

## Cartão de KPI (exemplo)
Valor: `=SOMASES(Vendas[Valor];Vendas[Mês];Mes_Selecionado)`. Variação: `=valor/valor_anterior-1` formatada `▲ 0,0%;▼ 0,0%`. Cor condicional verde/vermelha via formato numérico `[Cor10]▲ 0,0%;[Vermelho]▼ 0,0%`.
