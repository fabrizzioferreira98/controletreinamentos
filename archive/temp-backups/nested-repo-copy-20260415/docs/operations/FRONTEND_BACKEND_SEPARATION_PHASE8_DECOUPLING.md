# Frontend/Backend Separation - Phase 8 (Residual Coupling Removal)

Esta fase coloca as rotas HTML ja migradas em modo de compatibilidade com o frontend separado e reduz o papel visual do backend.

## O que mudou

- rotas HTML migradas passam a redirecionar para o frontend novo quando `FRONTEND_PUBLIC_ORIGIN` estiver configurado
- areas cobertas:
  - dashboard
  - tripulantes
  - treinamentos
  - relatorio de habilitacoes
  - relatorio de produtividade

## Legado/compatibilidade

- `GET` das telas migradas vira redirect para `#/...` no frontend novo
- `POST` legado ainda pode permanecer temporariamente para compatibilidade controlada
- exportacoes PDF/CSV continuam no backend

## Limpeza interna

- os renderizadores compartilhados de formulario deixaram de ser usados
- cada modulo legado agora mantem seu proprio render helper local
- o antigo `ui/form_renderers.py` foi neutralizado e ficou apenas como marcador de legado

## Aceite desta fase

- o backend nao renderiza mais as telas migradas quando o frontend separado esta habilitado
- o frontend novo vira ponto canonico de navegacao para essas areas
