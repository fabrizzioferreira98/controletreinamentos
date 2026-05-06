# Relatorio consolidado - Execucao Task Force no chat

Data de geracao: 2026-05-02
Workspace: C:\apps\controle-treinamentos

## 1. Objetivo do documento

Este PDF consolida o que foi feito no chat: auditoria forense, canonicalizacao de superficies, deduplicacao de contratos, erradicacao de mocks em runtime, correcao e blindagem de Treinamentos Raiz, auditoria de vetores analogos, criacao de guardas arquiteturais SSR-to-SPA e limpeza do residual fisico pages-training-workspace.js.

O documento separa fonte canonica, compat residual, artefatos removidos, prova material, testes executados, criterio de fechamento e divida remanescente.

## 2. Linha do tempo dos blocos

| Bloco | Resultado | Criterio |
| --- | --- | --- |
| Auditoria forense inicial | Mapeou superficies atuais, legadas, dualidades, mocks e causas-raiz da convivencia hibrida | fechado quanto ao diagnostico |
| 89.canonical-surface-navigation-hardening | Reconfigurou navegacao principal para superficies canonicas SPA nas frentes migradas | fechado |
| 90.contract-route-deduplication-governance | Consolidou contratos/rotas principais de treinamentos, arquivos de tripulante e operacoes | fechado |
| 91.runtime-mock-data-eradication | Removeu mocks/placeholders de negocio em runtime e implementou estados honestos | fechado |
| Auditoria Treinamentos Raiz | Localizou cadeia material dashboard SSR -> tipos_list legado | fechado quanto a causa |
| 92.training-root-reentry-canonicalization | Corrigiu card SSR e encapsulou /tipos-treinamento* para SPA quando frontend compat ativo | fechado |
| 93.training-root-router-state-hardening | Blindou backend-links, redirects, fallback e restore contra retorno ao legado | fechado |
| Gate final Treinamentos Raiz | Validou primeira entrada, saida, reentrada e ausencia de retorno ao legado | fechado |
| Auditoria de casos analogos | Nao encontrou segundo bug analogo confirmado; classificou riscos residuais | fechado |
| 94.ssr-template-canonical-link-guards | Criou guardas contra links SSR casuais para superficies SPA canonicas | fechado |
| 95.residual-training-workspace-cleanup | Removeu pages-training-workspace.js como artefato fisico nao roteado | fechado |

## 3. Auditoria forense inicial

### 3.1 Superficies atuais e legadas mapeadas

- Superficie atual canonica SPA: frontend/src/app/route-registry.js e frontend/src/shell/navigation.js.
- Superficie legada viva SSR: templates e rotas em backend/src/controle_treinamentos/templates e blueprints cadastros/admin/operacoes/bases.
- Compatibilidade ativa: frontend/src/compat/backend-links.js e backend/src/controle_treinamentos/core/frontend_routes.py.
- Legado documentado: legacy/LIVE_LEGACY.md.
- Residuo fisico nao roteado inicialmente: frontend/src/pages-training-workspace.js, depois removido no bloco 95.

### 3.2 Duplicidades e convivencia perigosa identificadas

- Navegacao concorrente SPA shell + sidebar SSR.
- Treinamentos dividido entre treinamentos generico e training_program.
- Rotas duplicadas: /treinamentos, #/treinamentos, /api/v1/treinamentos e /api/v1/treinamentos-tripulantes.
- Arquivos de tripulante duplicados: /tripulantes/<id>/file* e /api/v1/tripulantes/<id>/files*.
- Operacoes/Pernoites com SSR ativo e API futura nao registrada.
- Link invalido relevante: BACKEND_LINKS.tipos = "/tipos" sem rota SSR correspondente, corrigido depois para /tipos-treinamento.

### 3.3 Mocks e dados artificiais identificados

- DASHBOARD_UPPER_SECTION_MOCK em frontend/src/features/dashboard-operacional/upper-section-data.js.
- DASHBOARD_LOWER_SECTION_MOCK em frontend/src/features/dashboard-operacional/lower-section-data.js.
- Dashboard operacional injetava esses mocks na renderizacao inicial.
- Mapa de bases iniciava com snapshot artificial antes de tentar /bases/api/dados.
- Backend injetava placeholder "Sem habilitacoes cadastradas" com is_placeholder em dashboard_cache.py.
- Stubs financeiros zerados classificados como mortos ou fora de runtime.

### 3.4 Causas-raiz da salada atual

- Migracao incremental com convivencia prolongada e sem cutover final.
- Fonte dupla de navegacao: SPA shell e templates SSR.
- Compatibilidade residual formal, segura para transicao, mas extensa demais.
- Artefatos gerados/runtime convivendo perto da fonte canonica e aumentando ruido.

## 4. Bloco 89 - Canonical surface navigation hardening

### 4.1 Superficies canonicas definidas

- Painel Geral: /#/dashboard.
- Dashboard Operacional: /#/dashboard-operacional.
- Relatorio habilitacoes: /#/relatorios/habilitacoes.
- Relatorio individual: /#/relatorios/individual.
- Tripulantes: /#/tripulantes.
- Treinamentos: /#/treinamentos.
- Treinamentos Raiz: /#/treinamentos/raiz.
- Financeiro: /#/financeiro/*.
- Bases, Equipamentos, Usuarios/Admin: SSR mantido por necessidade formal.

### 4.2 Resultado

- Sidebar SSR principal reapontada para hashes canonicos nas frentes migradas.
- Cards de dashboard reapontados para superficies canonicas.
- BACKEND_LINKS.tipos corrigido de /tipos para /tipos-treinamento.
- SSR concorrente deixou de ser rota normal descoberta por menu principal.

