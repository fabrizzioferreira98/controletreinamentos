# Politica de Entrada na Raiz

## Objetivo

Impedir que a raiz volte a acumular ambiente local, temporarios, copias historicas, exports ou scripts concorrentes. A raiz deve mostrar apenas a arquitetura e a operacao reais do produto.

## O que pode entrar na raiz

| item/tipo | condicao |
| --- | --- |
| Pasta oficial de produto | So se representar nucleo vivo permanente, com ownership claro e sem sobrepor `backend/` ou `frontend/`. |
| Pasta operacional | So se representar operacao transversal que nao caiba em `ops/`; por padrao, novos fluxos operacionais devem entrar em `ops/`. |
| Pasta de teste | So se representar validacao oficial que nao caiba em `tests/`; por padrao, novos testes devem entrar em `tests/`. |
| Pasta de docs | So se representar documentacao governada que nao caiba em `docs/`; por padrao, novas docs devem entrar em `docs/`. |
| Pasta de archive | So se representar material historico classificado que nao caiba em `archive/`; por padrao, novo historico deve entrar em `archive/`. |
| Compat/legacy com justificativa | So com consumidor real, motivo de permanencia, destino canonico, criterio de saida e registro em `docs/governance/legacy-policy.md`. |
| Arquivo de configuracao | Permitido quando for consumido por tooling, testes, build, lint, dependencias ou onboarding. |
| Documento de entrada | Permitido para `README.md`, `CONTRIBUTING.md` ou outro arquivo raiz essencial ao onboarding. |

## Categorias validas para nova pasta

Toda pasta nova na raiz deve cair em uma categoria antes de existir fisicamente:

| categoria | quando e valida | evidencia exigida |
| --- | --- | --- |
| nucleo vivo | Superficie permanente do produto, sem duplicar `backend/` ou `frontend/`. | Ownership, fonte real, participacao em build/teste/operacao e atualizacao de `repo-topology.md`. |
| operacao | Operacao real do produto, sem caber em `ops/`. | Comando, runbook, job, workflow ou fluxo operacional ativo. |
| teste | Validacao oficial que nao cabe em `tests/`. | Suite, fixture ou contrato com execucao documentada. |
| docs | Documentacao governada que nao cabe em `docs/`. | Fonte viva unica, owner e regra contra duplicidade documental. |
| archive | Historico classificado que nao cabe em `archive/`. | Motivo, origem, status e registro em manifesto/politica de arquivo. |
| compat/legacy com justificativa | Compatibilidade ou legado vivo fora do nucleo. | Consumidor real, substituto canonico, pre-condicao de remocao e risco de compatibilidade. |

## O que nao pode entrar na raiz

| item/tipo | motivo |
| --- | --- |
| Ambiente local como entrada oficial | `.venv/`, `.vscode/`, caches, `frontend/dist/` e estado de editor nao sao arquitetura; apenas excecoes locais explicitamente documentadas podem permanecer visiveis. |
| Temporarios e residuos | `.tmp/`, logs soltos, dumps e evidencias geradas contaminam leitura e devem ir para destino classificado ou descarte. |
| Copia de repositorio/produto | Cria segunda raiz aparente e compete com o nucleo vivo. |
| Build gerado | Deve ser reconstruivel a partir de fonte, nao governar a raiz. |
| Snapshot, backup ou dump | Nao entra na raiz nem na arvore viva por conveniencia; deve ir para `archive/repo-snapshots/`, `archive/temp-backups/`, `archive/old-wrappers/`, `docs/archive/` ou descarte, conforme classificacao. |
| Wrapper historico novo | Nao criar caminho paralelo sem consumidor real e sem delegacao fina para trilha canonica. |
| Manual ou doc concorrente | Deve consolidar na fonte viva por assunto ou ir para `docs/archive/`/`docs/migration/`. |
| Temporario generico | "Temporario", "teste rapido", "backup local" ou "por enquanto" nao justificam pasta na raiz. |
| Pasta com nome de produto/plataforma | Nome bonito ou amplo nao basta; se competir com o nucleo vivo, deve ser negada ou classificada fora da raiz. |

## Excecoes locais visiveis

| item | regra |
| --- | --- |
| `.venv/` | Pode existir apenas na raiz do workspace local para praticidade de desenvolvimento. Continua ignorada pelo Git, nao integra a topologia oficial e nao define release/operacao; quando citada em docs, vale apenas como exemplo local de interpretador Windows para chamar a trilha canonica. |
| `frontend/dist/` | Pode existir apenas no caminho canonico de build como saida gerada/publicavel. Continua ignorado pelo Git, nao integra a topologia oficial e nunca pode ser tratado como fonte, doc viva ou referencia arquitetural. |
| `.env` | Pode existir apenas na raiz do workspace local como configuracao sensivel gitignored. Nao integra a topologia oficial, nao pode ser template e nao substitui `.env.example`. |
| `runtime/` | Pode existir apenas na raiz do workspace local como scratch/evidencia mutavel gitignored. Nao integra a topologia oficial, nao e fonte, nao e release artifact oficial e nao deve ser referenciado como input canonico. |
| `ops/artifacts/` | Pode existir apenas como output/evidencia operacional historica gitignored. Nao integra a operacao versionada, nao e fonte viva e nao deve substituir pacote oficial de release/evidencia fora do repo. |

