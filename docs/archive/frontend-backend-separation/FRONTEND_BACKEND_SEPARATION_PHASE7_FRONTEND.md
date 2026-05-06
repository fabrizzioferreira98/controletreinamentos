# Frontend/Backend Separation - Phase 7 (Separated Frontend in Production)

Esta fase sobe um frontend separado do backend com contratos `/api/v1`, autenticacao por cookie de sessao e protecao CSRF.

## Entregaveis

- `frontend/` independente do backend
- build estatico proprio via Python
- configuracao de ambiente para `API_BASE_URL` e `FRONTEND_PUBLIC_ORIGIN`
- CORS com credenciais para rotas `/api/*`
- headers observaveis com `X-Request-ID`

## Estrutura

- `frontend/src/`
- `frontend/dist/`
- `frontend/scripts/build_frontend.py`

## Backend

Variaveis novas recomendadas:

- `FRONTEND_PUBLIC_ORIGIN`
- `FRONTEND_ALLOWED_ORIGINS`
- `COOKIE_DOMAIN`
- `SESSION_COOKIE_SAMESITE=None` para cenario cross-origin real

## Frontend

Rotas entregues no app separado:

- `#/dashboard`
- `#/tripulantes`
- `#/tripulantes/new`
- `#/tripulantes/:id`
- `#/treinamentos`
- `#/treinamentos/new`
- `#/treinamentos/:id`
- `#/relatorios/habilitacoes`
- `#/relatorios/produtividade`

## Deploy sugerido

1. Gerar build do frontend:
   - `.venv\Scripts\python.exe frontend\scripts\build_frontend.py --env-file frontend\.env.example`
2. Publicar `frontend/dist/` em host estatico ou Caddy/Nginx
3. Publicar backend Flask/Waitress separadamente
4. Configurar `FRONTEND_ALLOWED_ORIGINS` no backend
5. Validar login, logout, leitura e escrita nos modulos migrados

## Observabilidade

- API expõe `X-Request-ID`
- frontend propaga mensagens com codigo de rastreio quando a API falha
- logs continuam concentrados no backend

## Limitacoes desta fase

- o frontend foi implementado sem toolchain Node nesta maquina
- o build estatico e simples, sem bundler
- a observabilidade de browser e basica
