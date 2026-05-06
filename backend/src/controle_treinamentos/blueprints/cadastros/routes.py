from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ...application.tripulante_media import load_tripulante_photo_payload
from ...application.tripulantes import save_tripulante
from ...auth import permission_required
from ...constants import TRIPULANTE_CATEGORIA_OPTIONS, TRIPULANTE_FUNCAO_OPTIONS, TRIPULANTE_STATUS_OPTIONS
from ...core.domain_errors import DomainError
from ...core.file_access_policy import TRIPULANTE_PHOTO_ACCESS_POLICY, build_file_access_response
from ...core.frontend_routes import frontend_compat_enabled, redirect_to_frontend
from ...core.http_utils import (
    resolve_pagination_state,
)
from ...db import fetch_unique_bases, get_db
from ...repositories.queries import (
    fetch_base_options,
    fetch_upcoming_training_items_by_tripulante,
)
from ...repositories.tripulantes import (
    count_tripulantes,
    fetch_tripulante_for_write,
    fetch_tripulante_list_page,
)
from ...service_layers.form_builders import (
    build_tripulante_form_state,
)
from ...services import whatsapp_tripulante_link
from . import cadastros_bp


def _build_tripulante_photo_response(row, *, tripulante_id: int | None = None):
    payload = load_tripulante_photo_payload(dict(row or {}))
    if not payload:
        return None
    return build_file_access_response(
        policy=TRIPULANTE_PHOTO_ACCESS_POLICY,
        action="preview",
        payload_bytes=payload["payload_bytes"],
        mime_type=(payload.get("mime_type") or "").strip() or "image/jpeg",
        entity_id=tripulante_id,
        subject_id=tripulante_id,
        source="ssr.tripulante_photo"
        if payload.get("compat_residual") is not True
        else "ssr.tripulante_photo.legacy",
    )


def _merge_tripulante_photo_state(row):
    if not row:
        return None
    payload = dict(row)
    payload["possui_foto"] = bool(payload.get("possui_foto"))
    return payload


def _load_tripulante_for_form(db, tripulante_id: int):
    return _merge_tripulante_photo_state(fetch_tripulante_for_write(db, tripulante_id=tripulante_id))


def _tripulante_foto_url(tripulante_id: int | None, current_tripulante) -> str:
    if not tripulante_id or not current_tripulante or not current_tripulante.get("possui_foto"):
        return ""
    return url_for("cadastros.tripulante_foto", tripulante_id=tripulante_id)


def _render_tripulante_form_legacy(
    *,
    db,
    tripulante,
    status_code: int = 200,
    tripulante_id: int | None = None,
    current_tripulante=None,
):
    return render_template(
        "tripulantes_form.html",
        tripulante=tripulante,
        tripulante_foto_url=_tripulante_foto_url(tripulante_id, current_tripulante or tripulante),
        bases_options=fetch_base_options(db, (tripulante or {}).get("base") if tripulante else None),
        status_options=TRIPULANTE_STATUS_OPTIONS,
        funcoes_options=TRIPULANTE_FUNCAO_OPTIONS,
        categorias_options=TRIPULANTE_CATEGORIA_OPTIONS,
    ), status_code


def _handle_tripulante_form_error(
    exc: DomainError,
    *,
    db,
    state,
    tripulante_id: int | None = None,
    current_tripulante=None,
):
    flash(exc.message, "error")
    status_code = 400 if exc.status in {400, 409} else exc.status
    return _render_tripulante_form_legacy(
        db=db,
        tripulante=state,
        status_code=status_code,
        tripulante_id=tripulante_id,
        current_tripulante=current_tripulante,
    )


