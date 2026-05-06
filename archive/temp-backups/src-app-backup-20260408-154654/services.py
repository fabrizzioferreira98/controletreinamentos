from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Iterable
from urllib.parse import quote
from zoneinfo import ZoneInfo

DATE_FMT = "%Y-%m-%d"
BUSINESS_TIMEZONE = ZoneInfo("America/Sao_Paulo")

EXPIRY_STATUS_META = {
    "vencido": {
        "key": "vencido",
        "label": "Vencido",
        "badge_class": "status-critical",
        "indicator_class": "avatar-expiry--expired",
        "pulse": True,
        "priority": 0,
    },
    "critico_15": {
        "key": "critico_15",
        "label": "Crítico (até 15 dias)",
        "badge_class": "status-red",
        "indicator_class": "avatar-expiry--warning-15",
        "pulse": True,
        "priority": 1,
    },
    "vencer_30": {
        "key": "vencer_30",
        "label": "A vencer em até 30 dias",
        "badge_class": "status-red",
        "indicator_class": "avatar-expiry--warning-30",
        "pulse": False,
        "priority": 2,
    },
    "vencer_60": {
        "key": "vencer_60",
        "label": "A vencer em até 60 dias",
        "badge_class": "status-orange",
        "indicator_class": "avatar-expiry--warning-60",
        "pulse": False,
        "priority": 3,
    },
    "vencer_90": {
        "key": "vencer_90",
        "label": "A vencer em até 90 dias",
        "badge_class": "status-yellow",
        "indicator_class": "avatar-expiry--warning-90",
        "pulse": False,
        "priority": 4,
    },
    "em_dia": {
        "key": "em_dia",
        "label": "Em dia",
        "badge_class": "status-green",
        "indicator_class": "avatar-expiry--safe",
        "pulse": False,
        "priority": 5,
    },
    "sem_vencimento": {
        "key": "sem_vencimento",
        "label": "Sem vencimento informado",
        "badge_class": "status-gray",
        "indicator_class": "avatar-expiry--neutral",
        "pulse": False,
        "priority": 6,
    },
}


def parse_date(value: str | date | None):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except (TypeError, ValueError):
        return None


def add_months(base_date: str | date | None, months: int) -> str | None:
    parsed = parse_date(base_date)
    if parsed is None or months <= 0:
        return None

    month_index = parsed.month - 1 + months
    year = parsed.year + month_index // 12
    month = month_index % 12 + 1
    day = min(parsed.day, monthrange(year, month)[1])
    return date(year, month, day).strftime(DATE_FMT)


def business_today() -> date:
    return datetime.now(BUSINESS_TIMEZONE).date()


def calculate_days_until(data_vencimento: str | date | None, reference: date | None = None) -> int | None:
    due_date = parse_date(data_vencimento)
    if due_date is None:
        return None
    today = reference or business_today()
    return (due_date - today).days


def resolve_expiry_status(days_remaining: int | None) -> dict:
    if days_remaining is None:
        return dict(EXPIRY_STATUS_META["sem_vencimento"])
    if days_remaining < 0:
        return dict(EXPIRY_STATUS_META["vencido"])
    if days_remaining <= 15:
        return dict(EXPIRY_STATUS_META["critico_15"])
    if days_remaining <= 30:
        return dict(EXPIRY_STATUS_META["vencer_30"])
    if days_remaining <= 60:
        return dict(EXPIRY_STATUS_META["vencer_60"])
    if days_remaining <= 90:
        return dict(EXPIRY_STATUS_META["vencer_90"])
    return dict(EXPIRY_STATUS_META["em_dia"])


def resolve_expiry_indicator_state(days_remaining: int | None) -> dict:
    status = resolve_expiry_status(days_remaining)
    return {
        "key": status["key"],
        "label": status["label"],
        "css_class": status["indicator_class"],
        "pulse": bool(status["pulse"]),
        "priority": int(status["priority"]),
    }


def build_expiry_status(data_vencimento: str | date | None, reference: date | None = None) -> dict:
    due_date = parse_date(data_vencimento)
    days_remaining = calculate_days_until(due_date, reference=reference)
    status = resolve_expiry_status(days_remaining)
    due_date_iso = due_date.strftime(DATE_FMT) if due_date else None
    due_date_label = due_date.strftime("%d/%m/%Y") if due_date else ""
    return {
        **status,
        "days_remaining": days_remaining,
        "due_date_iso": due_date_iso,
        "due_date_label": due_date_label,
        "sort_due_date": due_date or date.max,
    }


