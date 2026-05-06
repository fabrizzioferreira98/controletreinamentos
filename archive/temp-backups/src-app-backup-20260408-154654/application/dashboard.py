from __future__ import annotations

from datetime import datetime

from ..contracts.dashboard import (
    serialize_dashboard_calendar,
    serialize_dashboard_critical_trainings,
    serialize_dashboard_summary,
    serialize_tv_produtividade_payload,
    serialize_tv_vencimentos_payload,
)
from ..produtividade import calculate_competencia_consolidada, parse_competencia
from ..repositories.dashboard_cache import (
    _build_panel_tv_payload,
    _fetch_dashboard_critical_rows,
    build_dashboard_context,
    get_panel_cache,
    set_panel_cache,
)


def get_dashboard_summary_data(db) -> dict:
    cache_key = "api:dashboard:summary"
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return cached
    payload = serialize_dashboard_summary(build_dashboard_context(db))
    set_panel_cache(cache_key, payload)
    return payload


def get_dashboard_calendar_data(db) -> dict:
    cache_key = "api:dashboard:calendar"
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return cached
    payload = serialize_dashboard_calendar(build_dashboard_context(db))
    set_panel_cache(cache_key, payload)
    return payload


def get_dashboard_critical_trainings_data(db, *, limit: int = 8) -> dict:
    cache_key = f"api:dashboard:critical:{int(limit)}"
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return cached
    payload = serialize_dashboard_critical_trainings(_fetch_dashboard_critical_rows(db, limit=limit))
    set_panel_cache(cache_key, payload)
    return payload


def get_tv_vencimentos_data(db, *, base_filter: str = "") -> dict:
    cache_key = f"api:tv:vencimentos:{(base_filter or '').strip().lower()}"
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return cached
    payload = serialize_tv_vencimentos_payload(_build_panel_tv_payload(db, base_filter=base_filter))
    set_panel_cache(cache_key, payload)
    return payload


def get_tv_produtividade_data(db, *, competencia: str = "") -> dict:
    normalized_competencia = parse_competencia(competencia)
    cache_key = f"api:tv:produtividade:{normalized_competencia}"
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return cached
    context = calculate_competencia_consolidada(db, competencia=normalized_competencia)
    rows = [
        {
            "tripulante_id": row["tripulante_id"],
            "tripulante_nome": row["tripulante_nome"],
            "base": row["base"],
            "categoria": row["categoria"],
            "funcao": row["funcao"],
            "total_missoes_validas": row["total_missoes_validas"],
            "total_pernoites": row["total_pernoites_cobertura"] + row["total_pernoites_operacionais_elegiveis"],
            "total_produtividade": row["total_produtividade"],
            "valor_final_mes": row["valor_final_mes"],
            "criterio_fechamento": row["criterio_fechamento"],
        }
        for row in context["rows"]
    ]
    payload = serialize_tv_produtividade_payload(
        competencia=context["competencia"],
        summary=context["summary"],
        rows=rows,
        updated_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    )
    set_panel_cache(cache_key, payload)
    return payload
