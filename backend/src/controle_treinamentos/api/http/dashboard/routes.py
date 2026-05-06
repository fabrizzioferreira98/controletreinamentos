from __future__ import annotations

from flask import request

from ....application.aisweb_weather import (
    AiswebValidationError,
    get_aisweb_met,
    normalize_icao_code,
)
from ....application.dashboard import (
    get_dashboard_calendar_data,
    get_dashboard_critical_trainings_data,
    get_dashboard_summary_data,
)
from ....application.operational_dashboard import (
    build_dashboard_operational_alerts,
    build_dashboard_relevant_notams,
    build_dashboard_weather_by_base,
)
from ....auth import permission_required
from ....blueprints.bases.routes import build_bases_api_payload
from ....blueprints.dashboard import dashboard_bp
from ....contracts.bases import parse_bases_status_filter
from ....core.http_utils import error_payload
from ....core.utils import json_response_with_etag
from ....db import get_db


@dashboard_bp.route("/api/v1/dashboard/summary", methods=["GET"])
@permission_required("dashboard:view")
def api_dashboard_summary():
    payload = get_dashboard_summary_data(get_db())
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "dashboard_summary_ok",
            "dashboard": payload,
        },
        max_age=15,
    )


@dashboard_bp.route("/api/v1/dashboard/calendar", methods=["GET"])
@permission_required("dashboard:view")
def api_dashboard_calendar():
    payload = get_dashboard_calendar_data(get_db())
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "dashboard_calendar_ok",
            "calendar": payload,
        },
        max_age=15,
    )


@dashboard_bp.route("/api/v1/dashboard/critical-trainings", methods=["GET"])
@permission_required("dashboard:view")
def api_dashboard_critical_trainings():
    limit = request.args.get("limit", default=8, type=int) or 8
    payload = get_dashboard_critical_trainings_data(get_db(), limit=max(1, min(20, limit)))
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "dashboard_critical_trainings_ok",
            "critical_trainings": payload,
        },
        max_age=15,
    )


@dashboard_bp.route("/api/v1/dashboard/base-operations", methods=["GET"])
@permission_required("dashboard:view")
def api_dashboard_base_operations():
    status_filter = parse_bases_status_filter(request.args)
    return json_response_with_etag(build_bases_api_payload(status_filter=status_filter), max_age=15)


@dashboard_bp.route("/api/v1/dashboard/weather-by-base", methods=["GET"])
@permission_required("dashboard:view")
def api_dashboard_weather_by_base():
    payload = build_dashboard_weather_by_base()
    code_map = {
        "available": "dashboard_weather_by_base_ok",
        "degraded": "dashboard_weather_by_base_degraded",
        "unavailable": "dashboard_weather_by_base_unavailable",
        "error": "dashboard_weather_by_base_error",
    }
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": code_map.get(payload.get("status"), "dashboard_weather_by_base_error"),
            "weather_by_base": payload,
        },
        max_age=30,
    )


@dashboard_bp.route("/api/v1/dashboard/notams", methods=["GET"])
@permission_required("dashboard:view")
def api_dashboard_relevant_notams():
    payload = build_dashboard_relevant_notams()
    code_map = {
        "available": "dashboard_notams_ok",
        "degraded": "dashboard_notams_degraded",
        "empty": "dashboard_notams_empty",
        "unavailable": "dashboard_notams_unavailable",
        "error": "dashboard_notams_error",
    }
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": code_map.get(payload.get("status"), "dashboard_notams_error"),
            "notams": payload,
        },
        max_age=30,
    )


@dashboard_bp.route("/api/v1/dashboard/operational-alerts", methods=["GET"])
@permission_required("dashboard:view")
def api_dashboard_operational_alerts():
    summary_payload = get_dashboard_summary_data(get_db())
    base_payload = build_bases_api_payload()
    notams_payload = build_dashboard_relevant_notams()
    payload = build_dashboard_operational_alerts(
        summary_data=summary_payload,
        base_operations=base_payload,
        notams=notams_payload,
    )
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "dashboard_operational_alerts_ok",
            "operational_alerts": payload,
        },
        max_age=15,
    )


@dashboard_bp.route("/api/aisweb/met", methods=["GET"])
@dashboard_bp.route("/api/v1/aisweb/met", methods=["GET"])
@permission_required("dashboard:view")
def api_aisweb_met():
    raw_icao_code = (request.args.get("icaoCode") or request.args.get("icao_code") or "").strip()
    if not raw_icao_code:
        return error_payload(
            "icaoCode e obrigatorio.",
            status=400,
            code="aisweb_met_icao_required",
        )
    try:
        icao_code = normalize_icao_code(raw_icao_code)
    except AiswebValidationError:
        return error_payload(
            "icaoCode invalido. Use quatro letras ICAO.",
            status=400,
            code="aisweb_met_invalid_icao",
        )

    payload = get_aisweb_met(icao_code)
    status_code_map = {
        "available": "aisweb_met_ok",
        "stale": "aisweb_met_stale",
        "unavailable": "aisweb_met_unavailable",
        "error": "aisweb_met_error",
    }
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": status_code_map.get(payload.get("status"), "aisweb_met_error"),
            "weather": payload,
        },
        max_age=30,
    )
