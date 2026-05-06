from __future__ import annotations

from datetime import date, datetime

from flask import url_for

from ..core.file_access_policy import (
    TRIPULANTE_FILE_ACCESS_POLICY,
    TRIPULANTE_PHOTO_ACCESS_POLICY,
    file_access_policy_contract,
)
from ..core.legacy_blob_policy import legacy_blob_policy_contract
from ..core.pdf_document_policy import TRIPULANTE_FILE_EVIDENCE_PDF_POLICY, pdf_document_policy_contract
from ..service_layers.tripulante_files import status_label


def _as_optional_int(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text)


def _as_iso_datetime_or_none(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def serialize_tripulante_photo_state(*, tripulante_id: int, has_photo: bool) -> dict:
    return {
        "tripulante_id": int(tripulante_id),
        "has_photo": bool(has_photo),
        "photo_url": url_for("cadastros.api_tripulante_photo_get", tripulante_id=int(tripulante_id)) if has_photo else None,
        "access_policy": file_access_policy_contract(TRIPULANTE_PHOTO_ACCESS_POLICY),
        "legacy_blob_policy": legacy_blob_policy_contract("tripulante_photo"),
    }


def serialize_tripulante_file_item(row: dict) -> dict:
    tripulante_id = int(row["tripulante_id"])
    arquivo_id = int(row["id"])
    return {
        "id": arquivo_id,
        "tripulante_id": tripulante_id,
        "tipo_documento": row.get("tipo_documento") or "",
        "nome_original": row.get("nome_original") or "",
        "nome_interno": row.get("nome_interno") or "",
        "mime_type": row.get("mime_type") or "application/pdf",
        "tamanho_bytes": int(row.get("tamanho_bytes") or 0),
        "storage_ref": row.get("storage_ref") or "",
        "blob_storage": row.get("blob_storage") or "",
        "blob_available": bool(row.get("blob_available")),
        "blob_status": row.get("blob_status") or "",
        "compat_residual": bool(row.get("compat_residual")),
        "compat_source": row.get("compat_source") or "",
        "blob_policy": legacy_blob_policy_contract(
            "tripulante_document",
            compat_residual=bool(row.get("compat_residual")),
            compat_source=row.get("compat_source") or "",
        ),
        "arquivo_hash": row.get("arquivo_hash") or "",
        "status": row.get("status") or "",
        "status_label": status_label(row.get("status")),
        "enviado_por": _as_optional_int(row.get("enviado_por")),
        "enviado_em": _as_iso_datetime_or_none(row.get("enviado_em")),
        "substitui_arquivo_id": _as_optional_int(row.get("substitui_arquivo_id")),
        "removido_por": _as_optional_int(row.get("removido_por")),
        "removido_em": _as_iso_datetime_or_none(row.get("removido_em")),
        "motivo_status": row.get("motivo_status") or "",
        "links": {
            "self": f"/api/v1/tripulantes/{tripulante_id}/files/{arquivo_id}",
            "preview": f"/api/v1/tripulantes/{tripulante_id}/files/{arquivo_id}",
            "download": f"/api/v1/tripulantes/{tripulante_id}/files/{arquivo_id}?download=1",
        },
        "access_policy": file_access_policy_contract(TRIPULANTE_FILE_ACCESS_POLICY),
        "document_policy": pdf_document_policy_contract(TRIPULANTE_FILE_EVIDENCE_PDF_POLICY),
    }
