# Frontend/Backend Separation - Phase 4 (Treinamentos)

## Objective

Expose the `treinamentos` domain through explicit API contracts so a separate
frontend can handle list, filters, form options, create/update/delete flows, and
attachments without relying on Jinja-rendered training screens.

## New API endpoints

- `GET /api/v1/treinamentos`
- `GET /api/v1/treinamentos/options`
- `GET /api/v1/treinamentos/:id`
- `POST /api/v1/treinamentos`
- `PUT /api/v1/treinamentos/:id`
- `DELETE /api/v1/treinamentos/:id`
- `GET /api/v1/treinamentos/:id/attachments`
- `POST /api/v1/treinamentos/:id/attachments`
- `GET /api/v1/treinamentos/:id/attachments/:attachmentId`

## Architectural changes introduced

- New repository module:
  - [`backend/src/controle_treinamentos/repositories/treinamentos.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/repositories/treinamentos.py)
  - isolates filtering, counting, detail loading, attachment loading, and form options

- New contract module:
  - [`backend/src/controle_treinamentos/contracts/treinamentos.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/contracts/treinamentos.py)
  - defines collection/detail/options/attachment payloads

- New application use case module:
  - [`backend/src/controle_treinamentos/application/treinamentos.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/application/treinamentos.py)
  - centralizes training validation, due date resolution, persistence, delete flow,
    and attachment upload/read operations

- API endpoints integrated into:
  - [`backend/src/controle_treinamentos/blueprints/cadastros/routes_api.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/blueprints/cadastros/routes_api.py)

## Result of this phase

An external frontend can now:

- fetch the filtered training list
- fetch training form options
- fetch training detail
- create trainings
- update trainings
- delete trainings
- list attachments
- upload attachments
- open/download an attachment as binary

## Current legacy remainder

- `routes_treinamentos.py` still serves the server-rendered training pages
- `render_training_form(...)` and the Jinja training form still exist
- the old HTML flow still duplicates orchestration that now also exists in the application layer

## Why this phase is acceptable

The separation goal for Sprint 4 is met because the new frontend no longer
depends on Jinja to operate the training domain. The legacy HTML flow remains as
an old client until the next cleanup pass.

## Next recommended step

- adapt the old training HTML routes to reuse the new application layer
- then move to dashboards/relatórios for the next API-first extraction phase
