from __future__ import annotations

from datetime import date, datetime


def _parse_date_like(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def register_template_filters(app):
    @app.template_filter("br_date")
    def br_date(value, fallback="-"):
        parsed = _parse_date_like(value)
        if parsed is None:
            return fallback
        return parsed.strftime("%d/%m/%Y")

    @app.template_filter("br_datetime")
    def br_datetime(value, fallback="-"):
        parsed = _parse_date_like(value)
        if parsed is None:
            return fallback
        return parsed.strftime("%d/%m/%Y %H:%M")

    @app.template_filter("br_month")
    def br_month(value, fallback="-"):
        raw = (str(value or "")).strip()
        if not raw:
            return fallback
        try:
            parsed = datetime.strptime(raw, "%Y-%m")
        except ValueError:
            return raw
        return parsed.strftime("%m/%Y")
