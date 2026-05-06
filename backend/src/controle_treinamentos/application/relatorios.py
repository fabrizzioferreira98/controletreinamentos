from __future__ import annotations

from datetime import datetime

from ..contracts.relatorios import serialize_habilitacoes_report
from ..repositories.dashboard_cache import (
    build_habilitacoes_consolidadas_context,
    get_panel_cache,
    set_panel_cache,
)


def get_habilitacoes_report_data(
    db,
    *,
    nome: str = "",
    base: str = "",
    status: str = "",
    tipo: str = "",
    ordenacao: str = "",
) -> dict:
    cache_key = (
        f"api:relatorios:habilitacoes:{nome.lower()}:{base.lower()}:"
        f"{status.lower()}:{tipo.lower()}:{ordenacao.lower()}"
    )
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return cached
    payload = serialize_habilitacoes_report(
        build_habilitacoes_consolidadas_context(
            db,
            nome=nome,
            base=base,
            status=status,
            tipo=tipo,
            ordenacao=ordenacao,
        )
    )
    payload["emitted_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    set_panel_cache(cache_key, payload)
    return payload
