# Classificacao da pasta .tmp

## Objetivo

Este documento classifica o conteudo real que existia em `.tmp` e define destino por grupo. `.tmp` nao e arquitetura, nao e fonte canonica e nao pode receber novos fluxos. Na etapa 7.1, a pasta foi esvaziada e removida da raiz.

## Inventario e destino

| grupo | itens | papel real | classificacao | uso real | destino definido |
| --- | --- | --- | --- | --- | --- |
| Builds estaticos de frontend | `frontend-build-prod-20260408-*`, `frontend-build-validate-20260408-aba-tabs-remove`, `frontend-prod-hotfix-20260408-144520` | Copias de saida estatica com `index.html`, `app.css`, `app.js`, `config.js` e paginas JS | snapshot | Sem uso oficial; o build canonico vem de `frontend/scripts/build_frontend.py` | `archive/repo-snapshots/` aplicado na etapa 5.1; nomes padronizados na etapa 4.2 |
| Backups de arvore | `src-app-backup-20260408-154654`, `root-wrapper-docs-backup-20260408-1635` | Copias historicas de arvore antiga de aplicacao, wrappers de raiz e docs | backup de arvore | Sem uso oficial; fontes canonicas estao em `backend/`, `frontend/`, `ops/` e `docs/` | `archive/temp-backups/` aplicado na etapa 5.1 |
| Wrappers temporarios | `api-cron-backup-20260408-1612.py`, `api-index-backup-20260408-1612.py`, `backend-compat-cron-backup-20260408-1613.py`, `backend-compat-index-backup-20260408-1613.py` | Backups de entrypoints HTTP/compat antigos; o diretorio vazio `backend-compat-entrypoints-backup-20260408-1605` nao tinha conteudo | wrapper temporario | Sem uso oficial; compat vivo esta em `backend/src/controle_treinamentos/compat` | `archive/old-wrappers/` aplicado para arquivos com conteudo; diretorio vazio removido na etapa 7.1 |
| Backup de app antigo | `src-app-__init__-backup-20260408-1610.py` | Backup antigo de `backend/src/controle_treinamentos/__init__.py`, diferente do arquivo vivo | backup de arvore | Sem referencia operacional; preservavel apenas como comparacao historica | `archive/temp-backups/` aplicado na etapa 7.1 |
| Evidencias e residuos de QA | `prod_http_request_events*.jsonl`, `usage_truth_prod_30d*.json` | Logs HTTP de producao e relatorios derivados de uso real | residuo de QA | Sem referencia em fluxo oficial; valor apenas para auditoria manual encerravel | removidos na etapa 7.1; nao arquivar dentro do repo por conter eventos de producao |
| Aviso local | `.tmp/README.md` | Marcador para impedir uso canonico da pasta | outro | Util apenas enquanto `.tmp` existia fisicamente | removido junto com `.tmp` na etapa 7.1 |

## Regra operacional

Nada em `.tmp` deve ser importado, executado, documentado como comando oficial ou usado como fonte de build. Qualquer preservacao deve ocorrer fora de `.tmp`, em destino nomeado e com criterio de descarte.

## Criterio de encerramento

`.tmp` deve permanecer ausente. Se reaparecer, deve ser tratada como violacao da topologia oficial e so pode sobreviver temporariamente ate nova classificacao.

- snapshots preservados forem movidos para `archive/repo-snapshots/` ou descartados;
- backups temporarios forem movidos para `archive/temp-backups/` ou descartados;
- residuos de QA forem excluidos ou preservados fora do repositorio;
- o README local nao for mais necessario.

## Status da reorganizacao 5.1

| grupo | destino aplicado | observacao |
| --- | --- | --- |
| Builds estaticos de frontend | `archive/repo-snapshots/` | Movidos para fora de `.tmp`; continuam sem papel operacional |
| Backups de arvore | `archive/temp-backups/` | Movidos para area de backup temporario historico |
| Wrappers temporarios com conteudo | `archive/old-wrappers/` | Movidos porque nao sao compat vivo nem trilha oficial |
| Diretorio vazio de wrapper | removido | Descartado na etapa 7.1 por nao conter conteudo |
| Evidencias/residuos de QA | removidos | Descartados na etapa 7.1; nao devem ser arquivados no repo por conterem eventos/relatorios de producao |
| Backup de app antigo | `archive/temp-backups/src-app-__init__-backup-20260408-1610.py` | Classificado como backup de arvore e movido na etapa 7.1 |

## Status da reorganizacao 7.1

`.tmp/` foi removida da raiz. Nao ha excecao temporaria restante dentro dela.

## Ratificacao Frente 31

Durante a Frente 31, `.tmp/` reapareceu na raiz com JSONs temporarios de validacao/release. Eles nao foram promovidos a evidencia viva da Frente 31 nem a archive historico. O bloco `31.4.2-artefatos-locais-baixo-risco` reclassificou a ocorrencia como lixo local removivel e exigiu nova remocao fisica com `validate_repo_hygiene.py --root .` verde.
