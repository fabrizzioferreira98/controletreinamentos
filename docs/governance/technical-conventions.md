# Convencoes tecnicas do repositorio

## Objetivo

Definir nomes e formatos oficiais para pastas, arquivos, scripts, docs e testes. A convencao segue a estrutura real do repositorio: backend Flask, frontend estatico separado, operacao Windows/self-hosted, compat explicito, legacy documentado e archive historico.

Convencao nao substitui classificacao semantica. Um nome correto no lugar errado continua errado.

## 1. Convencao de pastas

| area | convencao oficial |
| --- | --- |
| Raiz | Apenas as areas aprovadas em `docs/governance/repo-topology.md`: `.github`, `backend`, `frontend`, `ops`, `tests`, `docs`, `scripts`, `legacy` e `archive`. |
| Backend fonte | `backend/src/controle_treinamentos/<area>` em `snake_case` quando houver mais de uma palavra. O pacote principal continua `controle_treinamentos`. |
| Backend tools | `backend/tools/<papel>`: `runtime`, `maintenance`, `data`, `compat_residual` e `manual_unsafe`. Novo papel operacional nao nasce solto na raiz. |
| Frontend | `frontend/src` para fonte, `frontend/scripts` para build tooling e `frontend/dist` apenas como build gerado. |
| Ops | `ops/scripts/<dominio_operacional>` com nomes curtos por funcao real: `admin`, `backup`, `database`, `diagnostics`, `jobs`, `manuals`, `perf`, `qa`, `release`, `repo`, `smoke`. |
| Windows ops | `ops/windows/<area>` para `scripts`, `env`, `caddy` e outros recursos Windows/self-hosted. |
| Docs | `docs/<classe>`: `architecture`, `operations`, `governance`, `product`, `migration`, `archive`. Doc viva nao nasce fora dessas quatro primeiras classes vivas. |
| Tests | `tests/<camada>`: `architecture`, `contract`, `e2e`, `integration`, `ops`, `unit`. |
| Compat | Compat de CLI fica em `scripts/`; compat interno de app fica em `backend/src/controle_treinamentos/compat/`; residual operacional fica em `backend/tools/compat_residual/`. |
| Legacy | `legacy/` registra legado vivo por dominio. Nao e segunda raiz de codigo. |
| Archive | `archive/<classe>` guarda material historico classificado e registrado em `archive/MANIFEST.md`. |

## 2. Convencao de arquivos

| tipo | convencao oficial |
| --- | --- |
| Python de aplicacao | `snake_case.py`, nomeado pelo papel de dominio ou infraestrutura. |
| Python entrypoint | `run_*.py`, `bootstrap_*.py`, `*_worker.py`, `*_postcheck.py` ou nome equivalente ja usado pela trilha canonica. |
| Python manual/destrutivo | Nome explicito como `cleanup_*`, `run_*_repair.py` ou wrapper em `manual_unsafe`; precisa exigir confirmacao quando houver risco operacional. |
| Python validator | `validate_*.py` quando valida contrato, evidencia, hygiene ou checklist. |
| Python drill/smoke | `*_drill.py` para ensaio operacional; `*_smoke.py` para validacao curta de ambiente/pos-deploy. |
| Testes | `test_<assunto>.py`; o assunto deve indicar camada ou comportamento, nao apenas o modulo interno. |
| Frontend fonte | Arquivos base podem ser `app.js`, `lib.js`, `shell.js`, `app.css`, `index.html`; paginas separadas seguem `pages-<dominio>.js`. |
| Docs governance | Novos docs em `docs/governance` usam `lowercase-kebab.md`. |
| Docs operacionais | Manter nomes existentes quando ja sao fonte viva. Novos guias curtos usam `lowercase-kebab.md`; runbooks/checklists/templates podem usar `UPPER_SNAKE.md` ou `UPPER_SNAKE.json` se seguirem familia operacional existente. |
| Docs de migracao | Prefixo de etapa ou frente mais slug: `<frente>.<etapa>-<assunto>.md`, como `18.6.p2.5-governanca-compat-residual-final.md`. |
| Archive | Nome com contexto e, quando for snapshot/backup, data `YYYYMMDD` no proprio nome. |

Arquivos gerados (`*.pyc`, `__pycache__/`, `.ruff_cache/`, `frontend/dist/*`, caches e logs) nao definem convencao de codigo.

## 3. Convencao de scripts

