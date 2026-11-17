---
habilidade: excel_avancado
arquivo: checklist_qualidade
tags: checklist, qualidade, auditoria, erros comuns, revisao
idioma: pt-BR
---

# Checklist de Qualidade e Erros Comuns

## Checklist antes de entregar
**Estrutura**
- [ ] Abas separadas: Leia-me, Premissas, Dados, Cálculos, Saídas, Controle
- [ ] Dados em Tabela do Excel, sem mesclagem, sem linhas em branco
- [ ] Premissas centralizadas e nomeadas, sem valores fixos em fórmulas

**Fórmulas**
- [ ] Fórmulas consistentes em toda a coluna/linha
- [ ] Sem funções voláteis desnecessárias (DESLOC, INDIRETO)
- [ ] Erros tratados com SEERRO/SENÃODISP apenas onde faz sentido (não esconder problemas)
- [ ] Sem referências externas quebradas (Dados > Editar Vínculos)
- [ ] Sem números armazenados como texto

**Entrada e proteção**
- [ ] Validação de dados nas células de entrada
- [ ] Células de fórmula bloqueadas, planilha protegida
- [ ] Verificações de integridade na aba Controle: tudo OK

**Apresentação**
- [ ] Formatação consistente, fonte única, cores com significado
- [ ] Formatos numéricos corretos (moeda, %, data), unidades indicadas
- [ ] Cabeçalhos congelados, filtros, larguras ajustadas
- [ ] Dashboard sem poluição visual, títulos informativos
- [ ] Área de impressão configurada

**Documentação**
- [ ] Instruções de uso, versão, autor, data de atualização
- [ ] Notas em premissas críticas

**Teste**
- [ ] Testar com valores extremos (zero, negativo, vazio)
- [ ] Conferir totais com cálculo independente
- [ ] Abrir em outra máquina/versão do Excel (compatibilidade das funções 365)
- [ ] Tamanho do arquivo razoável (remover formatação em linhas não usadas, `.xlsb` para arquivos pesados)

## Erros comuns e correções
- **Mesclar células na base**: quebra filtros e dinâmicas. Use "Centralizar na seleção".
- **PROCV com intervalo relativo**: o intervalo desliza ao copiar; fixar com `$` ou usar tabela.
- **Datas como texto**: converter com `DATA.VALOR` ou Power Query.
- **Hardcode dentro de fórmulas** (`=A1*1,18`): mover para premissa.
- **Arredondar com formatação** em vez de `ARRED`: o valor real continua com casas decimais.
- **Intervalos que não cobrem novas linhas**: usar Tabelas.
- **Uma planilha gigante com tudo em uma aba**: dividir por responsabilidade.
- **Referências circulares acidentais**: Fórmulas > Verificação de Erros > Referências Circulares.
- **Totais manuais sobre filtros**: usar `SUBTOTAL`/`AGREGAR`.
- **Planilha compartilhada sem controle**: usar OneDrive/SharePoint com histórico de versões.

## Fluxo de trabalho da IA ao criar uma planilha
1. Entender o objetivo e coletar requisitos (usuários, dados, saídas, volume).
2. Definir a arquitetura de abas (arquivo 01).
3. Modelar dados e premissas; escolher funções (02) e ferramentas (03).
4. Construir cálculos, depois dashboard (04).
5. Adicionar validação e proteção (05) e formatação (06).
6. Automatizar o que for repetitivo (07/08).
7. Rodar o checklist, corrigir e entregar com instruções.
