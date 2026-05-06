# Frontend real

Esta e a fonte viva curta da frente 30.2. Ela descreve a estrutura real do frontend hoje, sem design system, sem nova arquitetura e sem tratar build gerado como fonte.

## 1. Estrutura real

| item | papel real |
| --- | --- |
| `frontend/src/index.html` | HTML base do app estatico; carrega `config.js`, `app.css` e `app.js` como modulo. |
| `frontend/src/app.js` | Entrypoint fino do frontend; delega a inicializacao para `frontend/src/app/bootstrap.js`. |
| `frontend/src/app/bootstrap.js` | Bootstrap da SPA: sessao inicial, hash atual, login, resolucao de rota, fallback e ciclo de render. |
| `frontend/src/app/router.js` | Router runtime: cache de modulos, `import()` lazy, fases de performance e resolucao estatica/dinamica. |
| `frontend/src/app/route-registry.js` | Registro oficial de rotas SPA, loaders, exports e permissoes. |
| `frontend/src/app/guards.js` | Guards de permissao e render de acesso negado. |
| `frontend/src/app/errors.js` | Handlers globais e telas de falha de sessao/rota. |
| `frontend/src/shell.js` | Facade temporaria de compatibilidade para `renderLoginPage` e `renderShell`; nao e owner primario do shell. |
| `frontend/src/shell/render-shell.js` | Renderizacao estrutural do shell autenticado, flash visual, interacoes do menu e logout. |
| `frontend/src/shell/navigation.js` | `NAV_GROUPS`, permissao/estado ativo da navegacao e render dos links classificados. |
| `frontend/src/shell/login.js` | Tela de login SPA, refresh cacheado de sessao/CSRF, submit autenticado e destino pos-login. |
| `frontend/src/shell/redirects.js` | Facade temporaria para compat de destino backend/hash no login. |
| `frontend/src/compat/backend-links.js` | Owner dos links backend/SSR, export/print hrefs e redirects backend -> hash que ainda acoplam SPA ao backend. |
| `frontend/src/compat/static-assets.js` | Owner dos assets `/static/*` usados por modulos JavaScript do frontend. |
| `frontend/src/shared/ui/tokens.css` | Owner dos tokens semanticos frontend para cor, tipografia, spacing, radius, shadow, camadas e estados. |
| `frontend/src/shared/ui/primitives.css` | Owner dos primitives visuais minimos e neutros de dominio. |
| `frontend/src/shared/forms/draft-protection.js` | Wiring DOM reutilizavel para protecao de formularios criticos, sem conhecer endpoints ou regra de dominio. |
| `frontend/src/lib.js` | Facade temporaria de compatibilidade para imports existentes; nao e owner primario de services/state. |
| `frontend/src/services/api-client.js` | Client HTTP, timeout, JSON/blob, headers, `credentials: include`, erro normalizado e efeitos de auth. |
| `frontend/src/services/financeiro-missoes-api.js` | Client fino dos endpoints reais de Missões Operacionais em `/api/v1/financeiro/missoes`, `/api/v1/tripulantes` e `/api/v1/equipamentos/options`. |
| `frontend/src/services/session-service.js` | Refresh de sessao e sincronizacao de CSRF a partir de `/api/v1/session`. |
| `frontend/src/services/csrf-service.js` | Leitura/escrita minima do token CSRF e aplicacao do header de mutacao. |
| `frontend/src/services/trace-service.js` | Request id e correlation id do cliente. |
| `frontend/src/state/app-state.js` | Estado transversal minimo: config runtime, sessao, CSRF, flash bruto e medicao de fases. |
| `frontend/src/state/draft-state.js` | Storage curto de drafts criticos com TTL e assinatura de baseline, sem DOM e sem arquivos. |
| `frontend/src/state/flash-state.js` | Estado/armazenamento de flash e normalizacao de tipo de mensagem. |
| `frontend/src/state/navigation-state.js` | Memoria curta de rota intencional/ultima rota boa para login e recuperacao de hash, sem renderizar UI. |
| `frontend/src/pages-*.js` | Paginas vivas quando importadas e registradas por `frontend/src/app.js`. |
| `frontend/src/pages-financeiro.js` | Wrapper fino da superficie SPA Financeiro autorizada para Missões Operacionais. |
| `frontend/src/features/dashboard/page.js` | Owner da superficie SPA `#/dashboard`, incluindo adapters, render e interacoes do dashboard. |
| `frontend/src/features/dashboard-operacional/page.js` | Owner da superficie SPA `#/dashboard-operacional`, incluindo topo operacional, clima AISWEB via endpoint interno e alertas do layout operacional. |
| `frontend/src/features/financeiro/missoes-page.js` | Owner da superficie SPA `#/financeiro/missoes`, cadastro e edicao de Missões Operacionais sem calculo financeiro no frontend. |
| `frontend/src/features/tripulantes/list-page.js` | Owner da lista/cadastro de tripulantes e do seletor usado pelo relatorio individual. |
| `frontend/src/features/tripulantes/form-page.js` | Owner do cadastro/detalhe de tripulante, foto e documentos PDF. |
| `frontend/src/features/tripulantes/avatar.js` | Owner de avatar/foto/fallback visual de tripulante usado por lista e formulario. |
| `frontend/src/features/tripulantes/data-adapters.js` | Owner dos adapters minimos de payload de tripulantes/options. |
| `frontend/src/features/relatorio-individual/page.js` | Owner da entrada SPA do relatorio individual, delegando ao seletor de tripulantes em modo `report`. |
| `frontend/src/features/treinamentos/list-page.js` | Owner da superficie SPA `#/treinamentos`, incluindo selecao de programa, segmentos e registros salvos. |
| `frontend/src/features/treinamentos/form-page.js` | Owner da edicao canonica de treinamento por segmento em `treinamentos-tripulantes`. |
| `frontend/src/features/treinamentos/attachments.js` | Owner de anexos PDF de treinamento. |
| `frontend/src/features/treinamentos/program-helpers.js` | Owner dos helpers/adapters minimos do programa de treinamentos por tripulante. |
| `frontend/src/features/training-root/page.js` | Owner da superficie SPA `#/treinamentos/raiz`, tipos, segmentos e horas de voo. |
| `frontend/src/features/relatorios/habilitacoes-page.js` | Owner do consolidado SPA de habilitacoes. |
| `frontend/src/features/relatorios/report-ui.js` | Owner de helpers compartilhados de relatorio em tela/impressao/export. |
| `frontend/src/app.css` | Ajustes CSS do frontend estatico; o build concatena a base CSS do backend com este arquivo. |
| `frontend/scripts/build_frontend.py` | Build oficial do frontend. |
| `frontend/dist/` | Saida gerada pelo build; nao e fonte e nao orienta arquitetura. |

## 2. Fonte vs build

- Fonte viva: `frontend/src/`, `frontend/scripts/build_frontend.py` e configuracao de ambiente usada pelo build.
- Build gerado: `frontend/dist/`, com `index.html` apontando para entrypoints fingerprintados, `asset-manifest.json`, CSS composto e grafo de assets fechado por release.
- Um modulo em `frontend/src/pages-*.js` so vira rota oficial quando entra em `frontend/src/app/route-registry.js` com permissao declarada e import dinamico.
- `frontend/dist/` pode existir no deploy ou em build local, mas alteracao manual ali e residuo operacional.
- Checks automatizados que precisam inspecionar o artefato final devem preferir `frontend/scripts/build_frontend.py --output-dir <diretorio-temporario-fora-do-checkout>` em vez de depender de `frontend/dist/` persistido no workspace.

## 3. Build oficial

Comando oficial:

```powershell
.\.venv\Scripts\python.exe frontend\scripts\build_frontend.py --env-file frontend\.env.example
```

O build deve ser executado da raiz do repositorio. Ele gera `frontend/dist/`, cria `asset-manifest.json`, materializa JS/CSS fingerprintados e compoe o CSS final.

## 3.1. Startup canonico e medicao

- Startup canonico do frontend: `index.html` carrega `config.js` e `app.js`; `app.js` delega para o nucleo `frontend/src/app/`, que importa eager `lib.js`, `shell.js` e os owners minimos em `frontend/src/shell/`, mantendo modulos de pagina por `import()`.
- Modulos de pagina (`pages-dashboard-tripulantes.js`, `pages-treinamentos-relatorios.js`, `pages-financeiro.js`) entram por `import()` no primeiro acesso da rota.
- O boot publica `window.__FRONTEND_PERF__` via `frontend/src/state/app-state.js` com fases `startup`, `session`, `route_resolve`, `route_import` e `route_render`.
- O script `frontend/scripts/measure_frontend_perf.py` mede o artefato final e deve acompanhar mudancas que afetem startup, sessao ou waterfall de rota.

