from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

try:
    import psycopg2.extras
    _DictRow = psycopg2.extras.DictRow
except (ImportError, AttributeError):
    _DictRow = type(None)  # type: ignore[misc,assignment]

_REDACTED = "<redacted>"
_MAX_TEXT_LEN = 600
_SENSITIVE_FIELD_MARKERS = {
    "senha",
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "access_key",
    "cookie",
    "cpf",
    "documento",
    "telefone",
    "phone",
    "email",
    "foto",
    "arquivo_pdf",
    "arquivo",
    "anexo",
}


def _is_sensitive_key(key: str) -> bool:
    lowered = (key or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _SENSITIVE_FIELD_MARKERS)


def _truncate_text(value: str) -> str:
    if len(value) <= _MAX_TEXT_LEN:
        return value
    return f"{value[:_MAX_TEXT_LEN]}...[truncated]"


def _mask_cpf(value: str) -> str:
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) != 11:
        return _REDACTED
    return f"***.{digits[3:6]}.***-**"


def _mask_email(value: str) -> str:
    raw = (value or "").strip()
    if "@" not in raw:
        return _REDACTED
    local_part, domain = raw.split("@", 1)
    if not local_part:
        return f"{_REDACTED}@{domain}"
    return f"{local_part[:1]}***@{domain}"


def _mask_phone(value: str) -> str:
    digits = "".join(char for char in (value or "") if char.isdigit())
    if len(digits) < 4:
        return _REDACTED
    return f"***{digits[-4:]}"


def _mask_sensitive_value(key: str, value: Any):
    lowered = (key or "").lower()
    text = str(value or "")
    if "cpf" in lowered or "documento" in lowered:
        return _mask_cpf(text)
    if "email" in lowered:
        return _mask_email(text)
    if "telefone" in lowered or "phone" in lowered:
        return _mask_phone(text)
    if "foto" in lowered or "arquivo" in lowered or "anexo" in lowered:
        return _REDACTED
    return _REDACTED


def _normalize_value(value: Any, *, parent_key: str | None = None):
    if isinstance(value, _DictRow):
        return {key: _normalize_value(value[key], parent_key=str(key)) for key in value.keys()}
    if isinstance(value, dict):
        result = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                result[key] = _mask_sensitive_value(key, item)
            else:
                result[key] = _normalize_value(item, parent_key=key)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item, parent_key=parent_key) for item in value]
    if is_dataclass(value):
        return _normalize_value(asdict(value), parent_key=parent_key)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<binary:{len(bytes(value))} bytes>"
    if isinstance(value, str):
        if parent_key and _is_sensitive_key(parent_key):
            return _mask_sensitive_value(parent_key, value)
        return _truncate_text(value)
    return value


def normalize_audit_payload(value: Any):
    if value is None:
        return None
    return _normalize_value(value)


def record_audit_event(
    db,
    *,
    entidade: str,
    entidade_id: int,
    acao: str,
    realizado_por: int,
    payload_anterior=None,
    payload_novo=None,
    observacao: str | None = None,
):
    db.execute(
        """
        INSERT INTO auditoria_eventos
        (entidade, entidade_id, acao, payload_anterior, payload_novo, realizado_por, observacao)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        """,
        (
            entidade,
            entidade_id,
            acao,
            json.dumps(normalize_audit_payload(payload_anterior)) if payload_anterior is not None else None,
            json.dumps(normalize_audit_payload(payload_novo)) if payload_novo is not None else None,
            realizado_por,
            (observacao or "").strip() or None,
        ),
    )
