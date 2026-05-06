from __future__ import annotations

from datetime import date, datetime

from flask import url_for

from ..constants import (
    TRIPULANTE_CATEGORIA_OPTIONS,
    TRIPULANTE_FUNCAO_OPTIONS,
    TRIPULANTE_STATUS_OPTIONS,
)
from ..application.tripulante_media import resolve_tripulante_photo_state
from ..core.legacy_blob_policy import LEGACY_PHOTO_BLOB_COMPAT_SOURCE, legacy_blob_policy_contract
from ..service_layers.tripulante_operational_status import (
    build_tripulante_operational_base_contract,
    build_tripulante_operational_status_contract,
)


def _tripulante_photo_state_hint(row: dict) -> dict | None:
    source_hint = (row.get("photo_source_hint") or "").strip()
    if not source_hint:
        return None
    if source_hint == "storage":
        return {
            "has_photo": True,
            "source": "storage",
            "mime_type": "",
            "storage_ref": "",
            "broken_reference": False,
            "compat_residual": False,
            "compat_source": "",
        }
    if source_hint == "base64":
        return {
            "has_photo": True,
            "source": "base64",
            "mime_type": "",
            "storage_ref": "",
            "broken_reference": False,
            "compat_residual": True,
            "compat_source": LEGACY_PHOTO_BLOB_COMPAT_SOURCE,
        }
    return {
        "has_photo": False,
        "source": "empty",
        "mime_type": "",
        "storage_ref": "",
        "broken_reference": False,
        "compat_residual": False,
        "compat_source": "",
    }


def _tripulante_photo_state(row: dict) -> dict:
    cached = row.get("_photo_state")
    if cached is None:
        cached = _tripulante_photo_state_hint(row)
        if cached is None:
            cached = resolve_tripulante_photo_state(row)
        row["_photo_state"] = cached
    return cached


def _tripulante_photo_url(row: dict) -> str | None:
    if not bool(_tripulante_photo_state(row).get("has_photo")):
        return None
    return url_for("cadastros.api_tripulante_photo_get", tripulante_id=int(row["id"]))


def _tripulante_links(row: dict) -> dict:
    tripulante_id = int(row["id"])
    return {
        "self": f"/api/v1/tripulantes/{tripulante_id}",
        "photo": _tripulante_photo_url(row),
        "files": f"/api/v1/tripulantes/{tripulante_id}/files",
        "files_api": f"/api/v1/tripulantes/{tripulante_id}/files",
        "files_legacy": f"/tripulantes/{tripulante_id}/file",
    }


def _date_text(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def serialize_tripulante_summary(row: dict) -> dict:
    photo_state = _tripulante_photo_state(row)
    base_payload = build_tripulante_operational_base_contract(row)
    status_payload = build_tripulante_operational_status_contract(row)
    return {
        "id": int(row["id"]),
        "nome": row.get("nome") or "",
        "cpf": row.get("cpf") or "",
        "licenca_anac": row.get("licenca_anac") or "",
        "email": row.get("email") or "",
        "telefone": row.get("telefone") or "",
        "base": base_payload["base"],
        "base_operacional": base_payload["base_operacional"],
        "base_operacional_id": base_payload["base_operacional_id"],
        "base_operacional_owner": base_payload["base_operacional_owner"],
        "base_snapshot_compat": base_payload["base_snapshot_compat"],
        "base_snapshot_compat_source": base_payload["base_snapshot_compat_source"],
        "status": status_payload["status"],
        "status_operacional": status_payload["status_operacional"],
        "status_operacional_owner": status_payload["status_operacional_owner"],
        "status_snapshot_compat": status_payload["status_snapshot_compat"],
        "status_snapshot_compat_source": status_payload["status_snapshot_compat_source"],
        "ativo": bool(row.get("ativo")),
        "funcao_operacional": row.get("funcao_operacional") or "",
        "categoria_operacional": row.get("categoria_operacional") or "",
        "sdea_ativo": bool(row.get("sdea_ativo")),
        "sdea_icao_validade": _date_text(row.get("sdea_icao_validade")),
        "instrutor_ativo": bool(row.get("instrutor_ativo")),
        "instrutor_inicio": _date_text(row.get("instrutor_inicio")),
        "instrutor_fim": _date_text(row.get("instrutor_fim")),
        "checador_ativo": bool(row.get("checador_ativo")),
        "checador_inicio": _date_text(row.get("checador_inicio")),
        "checador_fim": _date_text(row.get("checador_fim")),
        "checador_carta_designacao": row.get("checador_carta_designacao") or "",
        "elegivel_adicional_excepcional": bool(row.get("elegivel_adicional_excepcional")),
        "possui_foto": bool(photo_state.get("has_photo")),
        "photo_source": photo_state.get("source") or "",
        "photo_compat_residual": bool(photo_state.get("compat_residual")),
        "photo_compat_source": photo_state.get("compat_source") or "",
        "photo_policy": legacy_blob_policy_contract(
            "tripulante_photo",
            compat_residual=bool(photo_state.get("compat_residual")),
            compat_source=photo_state.get("compat_source") or "",
        ),
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
