# Frontend/Backend Separation - Phase 2 (Tripulantes)

## Objective

Expose the `tripulantes` domain through explicit API contracts so an external
frontend can list, read, create, update, and delete tripulantes without relying
on server-rendered templates.

## New API endpoints

- `GET /api/v1/tripulantes`
- `GET /api/v1/tripulantes/:id`
- `POST /api/v1/tripulantes`
- `PUT /api/v1/tripulantes/:id`
- `DELETE /api/v1/tripulantes/:id`

## Architectural changes introduced

- New application use case:
  - [`backend/src/controle_treinamentos/application/tripulantes.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/application/tripulantes.py)
  - centralizes validation, persistence, photo handling, audit, pilot sync, and
    transactional write flow for create/update/delete

- New repository module:
  - [`backend/src/controle_treinamentos/repositories/tripulantes.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/repositories/tripulantes.py)
  - isolates list/detail/filter/dependency queries for the API contract

- New DTO/serializer module:
  - [`backend/src/controle_treinamentos/contracts/tripulantes.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/contracts/tripulantes.py)
  - defines stable response shape for collection and detail payloads

- New API route module:
  - [`backend/src/controle_treinamentos/blueprints/cadastros/routes_api.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/blueprints/cadastros/routes_api.py)

## Current status

The external frontend can now:

- authenticate via session API
- fetch tripulante collection data
- fetch tripulante detail data
- create tripulantes via JSON
- update tripulantes via JSON
- delete or inactivate tripulantes via JSON

## What still remains legacy

- The existing HTML routes in `cadastros/routes.py` still contain duplicated write logic.
- The current Jinja forms remain active for the legacy UI.
- Frontend form option catalogs still come from server-rendered screens in other domains.

## Why this is acceptable in this phase

Sprint 2 focuses on making the `tripulantes` domain usable without template
rendering. That goal is achieved even though the old HTML flow still exists as a
legacy client.

## Next recommended step

Refactor the legacy HTML `tripulantes_new` and `tripulantes_edit` routes to call
the new application use case, so the domain stops having duplicated write logic.

After that, proceed with `files` extraction for the tripulante area.
