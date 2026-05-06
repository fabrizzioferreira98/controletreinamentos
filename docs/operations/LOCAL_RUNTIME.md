# Runtime Local

## Objetivo

Congelar a trilha local que realmente sobe o sistema sem adivinhacao. Este documento separa:

- runtime local canonico de desenvolvimento;
- operacao Windows/self-hosted;
- caminhos concorrentes que ainda sobrevivem por compatibilidade.

Fonte curta de comandos por tarefa: `docs/operations/canonical-commands.md`.
Paridade minima entre local, homolog e producao: `docs/operations/ENVIRONMENT_PARITY.md`.

## Entry points reais de runtime local

| superficie | entrypoint real hoje | observacao operacional |
| --- | --- | --- |
| backend local | `backend/tools/runtime/run.py` | entrada real de desenvolvimento; sobe Flask builtin em `PORT` |
| backend operacional Windows | `ops/windows/scripts/Invoke-AppService.ps1` -> `ops/windows/scripts/run_waitress_server.py` | trilha self-hosted com Waitress |
| banco | PostgreSQL acessado por `DATABASE_URL` | obrigatorio para fluxo real; `healthz` so prova query `SELECT 1` |
| storage | filesystem local resolvido por `MEDIA_STORAGE_ROOT` ou `APP_INSTANCE_PATH/uploads` | se nao configurar, cai em runtime local/temp |
| worker | `backend/tools/maintenance/run_jobs_worker.py` | obrigatorio para jobs sairem de `queued/running` |
| cron/scheduler equivalente | Windows Task Scheduler + `ops/windows/scripts/Invoke-OperationalPython.ps1` na operacao oficial | no local dev nao existe daemon canonico consolidado; execucao manual continua necessaria |
| backup manual | `backend/tools/maintenance/run_backups.py` | sem worker nao cobre fluxo enfileirado pela UI |
| notificacoes manuais | `backend/tools/maintenance/run_notifications.py` | valida provider/recipients; nao substitui scheduler oficial |
| bootstrap estrutural | `backend/tools/maintenance/bootstrap_db_schema.py` | cria schema/indices previsiveis, sem massa minima |
| seed minima | `backend/tools/maintenance/bootstrap_seed_data.py` | aplica bases/defaults; admin depende de `BOOTSTRAP_ADMIN_*` ou `ops/scripts/admin/ensure_admin_user.py` |
| frontend build | `frontend/scripts/build_frontend.py` | gera `frontend/dist`; nao sobe servidor estatico |
| smoke pos-deploy | `ops/scripts/smoke/post_deploy_smoke.py` | prova URL/alive, nao prova worker/cron/storage real |

## Env files e variaveis obrigatorias

Arquivos vivos:

- `.env.example`: base local;
- `frontend/.env.example`: build do frontend;
- `ops/windows/env/prod.env.example` e `ops/windows/env/hml.env.example`: self-hosted.

Minimo obrigatorio para local real:

- `SECRET_KEY`
- `DATABASE_URL`
- `APP_ENV`
- `PORT`

Obrigatorio para verdade operacional, dependendo do fluxo:

- `WORKSPACE_RUNTIME_ROOT` e `APP_INSTANCE_PATH` quando quiser reproduzir runtime/storage fora do temp local
- `WORKSPACE_LOCAL_BACKUPS_ROOT` ou `BACKUP_DIR` quando quiser validar backup sem cair em caminho improvisado
- `MEDIA_STORAGE_ROOT` ou `APP_INSTANCE_PATH`
- `METRICS_TOKEN` para validar endpoint de metricas com o mesmo contrato de homolog/producao
- `SMTP_*` ou `RESEND_*` para notificacoes reais
- `CRON_SECRET` apenas quando usar entrada HTTP de cron compat
- `FRONTEND_LOCAL_ORIGIN` e `FRONTEND_ALLOWED_ORIGINS` somente se existir frontend estatico real em outra origem

## Scripts, wrappers e caminhos concorrentes ainda vivos

