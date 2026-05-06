from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from flask import Response, request

from ..constants import CONSOLIDATED_SORT_OPTIONS, CONSOLIDATED_STATUS_FILTERS, PT_BR_MONTHS


def env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value

def format_competencia_label(competencia: str) -> str:
    raw = (competencia or "").strip()
    try:
        parsed = datetime.strptime(raw, "%Y-%m")
    except ValueError:
        return raw
    return f"{PT_BR_MONTHS[parsed.month - 1]}/{parsed.year}"

def normalize_consolidated_status(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in CONSOLIDATED_STATUS_FILTERS else ""

def normalize_consolidated_sort(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in CONSOLIDATED_SORT_OPTIONS else "criticidade"

def days_remaining_label(days_remaining: int | None) -> str:
    if days_remaining is None:
        return "Sem vencimento informado"
    if days_remaining < 0:
        return f"Vencida há {abs(days_remaining)} dia(s)"
    if days_remaining == 0:
        return "Vence hoje"
    if days_remaining == 1:
        return "1 dia"
    return f"{days_remaining} dias"


def json_response_with_etag(payload, *, max_age: int = 15):
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    etag = hashlib.sha256(body.encode("utf-8")).hexdigest()

    if request.if_none_match and request.if_none_match.contains(etag):
        response = Response(status=304)
    else:
        response = Response(body, mimetype="application/json")

    response.set_etag(etag)
    normalized_max_age = int(max_age)
    if normalized_max_age <= 0:
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Cache-Control"] = f"private, max-age={normalized_max_age}, must-revalidate"
    return response
