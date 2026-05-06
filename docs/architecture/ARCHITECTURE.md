# Arquitetura do Sistema

Esta e a fonte viva curta da arquitetura. Ela descreve a estrutura real atual do produto, nao uma arvore desejada futura.

## 1. VISAO DO SISTEMA

O sistema e uma aplicacao web interna para controle de tripulantes, treinamentos, bases, operacoes, relatorios, arquivos, jobs, backup e release operacional.

Modelo oficial atual:

| camada | papel real | caminho principal |
| --- | --- | --- |
| Backend | Monolito Flask com app factory, sessoes, rotas HTML/JSON, dominio, repositorios e infra local. | `backend/src/controle_treinamentos/` |
| Frontend | Frontend estatico separado, buildado no repo e servido fora do backend em operacao Windows/self-hosted, com compat backend/static isolado em adapters nomeados. | `frontend/src/`, `frontend/src/compat/`, `frontend/scripts/build_frontend.py` |
| Banco | PostgreSQL nativo/local ou rede interna, com bootstrap idempotente e consistencia operacional. | `backend/src/controle_treinamentos/db/`, `backend/tools/maintenance/bootstrap_db_schema.py` |
| Storage | Filesystem local para fotos, anexos, documentos e artefatos restaurados. | `backend/src/controle_treinamentos/infra/media_storage.py`, `document_blobs.py` |
| Jobs | Fila persistida em banco, worker local e tarefas recorrentes via host Windows. | `backend/src/controle_treinamentos/infra/jobs.py`, `backend/tools/maintenance/run_jobs_worker.py` |
| Operacao | Scripts de release, smoke, backup/restore, diagnostico, QA, Windows e hygiene. | `ops/scripts/`, `ops/windows/scripts/` |
| Docs | Fontes vivas por assunto: arquitetura, operacao, governanca e produto. | `docs/architecture/`, `docs/operations/`, `docs/governance/`, `docs/product/` |
| Tests | Validacao por camada: unit, integration, contract, e2e, ops e architecture. | `tests/` |

Entrypoints reais:

| tarefa | entrypoint oficial | observacao |
| --- | --- | --- |
| Backend local | `backend/tools/runtime/run.py` | Desenvolvimento local. |
| WSGI/export auxiliar | `backend/tools/runtime/wsgi.py` | Usado por runtime/servico quando aplicavel. |
| App Windows/self-hosted | `ops/windows/scripts/Invoke-AppService.ps1` | Subida operacional com Waitress. |
| Frontend build | `frontend/scripts/build_frontend.py` | Gera `frontend/dist`; `dist` nao e fonte viva. |
| Worker | `backend/tools/maintenance/run_jobs_worker.py` | Consome fila de jobs. |
| Scheduler Windows | `ops/windows/scripts/Install-WindowsScheduledTasks.ps1` | Registra tarefas recorrentes no host. |
| Backup | `backend/tools/maintenance/run_backups.py` | Entrada canonica de backup. |
| Restore postcheck | `backend/tools/maintenance/run_restore_postcheck.py` | Valida metadata/blobs apos restore. |
| Backup/restore drill | `ops/scripts/backup/backup_restore_drill.py` | Ensaio operacional de pacote e restore. |
| Smoke | `ops/scripts/smoke/post_deploy_smoke.py` | Smoke pos-deploy. |
| Release gate | `ops/scripts/release/run_release_strict.py` | Gate estrito oficial. |
| CI/build minimo | `ops/scripts/release/run_ci_validation_minimal.py` | Trilha minima de validacao local/CI. |

Modulos principais:

