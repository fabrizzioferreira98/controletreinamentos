# Runbook Operacional

## 1) Incidente de erro 500
1. Capturar `request_id` do cliente.
2. Buscar log `http_request` com mesmo `request_id`.
3. Correlacionar com stacktrace no mesmo intervalo.
4. Avaliar impacto por endpoint/status.
5. Acionar rollback se taxa de 5xx acima do gate.

## 2) Fila de jobs degradada
1. Verificar tela de monitoramento e `dead_letter`.
2. Reenfileirar jobs críticos via endpoint de requeue.
3. Confirmar worker ativo (`backend/tools/maintenance/run_jobs_worker.py`).
4. Validar se `stale_running` voltou a 0.

## 3) Backup/restore
1. Executar backup manual (`/backups/executar`).
2. Confirmar criação de job e conclusão.
3. Validar artefato em storage/local.
4. Executar restore em ambiente de homologação (procedimento controlado).

## 4) Pós-deploy
1. Rodar smoke: `python ops/scripts/smoke/post_deploy_smoke.py --base-url <URL>`
2. Validar métricas internas e logs.
3. Monitorar 30 minutos de estabilidade.

## 5) Drills obrigatórios por release
1. Jobs concorrentes com retry/dead-letter:
   - `python ops/scripts/jobs/jobs_concurrency_drill.py --output C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/jobs/jobs_concurrency_drill.json`
2. Alerta externo ponta a ponta:
   - `python ops/scripts/release/alerts_external_drill.py --webhook-url <WEBHOOK> > C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/alerts/alerts_external_drill.json`
3. Backup/restore:
   - `python ops/scripts/backup/backup_restore_drill.py --restore-url <URL_RESTORE> --restore-schema public > C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/backup/backup_restore_drill.json`
4. Consolidar manifest:
   - preencher `docs/operations/RELEASE_EVIDENCE_TEMPLATE.json` e salvar em `C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/release_manifest.json`
5. Validar promoção no gate strict oficial:
   - `python ops/scripts/release/run_release_strict.py --base-url <URL_ALVO> --evidence-manifest C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/release_manifest.json --regression-checklist docs/operations/REGRESSION_AUDIT_CHECKLIST.md`
