from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Callable
from xml.etree import ElementTree

from ..infra.aisweb_client import (
    DEFAULT_AISWEB_BASE_URL,
    AiswebClientError,
    fetch_aisweb_notams,
)
from .aisweb_weather import (
    AiswebConfigurationError,
    AiswebResponseError,
    AiswebValidationError,
    normalize_icao_code,
)

NotamFetcher = Callable[..., str]

SEVERITY_RANK = {"critical": 0, "warning": 1, "attention": 2, "info": 3}
CRITICAL_TERMS = (
    " RWY ",
    " PISTA ",
    "CLSD",
    "FECHAD",
    "INTERDIT",
    "OBST",
    "INOP",
    "UNSERVICEABLE",
    "AERODROME CLOSED",
    "AD CLSD",
)
WARNING_TERMS = ("RTO", "NAV", "COM", "ILS", "VOR", "NDB", "GNSS", "AUTH", "COOR")


@dataclass
class _NotamCacheEntry:
    payload: dict
    fetched_at: datetime
    expires_at: datetime


_NOTAM_CACHE: dict[str, _NotamCacheEntry] = {}
_CACHE_LOCK = threading.RLock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _configuration() -> dict:
    api_key = (os.getenv("AISWEB_API_KEY", "") or "").strip()
    api_pass = (os.getenv("AISWEB_API_PASS", "") or "").strip()
    base_url = (os.getenv("AISWEB_BASE_URL", "") or DEFAULT_AISWEB_BASE_URL).strip() or DEFAULT_AISWEB_BASE_URL
    if not api_key or not api_pass:
        raise AiswebConfigurationError("Credenciais AISWEB ausentes.")
    return {
        "api_key": api_key,
        "api_pass": api_pass,
        "base_url": base_url,
        "timeout_seconds": _env_int("AISWEB_TIMEOUT_SECONDS", 8, minimum=1, maximum=30),
    }


def _compact_text(value: str | None) -> str:
    return " ".join(unescape(value or "").split())


def _tag_text(parent: ElementTree.Element, name: str) -> str:
    child = parent.find(name)
    if child is None:
        return ""
    return _compact_text("".join(child.itertext()))


def _parse_aisweb_datetime(value: str | None) -> str | None:
    raw = _compact_text(value)
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            return _iso_utc(parsed)
        except ValueError:
            pass
    if len(raw) == 10 and raw.isdigit():
        try:
            parsed = datetime.strptime(raw, "%y%m%d%H%M").replace(tzinfo=timezone.utc)
            return _iso_utc(parsed)
        except ValueError:
            return None
    return None


def _notam_label(value: str | None) -> str:
    parsed = _parse_aisweb_datetime(value)
    if not parsed:
        return _compact_text(value) or "--"
    dt = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    return dt.strftime("%d/%m %H:%MZ")


def _notam_severity(item: dict) -> str:
    haystack = f" {item.get('category', '')} {item.get('description', '')} {item.get('qcode', '')} ".upper()
    if any(term in haystack for term in CRITICAL_TERMS):
        return "critical"
    if any(term in haystack for term in WARNING_TERMS):
        return "warning"
    if item.get("type") == "NOTAMR":
        return "attention"
    return "info"