### 4.3 Testes

- Gate focal com 16 passed.
- Testes de navegacao, sidebar SSR e compat adapter ajustados.

## 5. Bloco 90 - Contract route deduplication governance

### 5.1 Classificacao final

- Treinamentos: SPA #/treinamentos + contrato /api/v1/treinamentos-tripulantes como principal; /api/v1/treinamentos como compat residual.
- Arquivos de tripulante: /api/v1/tripulantes/<id>/files* como principal; /tripulantes/<id>/file* como compat direto.
- Operacoes/Pernoites: SSR /pernoites* ratificado como canonico atual direto; API futura nao registrada e nao canonica.

### 5.2 Mudancas principais

- Endpoints canonicos de anexos em /api/v1/treinamentos-tripulantes/<id>/attachments*.
- Frontend de treinamentos passou a usar contrato training_program.
- FutureHref de operacoes deixou de aparecer como rota futura navegavel.

### 5.3 Testes

- Gate focal: 84 passed in 37.93s.
- Build frontend focal temporario executado com sucesso.

## 6. Bloco 91 - Runtime mock data eradication

### 6.1 Removido do runtime

- DASHBOARD_UPPER_SECTION_MOCK.
- DASHBOARD_LOWER_SECTION_MOCK.
- Snapshot artificial inicial do mapa de bases.
- Placeholder backend "Sem habilitacoes cadastradas" como pseudo-dado.

### 6.2 Estados honestos implementados

- Loading honesto.
- Vazio honesto.
- Erro honesto.
- Dados reais via APIs existentes.
- NOTAM sem contrato real fica vazio honesto, nao fake.

### 6.3 Testes e build

- Gate focal: 32 passed in 12.01s.
- Build oficial executado.
- Varredura em source/dist/runtime sem ocorrencia dos mocks removidos.

## 7. Treinamentos Raiz - Auditoria, correcao, hardening e gate final

### 7.1 Causa material localizada

Cadeia incorreta encontrada:

    dashboard SSR -> link/card residual -> cadastros.tipos_list -> /tipos-treinamento -> tipos_list.html legado

Conclusoes:

- O problema nao estava no menu principal SPA.
- Nao havia prova de cache.
- Nao havia prova de restore de ultima rota SPA.
- A causa era uma cadeia SSR residual descoberta casualmente.

### 7.2 Correcao do bloco 92

- Card SSR Tipos ativos corrigido para /#/treinamentos/raiz com hx-boost=false.
- GET /tipos-treinamento* redireciona para #/treinamentos/raiz quando frontend compat esta ativo.
- Mutacoes SSR residuais retornam para a superficie canonica quando compat esta ativa.
- SSR de tipos permanece apenas como fallback backend-only.

Testes:

- 30 passed no gate de canonicalizacao.
- 22 passed na integracao de catalogos SSR.

### 7.3 Hardening do bloco 93

- BACKEND_LINKS.tipos reclassificado como backend_ssr_compat_redirect_only.
- /tipos e /tipos-treinamento mapeados para #/treinamentos/raiz.
- navigation-state canonicaliza pathname backend antes de fallback/restore.
- Restore aceita apenas hashes #/... e nao persiste path legado.

Testes:

- 40 passed no gate de router/compat/navigation.
- 24 passed em integracao/arquitetura de catalogos.

### 7.4 Gate final especifico

- Primeira entrada validada em #/treinamentos/raiz.
- Saida para dashboard e reentrada validada.
- /tipos-treinamento, /tipos-treinamento/novo e /tipos-treinamento/<id>/editar retornam 302 para hash canonica.
- Corpo nao renderiza Tipos de Treinamento nem tipos_list.html.

Testes:

- Gate isolado: 4 passed.
- Bateria complementar: 64 passed.

## 8. Auditoria de casos analogos

### 8.1 Resultado

Nenhum segundo bug analogo confirmado.

Nao foi encontrada outra cadeia material do tipo:

    entrada inicial correta SPA -> saida -> reentrada casual por dashboard/card/sidebar/compat -> tela SSR antiga equivalente

### 8.2 Classificacoes relevantes

- Treinamentos Raiz: sem bug ativo; compat redirect-only.
- Treinamentos por tripulante: compat controlada aceitavel.
- Tripulantes: compat controlada aceitavel.
- Relatorio de habilitacoes: compat documental/export aceitavel.
- Relatorio individual: risco relevante de fronteira, nao bug analogo confirmado, pois SPA atua como seletor e detalhe segue documento SSR.
- Financeiro: sem SSR concorrente encontrado.
- Bases/Equipamentos/Usuarios/Operacoes: fora do padrao analogo quando ainda canonicos SSR ou sem SPA equivalente.

### 8.3 Testes

- Gate focal de navegacao/canonicalizacao: 68 passed in 48.51s.

## 9. Bloco 94 - SSR template canonical link guards

### 9.1 Superficies protegidas

- Tripulantes: /#/tripulantes.
- Treinamentos: /#/treinamentos.
- Treinamentos Raiz: /#/treinamentos/raiz.
- Relatorio de habilitacoes: /#/relatorios/habilitacoes.
- Relatorio individual: /#/relatorios/individual.

### 9.2 Guardas implementados

- tests/architecture/test_ssr_template_canonical_link_guards.py bloqueia url_for legado em templates descobertos pelo usuario.
- Templates publicos protegidos: base.html e dashboard.html.
- Guard exige hashes canonicos SPA nos templates publicos.
- Guard varre todos os templates SSR e exige excecao formal para residual legado.
- Payload runtime do dashboard nao pode reconstruir cadastros.treinamentos_edit; usa /#/treinamentos/<id>.