## 4. Integracao com backend

- O frontend consome API via `frontend/src/services/api-client.js`; imports existentes ainda podem passar pela facade temporaria `frontend/src/lib.js`.
- Sessao canonica: `GET /api/v1/session`, `POST /api/v1/session/login` e `POST /api/v1/session/logout`.
- Requests usam cookie de sessao, CSRF em mutacoes e `credentials: "include"`.
- `X-Request-ID` e `X-Correlation-ID` sao mantidos pelo client para rastreio operacional.
- `FRONTEND_API_BASE_URL` define a origem da API quando frontend e backend estao separados; vazio significa mesma origem.
- `FRONTEND_PUBLIC_ORIGIN`, `FRONTEND_LOCAL_ORIGIN` e `FRONTEND_ALLOWED_ORIGINS` pertencem ao contrato backend/origem/redirecionamento.

## 4.0. Services e state

`services/` nao renderiza DOM e nao importa shell, paginas ou features. `state/` e minimo: guarda apenas estado transversal necessario ao bootstrap, API, sessao, CSRF, flash, medicao, navegacao curta e drafts criticos baseline-bound.

| modulo | owner | pode fazer | nao pode fazer |
| --- | --- | --- | --- |
| `frontend/src/services/api-client.js` | frontend/services | HTTP, timeout, headers, JSON/blob e efeitos de auth ja existentes. | renderizar DOM, importar shell/paginas/features ou mudar rotas. |
| `frontend/src/services/financeiro-missoes-api.js` | frontend/services/financeiro | Consumir `/api/v1/financeiro/missoes` para missoes, `/api/v1/tripulantes` para seletores de tripulantes e `/api/v1/equipamentos/options` para seletores transversais de equipamentos. | Renderizar DOM, importar shell/paginas/features, chamar rotas legadas `/missoes`, calcular bonificacao ou acessar endpoints financeiros ainda 501. |
| `frontend/src/services/session-service.js` | frontend/services | buscar sessao canonica e sincronizar CSRF. | renderizar login ou decidir navegacao. |
| `frontend/src/services/csrf-service.js` | frontend/services | ler/escrever token CSRF e aplicar header em mutacoes. | conhecer formularios, paginas ou shell. |
| `frontend/src/services/trace-service.js` | frontend/services | criar request id e correlation id. | persistir estado de dominio. |
| `frontend/src/state/app-state.js` | frontend/state | expor `config`, `state` minimo e medicao `window.__FRONTEND_PERF__`. | virar store de dominio ou importar services/pages. |
| `frontend/src/state/draft-state.js` | frontend/state | guardar diferencas de formularios criticos em `sessionStorage` com TTL e assinatura do baseline. | serializar arquivos, reexecutar submit, renderizar DOM ou substituir dado salvo. |
| `frontend/src/state/flash-state.js` | frontend/state | guardar/consumir flash em memoria/sessionStorage. | renderizar markup de flash. |
| `frontend/src/state/navigation-state.js` | frontend/state | guardar rota de retorno e ultima rota renderizada com sucesso em `sessionStorage`. | decidir permissao, renderizar UI ou usar dashboard como fallback universal. |
| `frontend/src/shared/forms/draft-protection.js` | frontend/shared-forms | conectar formularios criticos ao draft-state, beforeunload e guarda de links internos. | conhecer endpoints, serializar uploads, criar overlay ou alterar negocio. |

Regra: `frontend/src/lib.js` existe como facade temporaria para preservar imports durante a migracao incremental. Novo codigo deve preferir importar diretamente de `services/`, `state/` ou futuros `shared/` quando o owner ja estiver explicito.

## 4.1. Shell global e paginas

O shell global em `frontend/src/shell.js` nao define sozinho que uma tela pertence a SPA. Entrada no menu deve ser cruzada com `frontend/src/app/route-registry.js`.

Ownership atual do shell:

| modulo | owner | pode fazer | nao pode fazer |
| --- | --- | --- | --- |
| `frontend/src/shell.js` | frontend/shell compat | Reexportar `renderLoginPage` e `renderShell` para imports existentes. | Concentrar navegacao, login, redirects, logout ou markup novo. |
| `frontend/src/shell/render-shell.js` | frontend/shell render | Montar shell autenticado, topbar, sidebar, flash renderizado, logout e interacoes do menu. | Definir pertencimento a SPA ou registrar rota. |
| `frontend/src/shell/navigation.js` | frontend/shell navigation | Manter `NAV_GROUPS`, aplicar permissoes e renderizar links ja classificados. | Migrar link backend/SSR para SPA sem router e bloco proprio. |
| `frontend/src/shell/login.js` | frontend/shell login | Renderizar login SPA, preparar sessao/CSRF, enviar credenciais e aplicar destino pos-login. | Alterar contrato de autenticacao ou decidir rota oficial fora do router. |
| `frontend/src/shell/redirects.js` | frontend/shell compat redirects | Reexportar destino backend conhecido para hash SPA a partir de `frontend/src/compat/backend-links.js`. | Ser owner de paths backend, servir HTML, chamar API ou renderizar DOM. |

Regra: shell nao define pertencimento a SPA. O owner de rota viva continua sendo `frontend/src/app/route-registry.js`; o shell apenas expõe entradas ja classificadas.

Classificacoes aceitas:

- `spa_viva`: hash route registrada em `frontend/src/app/route-registry.js` e carregada por loader oficial.
- `backend_ssr_compat`: caminho absoluto servido pelo backend como HTML compativel ou pagina operacional ainda nao migrada para SPA.
- `backend_ssr_compat_redirect_only`: path backend legado mantido apenas para resolver entrada historica para uma hash canonica, sem uso como href de runtime.
- `legacy_vivo_controlado`: rota backend/SSR ratificada em `legacy/LIVE_LEGACY.md`, com condicao de saida propria.
- `ssr_canonical_current_direct`: contrato SSR canonico atual, sem substituto API/SPA registrado, mantido fora da navegacao principal quando nao for item de shell.
- `externo_operacional`: saida operacional/documental fora do router SPA, como PDF gerado pelo backend.
- `ambigua_pendente`: item exposto no shell sem classificacao, owner ou condicao de saida; nao e aceito como estado fechado.

Inventario atual do shell:

| destino | classificacao | owner atual | condicao de saida quando nao for SPA |
| --- | --- | --- | --- |
| `#/dashboard` | `spa_viva` | frontend | n/a |
| `#/dashboard-operacional` | `spa_viva` | frontend | n/a |
| `/pernoites` | `ssr_ui_current_with_api_read_model` | operacoes SSR fora da navegacao principal | UI/listagem atual permanece SSR, mas leitura canonica ja existe em `/api/v1/operacoes/pernoites`; nao deve voltar ao shell principal como compat casual. |
| `/pernoites/novo` | `ssr_write_canonical_current_direct` | operacoes SSR fora da navegacao principal | formulario/escrita atual canonico de Pernoites ate cutover dedicado de API/SPA; nao deve voltar ao shell principal como compat casual. |
| `/bases` | `backend_ssr_compat` | backend bases + frontend shell | publicar substituto SPA/API para gestao de bases e migrar link/testes. |
| `#/relatorios/habilitacoes` | `spa_viva` | frontend | n/a |
| `#/relatorios/individual` | `spa_viva` | frontend | n/a |
| `#/tripulantes` | `spa_viva` | frontend | n/a |
| `#/treinamentos` | `spa_viva` | frontend | n/a |
| `#/financeiro/missoes` | `spa_viva` | frontend/financeiro | n/a |
| `#/financeiro/lancamentos-jornada` | `spa_viva` | frontend/financeiro | n/a |
| `#/financeiro/fechamento-parametros` | `spa_viva` | frontend/financeiro | n/a |
| `/equipamentos` | `backend_ssr_compat` | backend cadastros + frontend shell | publicar substituto SPA/API para equipamentos e migrar link/testes. |
| `#/treinamentos/raiz` | `spa_viva` | frontend | n/a |
| `/usuarios` | `backend_ssr_compat` | backend admin + frontend shell | publicar substituto SPA/API para usuarios e migrar link/testes. |
| `/usuarios/novo` | `backend_ssr_compat` | backend admin + frontend shell | publicar substituto SPA/API para usuarios e migrar link/testes. |
| `/monitoramento` | `backend_ssr_compat` | backend admin/ops + frontend shell | publicar substituto SPA/API ou manter como painel operacional backend classificado. |
| `/manual/usuario.pdf` | `externo_operacional` | docs produto + backend admin/ops | mover para superficie documental canonica ou manter como PDF operacional explicitamente classificado. |
| `/notificacoes-email` | `backend_ssr_compat` | backend admin/ops + frontend shell | publicar substituto SPA/API para notificacoes e migrar link/topbar/testes. |
| `/backups` | `backend_ssr_compat` | backend admin/ops + frontend shell | publicar substituto SPA/API ou manter como painel operacional backend classificado. |
| `/auditoria` | `backend_ssr_compat` | backend admin + frontend shell | publicar substituto SPA/API para auditoria e migrar link/testes. |

