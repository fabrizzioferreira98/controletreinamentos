from __future__ import annotations

import calendar
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Callable
from xml.etree import ElementTree

from ..infra.aisweb_client import (
    DEFAULT_AISWEB_BASE_URL,
    AiswebClientError,
    fetch_aisweb_met,
)

WeatherFetcher = Callable[..., str]

ICAO_RE = re.compile(r"^[A-Z]{4}$")
METAR_TEMPERATURE_RE = re.compile(r"\b(?P<temperature>M?\d{2})/(?P<dewpoint>M?\d{2}|//)\b")
METAR_WIND_RE = re.compile(r"\b(?P<direction>(?:\d{3}|VRB))(?P<speed>\d{2,3})(?:G\d{2,3})?KT\b")
METAR_OBSERVED_RE = re.compile(r"\b(?P<day>\d{2})(?P<hour>\d{2})(?P<minute>\d{2})Z\b")
METAR_VISIBILITY_RE = re.compile(r"\b(?P<visibility>\d{4})\b")
METAR_CEILING_RE = re.compile(r"\b(?P<cover>BKN|OVC|VV)(?P<height>\d{3}|///)\b")

LOCATION_LABELS = {
    "SBGO": "Goi\u00e2nia",
    "SBSP": "S\u00e3o Paulo",
    "SBPJ": "Palmas",
    "SBEG": "Manaus",
    "SBSV": "Salvador",
    "SBBE": "Bel\u00e9m",
    "SBSN": "Santar\u00e9m",
}

VALID_CONDITIONS = {"VMC", "IMC", "IFR", "MVFR", "UNKNOWN"}


class AiswebWeatherError(RuntimeError):
    pass


class AiswebConfigurationError(AiswebWeatherError):
    pass


class AiswebResponseError(AiswebWeatherError):
    pass


class AiswebValidationError(ValueError):
    pass


@dataclass
class _WeatherCacheEntry:
    payload: dict
    fetched_at: datetime
    expires_at: datetime


_MET_CACHE: dict[str, _WeatherCacheEntry] = {}
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


def normalize_icao_code(value: str | None) -> str:
    icao_code = (value or "").strip().upper()
    if not ICAO_RE.fullmatch(icao_code):
        raise AiswebValidationError("icaoCode deve conter quatro letras.")
    return icao_code


def _temperature_to_int(value: str | None) -> int | None:
    if not value:
        return None
    if value.startswith("M"):
        return -int(value[1:])
    return int(value)


def _metar_visibility_meters(raw_metar: str) -> int | None:
    if re.search(r"\bCAVOK\b", raw_metar):
        return 10000
    visibility_match = METAR_VISIBILITY_RE.search(raw_metar)
    return int(visibility_match.group("visibility")) if visibility_match else None


def _metar_lowest_ceiling_ft(raw_metar: str) -> int | None:
    ceilings: list[int] = []
    for match in METAR_CEILING_RE.finditer(raw_metar):
        height = match.group("height")
        if height == "///":
            continue
        ceilings.append(int(height) * 100)
    return min(ceilings) if ceilings else None


def _metar_operational_condition(raw_metar: str) -> str:
    if not raw_metar:
        return "UNKNOWN"
    if re.search(r"\bCAVOK\b", raw_metar):
        return "VMC"

    visibility_meters = _metar_visibility_meters(raw_metar)
    ceiling_ft = _metar_lowest_ceiling_ft(raw_metar)
    if visibility_meters is None and ceiling_ft is None:
        return "UNKNOWN"

    if (visibility_meters is not None and visibility_meters < 1500) or (
        ceiling_ft is not None and ceiling_ft < 500
    ):
        return "IMC"
    if (visibility_meters is not None and visibility_meters < 5000) or (
        ceiling_ft is not None and ceiling_ft < 1500
    ):
        return "IFR"
    if (visibility_meters is not None and visibility_meters < 8000) or (
        ceiling_ft is not None and ceiling_ft < 3000
    ):
        return "MVFR"
    return "VMC"


