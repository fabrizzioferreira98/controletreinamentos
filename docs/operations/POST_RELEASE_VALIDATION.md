# Post-release Validation

## Papel

Definir a validacao minima obrigatoria apos um deploy aprovado. Aplicacao de pe ou healthcheck verde nao fecham release.

## Comando minimo

```powershell
.venv\Scripts\python.exe ops\scripts\smoke\post_deploy_smoke.py `
  --base-url <base_url> `
  --metrics-url <metrics_url> `
  --metrics-token <metrics_token> `
  --output <evidence_root>\smoke\post_release_smoke.json
```

## O que o smoke cobre

O script valida respostas HTTP de rotas criticas e comportamento minimo do endpoint de metricas. Isso e necessario, mas nao suficiente.

## O que ainda precisa ser validado manualmente

- worker consumindo fila real, ou declaracao explicita de que o release nao toca esse fluxo;
- scheduler/cron executando, ou declaracao explicita de fora de escopo;
- upload, download, storage e PDF quando o release tocar esses fluxos;
- logs com request id e ausencia de erro estrutural apos o restart;
- observacao operacional por 30 minutos.

## Criterios de bloqueio

O release deve ser bloqueado ou revertido quando qualquer um destes pontos ocorrer:

- smoke HTTP falhar;
- metricas com token valido falharem;
- worker nao consumir fila real quando o fluxo faz parte do escopo;
- scheduler/cron nao executar quando o fluxo faz parte do escopo;
- storage, PDF, upload ou download quebrarem em release que toca esses fluxos;
- erro recorrente aparecer em logs logo apos a promocao.

## Evidencia minima

Salvar no pacote externo do release:

- `smoke/post_release_smoke.json`
- `release/post_release_validation.md`
- evidencias adicionais de worker, scheduler e storage quando aplicavel