Regra: nova entrada no shell precisa aparecer nesta tabela ou em documento vivo equivalente no mesmo change. Item backend/SSR ou legado nao pode ser apresentado como rota SPA viva sem registro no router.

### 4.1.1. Compat/static/backend adapters

F06 isola os acoplamentos residuais com backend/static em `frontend/src/compat/`. Esta pasta e a fronteira de compat/static/backend adapters; e fronteira explicita, nao pasta coringa.

| modulo | owner | pode fazer | nao pode fazer |
| --- | --- | --- | --- |
| `frontend/src/compat/backend-links.js` | frontend/compat backend links | Nomear paths backend/SSR vivos, classificar fronteira por path, montar hrefs de export/print com query, nomear hashes canonicas e resolver redirects backend -> hash recebidos pelo login/entrada SPA. | Registrar rota SPA, migrar SSR para SPA, chamar API, renderizar DOM ou promover path `backend_ssr_compat_redirect_only` como href de runtime. |
| `frontend/src/compat/static-assets.js` | frontend/compat static assets | Nomear assets `/static/*` usados por modulos JavaScript, como logo e foto de login. | Trocar asset visual, decidir cache de build, servir arquivo ou mexer em `frontend/dist/`. |

Regra: feature, shell ou pagina nao deve criar novo link backend/SSR ou novo asset `/static/*` hardcoded. Novo acoplamento residual precisa entrar primeiro no adapter correspondente, com owner e classificacao. O `frontend/src/index.html` e excecao de bootstrap HTML para favicon/manifest porque roda antes dos modulos JavaScript; ele continua acoplamento static documentado, nao fonte para novas referencias em features.

API `/api/v1/...` continua pertencendo ao contrato de `frontend/src/services/api-client.js` e aos owners de dominio que consomem endpoints. F06 nao reabre service layer nem cria registry geral de endpoint.

## 4.2. Modulos de pagina e roteamento

Presenca fisica em `frontend/src/pages-*.js` nao define superficie oficial. Modulo de pagina so entra na SPA viva quando esta no loader oficial de `frontend/src/app/route-registry.js` e tem exports usados por rotas estaticas ou dinamicas.

Inventario atual:

| modulo | classificacao | owner estrutural | superficie oficial | condicao de saida quando nao for pagina SPA viva |
| --- | --- | --- | --- | --- |
| `pages-dashboard-tripulantes.js` | `pagina_spa_viva` | frontend + tripulantes/dashboard | sim: `#/dashboard`, `#/dashboard-operacional`, `#/dashboard-operacional-tv`, `#/tripulantes`, `#/relatorios/individual`, `#/tripulantes/new` e `#/tripulantes/<id>` | n/a |
| `pages-financeiro.js` | `pagina_spa_viva` | frontend + financeiro | sim: `#/financeiro/missoes`, `#/financeiro/lancamentos-jornada`, aliases antigos `#/financeiro/bonificacoes*` e `#/financeiro/fechamento-parametros` | n/a |
| `pages-treinamentos-relatorios.js` | `pagina_spa_viva` | frontend + treinamentos/relatorios | sim: `#/treinamentos`, `#/treinamentos/new`, `#/treinamentos/raiz`, `#/relatorios/habilitacoes` e `#/treinamentos/<id>` | n/a |
| `pages-training-workspace.js` | `artefato_removido` | frontend + treinamentos | nao existe mais em `frontend/src`; removido no bloco 95 apos prova de ausencia de loader, rota e importador | reintroducao exige bloco proprio com rota oficial, owner e teste de fronteira atualizado. |

Regra: novo `pages-*.js` precisa ser classificado nesta tabela ou em documento vivo equivalente no mesmo change. Modulo nao roteado nao pode ser apresentado como pagina SPA viva sem entrada em `app/route-registry.js`, rota oficial e teste de fronteira atualizado.

### 4.2.1. Features dashboard/tripulantes

`frontend/src/pages-dashboard-tripulantes.js` permanece como wrapper compativel temporario porque o router oficial ainda carrega esse modulo. Ele nao e mais owner primario de dashboard, lista/formulario de tripulantes ou relatorio individual.

| modulo | owner | pode fazer | nao pode fazer |
| --- | --- | --- | --- |
| `frontend/src/pages-dashboard-tripulantes.js` | frontend/pages compat | Preservar exports roteados atuais para `app/route-registry.js`. | Concentrar API, DOM, render, adapters ou novas regras de dominio. |
| `frontend/src/features/dashboard/page.js` | frontend/features/dashboard | Renderizar dashboard, adaptar payloads do dashboard, compor calendario e fila critica. | Importar paginas, registrar rotas ou mexer em shell. |
| `frontend/src/features/dashboard-operacional/page.js` | frontend/features/dashboard-operacional | Renderizar o dashboard operacional com AISWEB, resumo, fila critica e Gestao de Bases usando dado real ou estado honesto (`loading`/`empty`/`error`). | Substituir o Painel Geral, chamar AISWEB direto do navegador, registrar rotas, injetar mock de negocio ou criar novos blocos fora do topo operacional. |
| `frontend/src/features/tripulantes/list-page.js` | frontend/features/tripulantes | Renderizar lista de tripulantes, filtros, paginacao e acoes de lista. | Assumir ownership do dashboard ou de treinamentos. |
| `frontend/src/features/tripulantes/form-page.js` | frontend/features/tripulantes | Renderizar formulario/detalhe, foto, PDF e persistencia de tripulante. | Criar rota nova ou migrar SSR compat. |
| `frontend/src/features/tripulantes/avatar.js` | frontend/features/tripulantes | Resolver foto, avatar e fallback visual de tripulante. | Chamar API ou renderizar paginas completas. |
| `frontend/src/features/tripulantes/data-adapters.js` | frontend/features/tripulantes | Validar/adaptar payloads de lista/options/files usados pela feature. | Renderizar DOM ou importar shell/paginas. |
| `frontend/src/features/relatorio-individual/page.js` | frontend/features/relatorio-individual | Expor entrada do relatorio individual usando lista em modo `report`. | Duplicar a lista ou reclassificar rota. |

Regra: nova responsabilidade de dashboard/tripulantes/relatorio individual deve entrar no owner de feature correspondente. O wrapper `pages-dashboard-tripulantes.js` existe apenas para compatibilidade incremental do loader atual.

#### Fronteira do relatorio individual

Classificacao final: `hibrido_documental_blindado`.

`#/relatorios/individual` e a entrada canonica SPA do relatorio individual e atua como seletor/read model de consulta. O detalhe por tripulante permanece documento SSR oficial em `/tripulantes/<id>/relatorio`, com PDF em `/tripulantes/<id>/relatorio/export.pdf`, porque ainda nao existe contrato SPA de detalhe equivalente e a leitura documental historica precisa ser preservada.

Regras:

- `frontend/src/features/relatorio-individual/page.js` nao renderiza detalhe; delega para `renderTripulantesListPage("report")`.
- Links SPA para `/tripulantes/<id>/relatorio` precisam declarar `data-boundary="ssr_document_read_model"`.
- Links de PDF precisam declarar `data-boundary="ssr_document_pdf"`.
- O documento SSR precisa oferecer retorno explicito para `/#/relatorios/individual` com `hx-boost="false"`.
- Dashboards, cards e atalhos operacionais nao devem abrir o documento SSR como atalho casual; quando o objetivo e abrir o tripulante, devem apontar para `/#/tripulantes/<id>`.

### 4.2.1.1. Features Financeiro

