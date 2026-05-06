# ADR 002 - Financeiro modular em backend Flask e frontend SPA

## Status

Proposto e vinculante para a fase de desenho e implementacao futura do modulo Financeiro.

## Contexto

O backend atual e Flask 3.1.3, com API em `/api/v1`, contratos em `backend/src/controle_treinamentos/contracts/`, rotas HTTP em `backend/src/controle_treinamentos/api/http/`, use cases em `backend/src/controle_treinamentos/application/` e repositories SQL em `backend/src/controle_treinamentos/repositories/`. O acesso a PostgreSQL ocorre via `psycopg2`, sem ORM.

O frontend atual e uma SPA em JavaScript puro, sem TypeScript, sem bundler Node, com funcionalidades em `frontend/src/features/`, services em `frontend/src/services/`, registro de rotas em `frontend/src/app/route-registry.js` e navegacao em `frontend/src/shell/navigation.js`.

## Decisao

O Financeiro sera implementado como dominio modular dentro do monolito existente. Nao sera criado microsservico. O backend seguira as camadas atuais de HTTP, contratos, application/use cases e repositories SQL. O frontend seguira o padrao atual da SPA, com feature propria em `frontend/src/features/financeiro` e chamadas HTTP via services.

## Consequencias

- O modulo usa a governanca tecnica ja existente, sem criar uma arquitetura paralela.
- O acoplamento com Tripulantes deve ocorrer por identificadores e contratos, nao por duplicacao cadastral.
- A evolucao futura pode ser feita por fronteiras modulares sem quebrar o deploy atual.
- O Financeiro herda os padroes de request id, correlation id, envelope de erro, autenticacao e autorizacao existentes.

## Regras praticas

- Rotas HTTP futuras devem ser finas e delegar regra de negocio para use cases.
- Repositories SQL devem concentrar acesso a banco e nao expor SQL para controllers ou frontend.
- Contratos e serializadores devem normalizar entrada e saida das APIs financeiras.
- O frontend deve consumir APIs, manter estado de tela e formatar exibicao.
- O frontend nao deve conhecer formulas, tabelas financeiras ou regras de fechamento.
- A integracao com Cadastro de Tripulantes deve consumir dados existentes, sem duplicar nome, CPF, ANAC, contato, base, status, funcao ou flags operacionais.

## O que viola esta decisao

- Criar microsservico financeiro sem necessidade operacional real.
- Colocar SQL em rotas HTTP.
- Colocar regra financeira em componentes ou services de frontend.
- Criar um segundo cadastro de tripulantes dentro do Financeiro.
- Criar estrutura de pastas paralela que ignore `api/http`, `contracts`, `application` e `repositories`.
- Acoplar o Financeiro a superficies legadas removidas.

## Impacto na proxima fase

A proxima fase deve desenhar os contratos e use cases financeiros dentro das fronteiras atuais do repositorio. Antes de escrever codigo, a equipe deve definir quais arquivos novos entrariam em cada camada e quais testes cobririam cada contrato.