| modulo | papel | fronteira |
| --- | --- | --- |
| `blueprints/` | Rotas Flask, HTML/SSR e endpoints JSON atrelados ao Flask. | Pode importar Flask; nao deve concentrar regra de negocio extensa. |
| `api/http/` | Rotas/programmatic APIs JSON por dominio. | Deve respeitar `core/http_contract.py`. |
| `application/` | Casos de uso e coordenacao de dominio. | Nao e camada HTTP. |
| `service_layers/` | Regras puras, validacoes e montagem de formularios. | Nao deve importar Flask. |
| `repositories/` | Acesso a dados e queries. | Nao deve conter regra HTTP ou renderizacao. |
| `contracts/` | Contratos de payload/semantica por dominio. | Apoia testes de contrato e fronteiras publicas. |
| `infra/` | Jobs, backup, mailer, storage e restore. | Infra viva chamada pelo backend/tools e ops. |
| `monitoring/` | Metricas, snapshots e observabilidade interna. | Suporta `/api/internal/metrics` e runbooks. |
| `reports/` | Geracao de relatorios/PDFs. | Isola processamento pesado de documentos. |
| `backend/tools/` | Entrypoints locais, manutencao, import manual, compat residual e acoes perigosas. | Operacional, mesmo estando dentro de `backend/`. |
| `ops/` | Operacao transversal: Windows, release, smoke, backup drills, diagnostics, QA e repo hygiene. | Nao e source de produto. |

Fronteiras reais:

- HTTP Flask fica em `blueprints/` e `api/http/`.
- Regra de dominio fica em `application/` e `service_layers/`.
- Banco fica em `db/` e `repositories/`.
- Infra local fica em `infra/` e nos entrypoints de `backend/tools/maintenance/`.
- Operacao transversal fica em `ops/`; comando principal novo nao nasce em `scripts/`.
- Frontend fonte fica em `frontend/src/`; `frontend/dist/` e build gerado.
- Documentacao viva fica em `docs/architecture`, `docs/operations`, `docs/governance` e `docs/product`.
- Testes ficam em `tests/<camada>`; teste de compat precisa nomear o compat e ter condicao de saida.

Compat residual relevante:

| item | papel real | nao e |
| --- | --- | --- |
| `scripts/*` | Wrappers historicos finos para consumidores antigos. | Entrada oficial nova. |
| `backend/src/controle_treinamentos/compat/http_entrypoints/` | Entry points HTTP antigos preservados temporariamente. | Runtime/scheduler principal. |
| `backend/src/controle_treinamentos/compat/python_reexports/` | Reexports para imports antigos. | Lugar para regra nova. |
| `backend/tools/compat_residual/sync_tripulantes_snapshot.py` | Snapshot residual controlado. | Job canonico. |
| `tripulantes.status` e `tripulantes.base` | Espelho/snapshot residual para compatibilidade e bootstrap. | Owner de status/base operacional. |
| `backend/src/controle_treinamentos/service_layers/domain_validation.py` | Superficie antiga de import ainda protegida por compat. | Owner canonico de validacao nova. |
| Rotas/templates SSR legados | Fluxo ainda vivo enquanto houver consumidor/teste. | Segunda arquitetura de frontend. |
| Aba File legada de tripulante | Compat de jornada antiga de arquivos. | Modelo futuro de arquivos. |

## 2. MAPA POR DOMINIO

