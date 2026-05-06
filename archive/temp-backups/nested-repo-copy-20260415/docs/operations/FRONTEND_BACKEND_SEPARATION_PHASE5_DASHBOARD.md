# Frontend/Backend Separation - Phase 5 (Dashboard and TV Panels)

Esta fase extrai os contratos de dashboard e painéis para endpoints programáticos sob `/api/v1`, sem depender de template Jinja nem de `url_for` no payload.

## Endpoints entregues

- `GET /api/v1/dashboard/summary`
- `GET /api/v1/dashboard/calendar`
- `GET /api/v1/dashboard/critical-trainings`
- `GET /api/v1/tv/vencimentos`
- `GET /api/v1/tv/produtividade`

## Fronteira nova

- As rotas HTML legadas continuam em produção para compatibilidade.
- Os novos contratos devolvem apenas dados consumíveis pelo frontend desacoplado.
- O cache da API é separado do cache de HTML para evitar vazamento de campos como `training_url` e `tripulante_url`.

## Regras desta fase

- `dashboard.summary` não expõe estrutura de tela.
- `dashboard.calendar` não expõe links de navegação nem classes CSS.
- `dashboard.critical-trainings` devolve somente dados de negócio relevantes ao frontend.
- `tv.vencimentos` e `tv.produtividade` passam a ter contratos explícitos para o app frontend.

## Aceite técnico

- O frontend novo consegue montar dashboard e painéis sem `render_template`.
- O payload não depende de `url_for`.
- As permissões seguem separadas por capacidade:
  - `dashboard:view`
  - `tv_vencimentos:view`
  - `tv_produtividade:view`
