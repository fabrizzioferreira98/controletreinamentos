# Relatorio da Reorganizacao do Repositorio

Status: arquivado. Este relatorio preserva o historico da reorganizacao estrutural e nao substitui as politicas vivas em `docs/governance/`, `docs/operations/`, `docs/architecture/` ou `docs/product/`.

## Objetivo

Registrar o que foi decidido, documentado, movido, consolidado, removido e validado durante a reorganizacao estrutural do repositorio.

Este relatorio nao reabre classificacoes. Ele resume o estado final da conversa e aponta as evidencias operacionais que ficaram no repo.

## Escopo executado

A conversa cobriu as etapas 1 a 10 da reorganizacao:

- congelamento da topologia oficial da raiz;
- isolamento de ambiente local e residuos;
- classificacao e destino de `.tmp` e `controle-treinamentos`;
- consolidacao de trilhas operacionais e comandos oficiais;
- reorganizacao da documentacao viva, historica e de migracao;
- definicao de `compat`, `legacy` e `archive`;
- criacao/reforco de guardrails;
- execucao fisica controlada em tres fases: mover, consolidar, remover;
- definicao do criterio de pronto da raiz e maturidade do repo.

## Decisoes principais

### Raiz canonica

A raiz oficial passou a comunicar produto, operacao, documentacao, testes e areas de transicao:

- `.github/`: CI, release e governanca automatizada.
- `backend/`: backend Flask, runtime local e ferramentas de manutencao.
- `frontend/`: frontend oficial; `src` e `scripts` sao fonte, `dist` e gerado.
- `ops/`: operacao real, Windows self-hosted, release, smoke, drills e scripts operacionais.
- `tests/`: validacao oficial.
- `docs/`: documentacao viva, governanca, operacao, produto, migracao e archive governados.
- `scripts/`: aliases historicos de compatibilidade; nao recebe novos fluxos.
- `archive/`: material historico fora da operacao viva.
- `legacy/`: area para legado vivo com dependencia real confirmada.

Foram marcados como proibidos ou nao oficiais na raiz: `.tmp`, `controle-treinamentos`, snapshots, backups, caches, builds gerados, runtime mutavel, logs e configuracoes locais.

### Compat, legacy e archive

- `compat`: existe apenas para manter caminhos antigos funcionando enquanto consumidores migram. Deve ser fino, explicito e ter condicao de saida.
- `legacy`: contem comportamento ainda vivo, mas fora do desenho canonico futuro. Nao deve receber feature nova como se fosse nucleo.
- `archive`: contem material historico, snapshots, backups, wrappers antigos e docs aposentadas. Nao e fonte de build, restore, operacao ou release.

Nao foi criada uma pasta raiz `compat/` por simetria. A compatibilidade real ficou nos wrappers de `scripts/` e em areas explicitas do codigo, como `backend/src/controle_treinamentos/compat`.

## Documentacao criada ou atualizada

### Governanca

- `docs/governance/repo-topology.md`: topologia oficial da raiz.
- `docs/governance/root-entry-policy.md`: politica minima de entrada na raiz.
- `docs/governance/legacy-policy.md`: regras de transicao para compat, legacy, archive e remocao.
- `docs/governance/documentation-governance.md`: distincao entre doc viva, migracao e archive.
- `docs/governance/tmp-classification.md`: classificacao e destino da antiga `.tmp`.
- `docs/governance/nested-repo-classification.md`: classificacao da copia aninhada `controle-treinamentos`.

### Operacao

- `docs/operations/canonical-commands.md`: fonte curta com um comando oficial por tarefa critica.
- `docs/operations/RUNBOOK.md`: alinhado para apontar para comandos canonicos e trilhas corretas.
- `docs/operations/RELEASE_GATES.md`: consolidou criterios vivos de release.

### README

- `README.md`: virou porta de entrada curta para topologia, comandos oficiais, docs vivas e itens que nao sao fonte viva.

### Scripts e compatibilidade

- `scripts/README.md`: documenta wrappers de compatibilidade, status, trilha canonica, risco e pre-condicao de remocao.

## Comandos oficiais definidos

A fonte oficial ficou em `docs/operations/canonical-commands.md`.

Tarefas cobertas:

- subir app;
- build frontend;
- rodar smoke;
- release gate;
- backup;
- worker;
- consistencia de banco;
- saneamento de usuarios de teste.

Decisao operacional: nao ha dois comandos oficiais para a mesma tarefa critica. Wrappers e entradas diretas antigas foram classificados como compat, implementacao, deprecated ou motor interno.

## Movimentos fisicos e arquivo historico

### `archive/`

Foi criada e governada a estrutura:

- `archive/repo-snapshots/`: snapshots historicos.
- `archive/temp-backups/`: backups temporarios de arvore ja classificados.
- `archive/old-wrappers/`: wrappers antigos sem papel oficial.

Itens movidos ou preservados ali:

- snapshots antigos de build/frontend;
- backups de arvore antigos;
- wrappers antigos de entrypoints;
- copia aninhada `controle-treinamentos`, movida para `archive/temp-backups/nested-repo-copy-20260415`.

### `.tmp`

A antiga `.tmp` foi classificada, esvaziada e removida da raiz. O que tinha valor historico foi movido para `archive/`; residuos de QA sem papel oficial foram removidos.

### Docs historicas

Docs claramente antigas foram movidas para:

- `docs/archive/`;
- `docs/migration/retired-platforms/`.

As docs vivas principais ficaram organizadas em:

- `docs/architecture/`;
- `docs/operations/`;
- `docs/governance/`;
- `docs/product/`.