| dominio | papel | backend vivo | frontend/API | ops/docs/tests |
| --- | --- | --- | --- | --- |
| auth | Login, sessao, permissoes, usuarios e semantica de erro sem sessao. | `blueprints/auth/routes.py`, `auth.py`, `repositories/user_repository.py`, `core/auth_contract.py`, `core/security.py`. | `/login`, APIs de sessao, contratos em `tests/contract/test_api_session_contract.py` e matriz auth. | `ops/scripts/admin/ensure_admin_user.py`, `sanitize_test_users.py`, `docs/operations/AUTH_TEST_USERS.md`. |
| tripulantes | Cadastro, status operacional, midia, arquivos do tripulante e dashboard. | `blueprints/cadastros/*`, `application/tripulantes.py`, `tripulante_media.py`, `repositories/tripulantes.py`, `tripulante_files.py`, `service_layers/tripulante_*`. | `api/http/cadastros/routes.py`, `contracts/tripulantes.py`, `contracts/tripulante_media.py`, `frontend/src/pages-dashboard-tripulantes.js`. | Contratos tripulantes/media, e2e File legacy, docs de storage/upload. |
| treinamentos | Treinamentos, programas de treinamento, periodicidade, completude e modelos de aeronave. | `blueprints/cadastros/routes_treinamentos.py`, `application/treinamentos.py`, `training_program.py`, `repositories/treinamentos.py`, `training_program.py`, `training_aircraft_model.py`. | `api/http/cadastros/routes_training_program.py`, `contracts/treinamentos.py`, `contracts/training_program.py`, `frontend/src/pages-treinamentos-relatorios.js` como wrapper e owners em `frontend/src/features/treinamentos/` + `frontend/src/features/training-root/`; `frontend/src/pages-training-workspace.js` foi removido como artefato nao roteado no bloco 95. | Testes de training program, completeness e contratos de treinamentos. |
| bases | Cadastro e APIs de bases operacionais. | `blueprints/bases/routes.py`, `repositories/bases.py`, `contracts/bases.py`, `bases.py`. | `/bases/api/` e `tests/contract/test_bases_api_contract.py`. | Bootstrap/seed minima e consistencia de banco. |
| operacoes | Pernoites e operacoes com UI/escrita SSR atual e leitura API canonica registrada. | `blueprints/operacoes/routes.py`, `api/http/operacoes/routes.py`, `application/operacoes.py`, `base_operations.py`, `repositories/operacoes.py`. | `contracts/operacoes.py`, `/api/v1/operacoes/pernoites*`, rotas SSR atuais, `tests/contract/test_operacoes_contract.py`. | Escrita SSR preservada ate cutover dedicado; schema historico removivel apenas por migracao separada. |
| relatorios | Relatorios, exportacoes e PDFs. | `blueprints/relatorios/*`, `api/http/relatorios/routes.py`, `application/relatorios.py`, `reports/_reports_impl.py`, `contracts/relatorios.py`. | `frontend/src/pages-treinamentos-relatorios.js` como wrapper e owners em `frontend/src/features/relatorios/`, contratos de relatorios e PDFs. | `docs/architecture/PDF_DOCUMENT_POLICY.md`, testes de contrato e PDF. |
| arquivos | Upload, acesso a arquivos, blobs, storage local, restauracao e politicas de PDF/documento. | `infra/media_storage.py`, `infra/document_blobs.py`, `infra/restore_validation.py`, `blueprints/cadastros/routes_file.py`, `repositories/tripulante_files.py`. | Rotas de arquivo de tripulante, contratos media/files legacy. | `docs/architecture/DOCUMENT_LAYER_POLICY.md`, `FILE_ACCESS_POLICY.md`, `UPLOAD_POLICY.md`, `backend/tools/maintenance/run_restore_postcheck.py`. |
| jobs | Fila persistida, worker, notificacoes e concorrencia. | `infra/jobs.py`, `jobs.py`, `backend/tools/maintenance/run_jobs_worker.py`, `run_notifications.py`. | Metricas internas e monitoramento de jobs. | `ops/scripts/jobs/*`, Task Scheduler Windows, testes `test_jobs_queue.py` e ops jobs. |
| backup | Backup, restore, drill e validacao de artefatos. | `infra/backup.py`, `backup.py`, `backend/tools/maintenance/run_backups.py`, `run_restore_postcheck.py`. | Sem UI principal; validacao operacional por scripts. | `ops/scripts/backup/*`, `docs/operations/windows_backup_restore_rollback.md`, testes de backup/restore. |
| release | Manifest, checklist, smoke, rollback metadata, evidencia e gates. | Runtime le release state/env quando aplicavel; app expoe metricas internas. | Smoke usa URL publica/base-url. | `ops/scripts/release/run_release_strict.py`, `run_ci_validation_minimal.py`, `ops/scripts/smoke/post_deploy_smoke.py`, `.github/workflows/*`, docs de release. |

## 3. MAPA DE OWNERS

Ownership aqui e papel de responsabilidade, nao pessoa nominal.

### Owners por dominio

