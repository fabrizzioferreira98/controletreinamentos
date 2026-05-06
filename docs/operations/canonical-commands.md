# Comandos Oficiais por Tarefa

## Objetivo

Registrar a entrada oficial para cada tarefa operacional critica. Esta e a fonte curta para escolher comando; runbooks podem detalhar contexto, mas nao devem definir outro caminho oficial para a mesma tarefa.

Regra de execucao local: os exemplos abaixo usam `.venv\Scripts\python.exe` como conveniencia de Windows no workspace, mas a autoridade canonica e o entrypoint da terceira coluna. Um interpretador Python equivalente, com as dependencias corretas, pode chamar os mesmos scripts sem mudar a politica oficial do repo.

Regra de build frontend: `frontend\dist` e apenas a saida gerada/publicavel do build. Pode existir localmente no caminho canonico apos executar `frontend\scripts\build_frontend.py`, mas nao e fonte viva nem criterio arquitetural.

## Tabela oficial

| tarefa | comando oficial | caminho oficial | observacao |
| --- | --- | --- | --- |
| subir backend local | `.venv\Scripts\python.exe backend\tools\runtime\run.py` | `backend\tools\runtime\run.py` | trilha local hibrida/compat; use com `FRONTEND_*` vazios ou com frontend estatico real separado |
| subir app | `powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Invoke-AppService.ps1 -EnvironmentName <env> -EnvFile <env-file>` | `ops\windows\scripts\Invoke-AppService.ps1` | subida operacional Windows/self-hosted |
| build frontend | `.venv\Scripts\python.exe frontend\scripts\build_frontend.py --env-file frontend\.env.example` | `frontend\scripts\build_frontend.py` | executar da raiz |
| rodar frontend separado local | `.venv\Scripts\python.exe frontend\scripts\build_frontend.py --env-file frontend\.env.example` | `frontend\scripts\build_frontend.py` | gera `frontend\dist`; para rodar, sirva `frontend\dist` por HTTP externo e configure `FRONTEND_*`; nao ha dev server canonico no repo |
| validacao minima de CI/build | `.venv\Scripts\python.exe ops\scripts\release\run_ci_validation_minimal.py` | `ops\scripts\release\run_ci_validation_minimal.py` | build frontend fora do checkout + suites minimas de governanca/pipeline; nao substitui o release gate |
| testes minimos locais | `.venv\Scripts\python.exe ops\scripts\release\run_ci_validation_minimal.py` | `ops\scripts\release\run_ci_validation_minimal.py` | usa a mesma trilha minima oficial de CI/build; para escopo maior, use suites especificas de `tests/` |
| rodar smoke | `.venv\Scripts\python.exe ops\scripts\smoke\post_deploy_smoke.py --base-url <URL>` | `ops\scripts\smoke\post_deploy_smoke.py` | smoke pos-deploy |
| release gate | `.venv\Scripts\python.exe ops\scripts\release\run_release_strict.py --base-url <URL> --evidence-manifest <manifest> --regression-checklist <checklist-preenchido>` | `ops\scripts\release\run_release_strict.py` | use `docs\operations\REGRESSION_AUDIT_CHECKLIST.md` como template vivo |
| backup | `.venv\Scripts\python.exe backend\tools\maintenance\run_backups.py` | `backend\tools\maintenance\run_backups.py` | backup recorrente/manual |
| backup/restore drill | `.venv\Scripts\python.exe ops\scripts\backup\backup_restore_drill.py --restore-url <URL_RESTORE> --restore-schema public --extract-archives` | `ops\scripts\backup\backup_restore_drill.py` | checa pacote minimo e restore real quando `--restore-url` e informado |
| restore postcheck | `.venv\Scripts\python.exe backend\tools\maintenance\run_restore_postcheck.py --json --media-root <uploads-restaurado> --artifact <dump> --artifact <assets> --artifact <config> --artifact <manifest>` | `backend\tools\maintenance\run_restore_postcheck.py` | valida metadata/blob apos restore; necessario para declarar restore canonico |
| worker | `.venv\Scripts\python.exe backend\tools\maintenance\run_jobs_worker.py` | `backend\tools\maintenance\run_jobs_worker.py` | worker de jobs |
| notificacoes manuais | `.venv\Scripts\python.exe backend\tools\maintenance\run_notifications.py` | `backend\tools\maintenance\run_notifications.py` | execucao pontual; nao substitui scheduler recorrente |
| scheduler Windows/self-hosted | `powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\windows\scripts\Install-WindowsScheduledTasks.ps1 -RootDir <srv-root>` | `ops\windows\scripts\Install-WindowsScheduledTasks.ps1` | registra tarefas recorrentes; executar como Administrador no host |
| bootstrap estrutural de banco | `.venv\Scripts\python.exe backend\tools\maintenance\bootstrap_db_schema.py` | `backend\tools\maintenance\bootstrap_db_schema.py` | sobe apenas schema e indices canonicamente previsiveis |
| seed minima de runtime local | `.venv\Scripts\python.exe backend\tools\maintenance\bootstrap_seed_data.py` | `backend\tools\maintenance\bootstrap_seed_data.py` | aplica bases/defaults; admin depende de `BOOTSTRAP_ADMIN_*` ou `ops\scripts\admin\ensure_admin_user.py` |
| consistencia de banco | `.venv\Scripts\python.exe backend\tools\maintenance\run_db_consistency.py` | `backend\tools\maintenance\run_db_consistency.py` | valida schema + dados; nao aceita repair na trilha canonica |
| repair manual de banco historico | `.venv\Scripts\python.exe backend\tools\manual_unsafe\run_db_repair.py` | `backend\tools\manual_unsafe\run_db_repair.py` | executa bootstrap estrutural + migrations corretivas; nao roda seed/import/sync historico |
| saneamento de usuarios de teste | `.venv\Scripts\python.exe ops\scripts\admin\sanitize_test_users.py --json` | `ops\scripts\admin\sanitize_test_users.py` | inventario primeiro; para aplicar, use `--apply --keep-login $env:E2E_LOGIN --json` |