### 9.3 Mudancas em dashboard SSR

- Tripulantes: /#/tripulantes.
- Tipos ativos: /#/treinamentos/raiz.
- Treinamentos: /#/treinamentos.
- Alertas/status/lista critica: hashes SPA de treinamentos.
- training_url do calendario SSR: /#/treinamentos/<id>.

### 9.4 Testes

- Guard isolado: 5 passed.
- Gate focal completo: 73 passed in 49.47s.

## 10. Bloco 95 - Residual training workspace cleanup

### 10.1 Classificacao

- Fonte canonica viva: frontend/src/pages-treinamentos-relatorios.js, carregado pelo route-registry.
- Owners canonicos: frontend/src/features/treinamentos e frontend/src/features/training-root.
- Artefato removivel: frontend/src/pages-training-workspace.js, sem loader, sem rota, sem importador e sem compat formal.
- frontend/dist: artefato gerado, regenerado.
- frontend/runtime, frontend/frontend/runtime e frontend/ops/artifacts: historico operacional fora do corte de fonte viva.

### 10.2 Resultado

- Removido frontend/src/pages-training-workspace.js.
- frontend/dist regenerado sem pages-training-workspace.*.js.
- Testes impedem retorno como modulo fisico nao roteado.
- Arquitetura marca pages-training-workspace.js como artefato_removido.

### 10.3 Testes

- Build canonico regenerado com autorizacao elevada apos falha inicial por permissao no dist.
- Gate focal: 33 passed in 0.96s.
- validate_repo_hygiene.py ainda vermelho por baseline global fora do corte: .env, runtime, ops/artifacts, .ruff_cache, __pycache__ e docs financeiros nao registrados.

## 11. Provas materiais principais por arquivo

- frontend/src/app/route-registry.js: registro de rotas SPA canonicas.
- frontend/src/shell/navigation.js: menu SPA canonico.
- frontend/src/compat/backend-links.js: fronteira de links backend/SSR e aliases canonicos.
- frontend/src/state/navigation-state.js: canonicalizacao de pathname antes de fallback/restore.
- backend/src/controle_treinamentos/templates/base.html: sidebar SSR reapontada.
- backend/src/controle_treinamentos/templates/dashboard.html: cards/atalhos SSR reapontados.
- backend/src/controle_treinamentos/blueprints/cadastros/routes_catalogos.py: redirects /tipos-treinamento*.
- backend/src/controle_treinamentos/blueprints/dashboard/routes.py: training_url do dashboard SSR usando hash SPA.
- frontend/src/features/dashboard-operacional/page.js: runtime sem mock inicial artificial.
- backend/src/controle_treinamentos/repositories/dashboard_cache.py: sem pseudo-habilitacao placeholder.
- tests/architecture/test_ssr_template_canonical_link_guards.py: guard SSR-to-SPA.
- tests/contract/test_training_root_release_gate.py: gate final de Treinamentos Raiz.
- tests/contract/test_frontend_page_module_boundaries.py: guard contra retorno do residual pages-training-workspace.js.

## 12. Testes executados e resultados citados

- Bloco 89: gate focal 16 passed; suite adicional com falhas preexistentes fora do escopo em baseline visual/compat.
- Bloco 90: 84 passed in 37.93s.
- Bloco 91: 32 passed in 12.01s.
- Bloco 92: 30 passed; integracao catalogos 22 passed.
- Bloco 93: 40 passed; integracao/arquitetura 24 passed.
- Gate final Treinamentos Raiz: 4 passed isolado; 64 passed complementar.
- Auditoria analogos: 68 passed in 48.51s.
- Bloco 94: 5 passed isolado; 73 passed focal completo.
- Bloco 95: 33 passed in 0.96s.

## 13. Criterio consolidado de fechamento

Fechado para os blocos executados porque:

- Navegacao principal expoe superficies canonicas por intencao nas frentes migradas.
- Treinamentos e arquivos de tripulante possuem contrato principal explicito e compat residual classificada.
- Operacoes/Pernoites foram ratificados como SSR canonico atual, sem ambiguidade de API futura.
- Dashboard operacional nao inicia mais com payload fake.
- Treinamentos Raiz nao retorna ao legado por entrada, saida, reentrada, fallback, redirect ou restore normal.
- Templates SSR publicos estao protegidos por guard arquitetural.
- pages-training-workspace.js foi removido da fonte viva e do dist gerado.

## 14. Divida remanescente consolidada

- Templates SSR legados ainda existem como compat autocontida.
- Relatorio individual ainda abre documento SSR por ausencia de detalhe SPA equivalente formal.
- Bases/Equipamentos/Usuarios/Admin permanecem SSR/compat onde nao ha SPA canonica equivalente.
- /api/v1/treinamentos ainda existe como compat residual historico.
- /tripulantes/<id>/file* ainda existe como compat direto.
- Operacoes/Pernoites permanecem SSR canonico atual; migracao para API/SPA exige bloco futuro.
- NOTAMs e meteorologia completa ainda dependem de contrato/agregador real; hoje ficam em estado honesto.
- validate_repo_hygiene.py ainda vermelho por baseline global fora do corte.
- C-pias historicas em runtime/artifacts nao foram apagadas em lote para preservar evidencia operacional.

## 15. Arquivos de migration registrados

