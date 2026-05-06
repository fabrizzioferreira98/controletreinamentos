# Topologia oficial do repositorio

## 1. Objetivo

Este documento congela a semantica da raiz do repositorio. A raiz representa o produto real em operacao self-hosted Windows: backend Flask, frontend estatico separado, operacao em `ops`, testes em `tests` e documentacao em `docs`.

Nao ha segunda pasta autorizada a representar o produto principal.

A governanca formal de entrada, merge, breaking estrutural e ownership fica em `docs/governance/repository-governance.md`. A politica de entrada para novas pastas ou arquivos na raiz fica em `docs/governance/root-entry-policy.md`. A politica de transicao entre compat, legacy, archive e remocao fica em `docs/governance/legacy-policy.md`.

## 2. Topologia oficial da raiz

Entradas oficiais ou aceitas na raiz:

- `.github/` - governanca de CI, release e higiene.
- `backend/` - backend Flask, runtime local e ferramentas de manutencao.
- `frontend/` - frontend oficial separado, com fonte em `src/` e build tooling em `scripts/`.
- `ops/` - operacao oficial, Windows self-hosted, release, smoke, drills e higiene.
- `tests/` - suites oficiais de validacao.
- `docs/` - documentacao oficial e legado isolado.
- `scripts/` - aliases historicos de compatibilidade.
- `archive/` - artefatos historicos fora da operacao viva.
- `legacy/` - area de legado vivo real, ainda fora do nucleo canonico e dependente de extracao segura.
- Arquivos de raiz - `README.md`, `CONTRIBUTING.md`, `Makefile`, `pyproject.toml`, `pytest.ini`, `requirements*.txt`, `.env.example`, `.gitignore` e `.python-version`.

## 3. Estrutura-alvo oficial

Esta e a arvore-alvo oficial do repositorio. Ela reflete a operacao real atual; nao e um desenho futuro idealizado. Quando a arvore fisica divergir desta referencia, a divergencia deve ser classificada como excecao local, compat, legacy, archive, build gerado ou item proibido.

```text
.
|-- .github/
|-- backend/
|   |-- src/controle_treinamentos/
|   |   |-- api/
|   |   |-- application/
|   |   |-- blueprints/
|   |   |-- bootstrap_data/
|   |   |-- compat/
|   |   |-- contracts/
|   |   |-- core/
|   |   |-- db/
|   |   |-- infra/
|   |   |-- monitoring/
|   |   |-- reports/
|   |   |-- repositories/
|   |   |-- service_layers/
|   |   |-- static/
|   |   |-- templates/
|   |   |-- ui/
|   |   `-- __init__.py
|   `-- tools/
|       |-- compat_residual/
|       |-- data/
|       |-- maintenance/
|       |-- manual_unsafe/
|       `-- runtime/
|-- frontend/
|   |-- scripts/
|   `-- src/
|-- ops/
|   |-- scripts/
|   `-- windows/
|-- tests/
|   |-- architecture/
|   |-- contract/
|   |-- e2e/
|   |-- integration/
|   |-- ops/
|   `-- unit/
|-- docs/
|   |-- architecture/
|   |-- archive/
|   |-- governance/
|   |-- migration/
|   |-- operations/
|   `-- product/
|-- scripts/
|-- legacy/
|-- archive/
|-- README.md
|-- CONTRIBUTING.md
|-- Makefile
|-- pyproject.toml
|-- pytest.ini
|-- requirements.txt
|-- requirements-dev.txt
|-- .env.example
|-- .gitignore
`-- .python-version
```

Leitura obrigatoria:

- `backend/src/controle_treinamentos/` e fonte da aplicacao Flask.
- `backend/tools/` e operacional, apesar de morar em `backend/`; ele existe para entrypoints de runtime, manutencao recorrente, import manual, compat residual e acoes manuais perigosas.
- `frontend/src/` e fonte do frontend separado; `frontend/scripts/` e build tooling; `frontend/dist/` e saida gerada local/publicavel, mas nao integra a topologia oficial do repo.
- `ops/` e operacao transversal: Windows self-hosted, release, smoke, QA, diagnostico, drills e hygiene.
- `scripts/` e somente compat historico; nao recebe fluxo novo.
- `legacy/` documenta legado vivo ainda acoplado ao backend real; nao e segunda raiz de codigo.
- `archive/` preserva historico classificado; nao e codigo vivo, restore oficial, build, teste ou release.

## 4. O que deve existir