| dominio | owner primario | owner secundario | obrigatorio ao mudar |
| --- | --- | --- | --- |
| auth | Owner backend/auth | Owner ops quando envolver usuarios, seed ou saneamento. | Contratos de sessao/auth, docs de usuarios de teste e runbook se mudar operacao. |
| tripulantes | Owner backend de cadastros/tripulantes | Owner arquivos quando envolver midia/storage. | Contratos de tripulantes/media, e2e de jornada critica e docs de storage quando aplicavel. |
| treinamentos | Owner backend de treinamentos | Owner frontend se mudar workspace/telas. | Contratos de treinamentos/training program e testes de regras de periodicidade/completude. |
| bases | Owner backend de bases | Owner bootstrap/seed se mudar dados default. | Contrato de bases e seed/bootstrap quando aplicavel. |
| operacoes | Owner backend de operacoes | Owner legacy quando envolver SSR compat. | Contratos de operacoes e inventario legacy quando mudar superficie SSR. |
| relatorios | Owner backend de relatorios | Owner arquivos/PDF quando envolver documento. | Contratos de relatorios/PDF e politicas de PDF/documento. |
| arquivos | Owner storage/documentos | Owner backend de dominio consumidor. | Politicas de upload/acesso/storage, restore postcheck e testes de media/documentos. |
| jobs | Owner ops/jobs | Owner backend infra. | Worker, Task Scheduler, filas, metricas e testes de jobs. |
| backup | Owner ops/backup | Owner storage/DB. | Runbook backup/restore, drill, postcheck e testes de integridade. |
| release | Owner ops/release | Owner governanca quando gate/topologia mudar. | Release gates, checklist, smoke, evidence template e workflows. |

### Owners de campos operacionais

| campo operacional | owner canonico unico | residual permitido | regra |
| --- | --- | --- | --- |
| status operacional do tripulante/piloto | `pilotos.status` | `tripulantes.status` como `status_snapshot_compat` | Serializer, filtro, relatorio e service leem/escrevem o owner canonico; snapshot nao decide leitura principal. |
| base operacional do tripulante/piloto | `pilotos.base_id` | `tripulantes.base` como `base_snapshot_compat` | Serializer, filtro, relatorio e service resolvem por `pilotos.base_id`/`bases.nome`; snapshot fica so para compatibilidade e bootstrap controlado. |
| modelo de aeronave de referencia em programa de treinamento | `horas_voo_aeronave(tipo_treinamento_id, aeronave_modelo)` | `treinamentos.aeronave_modelo` como `aeronave_modelo_snapshot` fisico | Template, filtro de referencia e CTAC usam `horas_voo_aeronave`; registro realizado le/escreve snapshot explicito e o nome fisico legado nao decide referencia. |

### Completude estrutural de treinamentos

`treinamentos.aeronave_modelo` tem papel fechado de snapshot do modelo usado no registro realizado. A referencia canonica do programa fica em `horas_voo_aeronave(tipo_treinamento_id, aeronave_modelo)`, vinculada ao tipo de treinamento e ao flag `tipos_treinamento.exige_equipamento`. `segmentos_teoricos` define a estrutura segmentada; CTAC deriva da referencia de horas do programa, nao do snapshot salvo em `treinamentos`.

| modo | obrigatorio | opcional | proibido/snapshot | guarda |
| --- | --- | --- | --- | --- |
| `simples` | tripulante, tipo e validade resolvida; equipamento quando `exige_equipamento` | data de realizacao, observacao, anexos, equipamento quando nao exigido | sem segmento, sem snapshot de aeronave e sem CTAC | CHECK impede campos de programa sem segmento; application valida tipo/equipamento/datas. |
| `programa_segmentado` | tripulante, tipo, segmento, data de realizacao e snapshot de aeronave quando `exige_equipamento` | validade derivada, observacao e anexos | sem `equipamento_id`; CTAC proibido quando a referencia nao exigir | CHECK impede mistura com equipamento; application valida segmento do tipo, referencia em `horas_voo_aeronave` e CTAC. |
| `programa_segmentado_ctac` | mesmos obrigatorios do programa segmentado | validade derivada, observacao, anexos e valores CTAC | sem `equipamento_id` | CHECK estrutural igual ao programa; application mantem CTAC opcional e permitido apenas pela referencia. |

