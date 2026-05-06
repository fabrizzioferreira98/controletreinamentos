from __future__ import annotations

import base64
import binascii
from decimal import Decimal
from math import ceil
from urllib.parse import unquote, urlsplit

from email_validator import EmailNotValidError, validate_email
from flask import current_app, g, jsonify, request, url_for
from werkzeug.utils import secure_filename

from ..constants import DEFAULT_PAGE_SIZE, MAX_PHOTO_BYTES, MAX_TEXT_LENGTH, PHOTO_PREFIXES
from ..services import parse_date
from .http_contract import PROGRAMMATIC_JSON_PATH_PREFIXES, is_programmatic_json_endpoint


def _coerce_text_value(form, field_name):
    value = form.get(field_name, "")
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def get_required_text(form, field_name, label):
    value = _coerce_text_value(form, field_name)
    if not value:
        raise ValueError(f"O campo '{label}' é obrigatório.")
    max_len = MAX_TEXT_LENGTH.get(field_name)
    if max_len and len(value) > max_len:
        raise ValueError(f"O campo '{label}' excede o limite de {max_len} caracteres.")
    return value

def get_optional_text(form, field_name):
    value = _coerce_text_value(form, field_name)
    max_len = MAX_TEXT_LENGTH.get(field_name)
    if max_len and len(value) > max_len:
        raise ValueError(f"O campo '{field_name}' excede o limite de {max_len} caracteres.")
    return value

def get_required_int(form, field_name, label):
    value = get_required_text(form, field_name, label)
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"O campo '{label}' é inválido.") from exc

def digits_only(value: str | None) -> str:
    return "".join(char for char in (value or "") if char.isdigit())

def get_validated_cpf(form, field_name="cpf", label="CPF"):
    value = get_required_text(form, field_name, label)
    digits = digits_only(value)
    if len(digits) != 11:
        raise ValueError("O campo 'CPF' deve conter exatamente 11 dígitos.")
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"

def get_validated_anac_code(form, field_name="licenca_anac", label="Código ANAC"):
    value = get_required_text(form, field_name, label)
    digits = digits_only(value)
    if len(digits) != 6:
        raise ValueError("O campo 'Código ANAC' deve conter exatamente 6 dígitos.")
    return digits

def get_optional_int(form, field_name, label):
    value = get_optional_text(form, field_name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"O campo '{label}' é inválido.") from exc

def get_optional_decimal(form, field_name, label):
    raw_value = form.get(field_name, "")
    if raw_value in ("", None):
        return Decimal("0")
    if isinstance(raw_value, Decimal):
        return raw_value
    if isinstance(raw_value, int):
        return Decimal(raw_value)
    if isinstance(raw_value, float):
        return Decimal(str(raw_value))
    value = get_optional_text(form, field_name)
    if not value:
        return Decimal("0")
    normalized = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except Exception as exc:
        raise ValueError(f"O campo '{label}' é inválido.") from exc

def get_required_date(form, field_name, label):
    value = get_required_text(form, field_name, label)
    parsed = parse_date(value)
    if parsed is None:
        raise ValueError(f"O campo '{label}' deve estar no formato YYYY-MM-DD.")
    return value

def get_optional_date(form, field_name, label):
    value = get_optional_text(form, field_name)
    if not value:
        return None
    if parse_date(value) is None:
        raise ValueError(f"O campo '{label}' deve estar no formato YYYY-MM-DD.")
    return value

def get_validated_email(form, field_name, label):
    value = get_required_text(form, field_name, label)
    try:
        return validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ValueError(f"O campo '{label}' é inválido.") from exc

def get_optional_email(form, field_name, label):
    value = get_optional_text(form, field_name)
    if not value:
        return ""
    try:
        return validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ValueError(f"O campo '{label}' é inválido.") from exc

def get_optional_limited_text(form, field_name, label):
    try:
        return get_optional_text(form, field_name)
    except ValueError as exc:
        raise ValueError(f"O campo '{label}' é inválido.") from exc

