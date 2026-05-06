from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.file_access_policy import resolve_file_access_action
from ..core.http_utils import safe_pdf_filename


def upload_treinamento_attachment_from_form(
    *,
    file_storage,
    treinamento_id: int,
    enviado_por: int,
    upload_attachment_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "filename": getattr(file_storage, "filename", "") if file_storage is not None else "",
        "arquivo_bytes": file_storage.read() if file_storage is not None else b"",
        "content_type": getattr(file_storage, "content_type", "") if file_storage is not None else "",
    }
    result = upload_attachment_fn(payload, treinamento_id=treinamento_id, enviado_por=enviado_por)
    return {
        "payload": payload,
        "result": result,
    }


def get_treinamento_attachment_response_model(
    *,
    treinamento_id: int,
    anexo_id: int,
    query_args,
    get_attachment_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    row = get_attachment_fn(treinamento_id=treinamento_id, anexo_id=anexo_id)
    safe_name = safe_pdf_filename(row.get("nome_original"), fallback=f"treinamento_{treinamento_id}_anexo.pdf")
    action = resolve_file_access_action(query_args)
    return {
        "row": row,
        "safe_name": safe_name,
        "action": action,
        "mime_type": row.get("mime_type") or "application/pdf",
        "payload_bytes": row["payload_bytes"],
    }


def delete_treinamento_attachment_from_form(
    *,
    treinamento_id: int,
    anexo_id: int,
    delete_attachment_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return delete_attachment_fn(treinamento_id=treinamento_id, anexo_id=anexo_id)
