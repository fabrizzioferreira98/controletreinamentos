# Shared UI foundation

Esta pasta e a fundacao visual minima do frontend apos G01. Ela nao e um design system completo e nao deve virar biblioteca ornamental.

## Owners

- `tokens.css`: tokens semanticos compartilhados para cor, tipografia, spacing, radius, shadow, camadas e estados.
- `primitives.css`: primitives pequenas de composicao visual que nao conhecem dominio, API, shell, router ou feature.
- Primitives estruturais como `ui-app-frame`, `ui-inverse-surface`, `ui-sticky-surface`, `ui-content-region` e `ui-navigation-list` podem ser usadas no shell/layout sem assumir regra de dominio.
- Primitives de pagina como `ui-page-shell` e `ui-page-header` podem ser usadas apenas quando o padrao ja aparece em mais de uma superficie real e nao carrega regra de dominio.
- Primitives de familia como `ui-card-grid`, `ui-card-grid-compact`, `ui-card-grid-wide`, `ui-card-equal-height`, `ui-card`, `ui-card-compact`, `ui-card-inset`, `ui-card-metric`, `ui-card-actions`, `ui-state`, `ui-state-inline`, `ui-state-actions`, `ui-alert`, `ui-master-detail`, `ui-master-pane`, `ui-detail-pane`, `ui-detail-back`, `ui-detail-actions`, `ui-overlay-root`, `ui-overlay-backdrop`, `ui-overlay-panel`, `ui-modal`, `ui-drawer`, `ui-side-panel`, `ui-overlay-header`, `ui-overlay-body`, `ui-overlay-actions`, `ui-overlay-close`, `ui-table-wrap`, `ui-table-scroll-controlled`, `ui-table-density-compact`, `ui-table-density-comfortable`, `ui-table-actions`, `ui-table-state`, `ui-table-row-detail`, `ui-table-expand-toggle`, `ui-form-toolbar`, `ui-form-section`, `ui-form-grid`, `ui-form-density-compact`, `ui-form-actions`, `ui-form-sticky-actions`, `ui-form-upload-grid`, `ui-form-upload-field`, `ui-form-upload-state`, `ui-form-field-long`, `ui-filter-bar`, `ui-filter-row`, `ui-filter-actions`, `ui-filter-summary`, `ui-filter-chip`, `ui-filter-panel`, `ui-filter-advanced`, `ui-filter-drawer` e `ui-field-help` podem ser usadas em cards/grids/overlays/tabelas/formularios/filtros/master-detail/estados densos sem criar componente de produto.
- Cards e grids responsivos oficiais usam `ui-card-grid` para colapso fluido, `ui-card-equal-height` quando a comparacao entre cards importa, `ui-card-compact` para faixas menores, `ui-card-inset` para cards internos sem aparencia de card aninhado pesado e `ui-card-actions` para CTAs que empilham corretamente.
- Modais, drawers e overlays responsivos oficiais usam `ui-overlay-root`, `ui-overlay-backdrop`, `ui-modal`, `ui-drawer`, `ui-side-panel`, `ui-overlay-body` e `ui-overlay-actions`; comportamento de foco, Escape, retorno de foco e scroll lock deve passar pelos helpers compartilhados de `lib.js`.
- Master-detail responsivo oficial usa `ui-master-detail`, `ui-master-pane`, `ui-detail-pane`, `ui-detail-back` e `ui-detail-actions`; comportamento de lista para detalhe, retorno, foco, scroll e persistencia de contexto deve passar por `wireResponsiveMasterDetail` em `lib.js`.
- Estados responsivos oficiais usam `ui-state` para loading, empty, error, no permission e no-results; `ui-alert` cobre banners informacionais, warnings e erros inline. Markup transversal deve preferir `responsiveStateMarkup`, `responsiveStateContentMarkup` e `responsiveAlertMarkup` em `lib.js`.
- Tabelas responsivas oficiais usam `responsive-cards` com `data-label`, prioridade `data-responsive-priority`, densidade `data-responsive-density` e overflow controlado no wrapper quando a leitura tabular precisa ser preservada.
- Formularios responsivos oficiais usam `ui-form-grid` com colunas fluidas, `ui-form-section` para grupos, `ui-form-sticky-actions` para acoes persistentes em viewport menor, `ui-form-upload-grid` para upload, `ui-form-field-long` para textos longos e `ui-field-help` para ajuda/validacao acessivel.
- Filtros responsivos oficiais usam `ui-filter-bar` para a barra, `ui-filter-row` para controles primarios, `ui-filter-actions` para aplicar/limpar/alternar, `ui-filter-panel` e `ui-filter-advanced` para filtros avancados, `ui-filter-drawer` para painel denso em viewport menor e `ui-filter-summary`/`ui-filter-chip` para persistencia visual local.

## Regra de adocao

- Nova UI deve preferir tokens de `shared/ui` antes de valor solto.
- Paginas existentes adotam primitives apenas quando isso reduz inline style, repeticao ou ambiguidade de composicao.
- promocao para shared/ui exige reutilizacao material em pelo menos duas superficies reais, sem regra de dominio e sem contrato especifico demais.
- Tokens precisam representar semantica reutilizavel, nao nome de tela, modulo ou gosto visual.
- `shared/ui` nao registra rota, nao chama API, nao renderiza DOM por JavaScript e nao importa features.
