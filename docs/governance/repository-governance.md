# Governanca formal do repositorio

## Objetivo

Definir a regra formal de entrada, merge, compatibilidade, legado, breaking change estrutural e ownership do repositorio.

Esta doc coordena as fontes ja vivas:

- `docs/governance/repo-topology.md` para topologia oficial.
- `docs/governance/root-entry-policy.md` para entrada na raiz.
- `docs/governance/technical-conventions.md` para convencoes.
- `docs/governance/legacy-policy.md` para compat, legacy, archive e remocao.
- `docs/operations/canonical-commands.md` para comandos oficiais.

Nenhuma mudanca deve criar caminho que pareca principal sem estar registrado nessas fontes.

## 1. O QUE PODE ENTRAR

| item | condicao obrigatoria | evidencia minima |
| --- | --- | --- |
| Codigo-fonte de backend | Deve morar em `backend/src/controle_treinamentos/` e representar comportamento vivo da aplicacao. | Teste da camada afetada, owner backend e doc/contrato atualizado quando mudar superficie publica. |
| Codigo-fonte de frontend | Deve morar em `frontend/src/`; build gerado nao e fonte viva. | Build ou teste aplicavel e, se houver nova origem/API, doc operacional atualizada. |
| Entrypoint oficial de backend | Deve morar em `backend/tools/runtime/` ou `backend/tools/maintenance/` conforme o papel. | Registro em `docs/operations/canonical-commands.md` e ausencia de concorrente em `scripts/`. |
| Script operacional vivo | Deve morar em `ops/scripts/<dominio>/` ou `ops/windows/scripts/` e executar operacao real. | Comando, runbook ou workflow que chama o script; owner operacional. |
| Utilitario manual perigoso | Deve ficar em `backend/tools/manual_unsafe/` ou area operacional explicitamente marcada como manual/destrutiva. | Nome explicito, confirmacao de uso quando aplicavel e ausencia da trilha normal. |
| Documentacao viva | Deve ficar em `docs/architecture`, `docs/operations`, `docs/governance` ou `docs/product`. | Fonte viva unica, entrada em indice e alinhamento com `documentation-governance.md`. |
| Teste oficial | Deve ficar em `tests/<camada>`: `unit`, `integration`, `contract`, `e2e`, `ops` ou `architecture`. | Nome que revele comportamento/camada e execucao documentada quando for gate. |
| Compat controlado | Deve existir so para manter consumidor antigo enquanto migra para destino canonico. | Owner, sinalizacao `COMPAT`, destino canonico, teste/README quando aplicavel e condicao de saida. |
| Legacy vivo | Deve representar fluxo ainda usado/testado que nao pode ser extraido sem quebrar compatibilidade. | Registro em `legacy/LIVE_LEGACY.md`, owner de dominio e criterio de saida. |
| Archive classificado | Deve guardar historico sem consumidor vivo e sem autoridade operacional. | Registro em manifesto/politica de archive e ausencia em build, teste, release e comandos oficiais. |
| Arquivo de raiz aceito | Deve sustentar onboarding, dependencias, tooling, testes ou configuracao basica. | Uso real por ferramenta, README ou workflow. |

## 2. O QUE NAO PODE ENTRAR

| item | motivo |
| --- | --- |
| Nova pasta de raiz sem categoria formal | Cria ambiguidade estrutural e compete com a topologia oficial. |
| Segunda arvore aparente do produto | Pastas como `controle-treinamentos/` aninhado parecem raiz principal falsa. |
| Build, cache, bytecode ou ambiente local versionado/tratado como fonte | `frontend/dist`, `.venv`, `.ruff_cache`, `__pycache__`, `.pytest_cache` e similares nao sao fonte; as unicas excecoes locais aceitas precisam estar explicitadas em `repo-topology.md` e `root-entry-policy.md`. |
| Logs, runtime state, evidencias ou backups operacionais no repo | Estado mutavel e evidencia gerada devem ficar fora da arvore viva. |
| Novo comando principal dentro de `scripts/` | `scripts/` e compat; comando oficial nasce em `backend/tools`, `ops/scripts` ou `ops/windows/scripts`. |
| Wrapper compat sem consumidor real | Compat sem consumidor vira trilha falsa e deve ser recusado ou removido. |
| Regra de negocio nova em compat ou legacy | Caminho de transicao nao pode virar segunda implementacao. |
| Doc viva em `docs/archive` ou `docs/migration/retired-platforms` | Archive e plataforma retirada nao tem autoridade operacional. |
| Doc concorrente para assunto ja governado | Deve consolidar na fonte viva primaria ou arquivar a anterior. |
| Script destrutivo com nome neutro | Reparo, cleanup e mutacao perigosa precisam parecer perigosos pelo caminho e pelo nome. |
| Breaking estrutural escondido | Mudanca que altera caminho, entrada, contrato operacional ou topologia precisa seguir a regra de breaking change. |

