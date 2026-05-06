# ADR 006 - Contratos HTTP para APIs Financeiras em /api/v1/financeiro

## Status

Proposto e vinculante para a fase de desenho e implementacao futura do modulo Financeiro.

## Contexto

O backend atual expoe APIs em `/api/v1` e usa contratos/serializadores em `backend/src/controle_treinamentos/contracts/`. Rotas HTTP ficam em `backend/src/controle_treinamentos/api/http/`, use cases em `backend/src/controle_treinamentos/application/` e repositories SQL em `backend/src/controle_treinamentos/repositories/`.

O sistema ja possui envelope com `success`, `status`, `code`, `message`, `request_id` e `correlation_id`, alem de paginacao `page`/`offset` quando aplicavel.

## Decisao

As APIs futuras do Financeiro serao novas e ficarao sob `/api/v1/financeiro`. Endpoints conceituais devem se organizar em torno de missoes, bonificacoes, parametros e fechamentos.

Os contratos HTTP financeiros devem seguir o padrao atual do sistema: serializadores em `contracts`, rotas finas em `api/http`, use cases em `application`, repositories SQL separados e envelope de resposta com request/correlation id.

## Consequencias

- Clientes terao uma superficie financeira coerente e isolada.
- Contratos existentes nao precisam ser alterados.
- Erros financeiros serao observaveis com os mesmos identificadores de requisicao do restante do sistema.
- Listagens financeiras poderao usar paginacao consistente com o produto.

## Regras praticas

- Usar prefixo `/api/v1/financeiro`.
- Usar envelope `success/status/code/message/request_id/correlation_id`.
- Usar `page`/`offset` em listagens quando aplicavel.
- Definir serializadores de entrada e saida antes de implementar rotas.
- Controllers nao devem acessar banco diretamente.
- Responses devem distinguir fato operacional, valor calculado, memoria de calculo e estado de fechamento.
- Nao alterar contratos HTTP existentes para acomodar o Financeiro.

## O que viola esta decisao

- Criar endpoints financeiros fora de `/api/v1/financeiro`.
- Retornar erro financeiro sem envelope padrao.
- Retornar listas grandes sem paginacao quando houver crescimento esperado.
- Validar payload apenas dentro do repository.
- Fazer rota chamar SQL diretamente.
- Alterar contrato existente de outro modulo para encaixar dado financeiro.

## Impacto na proxima fase

Antes de implementar codigo, devem ser desenhados contratos de request/response para missoes, previews de calculo, parametros e fechamentos. Esses contratos devem orientar testes de API e implementacao dos use cases.