| caminho | classificacao | motivo |
| --- | --- | --- |
| `backend/tools/runtime/run.py` | canonico | unica entrada local simples e direta do backend |
| `ops/windows/scripts/Invoke-AppService.ps1` | canonico | subida operacional Windows/self-hosted |
| `ops/windows/scripts/Invoke-OperationalPython.ps1` | wrapper fino aceitavel | injeta env e delega para comandos oficiais |
| `backend/tools/maintenance/*.py` | canonico | manutencao recorrente oficial |
| `ops/scripts/jobs/*.py`, `ops/scripts/backup/*.py`, `ops/scripts/database/run_db_consistency.py` | compat residual | implementacao real ainda existe, mas a entrada oficial foi rebaixada |
| `scripts/*` | compat residual | shim fino para consumidores antigos |
| `backend/tools/manual_unsafe/*` | legado perigoso | repair/cleanup fora da trilha normal |
| `backend/src/controle_treinamentos/compat/http_entrypoints/*.py` | aposentavel depois | superficie HTTP residual de cron/index para compatibilidade |
| `flask run` | redundante | nao fecha bootstrap real local nem representa trilha Windows oficial |
| `Makefile dev` | wrapper residual | delega para `backend/tools/runtime/run.py`, mas nao substitui o comando oficial documentado |

## Bootstrap local oficial

### Mapa por componente

| componente | comando/trilha | observacao |
| --- | --- | --- |
| envs | `.env` derivado de `.env.example` | minimo local: `SECRET_KEY`, `DATABASE_URL`, `APP_ENV`, `PORT`; mantenha `FRONTEND_*` vazio se nao houver frontend estatico servido |
| banco | PostgreSQL real em `DATABASE_URL` | o repo nao provisiona o servidor; `bootstrap_db_schema.py` apenas cria/ajusta schema e indices |
| storage | `MEDIA_STORAGE_ROOT` ou `APP_INSTANCE_PATH` | use caminho gravavel explicito; sem isso o runtime pode cair em temp/local e gerar falso verde |
| backend | `.venv\Scripts\python.exe backend\tools\runtime\run.py` | entrada local real; sobe Flask builtin em `PORT` |
| frontend | `.venv\Scripts\python.exe frontend\scripts\build_frontend.py --env-file frontend\.env.example` | gera `frontend/dist`; para usar SPA separado, sirva esse diretorio por servidor HTTP externo |
| worker | `.venv\Scripts\python.exe backend\tools\maintenance\run_jobs_worker.py` | necessario para consumir `background_jobs` |
| scheduler local | execucao manual de `run_notifications.py`, `run_backups.py` e `run_db_consistency.py` | nao existe daemon local canonico consolidado |
| scheduler Windows | Task Scheduler chamando `ops/windows/scripts/Invoke-OperationalPython.ps1` | trilha oficial para recorrencia em self-hosted |
| massa minima | `bootstrap_seed_data.py` + admin por `BOOTSTRAP_ADMIN_*` ou `ensure_admin_user.py` | seed cria defaults; usuario autenticavel precisa existir |

### Comando oficial para subir o sistema localmente

A trilha canonica local, hoje, e hibrida/compat no backend. Ela nao pressupoe frontend SPA separado.

1. Preparar `.env` a partir de `.env.example`, mantendo `FRONTEND_PUBLIC_ORIGIN`, `FRONTEND_LOCAL_ORIGIN` e `FRONTEND_ALLOWED_ORIGINS` vazios se nao houver frontend estatico servido.
2. Garantir PostgreSQL acessivel no `DATABASE_URL`.
3. Definir storage gravavel com `MEDIA_STORAGE_ROOT` ou `APP_INSTANCE_PATH`. Para validar backup local, definir tambem `WORKSPACE_LOCAL_BACKUPS_ROOT` ou `BACKUP_DIR`.
4. Executar bootstrap estrutural:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\bootstrap_db_schema.py
```

5. Executar seed minima:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\bootstrap_seed_data.py
```

6. Criar usuario administrativo real do ambiente se `BOOTSTRAP_ADMIN_*` nao estiver definido:

```powershell
.venv\Scripts\python.exe ops\scripts\admin\ensure_admin_user.py --login admin_local --password <senha-forte> --email admin@local
```

7. Subir backend local:

```powershell
.venv\Scripts\python.exe backend\tools\runtime\run.py
```

