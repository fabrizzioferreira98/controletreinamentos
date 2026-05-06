# Pipeline Minima de CI, Build e Release

## Objetivo

Congelar a esteira minima confiavel que hoje existe de verdade para build, validacao e promocao, sem vender como equivalente o que nao e.

Fonte curta de comandos: `docs/operations/canonical-commands.md`.
Gate de release e criterios de bloqueio: `docs/operations/RELEASE_GATES.md`.

## Esteira real encontrada

| etapa | trilha real hoje | status operacional |
| --- | --- | --- |
| lint | `python -m ruff check backend ops tests` ou `make lint` | existe, mas esta vermelho no estado atual do repo; nao e gate confiavel hoje |
| typecheck | nao existe comando/config/workflow vivo | inexistente; nao pode ser tratado como protecao real |
| testes unitarios | `pytest tests/unit -q` dentro de `pytest`/`run_release_strict.py` | existe, mas hoje roda junto com suites mais amplas via `pytest -q` |
| testes de integracao | `pytest tests/integration -q` | parte depende de `DATABASE_URL` de teste real; sem isso ha skip |
| testes de contrato | `pytest tests/contract -q` | existe; parte da cobertura de HTTP/frontend compat |
| smoke | `ops/scripts/smoke/post_deploy_smoke.py --base-url <url>` | validacao pos-deploy; nao substitui release completo |
| build frontend | `frontend/scripts/build_frontend.py --env-file frontend/.env.example` | build estatico real; agora entra na validacao minima de CI fora do checkout |
| build backend | nao existe build separado/pacote oficial | runtime backend segue a arvore fonte + dependencias; nao ha artefato de build backend versionado |
| artefatos de release | manifest, checklist, logs E2E, json de carga/jobs/alerts/backup/rollback/smoke/metrics | ja consumidos pelo gate strict |
| evidencias | `RELEASE_EVIDENCE_TEMPLATE.json` + checklist preenchido | obrigatorias para promocao |
| wrappers finos | `Makefile release-gate-strict` | aceitavel para compat, sem virar fonte principal |
| caminhos concorrentes de gate | `run_release_strict.py`, workflows `release-strict-gate.yml` e `promotion-ci.yml`, motor `release_gate.py` | `run_release_strict.py` e a unica entrada oficial; `release_gate.py` e motor interno deprecated |

## Classificacao das etapas

### Gate obrigatorio

- `repo-hygiene.yml` para higiene estrutural de branch;
- `validation-ci.yml` / `ops/scripts/release/run_ci_validation_minimal.py` para build minimo do frontend e contratos de pipeline;
- `run_release_strict.py`;
- `release-strict-gate.yml` quando o gate e disparado via workflow;
- `promotion-ci.yml` para sinal de promocao em `main`;
- manifest de evidencias e checklist validados por `validate_operational_evidence.py` e `validate_regression_checklist.py`.

### Validacao importante mas nao bloqueante

- lint com Ruff: importante, mas hoje nao e gate confiavel porque a base atual ainda acumula erros reais;
- suites amplas `tests/unit`, `tests/integration` e `tests/contract` fora do bundle minimo: relevantes, mas ainda nao foram reduzidas a um conjunto verde e reproduzivel para CI cotidiano;
- smoke manual fora do release gate: ajuda diagnostico, mas sozinho nao promove.

### Redundancia historica

- `make test`, `make cov`, `make lint`, `make dev`;
- execucao direta de `pytest -q` como sinal isolado de release;
- reruns manuais do smoke sem manifest/checklist.

### Wrapper aceitavel

- `Makefile release-gate-strict`;
- workflows GitHub que apenas invocam `run_ci_validation_minimal.py` ou `run_release_strict.py`.

### Legado perigoso

- chamar `ops/scripts/release/release_gate.py` como se fosse comando principal;
- usar `requirements.txt` em workflow que precisa de `pytest`;
- tratar `flask run` ou `make dev` como equivalentes a pipeline/release.

### Evidencia insuficiente

- typecheck inexistente;
- ausencia de build backend separado;
- `repo-hygiene.yml` verde sozinho;
- smoke isolado sem manifest/checklist;
- frontend buildado sem entrar na trilha de validacao minima.

## Pipeline minima oficial

### Ordem oficial

1. `repo-hygiene.yml` em PR/push valida a higiene estrutural.
2. `validation-ci.yml` roda `ops/scripts/release/run_ci_validation_minimal.py`.
3. `run_ci_validation_minimal.py`:
   - builda o frontend fora do checkout;
   - roda as suites minimas de governanca/pipeline:
     - `tests/unit/test_db_migrations_schema_split.py`
     - `tests/unit/test_local_runtime_bootstrap_policy.py`
     - `tests/unit/test_environment_parity_policy.py`
     - `tests/unit/test_ci_release_pipeline_policy.py`
     - `tests/contract/test_frontend_compat_redirects.py`
4. `run_release_strict.py` continua sendo o gate oficial de promocao.
5. `release-strict-gate.yml` e `promotion-ci.yml` rerodam a validacao minima antes do gate strict.

### Gates bloqueantes

- higiene estrutural falhou;
- validacao minima de CI/build falhou;
- `run_release_strict.py` retornou `FAIL`;
- manifest/checklist invalidos;
- smoke pos-deploy falhou;
- E2E, carga autenticada, jobs, alerts, backup/restore, rollback ou metrics hardening ausentes/invalidos.

### Criterios de promocao

- `validation-ci.yml` verde;
- `run_release_strict.py` em `PASS`;
- checklist 100% marcado com `GO` ou `GO CONDICIONAL`;
- manifest assinado e coerente com `release_id` e `commit_sha`.

### Falhas que impedem release

- qualquer passo do bundle minimo de CI/build falhando;
- workflows de release sem dependencias de dev;
- uso de `release_gate.py` como entrada direta;
- ausencia de evidencias obrigatorias;
- bypass do perfil strict (`--allow-dirty-worktree`, `--allow-cli-secrets`);
- smoke/metrics/worker/rollback sem evidencias validas.

### Falhas que hoje sinalizam risco, mas ainda nao bloqueiam

- Ruff vermelho;
- ausencia de typecheck;
- suites amplas fora do bundle minimo ainda nao estabilizadas para CI cotidiano;
- ausencia de artefato de build backend separado.

## Evidencias e artefatos esperados

### Artefatos obrigatorios de release

- checklist preenchido;
- manifest endurecido/assinado;
- logs E2E de homologacao;
- relatarios JSON de carga autenticada;
- artefatos de jobs concorrentes;
- drill de alertas externos;
- drill de backup/restore;
- artefatos de rollback com runtime ids;
- smoke pos-deploy;
- hardening de metricas.

### Artefatos obrigatorios de validacao minima

- build do frontend gerado com sucesso fora do checkout;
- saida verde do bundle minimo de testes/politicas de pipeline.

### Artefatos que ainda nao existem como contrato oficial

- build backend versionado;
- relatorio de typecheck;
- bundle unico de regressao ampla verde para CI cotidiano.

## Regras

- `run_release_strict.py` e a unica entrada oficial de gate de release.
- `release-strict-gate.yml` e `promotion-ci.yml` existem para executar a mesma trilha oficial em CI, nao para criar outra.
- `release_gate.py` continua motor interno deprecated.
- `validation-ci.yml` nao promove release; ele so bloqueia branch/build minimo antes da promocao.
- CI verde sem `run_release_strict.py` nao significa release verde.