def parse_metar(metar: str | None, *, now: datetime | None = None) -> dict:
    raw = " ".join((metar or "").strip().split())
    temperature_match = METAR_TEMPERATURE_RE.search(raw)
    wind_match = METAR_WIND_RE.search(raw)
    visibility_meters = _metar_visibility_meters(raw)
    return {
        "temperatureC": _temperature_to_int(temperature_match.group("temperature")) if temperature_match else None,
        "windDirection": wind_match.group("direction") if wind_match else None,
        "windSpeedKt": int(wind_match.group("speed")) if wind_match else None,
        "visibilityMeters": visibility_meters,
        "observedAt": parse_metar_observed_at(raw, now=now),
        "condition": _metar_operational_condition(raw),
    }


def parse_metar_observed_at(metar: str | None, *, now: datetime | None = None) -> str | None:
    raw = metar or ""
    match = METAR_OBSERVED_RE.search(raw)
    if not match:
        return None

    reference = (now or _utc_now()).astimezone(timezone.utc)
    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if hour > 23 or minute > 59:
        return None

    try:
        candidate = datetime(reference.year, reference.month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None

    if (candidate - reference).total_seconds() > 2 * 24 * 60 * 60:
        year = reference.year
        month = reference.month - 1
        if month == 0:
            month = 12
            year -= 1
        _, days_in_month = calendar.monthrange(year, month)
        if day <= days_in_month:
            candidate = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)

    if abs((reference - candidate).total_seconds()) > 35 * 24 * 60 * 60:
        return None
    return _iso_utc(candidate)


def _compact_text(value: str | None) -> str | None:
    compacted = " ".join(unescape(value or "").split())
    return compacted or None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _extract_tag_values_from_xml(text: str) -> dict:
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise AiswebResponseError("XML AISWEB invalido.") from exc

    values: dict[str, str | None] = {"loc": None, "metar": None, "taf": None}
    for element in root.iter():
        name = _local_name(element.tag)
        if name in values and values[name] is None:
            values[name] = _compact_text("".join(element.itertext()))
    return values


def _extract_tag_values_from_plain_text(text: str) -> dict:
    normalized = " ".join(text.split())
    values: dict[str, str | None] = {"loc": None, "metar": None, "taf": None}
    loc_match = re.search(r"\b[A-Z]{4}\b", normalized)
    metar_match = re.search(r"\b[A-Z]{4}\s+\d{6}Z\b.*?(?=\bTAF\b|$)", normalized)
    taf_match = re.search(r"\bTAF\b.*$", normalized)
    if loc_match:
        values["loc"] = loc_match.group(0)
    if metar_match:
        values["metar"] = _compact_text(metar_match.group(0))
    if taf_match:
        values["taf"] = _compact_text(taf_match.group(0))
    return values


def parse_aisweb_met_response(raw_response: str | None) -> dict:
    text = (raw_response or "").strip()
    if not text:
        raise AiswebResponseError("Resposta AISWEB vazia.")

    if text.startswith("<"):
        values = _extract_tag_values_from_xml(text)
    else:
        values = _extract_tag_values_from_plain_text(text)

    if not values.get("metar") and text.startswith("<"):
        raise AiswebResponseError("METAR ausente na resposta AISWEB.")

    return {
        "loc": _compact_text(values.get("loc")),
        "metar": _compact_text(values.get("metar")),
        "taf": _compact_text(values.get("taf")),
    }


def _location_label(icao_code: str) -> str:
    return LOCATION_LABELS.get(icao_code, icao_code)


def _updated_at_label(updated_at: datetime | None, *, now: datetime) -> str:
    if updated_at is None:
        return "Dados n\u00e3o atualizados"
    elapsed_seconds = max(0, int((now - updated_at).total_seconds()))
    if elapsed_seconds < 45:
        return "Atualizado agora"
    elapsed_minutes = elapsed_seconds // 60
    if elapsed_minutes < 60:
        return f"Atualizado h\u00e1 {elapsed_minutes} min"
    elapsed_hours = elapsed_minutes // 60
    return f"Atualizado h\u00e1 {elapsed_hours} h"


