from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...application.operacoes import (
    create_pernoite,
    delete_pernoite_use_case,
    update_pernoite_use_case,
)
from ...auth import permission_required
from ...constants import PERNOITE_TIPO_OPTIONS
from ...core.domain_errors import DomainError
from ...core.http_utils import resolve_pagination_state
from ...db import get_db
from ...repositories.dashboard_cache import fetch_cached_rows
from ...service_layers.form_builders import build_pernoite_form_state
from ...service_layers.form_options import get_pernoite_form_options
from . import operacoes_bp


def _render_pernoite_form_legacy(pernoite=None, *, options: dict):
    return render_template(
        "pernoites_form.html",
        pernoite=dict(pernoite) if pernoite else None,
        tripulantes=options.get("tripulantes", []),
        tipo_options=options.get("tipo_options", PERNOITE_TIPO_OPTIONS),
    )


def _pernoite_compat_payload_from_request() -> dict:
    return request.form.to_dict(flat=True)


def _handle_domain_form_error(exc: DomainError, *, template_renderer, state, options):
    flash(exc.message, "error")
    return template_renderer(state, options=options), exc.status


@operacoes_bp.route("/pernoites")
@login_required
def pernoites_list():
    db = get_db()
    tipo = request.args.get("tipo", "").strip()
    tripulante = request.args.get("tripulante", "").strip()
    clauses = []
    params = []
    if tipo in PERNOITE_TIPO_OPTIONS:
        clauses.append("p.tipo_pernoite = %s")
        params.append(tipo)
    if tripulante.isdigit():
        clauses.append("p.tripulante_id = %s")
        params.append(int(tripulante))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = db.execute(
        f"SELECT COUNT(*) AS total FROM pernoites_operacionais p {where}",
        tuple(params),
    ).fetchone()["total"]
    paging = resolve_pagination_state(
        total,
        endpoint="operacoes.pernoites_list",
        tipo=tipo,
        tripulante=tripulante,
    )
    rows = db.execute(
        f"""
        SELECT p.*, c.nome AS tripulante_nome
        FROM pernoites_operacionais p
        JOIN tripulantes c ON c.id = p.tripulante_id
        {where}
        ORDER BY p.data_pernoite DESC, p.id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, paging["per_page"], paging["offset"]),
    ).fetchall()
    return render_template(
        "pernoites_list.html",
        pernoites=rows,
        filtros={"tipo": tipo, "tripulante": tripulante},
        tripulantes=fetch_cached_rows(
            db,
            cache_key="options:tripulantes:id_nome",
            query="SELECT id, nome FROM tripulantes ORDER BY nome",
        ),
        tipo_options=PERNOITE_TIPO_OPTIONS,
        pagination=paging["pagination"],
    )


@operacoes_bp.route("/pernoites/novo", methods=["GET", "POST"])
@permission_required("pernoites:create")
def pernoites_new():
    db = get_db()
    if request.method == "POST":
        state = build_pernoite_form_state(request.form)
        try:
            result = create_pernoite(_pernoite_compat_payload_from_request(), actor_user_id=int(current_user.id))
        except DomainError as exc:
            opts = get_pernoite_form_options(get_db())
            return _handle_domain_form_error(exc, template_renderer=_render_pernoite_form_legacy, state=state, options=opts)
        flash(result["message"], "success")
        return redirect(url_for("operacoes.pernoites_list"))
    opts = get_pernoite_form_options(db)
    return _render_pernoite_form_legacy(pernoite=None, options=opts)


@operacoes_bp.route("/pernoites/<int:pernoite_id>/editar", methods=["GET", "POST"])
@permission_required("pernoites:edit")
def pernoites_edit(pernoite_id):
    db = get_db()
    pernoite = db.execute("SELECT * FROM pernoites_operacionais WHERE id = %s", (pernoite_id,)).fetchone()
    if not pernoite:
        abort(404)
    if request.method == "POST":
        state = build_pernoite_form_state(request.form)
        state["id"] = pernoite_id
        try:
            result = update_pernoite_use_case(
                pernoite_id,
                _pernoite_compat_payload_from_request(),
                actor_user_id=int(current_user.id),
            )
        except DomainError as exc:
            opts = get_pernoite_form_options(get_db())
            return _handle_domain_form_error(exc, template_renderer=_render_pernoite_form_legacy, state=state, options=opts)
        flash(result["message"], "success")
        return redirect(url_for("operacoes.pernoites_list"))
    opts = get_pernoite_form_options(db)
    return _render_pernoite_form_legacy(pernoite=pernoite, options=opts)


@operacoes_bp.route("/pernoites/<int:pernoite_id>/excluir", methods=["POST"])
@permission_required("pernoites:delete")
def pernoites_delete(pernoite_id):
    try:
        result = delete_pernoite_use_case(pernoite_id, actor_user_id=int(current_user.id))
    except DomainError as exc:
        flash(exc.message, "error")
        return redirect(url_for("operacoes.pernoites_list"))
    flash(result["message"], "success")
    return redirect(url_for("operacoes.pernoites_list"))
