# Gates de Release

## Pré-release (obrigatório)
1. `python ops/scripts/release/run_release_strict.py --base-url <url-alvo> --evidence-manifest <manifest.json> --regression-checklist docs/operations/REGRESSION_AUDIT_CHECKLIST.md` precisa retornar PASS.
2. Testes unitários/regressão verdes.
3. Migrações aplicadas sem erro em homologação.
4. Smoke interno em homologação executado.
5. Aprovação de rollback plan.
6. E2E de homologação obrigatório no gate (`--with-e2e`) com credenciais reais.
7. Consistência de banco obrigatória no gate (`--require-db-consistency`).
8. Evidência operacional obrigatória validada:
   - `python ops/scripts/release/run_release_strict.py --base-url <url-alvo> --evidence-manifest <manifest.json> --regression-checklist docs/operations/REGRESSION_AUDIT_CHECKLIST.md --evidence-max-age-hours 24`
   - template: `docs/operations/RELEASE_EVIDENCE_TEMPLATE.json`
  - validador direto (modo endurecido): `python ops/scripts/release/validate_operational_evidence.py --manifest <manifest.json> --require-signature --signing-key-env RELEASE_EVIDENCE_SIGNING_KEY --require-hashes --require-rollback-runtime-ids --require-alert-ack`
   - gerar hashes/assinatura (obrigatório): `python ops/scripts/release/harden_release_manifest.py --manifest <manifest.json>`
  - gerar metadados auditáveis de rollback por identificador de runtime/instância: `python ops/scripts/release/build_rollback_metadata.py --header-before <A> --header-rollback <B> --header-forward <A2> --smoke-before <json> --smoke-rollback <json> --smoke-forward <json> --output <rollback_runtime_ids.json>`
   - o manifest deve bater com o commit atual (`commit_sha == git rev-parse HEAD`) e estar dentro da janela de validade.
   - os artefatos declarados no manifest devem pertencer ao mesmo `release_id`.
   - artefatos precisam conter payload semântico mínimo (não apenas arquivo existente), hash SHA-256 válido e:
    - rollback com `before_runtime_id`, `rollback_runtime_id`, `forward_runtime_id`;
     - alerta externo com `acknowledged=true`, `acknowledged_by` e `escalation_target`.
   - `RELEASE_EVIDENCE_SIGNING_KEY` é obrigatória para validar assinatura HMAC do manifest no gate endurecido.
9. Checklist de auditoria de regressão preenchido e anexado:
   - `docs/operations/REGRESSION_AUDIT_CHECKLIST.md`
   - deve estar 100% marcado (`[x]`), com `Release ID` e `Commit SHA` coerentes com o manifest/HEAD.
   - todas as trilhas de evidência anexadas (E2E, carga, jobs, backup, rollback, smoke e manifest) devem apontar para o mesmo `release_id`.
   - `Resultado` aceito no gate: `GO` ou `GO CONDICIONAL`.

## Pós-deploy (obrigatório)
1. Rodar smoke pós-deploy.
2. Validar `X-Request-ID` presente.
3. Validar `/api/internal/metrics`.
4. Validar job worker processando fila.

## Critério de rollback
- 5xx > 2% por 10 minutos.
- p95 > 2s por 15 minutos.
- falha de autenticação generalizada.
- corrupção de fluxo crítico de CRUD.

## Critério de bloqueio de produção
- qualquer gate obrigatório em FAIL;
- execução com bypass no perfil oficial (`--allow-dirty-worktree`, `--allow-cli-secrets`);
- migração não idempotente sem rollback testado;
- ausência de evidência de smoke em produção.
- ausência de evidência operacional obrigatória (E2E, carga autenticada, jobs concorrentes, alertas, backup/restore, rollback).
- ausência de evidência de hardening de métricas em produção (bloqueio sem token válido e acesso somente com token correto).
- checklist de regressão incompleto, sem manifest anexado ou com commit/release divergentes.

## Hardening Operacional Obrigatório
- `APP_ENV` deve ser explícito e válido: `production`, `staging`, `homolog`, `development` ou `testing`.
- Em qualquer ambiente operacional real, `APP_ENV` deve ser definido explicitamente e não deve ficar em `development`.
- `/api/internal/metrics` é fail-closed:
  - sem `METRICS_TOKEN` => `503 metrics_unconfigured`;
  - token inválido/ausente => `403 metrics_forbidden`;
  - somente token válido => `200`.
- Evite segredos em CLI:
  - prefira `--*-file` ou variável de ambiente (`METRICS_TOKEN`, `ALERTS_TEST_WEBHOOK_URL`, `LOADTEST_PASSWORD`);
  - uso de token/senha por flag deve ser exceção e auditado.
