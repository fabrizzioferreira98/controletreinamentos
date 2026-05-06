from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...core.frontend_routes import frontend_compat_enabled, frontend_official_enabled, redirect_to_frontend, redirect_to_frontend_app
from ...core.http_contract import programmatic_json
from ...core.utils import json_response_with_etag
from ...db import get_db
from ...repositories.dashboard_cache import (
    _build_panel_tv_payload,
    _safe_refresh_seconds,
    build_dashboard_context,
    get_dashboard_cache,
    get_panel_cache,
    set_dashboard_cache,
    set_panel_cache,
)
from . import dashboard_bp


@dashboard_bp.route("/")
def home():
    if frontend_official_enabled():
        return redirect_to_frontend_app()
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))
    return redirect(url_for("auth.login"))


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    if frontend_compat_enabled():
        return redirect_to_frontend("#/dashboard")
    cached = get_dashboard_cache()
    if cached is not None:
        return render_template("dashboard.html", **cached)
    db = get_db()
    context = build_dashboard_context(db)

    # Injetando rotas na camada de Apresentação (Desacoplando o Repositório do HTTP Context)
    for week in context.get("calendar", {}).get("weeks", []):
        for day in week:
            for item in day.get("items", []):
                item["training_url"] = url_for("cadastros.treinamentos_edit", treinamento_id=item["training_id"])
                item["tripulante_url"] = url_for("cadastros.tripulante_report", tripulante_id=item["tripulante_id"])
    for item in context.get("calendar", {}).get("upcoming_rows", []):
        item["training_url"] = url_for("cadastros.treinamentos_edit", treinamento_id=item["training_id"])
        item["tripulante_url"] = url_for("cadastros.tripulante_report", tripulante_id=item["tripulante_id"])

    set_dashboard_cache(context)
    return render_template("dashboard.html", **context)


@dashboard_bp.route("/painel-tv")
@login_required
def painel_tv():
    base_filter = request.args.get("base", "").strip()
    refresh_seconds = _safe_refresh_seconds(request.args.get("refresh"), default=60)
    cache_key = f"vencimentos:{base_filter}"
    payload = get_panel_cache(cache_key)
    if payload is None:
        db = get_db()
        payload = _build_panel_tv_payload(db, base_filter=base_filter)
        set_panel_cache(cache_key, payload)
    return render_template(
        "painel_tv.html",
        initial_payload=payload,
        refresh_seconds=refresh_seconds,
        base_filter=base_filter,
    )


@dashboard_bp.route("/painel-tv/dados")
@login_required
@programmatic_json
def painel_tv_dados():
    db = get_db()
    base_filter = request.args.get("base", "").strip()
    cache_key = f"vencimentos:{base_filter}"
    cached = get_panel_cache(cache_key)
    if cached is not None:
        return json_response_with_etag(cached, max_age=15)
    payload = _build_panel_tv_payload(db, base_filter=base_filter)
    set_panel_cache(cache_key, payload)
    return json_response_with_etag(payload, max_age=15)
