from __future__ import annotations

from flask import url_for


def serialize_treinamento_summary(row: dict) -> dict:
    treinamento_id = int(row["id"])
    return {
        "id": treinamento_id,
        "tripulante_id": int(row["tripulante_id"]),
        "equipamento_id": row.get("equipamento_id"),
        "tipo_treinamento_id": int(row["tipo_treinamento_id"]),
        "tripulante_nome": row.get("tripulante_nome") or "",
        "equipamento_nome": row.get("equipamento_nome") or "",
        "tipo_treinamento_nome": row.get("tipo_treinamento_nome") or "",
        "data_realizacao": row.get("data_realizacao"),
        "data_vencimento": row.get("data_vencimento"),
        "observacao": row.get("observacao") or "",
        "status_calculado": row.get("status_calculado") or "",
        "links": {
            "self": f"/api/v1/treinamentos/{treinamento_id}",
            "attachments": f"/api/v1/treinamentos/{treinamento_id}/attachments",
        },
    }


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


def serialize_treinamento_attachment(row: dict) -> dict:
    treinamento_id = int(row["treinamento_id"])
    anexo_id = int(row["id"])
    return {
        "id": anexo_id,
        "treinamento_id": treinamento_id,
        "nome_original": row.get("nome_original") or "",
        "nome_interno": row.get("nome_interno") or "",
        "mime_type": row.get("mime_type") or "application/pdf",
        "tamanho_bytes": int(row.get("tamanho_bytes") or 0),
        "storage_ref": row.get("storage_ref") or "",
        "arquivo_hash": row.get("arquivo_hash") or "",
        "status": row.get("status") or "",
        "enviado_por": row.get("enviado_por"),
        "enviado_em": row.get("enviado_em"),
        "enviado_por_nome": row.get("enviado_por_nome") or "",
        "links": {
            "self": f"/api/v1/treinamentos/{treinamento_id}/attachments/{anexo_id}",
            "download": f"/api/v1/treinamentos/{treinamento_id}/attachments/{anexo_id}?download=1",
        },
    }