- docs/migration/89.canonical-surface-navigation-hardening.md
- docs/migration/90.contract-route-deduplication-governance.md
- docs/migration/91.runtime-mock-data-eradication.md
- docs/migration/92.training-root-reentry-canonicalization.md
- docs/migration/93.training-root-router-state-hardening.md
- docs/migration/94.ssr-template-canonical-link-guards.md
- docs/migration/95.residual-training-workspace-cleanup.md



# Apendice - registros de migration existentes


## 89.canonical-surface-navigation-hardening.md

# 89 - Canonical surface navigation hardening

## Contexto

A auditoria confirmou convivencia longa entre superficies SPA e SSR, com concorrencia de navegacao para a mesma intencao funcional. O objetivo deste bloco foi remover concorrencia na navegacao principal sem big bang e sem apagar compatibilidade viva.

## Superficie canonica por intencao

| intencao | superficie canonica | compat SSR controlada | estado |
| --- | --- | --- | --- |
| Painel Geral | `/#/dashboard` | `/dashboard` com redirect compat para hash | consolidado |
| Dashboard Operacional | `/#/dashboard-operacional` | n/a | consolidado |
| Relatorio de habilitacoes | `/#/relatorios/habilitacoes` | `/treinamentos/consolidado` com redirect compat | consolidado |
| Relatorio individual | `/#/relatorios/individual` | acesso SSR historico por listagem de tripulantes | consolidado |
| Tripulantes | `/#/tripulantes` | `/tripulantes` com redirect compat | consolidado |
| Treinamentos por tripulante | `/#/treinamentos` | `/treinamentos` com redirect compat | consolidado |
| Cadastro raiz de treinamentos | `/#/treinamentos/raiz` | `/tipos-treinamento` como compat controlada | consolidado |
| Financeiro | `/#/financeiro/*` | n/a | consolidado |
| Bases, Equipamentos, Usuarios, Monitoramento, Notificacoes, Backups, Auditoria | backend SSR em `BACKEND_LINKS` | necessario nesta fase | compat necessario |

## Mudanca aplicada

- `frontend/src/compat/backend-links.js`
  - correcao de `BACKEND_LINKS.tipos`: de `"/tipos"` para `"/tipos-treinamento"`.
- `frontend/src/features/dashboard/page.js`
  - card `Tipos ativos` reapontado de `BACKEND_LINKS.tipos` para `#/treinamentos/raiz`.
- `frontend/src/features/dashboard-operacional/page.js`
  - card `Tipos ativos` reapontado de `BACKEND_LINKS.tipos` para `#/treinamentos/raiz`.
- `backend/src/controle_treinamentos/templates/base.html`
  - links principais da sidebar SSR reapontados para hash canonico (`/#/...`) com `hx-boost="false"`:
    - `Painel Geral`
    - `Relatorios > Consolidado de habilitacoes`
    - `Relatorios > Relatorio individual`
    - `Cadastros > Tripulantes`
    - `Cadastros > Treinamentos por tripulante`
    - `Cadastros > Cadastro raiz treinamentos`
  - links SSR realmente necessarios foram preservados (ex.: `Bases`, `Equipamentos`, `Usuarios` e derivados admin).

## Isolamento do legado

- legado SSR concorrente deixou de ser rota normal descoberta via navegacao principal para as intencoes ja canonicas em SPA;
- permanencia SSR ficou restrita a compatibilidade controlada e a frentes sem substituto SPA nesta fase.

## Prova material

- `frontend/src/compat/backend-links.js` nao contem mais `"/tipos"` e mantem mapping `"/tipos-treinamento" -> "#/treinamentos/raiz"`.
- `frontend/src/features/dashboard/page.js` e `frontend/src/features/dashboard-operacional/page.js` apontam `Tipos ativos` para `#/treinamentos/raiz`.
- `backend/src/controle_treinamentos/templates/base.html` aponta entradas principais concorrentes para `/#/...` com `hx-boost="false"`.

## Validacao focal

- contratos atualizados para refletir cutover:
  - `tests/contract/test_frontend_compat_adapter_boundaries.py`
  - `tests/contract/test_frontend_priority_page_visual_foundation.py`
  - `tests/contract/test_frontend_responsive_dashboard_policy.py`
  - `tests/contract/test_backend_ssr_sidebar_shell.py`
- criterio de validacao deste bloco:
  - navegacao principal exposta com uma superficie por intencao;
  - ausencia de link quebrado `/tipos`;
  - SSR preservado apenas como compatibilidade controlada onde ainda necessario.

## Rollback seguro

1. Reverter os links hash em `backend/src/controle_treinamentos/templates/base.html` para os `url_for(...)` anteriores.
2. Reverter `BACKEND_LINKS.tipos` para `"/tipos"` apenas se a rota voltar a existir com contrato valido.
3. Reverter os cards `Tipos ativos` para `BACKEND_LINKS.tipos` se a estrategia canonia voltar para SSR.

Rollback so e aceitavel com prova de regressao funcional critica em fluxo vivo.


## 90.contract-route-deduplication-governance.md

# 90 - Contract route deduplication governance

## Contexto

O bloco 89 fechou a navegacao canonica. Este bloco reduz a dualidade estrutural restante em contratos e rotas, sem alterar schema e sem remover leitura historica necessaria.

## Dualidades classificadas