def sanitize_photo_base64(form, *, current_value=None):
    if form.get("remove_foto", "").strip() == "1":
        return None

    value = form.get("foto_base64", "").strip()
    if not value:
        return current_value
    if not any(value.startswith(prefix) for prefix in PHOTO_PREFIXES):
        raise ValueError("A foto deve estar em JPG, PNG ou WEBP.")
    try:
        decoded = base64.b64decode(value.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("A foto enviada está inválida.") from exc
    if len(decoded) > MAX_PHOTO_BYTES:
        raise ValueError("A foto deve ter no máximo 1 MB.")
    return value

def get_page_arg() -> int:
    raw = request.args.get("page", "1").strip()
    try:
        page = int(raw)
    except ValueError:
        return 1
    return max(1, page)

def build_pagination(endpoint: str, page: int, per_page: int, total: int, **params):
    pages = max(1, ceil(total / per_page)) if total else 1
    if page > pages:
        page = pages
    safe_params = {key: value for key, value in params.items() if value not in ("", None)}
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_prev": page > 1,
        "has_next": page < pages,
        "prev_url": None,
        "next_url": None,
    }
    if pagination["has_prev"]:
        pagination["prev_url"] = url_for(endpoint, page=page - 1, **safe_params)
    if pagination["has_next"]:
        pagination["next_url"] = url_for(endpoint, page=page + 1, **safe_params)
    return pagination

def normalize_page(page: int, per_page: int, total: int) -> int:
    pages = max(1, ceil(total / per_page)) if total else 1
    return min(page, pages)

def resolve_pagination_state(
    total: int,
    *,
    endpoint: str | None = None,
    per_page: int = DEFAULT_PAGE_SIZE,
    **params,
) -> dict:
    page = normalize_page(get_page_arg(), per_page, total)
    state = {
        "page": page,
        "per_page": per_page,
        "offset": (page - 1) * per_page,
    }
    if endpoint:
        state["pagination"] = build_pagination(endpoint, page, per_page, total, **params)
    return state

def safe_next_url(value: str | None, fallback: str) -> str:
    raw = (value or "").strip()
    if not raw or any(marker in raw for marker in ("\x00", "\r", "\n", "\\")):
        return fallback
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return fallback
    decoded = unquote(raw)
    if decoded.startswith("//") or any(marker in decoded for marker in ("\x00", "\r", "\n", "\\")):
        return fallback
    if parsed.path.startswith("/") and not raw.startswith("//"):
        return raw
    return fallback

def safe_pdf_filename(value: str | None, *, fallback: str = "anexo.pdf") -> str:
    cleaned = secure_filename((value or "").strip())
    if not cleaned:
        return fallback
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned

def expects_json_response() -> bool:
    endpoint = (request.endpoint or "").strip()
    view_func = current_app.view_functions.get(endpoint) if endpoint else None
    if is_programmatic_json_endpoint(endpoint, view_func):
        return True
    path = (request.path or "").strip().lower()
    if any(path.startswith(prefix) for prefix in PROGRAMMATIC_JSON_PATH_PREFIXES):
        return True
    xrw = (request.headers.get("X-Requested-With", "") or "").strip().lower()
    if xrw == "xmlhttprequest":
        return True
    best = request.accept_mimetypes
    return best.best == "application/json" and best["application/json"] >= best["text/html"]


def expects_binary_asset_response() -> bool:
    sec_fetch_dest = (request.headers.get("Sec-Fetch-Dest", "") or "").strip().lower()
    if sec_fetch_dest:
        # Navegação HTML envia Accept com image/*; usar Sec-Fetch-Dest evita falso 401.
        return sec_fetch_dest in {"image", "audio", "video", "font"}
    path = (request.path or "").strip().lower()
    if path.endswith("/foto"):
        return True
    best = request.accept_mimetypes
    best_match = (best.best or "").strip().lower()
    if (
        best_match.startswith(("image/", "audio/", "video/", "font/"))
        and best[best_match] >= best["text/html"]
        and best[best_match] >= best["application/json"]
    ):
        return True
    accept = (request.headers.get("Accept", "") or "").strip().lower()
    if accept.startswith(("image/", "audio/", "video/", "font/")):
        return True
    return False

def error_payload(message: str, *, status: int, code=None, details: dict | None = None):
    payload = {
        "success": False,
        "message": message,
        "status": status,
        "request_id": getattr(g, "request_id", None),
        "correlation_id": getattr(g, "correlation_id", None),
    }
    if code:
        payload["code"] = code
    if details:
        payload["details"] = details
    return jsonify(payload), status


def domain_error_payload(exc):
    return error_payload(exc.message, status=exc.status, code=exc.code, details=getattr(exc, "details", None))