@cadastros_bp.route("/tripulantes")
@login_required
def tripulantes_list():
    if frontend_compat_enabled():
        return redirect_to_frontend(
            "#/tripulantes",
            query={
                "nome": request.args.get("nome", "").strip(),
                "status": request.args.get("status", "").strip(),
                "base": request.args.get("base", "").strip(),
                "funcao": request.args.get("funcao", "").strip(),
                "categoria": request.args.get("categoria", "").strip(),
                "ativo": request.args.get("ativo", "").strip(),
            },
        )
    db = get_db()
    nome = request.args.get("nome", "").strip()
    status = request.args.get("status", "").strip()
    base = request.args.get("base", "").strip()
    funcao = request.args.get("funcao", "").strip()
    categoria = request.args.get("categoria", "").strip()
    ativo = request.args.get("ativo", "").strip()

    total = count_tripulantes(
        db,
        nome=nome,
        status=status,
        base=base,
        funcao=funcao,
        categoria=categoria,
        ativo=ativo,
    )
    paging = resolve_pagination_state(
        total,
        endpoint="cadastros.tripulantes_list",
        nome=nome,
        status=status,
        base=base,
        funcao=funcao,
        categoria=categoria,
        ativo=ativo,
    )
    tripulantes = fetch_tripulante_list_page(
        db,
        nome=nome,
        status=status,
        base=base,
        funcao=funcao,
        categoria=categoria,
        ativo=ativo,
        limit=paging["per_page"],
        offset=paging["offset"],
    )
    db = get_db()
    upcoming_by_tripulante = fetch_upcoming_training_items_by_tripulante(db, [row["id"] for row in tripulantes])
    tripulantes_view = []
    for row in tripulantes:
        item = dict(row)
        item["whatsapp_url"] = whatsapp_tripulante_link(
            row["nome"],
            row["telefone"],
            upcoming_by_tripulante.get(row["id"], []),
        )
        tripulantes_view.append(item)
    bases = fetch_unique_bases(db)
    return render_template(
        "tripulantes_list.html",
        tripulantes=tripulantes_view,
        filtros={"nome": nome, "status": status, "base": base, "funcao": funcao, "categoria": categoria, "ativo": ativo},
        bases=[row["nome"] for row in bases],
        statuses=TRIPULANTE_STATUS_OPTIONS,
        funcoes=TRIPULANTE_FUNCAO_OPTIONS,
        categorias=TRIPULANTE_CATEGORIA_OPTIONS,
        pagination=paging["pagination"],
    )


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/foto")
@permission_required("tripulantes:view", "relatorio_individual:view")
def tripulante_foto(tripulante_id):
    db = get_db()
    row = db.execute(
        "SELECT foto_base64, foto_storage_ref, foto_mime_type FROM tripulantes WHERE id = %s",
        (tripulante_id,),
    ).fetchone()
    if not row:
        abort(404)
    response = _build_tripulante_photo_response(row, tripulante_id=tripulante_id)
    if not response:
        abort(404)
    return response


@cadastros_bp.route("/tripulantes/novo", methods=["GET", "POST"])
@permission_required("tripulantes:create")
def tripulantes_new():
    if request.method == "GET" and frontend_compat_enabled():
        return redirect_to_frontend("#/tripulantes/new")
    db = get_db()
    if request.method == "POST":
        tripulante_state = build_tripulante_form_state(request.form)
        try:
            result = save_tripulante(request.form)
        except DomainError as exc:
            return _handle_tripulante_form_error(exc, db=get_db(), state=tripulante_state)
        flash("Tripulante cadastrado com sucesso." if result["operation"] == "created" else "Tripulante salvo com sucesso.", "success")
        return redirect(url_for("cadastros.tripulantes_list"))
    return _render_tripulante_form_legacy(db=db, tripulante=None)


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/editar", methods=["GET", "POST"])
@permission_required("tripulantes:edit")
def tripulantes_edit(tripulante_id):
    if request.method == "GET" and frontend_compat_enabled():
        return redirect_to_frontend(f"#/tripulantes/{tripulante_id}")
    db = get_db()
    tripulante = _load_tripulante_for_form(db, tripulante_id)
    if not tripulante:
        abort(404)
    if request.method == "POST":
        tripulante_state = build_tripulante_form_state(request.form)
        try:
            result = save_tripulante(request.form, tripulante_id=tripulante_id)
        except DomainError as exc:
            return _handle_tripulante_form_error(
                exc,
                db=get_db(),
                state=tripulante_state,
                tripulante_id=tripulante_id,
                current_tripulante=tripulante,
            )
        flash("Tripulante atualizado com sucesso." if result["operation"] == "updated" else "Tripulante salvo com sucesso.", "success")
        return redirect(url_for("cadastros.tripulantes_list"))
    return _render_tripulante_form_legacy(
        db=db,
        tripulante=tripulante,
        tripulante_id=tripulante_id,
        current_tripulante=tripulante,
    )