| frente | canonico | compat residual | classificacao aplicada |
| --- | --- | --- | --- |
| Treinamentos por tripulante | SPA `#/treinamentos` + API `/api/v1/treinamentos-tripulantes` | API generica `/api/v1/treinamentos` para historico simples e compat | `canonico_programa_segmentado`; generic fica fora do runtime SPA normal |
| Cadastro raiz de treinamentos | SPA `#/treinamentos/raiz` + API `/api/v1/treinamento-raiz/*` | SSR `/tipos-treinamento` como compat de rota | `canonico_raiz_spa_api` |
| Anexos de treinamento no fluxo por tripulante | `/api/v1/treinamentos-tripulantes/<id>/attachments*` | `/api/v1/treinamentos/<id>/attachments*` para compat historica | `canonico_program_attachment` |
| Arquivos de tripulante | SPA `#/tripulantes/:id` + API `/api/v1/tripulantes/<id>/files*` | SSR `/tripulantes/<id>/file*` direto/compat | `canonico_spa_api`; SSR nao entra em shell nem em backend-links |
| Operacoes/Pernoites | SSR `/pernoites*` | API futura `/api/v1/operacoes/*` apenas candidata nao registrada | `ssr_canonical_current_direct` |

## Mudanca aplicada

- `frontend/src/features/treinamentos/form-page.js`
  - removeu a funcao interna `legacyRenderTreinamentoFormPage`;
  - trocou upload/delete de anexos para `/api/v1/treinamentos-tripulantes/<id>/attachments*`.
- `backend/src/controle_treinamentos/api/http/cadastros/routes_training_program.py`
  - adicionou endpoints canonicos de anexos sob `/api/v1/treinamentos-tripulantes/<id>/attachments*`;
  - serializa links de anexos pelo namespace canonico do programa.
- `backend/src/controle_treinamentos/contracts/training_program.py`
  - `links.attachments` do registro por programa aponta para `/api/v1/treinamentos-tripulantes/<id>/attachments`.
- `backend/src/controle_treinamentos/contracts/treinamentos.py`
  - `serialize_treinamento_attachment` aceita `links_base_path`, mantendo default generico para compat e permitindo links canonicos no contrato de programa.
- `backend/src/controle_treinamentos/contracts/operacoes.py`
  - Pernoites deixa de ser `ssr_compat` ambiguo e passa a `ssr_canonical_current_direct`;
  - API futura fica `candidate_not_registered_not_canonical`.
- `frontend/src/compat/backend-links.js`
  - `/pernoites` e `/pernoites/novo` classificados como `ssr_canonical_current_direct`, fora da navegacao principal.
- `frontend/src/features/dashboard-operacional/lower-section-data.js`
  - removeu pseudo-rotas futuras desabilitadas (`futureHref`) e substituiu por `futureIntent`.

## Compatibilidade mantida

- `/api/v1/treinamentos` permanece vivo para leitura/CRUD historico do contrato simples, mas nao e mais consumidor do formulario SPA roteado.
- `/api/v1/treinamentos/<id>/attachments*` permanece vivo como compat de anexos historicos.
- `/tripulantes/<id>/file*` permanece vivo como acesso direto SSR de documentos, sem entrada em shell principal.
- `/pernoites*` permanece vivo e foi ratificado como contrato SSR atual ate um bloco dedicado de API/SPA.

## Protecoes

- `tests/architecture/test_contract_route_deduplication_governance.py`
  - garante `treinamentos-tripulantes` como contrato runtime da SPA;
  - garante anexos canonicos no namespace de programa;
  - garante arquivos de tripulante via API na SPA e SSR File fora do shell;
  - garante Operacoes sem API futura canonica registrada e sem `futureHref` runtime.
- `tests/contract/test_api_training_program_contract.py`
  - cobre os novos endpoints canonicos de anexos do programa.
- `tests/contract/test_operacoes_contract.py`
  - cobre `ssr_canonical_current_direct` e API futura nao canonica.
- `tests/unit/test_auth_permissions.py`
  - cobre RBAC explicito dos novos endpoints canonicos de anexos.

## Criterio de fechamento

`fechado` para a navegacao/fluxo principal das tres frentes:

- Treinamentos por tripulante tem SPA e API canonicas unicas para registro e anexos.
- Arquivos de tripulante tem API canonica no fluxo SPA; SSR ficou direto/compat e nao descoberto pelo shell.
- Operacoes tem SSR canonico atual; API futura nao e registrada nem canonica.

## Divida remanescente

- Remover `/api/v1/treinamentos` exige bloco proprio de migracao de historico simples e consumidores externos.
- Remover `/api/v1/treinamentos/<id>/attachments*` exige janela de compat e prova de ausencia de consumidores.
- Migrar Pernoites para API/SPA exige bloco de produto/contrato separado; ate la SSR e o canonico atual.
- Remover `/tripulantes/<id>/file*` exige prova de ausencia de acesso direto/operacional ao SSR File.


## 91.runtime-mock-data-eradication.md

# 91 - Runtime mock data eradication

## Contexto

Os blocos 89 e 90 fecharam navegacao canonica e deduplicacao de contratos. Este bloco remove dados artificiais ainda visiveis no runtime, sem reabrir rotas, menus ou contratos principais.

## Classificacao

