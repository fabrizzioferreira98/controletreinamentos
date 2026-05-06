# Frontend App

Frontend separado do produto autenticado.

Fonte canonica operacional: a tabela oficial de tarefas, comandos e caminhos fica em `docs\operations\canonical-commands.md`.

Fonte viva de estrutura, convencoes e integracao frontend/backend: `docs\architecture\FRONTEND_ARCHITECTURE.md`.

## Build

Da raiz do repositorio:

```powershell
.venv\Scripts\python.exe frontend\scripts\build_frontend.py --env-file frontend\.env.example
```

Da pasta `frontend\`, apenas como conveniencia local:

```powershell
& "..\\.venv\\Scripts\\python.exe" ".\\scripts\\build_frontend.py"
```

Opcionalmente informe um arquivo `.env`:

```powershell
& "..\\.venv\\Scripts\\python.exe" ".\\scripts\\build_frontend.py" --env-file ".env.example"
```

O build gera arquivos estaticos em `dist/`.

Contrato atual de build:

- `index.html` aponta para entrypoints fingerprintados por nome (`<arquivo>.<build_utc>.<hash>.js|css`);
- `asset-manifest.json` registra `entrypoints` e o mapa completo de assets fingerprintados;
- `?v=` nao e usado como estrategia principal de versionamento da SPA.

## Estrategia

- app estatico separado, mas nao autonomo em runtime
- roteamento por hash
- autenticacao via cookie de sessao + CSRF
- consumo de `/api/v1/...`
- deploy separado do backend

O build gera artefato estatico. Para runtime real, esse artefato precisa ser servido por HTTP externo e alinhado com `FRONTEND_*` no backend. `frontend/dist/` sozinho nao prova navegacao, login, CORS/origins ou publicacao homolog/producao.

## Design system fundacional v1

Fonte canonica de design:

- tokens semanticos globais em `backend/src/controle_treinamentos/static/styles.css`;
- o build concatena essa base com `frontend/src/app.css`, entao novos estilos devem preferir tokens canonicos antes de valores soltos;
- aliases legados continuam ativos para preservar markup existente.

Tokens canonicos mínimos:

- cor: `--color-background`, `--color-foreground`, `--color-foreground-muted`, `--color-surface`, `--color-surface-muted`, `--color-border`, `--color-primary`, `--color-secondary`, `--color-success`, `--color-warning`, `--color-error`, `--color-info`;
- tipografia: `--font-family-base`, `--font-size-caption`, `--font-size-small`, `--font-size-meta`, `--font-size-body`, `--font-size-body-lg`, `--font-size-section`, `--font-size-title`, `--font-weight-regular`, `--font-weight-medium`, `--font-weight-strong`, `--font-weight-emphasis`;
- spacing: `--space-1` a `--space-8`;
- superficie: `--border-default`, `--border-subtle`, `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-xl`, `--radius-pill`, `--shadow`, `--shadow-soft`, `--shadow-raised`, `--shadow-focus`.

Aliases compatíveis:

- variaveis antigas como `--bg`, `--panel`, `--text`, `--muted`, `--border`, `--accent`, `--green`, `--yellow`, `--red` e `--gray-soft` apontam para os tokens canonicos quando possivel;
- classes antigas criticas como `.panel`, `.card`, `.summary-card`, `.report-summary-card`, `.status-pill`, `.filters`, `.form-grid`, `.table-wrap`, `.empty`, `.flash`, `.button-link` e `.link-danger` continuam funcionando;
- esses aliases sao ponte de migracao, nao contrato para novos estilos.

Estados mínimos:

- botoes e links visuais suportam `:disabled`, `[disabled]`, `[aria-disabled="true"]`, `[data-busy="1"]` e `.is-loading`;
- campos suportam `:disabled`, `[aria-disabled="true"]`, `:read-only`, `[aria-readonly="true"]` e `.readonly-field`;
- estados visuais devem corresponder a comportamento real no JavaScript ou no HTML.

Legado congelado nesta fase:

- familias visuais especificas de login, monitor, mapas e relatorios densos ainda podem ter valores locais;
- novas telas nao devem copiar esses valores locais sem antes tentar compor com os tokens canonicos;
- consolidacao completa de componentes de produto fica para fases posteriores.

## Shared UI foundation

A fundacao visual incremental vive em `frontend/src/shared/ui/`:

- `tokens.css`: tokens semanticos frontend sobre a base CSS canonica;
- `primitives.css`: primitives neutros de dominio para composicao pequena;
- `README.md`: regra curta de adocao.

O build concatena `shared/ui` antes de `app.css`. Esta fundacao nao e redesign, nao e UI kit completo e nao deve receber regra de dominio.

## Shell/layout foundation

O shell autenticado adota a fundacao visual de forma incremental:

- `render-shell.js` marca container, sidebar, navegacao, topbar e content com primitives neutras de `shared/ui`;
- `app.css` aplica tokens de layout, inverse surface, navegacao, spacing e camadas sobre o shell;
- paginas funcionais seguem fora desta etapa e devem migrar por blocos proprios.

## Priority page foundation

A primeira superficie funcional com adocao visual incremental e `dashboard/tripulantes`:

- `features/dashboard/page.js` usa wrappers e primitives de `shared/ui` para header, feedback, paineis e cards operacionais;
- `features/tripulantes/list-page.js` usa wrappers e primitives para header, painel de lista, filtros, tabela e paginacao;
- `app.css` mantem o bloco G03 escopado a `.dashboard-page-shell`, `.tripulantes-page-shell` e `.priority-page-surface`.

A segunda superficie funcional com adocao visual incremental e `treinamentos/relatorios`:

- `features/treinamentos/list-page.js` usa wrappers e primitives para header, selecao, workbench, cards e registros;
- `features/training-root/page.js` usa wrappers e primitives para filtros, tabs, formularios e tabelas de cadastro raiz;
- `features/relatorios/*.js` usa wrappers e primitives para headers, filtros, cards, tabelas, contexto e evidencias;
- `app.css` mantem o bloco G04 escopado a `.training-reports-page-shell`, `.training-program-panel`, `.training-root-panel`, `.training-report-panel` e `.training-reports-table-wrap`.

Redesign amplo continua fora desta fase.

## Visual readiness second wave

G05 consolida a segunda onda visual como `pronta_para_proxima_fase_visual`:

- `shared/ui` segue como base comum de tokens e primitives neutros;
- shell/layout, `dashboard/tripulantes` e `treinamentos/relatorios` convergem em `priority-page-surface`, `ui-surface`, `ui-stack`, `ui-feedback` e tokens de spacing/surface/radius/shadow;
- a proxima fase pode expandir a linguagem visual por superficie ou por familia concreta de UI, como tabelas e formularios;
- CSS historico, tabelas densas, formularios profundos e static CSS backend permanecem como `divida_visual_controlada`, nao como resolvidos.

## Shared table/form patterns

G06 adiciona padroes pequenos e reutilizaveis em `shared/ui`:

- tabelas: `ui-table-wrap`, `ui-table-density-compact`, `ui-table-actions`, `ui-table-state`;
- formularios: `ui-form-toolbar`, `ui-form-grid`, `ui-form-actions`, `ui-field-help`;
- adocao inicial: tripulantes, treinamentos, cadastro raiz, relatorios e formularios profundos ja tratados;
- aliases legados como `table-wrap`, `filters-bar`, `form-grid` e `form-actions` continuam por compatibilidade, mas novos pontos devem preferir as primitives quando houver uso real.

## Third priority surface foundation

G07 escolhe `tripulante_form_detail` como terceira superficie prioritaria:

- rotas vivas: `#/tripulantes/new` e `#/tripulantes/<id>`;
- motivo: formulario profundo, upload de foto/PDF, tabela de anexos e baixo acoplamento SSR;
- adocao: `tripulante-detail-page-shell`, `priority-page-surface`, `ui-surface`, `ui-stack`, `ui-cluster`, `ui-form-*`, `ui-table-*` e `ui-field-help`;
- restricao: sem mudanca de submit, delete, upload, validacao, endpoints, rota ou loader.
- registro material do refino da Zona A (cabecalho + intake + feedback unificado do upload de documentos): `docs\\migration\\35.tripulante-document-upload-zona-a-refatoracao.md`.
- registro material do refino das Zonas B/C (biblioteca mestre + painel de detalhe forte + barra unica de acoes): `docs\\migration\\35.tripulante-document-zonas-bc-master-detail-refino.md`.

## Shared real components

G08 consolida apenas componentes compartilhados com reutilizacao comprovada:

- `ui-page-shell`: wrapper estrutural de pagina adotado em dashboard, tripulantes, treinamentos, cadastro raiz, relatorios e `tripulante_form_detail`;
- `ui-page-header`: header estrutural de pagina adotado nas mesmas superficies;
- aliases locais como `priority-page-surface` e `priority-page-header` continuam por compatibilidade e classificacao dos blocos anteriores;
- headers internos, toolbars, summary cards e previews seguem locais ate provarem reutilizacao estavel.

## Visual readiness third wave

G09 consolida a terceira onda visual como `pronta_para_expansao_visual`:

- `shared/ui` segue pequeno, neutro e reutilizavel;
- shell/layout e as tres superficies priorizadas convergem em page primitives, surfaces, feedbacks, table/form patterns e tokens semanticos;
- `ui-page-shell` e `ui-page-header` sao componentes compartilhados reais, nao aliases de dominio;
- a proxima expansao pode ser quarta superficie ou refinamento visual controlado;
- aliases locais, headers internos, toolbars, summary cards, previews, CSS legado/backend e familias historicas seguem como divida visual controlada.

## Fourth priority surface foundation

G10 escolhe `training_record_detail` como quarta superficie prioritaria:

- rota viva: `#/treinamentos/<id>`;
- motivo: formulario profundo, anexos PDF, tabela de evidencias e baixo acoplamento SSR;
- adocao: `training-record-detail-page-shell`, `priority-page-surface`, `ui-page-shell`, `ui-page-header`, `ui-surface`, `ui-stack`, `ui-cluster`, `ui-form-*`, `ui-table-*` e `ui-field-help`;
- restricao: sem mudanca de rota, loader, guard, submit, delete, upload, links de anexo, endpoints ou runtime.

## Visual final expansion readiness

G11 consolida a expansao visual atual como `pronta_para_encerramento_da_fase`:

- `shared/ui` segue pequeno, neutro e reutilizavel;
- shell/layout e quatro superficies reais usam a linguagem visual comum;
- `ui-page-shell`, `ui-page-header`, `ui-table-*` e `ui-form-*` sao suficientes para esta fase;
- aliases locais, CSS compat, headers internos, toolbars, summary cards e previews seguem como divida visual controlada;
- a proxima acao correta e consolidacao executiva final desta fase, nao quinta superficie nem redesign amplo.

## Surface removal

Registro ativo de superficies retiradas:

- `docs\migration\84.frontend-remove-painel-tv-produtividade-superficies.md`: remove Painel TV e Produtividade da experiencia frontend, incluindo navegacao, rotas SPA, paginas, CTAs, links compat expostos e microcopy.

## Dashboard isolated local refinements

O Dashboard passou a aceitar refinamentos estritamente locais sem reabrir shell/layout:

- `features/dashboard/page.js` concentra o header local da rota `#/dashboard` e pode comunicar a finalidade da pagina sem duplicar a topbar;
- o header local remove kicker redundante, usa titulo/subtitulo funcionais e trata o rail de acoes como camada utilitaria permissionada;
- o antigo banner superior pode ser tratado como `priority strip` compacto, orientando a ordem de triagem sem voltar a semantica de alerta generico permanente;
- o `entry layer` superior pode agrupar acoes rapidas por intencao (`Registrar` e `Monitorar`) e incluir contexto operacional imediato compacto, sem mexer nos blocos inferiores;
- os 3 cards superiores podem evoluir como atalhos operacionais com contagem, com criticidade visual clara entre `Vencidos`, `Ate 7 dias` e `Ate 30 dias`, sem virar KPI hero generico;
- a camada de prioridade/KPIs pode reduzir texto descritivo longo e operar com valor, share e estado de tratativa para melhorar escaneabilidade sem virar dashboard generica;
- a faixa superior pode ser consolidada por um wrapper local nao visual (`dashboard-top-cluster`), preservando um gap mais curto entre header, strip e cards e uma transicao mais clara para a fila critica;
- `Visao geral dos status` pode evoluir como painel compacto de distribuicao, com total monitorado, faixa de proporcao unica e grade interna mais densa, sem tocar `Base operacional`;
- o resumo superior de `Visao geral dos status` pode receber calibracao responsiva local por breakpoint (desktop/notebook/tablet), com colapso mais cedo entre `BASE MONITORADA`, numero principal e texto de apoio, sem tocar os cards internos;
- os itens internos de `Visao geral dos status` podem receber polish responsivo proprio, separando ponto/label, numero, percentual e apoio operacional em hierarquia local, sem reabrir macroestrutura;
- registro material do refino responsivo dos cards internos de `Visao geral dos status`: `docs\migration\35.dashboard-status-cards-responsive-hierarchy.md`;
- registro material da calibracao de breakpoint intermediario de `Visao geral dos status`: `docs\migration\35.dashboard-status-intermediate-breakpoint-calibration.md`;
- registro material de fechamento formal da frente responsiva de `Visao geral dos status`: `docs\migration\35.dashboard-status-final-consolidacao.md`;
- registro material do hotfix pos-screenshot de quebra de labels nos cards internos de `Visao geral dos status`: `docs\migration\35.dashboard-status-label-wrap-hotfix.md`;
- `Base operacional` pode evoluir como inventario navegavel denso, com resumo agregado, minicards mais contidos e menos heranca visual de `summary-card` dentro de `panel`;
- os minicards de `Base operacional` podem receber polish responsivo proprio, separando label, numero, contexto e CTA discreta sem tocar `Visao geral dos status`;
- a faixa intermediaria pode ser consolidada com grid proprio, heads compartilhados e loading coerente, evitando que `Visao geral dos status` e `Base operacional` fiquem bons isoladamente, mas ruins juntos;
- a faixa intermediaria pode receber calibragem especifica de notebook/tablet, com grid externo menos assimetrico, colapso em `1120px`, grids internos em duas colunas quando houver largura util e colapso mobile controlado;
- os overrides continuam escopados a `.dashboard-page-shell`, preservando sidebar, topbar, shell e CSS legado como base estrutural;
- priority strip, cards e fila critica seguem como camadas separadas, permitindo iteracao por bloco sem redesign global.
- a coluna `Acao` da `Fila critica` pode receber polish local de CTA de linha (secundario, denso e discreto), com largura/alinhamento estaveis e sem promover o link para bloco primario em card mode.
- a coluna `Acao` da `Fila critica` pode receber calibracao responsiva por breakpoint (desktop/notebook/tablet/intermediario), com largura elastica, ajuste de sizing do CTA e colapso controlado sem alterar contrato funcional.
- a microcopy da acao de linha da `Fila critica` pode ser contextualizada de forma minima por status (`Regularizar` para critico e `Abrir` para demais), reaproveitando `trainingStatusClass` e sem alterar rota, permissao, contrato ou comportamento.
- com polish visual, calibracao responsiva e microcopy contextual minima concluidos, a frente local da coluna `Acao` pode ser tratada como consolidada para este ciclo sem abrir redesign lateral.
- com a validacao local concluida, a faixa superior pode ser tratada como `fechada` para este ciclo: header, priority strip e cards ficaram consolidados, com contratos preservados e responsividade controlada.
- registro material do refino premium da faixa superior (`entry layer`): `docs\\migration\\35.dashboard-entry-layer-superior-refino.md`.
- registro material do refino da camada de prioridade/KPIs: `docs\\migration\\35.dashboard-kpi-priority-operational-refino.md`.
- registro material do refino operacional da `Fila critica` (hierarquia de cabecalho/filtros/tabela e protagonismo de regularizacao): `docs\\migration\\35.dashboard-critical-queue-operational-refino.md`.
- registro material do refino de card system da `Base operacional` (compacidade, hierarquia label/numero/CTA e reducao de ruido): `docs\\migration\\35.dashboard-base-operational-card-system-refino.md`.
- registro material do refino do `Calendario de vencimentos` como superficie secundaria (leitura mensal, protagonismo tatico e detalhe do dia): `docs\\migration\\35.dashboard-calendar-secondary-surface-refino.md`.
- registro material da calibracao responsiva final da dashboard (desktop/notebook/tablet) com estabilidade de hierarquia, cards e grids: `docs\\migration\\35.dashboard-responsive-breakpoint-calibration.md`.
- registro material da consolidacao final e readiness de release da frente da nova dashboard: `docs\\migration\\35.dashboard-final-consolidacao-release-readiness.md`.
- registro material da reanalise de paridade visual com o mock aprovado: `docs\\migration\\35.dashboard-reference-visual-parity-reanalysis.md`.
- registro material do hotfix de responsividade da grade KPI (ocupacao de colunas no breakpoint intermediario): `docs\\migration\\35.dashboard-responsive-kpi-grid-hotfix.md`.
- registro material do refino visual do calendario com novo bloco tatico abaixo da grade mensal: `docs\\migration\\35.dashboard-calendar-visual-tactical-support-block.md`.
- registro material da auditoria linguistica e do refino de UX writing da dashboard: `docs\\migration\\35.dashboard-ux-writing-qa-linguistico.md`.
- registro material do hardening visual da composicao `Fila critica` + `Calendario`, com correcoes de hierarquia, borda e overflow: `docs\\migration\\35.dashboard-critical-calendar-visual-hardening.md`.