## 3. POLITICA DE COMPAT

Compat existe para preservar consumidores antigos durante migracao. Nao e entrada oficial.

| area de compat | owner obrigatorio | sinalizacao obrigatoria | regra de permanencia |
| --- | --- | --- | --- |
| `scripts/*` | Owner do comando canonico mais owner estrutural de governanca. | Cabecalho `COMPAT:`, destino canonico no arquivo, linha em `scripts/README.md` e fila de remocao. | Fino, delega para o destino canonico e nao contem regra principal. |
| `backend/src/controle_treinamentos/compat/` | Owner backend da superficie canonica substituta. | Nome/pacote `compat`, teste de compat quando houver contrato publico e condicao de morte em backlog ou doc viva. | Pode adaptar import/entrypoint antigo, mas nao criar comportamento novo. |
| `backend/tools/compat_residual/` | Owner operacional da rotina substituta mais governanca. | Nome residual explicito, doc de comando canonico apontando para outro caminho. | Usado apenas enquanto consumidor antigo existir. |

Regras de merge para compat:

- Toda compat precisa declarar destino canonico.
- Toda compat precisa ter owner responsavel por matar o caminho depois.
- Docs oficiais nao podem apontar para compat como trilha principal.
- Teste de compat deve ter nome explicito e nao pode proteger caminho antigo sem condicao de saida.
- Compat sem consumidor real deve ir para archive ou remocao, nao para uma pasta decorativa.

## 4. POLITICA DE LEGADO

Legacy e fluxo vivo nao canonico. Ele existe porque remover ou mover agora quebraria comportamento real.

| regra | aplicacao |
| --- | --- |
| Owner obrigatorio | Cada item em `legacy/LIVE_LEGACY.md` precisa ter owner de dominio ou area responsavel. |
| Sinalizacao obrigatoria | O item deve estar listado como legado vivo, com local atual, motivo de permanencia e criterio de saida. |
| Sem feature nova | Legacy recebe correcao critica, seguranca ou ajuste para manter contrato; feature nova nasce no caminho canonico. |
| Sem segunda raiz | `legacy/` nao pode virar produto paralelo, pasta de despejo ou substituto de `backend/`. |
| Extracao segura | Mover codigo para `legacy/` exige import/rota preservada por shim, testes antes/depois e criterio de remocao. |
| Saida | Quando nao houver consumidor vivo, o item migra para archive ou remocao com pre-condicao comprovada. |

## 5. CRITERIOS DE MERGE

Um merge estrutural ou operacional so e aceitavel quando todos os criterios aplicaveis forem verdadeiros:

| criterio | regra |
| --- | --- |
| Classificacao | Todo item novo ou movido esta classificado como source, ops, docs, tests, compat, legacy, archive ou build gerado. |
| Caminho canonico | Nenhuma mudanca cria entrada principal concorrente, wrapper falso oficial ou doc viva duplicada. |
| Ownership | Area impactada e owner responsavel estao claros no PR ou na doc alterada. |
| Docs vivas | Comando, entrada, topologia, runbook ou politica afetados foram atualizados no mesmo change. |
| Compat/legacy | Se houve compat ou legacy, ha owner, sinalizacao, destino canonico e condicao de saida. |
| Testes | Testes da camada afetada foram executados ou a dispensa foi registrada com motivo. |
| Hygiene | Mudanca em raiz, docs vivas, scripts ou archive passa pelo validator de hygiene. |
| Release/ops | Mudanca em release, scheduler, backup, restore, worker ou smoke atualiza comandos/runbooks e valida trilha operacional. |
| Sem falso verde | Healthcheck, build ou processo subindo nao substituem validacao do fluxo afetado. |