| item | classificacao | decisao |
| --- | --- | --- |
| `DASHBOARD_UPPER_SECTION_MOCK` | mock ativo em runtime | removido; substituido por contrato vazio honesto e dados reais de APIs existentes |
| `DASHBOARD_LOWER_SECTION_MOCK` | mock ativo em runtime | removido; meteorologia usa AISWEB real quando disponivel, NOTAMs ficam vazios ate existir contrato real |
| mapa de bases com snapshot artificial | fallback artificial indevido | removido; a renderizacao usa `/bases/api/dados` ou mostra vazio/erro real |
| `Sem habilitacoes cadastradas` com `is_placeholder` | placeholder de negocio em runtime | removido do repository; tripulante sem habilitacao agora possui lista vazia e `has_habilitacoes=false` |
| `FINANCE_STUB_HTTP_CONTRACTS` e `FINANCE_STUB_API_PATHS` | stub morto/segregado | permanecem tuplas vazias e protegidas por teste; nao ha rota stub registrada |
| `_FakeDB`, monkeypatches e fixtures de testes | stub de teste isolado | mantidos apenas em `tests/`, sem import por runtime |
| placeholders de campos HTML | placeholder de UI aceitavel | mantidos como instrucao de entrada, sem fingir registro de negocio |

## Mudanca aplicada

- `frontend/src/features/dashboard-operacional/upper-section-data.js`
  - deixou de exportar `DASHBOARD_UPPER_SECTION_MOCK`;
  - passou a exportar `DASHBOARD_UPPER_SECTION_EMPTY` e `DASHBOARD_EMPTY_BASE_OPERATIONS`.
- `frontend/src/features/dashboard-operacional/lower-section-data.js`
  - deixou de exportar `DASHBOARD_LOWER_SECTION_MOCK`;
  - separou `DASHBOARD_OPERATIONAL_QUICK_ACTIONS` como configuracao de UI, sem meteorologia/NOTAM artificiais.
- `frontend/src/features/dashboard-operacional/page.js`
  - removeu imports dos mocks;
  - monta secao superior a partir de `/api/v1/dashboard/summary`, `/api/v1/dashboard/critical-trainings-limit=20` e `/bases/api/dados`;
  - monta secao inferior com AISWEB real quando disponivel, NOTAM vazio honesto e atalhos de UI;
  - deixou de inicializar o mapa com snapshot artificial antes da API.
- `backend/src/controle_treinamentos/repositories/dashboard_cache.py`
  - removeu criacao de item pseudo-habilitacao `Sem habilitacoes cadastradas`;
  - passa a retornar grupo com `habilitacoes=[]` e `has_habilitacoes=false`.
- `backend/src/controle_treinamentos/contracts/dashboard.py`
  - adicionou `alerts.vencem_hoje` real para evitar numero artificial no card de vencimentos.
- `backend/src/controle_treinamentos/contracts/relatorios.py`
  - expõe `has_habilitacoes` no contrato serializado.
- Templates e SPA de relatorio exibem linha de estado vazio quando um tripulante real nao possui habilitacoes no recorte.

## Protecoes

- `tests/architecture/test_runtime_mock_data_eradication.py`
  - bloqueia reintroducao de `DASHBOARD_UPPER_SECTION_MOCK`, `DASHBOARD_LOWER_SECTION_MOCK`, blueprints artificiais e fallback local no dashboard operacional;
  - garante que o dashboard inicial use endpoints reais ou estado vazio/erro;
  - garante ausencia do placeholder de negocio no repository;
  - garante stubs financeiros vazios e fora de runtime.
- `tests/contract/test_api_dashboard_contract.py`
  - cobre `alerts.vencem_hoje`.
- `tests/unit/test_hot_query_tuning_p1_2.py`
  - cobre tripulante sem habilitacao como lista vazia honesta.

## Criterio de fechamento

`fechado` para mock de negocio em runtime no dashboard operacional e para o placeholder material de habilitacoes.

## Divida remanescente

- Meteorologia por todas as bases e NOTAMs continuam sem contrato agregador proprio; ate existir API real, a UI exibe vazio honesto em vez de mock.
- Fixtures e stubs de testes permanecem em `tests/`, isolados do runtime.
- Artefatos antigos em diretorios temporarios de build nao sao fonte viva; a publicacao real deve sempre regerar `frontend/dist/`.


## 92.training-root-reentry-canonicalization.md

# 92 - Training root reentry canonicalization

## Contexto

A auditoria focal confirmou que `Treinamentos Raiz` abria corretamente pela primeira entrada SPA, mas podia retornar para a tela SSR antiga quando o usuario passava pelo dashboard SSR. A cadeia material era:

- menu SPA `#/treinamentos/raiz` abre a superficie nova;
- dashboard SSR ainda tinha card `Tipos ativos` apontando para `cadastros.tipos_list`;
- `cadastros.tipos_list` resolvia para `/tipos-treinamento`;
- `/tipos-treinamento` ainda renderizava `tipos_list.html`.

## Superficie canonica fixada

| intencao | entrada normal | contrato de superficie | residual |
| --- | --- | --- | --- |
| Cadastro raiz de treinamentos | `/#/treinamentos/raiz` | `frontend/src/features/training-root/page.js` | `/tipos-treinamento*` apenas como compat SSR quando o frontend oficial nao estiver ativo |

## Mudanca aplicada

- `backend/src/controle_treinamentos/templates/dashboard.html`
  - o card `Tipos ativos` foi reapontado para `/#/treinamentos/raiz`;
  - o link recebeu `hx-boost="false"` para impedir que o `hx-boost` global do SSR intercepte a hash route.
- `backend/src/controle_treinamentos/blueprints/cadastros/routes_catalogos.py`
  - GET `/tipos-treinamento` redireciona para `#/treinamentos/raiz` quando `frontend_compat_enabled()` esta ativo;
  - GET `/tipos-treinamento/novo` e GET `/tipos-treinamento/<id>/editar` tambem redirecionam para a superficie canonica em modo frontend oficial;
  - mutacoes SSR residuais de tipos passam a retornar para a superficie canonica quando a compat frontend esta ativa.