`frontend/src/pages-financeiro.js` e um wrapper fino para o loader `financeiro` do router. As superficies vivas do modulo sao `#/financeiro/missoes`, `#/financeiro/lancamentos-jornada` e `#/financeiro/fechamento-parametros`. Os hashes antigos `#/financeiro/bonificacoes`, `#/financeiro/bonificacoes/horaria` e `#/financeiro/bonificacoes/produtividade` existem apenas como aliases de compatibilidade e precisam renderizar o owner canonico `renderFinanceiroLancamentosJornadaPage`.

| modulo | owner | pode fazer | nao pode fazer |
| --- | --- | --- | --- |
| `frontend/src/pages-financeiro.js` | frontend/pages compat | Preservar exports roteados atuais para `app/route-registry.js`. | Concentrar API, DOM, render, adapters ou regra de dominio. |
| `frontend/src/features/financeiro/missoes-page.js` | frontend/features/financeiro | Renderizar lista, detalhe, criacao, edicao basica e cancelamento de Missões Operacionais usando capacidades `finance:missions:*`. | Calcular bonificacao, hora noturna, pre/pos-jornada, garantia minima, produtividade, fechamento ou chamar superficies legadas. |
| `frontend/src/features/financeiro/bonificacoes-page.js` | frontend/features/financeiro | Renderizar a experiencia canonica `Lançamentos de Jornada` para grade mensal, preview backend, relatorios e acoes financeiras de jornada. | Recriar hub antigo de Bonificacoes, registrar rota propria para Horaria/Produtividade ou aplicar CSS antigo `.financeiro-bonificacoes-page` ao root da tela nova. |
| `frontend/src/services/financeiro-missoes-api.js` | frontend/services/financeiro | Encapsular chamadas reais de Missões Operacionais em `/api/v1/financeiro/missoes` e opcoes operacionais existentes em `/api/v1/tripulantes` e `/api/v1/equipamentos/options`. | Chamar `/missoes`, `/api/v1/missoes`, bonificacoes, parametros, feriados, competencias ou endpoints ainda 501. |

Regra: o frontend cadastra e exibe fatos operacionais. Horario de apresentacao e horario de abandono pertencem a missao operacional; nao existem horarios separados por tripulante na tela. Bonificacoes, parametros, feriados e fechamento permanecem fora desta superficie.

### 4.2.2. Features treinamentos/relatorios

`frontend/src/pages-treinamentos-relatorios.js` permanece como wrapper compativel temporario porque o router oficial ainda carrega esse modulo. Ele nao e mais owner primario de treinamentos por tripulante, cadastro raiz ou relatorios consolidados.

| modulo | owner | pode fazer | nao pode fazer |
| --- | --- | --- | --- |
| `frontend/src/pages-treinamentos-relatorios.js` | frontend/pages compat | Preservar exports roteados atuais para `app/route-registry.js`. | Concentrar API, DOM, render, adapters ou novas regras de dominio. |
| `frontend/src/features/treinamentos/list-page.js` | frontend/features/treinamentos | Renderizar selecao de tripulante/tipo/aeronave, segmentos, batch e registros salvos. | Registrar rota ou assumir relatorios consolidados. |
| `frontend/src/features/treinamentos/form-page.js` | frontend/features/treinamentos | Renderizar edicao de registro de treinamento por segmento, validacao e compat legado interno do formulario. | Criar rota nova ou migrar SSR compat. |
| `frontend/src/features/treinamentos/attachments.js` | frontend/features/treinamentos | Renderizar anexos PDF de treinamento. | Chamar API ou decidir permissao fora do consumidor. |
| `frontend/src/features/treinamentos/program-helpers.js` | frontend/features/treinamentos | Manter helpers/adapters do programa de treinamento por tripulante. | Renderizar shell ou importar paginas. |
| `frontend/src/features/training-root/page.js` | frontend/features/training-root | Renderizar cadastro raiz, tipos, segmentos, horas de voo, abas e acoes de CRUD. | Assumir lista por tripulante ou relatorios consolidados. |
| `frontend/src/features/relatorios/habilitacoes-page.js` | frontend/features/relatorios | Renderizar consolidado de habilitacoes, filtros, tabela e saidas CSV/PDF/impressao. | Migrar backend SSR/export ou alterar contrato operacional. |
| `frontend/src/features/relatorios/report-ui.js` | frontend/features/relatorios | Compartilhar helpers de contexto, evidencia, loading/error e filtros responsivos de relatorios. | Chamar API, registrar rota ou renderizar pagina completa. |

Regra: nova responsabilidade de treinamentos, cadastro raiz ou relatorios deve entrar no owner de feature correspondente. O wrapper `pages-treinamentos-relatorios.js` existe apenas para compatibilidade incremental do loader atual.

## 4.2.3. Fundacao visual shared/ui

G01 cria a base visual minima para a proxima fase sem redesenhar paginas. O objetivo e preparar semantica, composicao e estados para componentizacao futura, mantendo a adocao incremental.

| modulo | classificacao | owner | pode fazer | nao pode fazer |
| --- | --- | --- | --- | --- |
| `frontend/src/shared/ui/tokens.css` | `consolidado` | frontend/shared-ui | Definir tokens semanticos de cor, tipografia, spacing, radius, shadow, z-index/camadas e estados (`default`, `hover`, `focus`, `disabled`, `error`, `success`, `warning`, `info`). | Criar token por tela, dominio, gosto visual ou valor sem semantica reutilizavel. |
| `frontend/src/shared/ui/primitives.css` | `consolidado` | frontend/shared-ui | Expor primitives pequenas como `ui-stack`, `ui-cluster`, `ui-panel-offset`, `ui-heading-reset`, `ui-surface`, `ui-feedback` e `ui-badge`. | Virar UI kit completo, conhecer API, router, shell, feature ou regra de dominio. |
| `frontend/src/shared/ui/README.md` | `consolidado` | frontend/shared-ui | Registrar regra curta de adocao e ownership. | Substituir docs vivas de arquitetura. |

Politica de adocao: `adocao_gradual`. Nova UI deve preferir tokens e primitives antes de hardcoded visual; telas existentes adotam apenas quando isso reduz inline style, repeticao ou ambiguidade de composicao. Estado deste bloco: `nao_redesign`.

Divida visual: `divida_visual_controlada`. O CSS ainda contem valores locais e familias visuais especificas de login, relatorios densos, dashboard e formularios grandes. Esses valores nao bloqueiam a proxima fase, mas devem ser convertidos por blocos de componentizacao/UX, nao por limpeza estetica.

### 4.2.4. Aplicacao da fundacao visual no shell/layout

G02 aplica a fundacao visual no shell autenticado e no layout estrutural sem redesenhar paginas funcionais.

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `frontend/src/shell/render-shell.js` | `consolidado` | markup do shell usa `ui-app-frame`, `ui-inverse-surface`, `ui-navigation-list`, `ui-sticky-surface`, `ui-cluster` e `ui-content-region`. | nao muda links, login, logout, redirects ou pertencimento a SPA. |
| `frontend/src/app.css` | `consolidado` | overrides estruturais do shell usam tokens de inverse surface, layout, navegacao, camadas e spacing. | nao redesenhar dashboard, treinamentos, relatorios ou paginas de dominio neste bloco. |
| `frontend/src/shared/ui/tokens.css` | `consolidado` | tokens de layout/shell reutilizaveis: `--color-inverse-*`, `--space-layout-*`, `--space-navigation-*`, `--size-sidebar-width`, `--size-content-wide`. | tokens devem continuar sem nome de tela ou regra de dominio. |
| `frontend/src/shared/ui/primitives.css` | `consolidado` | primitives estruturais neutros: `ui-app-frame`, `ui-inverse-surface`, `ui-sticky-surface`, `ui-content-region`, `ui-navigation-list`. | primitives nao podem conhecer API, router, feature ou regra de produto. |
| `backend/src/controle_treinamentos/static/styles.css` | `divida_residual_controlada` | ainda e a base CSS legada/backend concatenada antes de `shared/ui` e `app.css`. | nao editar como fonte visual moderna neste bloco; desacoplamento CSS exige frente propria. |

Politica de adocao: shell/layout pode usar tokens e primitives imediatamente quando isso reduzir hardcodes estruturais. Paginas de dominio continuam migrando por blocos proprios para evitar redesign prematuro.

### 4.2.5. Aplicacao da fundacao visual em dashboard/tripulantes

