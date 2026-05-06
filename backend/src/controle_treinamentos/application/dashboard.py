from __future__ import annotations

from ..contracts.dashboard import (
    serialize_dashboard_calendar,
    serialize_dashboard_critical_trainings,
    serialize_dashboard_summary,
)
from ..repositories.dashboard_cache import (
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