def _base_payload(icao_code: str, *, now: datetime, status: str) -> dict:
    normalized_status = status if status in {"available", "stale", "unavailable", "error"} else "error"
    return {
        "icaoCode": icao_code,
        "locationLabel": _location_label(icao_code),
        "temperatureC": None,
        "windDirection": None,
        "windSpeedKt": None,
        "visibilityMeters": None,
        "condition": "UNKNOWN",
        "rawMetar": None,
        "rawTaf": None,
        "observedAt": None,
        "updatedAt": None,
        "updatedAtLabel": _updated_at_label(None, now=now),
        "source": "AISWEB",
        "status": normalized_status,
    }


def _with_dynamic_status(payload: dict, *, now: datetime, status: str | None = None) -> dict:
    next_payload = dict(payload)
    if status:
        next_payload["status"] = status
    updated_at_raw = next_payload.get("updatedAt")
    updated_at = None
    if updated_at_raw:
        try:
            updated_at = datetime.fromisoformat(str(updated_at_raw).replace("Z", "+00:00"))
        except ValueError:
            updated_at = None
    next_payload["updatedAtLabel"] = _updated_at_label(updated_at, now=now)
    return next_payload


def _available_payload(icao_code: str, parsed_response: dict, *, now: datetime) -> dict:
    metar = parsed_response.get("metar")
    taf = parsed_response.get("taf")
    parsed_metar = parse_metar(metar, now=now)
    response_icao = icao_code
    if parsed_response.get("loc"):
        try:
            response_icao = normalize_icao_code(parsed_response.get("loc"))
        except AiswebValidationError:
            response_icao = icao_code
    payload = _base_payload(icao_code, now=now, status="available")
    payload.update(
        {
            "icaoCode": response_icao,
            "locationLabel": _location_label(icao_code),
            "temperatureC": parsed_metar["temperatureC"],
            "windDirection": parsed_metar["windDirection"],
            "windSpeedKt": parsed_metar["windSpeedKt"],
            "visibilityMeters": parsed_metar["visibilityMeters"],
            "condition": parsed_metar["condition"],
            "rawMetar": metar,
            "rawTaf": taf,
            "observedAt": parsed_metar["observedAt"],
            "updatedAt": _iso_utc(now),
            "updatedAtLabel": _updated_at_label(now, now=now),
            "status": "available",
        }
    )
    return payload


def _cache_get(icao_code: str, *, now: datetime, allow_stale: bool = False) -> dict | None:
    with _CACHE_LOCK:
        entry = _MET_CACHE.get(icao_code)
        if not entry:
            return None
        is_fresh = entry.expires_at > now
        if not is_fresh and not allow_stale:
            return None
        return _with_dynamic_status(entry.payload, now=now, status="available" if is_fresh else "stale")


def _cache_set(icao_code: str, payload: dict, *, now: datetime, ttl_seconds: int) -> None:
    with _CACHE_LOCK:
        _MET_CACHE[icao_code] = _WeatherCacheEntry(
            payload=dict(payload),
            fetched_at=now,
            expires_at=datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc),
        )


def clear_aisweb_met_cache() -> None:
    with _CACHE_LOCK:
        _MET_CACHE.clear()


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


def get_aisweb_met(
    icao_code: str,
    *,
    now: datetime | None = None,
    fetcher: WeatherFetcher = fetch_aisweb_met,
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
        return _base_payload(normalized_icao, now=reference, status="unavailable")

    ttl_seconds = _env_int("AISWEB_MET_CACHE_TTL_SECONDS", 180, minimum=60, maximum=300)
    try:
        raw_response = fetcher(icao_code=normalized_icao, **config)
        parsed_response = parse_aisweb_met_response(raw_response)
        if not parsed_response.get("metar"):
            stale = _cache_get(normalized_icao, now=reference, allow_stale=True)
            if stale:
                return stale
            return _base_payload(normalized_icao, now=reference, status="unavailable")
        payload = _available_payload(normalized_icao, parsed_response, now=reference)
        _cache_set(normalized_icao, payload, now=reference, ttl_seconds=ttl_seconds)
        return payload
    except (AiswebClientError, AiswebResponseError, AiswebValidationError):
        stale = _cache_get(normalized_icao, now=reference, allow_stale=True)
        if stale:
            return stale
        return _base_payload(normalized_icao, now=reference, status="error")
