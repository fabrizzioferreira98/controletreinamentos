from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


PILOT_STATUS_KEYS = (
    "ativo",
    "folga",
    "ferias",
    "atestado",
    "afastado",
    "treinamento",
    "desconhecido",
)


def _as_int(value, *, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _as_optional_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _as_bool(value) -> bool:
    return bool(value)


def _as_float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _as_text(value) -> str:
    return str(value or "").strip()


def _empty_to_none(value) -> str | None:
    text = _as_text(value)
    return text or None


def _as_iso_datetime_or_none(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _empty_to_none(value)


def parse_bases_status_filter(args) -> str:
    return _as_text(args.get("status")).lower()


def parse_base_pilot_add_request(payload) -> dict:
    return {
        "nome": _as_text(payload.get("nome")),
        "matricula": _as_text(payload.get("matricula")),
        "status": _as_text(payload.get("status")),
        "base_id": _as_text(payload.get("base_id")),
        "tripulante_id": _as_text(payload.get("tripulante_id")),
        "observacao": _as_text(payload.get("observacao")),
    }


def parse_base_pilot_status_request(payload) -> dict:
    return {
        "status_novo": _as_text(payload.get("status_novo")),
        "observacao": _as_text(payload.get("observacao")),
    }


def parse_base_pilot_move_request(payload) -> dict:
    return {
        "base_nova_id": _as_text(payload.get("base_nova_id")),
        "observacao": _as_text(payload.get("observacao")),
    }


def _serialize_status_option(item: dict) -> dict:
    return {
        "key": _as_text(item.get("key")),
        "label": _as_text(item.get("label")),
        "class": _as_text(item.get("class")),
        "marker_class": _as_text(item.get("marker_class")),
    }


def _serialize_counts(counts: dict | None) -> dict:
    source = counts or {}
    serialized = {key: _as_int(source.get(key)) for key in PILOT_STATUS_KEYS}
    for key, value in source.items():
        normalized_key = _as_text(key)
        if normalized_key and normalized_key not in serialized:
            serialized[normalized_key] = _as_int(value)
    return serialized


def _serialize_expiry_indicator(item: dict | None) -> dict:
    source = item or {}
    return {
        "key": _as_text(source.get("key")),
        "label": _as_text(source.get("label")),
        "css_class": _as_text(source.get("css_class")),
        "pulse": _as_bool(source.get("pulse")),
        "priority": _as_int(source.get("priority")),
        "days_remaining": _as_optional_int(source.get("days_remaining")),
        "due_date_iso": _as_iso_datetime_or_none(source.get("due_date_iso")),
        "due_date_label": _as_text(source.get("due_date_label")),
    }


def _serialize_pilot(item: dict) -> dict:
    return {
        "id": _as_int(item.get("id")),
        "nome": _as_text(item.get("nome")),
        "matricula": _as_text(item.get("matricula")),
        "tripulante_id": _as_optional_int(item.get("tripulante_id")),
        "base_id": _as_int(item.get("base_id")),
        "base_nome": _as_text(item.get("base_nome")),
        "base_uf": _as_text(item.get("base_uf")),
        "status": _as_text(item.get("status")),
        "status_label": _as_text(item.get("status_label")),
        "status_class": _as_text(item.get("status_class")),
        "status_raw": _empty_to_none(item.get("status_raw")),
        "possui_foto": _as_bool(item.get("possui_foto")),
        "foto_url": _as_text(item.get("foto_url")),
        "iniciais": _as_text(item.get("iniciais")),
        "expiry_indicator": _serialize_expiry_indicator(item.get("expiry_indicator")),
        "criado_em": _as_text(item.get("criado_em")),
        "criado_em_iso": _as_iso_datetime_or_none(item.get("criado_em_iso")),
    }


def _serialize_base(item: dict) -> dict:
    return {
        "id": _as_int(item.get("id")),
        "nome": _as_text(item.get("nome")),
        "uf": _as_text(item.get("uf")),
        "latitude": _as_float_or_none(item.get("latitude")),
        "longitude": _as_float_or_none(item.get("longitude")),
        "ativa": _as_bool(item.get("ativa")),
        "total_pilotos": _as_int(item.get("total_pilotos")),
        "counts": _serialize_counts(item.get("counts")),
        "pilotos": [_serialize_pilot(pilot) for pilot in item.get("pilotos", [])],
    }


def serialize_bases_payload(payload: dict) -> dict:
    return {
        "success": True,
        "status": 200,
        "code": "bases_payload_ok",
        "bases": [_serialize_base(item) for item in payload.get("bases", [])],
        "pilotos": [_serialize_pilot(item) for item in payload.get("pilotos", [])],
        "status_options": [_serialize_status_option(item) for item in payload.get("status_options", [])],
        "status_filter": _as_text(payload.get("status_filter")),
    }


def serialize_base_pilot_added(result: dict) -> dict:
    return {
        "success": True,
        "status": 201,
        "code": "base_pilot_added",
        "message": _as_text(result.get("message")),
        "pilot_id": _as_int(result.get("pilot_id")),
    }


def serialize_base_pilot_mutation(result: dict, *, code: str, pilot_id: int) -> dict:
    return {
        "success": True,
        "status": 200,
        "code": code,
        "message": _as_text(result.get("message")),
        "pilot_id": int(pilot_id),
    }


def _serialize_history_pilot(item: dict) -> dict:
    return {
        "id": _as_int(item.get("id")),
        "nome": _as_text(item.get("nome")),
        "matricula": _as_text(item.get("matricula")),
    }


def _serialize_history_item(item: dict) -> dict:
    return {
        "id": _as_int(item.get("id")),
        "event_type": _as_text(item.get("event_type")),
        "status_anterior": _empty_to_none(item.get("status_anterior")),
        "status_novo": _empty_to_none(item.get("status_novo")),
        "base_anterior_nome": _empty_to_none(item.get("base_anterior_nome")),
        "base_nova_nome": _empty_to_none(item.get("base_nova_nome")),
        "alterado_por": _as_text(item.get("alterado_por")),
        "alterado_em": _as_text(item.get("alterado_em")),
        "alterado_em_iso": _as_iso_datetime_or_none(item.get("alterado_em_iso")),
        "observacao": _as_text(item.get("observacao")),
    }


def serialize_base_pilot_history(payload: dict) -> dict:
    return {
        "success": True,
        "status": 200,
        "code": "base_pilot_history_ok",
        "piloto": _serialize_history_pilot(payload.get("piloto", {})),
        "historico": [_serialize_history_item(item) for item in payload.get("historico", [])],
    }