Essas excecoes toleram presenca fisica local, nao entrada semantica na raiz oficial.

## Avaliacao de saida futura das excecoes locais

| item | decisao atual | pre-condicao para mudar | custo/risco |
| --- | --- | --- | --- |
| `.venv/` | Permanecer como excecao local explicita e unica para ambiente Python dentro do workspace. | Documentacao oficial aceitar runner externo equivalente sem quebrar onboarding local; quando isso estiver consolidado, a excecao pode ser reavaliada. | Medio: remover agora sem trilha neutra consolidada aumentaria friccao local e ruido operacional. |
| `frontend/dist/` | Permanecer como excecao local explicita e unica para publish/build do frontend dentro do checkout. | Build/publish oficial fora do checkout ou limpeza automatica no fim da trilha precisa estar validada sem depender do artefato persistido. | Medio: remover a excecao agora deixaria build local e verificacao de publish sem caminho documentado. |
| `.env` | Permanecer como excecao local sensivel, nunca versionada. | Provisionamento local/Windows passar a depender somente de secret store externo ou env-file fora do checkout com onboarding validado. | Medio: remover agora quebraria bootstrap local descrito no README e aumentaria risco de improviso. |
| `runtime/` | Permanecer como excecao local de scratch/evidencia mutavel ignorada. | Runtime local e QA passarem a escrever em `APP_INSTANCE_PATH`/workspace externo por padrao validado. | Baixo/medio: apagar evidencia historica sem trilha externa reduziria auditabilidade local. |
| `ops/artifacts/` | Permanecer como excecao local de artifacts/evidencias historicas ignoradas. | Evidencias operacionais historicas serem migradas para storage externo ou pacote oficial assinado, com manifest preservado. | Medio: mover/apagar agora poderia perder material de auditoria de execucoes financeiras/prod. |

## Quando criar pasta nova

Nova pasta na raiz so e permitida quando todos os criterios forem verdadeiros:

1. Nao cabe semanticamente em `backend/`, `frontend/`, `ops/`, `docs/`, `tests/`, `archive/`, `scripts/` ou `legacy/`.
2. Tem categoria valida: nucleo vivo, operacao, teste, docs, archive ou compat/legacy com justificativa.
3. Nao duplica uma trilha existente.
4. Tem dono, README curto, regra de entrada, criterio de revisao e evidencia real.
5. A topologia oficial em `docs/governance/repo-topology.md` e o allowlist do hygiene sao atualizados no mesmo change.

Se algum criterio falhar, nao criar pasta na raiz.

## Criterios praticos por exemplo

| regra | evidencia exigida | exemplo |
| --- | --- | --- |
| Nucleo vivo novo | Build/teste/operacao dependem da pasta e ela nao duplica produto existente. | Negar `platform/` se for apenas outro nome para `backend/` + `frontend/`. |
| Operacao nova | Ha comando ou workflow real e `ops/` nao comporta o caso. | Preferir `ops/scripts/release/` para release, nao `release-tools/` na raiz. |
| Teste novo | Ha suite executada e `tests/` nao comporta o caso. | Preferir `tests/contract/` a `contract-tests/` na raiz. |
| Docs nova | Ha fonte viva unica e `docs/` nao comporta o caso. | Preferir `docs/operations/` a `runbooks/` na raiz. |
| Archive novo | Material ja esta classificado e `archive/` nao comporta o caso. | Preferir `archive/temp-backups/` a `old-backups/` na raiz. |
| Compat/legacy novo | Existe consumidor real, substituto canonico e condicao de saida. | Preferir `scripts/` para wrapper compat; negar `legacy-tools/` sem consumidor. |

## Quando usar cada area

| area | usar quando |
| --- | --- |
| `ops/` | Scripts, runbooks auxiliares, Windows self-hosted, release, smoke, drills, diagnosticos e automacoes operacionais vivas. |
| `docs/` | Documentacao viva, governanca, produto, arquitetura, operacao, migracao e arquivo documental governado. |
| `archive/` | Snapshot, backup, wrapper morto, material historico ou artefato sem papel operacional vivo, sempre com classificacao previa. |
| `legacy/` | Codigo ou fluxo ainda vivo por dependencia real, mas nao canonico; exige motivo de permanencia e criterio de extracao. |

Para decidir entre compat, legacy, archive ou remocao, use `docs/governance/legacy-policy.md`.

## Direcionamento de material arquivavel

Novo backup, snapshot, dump, copia aninhada ou residuo com valor historico nunca deve ser criado na raiz ou em `backend/`, `frontend/`, `ops/`, `scripts/` ou `tests/` como atalho local. Se precisar ser preservado no repo, nasce classificado em `archive/` e registrado em `archive/MANIFEST.md`; se for operacional, sensivel ou sem valor historico, deve ficar fora do repo ou ser removido.

## Revisao minima

Antes de aceitar nova entrada na raiz, verificar:

- existe area atual que comporta o item;
- o item nao e local, temporario, historico ou gerado;
- comandos oficiais continuam em `docs/operations/canonical-commands.md`;
- docs vivas nao passam a concorrer;
- a raiz continua com uma unica arvore de produto.
