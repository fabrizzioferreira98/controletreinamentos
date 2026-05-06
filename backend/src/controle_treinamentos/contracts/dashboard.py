from __future__ import annotations

from datetime import date, datetime


def _as_iso_date_or_none(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _as_int(value) -> int:
    return int(value or 0)


def _serialize_calendar_item(item: dict) -> dict:
    return {
        "id": int(item["training_id"]),
        "tripulante_id": int(item["tripulante_id"]),
        "tripulante_nome": item.get("tripulante_nome") or "",
        "equipamento_nome": item.get("equipamento_nome") or "",
        "tipo_treinamento_nome": item.get("tipo_treinamento_nome") or "",
        "data_vencimento": item.get("data_vencimento") or "",
        "status": item.get("status") or "",
    }


def serialize_dashboard_summary(context: dict) -> dict:
    totals = context.get("totals", {})
    summary = context.get("summary", {})
    alerts = context.get("alerts", {})
    return {
        "totals": {
            "tripulantes": _as_int(totals.get("tripulantes")),
            "equipamentos": _as_int(totals.get("equipamentos")),
            "tipos": _as_int(totals.get("tipos")),
            "treinamentos": _as_int(totals.get("treinamentos")),
        },
        "summary": {
            "total": _as_int(summary.get("total")),
            "vencido": _as_int(summary.get("vencido")),
            "a_vencer": _as_int(summary.get("a vencer")),
            "regular": _as_int(summary.get("regular")),
            "sem_informacao": _as_int(summary.get("sem informação")),
        },
        "alerts": {
            "vencidos": _as_int(alerts.get("vencidos")),
            "vencem_hoje": _as_int(alerts.get("vencem_hoje")),
            "em_7_dias": _as_int(alerts.get("em_7_dias")),
            "em_30_dias": _as_int(alerts.get("em_30_dias")),
        },
    }


def serialize_dashboard_calendar(context: dict) -> dict:
    calendar = context.get("calendar", {})
    weeks = []
    for week in calendar.get("weeks", []):
        days = []
        for day in week:
            days.append(
                {
                    "iso_date": day.get("iso_date") or "",
                    "day_number": _as_int(day.get("day_number")),
                    "is_current_month": bool(day.get("is_current_month")),
                    "is_today": bool(day.get("is_today")),
                    "has_due": bool(day.get("has_due")),
                    "pulse": bool(day.get("pulse")),
                    "count": _as_int(day.get("count")),
                    "items": [_serialize_calendar_item(item) for item in day.get("items", [])],
                }
            )
        weeks.append(days)
    return {
        "month_label": calendar.get("month_label") or "",
        "weekday_labels": list(calendar.get("weekday_labels", [])),
        "today_label": calendar.get("today_label") or "",
        "items_total": _as_int(calendar.get("items_total")),
        "weeks": weeks,
        "upcoming": [_serialize_calendar_item(item) for item in calendar.get("upcoming_rows", [])],
    }


def serialize_dashboard_critical_trainings(rows: list[dict]) -> dict:
    return {
        "items": [
            {
                "id": int(row["id"]),
                "tripulante_id": int(row["tripulante_id"]),
                "tripulante_nome": row.get("tripulante_nome") or "",
                "equipamento_id": row.get("equipamento_id"),
                "equipamento_nome": row.get("equipamento_nome") or "",
                "tipo_treinamento_id": row.get("tipo_treinamento_id"),
                "tipo_treinamento_nome": row.get("tipo_treinamento_nome") or "",
                "data_realizacao": _as_iso_date_or_none(row.get("data_realizacao")),
                "data_vencimento": _as_iso_date_or_none(row.get("data_vencimento")),
                "status": row.get("status_calculado") or "",
            }
            for row in rows
        ]
    }
