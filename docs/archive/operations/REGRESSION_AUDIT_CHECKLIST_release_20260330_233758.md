# Auditoria de Regressao por Release

Status: arquivado. Este documento preserva a evidencia historica da release `release_20260330_233758`. A fonte viva para novas releases e `docs/operations/REGRESSION_AUDIT_CHECKLIST.md`.

## Metadados
- Release ID: release_20260330_233758
- Commit SHA: 7da9e192b816a7246c1a38ff32332d9d1c3cbb7b
- Ambiente: homolog
- Responsavel tecnico: release-bot
- Data/hora: 2026-03-30 22:24:12

## Checklist obrigatorio (PASS/FAIL)
- [x] Contrato HTTP (401/403/500/CSRF) validado em navegacao e chamadas programaticas.
- [x] Autenticacao e autorizacao (login, logout, permissao) validadas.
- [x] CRUDs criticos validados ponta a ponta.
- [x] Jobs (enqueue, worker, retry, dead-letter) validados.
- [x] Backup/restore drill validado.
- [x] Rollback drill validado (ida e volta).
- [x] Carga autenticada validada dentro do SLO.
- [x] Alertas externos validados ponta a ponta.
- [x] Smoke pos-deploy validado.
- [x] Gate de release com evidencias operacionais em PASS.

## Evidencias anexadas
- E2E: C:/srv-data/controle-treinamentos/hml/evidence/release_20260330_233758/e2e/e2e_homolog_summary.json
- Carga autenticada: C:/srv-data/controle-treinamentos/hml/evidence/release_20260330_233758/perf/load_auth_matrix.json
- Jobs concorrentes: C:/srv-data/controle-treinamentos/hml/evidence/release_20260330_233758/jobs/jobs_concurrency_drill.json
- Alertas externos: C:/srv-data/controle-treinamentos/hml/evidence/release_20260330_233758/alerts/alerts_external_drill.json
- Backup/restore: C:/srv-data/controle-treinamentos/hml/evidence/release_20260330_233758/backup/backup_restore_drill.json
- Rollback: C:/srv-data/controle-treinamentos/hml/evidence/release_20260330_233758/rollback/rollback_runtime_ids.json
- Smoke: C:/srv-data/controle-treinamentos/hml/evidence/release_20260330_233758/smoke/post_deploy_smoke.json
- Manifest de evidencias: C:/srv-data/controle-treinamentos/hml/evidence/release_20260330_233758/release_manifest.json

## Decisao
- Resultado: GO
- Justificativa: Todos os checks obrigatorios executados e validados.
- Riscos residuais: monitoramento pos-release por 30 min.
