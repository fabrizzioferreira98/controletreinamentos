from __future__ import annotations

from flask import url_for

from ..service_layers.tripulante_files import status_label


def serialize_tripulante_photo_state(*, tripulante_id: int, has_photo: bool) -> dict:
    return {
        "tripulante_id": int(tripulante_id),
        "has_photo": bool(has_photo),
        "photo_url": url_for("cadastros.api_tripulante_photo_get", tripulante_id=int(tripulante_id)) if has_photo else None,
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
        "arquivo_hash": row.get("arquivo_hash") or "",
        "status": row.get("status") or "",
        "status_label": status_label(row.get("status")),
        "enviado_por": row.get("enviado_por"),
        "enviado_em": row.get("enviado_em"),
        "substitui_arquivo_id": row.get("substitui_arquivo_id"),
        "removido_por": row.get("removido_por"),
        "removido_em": row.get("removido_em"),
        "motivo_status": row.get("motivo_status") or "",
        "links": {
            "self": f"/api/v1/tripulantes/{tripulante_id}/files/{arquivo_id}",
            "download": f"/api/v1/tripulantes/{tripulante_id}/files/{arquivo_id}?download=1",
        },
    }
