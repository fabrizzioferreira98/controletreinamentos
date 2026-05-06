# ADR 005 - Estrategia de org_scope para evolucao SaaS

## Status

Proposto e vinculante para a fase de desenho e implementacao futura do modulo Financeiro.

## Contexto

O produto atual e single-tenant/self-hosted Windows/local. O inventario tecnico nao identificou org_scope ou multi-tenant ativo. Ao mesmo tempo, o Financeiro e um dominio sensivel e pode se tornar uma base para evolucao SaaS.

Refatorar o produto inteiro para multi-tenant antes do Financeiro aumentaria risco e escopo. Ignorar isolamento organizacional nas novas tabelas financeiras tambem criaria divida dificil de remover.

## Decisao

O Financeiro adotara estrategia incremental de org_scope. Novas tabelas financeiras devem nascer com `org_id` ou campo equivalente se ja houver entidade organizacional definida ate a fase de schema.

Se ainda nao houver entidade organizacional, a fase de modelagem deve registrar uma abstracao/placeholder de organizacao para o Financeiro antes de criar migrations. Esse placeholder pode representar a organizacao default do deploy single-tenant, mas deve manter o caminho aberto para isolamento futuro.

Nao havera refatoracao global de multi-tenant nesta etapa. O Financeiro nao deve ser lancado como multi-tenant real sem isolamento por organizacao em banco, contratos, autorizacao e auditoria.

## Consequencias

- O modulo nasce preparado para evolucao SaaS sem prometer multi-tenant imediato.
- O produto atual continua operando como single-tenant.
- A modelagem financeira tera uma decisao explicita sobre organizacao antes de criar tabelas.
- Consultas financeiras futuras deverao considerar escopo organizacional desde o inicio.

## Regras praticas

- Antes de criar schema financeiro, decidir se existe entidade organizacional real ou placeholder.
- Queries financeiras futuras devem filtrar pelo escopo organizacional quando o campo existir.
- Contratos financeiros nao devem expor dados de outra organizacao.
- Audit log financeiro deve registrar o escopo organizacional quando disponivel.
- Nao refatorar autenticacao global apenas para criar o Financeiro.
- Nao anunciar multi-tenant financeiro sem isolamento efetivo.

## O que viola esta decisao

- Criar tabelas financeiras sem qualquer caminho para `org_id` ou equivalente.
- Implementar isolamento apenas no frontend.
- Usar tenant em contrato sem enforcement no backend e banco.
- Refatorar todo o produto para multi-tenant dentro da primeira entrega financeira.
- Permitir fechamento financeiro compartilhando dados entre organizacoes.

## Impacto na proxima fase

A proxima fase deve incluir uma decisao de modelagem sobre `org_id` antes de qualquer migration. Se a entidade organizacional ainda nao existir, deve ser criado um desenho documentado de placeholder e default org para o Financeiro.
