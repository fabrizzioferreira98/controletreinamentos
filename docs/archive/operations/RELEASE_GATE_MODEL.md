# Arquivado: Modelo de Release Gate Endurecido

Status: historico. A fonte viva consolidada e `docs/operations/RELEASE_GATES.md`; o comando oficial fica em `docs/operations/canonical-commands.md`.

---

# Modelo de Release Gate Endurecido

## Execução mínima obrigatória (pipeline)

```bash
python ops/scripts/release/run_release_strict.py \
  --base-url https://seu-ambiente \
  --evidence-manifest C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/release_manifest.json \
  --evidence-max-age-hours 24 \
  --regression-checklist docs/operations/REGRESSION_AUDIT_CHECKLIST.md
```

Observacao: `run_release_strict.py` e a entrada oficial de promocao. O motor `release_gate.py` nao deve ser usado como comando oficial direto.

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
