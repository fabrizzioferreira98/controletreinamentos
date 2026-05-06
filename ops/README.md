# Operacao

## Papel

`ops/` e o centro operacional real do repositorio: scripts de release, smoke, QA, diagnostico, higiene, drills e automacao Windows/self-hosted vivem aqui.

A fonte curta de comandos oficiais continua em `docs/operations/canonical-commands.md`. Este README explica a fronteira operacional de `ops/`.

## Areas

| area | papel oficial |
| --- | --- |
| `scripts/admin/` | Saneamento e preparacao operacional de usuarios, incluindo usuarios de teste. |
| `scripts/backup/` | Drills de backup/restore e implementacoes operacionais de backup. O comando recorrente oficial fica em `backend/tools/maintenance/run_backups.py`. |
| `scripts/database/` | Rotinas manuais de dados, importacao, sincronizacao, consistencia e reconciliacao. O bootstrap estrutural oficial fica em `backend/tools/maintenance/bootstrap_db_schema.py`; a validacao oficial fica em `backend/tools/maintenance/run_db_consistency.py`; repair e cleanup sobrevivem apenas em `backend/tools/manual_unsafe/`; `sync_tripulantes_snapshot.py` vive como compat residual. |
| `scripts/diagnostics/` | Diagnosticos, rastreio de erros e relatorios de uso operacional. |
| `scripts/jobs/` | Drills de jobs e implementacoes de worker/notificacoes. As entradas oficiais recorrentes ficam em `backend/tools/maintenance/`. |
| `scripts/manuals/` | Geracao operacional de manuais e artefatos documentais. |
| `scripts/perf/` | Testes de carga e matriz autenticada. |
| `scripts/qa/` | Validacoes de QA, baseline de UI e smoke de homologacao. |
| `scripts/release/` | Gate de release, hardening de manifest, validacao de evidencias, rollback metadata e drills de release. |
| `scripts/repo/` | Hygiene estrutural do repositorio. |
| `scripts/smoke/` | Smoke pos-deploy. |
| `windows/` | Operacao Windows/self-hosted: env templates, Caddy, servicos, firewall, tasks e wrappers PowerShell. |

## Ligacao com docs vivas

| trilha em `ops/` | doc viva correspondente |
| --- | --- |
| `scripts/admin/` | `docs/operations/AUTH_TEST_USERS.md` e `docs/operations/canonical-commands.md`. |
| `scripts/backup/` | `docs/operations/RUNBOOK.md` e `docs/operations/windows_backup_restore_rollback.md`. |
| `scripts/database/` | `docs/operations/RUNBOOK.md` e `docs/operations/canonical-commands.md` para bootstrap estrutural e consistencia canonicos. |
| `scripts/diagnostics/` | `docs/operations/OBSERVABILITY.md` e `docs/operations/RUNBOOK.md`. |
| `scripts/jobs/` | `docs/operations/RUNBOOK.md`, `docs/operations/RELEASE_GATES.md` e `docs/operations/canonical-commands.md` para worker canonico. |
| `scripts/perf/` | `docs/operations/LOAD_TEST_PLAN.md` e `docs/operations/RELEASE_GATES.md`. |
| `scripts/qa/` | `docs/operations/AUTH_TEST_USERS.md` e `docs/operations/ui_baseline_hashes.json`. |
| `scripts/release/` | `docs/operations/RELEASE_GATES.md`, `docs/operations/REGRESSION_AUDIT_CHECKLIST.md` e `docs/operations/RELEASE_EVIDENCE_TEMPLATE.json`. |
| `scripts/repo/` | `docs/governance/repo-topology.md`, `docs/governance/root-entry-policy.md` e workflow `.github/workflows/repo-hygiene.yml`. |
| `scripts/smoke/` | `docs/operations/RUNBOOK.md`, `docs/operations/RELEASE_GATES.md` e `docs/operations/canonical-commands.md`. |
| `windows/` | `docs/operations/WINDOWS_SELF_HOSTED_SERVER.md`, `docs/operations/windows_backup_restore_rollback.md` e `docs/operations/canonical-commands.md`. |

## Fronteiras

- `ops/` concentra operacao transversal do produto.
- `backend/tools/maintenance/` permanece como entrada canonica para manutencao recorrente da aplicacao: bootstrap estrutural, backup, worker, notificacoes e consistencia de leitura/validacao.
- `backend/tools/manual_unsafe/` concentra repair e cleanup destrutivo fora da trilha normal.
- `backend/tools/compat_residual/` concentra entradas residuais que nao podem parecer fluxo canonico.
- `scripts/` permanece apenas como compatibilidade historica; nao recebe novos fluxos.
- `docs/operations/` documenta comandos e runbooks; nao substitui scripts reais.
- `archive/` guarda material historico fora da operacao viva.

## Regras

- Novo fluxo operacional vivo deve nascer em `ops/`, salvo quando for manutencao recorrente da aplicacao que pertence a `backend/tools/maintenance/`.
- Entrada direta em `ops/scripts/backup`, `ops/scripts/jobs` ou `ops/scripts/database` nao deve competir com comando canonico ja definido.
- Seed, sync, import e reconciliacao em `ops/scripts/database` nao sao bootstrap estrutural e nao devem voltar para a trilha principal.
- `cleanup_operational_data.py` e `run_db_consistency.py --repair` nao sao manutencao recorrente; ficam isolados em `backend/tools/manual_unsafe/`.
- `sync_tripulantes_snapshot.py` nao e sync oficial; fica rebaixado a compat residual.
- Release, smoke, QA, diagnostics, repo hygiene e Windows/self-hosted devem permanecer em `ops/`.
- Evidencias, backups e artefatos gerados nao devem ser gravados dentro de `ops/`; use caminhos externos ou `archive/` quando houver valor historico classificado.
