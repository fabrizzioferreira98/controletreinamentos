# Archive Manifest

## Padrao minimo

Todo item arquivado precisa ter:

- nome com contexto e data;
- origem;
- motivo do arquivamento;
- status explicito.

Status aceitos: `snapshot`, `backup`, `wrapper antigo`, `copia aninhada` e `doc historica`.

## Inventario classificado

| item | origem | motivo | status |
| --- | --- | --- | --- |
| `repo-snapshots/frontend-build-prod-20260408-143932/` | `.tmp/frontend-build-prod/` | Preservar saida de build do frontend para comparacao historica. | snapshot |
| `repo-snapshots/frontend-build-prod-20260408-150140/` | `.tmp/frontend-build-prod-20260408-150140/` | Preservar saida de build do frontend para comparacao historica. | snapshot |
| `repo-snapshots/frontend-build-prod-20260408-151038/` | `.tmp/frontend-build-prod-20260408-151038/` | Preservar saida de build do frontend para comparacao historica. | snapshot |
| `repo-snapshots/frontend-build-prod-20260408-aba-tabs-removed/` | `.tmp/frontend-build-prod-20260408-aba-tabs-removed/` | Preservar saida de build do frontend apos remocao das abas. | snapshot |
| `repo-snapshots/frontend-build-validate-20260408-aba-tabs-remove/` | `.tmp/frontend-build-validate-20260408-aba-tabs-remove/` | Preservar saida de validacao de build do frontend. | snapshot |
| `repo-snapshots/frontend-prod-hotfix-20260408-144520/` | `.tmp/frontend-prod-hotfix/` | Preservar saida/hotfix do frontend para auditoria historica. | snapshot |
| `temp-backups/root-wrapper-docs-backup-20260408-1635/` | `.tmp/root-wrapper-docs-backup-20260408-1635/` | Preservar backup temporario de wrappers e docs antigos de raiz. | backup |
| `temp-backups/src-app-backup-20260408-154654/` | `.tmp/src-app-backup-20260408-154654/` | Preservar backup temporario de arvore antiga de app. | backup |
| `temp-backups/src-app-__init__-backup-20260408-1610.py` | `.tmp/src-app-__init__-backup-20260408-1610.py` | Preservar backup de arquivo antigo de inicializacao para comparacao. | backup |
| `temp-backups/nested-repo-copy-20260415/` | `controle-treinamentos/` aninhado na raiz | Preservar copia aninhada movida da raiz enquanto a remocao futura nao e decidida. | copia aninhada |
| `old-wrappers/api-cron-backup-20260408-1612.py` | `.tmp/api-cron-backup-20260408-1612.py` | Preservar wrapper antigo sem papel oficial como referencia historica. | wrapper antigo |
| `old-wrappers/api-index-backup-20260408-1612.py` | `.tmp/api-index-backup-20260408-1612.py` | Preservar wrapper antigo sem papel oficial como referencia historica. | wrapper antigo |
| `old-wrappers/backend-compat-cron-backup-20260408-1613.py` | `.tmp/backend-compat-cron-backup-20260408-1613.py` | Preservar wrapper antigo sem papel oficial como referencia historica. | wrapper antigo |
| `old-wrappers/backend-compat-index-backup-20260408-1613.py` | `.tmp/backend-compat-index-backup-20260408-1613.py` | Preservar wrapper antigo sem papel oficial como referencia historica. | wrapper antigo |

## Doc historica

Docs historicas nao devem ser soltas em `archive/` raiz. O destino governado para esse status e `docs/archive/` ou `docs/migration/retired-platforms/`, conforme a governanca de documentacao.

## Permanencia por grupo

| grupo | fica para historico quando | pre-condicao de remocao | nunca voltar para |
| --- | --- | --- | --- |
| `repo-snapshots/frontend-*` | Ajuda a comparar saidas de build/frontend de transicoes encerradas. | Nao houver auditoria, comparacao, bug hunt ou referencia documental pendente. | `frontend/dist/`, raiz, build oficial ou fonte viva. |
| `temp-backups/root-wrapper-docs-backup-20260408-1635/` | Ajuda a comparar wrappers/docs antigos de raiz. | Docs vivas e wrappers canonicos estiverem suficientes e sem referencia pendente ao backup. | Raiz, `scripts/` ou docs vivas sem revisao. |
| `temp-backups/src-app-backup-20260408-154654/` | Ajuda a comparar arvore antiga de app com o backend atual. | Nao houver diff/auditoria pendente sobre a arvore antiga. | `backend/` ou qualquer modulo vivo. |
| `temp-backups/src-app-__init__-backup-20260408-1610.py` | Ajuda a comparar inicializacao antiga com a atual. | Nao houver investigacao pendente sobre inicializacao/compat antiga. | `backend/src/controle_treinamentos/__init__.py`. |
| `temp-backups/nested-repo-copy-20260415/` | Preserva a copia aninhada ate confirmar ausencia de dependencia externa. | Confirmar que nenhuma automacao local externa aponta para a antiga pasta aninhada e que nao ha valor de auditoria. | Raiz como `controle-treinamentos/` aninhado. |
| `old-wrappers/*.py` | Ajuda a entender wrappers antigos ja fora da trilha viva. | Consumidores antigos estiverem migrados ou inexistentes e a trilha canonica estiver documentada. | Comando oficial, compat vivo ou entrypoint de runtime. |
| `docs/archive/` e `docs/migration/retired-platforms/` | Explica decisao, migracao, auditoria encerrada ou plataforma retirada. | Conteudo estiver duplicado, sem referencia e sem valor historico util. | Doc viva sem revisao e reconsolidacao. |

## Ratificacao Frente 31

Regra formal do bloco `31.4.1`:

- `archive/` e historico congelado, nao fonte viva.
- `archive/temp-backups/nested-repo-copy-20260415/` nao e segunda raiz oficial.
- nenhum historico legitimo deve ser apagado por conveniencia.
- remocao futura depende de perda objetiva de valor de auditoria, ausencia de referencia e, quando aplicavel, ausencia de consumidor externo.

| bloco | grupo | decisao |
| --- | --- | --- |
| `31.4.1` | `repo-snapshots/frontend-*` | historico legitimo congelado; nao e build oficial nem fonte viva |
| `31.4.1` | `temp-backups/root-wrapper-docs-backup-*` | historico legitimo congelado; nao volta para raiz nem docs vivas |
| `31.4.1` | `temp-backups/src-app-backup-*` | historico legitimo congelado; nao volta para `backend/` |
| `31.4.1` | `temp-backups/nested-repo-copy-*` | copia aninhada congelada; nao e segunda raiz e so sai com auditoria externa/valor historico resolvido |
| `31.4.1` | `old-wrappers/*.py` | wrappers antigos arquivados; nao sao compat vivo nem comando oficial |
| `31.4.1` | `local-artifacts/` | area de residuo local controlado; vazia nesta medicao e sem papel de historico vivo |
| `31.4.2` | `local-artifacts/.DS_Store` | artefato local sem valor historico; removido fisicamente |

## Excecao temporaria

| item | origem | motivo | status |
| --- | --- | --- | --- |
| `local-artifacts/.DS_Store` | ambiente local macOS | Artefato local sem papel arquitetural; removido fisicamente pela Frente 31. | removido em 31.4.2 |
