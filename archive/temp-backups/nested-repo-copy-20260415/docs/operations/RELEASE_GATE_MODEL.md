# Modelo de Release Gate Endurecido

## Execução mínima obrigatória (pipeline)

```bash
python ops/scripts/release/release_gate.py \
  --base-url https://seu-ambiente \
  --evidence-manifest C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/release_manifest.json \
  --evidence-max-age-hours 24 \
  --regression-checklist docs/operations/REGRESSION_AUDIT_CHECKLIST.md
```

Observação: o perfil padrão do gate é `strict`, que já força E2E, consistência de banco,
evidência operacional e checklist. Use `--gate-profile basic` apenas fora de promoção oficial.

## O que bloqueia automaticamente
- `pytest` em FAIL.
- `E2E` sem testes `passed`.
- consistência de banco em FAIL.
- manifest ausente/inválido/antigo.
- `commit_sha` do manifest diferente de `git rev-parse HEAD`.
- assinatura HMAC ausente/inválida.
- hash ausente/inválido para artefatos declarados.
- qualquer check obrigatório com `status != PASS`.
- carga autenticada sem `workers` esperados, com falha de auth, disponibilidade < 99% ou p95 > 1200ms.
- rollback drill sem metadados de runtime/instância ou com smoke em FAIL.
- alerta externo sem `acknowledged`, `acknowledged_by` e `escalation_target`.
- smoke pós-deploy sem `results` válidos/semânticos.
- checklist de regressão incompleto, sem manifest anexado, com release/commit divergente ou decisão inválida.

## Requisitos de evidência
- `release_id` obrigatório e consistente nos artefatos.
- `generated_at` dentro da janela do gate e não futura.
- artefatos legíveis, não vazios, com semântica mínima por tipo.
- checklist com todos itens marcados e metadados completos.