G03 aplica a fundacao visual na primeira superficie funcional prioritaria: dashboard/tripulantes. O bloco cria uma referencia concreta de pagina sem alterar rota, loader, guards, services, state ou compat backend/SSR.

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `frontend/src/features/dashboard/page.js` | `consolidado` | usa `dashboard-page-shell`, `priority-page-surface`, `ui-stack`, `priority-page-header`, `ui-surface`, `ui-feedback`, `ui-cluster` e cards `ui-surface`. | nao muda endpoints, calendario, links, fila critica ou loaders. |
| `frontend/src/features/tripulantes/list-page.js` | `consolidado` | usa `tripulantes-page-shell`, `priority-page-surface`, `priority-page-header`, `tripulantes-list-panel`, `ui-surface`, `ui-stack`, `ui-stack-sm` e `ui-cluster`. | nao muda filtros, paginacao, exclusao, relatorio, WhatsApp ou permissao. |
| `frontend/src/app.css` | `consolidado` | bloco G03 escopado em `.dashboard-page-shell`, `.tripulantes-page-shell` e `.priority-page-surface`, usando tokens de spacing, surface, radius, shadow, estados e transicao. | nao virar regra global de pagina nem redesenhar treinamentos/relatorios. |
| `tests/contract/test_frontend_priority_page_visual_foundation.py` | `consolidado` | garante adocao material da fundacao visual e preservacao dos contratos funcionais principais. | nao substitui teste visual end-to-end. |
| hardcodes visuais profundos de formularios/tabelas densas | `divida_visual_controlada` | ainda existem em CSS legado e em familias visuais de dominio. | migrar em blocos futuros de pagina/feature, nao por limpeza estetica. |

Politica de adocao: `adocao_gradual`. Esta superficie e a primeira referencia funcional da nova linguagem visual, mas ainda e `nao_redesign` amplo. G03 nao autoriza mudancas em treinamentos/relatorios nem componentizacao ornamental.

### 4.2.6. Aplicacao da fundacao visual em treinamentos/relatorios

G04 aplica a fundacao visual na segunda superficie funcional prioritaria: treinamentos/relatorios. O bloco preserva o wrapper roteado de `pages-treinamentos-relatorios.js`, nao altera rota, loader, guards, services/state, redirects ou compat backend/SSR.

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `frontend/src/features/treinamentos/list-page.js` | `consolidado` | usa `training-reports-page-shell`, `training-program-page-shell`, `priority-page-surface`, `ui-stack`, `priority-page-header`, `ui-surface`, `ui-stack-sm` e superficies `ui-surface` no workbench e nos cards. | nao muda endpoints, selecao de treinamento, envio batch, reset/continue, tabela de registros ou capacidades. |
| `frontend/src/features/training-root/page.js` | `consolidado` | usa `training-root-page-shell`, `training-root-filter-panel`, `training-root-panel`, `ui-surface`, `ui-stack`, cards `ui-surface` e tabela `training-reports-table-wrap`. | nao muda tabs, formularios, exclusoes, submit explicito ou chamadas de cadastro raiz. |
| `frontend/src/features/relatorios/habilitacoes-page.js` | `consolidado` | usa `report-priority-page-shell`, `priority-page-header`, `training-report-panel`, `ui-surface`, `ui-feedback`, `ui-stack-sm`, cards `ui-surface` e tabela escopada. | nao muda filtros, export/print/PDF, calculo de vencimentos ou endpoints de habilitacoes. |
| `frontend/src/features/relatorios/report-ui.js` | `consolidado` | aplica `ui-surface` e `ui-feedback` em estados, contexto e evidencias compartilhadas dos relatorios. | nao conhecer router, services/state ou regra nova de dominio. |
| `frontend/src/app.css` | `consolidado` | bloco G04 escopado em `.training-reports-page-shell`, `.training-program-panel`, `.training-root-panel`, `.training-report-panel` e `.training-reports-table-wrap`, usando tokens de spacing, surface, radius, shadow, estados e transicao. | nao virar regra global nem redesenhar dashboard/tripulantes. |
| `tests/contract/test_frontend_training_reports_visual_foundation.py` | `consolidado` | garante adocao material da fundacao visual e preservacao de contratos funcionais principais de treinamentos, cadastro raiz e relatorios. | nao substitui teste visual end-to-end. |
| hardcodes visuais profundos de tabelas, formularios e relatorios densos | `divida_visual_controlada` | ainda existem em CSS legado e familias especificas de dominio. | migrar em blocos posteriores de pagina/feature, nao por limpeza estetica. |

Politica de adocao: `adocao_gradual`. Esta superficie e a segunda referencia funcional da nova linguagem visual e continua `nao_redesign` amplo. G04 nao autoriza redesign completo, mudanca em shell/layout ou componentizacao ornamental.

## 4.3. Build, runtime e env

Build nao e runtime. Runtime nao e fonte viva. `.env.example` e template, nao prova de ambiente real.

Trilha real de build:

1. `frontend/scripts/build_frontend.py` roda a partir da raiz.
2. O build copia `frontend/src/` para o diretorio de saida, preservando apenas assets estaticos nao JS/CSS.
3. O build compoe `app.css` concatenando `backend/src/controle_treinamentos/static/styles.css`, `frontend/src/shared/ui/tokens.css`, `frontend/src/shared/ui/primitives.css` e `frontend/src/app.css`.
4. O build gera payload de `config.js` a partir de ambiente de processo e, opcionalmente, `--env-file`.
5. O build aplica fingerprint por nome para `.js/.css` no formato `<arquivo>.<build_utc>.<hash>.ext` e reescreve referencias de HTML/JS para esses nomes.
6. O build grava `asset-manifest.json` com `entrypoints` e mapa completo de assets fingerprintados.
7. A saida padrao e `frontend/dist/`; checks automatizados devem preferir `--output-dir` fora do checkout.

Trilha real de runtime:

1. Nao ha dev server canonico de frontend dentro do repo.
2. Localmente, o backend sobe pela trilha propria e o frontend separado so roda se o artefato gerado for servido por HTTP externo.
3. Em homolog/producao, o frontend separado depende de publicacao/servidor HTTP real e de `FRONTEND_*` coerentes no backend.
4. O backend usa `FRONTEND_PUBLIC_ORIGIN`, `FRONTEND_LOCAL_ORIGIN`, `FRONTEND_ALLOWED_ORIGINS` e `FRONTEND_COMPAT_REDIRECTS` para redirects, CORS e compat.
5. O browser usa o `config.js` gerado para `appName`, `apiBaseUrl`, `publicOrigin` e `debug`.
6. O `ops/windows/caddy/Caddyfile.example` vivo prova proxy backend; ele nao prova sozinho publicacao estatica de `frontend/dist/`.

Classificacao atual:

| elemento | classificacao | owner atual | condicao de saida quando nao for fonte viva |
| --- | --- | --- | --- |
| `frontend/src/` | `fonte_viva` | frontend | n/a |
| `frontend/src/shared/ui/*.css` | `fonte_viva` | frontend/shared-ui | n/a |
| `frontend/scripts/build_frontend.py` | `fonte_viva` | frontend/build | n/a |
| `frontend/.env.example` | `config_de_build` | frontend/build | manter como template; env real precisa vir do ambiente alvo ou arquivo operacional real. |
| `FRONTEND_APP_NAME` | `config_de_build` | frontend/build | sai apenas se `config.js` deixar de materializar nome publico do app. |
| `FRONTEND_API_BASE_URL` | `config_de_build` | frontend/build + backend/API | sai apenas se origem da API for resolvida por contrato runtime diferente. |
| `FRONTEND_PUBLIC_ORIGIN` no build | `config_de_build` | frontend/build + ops | sai apenas se `publicOrigin` deixar de ser gravado no `config.js`. |
| `FRONTEND_ENABLE_DEBUG` | `config_de_build` | frontend/build | sai apenas se debug de frontend deixar de ser configuravel por build. |
| `frontend/dist/` | `artefato_gerado` | frontend/build + ops | pode existir como artefato publicavel; nunca vira fonte viva. |
| `frontend/dist/config.js` | `config_de_runtime` | frontend/build + ops | gerado pelo build; nao editar manualmente nem usar como fonte de verdade. |
| servidor HTTP externo/Caddy equivalente | `publicacao_local_ou_homolog` | ops/runtime | substituir apenas por runtime canonico documentado que sirva o artefato frontend. |
| `FRONTEND_PUBLIC_ORIGIN` no backend | `config_de_runtime` | backend/runtime + ops | sai apenas se redirects oficiais deixarem de depender de origem publica. |
| `FRONTEND_LOCAL_ORIGIN` | `config_de_runtime` | backend/runtime + ops | sai apenas se nao houver mais modo local/direct-backend separado. |
| `FRONTEND_ALLOWED_ORIGINS` | `config_de_runtime` | backend/security + ops | sai apenas se CORS/auth cross-origin forem substituidos por contrato diferente. |
| `FRONTEND_COMPAT_REDIRECTS` | `config_de_runtime` | backend/compat + ops | sai quando redirects SSR/compat forem aposentados por bloco proprio. |
| `backend/src/controle_treinamentos/static/styles.css` | `acoplamento_backend_frontend` | frontend + backend/static | desacoplamento futuro exige fonte CSS/tokens propria ou contrato compartilhado fora do static backend. |
| referencias `/static/*` em `frontend/src` | `acoplamento_backend_frontend` | frontend + backend/static + ops | sair quando assets publicos forem publicados junto do artefato frontend ou houver contrato estatico separado. |
| `ops/windows/env/*.env.example` | `config_de_runtime` | ops/runtime | manter como template; nao e prova de env real homolog/producao. |
| `docs/operations/LOCAL_RUNTIME.md` e `ENVIRONMENT_PARITY.md` | `publicacao_local_ou_homolog` | ops/runtime | manter como doc viva de fronteira entre build, publish e validacao real. |
| ambiguidade central de build/runtime/env | `ambiguidade_pendente` | frontend + ops | `0` item central pendente neste bloco. |

