# Classic file risk policy

This note records the residual risks that must stay visible in storage, files,
and generated PDFs.

| Risk | Where it appears | Severity | Mitigation |
| --- | --- | --- | --- |
| Improvised path | Any `fs:` reference that does not match the domain path policy exactly. | High | New policy matching rejects traversal, Windows separators, nested files under a file slot, and wrong domain prefixes. |
| File accessible without permission | Preview and download routes for photos, tripulante files, and training attachments. | High | Responses go through `build_file_access_response`, which checks the action-specific permission before streaming. |
| Orphan blob | Local file under media storage with no metadata reference. | Medium | Inventory summary counts orphan blobs and monitoring raises a document-storage warning. |
| Inconsistent metadata/blob | Metadata row whose local or legacy blob cannot be read. | High | Blob state classification marks `metadata_without_blob`, `metadata_without_reference`, and unsupported references explicitly. |
| PDF without visual contract | Generated PDFs without the official template/layout keys. | High | Generated PDF responses validate the official ReportLab template/layout policy before serving. |
| Broken PDF in production | Generated PDF payload with header but incomplete body. | High | Generated PDF responses now require a PDF EOF marker before serving. |

Compatibility rule: legacy readable `fs:` references remain readable through the
media root guard, but new policy-constrained references must match the canonical
domain path exactly.