## Compat e legado

- `scripts\` contem wrappers historicos de compatibilidade. Nao e trilha oficial para novos fluxos.
- `backend\tools\runtime\run.py` e entrada local de desenvolvimento; nao compete com a subida operacional Windows/self-hosted.
- `backend\tools\runtime\wsgi.py` e auxiliar WSGI/importavel para runtime ou hospedagem; nao e comando principal de desenvolvimento e nao substitui `run.py` nem `Invoke-AppService.ps1`.
- `flask run` sobrevive apenas como conveniencia residual historica e nao fecha o bootstrap local real.
- `make dev` sobrevive como wrapper fino para `backend\tools\runtime\run.py`; nao substitui o comando oficial documentado.
- `ops\scripts\release\release_gate.py` e motor/entrada direta redundante do gate. O comando oficial de release e `run_release_strict.py`.
- `Makefile release-gate-strict` sobrevive como wrapper fino aceitavel para quem ja injeta `BASE_URL`, `EVIDENCE_MANIFEST` e `REGRESSION_CHECKLIST`; nao substitui o comando oficial nem os workflows de CI/release.
- `ops\scripts\backup`, `ops\scripts\jobs` e `ops\scripts\database` contem implementacoes reais; para bootstrap estrutural, backup, worker, notificacoes e consistencia, a entrada oficial e `backend\tools\maintenance`. Entradas diretas nesses `run_*.py` sao despriorizadas e devem apontar para a entrada canonica.
- `sync_tripulantes_snapshot.py` sobrevive apenas como compat residual via `backend\tools\compat_residual\sync_tripulantes_snapshot.py`; nao e trilha normal.
- `cleanup_operational_data.py` e `run_db_repair.py` sobrevivem apenas em `backend\tools\manual_unsafe\`; nao sao bootstrap, nao sao migracao estrutural e nao entram em rotina recorrente.
- em consistencia canonica, use `--repair` apenas como reparo manual na trilha `backend\tools\manual_unsafe\run_db_repair.py`.
- `training_program_seed.py`, `import_tripulantes_csv.py` e `sync_training_master_types.py` ficam fora do bootstrap: seed/import historico e sync operacional estao classificados em `docs\operations\DATABASE_EVOLUTION.md`.
- `sistema_controle` fica congelado como superficie residual: notificacoes historicas e cache legado ja existente. Nao e ponto aberto para novo estado generico.

## Runtime local

Bootstrap local oficial, falso verde conhecido, dependencias minimas e ordem de subida ficam em `docs/operations/LOCAL_RUNTIME.md`.

Evolucao de banco, classificacao entre schema/corretiva/seed/import/sync e itens congelados ficam em `docs/operations/DATABASE_EVOLUTION.md`.

Pipeline minima de CI/build/release e classificacao dos gates ficam em `docs/operations/CI_RELEASE_PIPELINE.md`.

## Validacao operacional minima

Um comando que retorna `0` nao prova operacao completa sozinho. Para considerar a trilha principal saudavel, valide pelo menos:

| superficie | validacao minima |
| --- | --- |
| app/backend | processo subiu pela entrada oficial e `GET /login` responde sem loop |
| banco | `bootstrap_db_schema.py` e `run_db_consistency.py` passam sem repair |
| sessao | login/logout com usuario canonico funciona e cookie de sessao e emitido |
| storage | upload/anexo grava no `MEDIA_STORAGE_ROOT` ou `APP_INSTANCE_PATH` esperado |
| jobs | worker consome ao menos um job `queued`; backlog/dead-letter nao cresce |
| frontend separado | `frontend/dist` foi rebuildado e servido por HTTP externo configurado em `FRONTEND_*` |
| smoke | `post_deploy_smoke.py` passa, mas nao substitui checks de worker, storage e backup |
| backup/restore | backup gera dump/assets/config/manifest da mesma janela e drill/postcheck passam |
| release state | manifest, checklist e logs carregam o mesmo `release_id`/commit; gate strict retorna PASS |
