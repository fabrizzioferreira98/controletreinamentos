from __future__ import annotations

from typing import Any

from ..db import get_db
from ..repositories.queries import fetch_training_page
from ..repositories.treinamentos import (
    build_training_filters,
    count_treinamentos,
    fetch_training_options,
    fetch_treinamento_detail,
)
from .treinamentos import list_treinamento_attachments


def list_treinamentos_read_model(*, filters: dict, page: int, per_page: int) -> dict[str, Any]:
    db = get_db()
    resumo = count_treinamentos(db, **filters)
    where_clause, params = build_training_filters(**filters)
    items = fetch_training_page(
        db,
        where_clause,
        params,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": int(resumo["total"] or 0),
        "resumo": resumo,
    }


def get_treinamentos_options_read_model(
    *,
    treinamento_id: int | None,
    selected_equipment_id: int | None,
    selected_tipo_id: int | None,
) -> Any:
    db = get_db()
    return fetch_training_options(
        db,
        treinamento_id=treinamento_id,
        selected_equipment_id=selected_equipment_id,
        selected_tipo_id=selected_tipo_id,
    )


def get_treinamento_detail_read_model(*, treinamento_id: int):
    db = get_db()
    row = fetch_treinamento_detail(db, treinamento_id=treinamento_id)
    if not row:
        return None, []
    attachments = list_treinamento_attachments(treinamento_id=treinamento_id)
    return row, attachments
