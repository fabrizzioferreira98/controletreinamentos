from __future__ import annotations

from ..db import get_db
from ..repositories.catalogos import fetch_equipamento_options


def get_equipamentos_options_read_model(*, selected_equipment_id: int | None = None) -> list[dict]:
    db = get_db()
    return fetch_equipamento_options(db, selected_equipment_id=selected_equipment_id)