Regra: nenhuma validacao pode declarar runtime frontend real apenas porque `build_frontend.py` passou ou `frontend/dist/` existe. Para validar frontend separado, e obrigatorio servir o artefato por HTTP real e alinhar `FRONTEND_*` ao ambiente alvo.

## 5. Como servir na operacao real

- Localmente, o backend oficial sobe por `backend\tools\runtime\run.py`.
- O frontend separado e gerado por build e servido por HTTP estatico externo apontando para `frontend/dist/`.
- Na operacao Windows/self-hosted, a publicacao do app e do frontend deve seguir `docs/operations/LOCAL_RUNTIME.md` e `docs/operations/WINDOWS_SELF_HOSTED_SERVER.md`.
- Nao existe dev server canonico de frontend dentro do repo nesta fase.

## 6. O que nao deve ser tratado como fonte

- `frontend/dist/`;
- `frontend/dist/config.js` e demais saidas geradas;
- caches, bytecode ou arquivos temporarios de build local;
- modulo de pagina nao registrado em `frontend/src/app/route-registry.js`;
- wrapper compat ou comando manual que apenas serve artefato ja gerado.

## 7. Readiness arquitetural apos F07

Decisao de readiness: `pronta_para_proxima_fase`.

Esta decisao significa que a primeira onda arquitetural do frontend ficou materialmente coerente para abrir uma frente posterior de arquitetura visual, componentizacao seria, tokens e UX. Nao significa GO visual, nao remove compat/legacy e nao encerra divida residual.

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `frontend/src/app/` | `consolidado` | bootstrap, router, registry, guards e errors existem separados. | nao concentrar pagina, shell ou service novo no bootstrap. |
| `frontend/src/shell/` | `consolidado` | render-shell, navigation, login e redirects estao separados; `shell.js` e facade. | shell nao define pertencimento a SPA. |
| `frontend/src/services/` | `consolidado` | API, sessao, CSRF e tracing tem owners proprios. | services nao renderizam DOM nem importam paginas/features/shell. |
| `frontend/src/state/` | `consolidado` | estado transversal minimo e flash isolados. | nao virar store global de dominio. |
| `frontend/src/features/` | `consolidado` | dashboard, tripulantes, relatorio individual, treinamentos, training-root e relatorios tem owners reais. | novas responsabilidades entram no owner de dominio, nao nos wrappers. |
| `frontend/src/compat/` | `consolidado` | backend links, redirects backend -> hash e assets staticos JS centralizados. | compat nao vira pasta coringa nem migra SSR por presuncao. |
| `pages-dashboard-tripulantes.js` | `wrapper_temporario_controlado` | wrapper fino preserva exports roteados atuais. | remover apenas com bloco proprio de loader por feature. |
| `pages-treinamentos-relatorios.js` | `pagina_spa_viva` | frontend + treinamentos/relatorios | sim: `#/treinamentos`, `#/treinamentos/new`, `#/treinamentos/raiz`, `#/relatorios/habilitacoes` e `#/treinamentos/<id>` | n/a |
| `pages-training-workspace.js` | `artefato_removido` | removido de `frontend/src` apos prova de ausencia de consumidor. | nao reintroduzir como modulo fisico nao roteado. |
| `frontend/src/index.html` com `/static/*` | `divida_residual_controlada` | excecao bootstrap HTML para favicon/manifest. | nova referencia static em JS deve passar por `compat/static-assets.js`. |
| SSR/backend links vivos | `divida_residual_controlada` | classificados e centralizados em `compat/backend-links.js`. | migracao/remocao exige frente propria. |
| `admin/routes.py:748>725` | `baseline_fora_do_escopo` | baseline arquitetural backend conhecido. | nao bloqueia readiness frontend, mas nao pode ser declarado verde. |

## 8. Readiness visual apos G05

Decisao de readiness: `pronta_para_proxima_fase_visual`.

Esta decisao significa que a segunda onda visual ficou materialmente coerente para expandir a nova linguagem visual para novas superficies, consolidar padroes de tabela/formulario e aprofundar `shared/ui` quando houver uso real. Nao significa redesign completo da aplicacao, nao encerra divida visual historica e nao autoriza design system inflado.

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `frontend/src/shared/ui/` | `consolidado` | `tokens.css`, `primitives.css` e README seguem como base comum; primitives continuam neutros de dominio. | nao receber regra de pagina, rota, API, feature ou gosto visual. |
| shell/layout | `adocao_visual_controlada` | `render-shell.js` usa `ui-app-frame`, `ui-inverse-surface`, `ui-navigation-list`, `ui-sticky-surface`, `ui-cluster` e `ui-content-region`; bloco G02 de `app.css` usa tokens semanticos. | nao muda navegacao, login, redirects, classificacao de links ou pertencimento a SPA. |
| dashboard/tripulantes | `adocao_visual_controlada` | G03 aplica `priority-page-surface`, `priority-page-header`, `ui-surface`, `ui-stack`, `ui-feedback`, `ui-cluster` e CSS escopado em `.dashboard-page-shell`/`.tripulantes-page-shell`. | nao reabrir rota, loader, services/state, dashboard ou lista por limpeza visual. |
| treinamentos/relatorios | `adocao_visual_controlada` | G04 aplica `priority-page-surface`, `ui-surface`, `ui-stack`, `ui-feedback`, `ui-stack-sm`, tabelas escopadas e CSS em `.training-reports-page-shell`. | nao mudar tabs, filtros, formularios, exports, impressao, PDF ou endpoints. |
| `frontend/src/app.css` | `divida_visual_controlada` | blocos G02/G03/G04 estao tokenizados, mas ainda existem familias historicas com valores locais para login, relatorios densos, formularios e operacao. | converter por blocos de pagina/componente, nao por limpeza estetica. |
| `backend/src/controle_treinamentos/static/styles.css` | `baseline_fora_do_escopo` | segue como base CSS legada/backend concatenada antes de `shared/ui` e `app.css`. | desacoplamento CSS exige frente propria de build/static. |
| bloqueio para proxima fase visual | `bloqueio_para_proxima_fase` | `0` item material. | manter checks G01-G05 verdes antes de expandir superficies. |

Politica para a proxima fase: expansao visual pode avancar apenas por superficie ou familia concreta de UI, com contrato funcional preservado, tokens/primitives reutilizados e divida residual registrada. Tabelas, formularios e estados densos podem virar proximo alvo; redesign amplo continua dependendo de bloco proprio.

## 9. Padroes compartilhados de tabela e formulario apos G06

