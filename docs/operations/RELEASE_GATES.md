# Gates de Release

## Fonte oficial

Esta e a fonte viva para criterios de release. O comando oficial de gate fica em `docs/operations/canonical-commands.md` e aponta para `ops/scripts/release/run_release_strict.py`.

`ops/scripts/release/release_gate.py` e motor interno/deprecated como entrada direta; nao deve ser usado como comando oficial.

O modelo endurecido que antes estava em `RELEASE_GATE_MODEL.md` foi consolidado aqui e arquivado em `docs/archive/operations/`.

## Sequencia oficial minima

1. `validation-ci.yml` / `ops/scripts/release/run_ci_validation_minimal.py` valida build minimo do frontend e contratos de pipeline antes da promocao.
2. `docs/operations/RELEASE_EXECUTION_CHECKLIST.md` e `docs/operations/ROLLBACK_CHECKLIST.md` precisam ser preenchidos no pacote externo do release antes do deploy.
3. `.venv\Scripts\python.exe ops\scripts\release\run_release_strict.py --base-url <url-alvo> --evidence-manifest <manifest.json> --regression-checklist <checklist-preenchido>` continua sendo a unica entrada oficial de gate.
4. `release-strict-gate.yml` e `promotion-ci.yml` apenas executam a mesma trilha oficial em CI; nao competem com ela.
5. `ops/scripts/release/release_gate.py` permanece como motor interno/deprecated e nao e trilha principal.

## Pre-release (obrigatorio)
1. `.venv\Scripts\python.exe ops\scripts\release\run_release_strict.py --base-url <url-alvo> --evidence-manifest <manifest.json> --regression-checklist <checklist-preenchido>` precisa retornar PASS.
2. Testes unitarios/regressao verdes.
3. Migracoes aplicadas sem erro em homologacao.
4. Smoke interno em homologacao executado.
5. Aprovacao de rollback plan.
6. E2E de homologacao obrigatorio no gate (`--with-e2e`) com credencial canonica de teste/homologacao (`E2E_LOGIN`/`E2E_PASSWORD`), nunca conta pessoal ou real.
7. Consistencia de banco obrigatoria no gate (`--require-db-consistency`).
8. Evidencia operacional obrigatoria validada:
   - `.venv\Scripts\python.exe ops\scripts\release\run_release_strict.py --base-url <url-alvo> --evidence-manifest <manifest.json> --regression-checklist <checklist-preenchido> --evidence-max-age-hours 24`
   - template: `docs/operations/RELEASE_EVIDENCE_TEMPLATE.json`
   - validador direto (modo endurecido): `python ops/scripts/release/validate_operational_evidence.py --manifest <manifest.json> --require-signature --signing-key-env RELEASE_EVIDENCE_SIGNING_KEY --require-hashes --require-rollback-runtime-ids --require-alert-ack`
   - gerar hashes/assinatura (obrigatorio): `python ops/scripts/release/harden_release_manifest.py --manifest <manifest.json>`
   - gerar metadados auditaveis de rollback por identificador de runtime/instancia: `python ops/scripts/release/build_rollback_metadata.py --header-before <A> --header-rollback <B> --header-forward <A2> --smoke-before <json> --smoke-rollback <json> --smoke-forward <json> --output <rollback_runtime_ids.json>`
   - o manifest deve bater com o commit atual (`commit_sha == git rev-parse HEAD`) e estar dentro da janela de validade.
   - os artefatos declarados no manifest devem pertencer ao mesmo `release_id`.
   - artefatos precisam conter payload semantico minimo (nao apenas arquivo existente), hash SHA-256 valido e:
     - rollback com `before_runtime_id`, `rollback_runtime_id`, `forward_runtime_id`;
     - alerta externo com `acknowledged=true`, `acknowledged_by` e `escalation_target`.
   - `RELEASE_EVIDENCE_SIGNING_KEY` e obrigatoria para validar assinatura HMAC do manifest no gate endurecido.
9. Checklist de auditoria de regressao preenchido e anexado:
   - template vivo: `docs/operations/REGRESSION_AUDIT_CHECKLIST.md`
   - arquivo preenchido: copia do template no diretorio externo de evidencias da release
   - deve estar 100% marcado (`[x]`), com `Release ID` e `Commit SHA` coerentes com o manifest/HEAD.
   - todas as trilhas de evidencia anexadas (paridade, gate final, checklist de release, checklist de rollback, E2E, carga, jobs, scheduler, storage, alertas, backup, rollback, smoke e manifest) devem apontar para o mesmo `release_id`.
   - `Resultado` aceito no gate: `GO` ou `GO CONDICIONAL`.
10. Checklists operacionais obrigatorios preenchidos e anexados:
   - `docs/operations/RELEASE_EXECUTION_CHECKLIST.md`
   - `docs/operations/ROLLBACK_CHECKLIST.md`
11. Fluxo oficial de release e validacao pos-deploy:
   - `docs/operations/RELEASE_MANAGEMENT.md`
   - `docs/operations/POST_RELEASE_VALIDATION.md`

## Pos-deploy (obrigatorio)
1. Rodar smoke pos-deploy.
2. Validar `X-Request-ID` presente.
3. Validar `/api/internal/metrics`.
4. Validar job worker processando fila.
5. Registrar evidencias em `RELEASE_EXECUTION_CHECKLIST.md`.

## Criterio de rollback
- 5xx > 2% por 10 minutos.
- p95 > 2s por 15 minutos.
- falha de autenticacao generalizada.
- corrupcao de fluxo critico de CRUD.

## Criterio de bloqueio de producao
- qualquer gate obrigatorio em FAIL;
- execucao com bypass no perfil oficial (`--allow-dirty-worktree`, `--allow-cli-secrets`);
- migracao nao idempotente sem rollback testado;
- ausencia de evidencia de smoke em producao;
- ausencia de evidencia operacional obrigatoria (E2E, carga autenticada, jobs concorrentes, alertas, backup/restore, rollback);
- ausencia de evidencia de hardening de metricas em producao (bloqueio sem token valido e acesso somente com token correto);
- checklist de regressao incompleto, sem manifest anexado ou com commit/release divergentes.

## Hardening Operacional Obrigatorio
- `APP_ENV` deve ser explicito e valido: `production`, `staging`, `homolog`, `development` ou `testing`.
- Em qualquer ambiente operacional real, `APP_ENV` deve ser definido explicitamente e nao deve ficar em `development`.
- `/api/internal/metrics` e fail-closed:
  - sem `METRICS_TOKEN` => `503 metrics_unconfigured`;
  - token invalido/ausente => `403 metrics_forbidden`;
  - somente token valido => `200`.
- Evite segredos em CLI:
  - prefira `--*-file` ou variavel de ambiente (`METRICS_TOKEN`, `ALERTS_TEST_WEBHOOK_URL`, `LOADTEST_PASSWORD`);
  - uso de token/senha por flag deve ser excecao e auditado.
