from __future__ import annotations

from flask import current_app, has_app_context

from ..core.document_storage import FILESYSTEM_STORAGE_PREFIX, document_blob_state, storage_reference_kind
from .media_storage import iter_local_media_refs, media_ref_exists, read_media_bytes


def _is_document_media_ref(storage_ref: str | None) -> bool:
    raw = str(storage_ref or "").strip()
    if not raw.startswith(FILESYSTEM_STORAGE_PREFIX):
        return False
    return "/documentos/" in raw or "/anexos/" in raw


def annotate_document_blob_state(row: dict) -> dict:
    item = dict(row)
    filesystem_exists = None
    if storage_reference_kind(item.get("storage_ref")) == "filesystem":
        try:
            filesystem_exists = media_ref_exists(item.get("storage_ref"))
        except ValueError:
            filesystem_exists = False
    item.update(document_blob_state(item, filesystem_exists=filesystem_exists))
    return item


def _log_legacy_document_read(row: dict) -> None:
    if not has_app_context():
        return
    current_app.logger.warning(
        "Compat residual documental lida via db:bytea. origem=%s origem_id=%s storage_ref=%s",
        row.get("origem") or row.get("source_table") or "",
        row.get("origem_id") or row.get("id") or "",
        row.get("storage_ref") or "",
    )


def read_document_blob(row: dict) -> bytes | None:
    reference_kind = storage_reference_kind(row.get("storage_ref"))
    if reference_kind == "filesystem":
        try:
            return read_media_bytes(row.get("storage_ref"), fallback_bytes=None)
        except ValueError:
            return None
    if reference_kind == "database":
        payload = bytes(row["arquivo_pdf"]) if row.get("arquivo_pdf") is not None else None
        if payload:
            _log_legacy_document_read(row)
        return payload
    return None


def find_orphan_media_refs(
    referenced_storage_refs: list[str] | tuple[str, ...] | set[str],
    *,
    local_storage_refs: list[str] | tuple[str, ...] | set[str] | None = None,
) -> list[str]:
    local_refs = {
        ref
        for ref in (local_storage_refs if local_storage_refs is not None else iter_local_media_refs())
        if _is_document_media_ref(ref)
    }
    referenced_refs = {
        str(item or "").strip()
        for item in referenced_storage_refs
        if _is_document_media_ref(item)
    }
    return sorted(local_refs - referenced_refs)


def classify_document_inventory(
    metadata_rows: list[dict] | tuple[dict, ...],
    *,
    local_storage_refs: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict:
    annotated = [annotate_document_blob_state(row) for row in metadata_rows]
    referenced_refs = [str(row.get("storage_ref") or "").strip() for row in metadata_rows]
    return {
        "consistent": [row for row in annotated if row.get("consistency_status") in {"consistent", "consistent_legacy"}],
        "metadata_without_blob": [row for row in annotated if row.get("consistency_status") == "metadata_without_blob"],
        "metadata_without_reference": [
            row for row in annotated if row.get("consistency_status") == "metadata_without_reference"
        ],
        "remote_reference_unverified": [
            row for row in annotated if row.get("consistency_status") == "remote_reference_unverified"
        ],
        "unsupported_reference": [
            row for row in annotated if row.get("consistency_status") == "metadata_with_unsupported_reference"
        ],
        "orphan_blobs": find_orphan_media_refs(referenced_refs, local_storage_refs=local_storage_refs),
    }


def summarize_document_inventory(
    metadata_rows: list[dict] | tuple[dict, ...],
    *,
    local_storage_refs: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict:
    inventory = classify_document_inventory(metadata_rows, local_storage_refs=local_storage_refs)
    counts = {
        "consistent": len(inventory["consistent"]),
        "metadata_without_blob": len(inventory["metadata_without_blob"]),
        "metadata_without_reference": len(inventory["metadata_without_reference"]),
        "remote_reference_unverified": len(inventory["remote_reference_unverified"]),
        "unsupported_reference": len(inventory["unsupported_reference"]),
        "orphan_blobs": len(inventory["orphan_blobs"]),
    }
    critical_count = (
        counts["metadata_without_blob"]
        + counts["metadata_without_reference"]
        + counts["unsupported_reference"]
    )
    warning_count = counts["remote_reference_unverified"] + counts["orphan_blobs"]
    if critical_count:
        status_key = "degraded"
    elif warning_count:
        status_key = "attention"
    else:
        status_key = "operational"
    return {
        "inventory": inventory,
        "counts": counts,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "problem_count": critical_count + warning_count,
        "status_key": status_key,
    }
