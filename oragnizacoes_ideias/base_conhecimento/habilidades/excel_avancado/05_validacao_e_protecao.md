---
habilidade: excel_avancado
arquivo: validacao_protecao
tags: validacao de dados, protecao, lista suspensa, seguranca, integridade
idioma: pt-BR
---

# Validação de Dados e Proteção

## Validação de dados
Dados > Validação de Dados. Tipos: Número inteiro, Decimal, Lista, Data, Hora, Comprimento do texto, Personalizado (fórmula).
- **Lista suspensa**: fonte = nome definido ou coluna de tabela (`=Lista_Categorias`). Com matriz dinâmica: `=ÚNICO(tbl[Cat])#` via nome definido.
- **Listas dependentes** (País > Estado): `=DESLOC` evitado; preferir `=ÍNDICE` ou nomes definidos com FILTRO: `=FILTRO(Estados[Estado];Estados[País]=B1)`.
- **Validação personalizada**: impedir duplicados `=CONT.SE($A:$A;A1)=1`; só datas futuras `=A1>HOJE()`; só texto sem espaços `=NÃO(ÉERROS(LOCALIZAR(" ";A1)))`.
- Configurar mensagem de entrada e **alerta de erro** em estilo "Parar".
- Círculos de validação: Dados > Validação > Circular Dados Inválidos (auditar).

## Proteção
- Bloquear células de fórmulas e liberar apenas células de entrada: selecionar entradas > Formatar Células > Proteção > desmarcar "Bloqueada"; depois Revisão > Proteger Planilha (com ou sem senha).
- Proteger estrutura da pasta de trabalho (impede excluir/renomear abas).
- Permitir Editar Intervalos para usuários específicos.
- Criptografar arquivo: Arquivo > Informações > Proteger Pasta de Trabalho > Criptografar com Senha.
- Atenção: proteção de planilha é para evitar erros acidentais, não segurança real; a senha de planilha é fraca.

## Verificações de integridade (aba Controle)
Incluir checagens que retornam OK/ERRO: total do dashboard = total da base; soma das partes = total; sem erros (`=SOMARPRODUTO(--ÉERRO(Dados!A2:Z1000))=0`); sem duplicados na chave; balanço fecha (ativo = passivo + PL). Um semáforo geral na capa.

## Tratamento de entrada
Usar `ARRUMAR` e `MAIÚSCULA`/`PRI.MAIÚSCULA` para normalizar texto; `VALOR`/`DATA.VALOR` para converter texto em número/data; Texto para Colunas e Power Query para limpeza em massa.
