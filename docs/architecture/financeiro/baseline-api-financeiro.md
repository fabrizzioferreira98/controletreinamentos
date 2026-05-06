# Baseline de contratos HTTP financeiros

## Status

Especificacao conceitual para a proxima fase. Este documento nao cria rotas, blueprint, schema, permissao real ou frontend.

## Padrao do repositorio

As APIs financeiras futuras devem seguir o padrao vivo do backend Flask:

- prefixo de API: `/api/v1/financeiro`;
- rotas HTTP em `backend/src/controle_treinamentos/api/http/`;
- contratos e serializadores em `backend/src/controle_treinamentos/contracts/`;
- use cases em `backend/src/controle_treinamentos/application/`;
- repositories SQL em `backend/src/controle_treinamentos/repositories/`;
- RBAC por `permission_required` e mapa central de permissoes;
- audit log disparado explicitamente por use case;
- envelope com `success`, `status`, `code`, `message`, `request_id` e `correlation_id`;
- paginacao `page` e `offset` em listagens financeiras quando aplicavel.

## Envelope base

Resposta de sucesso conceitual:

```json
{
  "success": true,
  "status": 200,
  "code": "finance_example_ok",
  "message": "Operacao concluida.",
  "request_id": "req-id",
  "correlation_id": "corr-id"
}
```

Resposta de erro conceitual:

```json
{
  "success": false,
  "status": 400,
  "code": "finance_validation_error",
  "message": "Mensagem de erro de dominio.",
  "request_id": "req-id",
  "correlation_id": "corr-id"
}
```

Listagens devem retornar `pagination` com `page`, `offset`, `limit`, `total` e indicadores de navegacao quando aplicavel.

## Endpoints de Missoes

| Metodo | Caminho | Objetivo | Permissao conceitual | Auditoria |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/financeiro/missoes` | Listar missoes operacionais por filtros | `finance:missions:read` | Nao dispara |
| POST | `/api/v1/financeiro/missoes` | Criar missao operacional | `finance:missions:create` | `finance.mission.created` |
| GET | `/api/v1/financeiro/missoes/{id}` | Consultar detalhe de missao | `finance:missions:read` | Nao dispara |
| PATCH | `/api/v1/financeiro/missoes/{id}` | Alterar fatos operacionais da missao | `finance:missions:update` | `finance.mission.updated` |
| POST | `/api/v1/financeiro/missoes/{id}/recalcular` | Recalcular bonificacao horaria da missao | `finance:missions:recalculate` | `finance.mission.recalculated` e `finance.hourly_bonus.calculated` |
| POST | `/api/v1/financeiro/missoes/{id}/cancelar` | Cancelar missao operacional | `finance:missions:cancel` | `finance.mission.cancelled` |

Filtros de listagem:

- `competencia`;
- `status`;
- `tripulante_id`;
- `aeronave_id`;
- `data_inicio`;
- `data_fim`;
- `page`;
- `offset`.

`POST /missoes` deve aceitar somente fatos operacionais da `FinanceMissionCreateRequest`. Nao aceita totais calculados.

`PATCH /missoes/{id}` pode alterar fatos operacionais enquanto a competencia nao estiver fechada. Nao pode alterar valores derivados nem criar horario por tripulante.

`POST /missoes/{id}/cancelar` deve exigir `motivo`.

## Endpoints de Bonificacoes

| Metodo | Caminho | Objetivo | Permissao conceitual | Auditoria |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/financeiro/bonificacoes/horaria` | Listar bonificacoes horarias calculadas | `finance:bonuses:read` | Nao dispara |
| GET | `/api/v1/financeiro/bonificacoes/horaria/{id}` | Consultar calculo horario especifico | `finance:bonuses:read` | Nao dispara |
| GET | `/api/v1/financeiro/bonificacoes/produtividade` | Listar produtividade por competencia | `finance:bonuses:read` | Nao dispara |
| GET | `/api/v1/financeiro/bonificacoes/produtividade/{tripulante_id}` | Consultar produtividade de um tripulante | `finance:bonuses:read` | Nao dispara |

Filtros esperados:

- `competencia`;
- `tripulante_id`;
- `funcao`;
- `mission_id`;
- `status_calculo`;
- `page`;
- `offset`.

Bonificacoes sao leitura de resultados calculados pelo backend. O frontend nao envia total, formula ou tabela financeira.

## Endpoints de Fechamento

