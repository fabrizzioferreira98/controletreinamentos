# Release Management

## Papel

Esta e a fonte viva para o fluxo oficial de release da fase atual. O objetivo aqui nao e inventar automacao nova, e sim fechar o processo real com gate, checklist, validacao pos-release, rollback e evidencia minima obrigatoria.

## Fluxo real encontrado

1. A validacao minima antes da promocao ja existe em `ops/scripts/release/run_ci_validation_minimal.py` e `.github/workflows/validation-ci.yml`.
2. O gate tecnico final ja existe em `ops/scripts/release/run_release_strict.py`, `.github/workflows/release-strict-gate.yml` e `.github/workflows/promotion-ci.yml`.
3. O deploy em si nao e automatizado por uma pipeline unica de promocao. O host Windows/self-hosted sobe a versao presente no servidor pelo servico operacional ou por `ops/windows/scripts/Invoke-AppService.ps1`.
4. O smoke tecnico de aplicacao ja existe em `ops/scripts/smoke/post_deploy_smoke.py`, mas sozinho nao prova worker, scheduler, storage real, rollback nem observacao operacional.
5. O rollback tem documentacao parcial em `docs/operations/windows_backup_restore_rollback.md` e drill de evidencia via `ops/scripts/release/build_rollback_metadata.py`, mas a execucao operacional ainda e manual.

## Pre-condicoes obrigatorias

O release so pode seguir para deploy quando todos os itens abaixo estiverem verdadeiros:

- `validation-ci` verde para o commit candidato;
- `REGRESSION_AUDIT_CHECKLIST.md` preenchido no pacote externo do release;
- manifesto de evidencias preenchido e endurecido;
- backup pre-release executado e registrado;
- checklist de release preenchido;
- checklist de rollback preenchido antes do deploy;
- gate final `run_release_strict.py` em `PASS`.

## Fluxo oficial de release

1. Definir `release_id`, ambiente alvo, operador responsavel e diretório externo de evidencias.
2. Executar a validacao minima oficial (`run_ci_validation_minimal.py`) para o commit candidato.
3. Produzir as evidencias operacionais obrigatorias da release.
4. Preencher o checklist de regressao com caminhos reais para o mesmo `release_id`.
5. Preencher `RELEASE_EXECUTION_CHECKLIST.md` e `ROLLBACK_CHECKLIST.md` no pacote externo do release.
6. Executar `ops/scripts/release/run_release_strict.py`.
7. Somente com `PASS`, promover manualmente a release no host e reiniciar o runtime.
8. Executar `POST_RELEASE_VALIDATION.md`.
9. Monitorar a aplicacao por 30 minutos ou pela janela operacional definida.
10. Registrar decisao final, desvios e, se necessario, rollback.

## Deploy oficial

Nao existe pipeline unico que mova codigo, assets, configuracao e banco ate producao. O deploy oficial desta fase continua sendo operacional e manual:

1. preparar o host com a versao candidata aprovada;
2. garantir que configuracao e assets apontam para a versao aprovada;
3. reiniciar o runtime pelo servico do host ou por `ops/windows/scripts/Invoke-AppService.ps1`;
4. executar a validacao pos-release e salvar as evidencias.

Se qualquer um desses passos depender apenas de memoria do operador, o release nao esta fechado.

## Gate final oficial

O gate final oficial continua sendo:

```powershell
.venv\Scripts\python.exe ops\scripts\release\run_release_strict.py `
  --base-url <url-alvo> `
  --evidence-manifest <manifest.json> `
  --regression-checklist <checklist-preenchido>
```

O release nao pode ser promovido se este comando nao retornar `PASS`.

## Validacao pos-release obrigatoria

A validacao pos-release oficial esta descrita em `docs/operations/POST_RELEASE_VALIDATION.md`. O minimo obrigatorio e:

- smoke HTTP com `post_deploy_smoke.py`;
- validacao de metricas com token valido;
- confirmacao de worker/fila real ou declaracao explicita de fora de escopo;
- confirmacao de scheduler/cron ou declaracao explicita de fora de escopo;
- checagem de logs e request id;
- observacao operacional por 30 minutos.

## Rollback oficial

Rollback oficial nao pode depender de memoria. O operador deve seguir `docs/operations/ROLLBACK_CHECKLIST.md` e classificar a reversao em um ou mais tipos:

- codigo/assets;
- configuracao/env;
- banco;
- storage.

O rollback so e considerado acionavel quando existe:

- release anterior identificada;
- backup restauravel da mesma janela;
- criterio de reversao definido;
- evidencias antes/depois/apos rollback.

## Evidencia minima obrigatoria

O pacote externo do release deve conter, no minimo:

- checklist de regressao preenchido;
- manifesto de evidencias;
- log do gate final;
- checklist de release;
- checklist de rollback;
- backup pre-release;
- evidencias da validacao pos-release;
- evidencias do rollback drill;
- decisao final do operador.

## Aceite final de entrega do produto

O aceite final de entrega do produto e uma decisao operacional sobre um candidato e nao nasce de documentacao isolada.

O operador responsavel deve preencher `<evidence_root>/release/release_decision.md` somente depois de conferir:

- candidato final identificado por `release_id`, ambiente alvo, commit/identificador operacional e diretorio externo de evidencias;
- manifest, checklist de regressao, checklist de release e checklist de rollback apontando para o mesmo candidato;
- `run_release_strict.py` em `PASS` sem bypass;
- `post_deploy_smoke.py` em `PASS` quando houver deploy/promocao;
- metricas, rollback, worker/scheduler/storage e demais evidencias obrigatorias anexadas ou explicitamente justificadas quando nao aplicaveis;
- divergencias, evidencias stale, falhas ou lacunas registradas como `NO-GO` ou `BLOQUEADO`.

Resultado permitido no aceite final:

- `GO_OPERACIONAL_FINAL`: todos os gates aplicaveis estao verdes e as provas materiais apontam para o mesmo candidato.
- `NO-GO`: existe falha material ou gate reprovado.
- `BLOQUEADO`: existe pre-condicao ausente, evidencia indisponivel ou ambiente/candidato sem identidade suficiente.

Separacao obrigatoria:

- `GO_DE_GOVERNANCA` encerra governanca, compatibilidade, legacy, archive/topologia ou backlog governado.
- `GO_DE_GOVERNANCA` nao autoriza entrega de produto.
- Entrega de produto exige `GO_OPERACIONAL_FINAL` emitido por evidencia operacional propria.