- `backend/src/controle_treinamentos/blueprints/dashboard/routes.py`
  - import de `frontend_compat_enabled` foi explicitado para manter o redirect compat de `/dashboard` funcional.

## Politica final

- Navegacao normal, cards, atalhos e reentrada devem usar `/#/treinamentos/raiz`.
- `/tipos-treinamento*` nao e entrada casual de usuario quando o frontend oficial esta ativo.
- O SSR de tipos permanece apenas como fallback compat em ambiente sem frontend oficial, sem promocao em menu/card principal.

## Protecoes

- `tests/contract/test_training_root_canonical_reentry.py`
  - garante que a superficie SPA continua registrada;
  - garante que o dashboard SSR nao aponta para `cadastros.tipos_list`;
  - garante que a rota legada esta encapsulada por redirect compat.
- `tests/contract/test_frontend_compat_redirects.py`
  - cobre o redirect de `/tipos-treinamento`, `/tipos-treinamento/novo` e `/tipos-treinamento/<id>/editar` para `#/treinamentos/raiz` quando o frontend oficial esta ativo.
- `tests/contract/test_frontend_navigation_stability.py`
  - garante indexacao deste bloco no `README.md`.

## Criterio de fechamento

`fechado`: a navegacao normal para `Treinamentos Raiz` fica canonica por primeira entrada e reentrada; o card SSR residual foi corrigido; `/tipos-treinamento*` deixou de renderizar a tela antiga quando a compat frontend esta ativa.

## Divida remanescente

- Remover definitivamente templates SSR `tipos_list.html` e `tipos_form.html` exige prova de ausencia de ambiente backend-only e consumidores operacionais diretos.
- `pages-training-workspace.js` segue como residual frontend nao roteado ja classificado em bloco anterior.


## 93.training-root-router-state-hardening.md

# 93 - Training root router state hardening

## Contexto

O bloco 92 corrigiu a cadeia material que fazia `Treinamentos Raiz` reabrir a tela SSR antiga pela reentrada via dashboard. Este bloco blinda os vetores de regressao em compat, redirects, fallback e restore.

## Normalizacao aplicada

- `frontend/src/compat/backend-links.js`
  - declara `CANONICAL_FRONTEND_HASHES.trainingRoot` como `#/treinamentos/raiz`;
  - reclassifica `BACKEND_LINKS.tipos` como `backend_ssr_compat_redirect_only`;
  - mapeia `/tipos-treinamento` para `#/treinamentos/raiz`;
  - mapeia o alias historico `/tipos` para `#/treinamentos/raiz`;
  - adiciona `resolveFrontendHashForBackendPath()` como resolver unico de path backend conhecido para hash SPA canonica.
- `frontend/src/state/navigation-state.js`
  - canonicaliza `window.location.pathname` via `resolveFrontendHashForBackendPath()` antes de qualquer fallback de rota;
  - preserva `normalizeHashRoute()` como filtro de restore, impedindo path SSR legado de entrar em `last_successful_route` ou `return_route`.
- `docs/architecture/FRONTEND_ARCHITECTURE.md`
  - documenta `backend_ssr_compat_redirect_only` como path legado apenas redirecionavel, proibido como href de runtime.

## Politica final

- Runtime normal deve navegar para `#/treinamentos/raiz`.
- `/tipos-treinamento` e `/tipos` podem ser interpretados apenas como aliases de entrada historica para a hash canonica.
- `BACKEND_LINKS.tipos` nao deve ser usado por feature, shell, card ou atalho como href renderizado.
- Fallback autenticado continua limitado a return route valida, last successful route valida ou `#/dashboard`; path SSR legado nao e restorable.

## Protecoes

- `tests/contract/test_frontend_compat_adapter_boundaries.py`
  - garante canonical hash, alias `/tipos`, mapping `/tipos-treinamento` e boundary `backend_ssr_compat_redirect_only`.
- `tests/contract/test_frontend_navigation_stability.py`
  - garante que `navigation-state` canonicaliza pathname backend antes de fallback/restore;
  - garante que esta migration esta indexada no README.
- `tests/contract/test_training_root_canonical_reentry.py`
  - garante que nenhum modulo JS de runtime usa `BACKEND_LINKS.tipos` como href fora do adapter compat;
  - preserva a prova de `.training-root-page-shell` como superficie SPA normal.

## Criterio de fechamento

`fechado`: `Treinamentos Raiz` fica protegido contra retorno ao legado por link, compat adapter, entrada pathname, fallback autenticado ou restore de rota.

## Divida remanescente

- Remocao definitiva de `/tipos-treinamento*` depende de retirada formal do fallback SSR backend-only.
- Remocao de `pages-training-workspace.js` permanece em backlog de modulo frontend nao roteado.


## 94.ssr-template-canonical-link-guards.md

# 94. SSR template canonical link guards

## Bloco executado

Architecture guarding para impedir regressao de links casuais SSR para superficies ja migradas para SPA.

## Superficies protegidas

- Tripulantes: entrada publica canonica `/#/tripulantes`; residual SSR `cadastros.tripulantes_*` apenas em templates legados autocontidos.
- Treinamentos: entrada publica canonica `/#/treinamentos`; residual SSR `cadastros.treinamentos_*` apenas em templates legados autocontidos.
- Treinamentos Raiz: entrada publica canonica `/#/treinamentos/raiz`; residual SSR `cadastros.tipos_*` apenas em templates legados autocontidos ou redirect compat.
- Relatorio de habilitacoes: entrada publica canonica `/#/relatorios/habilitacoes`; residual SSR `cadastros.treinamentos_consolidado` apenas em templates de relatorio/export legado.
- Relatorio individual: entrada publica canonica `/#/relatorios/individual`; detalhe documental SSR de tripulante segue como excecao operacional ate existir detalhe SPA equivalente.