| classe | convencao oficial |
| --- | --- |
| Entrada oficial de backend runtime | Fica em `backend/tools/runtime/`; `run.py` e `wsgi.py` sao nomes reservados para runtime local/export WSGI. |
| Entrada oficial de manutencao | Fica em `backend/tools/maintenance/`; deve delegar para implementacao real quando necessario e ser documentada em `docs/operations/canonical-commands.md`. |
| Script operacional vivo | Fica em `ops/scripts/<dominio>/`; pode ser implementacao chamada por `backend/tools`, release, smoke, QA, diagnostico ou drill. |
| Script Windows oficial | Fica em `ops/windows/scripts/`; PowerShell usa `Verb-Noun.ps1`, como `Invoke-AppService.ps1`. |
| Wrapper compat | Fica em `scripts/`, tem cabecalho ou aviso `COMPAT:`, permanece fino, delega para caminho canonico e aparece em `scripts/README.md` com fila de remocao. |
| Compat entry HTTP/import | Fica em `backend/src/controle_treinamentos/compat/`; nao recebe regra nova e precisa ter condicao de morte. |
| Manual/destrutivo | Fica em `backend/tools/manual_unsafe/` ou implementacao explicitamente marcada em `ops/scripts/database/`; nao pode parecer rotina recorrente. |
| Diagnostico | Fica em `ops/scripts/diagnostics/` ou `ops/scripts/qa/`, com nome que indique observacao/validacao, nao reparo. |
| Validator | Fica no dominio que valida: `ops/scripts/repo/validate_*.py` para hygiene estrutural, `ops/scripts/release/validate_*.py` para release/evidencia. |

Script novo precisa responder a tres perguntas antes de nascer: entrada oficial, implementacao operacional ou compat residual. Se nao couber em uma delas, a pasta esta errada.

## 4. Convencao de docs

| classe | convencao oficial |
| --- | --- |
| Doc viva arquitetural | `docs/architecture/`; descreve desenho atual e nao runbook operacional. |
| Doc viva operacional | `docs/operations/`; comandos, runbooks, release, backup, observabilidade, Windows e checklists vivos. |
| Doc viva de governanca | `docs/governance/`; topologia, politicas, convencoes, classificacao e limpeza. |
| Doc viva de produto | `docs/product/`; manual e comportamento visivel ao usuario. |
| Runbook | Deve morar em `docs/operations/` e apontar para scripts canonicos reais. Nao pode apontar para wrapper compat como trilha principal. |
| Checklist | Template vivo fica em `docs/operations/`; checklist preenchido de release fica fora do repo com evidencias ou em `docs/archive/operations/` quando houver valor historico. |
| Doc de migracao | `docs/migration/`; explica transicao, nao define operacao oficial. Deve apontar para doc viva quando houver risco de confusao. |
| Plataforma retirada | `docs/migration/retired-platforms/`; pode preservar nomes originais como `DEPLOY_RENDER.md` ou `vercel.json`, sem autoridade de deploy atual. |
| Doc arquivada | `docs/archive/`; nao recebe instrucao operacional nova e nao deve ser linkada como fonte de verdade. |

Toda doc viva nova deve entrar em `docs/README.md` ou em um indice vivo da sua area, e deve ser aceita pelo hygiene se houver allowlist.

## 5. Convencao de testes

| camada | convencao oficial |
| --- | --- |
| `tests/unit/` | Regras puras, helpers, seguranca local, serializacao, policies e unidades sem depender do fluxo completo. |
| `tests/integration/` | Interacao entre app, DB, repositorios, storage, monitoramento e componentes reais em conjunto. |
| `tests/contract/` | Contratos HTTP/API, respostas, CORS, erros, payloads e compatibilidade publica. |
| `tests/e2e/` | Jornadas criticas de usuario ou fluxo completo ponta a ponta. |
| `tests/ops/` | Scripts operacionais, hygiene, backup/restore, release, repo, evidencias e protecoes de operacao. |
| `tests/architecture/` | Fronteiras estruturais: raiz, imports, separacao backend/frontend/ops/docs/tests e proibicoes arquiteturais. |

Testes de compat devem nomear o compat explicitamente. Teste novo nao deve proteger caminho antigo sem tambem registrar condicao de saida em `docs/governance/removal-backlog.md`.

## 6. Regras curtas de aplicacao

- Oficial fica no caminho canonico, com nome que revele papel real.
- Compat fica fino, avisado e com destino canonico declarado.
- Manual/destrutivo fica isolado e nunca vira rotina por nome neutro.
- Diagnostico observa; reparo altera. O nome precisa deixar essa diferenca clara.
- Archive preserva historico, mas nao executa, nao builda e nao orienta operacao viva.
- Legacy so permanece enquanto houver consumidor real e criterio de saida registrado.