Comandos minimos recomendados:

```powershell
.venv\Scripts\python.exe -m pytest tests\ops\test_repo_hygiene_validation.py
.venv\Scripts\python.exe -m pytest tests\architecture\test_architecture_boundaries.py
```

Use testes adicionais da camada tocada quando houver mudanca funcional, contrato HTTP, storage, jobs, release ou frontend.

## 6. CRITERIOS DE BREAKING CHANGE ESTRUTURAL

Breaking change estrutural e qualquer alteracao que mude como pessoas, CI, operacao ou codigo encontram o sistema.

Conta como breaking estrutural:

- remover, renomear ou mover pasta oficial da raiz;
- trocar entrypoint oficial de backend, frontend, worker, scheduler, backup, restore, smoke ou release gate;
- alterar contrato de env, storage, banco, release state ou Task Scheduler;
- remover compat/legacy ainda protegido por teste, doc, job, import ou consumidor externo;
- mudar fonte viva primaria de docs;
- alterar topologia oficial, allowlist de hygiene ou regra de entrada na raiz.

Regra obrigatoria para aprovar breaking estrutural:

1. Declarar no PR: `BREAKING STRUCTURE`.
2. Apontar caminho antigo, caminho novo e motivo.
3. Provar ausencia de consumidor ou definir janela de compatibilidade.
4. Atualizar README, docs vivas, comandos oficiais, runbooks, tests e validators afetados no mesmo change.
5. Registrar rollback ou plano de retorno.
6. Obter aceite do owner da area impactada e do owner estrutural de governanca.

Se qualquer item acima faltar, a mudanca deve ser tratada como refatoracao interna sem quebra publica ou deve ser recusada.

## 7. OWNERSHIP

Ownership aqui e papel de responsabilidade, nao cargo nominal. O PR deve deixar claro qual papel revisou ou assumiu a mudanca.

| area | owner primario | responsabilidade |
| --- | --- | --- |
| Topologia, raiz e governanca | Owner estrutural de governanca | Aprovar novas areas, excecoes, breaking estrutural e atualizacao das politicas. |
| Backend source | Owner backend | Garantir fronteiras de app, contratos, DB, storage, seguranca e testes da camada. |
| Frontend | Owner frontend | Garantir `frontend/src`, build, envs `FRONTEND_*` e validacao de navegacao quando aplicavel. |
| Operacao e release | Owner ops | Garantir comandos oficiais, scheduler, worker, backup/restore, smoke, release gate e runbooks. |
| Documentacao viva | Owner da area documental | Impedir doc concorrente e manter indice/fonte primaria atualizados. |
| Testes | Owner da camada de teste | Garantir cobertura minima para unidade, contrato, integracao, ops, arquitetura ou e2e. |
| Compat | Owner do destino canonico mais governanca | Manter shim fino, documentado e com condicao de saida. |
| Legacy | Owner de dominio mais governanca | Manter inventario vivo, impedir feature nova e conduzir extracao segura. |
| Archive/remocao | Owner que classificou o material mais governanca | Garantir que historico nao vire fonte viva e que remocao tenha pre-condicao comprovada. |

Quando uma mudanca cruza duas areas, ambos os owners precisam validar a fronteira. Exemplo: novo job que altera backend e scheduler precisa de owner backend e owner ops.

## 8. CONCLUSAO DA GOVERNANCA

O repositorio aceita apenas material com papel real, caminho canonico e owner claro. Compat e legacy continuam permitidos, mas sempre sinalizados, finos ou inventariados, com condicao de saida. Merge nao pode introduzir caminho falso principal. Breaking estrutural deixa de ser implicito: precisa ser declarado, documentado, testado, aceito pelos owners e acompanhado de rollback ou plano de compatibilidade.