def build_expiry_indicator(data_vencimento: str | date | None, reference: date | None = None) -> dict:
    status = build_expiry_status(data_vencimento, reference=reference)
    return {
        "key": status["key"],
        "label": status["label"],
        "css_class": status["indicator_class"],
        "pulse": bool(status["pulse"]),
        "priority": int(status["priority"]),
        "days_remaining": status["days_remaining"],
        "due_date_iso": status["due_date_iso"],
        "due_date_label": status["due_date_label"],
    }


def calculate_training_status(data_vencimento: str | date | None, reference: date | None = None) -> str:
    # Handle if it's already a date object due to new schema
    if isinstance(data_vencimento, date):
        due_date = data_vencimento
    else:
        due_date = parse_date(data_vencimento)
    today = reference or business_today()

    if due_date is None:
        return "sem informação"

    if due_date < today:
        return "vencido"

    if (due_date - today).days <= 30:
        return "a vencer"

    return "regular"


def status_color(status: str) -> str:
    return {
        "vencido": "status-red",
        "a vencer": "status-yellow",
        "regular": "status-green",
        "sem informação": "status-gray",
    }.get(status, "status-gray")


def summarize_training_status(rows: Iterable[dict]) -> dict:
    summary = {
        "total": 0,
        "vencido": 0,
        "a vencer": 0,
        "regular": 0,
        "sem informação": 0,
    }
    for row in rows:
        status = row["status_calculado"]
        summary["total"] += 1
        summary[status] += 1
    return summary


def training_sort_key(row: dict):
    status_priority = {
        "vencido": 0,
        "a vencer": 1,
        "regular": 2,
        "sem informação": 3,
    }
    if isinstance(row["data_vencimento"], date):
        due_date = row["data_vencimento"]
    else:
        due_date = parse_date(row["data_vencimento"])

    return (
        status_priority.get(row["status_calculado"], 99),
        due_date or date.max,
        row["tipo_treinamento_nome"] or "",
    )


def name_initials(name: str | None) -> str:
    parts = [part for part in (name or "").strip().split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def normalize_phone_digits(phone: str | None) -> str:
    digits = "".join(char for char in (phone or "") if char.isdigit())
    if not digits:
        return ""
    if digits.startswith("55"):
        return digits
    if len(digits) in {10, 11}:
        return f"55{digits}"
    return digits


def build_tripulante_whatsapp_message(name: str | None, upcoming_items: Iterable[dict] | None = None) -> str:
    items = list(upcoming_items or [])
    saudacao = f"Prezado(a) {name or 'tripulante'},"
    intro = (
        "Constam os seguintes treinamentos com vencimento próximo em seu cadastro "
        "no sistema Treinamentos Brasil vida:"
    )

    if items:
        lines = []
        for item in items:
            equipment_name = item.get("equipamento_nome")
            equipment_suffix = f" ({equipment_name})" if equipment_name and equipment_name != "Sem equipamento" else ""
            lines.append(
                f"- {item.get('tipo_treinamento_nome') or 'Treinamento'}"
                f"{equipment_suffix}"
                f" — vencimento em {item.get('data_vencimento')}"
            )
        body = "\n".join(lines)
    else:
        body = "- Não há treinamentos com vencimento próximo listados neste momento."

    closing = (
        "Solicitamos que verifique sua situação junto à coordenação operacional "
        "e adote as providências necessárias dentro do prazo estabelecido.\n\n"
        "Atenciosamente,\n"
        "Coordenação Operacional\n"
        "Treinamentos Brasil vida"
    )
    return f"{saudacao}\n\n{intro}\n\n{body}\n\n{closing}"


def whatsapp_tripulante_link(name: str | None, phone: str | None, upcoming_items: Iterable[dict] | None = None) -> str | None:
    normalized_phone = normalize_phone_digits(phone)
    if not normalized_phone:
        return None
    items = list(upcoming_items or [])
    message = build_tripulante_whatsapp_message(name, items)
    return f"https://wa.me/{normalized_phone}?text={quote(message)}"
