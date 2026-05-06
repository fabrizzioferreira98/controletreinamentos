from __future__ import annotations

from datetime import date, datetime

from flask import url_for

from ..core.file_access_policy import TRAINING_ATTACHMENT_ACCESS_POLICY, file_access_policy_contract
from ..core.legacy_blob_policy import legacy_blob_policy_contract
from ..core.pdf_document_policy import TRAINING_ATTACHMENT_EVIDENCE_PDF_POLICY, pdf_document_policy_contract
from ..service_layers.training_completeness import TRAINING_COMPLETENESS_MODE_FIELD, resolve_training_structural_mode
from ..training_aircraft_model import (
    build_training_aircraft_snapshot_contract,
    is_training_program_record,
    resolve_training_record_origin,
)


def _as_optional_int(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text)


def _as_iso_date_or_none(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _as_iso_datetime_or_none(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def serialize_treinamento_summary(row: dict) -> dict:
    treinamento_id = int(row["id"])
    payload = {
        "id": treinamento_id,
        "origem_registro": resolve_training_record_origin(row),
        TRAINING_COMPLETENESS_MODE_FIELD: resolve_training_structural_mode(row),
        "tripulante_id": int(row["tripulante_id"]),
        "equipamento_id": row.get("equipamento_id"),
        "tipo_treinamento_id": int(row["tipo_treinamento_id"]),
        "tripulante_nome": row.get("tripulante_nome") or "",
        "equipamento_nome": row.get("equipamento_nome") or "",
        "tipo_treinamento_nome": row.get("tipo_treinamento_nome") or "",
        "data_realizacao": _as_iso_date_or_none(row.get("data_realizacao")),
        "data_vencimento": _as_iso_date_or_none(row.get("data_vencimento")),
        "observacao": row.get("observacao") or "",
        "status_calculado": row.get("status_calculado") or "",
        "links": {
            "self": f"/api/v1/treinamentos/{treinamento_id}",
            "attachments": f"/api/v1/treinamentos/{treinamento_id}/attachments",
        },
    }
    if is_training_program_record(row):
        payload.update(build_training_aircraft_snapshot_contract(row))
        if row.get("segmento_teorico_id") is not None:
            payload["segmento_teorico_id"] = int(row["segmento_teorico_id"])
    return payload


def serialize_treinamento_detail(row: dict, *, attachments: list[dict] | None = None) -> dict:
    payload = serialize_treinamento_summary(row)
    if attachments is not None:
        payload["attachments"] = [serialize_treinamento_attachment(item) for item in attachments]
    return payload


def serialize_treinamento_collection(*, items: list[dict], page: int, per_page: int, total: int, resumo: dict) -> dict:
    pages = max(1, ((int(total) - 1) // int(per_page)) + 1) if int(total) > 0 else 1
    return {
        "items": [serialize_treinamento_summary(item) for item in items],
        "pagination": {
            "page": int(page),
            "per_page": int(per_page),
            "total": int(total),
            "pages": int(pages),
            "has_prev": int(page) > 1,
            "has_next": int(page) < int(pages),
        },
        "summary": {
            "total": int(resumo.get("total") or 0),
            "vencido": int(resumo.get("vencido") or 0),
            "a_vencer": int(resumo.get("a_vencer") or 0),
            "regular": int(resumo.get("regular") or 0),
            "sem_informacao": int(resumo.get("sem_informacao") or 0),
        },
    }


def serialize_treinamento_options(options: dict) -> dict:
    return {
        "tripulantes": options.get("tripulantes", []),
        "equipamentos": options.get("equipamentos", []),
        "tipos": options.get("tipos", []),
        "attachments": [serialize_treinamento_attachment(item) for item in options.get("attachments", [])],
    }


def serialize_treinamento_attachment(row: dict, *, links_base_path: str | None = None) -> dict:
    treinamento_id = int(row["treinamento_id"])
    anexo_id = int(row["id"])
    attachment_base_path = links_base_path or f"/api/v1/treinamentos/{treinamento_id}/attachments"
    return {
        "id": anexo_id,
        "treinamento_id": treinamento_id,
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
            "training_attachment",
            compat_residual=bool(row.get("compat_residual")),
            compat_source=row.get("compat_source") or "",
        ),
        "arquivo_hash": row.get("arquivo_hash") or "",
        "status": row.get("status") or "",
        "enviado_por": _as_optional_int(row.get("enviado_por")),
        "enviado_em": _as_iso_datetime_or_none(row.get("enviado_em")),
        "removido_por": _as_optional_int(row.get("removido_por")),
        "removido_em": _as_iso_datetime_or_none(row.get("removido_em")),
        "motivo_status": row.get("motivo_status") or "",
        "enviado_por_nome": row.get("enviado_por_nome") or "",
        "links": {
            "self": f"{attachment_base_path}/{anexo_id}",
            "preview": f"{attachment_base_path}/{anexo_id}",
            "download": f"{attachment_base_path}/{anexo_id}?download=1",
        },
        "access_policy": file_access_policy_contract(TRAINING_ATTACHMENT_ACCESS_POLICY),
        "document_policy": pdf_document_policy_contract(TRAINING_ATTACHMENT_EVIDENCE_PDF_POLICY),
    }
