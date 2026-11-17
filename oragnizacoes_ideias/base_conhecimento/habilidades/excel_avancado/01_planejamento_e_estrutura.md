---
habilidade: excel_avancado
arquivo: planejamento_estrutura
tags: estrutura, abas, tabelas, nomes definidos, modelagem
idioma: pt-BR
---

# Planejamento e Estrutura

## Antes de abrir o Excel
Responder: Qual decisão a planilha apoia? Quem usa? Quais entradas, cálculos e saídas? Qual a frequência de atualização? Qual o volume de dados (linhas)? Excel é a ferramenta certa (acima de ~1 milhão de linhas, usar banco de dados/Power BI)?

## Arquitetura de abas recomendada
1. **Capa / Leia-me**: objetivo, instruções, versão, autor, data, legenda de cores.
2. **Premissas / Parâmetros**: todas as entradas editáveis e listas (taxas, metas, categorias).
3. **Dados**: dados brutos em formato tabular, sem mesclar células, um registro por linha.
4. **Cálculos**: fórmulas intermediárias, sem formatação decorativa.
5. **Saídas / Dashboard**: resumos, gráficos e relatórios para leitura.
6. **Controle**: log de alterações, verificações de integridade.

## Regras para a base de dados
- Primeira linha = cabeçalhos únicos e sem células mescladas.
- Uma coluna = um tipo de dado (nunca misturar texto e número).
- Sem linhas ou colunas em branco no meio, sem totais dentro da base.
- Datas como datas reais (não texto), valores numéricos como número.
- Formato "longo" (uma linha por observação) em vez de "largo" (um mês por coluna) para facilitar tabelas dinâmicas.

## Tabelas do Excel (Ctrl+T)
Vantagens: expansão automática, referências estruturadas (`Vendas[Valor]`), formatação consistente, segmentações, fórmulas que se propagam sozinhas. Nomear cada tabela com prefixo, ex.: `tbl_Vendas`, `tbl_Clientes`.

## Nomes definidos
Gerenciador de Nomes (Ctrl+F3). Usar para premissas (`Taxa_Imposto`), intervalos de lista e constantes. Convenção: sem espaços, iniciando com letra, padrão consistente (`Premissa_Taxa`, `Lista_Categorias`).

## Padrão de cores (convenção de mercado)
- Fonte **azul**: entrada manual (hardcode).
- Fonte **preta**: fórmula.
- Fonte **verde**: link para outra aba.
- Fundo amarelo claro: célula de premissa editável.
- Vermelho: alertas e erros.

## Boas práticas de layout
Fórmulas consistentes na linha/coluna inteira, congelar painéis nos cabeçalhos, evitar mais de 3 níveis de dependência entre abas, ocultar gridlines em abas de apresentação, definir área de impressão.
