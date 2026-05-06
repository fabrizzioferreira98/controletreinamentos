from __future__ import annotations

from datetime import datetime, timezone

from .aisweb_notams import get_aisweb_notams
from .aisweb_weather import get_aisweb_met

DASHBOARD_OPERATIONAL_BASES = (
    {"icaoCode": "SBGO", "locationLabel": "Goi\u00e2nia"},
    {"icaoCode": "SBSP", "locationLabel": "S\u00e3o Paulo"},
    {"icaoCode": "SBPJ", "locationLabel": "Palmas"},
    {"icaoCode": "SBSV", "locationLabel": "Salvador"},
    {"icaoCode": "SBEG", "locationLabel": "Manaus"},
    {"icaoCode": "SBBE", "locationLabel": "Bel\u00e9m"},
    {"icaoCode": "SBSN", "locationLabel": "Santar\u00e9m"},
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _collection_status(items: list[dict]) -> str:
    if not items:
        return "unavailable"
    statuses = {str(item.get("status") or "error").lower() for item in items}
    if statuses <= {"available", "stale"}:
        return "available" if statuses == {"available"} else "degraded"
    if statuses & {"available", "stale"}:
        return "degraded"
    if "unavailable" in statuses:
        return "unavailable"
    return "error"


def _weather_severity(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized == "available":
        return "normal"
    if normalized == "stale":
        return "attention"
    if normalized == "error":
        return "critical"
    return "unknown"


def build_dashboard_weather_by_base(*, fetcher=get_aisweb_met, now: datetime | None = None) -> dict:
    reference = (now or _utc_now()).astimezone(timezone.utc)
    items: list[dict] = []
    errors: list[dict] = []
    for base in DASHBOARD_OPERATIONAL_BASES:
        icao_code = base["icaoCode"]
        try:
            payload = dict(fetcher(icao_code) or {})
        except Exception as exc:  # noqa: BLE001 - isolate one base without fabricating weather data.
            payload = {
                "icaoCode": icao_code,
                "locationLabel": base["locationLabel"],
                "temperatureC": None,
                "windDirection": None,
                "windSpeedKt": None,
                "visibilityMeters": None,
                "condition": "UNKNOWN",
                "rawMetar": None,
                "rawTaf": None,
                "observedAt": None,
                "updatedAt": None,
                "updatedAtLabel": "\u00daltima atualiza\u00e7\u00e3o indispon\u00edvel",
                "source": "AISWEB",
                "status": "error",
            }
            errors.append(
                {
                    "icaoCode": icao_code,
                    "code": "dashboard_weather_base_error",
                    "message": str(exc) or "Falha ao carregar meteorologia da base.",
                }
            )
        payload.setdefault("icaoCode", icao_code)
        payload.setdefault("locationLabel", base["locationLabel"])
        payload.setdefault("source", "AISWEB")
        payload.setdefault("status", "error")
        payload["severity"] = _weather_severity(str(payload.get("status") or "error"))
        items.append(payload)

    status = _collection_status(items)
    return {
        "status": status,
        "source": "AISWEB",
        "updatedAt": _iso_utc(reference),
        "updatedAtLabel": "Atualizado agora" if status in {"available", "degraded"} else "\u00daltima atualiza\u00e7\u00e3o indispon\u00edvel",
        "items": items,
        "errors": errors,
    }


def _notam_sort_key(item: dict) -> tuple[int, str]:
    rank = {"critical": 0, "warning": 1, "attention": 2, "info": 3}
    severity = str(item.get("severity") or "info").lower()
    updated_at = str(item.get("updatedAt") or "")
    return (rank.get(severity, 3), updated_at)


def _notam_collection_status(collections: list[dict], items: list[dict]) -> str:
    statuses = {str(collection.get("status") or "error").lower() for collection in collections}
    if items:
        return "available" if statuses <= {"available", "empty", "stale"} else "degraded"
    if statuses and statuses <= {"available", "empty", "stale"}:
        return "empty"
    if "unavailable" in statuses:
        return "unavailable"
    return "error"


def build_dashboard_relevant_notams(
    *,
    now: datetime | None = None,
    fetcher=get_aisweb_notams,
    limit: int = 8,
) -> dict:
    reference = (now or _utc_now()).astimezone(timezone.utc)
    collections: list[dict] = []
    items_by_id: dict[str, dict] = {}
    errors: list[dict] = []

    for base in DASHBOARD_OPERATIONAL_BASES:
        icao_code = base["icaoCode"]
        try:
            collection = dict(fetcher(icao_code) or {})
        except Exception as exc:  # noqa: BLE001 - isolate one base without fabricating NOTAM.
            collection = {
                "status": "error",
                "source": "AISWEB",
                "updatedAt": _iso_utc(reference),
                "updatedAtLabel": "\u00daltima atualiza\u00e7\u00e3o indispon\u00edvel",
                "message": "Falha ao consultar NOTAM real na AISWEB.",
                "items": [],
            }
            errors.append(
                {
                    "icaoCode": icao_code,
                    "code": "dashboard_notams_base_error",
                    "message": str(exc) or "Falha ao carregar NOTAMs da base.",
                }
            )
        collections.append(collection)
        for item in collection.get("items") or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or item.get("notamId") or item.get("number") or "").strip()
            if not item_id:
                continue
            items_by_id.setdefault(item_id, item)

    items = sorted(items_by_id.values(), key=_notam_sort_key)[: max(1, int(limit or 8))]
    status = _notam_collection_status(collections, items)
    source = "AISWEB" if any(str(collection.get("source") or "").upper() == "AISWEB" for collection in collections) else "not_configured"
    message = ""
    if status == "empty":
        message = "Nenhum NOTAM relevante retornado pela AISWEB para as bases monitoradas."
    elif status in {"unavailable", "error"}:
        message = "Integra\u00e7\u00e3o real de NOTAM indispon\u00edvel."
    elif status == "degraded":
        message = "NOTAMs carregados parcialmente pela AISWEB."
    return {
        "status": status,
        "source": source,
        "updatedAt": _iso_utc(reference),
        "updatedAtLabel": "Atualizado agora" if status in {"available", "degraded", "empty"} else "\u00daltima atualiza\u00e7\u00e3o indispon\u00edvel",
        "message": message,
        "items": items,
        "errors": errors,
    }


def _alert_item(alert_id: str, *, severity: str, label: str, message: str, source: str) -> dict:
    return {
        "id": alert_id,
        "severity": severity,
        "label": label,
        "message": message,
        "source": source,
    }


def build_dashboard_operational_alerts(
    *,
    summary_data: dict,
    base_operations: dict,
    notams: dict | None = None,
) -> dict:
    alerts = summary_data.get("alerts") if isinstance(summary_data, dict) else {}
    summary = summary_data.get("summary") if isinstance(summary_data, dict) else {}
    items: list[dict] = []

    due_today = _as_int((alerts or {}).get("vencem_hoje"))
    expired = _as_int((alerts or {}).get("vencidos") or (summary or {}).get("vencido"))
    due_7 = _as_int((alerts or {}).get("em_7_dias"))
    missing_info = _as_int((summary or {}).get("sem_informacao"))

    if due_today:
        items.append(
            _alert_item(
                "training-due-today",
                severity="critical",
                label="Vencem hoje",
                message=f"{due_today} treinamento(s) vencem hoje.",
                source="dashboard_summary",
            )
        )
    if expired:
        items.append(
            _alert_item(
                "training-expired",
                severity="critical",
                label="Vencidos",
                message=f"{expired} treinamento(s) vencido(s).",
                source="dashboard_summary",
            )
        )
    if due_7:
        items.append(
            _alert_item(
                "training-due-7-days",
                severity="warning",
                label="Pr\u00f3ximos 7 dias",
                message=f"{due_7} treinamento(s) vencem em at\u00e9 7 dias.",
                source="dashboard_summary",
            )
        )
    if missing_info:
        items.append(
            _alert_item(
                "training-missing-info",
                severity="attention",
                label="Cadastro incompleto",
                message=f"{missing_info} registro(s) sem informa\u00e7\u00e3o de vencimento.",
                source="dashboard_summary",
            )
        )

    bases = base_operations.get("bases") if isinstance(base_operations, dict) else []
    inactive_bases = sum(1 for base in bases or [] if not bool(base.get("ativa", True)))
    if inactive_bases:
        items.append(
            _alert_item(
                "inactive-bases",
                severity="warning",
                label="Bases inativas",
                message=f"{inactive_bases} base(s) operacional(is) inativa(s).",
                source="dashboard_base_operations",
            )
        )

    if isinstance(notams, dict) and notams.get("status") in {"unavailable", "error"}:
        items.append(
            _alert_item(
                "notams-unavailable",
                severity="warning",
                label="NOTAMs",
                message="NOTAMs indispon\u00edveis: fonte real n\u00e3o configurada.",
                source="dashboard_notams",
            )
        )

    status = "available"
    return {
        "status": status,
        "source": "dashboard_operational_contracts",
        "items": items,
        "updatedAt": _iso_utc(_utc_now()),
        "message": "Sem alertas operacionais no momento." if not items else "",
    }