| Metodo | Caminho | Objetivo | Permissao conceitual | Auditoria |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/financeiro/competencias/{competencia}` | Consultar competencia, totais, estado e snapshot | `finance:periods:read` | Nao dispara |
| POST | `/api/v1/financeiro/competencias/{competencia}/recalcular` | Recalcular competencia aberta ou reaberta | `finance:periods:recalculate` | `finance.period.recalculated` |
| POST | `/api/v1/financeiro/competencias/{competencia}/fechar` | Fechar competencia mensal com snapshot | `finance:periods:close` | `finance.period.closed` |
| POST | `/api/v1/financeiro/competencias/{competencia}/reabrir` | Reabrir competencia fechada | `finance:periods:reopen` | `finance.period.reopened` |

`POST /fechar` deve exigir confirmacao explicita e deve gerar snapshot com missoes, participantes, parametros, memoria de calculo, totais, usuario e data.

`POST /reabrir` deve exigir `motivo`.

## Endpoints de Parametros e Feriados

| Metodo | Caminho | Objetivo | Permissao conceitual | Auditoria |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/financeiro/parametros` | Listar parametros financeiros com vigencia | `finance:parameters:read` | Nao dispara |
| POST | `/api/v1/financeiro/parametros` | Criar parametro financeiro | `finance:parameters:create` | `finance.parameter.created` |
| PATCH | `/api/v1/financeiro/parametros/{id}` | Alterar vigencia, status ou metadados de parametro | `finance:parameters:update` | `finance.parameter.updated` |
| GET | `/api/v1/financeiro/feriados` | Listar calendario financeiro | `finance:parameters:read` | Nao dispara |
| POST | `/api/v1/financeiro/feriados` | Criar feriado/regra de calendario financeiro | `finance:parameters:create` | `finance.parameter.created` com `entity_type=finance_holiday` |
| PATCH | `/api/v1/financeiro/feriados/{id}` | Alterar feriado/regra de calendario financeiro | `finance:parameters:update` | `finance.parameter.updated` com `entity_type=finance_holiday` |

Parametros devem ter vigencia. A API deve rejeitar sobreposicoes ambiguas quando comprometerem calculo.

## Endpoints de Auditoria e Divergencias

| Metodo | Caminho | Objetivo | Permissao conceitual | Auditoria |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/financeiro/auditoria` | Consultar eventos financeiros de auditoria | `finance:audit:read` | Nao dispara |
| GET | `/api/v1/financeiro/divergencias` | Consultar divergencias e inconsistencias financeiras | `finance:divergences:read` | Nao dispara |

Filtros esperados para auditoria:

- `competencia`;
- `entity_type`;
- `entity_id`;
- `event`;
- `actor_user_id`;
- `data_inicio`;
- `data_fim`;
- `page`;
- `offset`.

## Requests conceituais principais

`FinanceMissionCreateRequest`:

```json
{
  "competencia": "2026-04",
  "data_missao": "2026-04-29",
  "cavok_numero_voo": "CAVOK-123",
  "contratante": "Cliente",
  "chamado": "CH-123",
  "aeronave_id": 10,
  "categoria_financeira_aeronave": "categoria_a",
  "comandante_tripulante_id": 1,
  "copiloto_tripulante_id": 2,
  "horario_apresentacao": "2026-04-29T08:00:00-03:00",
  "horario_abandono": "2026-04-29T18:00:00-03:00",
  "trecho": "SBSP-SBRJ",
  "houve_pernoite": false,
  "quantidade_pernoites": 0,
  "cobertura_base": false,
  "operacao_especial": false,
  "observacoes": ""
}
```

`FinanceParameterCreateRequest`:

```json
{
  "tipo": "adicional_noturno",
  "funcao": "comandante",
  "categoria": "categoria_a",
  "valor": "150.00",
  "unidade": "BRL",
  "vigencia_inicio": "2026-04-01",
  "vigencia_fim": null,
  "motivo": "Parametro inicial aprovado"
}
```

`FinancePeriodCloseRequest`:

```json
{
  "confirm": true,
  "motivo": "Fechamento mensal revisado",
  "expected_calculation_version": "finance-v1"
}
```

## Responses conceituais principais

Detalhe de missao:

```json
{
  "success": true,
  "status": 200,
  "code": "finance_mission_detail_ok",
  "mission": {},
  "participants": [],
  "hourly_bonus_calculations": [],
  "request_id": "req-id",
  "correlation_id": "corr-id"
}
```

Resumo de competencia:

```json
{
  "success": true,
  "status": 200,
  "code": "finance_period_detail_ok",
  "period": {},
  "totals": {},
  "divergences": [],
  "request_id": "req-id",
  "correlation_id": "corr-id"
}
```

## Regras de fronteira

- Horarios de apresentacao e abandono pertencem a missao.
- Participantes referenciam tripulantes por id; nao duplicam cadastro.
- Valores calculados sao retornados pelo backend.
- Endpoints financeiros nao devem alterar contratos HTTP existentes.
- Nenhum endpoint deste documento existe ate implementacao futura.
