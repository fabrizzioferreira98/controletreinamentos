# Operacao: docs e execucao

## Papel

Este indice liga documentacao operacional viva aos caminhos reais de execucao.

A fonte curta de comandos oficiais continua sendo `docs/operations/canonical-commands.md`. Este arquivo existe para rastrear a relacao entre docs vivas, scripts canonicos e scripts auxiliares em `ops/`.

## Docs vivas -> trilha canonica

| doc | trilha canonica correspondente |
| --- | --- |
| `canonical-commands.md` | Fonte oficial de comandos por tarefa critica. |
| `LOCAL_RUNTIME.md` | Bootstrap local real, ordem de subida, dependencias minimas e falso verde conhecido. |
| `ENVIRONMENT_PARITY.md` | Diferencas aceitaveis/perigosas entre local, homolog e producao; criterios para validar sem falso verde. |
| `CI_RELEASE_PIPELINE.md` | Esteira minima real de CI/build/release, classificacao dos gates e caminhos oficiais de promocao. |
| `RELEASE_MANAGEMENT.md` | Fluxo oficial de release, gate final, deploy operacional manual, validacao pos-release e rollback. |
| `RELEASE_EXECUTION_CHECKLIST.md` | Checklist obrigatorio para execucao de release e registro de evidencias. |
| `ROLLBACK_CHECKLIST.md` | Checklist obrigatorio para rollback acionavel. |
| `POST_RELEASE_VALIDATION.md` | Validacao minima obrigatoria apos deploy, sem falso verde de healthcheck. |
| `RUNBOOK.md` | Runbooks oficiais, troubleshooting, evidencia operacional e `ops/scripts/...`, `backend/tools/maintenance/...`, `ops/windows/scripts/...`, conforme tarefa. |
| `RELEASE_GATES.md` | `ops/scripts/release/run_release_strict.py` e validadores auxiliares em `ops/scripts/release/`. |
| `REGRESSION_AUDIT_CHECKLIST.md` | Checklist preenchido consumido por `ops/scripts/release/run_release_strict.py`. |
| `TEST_PROTECTION_STRATEGY.md` | Estrategia viva de protecao por camadas: unitario, integracao, contrato, frontend funcional, E2E e regressao operacional. |
| `RELEASE_EVIDENCE_TEMPLATE.json` | Manifest preenchido validado por `ops/scripts/release/validate_operational_evidence.py`. |
| `AUTH_TEST_USERS.md` | `ops/scripts/admin/sanitize_test_users.py` e usuarios canonicos de QA/E2E. |
| `LOAD_TEST_PLAN.md` | `ops/scripts/perf/load_test_smoke.py`, `ops/scripts/perf/load_test_authenticated.py` e `ops/scripts/perf/run_authenticated_matrix.py`. |
| `OBSERVABILITY.md` | Diagnostico por request/logs e `ops/scripts/diagnostics/trace_request_errors.py`. |
| `SLOS.md` | Incidentes e validacoes descritos em `RUNBOOK.md`, `OBSERVABILITY.md` e smoke pos-deploy. |
| `SECURITY_FRONT_26.md` | Mapa vivo da frente 26: superficies criticas, controles, hotspots e fila residual de seguranca. |
| `HTTP_CONTRACT_GUARDRAILS.md` | Catalogo HTTP em `backend/src/controle_treinamentos/core/http_contract.py` e testes de contrato em `tests/`. |
| `DATABASE_EVOLUTION.md` | Separacao entre bootstrap estrutural, migrations corretivas, seed/import historico, sync operacional e compat historica. |
| `WINDOWS_SELF_HOSTED_SERVER.md` | `ops/windows/scripts/`, `ops/windows/env/` e `ops/windows/caddy/`. |
| `windows_backup_restore_rollback.md` | `ops/windows/scripts/Invoke-BackupRestoreDrill.ps1` e manutencao canonica de backup em `backend/tools/maintenance/run_backups.py`. |
| `ui_baseline_hashes.json` | Dados de referencia usados por `ops/scripts/qa/validate_ui_baseline.py`. |

## Trilhas criticas -> doc viva

| trilha critica | doc viva |
| --- | --- |
| `backend/tools/runtime/run.py` | `LOCAL_RUNTIME.md` e `canonical-commands.md`. |
| `backend/tools/maintenance/bootstrap_db_schema.py` | `DATABASE_EVOLUTION.md`, `LOCAL_RUNTIME.md` e `canonical-commands.md`. |
| `backend/tools/maintenance/bootstrap_seed_data.py` | `LOCAL_RUNTIME.md` e `canonical-commands.md`. |
| `backend/tools/manual_unsafe/run_db_repair.py` | `DATABASE_EVOLUTION.md` e `canonical-commands.md`. |
| `ops/scripts/admin/sanitize_test_users.py` | `AUTH_TEST_USERS.md` e `canonical-commands.md`. |
| `ops/scripts/smoke/post_deploy_smoke.py` | `RUNBOOK.md`, `RELEASE_GATES.md`, `POST_RELEASE_VALIDATION.md` e `canonical-commands.md`. |
| `ops/scripts/release/run_release_strict.py` | `RELEASE_GATES.md`, `RELEASE_MANAGEMENT.md`, `REGRESSION_AUDIT_CHECKLIST.md`, `RELEASE_EVIDENCE_TEMPLATE.json` e `canonical-commands.md`. |
| `ops/scripts/release/validate_operational_evidence.py` | `RELEASE_GATES.md` e `RELEASE_EVIDENCE_TEMPLATE.json`. |
| `ops/scripts/release/harden_release_manifest.py` | `RELEASE_GATES.md` e `RELEASE_EVIDENCE_TEMPLATE.json`. |
| `ops/scripts/release/build_rollback_metadata.py` | `RELEASE_GATES.md`, `RELEASE_MANAGEMENT.md` e `windows_backup_restore_rollback.md`. |
| `ops/scripts/backup/backup_restore_drill.py` | `RUNBOOK.md` e `windows_backup_restore_rollback.md`. |
| `ops/scripts/jobs/jobs_concurrency_drill.py` | `RUNBOOK.md` e `RELEASE_GATES.md`. |
| `ops/scripts/perf/*.py` | `LOAD_TEST_PLAN.md` e `RELEASE_GATES.md`. |
| `ops/scripts/qa/validate_ui_baseline.py` | `ui_baseline_hashes.json`. |
| `ops/scripts/diagnostics/*.py` | `OBSERVABILITY.md` e `RUNBOOK.md`. |
| `ops/scripts/repo/validate_repo_hygiene.py` | Governanca estrutural em `docs/governance/` e workflow `.github/workflows/repo-hygiene.yml`. |
| `ops/windows/scripts/*.ps1` | `WINDOWS_SELF_HOSTED_SERVER.md`, `windows_backup_restore_rollback.md`, `RELEASE_MANAGEMENT.md` e `canonical-commands.md`. |

## Regra

- Script critico novo deve entrar em `ops/README.md` e neste indice com doc viva correspondente.
- Doc operacional nova deve apontar para comando, script, teste, template ou fluxo canonico real.
- Alias em `scripts/` nao deve ser documentado como trilha principal.