G06 materializa a camada minima reutilizavel para tabelas densas e formularios profundos sem transformar `shared/ui` em design system completo. A decisao do bloco e `fechado`.

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `ui-table-wrap` | `consolidado` | primitive neutro para wrapper/scroll/surface de tabela, adotado em tripulantes, treinamentos, training-root e relatorios. | nao conhecer dominio, colunas, endpoint ou comportamento de tabela. |
| `ui-table-density-compact` | `consolidado` | primitive neutro para densidade compacta de celulas, usando tokens de spacing. | nao substituir regra responsiva ou semantica de dados. |
| `ui-table-actions` | `consolidado` | primitive neutro para acoes de tabela, com `--size-action-min-height` e gap tokenizado. | nao definir permissao, submit, delete ou navegacao. |
| `ui-table-state` | `consolidado` | primitive neutro para empty/loading/error em linhas de tabela, adotado no helper compartilhado `emptyTableRowMarkup`. | nao inventar estado funcional; apenas estiliza feedback existente. |
| `ui-form-toolbar` | `consolidado` | primitive neutro para filtros/toolbars de formulario, adotado em tripulantes, treinamentos, training-root e relatorios. | nao mudar submit, query string, filtros densos ou toggles. |
| `ui-form-grid` | `consolidado` | primitive neutro para grupos/campos de formulario, adotado em training-root e formularios profundos de tripulantes/treinamentos. | nao virar store de validacao nem componente de formulario. |
| `ui-form-actions` | `consolidado` | primitive neutro para submit/cancel/reset/actions, adotado em filtros, forms e workbench de treinamento. | nao alterar contrato de botao nem fluxo de permissao. |
| `ui-field-help` | `consolidado` | primitive neutro para ajuda/erro/sucesso por campo. | adocao ampla fica gradual; nao exige reescrita de todos os feedbacks existentes. |
| aliases legados `table-wrap`, `filters-bar`, `form-grid`, `form-actions` | `divida_visual_controlada` | continuam existindo por compatibilidade com CSS legado/backend e markup anterior. | novos pontos devem preferir `ui-table-*`/`ui-form-*` quando houver uso real. |

Politica de adocao: `adocao_gradual`. Padroes de tabela/formulario podem ser aplicados em superficies existentes quando reduzirem duplicacao visual ou hardcodes, sem alterar rota, loader, endpoint, submit, permissao, SSR ou runtime.

## 10. Aplicacao da fundacao visual na terceira superficie apos G07

G07 escolhe e aplica a fundacao visual na terceira superficie prioritaria: `tripulante_form_detail`, cobrindo as rotas SPA vivas `#/tripulantes/new` e `#/tripulantes/<id>`. A decisao do bloco e `fechado`.

Escolha objetiva:

| criterio | leitura material |
| --- | --- |
| superficie viva e relevante | `app/route-registry.js` registra `#/tripulantes/new` e `#/tripulantes/<id>` para `renderTripulanteFormPage`. |
| risco funcional controlavel | superficie SPA, sem SSR direto; contratos ficam em API `/api/v1/tripulantes...`, IDs de formulario e handlers existentes. |
| reaproveitamento G06 | formulario profundo, upload de foto/PDF, tabela de anexos, feedbacks e actions usam `ui-form-*`, `ui-table-*`, `ui-field-help`, `ui-surface`, `ui-stack` e `ui-cluster`. |
| dependencia compat residual | menor que relatorios/export SSR; usa APIs SPA e links hash. |
| custo/beneficio visual | alta densidade operacional com muita repeticao visual e baixo alcance lateral. |

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `frontend/src/features/tripulantes/form-page.js` | `adocao_visual_controlada` | `tripulante-detail-page-shell`, `priority-page-surface`, `priority-page-header`, `ui-surface`, `ui-stack`, `ui-cluster`, `ui-form-grid`, `ui-form-toolbar`, `ui-form-actions`, `ui-field-help`, `ui-table-wrap`, `ui-table-density-compact`, `ui-table-actions` e `ui-table-state`. | nao mudar submit, upload, delete, foto, anexos, validacao ou endpoints. |
| `frontend/src/app.css` | `consolidado` | bloco G07 escopado em `.tripulante-detail-page-shell`, usando tokens de spacing, surface, radius, shadow e mobile padding. | nao virar regra global de formulario nem reabrir dashboard/lista. |
| `tests/contract/test_frontend_third_surface_visual_foundation.py` | `consolidado` | garante escolha viva/roteada, adocao material e preservacao de contratos funcionais. | nao substitui teste visual end-to-end. |
| formularios/feedbacks legados fora desta superficie | `divida_visual_controlada` | ainda existem `field-feedback`, `section-feedback` e familias visuais antigas em outras superficies. | migrar apenas por blocos futuros especificos. |

Politica de adocao: `adocao_gradual`. G07 nao autoriza redesign completo, mudanca de rota, loader, guard, SSR, runtime ou expansao simultanea para outras superficies.

Bloqueio para proxima fase: nenhum `bloqueio_para_proxima_fase` material encontrado na fronteira frontend. A proxima fase ainda deve respeitar wrappers, compat, SSR vivo e build/runtime/env ja classificados.

## 11. Consolidacao minima de componentes compartilhados reais apos G08

G08 promove para `shared/ui` apenas padroes com reutilizacao material comprovada em superficies reais ja tratadas. A decisao do bloco e `fechado`.

| componente/padrao | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `ui-page-shell` | `consolidado` | padrao de wrapper de superficie adotado em dashboard, tripulantes, treinamentos, cadastro raiz, relatorios e `tripulante_form_detail`. | nao conhecer rota, loader, API, permissao, feature ou regra de dominio. |
| `ui-page-header` | `consolidado` | padrao de header de superficie adotado nas mesmas superficies com `priority-page-header` preservado como alias local/compat. | nao definir acao, titulo, breadcrumbs, exportacao, SSR ou semantica de pagina especifica. |
| aliases locais `priority-page-surface` e `priority-page-header` | `divida_visual_controlada` | continuam no markup e em `app.css` como ponte para blocos G03/G04/G07 e para checks de superficie. | novos usos devem compor com `ui-page-shell`/`ui-page-header` quando o padrao for de pagina, nao inventar alias local novo. |
| headers internos, toolbars de acao, summary cards e blocos de preview | `nao_promovido_agora` | aparecem com variacao de contexto, densidade e regra de dominio entre dashboard, relatorios, training-root e detalhe de tripulante. | so podem virar shared/ui em bloco futuro se cumprirem reutilizacao material, sem regra de dominio e sem props/contratos especificos demais. |

Politica de promocao: `shared/ui` aceita componente/padrao novo somente com evidencia em pelo menos duas superficies reais, estrutura visual/semantica consistente, ausencia de regra de dominio, reducao clara de repeticao e contrato simples. G08 nao autoriza design system inflado, quarta superficie, redesign amplo, motion, SSR, runtime ou deploy.

## 12. Readiness visual da terceira onda apos G09

Decisao de readiness: `pronta_para_expansao_visual`.

Esta decisao significa que a terceira onda visual ficou materialmente coerente para abrir uma quarta superficie prioritaria ou uma fase maior de refinamento visual controlado. Nao significa redesign completo, nao encerra a divida visual historica e nao autoriza promocao indiscriminada para `shared/ui`.

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `frontend/src/shared/ui/` | `consolidado` | segue limitado a `tokens.css`, `primitives.css` e README; primitives continuam sem dominio, API, router, shell ou feature. | nao virar design system inflado nem receber regra de produto. |
| `ui-page-shell` e `ui-page-header` | `componente_compartilhado_real` | reutilizados em dashboard, tripulantes, treinamentos, cadastro raiz, relatorios e `tripulante_form_detail`. | nao definir titulo, acao, breadcrumb, rota, permissao, endpoint ou SSR. |
| `ui-table-*` e `ui-form-*` | `componente_compartilhado_real` | adotados em tabelas/formularios de tripulantes, treinamentos, cadastro raiz, relatorios e detalhe de tripulante. | nao mudar submit, filtro, coluna, acao ou comportamento funcional. |
| shell/layout | `adocao_visual_controlada` | usa `ui-app-frame`, `ui-inverse-surface`, `ui-navigation-list`, `ui-sticky-surface`, `ui-cluster` e `ui-content-region`. | nao muda navegacao, login, redirects ou classificacao de links. |
| dashboard/tripulantes | `adocao_visual_controlada` | usa page primitives, `ui-surface`, `ui-feedback`, `ui-cluster`, table/form primitives e CSS escopado. | nao reabrir dashboard/lista ou rotas por limpeza visual. |
| treinamentos/relatorios | `adocao_visual_controlada` | usa page primitives, table/form primitives, surfaces, feedbacks, contexto/evidencias e CSS escopado. | nao mudar tabs, filtros, exports, impressao, PDF ou endpoints. |
| `tripulante_form_detail` | `adocao_visual_controlada` | usa page primitives, `ui-form-*`, `ui-table-*`, `ui-field-help`, `ui-surface`, `ui-stack` e `ui-cluster`. | nao mudar submit, upload, delete, validacao, foto, anexos ou endpoints. |
| aliases locais `priority-page-*`, `table-wrap`, `filters-bar`, `form-grid`, `form-actions` | `divida_visual_controlada` | continuam como compat controlada para blocos anteriores e CSS legado/backend. | nao remover por conveniencia; substituir apenas em bloco com prova e baixo drift. |
| headers internos, toolbars, summary cards, previews e familias visuais especificas | `divida_visual_controlada` | ainda variam por contexto e carregam semantica local. | `nao_promovido_agora` ate provar reutilizacao material sem regra de dominio. |
| `backend/src/controle_treinamentos/static/styles.css` e `admin/routes.py:748>725` | `baseline_fora_do_escopo` | CSS backend legado segue concatenado antes de `shared/ui`; baseline backend continua conhecido. | nao declarar resolvido neste bloco. |
| bloqueio para expansao visual | `bloqueio_para_expansao` | `0` item material. | manter checks G01-G09 verdes antes de expandir. |

