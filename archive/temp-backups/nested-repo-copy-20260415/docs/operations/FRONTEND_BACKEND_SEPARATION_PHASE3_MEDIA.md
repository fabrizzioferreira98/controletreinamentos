# Frontend/Backend Separation - Phase 3 (Tripulante Media)

## Objective

Expose photos and File documents from the `tripulantes` domain through explicit
API contracts so a separate frontend can render photos, upload/remove photos,
list PDFs, upload PDFs, view PDFs, and remove PDFs without relying on the
server-rendered File tab.

## New API endpoints

- `GET /api/v1/tripulantes/:id/photo`
- `POST /api/v1/tripulantes/:id/photo`
- `DELETE /api/v1/tripulantes/:id/photo`
- `GET /api/v1/tripulantes/:id/files`
- `POST /api/v1/tripulantes/:id/files`
- `GET /api/v1/tripulantes/:id/files/:fileId`
- `DELETE /api/v1/tripulantes/:id/files/:fileId`

## Architectural changes introduced

- New application use case module:
  - [`backend/src/controle_treinamentos/application/tripulante_media.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/application/tripulante_media.py)
  - centralizes photo/file read-write operations, validation, storage, and audit

- New serializers:
  - [`backend/src/controle_treinamentos/contracts/tripulante_media.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/contracts/tripulante_media.py)

- New API routes integrated into:
  - [`backend/src/controle_treinamentos/blueprints/cadastros/routes_api.py`](/C:/apps/controle-treinamentos/backend/src/controle_treinamentos/blueprints/cadastros/routes_api.py)

## Compatibility notes

- Photo GET keeps compatibility with legacy `foto_base64` fallback if storage
  still points to older rows.
- File API focuses on the `tripulante_arquivos_pdf` source.
- The legacy HTML File tab and the legacy photo route continue to exist.

## Result of this phase

An external frontend can now:

- fetch tripulante photo as binary
- save tripulante photo with authenticated API call
- remove tripulante photo with authenticated API call
- list tripulante PDF documents
- upload tripulante PDF documents
- open/download tripulante PDF documents
- remove tripulante PDF documents

## What remains for the next step

- migrate the legacy HTML File tab to call the new application layer instead of
  holding duplicated orchestration in route handlers
- expose training attachments with explicit API contracts in the training domain
- connect the standalone frontend to these media endpoints