Separacao de regras:

- CHECK/constraint: combinacoes provaveis na propria linha (`aeronave_modelo`/CTAC sem segmento e programa com `equipamento_id`).
- Invariavel de application: regra cross-table (`exige_equipamento`, segmento pertence ao tipo, referencia em `horas_voo_aeronave`, datas e permissao de CTAC).
- Compat residual: `aeronave_modelo` permanece como nome fisico legado ate a renomeacao controlada para `aeronave_modelo_snapshot`.

### Owners de scripts criticos e runbooks

| superficie | owner | fonte oficial |
| --- | --- | --- |
| Runtime local e WSGI | Owner backend runtime | `backend/tools/runtime/`, `docs/operations/LOCAL_RUNTIME.md`. |
| App Windows/self-hosted | Owner ops Windows | `ops/windows/scripts/Invoke-AppService.ps1`, `docs/operations/WINDOWS_SELF_HOSTED_SERVER.md`. |
| Scheduler | Owner ops Windows/jobs | `ops/windows/scripts/Install-WindowsScheduledTasks.ps1`, runbook Windows. |
| Worker/notificacoes | Owner ops/jobs | `backend/tools/maintenance/run_jobs_worker.py`, `run_notifications.py`, `docs/operations/canonical-commands.md`. |
| Backup/restore | Owner ops/backup | `backend/tools/maintenance/run_backups.py`, `ops/scripts/backup/backup_restore_drill.py`, `docs/operations/windows_backup_restore_rollback.md`. |
| Smoke/release gate | Owner ops/release | `ops/scripts/smoke/post_deploy_smoke.py`, `ops/scripts/release/run_release_strict.py`, `docs/operations/RELEASE_GATES.md`. |
| Repo hygiene | Owner governanca estrutural | `ops/scripts/repo/validate_repo_hygiene.py`, `docs/governance/repository-governance.md`. |

### Owners de compat residual e documentacao central

| area | owner | regra |
| --- | --- | --- |
| `scripts/*` | Owner do destino canonico + governanca | Compat fino, com `COMPAT`, destino canonico e fila de remocao. |
| `backend/src/controle_treinamentos/compat/` | Owner backend do substituto canonico | Preserva import/entrypoint antigo, sem regra nova. |
| `backend/tools/compat_residual/` | Owner ops do fluxo substituto + governanca | Residual explicito; nao aparece como trilha principal. |
| `legacy/` | Owner de dominio + governanca | Inventario em `legacy/LIVE_LEGACY.md`, sem feature nova. |
| `docs/architecture/ARCHITECTURE.md` | Owner arquitetura | Fonte viva curta do desenho real do sistema. |
| `docs/operations/canonical-commands.md` | Owner ops | Fonte oficial de comandos por tarefa. |
| `docs/governance/repository-governance.md` | Owner governanca estrutural | Regras de entrada, merge, compat, legacy, breaking change e ownership. |
| `docs/product/manual_usuario_operacional.md` | Owner produto | Fonte viva de comportamento para usuario. |

## 4. CONCLUSAO DA 30.1

A arquitetura viva do repo e: monolito Flask self-hosted Windows, frontend estatico separado, PostgreSQL, storage local, jobs em banco, operacao em `ops` e governanca formal em `docs/governance`.

As fronteiras principais ficam estaveis:

- source em `backend/src` e `frontend/src`;
- operacao em `backend/tools`, `ops/scripts` e `ops/windows`;
- docs vivas em `docs/*` por assunto;
- testes em `tests/<camada>`;
- compat e legacy apenas como transicao sinalizada, com owner e condicao de saida.

Mudanca arquitetural nova deve atualizar esta doc quando alterar dominio, fronteira, entrypoint real, compat residual relevante ou ownership.
