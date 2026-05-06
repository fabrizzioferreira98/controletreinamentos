# Catalogo de audit log financeiro

## Status

Especificacao conceitual. Este catalogo nao cria eventos reais nem altera `auditoria_eventos`.

## Padrao atual a respeitar

O repositorio ja possui `backend/src/controle_treinamentos/audit.py` com `record_audit_event`, gravando `entidade`, `entidade_id`, `acao`, `payload_anterior`, `payload_novo`, `realizado_por` e `observacao`. Use cases existentes disparam auditoria explicitamente e podem operar com modo estrito.

Eventos financeiros futuros devem seguir esse padrao e adicionar metadados financeiros dentro dos payloads normalizados.

## Metadata minima comum

Todo evento financeiro deve carregar, quando aplicavel:

- `event_name`;
- `org_id`;
- `competencia`;
- `request_id`;
- `correlation_id`;
- `actor_user_id`;
- `entity_type`;
- `entity_id`;
- `permission`;
- `reason`;
- `calculation_version`;
- `source_endpoint`;
- `snapshot_id` quando houver fechamento.

Dados cadastrais sensiveis de tripulantes nao devem ser duplicados no audit payload. Usar `tripulante_id`.

## Eventos

| Evento | Quando dispara | entity_type | entity_id | before/after esperado | Metadata minima | Permissao relacionada |
| --- | --- | --- | --- | --- | --- | --- |
| `finance.mission.created` | Criacao de missao operacional | `finance_mission` | `mission_id` | `before=null`, `after=FinanceMission` | `org_id`, `competencia`, `mission_id`, `comandante_tripulante_id`, `copiloto_tripulante_id` | `finance:missions:create` |
| `finance.mission.updated` | Alteracao de fatos operacionais da missao | `finance_mission` | `mission_id` | `before=campos anteriores`, `after=campos novos` | `org_id`, `competencia`, `changed_fields`, `reason` | `finance:missions:update` |
| `finance.mission.cancelled` | Cancelamento de missao | `finance_mission` | `mission_id` | `before=status anterior`, `after=status cancelada` | `org_id`, `competencia`, `reason` | `finance:missions:cancel` |
| `finance.mission.recalculated` | Recalculo de uma missao | `finance_mission` | `mission_id` | `before=totais anteriores`, `after=totais novos` | `org_id`, `competencia`, `calculation_version`, `reason` | `finance:missions:recalculate` |
| `finance.hourly_bonus.calculated` | Calculo horario por participante e missao | `finance_hourly_bonus` | `calculation_id` ou `mission_id` | `before=calculo anterior/null`, `after=HourlyBonusCalculation` | `org_id`, `mission_id`, `tripulante_id`, `funcao`, `calculation_version` | `finance:missions:recalculate` ou `finance:periods:recalculate` |
| `finance.productivity.calculated` | Calculo de produtividade por competencia/tripulante | `finance_productivity_bonus` | `calculation_id` ou `tripulante_id` | `before=calculo anterior/null`, `after=ProductivityBonusCalculation` | `org_id`, `competencia`, `tripulante_id`, `calculation_version` | `finance:periods:recalculate` ou `finance:bonuses:recalculate` |
| `finance.parameter.created` | Criacao de parametro financeiro ou feriado | `finance_parameter` ou `finance_holiday` | `parameter_id` ou `holiday_id` | `before=null`, `after=FinanceParameter/holiday` | `org_id`, `tipo`, `vigencia_inicio`, `vigencia_fim`, `reason` | `finance:parameters:create` |
| `finance.parameter.updated` | Alteracao de parametro, vigencia, status ou feriado | `finance_parameter` ou `finance_holiday` | `parameter_id` ou `holiday_id` | `before=parametro anterior`, `after=parametro novo` | `org_id`, `tipo`, `changed_fields`, `reason` | `finance:parameters:update` |
| `finance.period.recalculated` | Recalculo de competencia | `finance_period` | identificador da competencia | `before=totais anteriores`, `after=totais recalculados` | `org_id`, `competencia`, `calculation_version`, `mission_count`, `participant_count` | `finance:periods:recalculate` |
| `finance.period.closed` | Fechamento mensal com snapshot | `finance_period` | identificador da competencia | `before=status aberto/em_conferencia`, `after=status fechada + snapshot` | `org_id`, `competencia`, `snapshot_id`, `closed_at`, `total_geral` | `finance:periods:close` |
| `finance.period.reopened` | Reabertura de competencia fechada | `finance_period` | identificador da competencia | `before=status fechada`, `after=status reaberta` | `org_id`, `competencia`, `reason`, `previous_snapshot_id` | `finance:periods:reopen` |
| `finance.export.generated` | Geracao de exportacao financeira | `finance_export` | `export_id` ou 0 | `before=null`, `after=metadados da exportacao` | `org_id`, `competencia`, `format`, `filters`, `record_count` | `finance:exports:create` |

## Regras praticas

- Eventos de mutation devem ser disparados no use case, nao na rota.
- Falha de auditoria deve seguir a politica de modo estrito do sistema.
- Payloads devem evitar CPF, telefone, e-mail, foto e documentos.
- Recalculo que altera resultado persistido deve ser auditado.
- Preview sem persistencia pode ser tratado como leitura, desde que nao altere snapshot ou total.
- Fechamento deve registrar snapshot ou referencia ao snapshot no audit log.
