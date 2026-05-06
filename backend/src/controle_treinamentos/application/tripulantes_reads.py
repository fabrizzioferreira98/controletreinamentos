from __future__ import annotations

from typing import Any

from ..db import get_db
from ..repositories.queries import fetch_base_options
from ..repositories.tripulantes import count_tripulantes, fetch_tripulante_detail, fetch_tripulante_list_page


def list_tripulantes_read_model(*, filters: dict, page: int, per_page: int) -> dict[str, Any]:
    db = get_db()
    total = count_tripulantes(db, **filters)
    offset = (page - 1) * per_page
    rows = fetch_tripulante_list_page(db, **filters, limit=per_page, offset=offset)
    return {
        "items": rows,
        "page": page,
        "per_page": per_page,
        "total": total,
    }


def get_tripulantes_options_read_model(*, base: str | None) -> dict[str, Any]:
    db = get_db()
    return {
        "bases": fetch_base_options(db, base),
    }


def get_tripulante_detail_read_model(*, tripulante_id: int):
    db = get_db()
    return fetch_tripulante_detail(db, tripulante_id=tripulante_id)
