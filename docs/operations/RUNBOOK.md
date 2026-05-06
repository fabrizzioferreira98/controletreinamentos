# Runbook Operacional

## 0) Fonte canonica

A lista oficial de tarefas, comandos e caminhos fica em `docs\operations\canonical-commands.md`. A separacao entre bootstrap estrutural, corretivas, seed/import historico, sync operacional e compat historica fica em `docs\operations\DATABASE_EVOLUTION.md`.

Use `ops\windows\scripts\Invoke-AppService.ps1` para subida operacional Windows/self-hosted, `backend\tools\maintenance\...` para manutencao da aplicacao, `frontend\scripts\build_frontend.py` para build do frontend e `ops\scripts\...` para release, smoke, drills e evidencias operacionais. Caminhos em `scripts\` sao aliases historicos de compatibilidade enquanto consumidores antigos migram.

Para release management, a trilha oficial agora fica em `docs\operations\RELEASE_MANAGEMENT.md`, `docs\operations\RELEASE_EXECUTION_CHECKLIST.md`, `docs\operations\ROLLBACK_CHECKLIST.md` e `docs\operations\POST_RELEASE_VALIDATION.md`.

Bootstrap estrutural de banco e consistencia/reparo seguem trilhas diferentes:
1. `backend\tools\maintenance\bootstrap_db_schema.py` sobe apenas schema e indices canonicos.
2. `backend\tools\maintenance\run_db_consistency.py` valida schema e dados.
3. `backend\tools\manual_unsafe\run_db_repair.py` fica restrito a reparo manual/perigoso; nao substitui bootstrap estrutural, nao roda em gate e nao roda agendado.
4. `backend\tools\manual_unsafe\cleanup_operational_data.py` e `backend\tools\compat_residual\sync_tripulantes_snapshot.py` ficam fora da trilha canonica; sobrevivem apenas por excecao controlada.

`sistema_controle` fica congelado como superficie residual. Novos usos genericos de cache/controle/estado operacional nao entram na trilha normal.

## 0.1) Runbooks oficiais

| area | runbook/fonte viva | comando/trilha oficial | evidencia minima |
| --- | --- | --- | --- |
| Subir ambiente local | `docs\operations\LOCAL_RUNTIME.md` e `docs\operations\canonical-commands.md` | `backend\tools\runtime\run.py`, `bootstrap_db_schema.py`, `bootstrap_seed_data.py`, worker manual quando necessario | App responde, login real funciona, DB consistente e storage gravavel. |
| Subir app Windows/self-hosted | `docs\operations\WINDOWS_SELF_HOSTED_SERVER.md` | `ops\windows\scripts\Invoke-AppService.ps1` | Servico sobe, logs sem erro fatal, `GET /login` e smoke basico passam. |
| Validar ambiente | `docs\operations\ENVIRONMENT_PARITY.md`, `POST_RELEASE_VALIDATION.md` e `canonical-commands.md` | Smoke, consistencia de DB, login, storage, worker, frontend servido e metricas | Checklist externo com URL, ambiente, commit/release id e resultado dos checks. |
| Release | `docs\operations\RELEASE_MANAGEMENT.md`, `RELEASE_GATES.md`, `RELEASE_EXECUTION_CHECKLIST.md` | `ops\scripts\release\run_release_strict.py` | Manifest, checklist de regressao, checklist de release, gate PASS e smoke. |
| Rollback | `docs\operations\ROLLBACK_CHECKLIST.md` e `RELEASE_MANAGEMENT.md` | Plano de rollback do release + smoke antes/depois | Checklist de rollback preenchido, runtime ids e evidencias de smoke A/B/A. |
| Backup | `docs\operations\windows_backup_restore_rollback.md` e `canonical-commands.md` | `backend\tools\maintenance\run_backups.py` ou task Windows oficial | Dump, assets, config e manifest da mesma janela. |
| Restore | `docs\operations\windows_backup_restore_rollback.md` | `ops\scripts\backup\backup_restore_drill.py` + `backend\tools\maintenance\run_restore_postcheck.py` | Drill PASS, postcheck sem inconsistencia critica, smoke e contagens basicas. |
| Worker/jobs | `RUNBOOK.md`, `RELEASE_GATES.md` e `WINDOWS_SELF_HOSTED_SERVER.md` | `backend\tools\maintenance\run_jobs_worker.py`, Task Scheduler e `jobs_concurrency_drill.py` | Fila consome job, backlog/dead-letter controlados e drill salvo. |
| Monitoramento | `docs\operations\OBSERVABILITY.md` e `SLOS.md` | `/api/internal/metrics`, logs, `trace_request_errors.py` | Request/correlation id rastreavel, metricas acessiveis com token e incidente registrado quando houver. |
| Troubleshooting/incidentes | `RUNBOOK.md` e `OBSERVABILITY.md` | Tabelas de troubleshooting abaixo + diagnosticos em `ops\scripts\diagnostics` | Sintoma, impacto, request/correlation id, acao tomada e resultado. |
| Evidencia operacional | `RUNBOOK.md`, `RELEASE_EVIDENCE_TEMPLATE.json` e `RELEASE_GATES.md` | Manifest externo + artefatos externos por release/restore/incidente | Evidencia fora do repo, com hash/assinatura quando exigido pelo gate. |

Regra: runbook detalha contexto, mas comando oficial continua em `docs\operations\canonical-commands.md`. Se uma doc operacional precisar mudar um comando principal, atualize a tabela canonica no mesmo change.

## 0.2) Troubleshooting oficial curto

| problema | onde olhar | acao |
| --- | --- | --- |
| App nao sobe localmente | terminal de `backend\tools\runtime\run.py`, `.env`, `DATABASE_URL`, `SECRET_KEY`, `APP_ENV` | Corrigir env minimo, garantir PostgreSQL acessivel e subir pela entrada oficial local. |
| App Windows/self-hosted nao sobe | saida de `ops\windows\scripts\Invoke-AppService.ps1`, `C:\srv\controle-treinamentos\logs\`, `D:\srv-data\controle-treinamentos\<env>\logs\`, env file do ambiente | Validar `prod.env`/`hml.env`, `PG_BIN_DIR`, `DATABASE_URL`, permissao de storage e runner Waitress. |
| Erro 500 em API/tela | `request_id`, `correlation_id`, evento `http_request`, `/api/internal/errors/<request_id>` | Rastrear por request/correlation id; usar `ops\scripts\diagnostics\trace_request_errors.py --log-file <log.jsonl> --codes <request_id>`. |
| Logs parecem ausentes | `C:\srv\controle-treinamentos\logs\`, `D:\srv-data\controle-treinamentos\<env>\logs\`, stdout/stderr do servico ou terminal | Confirmar `APP_ENV`, paths de runtime, permissao de escrita e se a app esta rodando pelo wrapper oficial. |
| Sessao/login falha | `/login`, cookie `controle_treinamentos_session`, logs de auth, `SECRET_KEY`, `SESSION_COOKIE_*`, usuario admin/teste | Validar usuario, limpar cookies, conferir `SECRET_KEY` estavel e rodar login real; `healthz` nao valida sessao. |
| Storage/upload/PDF falha | `MEDIA_STORAGE_ROOT`, `APP_INSTANCE_PATH`, `/admin/monitoramento`, metricas `storage_*`, arquivos em uploads | Confirmar raiz gravavel e mesma raiz usada pela app; em restore, rodar `run_restore_postcheck.py`. |
| Documento/PDF abre errado ou some apos restore | `storage_ref`, tabelas de arquivos/anexos, uploads restaurado, `DOCUMENT_LAYER_POLICY.md`, `PDF_DOCUMENT_POLICY.md` | Confirmar metadata e blob na mesma janela; rodar postcheck e nao declarar restore canonico com metadata sem blob. |
| Jobs nao processam | `/admin/monitoramento`, tabela `background_jobs`, metricas `background_job_queue_backlog`, logs `background_job_*` | Subir `backend\tools\maintenance\run_jobs_worker.py`; verificar `queued`, `running`, `dead_letter` e `stale_running`. |
| Scheduler nao roda | Windows Task Scheduler, scripts `tasks\*.ps1`, `Install-WindowsScheduledTasks.ps1`, logs do host | Recriar tarefas com `ops\windows\scripts\Install-WindowsScheduledTasks.ps1`; no local dev executar rotinas manualmente. |
| Backup passa mas restore nao e confiavel | `BACKUP_DIR`, dump/assets/config/manifest, `backup_restore_drill.py`, `run_restore_postcheck.py` | Exigir artefatos da mesma janela, drill com `--restore-url` e postcheck metadata/blob antes de declarar restore canonico. |
| Backup falha no host | task Windows de backup, `BACKUP_DIR`, `PG_BIN_DIR`, permissao de escrita, logs do job | Corrigir binarios/paths/permissoes; repetir backup manual e registrar artefatos gerados ou falha. |
| Frontend abre mas navega errado | `frontend\dist`, origem HTTP que serve o build, `FRONTEND_LOCAL_ORIGIN`, `FRONTEND_ALLOWED_ORIGINS`, `FRONTEND_API_BASE_URL` | Rebuildar frontend, servir por HTTP externo e alinhar origins; `frontend\dist` sozinho nao roda o app. |
| Release state divergente | `release_manifest.json`, checklist preenchido, output de `run_release_strict.py`, logs com `release_id`, `APP_RELEASE_ID`/`CONTROL_TREINAMENTOS_RELEASE_ID` | Corrigir manifest/checklist/commit, validar rollback runtime ids e repetir gate strict. |
| Gate de release falha | saida do `run_release_strict.py`, manifest, checklist de regressao, hashes, assinatura, idade dos artefatos | Corrigir evidencia/checklist, regenerar hashes/assinatura quando aplicavel e repetir gate; nao promover com FAIL. |
| Incidente operacional em andamento | SLO afetado, request/correlation ids, logs, metricas, smoke, jobs, storage e release id ativo | Abrir pasta externa de incidente, salvar timeline/evidencias, mitigar, decidir rollback pelos criterios de `RELEASE_GATES.md`. |

## 0.3) Evidencia operacional

Evidencia operacional e artefato externo que prova execucao, decisao ou resultado. Ela nao deve ser salva na arvore viva do repo.

Raiz externa padrao:

```text
C:/srv-data/controle-treinamentos/<env>/evidence/
```

Estrutura recomendada:

| caso | onde salvar | exemplos |
| --- | --- | --- |
| Release | `C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/` | manifest, checklist de regressao, checklist de release, smoke, e2e, carga, jobs, alertas, rollback, metricas. |
| Restore ligado a release | `C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/backup/` ou `restore/` | `backup_restore_drill.json`, `restore_postcheck.json`, contagens, smoke final. |
| Restore standalone | `C:/srv-data/controle-treinamentos/<env>/evidence/restore_<YYYYMMDD_HHMMSS>/` | artefatos usados, drill, postcheck, decisao de continuidade. |
| Incidente | `C:/srv-data/controle-treinamentos/<env>/evidence/incidents/<incident_id>/` | timeline, request/correlation ids, traces, metricas, logs recortados, acao tomada. |
| Drill periodico | `C:/srv-data/controle-treinamentos/<env>/evidence/drills/<YYYYMMDD>_<tema>/` | jobs concurrency, backup/restore, alerta externo, rollback, carga. |

O que salvar:

| tipo | salvar | nao salvar |
| --- | --- | --- |
| Checklist | Copia preenchida de template vivo, com ambiente, release id, commit, responsavel e decisao. | Template vazio como se fosse evidencia. |
| Gate | Saida do comando, manifest validado, hashes/assinatura quando exigidos e status PASS/FAIL. | Print solto sem comando, release id ou commit. |
| Drill | JSON/log estruturado do ensaio, parametros nao secretos, resultado e data. | Segredo, senha, token ou dump sensivel dentro do repo. |
| Evidencia de release | `release_manifest.json`, checklist de regressao, checklists operacionais, smoke, e2e, carga, jobs, alertas, backup/restore, rollback e metricas. | Artefato de release salvo em `docs/`, `ops/` ou raiz do repo. |
| Evidencia de restore | Lista de dump/assets/config/manifest da mesma janela, output do drill, output do postcheck, contagens basicas e smoke final. | Dump isolado apresentado como restore canonico. |
| Evidencia de incidente | Sintoma, impacto, request/correlation id, logs relevantes, metricas, decisao, mitigacao e follow-up. | Logs completos com dados sensiveis sem recorte/minimizacao. |

Definicoes obrigatorias:

| termo | definicao | fonte/validador |
| --- | --- | --- |
| Checklist | Documento humano preenchido para confirmar passos, risco e decisao. | `RELEASE_EXECUTION_CHECKLIST.md`, `ROLLBACK_CHECKLIST.md`, `REGRESSION_AUDIT_CHECKLIST.md`. |
| Gate | Validador automatizado que retorna PASS/FAIL e bloqueia promocao quando falha. | `ops\scripts\release\run_release_strict.py`. |
| Drill | Ensaio operacional de uma capacidade critica sem depender de incidente real. | `jobs_concurrency_drill.py`, `backup_restore_drill.py`, `alerts_external_drill.py`. |
| Evidencia de release | Pacote externo por `release_id`, consumido pelo gate e manifestado em JSON. | `RELEASE_EVIDENCE_TEMPLATE.json`, `validate_operational_evidence.py`. |
| Evidencia de restore | Prova de continuidade: artefatos da mesma janela + restore/drill + postcheck + smoke. | `windows_backup_restore_rollback.md`, `run_restore_postcheck.py`. |
| Evidencia de incidente | Pacote externo com timeline, ids, metricas, logs recortados, decisao e resultado. | `OBSERVABILITY.md`, `SLOS.md`, este runbook. |

Regras:

- Evidencia viva nao entra em `docs/`, `ops/`, `tests/`, `frontend/`, `backend/` ou raiz do repo.
- Checklists em `docs/operations/` sao templates vivos; checklist preenchido vira evidencia externa.
- Manifest de release deve apontar para artefatos externos do mesmo `release_id`.
- Restore canonico exige dump, assets, config e manifest da mesma janela mais postcheck sem falha critica.
- Gate automatizado nao substitui checklist humano; checklist humano nao substitui gate automatizado.
- Drill prova ensaio; para promover release ou restore, o drill precisa estar ligado ao manifest/evidencia correta.
- Segredos, tokens, dumps sensiveis e logs brutos completos devem ficar fora do repo e ser minimizados antes de compartilhamento.

## 0.4) Falso verde operacional

| item | por que engana | correcao |
| --- | --- | --- |
| `backend\tools\runtime\run.py` sobe sem erro | Prova processo local, nao prova sessao, storage, worker, scheduler ou backup. | Rodar bootstrap completo, login real, worker e validacao de storage/jobs. |
| `GET /healthz` retorna 200 | Valida banco basico, nao valida autenticao, fila, storage, SMTP, backup ou release state. | Usar `GET /login`, metricas, monitoramento, worker e checks de backup/storage. |
| `frontend\scripts\build_frontend.py` passa | Prova build, nao prova frontend servido, login, CORS/origins ou navegacao. | Servir `frontend\dist` por HTTP externo e configurar `FRONTEND_*` antes de validar SPA. |
| `frontend\dist` existe | Pode ser build velho ou artefato local; nao e fonte viva. | Rebuildar pela trilha oficial e nao tratar `dist` como arquitetura. |
| `post_deploy_smoke.py` passa | Smoke prova URL/metrics basicos, nao worker, scheduler, storage nem restore. | Completar release gate, jobs, backup/restore drill e checks de storage. |
| `run_backups.py` retorna sucesso | Backup pontual nao prova restore canonico nem janela consistente de assets/config. | Rodar `backup_restore_drill.py` com `--restore-url` e `run_restore_postcheck.py`. |
| `run_notifications.py` retorna sucesso | Execucao pontual nao prova scheduler recorrente. | Validar Task Scheduler no Windows ou registrar execucao manual no local. |
| `scripts\*` funciona | Wrapper compat pode mascarar entrada oficial antiga. | Usar caminho canonico em `backend\tools`, `ops\windows` ou `ops\scripts` conforme a tarefa. |
| `ops\scripts\release\release_gate.py` parece gate | E motor/entrada direta deprecated; pode contornar wrapper strict. | Usar somente `ops\scripts\release\run_release_strict.py`. |
| `docs\archive\operations\RELEASE_GATE_MODEL.md` parece atual | Esta arquivado; nao define release vigente. | Usar `docs\operations\RELEASE_GATES.md` e `canonical-commands.md`. |
| `docs\migration\retired-platforms\DEPLOY_RENDER.md` parece deploy | Plataforma retirada; nao e operacao oficial. | Usar `docs\operations\WINDOWS_SELF_HOSTED_SERVER.md`. |
| `backend\src\controle_treinamentos\compat\http_entrypoints\*.py` responde | Compat HTTP residual pode parecer scheduler/runtime principal. | Usar Task Scheduler + `Invoke-OperationalPython.ps1` e app via `Invoke-AppService.ps1`. |
| `run_db_consistency.py --repair` resolve algo | Repair nao e consistencia canonica e nao entra em gate. | Consistencia oficial sem repair; reparo apenas em `manual_unsafe` com aceite explicito. |

## 1) Incidente de erro 500
1. Capturar `request_id` e `correlation_id` do cliente ou do payload JSON.
2. Buscar log `http_request` com mesmo `request_id`.
3. Consultar `/api/internal/errors/<request_id>` com token operacional quando precisar da evidencia persistida.
4. Seguir `correlation_id` para eventos de job, storage, PDF ou release no mesmo fluxo.
5. Avaliar impacto por endpoint/status.
6. Acionar rollback se taxa de 5xx acima do gate.

## 2) Fila de jobs degradada
1. Verificar tela de monitoramento e `dead_letter`.
2. Buscar `background_job_enqueued`, `background_job_started` e `background_job_failed` por `origin_request_id` ou `correlation_id`.
3. Reenfileirar jobs criticos via endpoint de requeue.
4. Confirmar worker ativo (`backend\tools\maintenance\run_jobs_worker.py`).
5. Validar se `stale_running` voltou a 0.

## 3) Backup/restore
1. Executar backup manual (`/backups/executar`).
2. Confirmar criacao de job e conclusao.
3. Validar artefato em storage/local.
4. Executar restore em ambiente de homologacao (procedimento controlado).

## 4) Pos-deploy
1. Rodar smoke: `.venv\Scripts\python.exe ops\scripts\smoke\post_deploy_smoke.py --base-url <URL>`
2. Validar metricas internas e logs.
3. Monitorar 30 minutos de estabilidade.
4. Registrar a execucao em `RELEASE_EXECUTION_CHECKLIST.md`.
5. Se houver falha estrutural, seguir `ROLLBACK_CHECKLIST.md`.

## 5) Drills obrigatorios por release
1. Jobs concorrentes com retry/dead-letter:
   - `.venv\Scripts\python.exe ops\scripts\jobs\jobs_concurrency_drill.py --output C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/jobs/jobs_concurrency_drill.json`
2. Alerta externo ponta a ponta:
   - `.venv\Scripts\python.exe ops\scripts\release\alerts_external_drill.py --webhook-url <WEBHOOK> > C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/alerts/alerts_external_drill.json`
3. Backup/restore:
   - `.venv\Scripts\python.exe ops\scripts\backup\backup_restore_drill.py --restore-url <URL_RESTORE> --restore-schema public > C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/backup/backup_restore_drill.json`
4. Consolidar manifest:
   - preencher `docs/operations/RELEASE_EVIDENCE_TEMPLATE.json` e salvar em `C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/release_manifest.json`
5. Validar promocao no gate strict oficial:
   - `.venv\Scripts\python.exe ops\scripts\release\run_release_strict.py --base-url <URL_ALVO> --evidence-manifest C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/release_manifest.json --regression-checklist C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/regression_audit_checklist.md`