| item | motivo |
| --- | --- |
| `.github/` | Workflows, Dependabot e governanca automatizada do repositorio. |
| `backend/src/controle_treinamentos/` | Nucleo vivo Flask: app factory, blueprints, APIs, dominio, contratos, DB, infra, templates SSR ainda vivos e compat interno. |
| `backend/tools/runtime/` | Entradas de runtime local e export WSGI auxiliar. |
| `backend/tools/maintenance/` | Entradas canonicas de manutencao recorrente da aplicacao: bootstrap estrutural, seed, backup, worker, notificacoes, consistencia e pos-restore. |
| `backend/tools/manual_unsafe/` | Repair e cleanup destrutivos isolados da trilha normal. |
| `backend/tools/compat_residual/` | Entradas residuais que precisam existir sem parecer fluxo canonico. |
| `backend/tools/data/` | Imports manuais de dados, separados de bootstrap e seed canonicos. |
| `frontend/src/` | Fonte do frontend estatico separado. |
| `frontend/scripts/` | Build tooling do frontend. |
| `ops/scripts/` | Operacao viva: admin, backup drills, database manual, diagnostics, jobs drills, manuals, perf, QA, release, repo hygiene e smoke. |
| `ops/windows/` | Operacao Windows/self-hosted: env templates, Caddy, servicos, firewall, Task Scheduler e wrappers PowerShell oficiais. |
| `tests/` | Suites oficiais de arquitetura, contrato, e2e, integracao, ops e unidade. |
| `docs/architecture/`, `docs/operations/`, `docs/governance/`, `docs/product/` | Documentacao viva por assunto. |
| `docs/migration/` | Registros de transicao que explicam contexto, sem autoridade operacional. |
| `docs/archive/` | Historico documental, sem autoridade como fonte viva. |
| `scripts/` | Wrappers de compatibilidade historica ja classificados e com fila de remocao. |
| `legacy/` | Inventario de legado vivo real com criterio de saida. |
| `archive/` | Snapshots, backups, wrappers antigos e copias historicas classificados em `archive/MANIFEST.md`. |
| Arquivos de raiz aceitos | Onboarding, dependencias, testes, lint, ambiente exemplo e configuracao basica do repo. |

## 5. O que nao deve existir

| item | motivo |
| --- | --- |
| `controle-treinamentos/` aninhado na raiz | Cria segunda arvore aparente do produto principal. |
| `.tmp/` | Mistura temporarios, backups e residuos com fonte viva. |
| `.ruff_cache/`, `.pytest_cache/`, `.mypy_cache/`, `__pycache__/` | Caches de tooling ou bytecode; nao sao arquitetura. |
| `backend/runtime/`, `logs/`, `ops/evidence/`, `ops/backups/` | Estado mutavel, evidencias vivas e backups nao pertencem a operacao versionada. |
| `runtime/`, `ops/artifacts/` como fonte versionada ou autoridade operacional | Podem existir apenas como excecoes locais gitignored de output/evidencia historica; nunca como fonte viva, input canonico, release oficial ou documentacao governante. |
| `.env` como arquivo versionado, template ou documento | Pode existir apenas como configuracao sensivel local gitignored na raiz; templates oficiais continuam em `.env.example` e `*.env.example`. |
| `frontend/dist/`, `frontend/dist-*`, `frontend/dist-preview*` como fonte versionada ou referencia arquitetural | Build gerado deve ser reconstruido a partir de `frontend/src/`; apenas `frontend/dist/` pode aparecer localmente como excecao explicita de build. |
| Dumps, snapshots, backups ou arquivos compactados soltos na raiz | Historico classificavel deve entrar em `archive/`; material sensivel ou sem valor historico deve ficar fora do repo ou ser removido. |
| Novas pastas de script concorrente, como `release-tools/`, `runbooks/`, `contract-tests/` ou `legacy-tools/` | Ja existem areas canonicas (`ops/`, `docs/`, `tests/`, `legacy/`); nova raiz so e permitida com justificativa formal. |
| Docs vivas soltas fora de `docs/architecture`, `docs/operations`, `docs/governance` ou `docs/product` | Documento vivo precisa ter owner, assunto e governanca claros. |
| Novo wrapper em `scripts/` sem consumidor real, aviso `COMPAT:` e destino canonico | Compat nao pode virar segunda trilha operacional. |

## 6. Excecoes permitidas

| item | por que e excecao |
| --- | --- |
| `.venv/` | Excecao local explicita: pode existir apenas na raiz do workspace para conveniencia de desenvolvimento, continua ignorada pelo Git e nao define a topologia oficial. |
| `frontend/dist/` apos build local | Excecao local explicita no caminho canonico de build. Pode existir como saida gerada/publicavel, mas nao e fonte viva, nao recebe edicao manual e nao muda a topologia oficial. |
| `.env` | Excecao local sensivel: pode existir apenas na raiz do workspace para runtime local, continua ignorada pelo Git e nao substitui `.env.example`. |
| `runtime/` | Excecao local de scratch/evidencia mutavel: pode existir apenas na raiz, continua ignorada pelo Git e nao e fonte, release artifact oficial ou documentacao. |
| `ops/artifacts/` | Excecao local de artefatos/evidencias operacionais historicas: pode existir apenas como output gitignored, sem autoridade como fonte viva ou input canonico. |
| `scripts/` | Excecao temporaria de compatibilidade para consumidores antigos; deve permanecer fino, documentado e sem novos fluxos. |
| `backend/src/controle_treinamentos/compat/` | Compat interno de imports e entrypoints antigos; codigo novo nao nasce ali. |
| `legacy/` | Container de legado vivo documentado; continua enquanto `legacy/LIVE_LEGACY.md` tiver consumidores reais e criterios de saida pendentes. |
| `archive/temp-backups/nested-repo-copy-20260415/` | Copia aninhada preservada como historico classificado; nao e raiz alternativa e deve sair quando nao houver dependencia externa ou valor de auditoria. |
| `docs/migration/retired-platforms/` | Preserva plataformas retiradas; nao e guia de deploy atual. |

