# Politica de Compat, Legacy, Archive e Remocao

## Objetivo

Governar a transicao de material fora do nucleo vivo. Um item deve ter um unico destino semantico: compat, legacy, archive ou remocao.

## Quando vira compat

| regra | exemplo | condicao de saida |
| --- | --- | --- |
| Existe apenas para manter caminho, import, comando ou entrypoint antigo funcionando enquanto consumidores migram. | `scripts/backup/run_backups.py` delegando para `backend/tools/maintenance/run_backups.py`. | Consumidores usam a trilha canonica, teste de shim pode ser removido e o risco operacional foi mitigado. |
| Deve ser fino, delegar para o caminho canonico e avisar quando aplicavel. | `scripts/windows/Invoke-AppService.ps1` apontando para `ops/windows/scripts/Invoke-AppService.ps1`. | Servicos, atalhos e tarefas antigas foram migrados. |

Compat nao recebe regra de negocio nova, nao vira segunda implementacao e nao pode permanecer sem plano de remocao.

## Quando vira legacy

| regra | exemplo | condicao de permanencia |
| --- | --- | --- |
| Ainda e usado/testado, mas nao representa o desenho canonico futuro. | Rotas e templates SSR ainda acoplados ao Flask. | Consumidor real, teste ou contrato vivo ainda depende do comportamento. |
| Nao e apenas wrapper; contem fluxo ou superficie funcional que ainda nao pode ser extraida sem quebrar compatibilidade. | Contratos `ssr_compat` ou `files_legacy`. | Ha criterio de extracao registrado e o item nao recebe feature nova. |

Legacy nao compete com o nucleo. Correcoes criticas sao permitidas; novas features devem nascer no caminho canonico.

## Quando vai para archive

| regra | exemplo |
| --- | --- |
| Nao tem consumidor vivo, mas tem valor de auditoria, comparacao ou historico. | `archive/temp-backups/nested-repo-copy-20260415/`. |
| E snapshot, backup, doc antiga, wrapper morto ou material de plataforma retirada. | `archive/old-wrappers/`, `docs/archive/`, `docs/migration/retired-platforms/`. |

Archive nao pode conter material vivo, nao e restore oficial e nao deve ser importado, executado, buildado ou usado em release. Material arquivavel novo nao passa pela raiz: deve entrar ja classificado em `archive/` e registrado em `archive/MANIFEST.md`, ou ser descartado se nao tiver valor historico.

## Quando pode ser removido

| regra | pre-condicao | risco |
| --- | --- | --- |
| Item sem consumidor vivo e sem valor historico necessario. | Busca/review nao encontra chamada real, doc viva, job, teste, import ou automacao dependente. | Remover dependencia externa invisivel. |
| Residuo local, cache, temporario ou evidencia sensivel que nao deve ficar no repo. | Classificacao registrada e destino seguro definido fora do repo ou descarte aprovado. | Perder evidencia manual ainda nao encerrada. |
| Compat com migracao concluida. | Consumidores migrados, teste de shim atualizado/removido e rollback conhecido. | Quebrar operador, agendador, import ou servico antigo. |

Remocao exige pre-condicao explicita. Se a pre-condicao nao puder ser provada, o item fica como compat, legacy ou archive conforme uso real.

## Matriz de transicao

| estado atual | destino correto |
| --- | --- |
| Nucleo vivo e canonico | Permanecer no modulo oficial. |
| Caminho antigo que so delega | Compat. |
| Fluxo vivo nao canonico com comportamento proprio | Legacy. |
| Material historico sem consumidor vivo | Archive. |
| Temporario, cache, log local ou evidencia sensivel | Remocao ou preservacao fora do repo. |
| Doc antiga concorrente | Consolidar na doc viva e mover para `docs/archive/` ou `docs/migration/`. |
| Snapshot ou backup classificado | `archive/repo-snapshots/` ou `archive/temp-backups/`. |
| Wrapper morto sem consumidor | `archive/old-wrappers/` ou remocao se nao houver valor historico. |

## Regra de review

Antes de mover, arquivar ou remover:

- classificar pelo uso real, nao pelo nome;
- identificar consumidor, teste, job, doc ou automacao;
- registrar condicao de saida quando for compat ou legacy;
- impedir que archive ou legacy virem segunda raiz do produto;
- atualizar docs e referencias que apontavam para o caminho antigo.
