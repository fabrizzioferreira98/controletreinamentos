# Matriz RBAC financeira

## Status

Especificacao conceitual. Nenhuma permissao real foi adicionada em `backend/src/controle_treinamentos/auth.py`.

## Perfis conceituais

- `admin`: administracao completa do produto e do Financeiro.
- `financeiro`: operacao financeira diaria, parametros e fechamento.
- `operacoes`: registro e manutencao de fatos operacionais, sem acesso decisorio a valores financeiros.
- `auditor`: leitura ampla, auditoria, divergencias e exportacao para revisao.
- `leitura`: consulta financeira sem mutacao.

## Permissoes

| Permissao | admin | financeiro | operacoes | auditor | leitura | Observacao |
| --- | --- | --- | --- | --- | --- | --- |
| `finance:missions:read` | X | X | X | X | X | Consulta missoes operacionais |
| `finance:missions:create` | X | X | X |  |  | Cria fatos operacionais financeiros |
| `finance:missions:update` | X | X | X |  |  | Altera fatos antes de fechamento |
| `finance:missions:cancel` | X | X |  |  |  | Cancela missao com motivo |
| `finance:missions:recalculate` | X | X |  |  |  | Recalcula missao no backend |
| `finance:bonuses:read` | X | X |  | X | X | Consulta valores calculados |
| `finance:bonuses:recalculate` | X | X |  |  |  | Reservada para recalculos especificos futuros |
| `finance:parameters:read` | X | X |  | X | X | Consulta parametros e vigencias |
| `finance:parameters:create` | X | X |  |  |  | Cria parametros com audit log |
| `finance:parameters:update` | X | X |  |  |  | Altera vigencia/status com audit log |
| `finance:periods:read` | X | X |  | X | X | Consulta competencias |
| `finance:periods:recalculate` | X | X |  |  |  | Recalcula competencia aberta/reaberta |
| `finance:periods:close` | X | X |  |  |  | Fecha competencia com snapshot |
| `finance:periods:reopen` | X | X |  |  |  | Reabre competencia com motivo |
| `finance:audit:read` | X |  |  | X |  | Consulta audit log financeiro |
| `finance:divergences:read` | X | X | X | X | X | Consulta inconsistencias e bloqueios |
| `finance:exports:create` | X | X |  | X |  | Gera exportacoes financeiras |

## Dependencias conceituais

- `finance:missions:create`, `finance:missions:update`, `finance:missions:cancel` e `finance:missions:recalculate` implicam `finance:missions:read`.
- `finance:bonuses:recalculate` implica `finance:bonuses:read`.
- `finance:parameters:create` e `finance:parameters:update` implicam `finance:parameters:read`.
- `finance:periods:recalculate`, `finance:periods:close` e `finance:periods:reopen` implicam `finance:periods:read`.
- `finance:exports:create` deve respeitar os mesmos filtros de escopo de leitura do usuario.

## Regras de seguranca

- O backend deve negar operacoes sem permissao mesmo que o frontend esconda botoes.
- O frontend pode usar permissoes para navegacao e estados visuais, mas nao como controle unico.
- Mutations financeiras criticas devem gerar audit log.
- Permissoes financeiras nao devem ser adicionadas ao auth global antes dos contratos e testes da fase de implementacao.
- Permissao ampla unica como `finance:*` nao deve substituir a matriz granular.