## 7. Pastas oficiais

- `.github/` participa da governanca automatizada do repositorio.
- `backend/` contem o nucleo vivo da aplicacao e seus entrypoints oficiais.
- `frontend/` contem o frontend oficial; `frontend/src` e `frontend/scripts` sao a superficie viva. `frontend/dist` e apenas a saida gerada do build.
- `ops/` contem a operacao real do produto.
- `tests/` contem a validacao oficial de arquitetura, contratos, unidade, integracao, ops e e2e.
- `docs/` contem a documentacao oficial. A governanca de docs fica em `docs/governance/documentation-governance.md`. Subpastas de migracao aposentada nao tem autoridade operacional.

## 8. Pastas auxiliares

- `scripts/` permanece apenas como compatibilidade para caminhos historicos. Novos fluxos devem nascer nos caminhos canonicos indicados pelo `README.md`.
- `archive/` preserva artefatos historicos e nao participa de build, teste, release ou operacao.
- `legacy/` registra legado vivo real com dependencia confirmada. Codigo so deve ser movido para la quando imports, rotas, testes e runbooks permitirem extracao segura.
- Arquivos de configuracao na raiz sustentam instalacao, testes, lint, contribuicao e onboarding.

## 9. Pastas legadas

- `.tmp/`, quando presente, e arquivo morto local classificado em `docs/governance/tmp-classification.md`. Nao e fonte de codigo, build, release ou operacao. A etapa 7.1 removeu a ocorrencia conhecida da raiz.
- `docs/migration/retired-platforms/` preserva artefatos de plataformas descontinuadas. Nao e guia de deploy.
- `controle-treinamentos/`, quando presente dentro da raiz, e copia legada aninhada classificada em `docs/governance/nested-repo-classification.md`. A ocorrencia conhecida foi movida para `archive/temp-backups/nested-repo-copy-20260415/` na etapa 7.3.

## 10. Pastas proibidas na raiz

Estas entradas nao devem existir como parte da topologia oficial nem competir semanticamente com o produto:

- `controle-treinamentos/` - cria uma segunda arvore com aparencia de produto principal; deve permanecer ausente da raiz.
- `.tmp/` - mistura residuos historicos com fonte viva; deve permanecer ausente.
- `.ruff_cache/`, `.pytest_cache/`, `.mypy_cache/`, `__pycache__/` - caches de tooling ou bytecode; nao sao arquitetura.
- `backend/runtime/`, `logs/` - estado mutavel de execucao fora das excecoes locais.
- `ops/evidence/`, `ops/backups/` - evidencias vivas e backups operacionais nao pertencem a operacao versionada.
- `runtime/` e `ops/artifacts/` como fonte, input canonico, release oficial ou documentacao - permitidos apenas como excecoes locais gitignored descritas abaixo.
- `frontend/dist-*`, `frontend/dist-preview*` e qualquer build frontend fora do caminho canonico - residuos gerados; devem ser reconstruidos a partir de `frontend/src` e nao entram como excecao local.

## 11. Itens locais tolerados no workspace

Somente estas excecoes locais podem aparecer fisicamente sem contaminar a topologia oficial:

- `.venv/` na raiz do workspace, como conveniencia local de interpretador/dependencias para desenvolvimento. Ela continua ignorada pelo Git; comandos oficiais podem usar `.venv\Scripts\python.exe` como exemplo local de Windows, mas a autoridade canonica continua sendo o entrypoint/script chamado.
- `frontend/dist/` no caminho canonico de build, como saida gerada/publicavel. Ela continua ignorada pelo Git, deve ser reconstruivel a partir de `frontend/src/` e nunca pode ser tratada como fonte ou criterio arquitetural.
- `.env` na raiz do workspace, como configuracao sensivel local. Ela continua ignorada pelo Git e nao substitui `.env.example`.
- `runtime/` na raiz do workspace, como scratch/evidencia mutavel local. Continua ignorado pelo Git e nao e fonte, release artifact oficial ou documentacao.
- `ops/artifacts/` como output/evidencia historica local. Continua ignorado pelo Git e nao e fonte viva nem input canonico.

Qualquer outra pasta local visivel na raiz ou na arvore viva continua sujeita ao hygiene como sujeira estrutural.

## 12. Excecoes temporarias, se houver

- `scripts/` e uma excecao temporaria de compatibilidade. Deve continuar sem novos fluxos ate consolidacao futura.
- `docs/migration/retired-platforms/` pode permanecer para preservacao historica, desde que nao seja referenciado como operacao vigente.
- Itens proibidos que ainda existam fisicamente continuam sendo sujeira estrutural; o hygiene deve permanecer verde sem depender de tolerancia silenciosa fora das excecoes locais explicitas acima.