8. Em outro terminal, subir worker:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\run_jobs_worker.py
```

9. Se precisar simular rotinas recorrentes localmente, executar manualmente:

```powershell
.venv\Scripts\python.exe backend\tools\maintenance\run_notifications.py
.venv\Scripts\python.exe backend\tools\maintenance\run_backups.py
.venv\Scripts\python.exe backend\tools\maintenance\run_db_consistency.py
```

10. Se precisar validar o frontend separado, buildar `frontend/dist` e servir por HTTP externo:

```powershell
.venv\Scripts\python.exe frontend\scripts\build_frontend.py --env-file frontend\.env.example
```

### Ordem obrigatoria

1. banco;
2. schema;
3. seed minima;
4. usuario administrativo;
5. backend;
6. worker;
7. rotinas manuais ou scheduler externo, quando o fluxo testado depender delas;
8. frontend estatico separado apenas quando houver servidor HTTP real para `frontend/dist`.

### Dependencias obrigatorias

- PostgreSQL real;
- filesystem gravavel para runtime/storage;
- worker ativo para fluxos assincronos;
- pelo menos um usuario autenticavel.

### Dependencias que podem ser fake no local

- SMTP/Resend, desde que voce nao use notificacoes como evidencia de sucesso;
- scheduler/cron continuo, desde que voce execute manualmente os comandos de notificacao/backup e deixe isso explicito;
- frontend SPA separado, porque hoje ele ainda nao tem servidor local consolidado no repo.

### Massa minima obrigatoria

- bases/defaults operacionais vindos de `bootstrap_seed_data.py`;
- um admin local;
- diretorio de storage resolvido e gravavel;
- tabelas de jobs existentes no banco.

## Frontend SPA separado no local

O frontend separado existe como build, nao como bootstrap local consolidado. Hoje ele exige improviso controlado:

1. buildar `frontend/dist`;
2. servir `frontend/dist` por um servidor HTTP externo;
3. apontar backend para `FRONTEND_LOCAL_ORIGIN=<origem-estatica>`;
4. ajustar `FRONTEND_ALLOWED_ORIGINS` e `FRONTEND_API_BASE_URL`.

Sem isso, o frontend separado **nao** e a trilha local canonica.

## Falso verde local identificado

- `.env.example` apontando `FRONTEND_LOCAL_ORIGIN` para a mesma origem do backend fazia `/` e `/login` redirecionarem para si mesmos quando nao havia frontend estatico servido.
- `bootstrap_db_schema.py` deixa o banco estruturalmente pronto, mas nao cria massa minima; schema consistente nao significa sistema utilizavel.
- `healthz` so valida banco basico; nao prova worker, storage, SMTP, backups nem fila.
- `post_deploy_smoke.py` aceita redirects/metrics, mas nao confirma processamento assincrono nem paridade de frontend local.
- o backend pode subir com `DATABASE_URL` ausente fora de ambiente seguro; isso nao significa fluxo autenticado funcional.
- `run_notifications.py` e `run_backups.py` manuais nao provam scheduler recorrente; apenas prova execucao pontual.
- storage sem `MEDIA_STORAGE_ROOT` cai para runtime local/temp e mascara ausencia de paridade com o host operacional.
- frontend buildado sem servidor HTTP real continua sem autenticar/circular corretamente; `frontend/dist` por si so nao fecha o runtime.

## Validacao local minima

1. `bootstrap_db_schema.py` retorna `0`.
2. `bootstrap_seed_data.py` retorna `0`.
3. `GET /login` responde `200` HTML, nao loop de redirect.
4. `GET /healthz` responde `200` com banco `ok`.
5. login com usuario local funciona.
6. acao que enfileira job cria linha em `background_jobs`.
7. `run_jobs_worker.py` consome ao menos um job `queued`.
8. upload/anexo grava em raiz de storage explicita esperada, nao em caminho improvisado.

## Limitacoes conhecidas

- nao existe servidor local do frontend SPA consolidado no repo;
- nao existe scheduler local unico e oficial fora da operacao Windows/Task Scheduler;
- o runtime local canonico atual e hibrido/compat, nao paridade completa com o frontend separado de producao;
- smoke pos-deploy continua util para deploy, mas insuficiente como prova de runtime local real.
