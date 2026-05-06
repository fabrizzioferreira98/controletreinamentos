# Financeiro - indice tecnico

## Proposito

Esta pasta documenta o futuro modulo Financeiro antes de qualquer schema, rota funcional, frontend ou calculo. O Financeiro e um novo dominio sob `/api/v1/financeiro` e nao restaura as superficies legadas de Missoes ou Produtividade.

## ADRs

- `adr-001-novo-dominio-financeiro-nao-restauracao-legado.md`: novo dominio Financeiro, sem restauracao do legado.
- `adr-002-financeiro-modular-flask-spa.md`: Financeiro dentro do backend Flask e da SPA atual.
- `adr-003-backend-fonte-verdade-calculos.md`: backend calcula, frontend exibe.
- `adr-004-separacao-fatos-calculos-parametros-fechamento.md`: fatos, calculos, parametros e fechamento separados.
- `adr-005-org-scope-evolucao-saas.md`: estrategia incremental de org_scope.
- `adr-006-contratos-http-financeiro-api-v1.md`: contratos HTTP sob `/api/v1/financeiro`.
- `adr-007-rbac-audit-log-trilha-calculo.md`: RBAC, audit log e trilha de calculo.
- `adr-008-parametros-vigencia-snapshots-fechamento.md`: parametros com vigencia e snapshots.

## Baseline de contratos

- `baseline-api-financeiro.md`: mapa de endpoints futuros e contratos request/response conceituais.
- `contratos-dominio-financeiro.md`: contratos de dominio para missao, participante, calculos, parametros e competencia.
- `matriz-rbac-financeiro.md`: permissoes conceituais e perfis de acesso.
- `catalogo-audit-log-financeiro.md`: eventos futuros de auditoria financeira.
- `contrato-memoria-calculo-financeiro.md`: formato conceitual da memoria de calculo.
- `org-scope-placeholder-financeiro.md`: decisao concreta de `org_id` placeholder para futuras migrations.
- `checklist-pre-schema-financeiro.md`: validacao obrigatoria antes de criar schema financeiro.

## Documentos de apoio

- `visao-tecnica-financeiro.md`: visao tecnica curta do modulo.
- `glossario-dominio-financeiro.md`: glossario de dominio financeiro.

## Guardrails

- Nao criar migrations antes do checklist pre-schema.
- Nao criar rotas Flask funcionais nesta etapa.
- Nao editar `backend/src/controle_treinamentos/auth.py` nesta etapa.
- Nao criar frontend ou navegacao nesta etapa.
- Nao duplicar dados cadastrais de tripulantes.
- Nao calcular valores financeiros no frontend.
- Nao reativar Missoes ou Produtividade legadas.