def parse_aisweb_notam_response(raw_response: str | None, *, icao_code: str, now: datetime | None = None) -> dict:
    text = (raw_response or "").strip()
    if not text:
        raise AiswebResponseError("Resposta AISWEB NOTAM vazia.")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise AiswebResponseError("XML AISWEB NOTAM invalido.") from exc

    notam_node = root.find(".//notam")
    if notam_node is None:
        raise AiswebResponseError("Bloco NOTAM ausente na resposta AISWEB.")

    reference = (now or _utc_now()).astimezone(timezone.utc)
    updated_at = _parse_aisweb_datetime(notam_node.attrib.get("updatedat")) or _iso_utc(reference)
    items: list[dict] = []
    for item_node in notam_node.findall(".//item"):
        notam_id = _tag_text(item_node, "id") or item_node.attrib.get("id") or ""
        notam_number = _tag_text(item_node, "n") or _tag_text(item_node, "cod") or notam_id
        description = _tag_text(item_node, "e")
        loc = _tag_text(item_node, "loc") or _tag_text(item_node, "icaoairport_id") or icao_code
        starts_at = _parse_aisweb_datetime(_tag_text(item_node, "b"))
        valid_until = _parse_aisweb_datetime(_tag_text(item_node, "c"))
        item = {
            "id": notam_id or f"{loc}-{notam_number}",
            "notamId": notam_id,
            "number": notam_number,
            "code": _tag_text(item_node, "cat") or "NOTAM",
            "qcode": _tag_text(item_node, "cod"),
            "icao": loc,
            "icaoCode": loc,
            "description": description,
            "message": description,
            "updatedAt": _parse_aisweb_datetime(_tag_text(item_node, "dt")) or starts_at or updated_at,
            "updatedAtLabel": _notam_label(_tag_text(item_node, "dt") or _tag_text(item_node, "b")),
            "validFrom": starts_at,
            "validUntil": valid_until,
            "validUntilLabel": _notam_label(_tag_text(item_node, "c")),
            "type": _tag_text(item_node, "tp"),
            "category": _tag_text(item_node, "cat"),
            "status": _tag_text(item_node, "status") or _tag_text(item_node, "state") or "ACTIVE",
            "source": "AISWEB",
        }
        item["severity"] = _notam_severity(item)
        if item["description"]:
            items.append(item)

    return {
        "status": "available" if items else "empty",
        "source": "AISWEB",
        "updatedAt": updated_at,
        "updatedAtLabel": _notam_label(notam_node.attrib.get("updatedat")),
        "message": "" if items else "Nenhum NOTAM relevante retornado pela AISWEB para esta base.",
        "items": items,
    }


def _cache_get(icao_code: str, *, now: datetime, allow_stale: bool = False) -> dict | None:
    with _CACHE_LOCK:
        entry = _NOTAM_CACHE.get(icao_code)
        if not entry:
            return None
        is_fresh = entry.expires_at > now
        if not is_fresh and not allow_stale:
            return None
        payload = dict(entry.payload)
        if not is_fresh:
            payload["status"] = "stale" if payload.get("items") else "empty"
        return payload


def _cache_set(icao_code: str, payload: dict, *, now: datetime, ttl_seconds: int) -> None:
    with _CACHE_LOCK:
        _NOTAM_CACHE[icao_code] = _NotamCacheEntry(
            payload=dict(payload),
            fetched_at=now,
            expires_at=datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc),
        )


def clear_aisweb_notam_cache() -> None:
    with _CACHE_LOCK:
        _NOTAM_CACHE.clear()


def get_aisweb_notams(
    icao_code: str,
    *,
    now: datetime | None = None,
    fetcher: NotamFetcher = fetch_aisweb_notams,
) -> dict:
    reference = (now or _utc_now()).astimezone(timezone.utc)
    normalized_icao = normalize_icao_code(icao_code)
    cached = _cache_get(normalized_icao, now=reference)
    if cached:
        return cached

    try:
        config = _configuration()
    except AiswebConfigurationError:
        stale = _cache_get(normalized_icao, now=reference, allow_stale=True)
        if stale:
            return stale
        return {
            "status": "unavailable",
            "source": "not_configured",
            "updatedAt": _iso_utc(reference),
            "updatedAtLabel": "\u00daltima atualiza\u00e7\u00e3o indispon\u00edvel",
            "message": "Credenciais AISWEB indispon\u00edveis para consulta real de NOTAM.",
            "items": [],
        }

    ttl_seconds = _env_int("AISWEB_NOTAM_CACHE_TTL_SECONDS", 300, minimum=60, maximum=900)
    try:
        raw_response = fetcher(icao_code=normalized_icao, **config)
        payload = parse_aisweb_notam_response(raw_response, icao_code=normalized_icao, now=reference)
        _cache_set(normalized_icao, payload, now=reference, ttl_seconds=ttl_seconds)
        return payload
    except (AiswebClientError, AiswebResponseError, AiswebValidationError):
        stale = _cache_get(normalized_icao, now=reference, allow_stale=True)
        if stale:
            return stale
        return {
            "status": "error",
            "source": "AISWEB",
            "updatedAt": _iso_utc(reference),
            "updatedAtLabel": "\u00daltima atualiza\u00e7\u00e3o indispon\u00edvel",
            "message": "Falha ao consultar NOTAM real na AISWEB.",
            "items": [],
        }
