from __future__ import annotations

from decimal import Decimal

from ..core.utils import format_competencia_label


def _as_int(value) -> int:
    return int(value or 0)


def _as_float(value) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


def _serialize_alert(item: dict) -> dict:
    return {
        "level": item.get("level") or "normal",
        "message": item.get("message") or "",
    }


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


def _serialize_panel_item(item: dict) -> dict:
    return {
        "treinamento_id": int(item["treinamento_id"]),
        "tripulante_id": int(item["tripulante_id"]),
        "tripulante_nome": item.get("tripulante_nome") or "",
        "tripulante_base": item.get("tripulante_base") or "",
        "habilitacao_nome": item.get("habilitacao_nome") or "",
        "data_vencimento": item.get("due_date_label") or "",
        "days_remaining": item.get("days_remaining"),
        "status_key": item.get("status_key") or "",
        "status_label": item.get("status_label") or "",
        "pulse": bool(item.get("pulse")),
        "priority": _as_int(item.get("priority")),
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
                "data_realizacao": row.get("data_realizacao"),
                "data_vencimento": row.get("data_vencimento"),
                "status": row.get("status_calculado") or "",
            }
            for row in rows
        ]
    }


def serialize_tv_vencimentos_payload(payload: dict) -> dict:
    summary = payload.get("summary", {})
    return {
        "generated_at": {
            "iso": payload.get("generated_at_iso") or "",
            "label": payload.get("generated_at_label") or "",
        },
        "base_filter": payload.get("base_filter") or "",
        "summary": {
            "total_tripulantes": _as_int(summary.get("total_tripulantes")),
            "total_habilitacoes": _as_int(summary.get("total_habilitacoes")),
            "total_em_dia": _as_int(summary.get("total_em_dia")),
            "total_vencer_90": _as_int(summary.get("total_vencer_90")),
            "total_vencer_60": _as_int(summary.get("total_vencer_60")),
            "total_vencer_30": _as_int(summary.get("total_vencer_30")),
            "total_critico_15": _as_int(summary.get("total_critico_15")),
            "total_vencido": _as_int(summary.get("total_vencido")),
        },
        "proximos_vencimentos": [_serialize_panel_item(item) for item in payload.get("proximos_vencimentos", [])],
        "critical_trainings": [_serialize_panel_item(item) for item in payload.get("criticos", [])],
        "expired_trainings": [_serialize_panel_item(item) for item in payload.get("vencidos", [])],
        "ranking_bases": [
            {
                "base": item.get("base") or "",
                "total_pendencias": _as_int(item.get("total_pendencias")),
            }
            for item in payload.get("ranking_bases", [])
        ],
        "ranking_tripulantes": [
            {
                "tripulante_id": int(item["tripulante_id"]),
                "tripulante_nome": item.get("tripulante_nome") or "",
                "base": item.get("base") or "",
                "total": _as_int(item.get("total")),
            }
            for item in payload.get("ranking_tripulantes", [])
        ],
        "alerts": [_serialize_alert(item) for item in payload.get("alerts", [])],
    }


def serialize_tv_produtividade_payload(*, competencia: str, summary: dict, rows: list[dict], updated_at: str) -> dict:
    return {
        "competencia": competencia,
        "competencia_label": format_competencia_label(competencia),
        "updated_at": updated_at,
        "summary": {
            key: _as_float(value)
            for key, value in summary.items()
        },
        "rows": [
            {
                "tripulante_id": int(row["tripulante_id"]),
                "tripulante_nome": row.get("tripulante_nome") or "",
                "base": row.get("base") or "",
                "categoria": row.get("categoria") or "",
                "funcao": row.get("funcao") or "",
                "total_missoes_validas": _as_int(row.get("total_missoes_validas")),
                "total_pernoites": _as_int(row.get("total_pernoites")),
                "total_produtividade": _as_float(row.get("total_produtividade")),
                "valor_final_mes": _as_float(row.get("valor_final_mes")),
                "criterio_fechamento": row.get("criterio_fechamento") or "",
            }
            for row in rows
        ],
    }
