# Frontend/Backend Separation - Phase 1

## Objective

Open an explicit API boundary for authentication/session state without breaking the
existing server-rendered product.

This phase does **not** remove Jinja, templates, or the current login screen.
It introduces a stable session contract that a future standalone frontend can use
without depending on HTML parsing or implicit redirects.

## New API endpoints

All endpoints below reuse the current cookie session and Flask-Login integration.

- `GET /api/v1/session`
  - returns current authentication state
  - returns a CSRF token for subsequent mutating API calls
  - returns the authenticated user and grouped capabilities when a session exists

- `POST /api/v1/session/login`
  - accepts JSON payload with `login`, `senha`, and optional `remember`
  - reuses the same authentication flow and rate limiting as `/login`
  - returns authenticated user + capabilities on success

- `POST /api/v1/session/logout`
  - terminates the current session
  - preserves remember-cookie clearing behavior

- `GET /api/v1/me`
  - returns the authenticated user identity

- `GET /api/v1/capabilities`
  - returns grouped permissions for frontend composition

## What remains legacy in this phase

- `GET /login` and `POST /login`
- Jinja templates and `render_template(...)`
- `flash(...)` based HTML feedback
- redirect-oriented navigation for the current UI

## Why this phase matters

This is the minimum viable boundary for a truly separated frontend:

- the frontend can discover whether the user is authenticated
- the frontend can obtain CSRF safely
- the frontend can login/logout without HTML coupling
- the frontend can build navigation and route guards from capabilities

## Guardrails

- Session/cookie behavior remains unchanged
- Existing HTML login/logout behavior remains supported
- Existing programmatic error contract remains unchanged
- Contract tests cover the new API routes

## Next extraction steps

1. Extract `tripulantes` list/detail/create/update endpoints under `/api/v1/tripulantes`
2. Extract photo/document contracts under `/api/v1/tripulantes/:id/photo` and `/api/v1/tripulantes/:id/files`
3. Move form/list rendering concerns out of backend routes
4. Introduce the separate frontend app after auth + first business domain are stable
