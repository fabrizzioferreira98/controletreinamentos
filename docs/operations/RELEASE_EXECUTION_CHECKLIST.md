# Release Execution Checklist

Copiar este arquivo para o pacote externo do release e preencher antes de iniciar o deploy.

## Metadata

- Release ID: `<release_id>`
- Ambiente alvo: `<homolog|production>`
- Operador responsavel: `<nome>`
- Janela operacional: `<YYYY-MM-DD HH:MM - TZ>`
- Commit candidato: `<git_sha>`
- Diretorio de evidencias: `<WORKSPACE_EVIDENCE_ROOT>/<release_id>`

## Pre-condicoes

- [ ] `validation-ci` do commit candidato concluiu com sucesso.
- [ ] `REGRESSION_AUDIT_CHECKLIST.md` foi copiado e preenchido para este release.
- [ ] Manifesto de evidencias foi gerado, endurecido e salvo no diretorio externo.
- [ ] Backup pre-release foi executado e o caminho do artefato foi registrado.
- [ ] `ROLLBACK_CHECKLIST.md` foi copiado e preenchido antes do deploy.
- [ ] Variaveis obrigatorias do ambiente foram validadas no host alvo.
- [ ] Worker, scheduler e storage fora de escopo foram explicitamente declarados quando aplicavel.

## Gate final

- [ ] `run_release_strict.py` foi executado para este `release_id`.
- [ ] O resultado foi `PASS`.
- [ ] O log do gate foi salvo em `<evidence_root>/gate/run_release_strict.log`.

## Deploy

- [ ] O host alvo recebeu a versao candidata aprovada.
- [ ] Configuracao/env do host foi revisada antes do restart.
- [ ] Assets/build de frontend correspondem ao commit aprovado.
- [ ] O runtime foi reiniciado pelo servico operacional ou por `ops/windows/scripts/Invoke-AppService.ps1`.
- [ ] O horario real do restart foi registrado.

## Validacao pos-release

- [ ] `post_deploy_smoke.py` executou contra o ambiente promovido.
- [ ] O resultado do smoke foi salvo em `<evidence_root>/smoke/post_release_smoke.json`.
- [ ] Metricas com token valido responderam como esperado.
- [ ] Worker/fila real foram validados ou declarados fora de escopo.
- [ ] Scheduler/cron foram validados ou declarados fora de escopo.
- [ ] Logs e request ids foram revisados.
- [ ] A observacao operacional minima de 30 minutos foi concluida.

## Decisao

- [ ] Release mantido em producao.
- [ ] Rollback nao necessario.
- [ ] Desvios, limitacoes e riscos residuais foram registrados.

## Aceite final da entrega do produto

Preencher somente depois de gate final, smoke pos-release, evidencias obrigatorias e revisao do operador. Este checklist nao declara aceite por si so.

- [ ] O candidato final esta identificado por `release_id`, ambiente alvo, commit/identificador operacional e diretorio externo de evidencias.
- [ ] O manifest de evidencias aponta para artefatos materiais do mesmo candidato.
- [ ] O checklist de regressao preenchido foi validado para o mesmo `release_id` e ambiente.
- [ ] `run_release_strict.py` retornou `PASS` para o candidato final, sem bypass.
- [ ] `post_deploy_smoke.py` retornou `PASS` contra o ambiente final, com metricas validadas quando aplicavel.
- [ ] Checklist de rollback e evidencia de rollback/drill estao anexados.
- [ ] Evidencias ausentes, stale, vermelhas ou divergentes foram registradas como `NO-GO` ou `BLOQUEADO`, nunca como aceite documental.
- [ ] `GO_DE_GOVERNANCA` foi tratado apenas como governanca encerrada; nao foi usado como `GO` de entrega do produto.
- [ ] Dividas nao-bloqueantes e baseline vermelho conhecido foram separados de impedimento real de entrega.
- [ ] A decisao final do operador foi salva em `<evidence_root>/release/release_decision.md`.

Modelo minimo para `<evidence_root>/release/release_decision.md`:

```markdown
# Decisao final de entrega

- Release ID: <release_id>
- Ambiente alvo: <homolog|production>
- Commit/identificador operacional: <git_sha|identificador>
- Operador responsavel: <nome>
- Data/hora da decisao: <YYYY-MM-DD HH:MM TZ>
- Resultado: <GO_OPERACIONAL_FINAL|NO-GO|BLOQUEADO>

## Provas materiais

- Manifest: <path>
- Checklist de regressao: <path>
- Checklist de release: <path>
- Checklist de rollback: <path>
- Gate final strict: <path>
- Smoke pos-release: <path>
- Evidencias obrigatorias adicionais: <paths>

## Justificativa

<resumo objetivo baseado nas provas materiais>

## Pendencias, desvios e riscos residuais

<nenhum|lista objetiva>
```

## Evidencias minimas

- Checklist de release: `<evidence_root>/release/release_execution_checklist.md`
- Checklist de rollback: `<evidence_root>/rollback/rollback_checklist.md`
- Gate final strict: `<evidence_root>/gate/run_release_strict.log`
- Smoke pos-release: `<evidence_root>/smoke/post_release_smoke.json`
- Manifest de evidencias: `<evidence_root>/manifest/evidence-manifest.json`
- Decisao final do operador: `<evidence_root>/release/release_decision.md`