## Consolidacao de scripts e wrappers

### `scripts/`

Permaneceu como area de aliases historicos de compatibilidade. Os wrappers foram mantidos porque ainda nao ha evidencia objetiva de migracao completa dos consumidores antigos.

Wrappers mantidos:

- `scripts/backup/run_backups.py`;
- `scripts/database/run_db_consistency.py`;
- `scripts/jobs/run_jobs_worker.py`;
- `scripts/jobs/run_notifications.py`;
- `scripts/windows/Invoke-AppService.ps1`;
- `scripts/windows/Invoke-OperationalPython.ps1`.

Cada wrapper deve ser fino, emitir aviso de compatibilidade e delegar para a trilha canonica.

### `ops/scripts`

Entradas diretas que poderiam competir com `backend/tools/maintenance` foram marcadas como implementacao despriorizada:

- `ops/scripts/backup/run_backups.py`;
- `ops/scripts/database/run_db_consistency.py`;
- `ops/scripts/jobs/run_jobs_worker.py`;
- `ops/scripts/jobs/run_notifications.py`.

`ops/scripts/release/release_gate.py` ficou marcado como deprecated para uso direto, mas continua como motor interno chamado por `ops/scripts/release/run_release_strict.py`.

`run_release_strict.py` foi corrigido para resolver caminhos pela raiz real do repo e chamar o motor interno de forma controlada.

## Guardrails criados ou reforcados

Foi criado/reforcado o check:

- `ops/scripts/repo/validate_repo_hygiene.py`.

O check cobre, entre outros pontos:

- snapshot ou backup novo na raiz;
- pasta ambigua nova;
- doc viva nao registrada;
- script em `scripts/` sem classificacao de compat;
- referencias a evidencias/backups/artefatos dentro do repo;
- caches, bytecode, runtime, builds e segredos locais em locais proibidos.

O check e aplicavel em desenvolvimento e CI. Em modo normal falha; em `--report-only` inventaria sem bloquear.

## Remocoes controladas

Na etapa final foram removidos apenas itens comprovadamente mortos, gerados ou regeneraveis:

- `.ruff_cache/`;
- `frontend/dist/`;
- `frontend/.tmp/`;
- `backend/runtime/`, que estava vazio;
- `__pycache__/` e bytecode fora de `.venv/` e `archive/`.

Nao foram removidos:

- `.venv/`, para preservar o fluxo local de desenvolvimento;
- `.vscode/`, por ser ambiente local ainda presente;
- wrappers de `scripts/`, por ainda serem compatibilidade documentada;
- `release_gate.py`, por ainda ser motor interno;
- conteudo em `archive/`, por ser preservacao historica classificada.

## Validacoes realizadas

Durante a reorganizacao foram executadas validacoes pontuais, incluindo:

- sintaxe dos scripts alterados;
- `ops/scripts/release/run_release_strict.py --help`;
- `tests/unit/test_legacy_windows_compat.py`, com resultado aprovado;
- `ops/scripts/repo/validate_repo_hygiene.py --report-only`;
- verificacao de ausencia de `.tmp`, snapshots e backups na raiz;
- verificacao de ausencia de `frontend/dist`, `.ruff_cache`, `frontend/.tmp`, `backend/runtime` e `__pycache__` fora de `.venv/` e `archive/` apos a remocao.

Estado final observado do hygiene em modo relatorio: restaram apenas `.venv/` e `.vscode/` como itens locais ainda visiveis, ja classificados como ambiente local e nao arquitetura.

## Estado final da raiz

Ao final da conversa, a raiz visivel continha:

- `.github/`;
- `.venv/`;
- `.vscode/`;
- `archive/`;
- `backend/`;
- `docs/`;
- `frontend/`;
- `legacy/`;
- `ops/`;
- `scripts/`;
- `tests/`;
- arquivos de configuracao e entrada do projeto.

Ausentes da raiz apos a reorganizacao:

- `.tmp/`;
- `controle-treinamentos/` aninhado;
- `.ruff_cache/`;
- `frontend/dist/`;
- `frontend/.tmp/`;
- `backend/runtime/`;
- `__pycache__/` fora de `.venv/` e `archive/`.

## Criterio de pronto definido

A raiz foi considerada pronta quando:

- uma pessoa nova consegue entender os papeis principais em poucos minutos;
- ativo, compat, legado e archive nao se confundem;
- existe um comando oficial por tarefa critica;
- README e docs apontam para trilhas corretas;
- snapshot, backup, build gerado e residuo nao competem com o produto.

O repo foi considerado maduro quando:

- nao depende de folclore;
- nao depende de memoria historica;
- a arvore comunica arquitetura e operacao reais;
- transicao tem semantica, consumidor e condicao de saida;
- guardrails conseguem detectar recontaminacao.

## Dividas adiadas

- Migrar consumidores antigos para remover wrappers em `scripts/`.
- Extrair o motor de `release_gate.py` para modulo interno antes de eliminar a entrada direta deprecated.
- Decidir futuramente se `.venv/` e `.vscode/` devem sair fisicamente da raiz ou permanecer apenas como excecao local tolerada.
- Revisar periodicamente `archive/` para evitar que preservacao historica vire deposito indefinido.

## Conclusao

A reorganizacao transformou a raiz de uma area ambigua em uma topologia governada: nucleo vivo, operacao, documentacao, compatibilidade, legado e arquivo historico passaram a ter papeis distintos.

O estado final nao depende de memoria de quem reorganizou. As decisoes centrais estao documentadas, os comandos oficiais estao centralizados, os residuos classificados sairam do campo visual principal e a recontaminacao passou a ter check automatizado.
