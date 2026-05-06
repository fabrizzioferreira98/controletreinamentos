from __future__ import annotations

from flask import request

from ....application.dashboard import (
    get_dashboard_calendar_data,
    get_dashboard_critical_trainings_data,
    get_dashboard_summary_data,
    get_tv_produtividade_data,
    get_tv_vencimentos_data,
)
from ....auth import permission_required
from ....blueprints.dashboard import dashboard_bp
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


@dashboard_bp.route("/api/v1/tv/vencimentos", methods=["GET"])
@permission_required("tv_vencimentos:view")
def api_tv_vencimentos():
    payload = get_tv_vencimentos_data(get_db(), base_filter=request.args.get("base", "").strip())
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "tv_vencimentos_ok",
            "panel": payload,
        },
        max_age=15,
    )


@dashboard_bp.route("/api/v1/tv/produtividade", methods=["GET"])
@permission_required("tv_produtividade:view")
def api_tv_produtividade():
    payload = get_tv_produtividade_data(get_db(), competencia=request.args.get("competencia", "").strip())
    return json_response_with_etag(
        {
            "success": True,
            "status": 200,
            "code": "tv_produtividade_ok",
            "panel": payload,
        },
        max_age=20,
    )
