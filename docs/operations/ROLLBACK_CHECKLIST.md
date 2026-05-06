# Rollback Checklist

Copiar este arquivo para o pacote externo do release e preencher antes de qualquer deploy. Nao existe rollback acionavel sem esta preparacao.

## Metadata

- Release ID atual: `<release_id>`
- Release anterior conhecida: `<release_id_anterior>`
- Ambiente alvo: `<homolog|production>`
- Operador responsavel: `<nome>`
- Janela operacional: `<YYYY-MM-DD HH:MM - TZ>`

## Gatilho de rollback

- Sintoma principal: `<falha>`
- Fonte da deteccao: `<smoke|monitoramento|usuario|operacao>`
- Momento da deteccao: `<timestamp>`
- Escopo impactado: `<codigo|configuracao|banco|storage|misto>`

## Pre-condicoes obrigatorias

- [ ] Release anterior foi identificada.
- [ ] Backup/restauracao da mesma janela foi confirmado.
- [ ] Dump, config e assets necessarios para reversao foram localizados.
- [ ] Criterio de rollback total ou parcial foi definido.
- [ ] Janela de manutencao para rollback de banco foi confirmada, se aplicavel.
- [ ] Caminhos de evidencia antes/depois foram preparados.

## Execucao de rollback de codigo/configuracao

- [ ] A versao anterior foi reposta no host alvo.
- [ ] Configuracao/env associados foram revertidos quando necessario.
- [ ] O runtime foi reiniciado pelo servico operacional ou por `ops/windows/scripts/Invoke-AppService.ps1`.
- [ ] `post_deploy_smoke.py` foi executado apos a reversao.

## Execucao de rollback de banco/storage

- [ ] O plano de restore usa dump/assets/config da mesma janela do release.
- [ ] O restore foi executado em ambiente de manutencao controlado.
- [ ] Post-check de contagem/login/fluxo principal foi executado.
- [ ] A promocao do estado restaurado foi registrada.

## Evidencias obrigatorias

- Decisao de rollback: `<evidence_root>/rollback/rollback_decision.md`
- Smoke antes do rollback: `<evidence_root>/smoke/pre_release_smoke.json`
- Smoke apos rollback: `<evidence_root>/smoke/rollback_smoke.json`
- Headers e runtime ids: `<evidence_root>/rollback/rollback_runtime_ids.json`
- Post-check de restore: `<evidence_root>/rollback/restore_postcheck.json`

## Decisao final

- [ ] Rollback concluido com sucesso.
- [ ] Rollback parcial aplicado e riscos residuais registrados.
- [ ] Rollback inviavel: escalacao registrada e release tratado como incidente.