## Guardas implementados

- `tests/architecture/test_ssr_template_canonical_link_guards.py` bloqueia `url_for(...)` legado em templates descobertos pelo usuario, incluindo `base.html` e `dashboard.html`.
- O mesmo teste exige que templates publicos mantenham hashes canonicos SPA para as superficies migradas.
- O mesmo teste varre todos os templates SSR e falha se surgir endpoint legado migrado fora da lista formal de excecoes.
- O dashboard SSR nao pode reconstruir `cadastros.treinamentos_edit` em payload runtime; atalhos de treinamento devem usar `/#/treinamentos/<id>`.

## Excecoes formais documentadas

Estas excecoes sao residual compat controlado, nao entrada normal de usuario:

- `tipos_form.html`: `cadastros.tipos_list`.
- `tipos_list.html`: `cadastros.tipos_new`, `cadastros.tipos_edit`.
- `treinamentos_consolidado.html`: `cadastros.treinamentos_consolidado`, `cadastros.treinamentos_edit`, `cadastros.treinamentos_list`.
- `treinamentos_consolidado_relatorio.html`: `cadastros.treinamentos_consolidado`.
- `treinamentos_form.html`: `cadastros.treinamentos_list`.
- `treinamentos_list.html`: `cadastros.treinamentos_edit`, `cadastros.treinamentos_list`, `cadastros.treinamentos_new`.
- `tripulantes_file.html`: `cadastros.treinamentos_edit`, `cadastros.tripulantes_edit`, `cadastros.tripulantes_list`.
- `tripulantes_form.html`: `cadastros.tripulantes_list`.
- `tripulantes_list.html`: `cadastros.tripulantes_edit`, `cadastros.tripulantes_list`, `cadastros.tripulantes_new`.

## Mudancas materiais

- `backend/src/controle_treinamentos/templates/dashboard.html`: cards, alertas, filtros de status, lista completa e acao critica de treinamento usam hashes SPA canonicos.
- `backend/src/controle_treinamentos/blueprints/dashboard/routes.py`: `training_url` do calendario SSR usa `/#/treinamentos/<id>` em vez de `cadastros.treinamentos_edit`.
- `tests/architecture/test_ssr_template_canonical_link_guards.py`: guarda anti-regressao para templates, cards, atalhos e payload runtime do dashboard.

## Criterio de fechamento

Fechado quando o gate arquitetural passa e nenhum template publico SSR aponta para rota legada de superficie ja migrada sem excecao formal.


## 95.residual-training-workspace-cleanup.md

# 95. Residual training workspace cleanup

## Bloco executado

Limpeza governada de superficie residual fisica de frontend sem papel canonico atual.

## Residuos classificados

| item | classificacao anterior | classificacao final | prova material |
| --- | --- | --- | --- |
| `frontend/src/pages-treinamentos-relatorios.js` | fonte SPA viva | fonte canonica/wrapper vivo | carregado por `frontend/src/app/route-registry.js` como loader `treinamentos`. |
| `frontend/src/features/treinamentos/` | fonte SPA viva | owner canonico de treinamentos por tripulante | importado pelo wrapper vivo. |
| `frontend/src/features/training-root/` | fonte SPA viva | owner canonico de Treinamentos Raiz | importado pelo wrapper vivo. |
| `frontend/src/pages-training-workspace.js` | `candidata_remocao_futura` / `divida_residual_controlada` | artefato removivel removido | sem loader, sem rota, sem importador frontend e sem papel de compat formal. |
| `frontend/dist/` | artefato gerado local/publicavel | gerado novamente apos remocao da fonte residual | build canonico limpou a copia fingerprintada antiga. |
| `frontend/runtime/`, `frontend/frontend/runtime/`, `frontend/ops/artifacts/` | historico operacional gerado | fora do corte de fonte viva | nao define rota, loader ou superficie canonica. |

## Mudancas materiais

- Removido `frontend/src/pages-training-workspace.js`.
- Atualizado `tests/contract/test_frontend_page_module_boundaries.py` para impedir retorno do modulo residual como arquivo fisico nao roteado.
- Atualizado `tests/contract/test_frontend_readiness_consolidation.py` para exigir a ausencia fisica do residual e a classificacao `artefato_removido`.
- Atualizado `docs/architecture/FRONTEND_ARCHITECTURE.md` para substituir `candidata_remocao_futura` / `divida_residual_controlada` por `artefato_removido`.
- Atualizado `docs/architecture/ARCHITECTURE.md` para remover a promocao documental do residual como modulo ainda existente.

## Fronteira de runtime

O build canonico `frontend/scripts/build_frontend.py` reconstruiu `frontend/dist/` a partir de `frontend/src/`.
Como o arquivo removido nao existe mais em `frontend/src`, a saida atual nao deve conter `pages-training-workspace.*.js`.

Os diretorios historicos de runtime/artifacts nao foram limpos em lote porque sao evidencias operacionais geradas e nao fonte viva. Eles permanecem fora da topologia canonica, sem loader, rota ou importador.

## Criterio de fechamento

Fechado quando:

- `frontend/src/pages-training-workspace.js` nao existe;
- `route-registry.js` nao referencia `pages-training-workspace.js`;
- `frontend/dist/` reconstruido nao contem `pages-training-workspace.*.js`;
- testes de fronteira frontend passam.
