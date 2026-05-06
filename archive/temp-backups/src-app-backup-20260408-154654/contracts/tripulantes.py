from __future__ import annotations

from flask import url_for

from ..constants import (
    TRIPULANTE_CATEGORIA_OPTIONS,
    TRIPULANTE_FUNCAO_OPTIONS,
    TRIPULANTE_STATUS_OPTIONS,
)


def _tripulante_photo_url(row: dict) -> str | None:
    if not bool(row.get("possui_foto")):
        return None
    return url_for("cadastros.tripulante_foto", tripulante_id=int(row["id"]))


def _tripulante_links(row: dict) -> dict:
    tripulante_id = int(row["id"])
    return {
        "self": f"/api/v1/tripulantes/{tripulante_id}",
        "photo": _tripulante_photo_url(row),
        "files": f"/tripulantes/{tripulante_id}/file",
    }


def serialize_tripulante_summary(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "nome": row.get("nome") or "",
        "cpf": row.get("cpf") or "",
        "licenca_anac": row.get("licenca_anac") or "",
        "email": row.get("email") or "",
        "telefone": row.get("telefone") or "",
        "base": row.get("base") or "",
        "status": row.get("status") or "",
        "ativo": bool(row.get("ativo")),
        "funcao_operacional": row.get("funcao_operacional") or "",
        "categoria_operacional": row.get("categoria_operacional") or "",
        "sdea_ativo": bool(row.get("sdea_ativo")),
        "instrutor_ativo": bool(row.get("instrutor_ativo")),
        "checador_ativo": bool(row.get("checador_ativo")),
        "elegivel_adicional_excepcional": bool(row.get("elegivel_adicional_excepcional")),
        "possui_foto": bool(row.get("possui_foto")),
        "photo_url": _tripulante_photo_url(row),
        "links": _tripulante_links(row),
    }


def serialize_tripulante_detail(row: dict) -> dict:
    payload = serialize_tripulante_summary(row)
    payload.update(
        {
            "observacoes": row.get("observacoes") or "",
            "foto_storage_ref": row.get("foto_storage_ref") or "",
            "foto_mime_type": row.get("foto_mime_type") or "",
        }
    )
    return payload


def serialize_tripulante_collection(*, items: list[dict], page: int, per_page: int, total: int) -> dict:
    pages = max(1, ((int(total) - 1) // int(per_page)) + 1) if int(total) > 0 else 1
    return {
        "items": [serialize_tripulante_summary(item) for item in items],
        "pagination": {
            "page": int(page),
            "per_page": int(per_page),
            "total": int(total),
            "pages": int(pages),
            "has_prev": int(page) > 1,
            "has_next": int(page) < int(pages),
        },
    }


def serialize_tripulante_options(*, bases: list[dict]) -> dict:
    return {
        "bases": [
            {
                "nome": item.get("nome") or "",
                "uf": item.get("uf") or "",
            }
            for item in bases
        ],
        "status": list(TRIPULANTE_STATUS_OPTIONS),
        "funcoes": list(TRIPULANTE_FUNCAO_OPTIONS),
        "categorias": list(TRIPULANTE_CATEGORIA_OPTIONS),
    }
