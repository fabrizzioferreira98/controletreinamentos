from flask import redirect, render_template, url_for
from flask_login import current_user, login_required

from ...core.frontend_routes import (
    frontend_compat_enabled,
    frontend_official_enabled,
    redirect_to_frontend,
    redirect_to_frontend_app,
)
from ...db import get_db
from ...repositories.dashboard_cache import (
    build_dashboard_context,
    get_dashboard_cache,
    set_dashboard_cache,
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
                item["training_url"] = f"/#/treinamentos/{item['training_id']}"
                item["tripulante_url"] = f"/#/tripulantes/{item['tripulante_id']}"
    for item in context.get("calendar", {}).get("upcoming_rows", []):
        item["training_url"] = f"/#/treinamentos/{item['training_id']}"
        item["tripulante_url"] = f"/#/tripulantes/{item['tripulante_id']}"

    set_dashboard_cache(context)
    return render_template("dashboard.html", **context)