Politica de expansao: a proxima etapa pode abrir quarta superficie ou refinamento visual controlado, desde que preserve rota, loader, guards, SSR, runtime, deploy, compat residual e ownership atual. Novo componente em `shared/ui` continua exigindo reutilizacao material comprovada em pelo menos duas superficies reais.

## 13. Aplicacao da fundacao visual na quarta superficie apos G10

G10 escolhe e aplica a fundacao visual na quarta superficie prioritaria: `training_record_detail`, cobrindo a rota SPA viva `#/treinamentos/<id>`. A decisao do bloco e `fechado`.

Escolha objetiva:

| criterio | leitura material |
| --- | --- |
| superficie viva e relevante | `app/route-registry.js` registra `pattern: /^#\/treinamentos\/\d+$/` para `renderTreinamentoFormPage`. |
| risco funcional controlavel | superficie SPA com formulario, anexos e tabela de PDFs; contratos ficam em APIs e handlers existentes. |
| reaproveitamento G06/G08 | usa `ui-form-*`, `ui-table-*`, `ui-field-help`, `ui-page-shell`, `ui-page-header`, `ui-surface`, `ui-stack` e `ui-cluster`. |
| dependencia compat residual | menor que superficies SSR/report; nao migra backend link ou compat residual. |
| custo/beneficio visual | alta densidade operacional com repeticao visual residual e baixo alcance lateral. |

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `frontend/src/features/treinamentos/form-page.js` | `adocao_visual_controlada` | `training-record-detail-page-shell`, `priority-page-surface`, `ui-page-shell`, `ui-page-header`, `ui-surface`, `ui-stack`, `ui-cluster`, `ui-form-grid`, `ui-form-actions` e `ui-field-help`. | nao mudar submit, delete, validacao, endpoints, rota ou loader. |
| `frontend/src/features/treinamentos/attachments.js` | `adocao_visual_controlada` | `training-record-attachment-panel`, `ui-form-toolbar`, `ui-table-wrap`, `ui-table-density-compact`, `ui-table-actions` e `ui-table-state`. | nao mudar upload, visualizar, download, delete de anexo ou permissoes. |
| `frontend/src/app.css` | `consolidado` | bloco G10 escopado em `.training-record-detail-page-shell`, usando tokens de spacing, surface, radius, shadow e mobile padding. | nao virar regra global de formularios/tabelas nem criar primitive de dominio. |
| `tests/contract/test_frontend_fourth_surface_visual_foundation.py` | `consolidado` | garante escolha viva/roteada, adocao material, preservacao funcional e CSS tokenizado. | nao substitui teste visual end-to-end. |
| `renderHoursReference(template)` | `divida_visual_controlada` | permanece local porque tambem atende superficies de treinamento ja tratadas e nao exige mudanca para fechar G10. | promover/refinar apenas em bloco futuro com criterio material. |
| `legacyRenderTreinamentoFormPage` | `encerrado_no_bloco_90` | funcao interna nao exportada removida da superficie SPA roteada. | manter o formulario SPA em `treinamentos-tripulantes`; generic API fica residual/historica fora do runtime normal. |

Politica de adocao: `adocao_gradual`. G10 nao autoriza redesign completo, mudanca de rota, loader, guard, SSR, runtime, deploy ou expansao simultanea para outras superficies.

## 14. Consolidacao visual final da expansao apos G11

Decisao de readiness: `pronta_para_encerramento_da_fase`.

Esta decisao significa que a fase visual incremental atual tem massa critica material para receber consolidacao executiva final. Nao significa que o frontend inteiro esta perfeito, nao encerra toda divida visual historica e nao autoriza redesign completo, quinta superficie, motion, SSR, runtime/deploy ou promocao indiscriminada para `shared/ui`.

| area | classificacao | evidencia material | restricao |
| --- | --- | --- | --- |
| `frontend/src/shared/ui/` | `consolidado` | contem apenas `tokens.css`, `primitives.css` e `README.md`; primitives seguem neutros de dominio, API, router, shell e feature. | nao virar design system inflado nem receber regra de produto. |
| `ui-page-shell` e `ui-page-header` | `componente_compartilhado_real` | reutilizados em dashboard, tripulantes, treinamentos, cadastro raiz, relatorios, `tripulante_form_detail` e `training_record_detail`. | nao definir titulo, rota, loader, permissao, endpoint ou SSR. |
| `ui-table-*` e `ui-form-*` | `componente_compartilhado_real` | adotados em tabelas/formularios densos das superficies tratadas, incluindo anexos de tripulante e registro de treinamento. | nao alterar submit, filtros, upload, delete, colunas ou contrato funcional. |
| shell/layout | `adocao_visual_controlada` | `render-shell.js` usa `ui-app-frame`, `ui-navigation-list`, `ui-content-region` e primitives estruturais. | nao mudar login, redirects, navegacao ou classificacao de links. |
| `dashboard/tripulantes` | `adocao_visual_controlada` | usa page primitives, surfaces, feedbacks, table/form patterns e CSS escopado. | nao reabrir dashboard/lista por limpeza visual. |
| `treinamentos/relatorios` | `adocao_visual_controlada` | usa page primitives, surfaces, table/form patterns e CSS escopado. | nao mudar tabs, filtros, exports, PDF, impressao ou endpoints. |
| `tripulante_form_detail` | `adocao_visual_controlada` | usa page primitives, form/table patterns, feedbacks, previews e CSS escopado G07. | nao mudar submit, upload, delete, validacao, foto, anexos ou endpoints. |
| `training_record_detail` | `adocao_visual_controlada` | usa page primitives, form/table patterns, feedbacks, anexos e CSS escopado G10. | nao mudar rota, submit, delete, upload, links de anexo, validacao ou endpoints. |
| aliases locais `priority-page-*`, `panel`, `table-wrap`, `filters-bar`, `form-grid`, `form-actions` | `divida_visual_controlada` | permanecem como ponte de migracao e compatibilidade com CSS legado/backend. | nao remover por conveniencia. |
| headers internos, toolbars, summary cards, previews e familias historicas | `divida_visual_controlada` | continuam locais porque ainda carregam variacao de contexto ou regra de dominio. | so promover com reutilizacao material e contrato neutro. |
| CSS backend/static, SSR compat, legacy e `admin/routes.py:748>725` | `baseline_fora_do_escopo` | seguem conhecidos e fora do aceite visual incremental. | nao declarar resolvido neste bloco. |
| bloqueio para encerramento | `bloqueio_para_encerramento` | `0` item material. | manter checks verdes para emitir consolidacao executiva. |

Politica final da fase: a proxima acao correta pode ser uma consolidacao executiva final da onda visual incremental. Qualquer nova superficie, redesign amplo, nova familia de componente ou promocao para `shared/ui` exige bloco proprio com prova material.

## 8. Conclusao da 30.2

O frontend oficial e um app estatico em `frontend/src`, com `frontend/src/app.js` como entrypoint fino, nucleo de bootstrap/router em `frontend/src/app/`, build por `frontend/scripts/build_frontend.py` e saida gerada em `frontend/dist`. A integracao real com backend passa por contrato JSON, sessao, CSRF, request/correlation id e origem configurada por variaveis `FRONTEND_*`.
