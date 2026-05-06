# Checklist pre-schema do Financeiro

## Status

Checklist obrigatorio antes de criar migrations, tabelas, rotas funcionais ou frontend financeiro.

## Contratos HTTP

- [ ] Endpoints sob `/api/v1/financeiro` revisados e aprovados.
- [ ] Requests de criacao/alteracao de missao nao aceitam valores calculados.
- [ ] Responses de calculo incluem memoria de calculo.
- [ ] Listagens usam paginacao `page`/`offset` quando aplicavel.
- [ ] Envelope `success/status/code/message/request_id/correlation_id` mantido.
- [ ] Nenhum contrato existente fora do Financeiro foi alterado para encaixar o modulo.

## Dominio

- [ ] `FinanceMission` aprovado como fato operacional.
- [ ] `horario_apresentacao` pertence a missao.
- [ ] `horario_abandono` pertence a missao.
- [ ] Comandante e copiloto referenciam Tripulantes por id.
- [ ] Nenhum dado cadastral de tripulante e duplicado.
- [ ] Calculos horarios sao por participante.
- [ ] Produtividade e consolidada por competencia.
- [ ] Parametros financeiros possuem vigencia.
- [ ] Fechamento possui snapshot.

## org_scope

- [ ] Coluna conceitual `org_id` confirmada para futuras tabelas financeiras.
- [ ] Placeholder `default_single_tenant` confirmado para ambiente single-tenant.
- [ ] Queries futuras definidas com filtro por `org_id`.
- [ ] Restricoes unicas e indices futuros consideram `org_id`.
- [ ] Contratos de escrita nao aceitam `org_id` arbitrario do frontend.

## RBAC

- [ ] Matriz de permissoes financeiras revisada.
- [ ] Dependencias entre permissoes revisadas.
- [ ] Endpoints mutaveis possuem permissao explicita.
- [ ] Leitura de audit log restrita a `finance:audit:read`.
- [ ] Nenhuma permissao foi adicionada a `auth.py` antes dos testes da fase de implementacao.

## Audit log

- [ ] Eventos financeiros revisados.
- [ ] Mutations criticas possuem evento definido.
- [ ] Fechamento registra snapshot ou referencia ao snapshot.
- [ ] Reabertura exige motivo.
- [ ] Payloads evitam CPF, telefone, e-mail, foto e documentos.
- [ ] Falha de auditoria respeita politica de modo estrito.

## Calculo e memoria

- [ ] `calculation_version` definido para a primeira implementacao.
- [ ] Memoria de calculo inclui entradas, parametros, calendario, passos e totais.
- [ ] Parametros usados incluem vigencia.
- [ ] Fechamento congela memoria de calculo.
- [ ] Frontend nao recebe responsabilidade de recalcular valores.

## Legado

- [ ] Nenhuma rota legada de Missoes ou Produtividade sera recriada.
- [ ] Nenhuma tela legada sera reativada.
- [ ] Testes que protegem remocao do legado permanecem intactos.
- [ ] Nomes de rotas, permissoes e arquivos deixam claro o namespace financeiro.

## Gate de implementacao

Somente apos todos os itens aplicaveis estarem resolvidos a equipe deve criar:

- migrations financeiras;
- contracts Python;
- use cases;
- repositories SQL;
- rotas Flask;
- permissoes reais;
- frontend SPA.
