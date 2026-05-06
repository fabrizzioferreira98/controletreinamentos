import base64
import binascii
import re

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import Response, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ...auth import permission_required
from ...constants import TRIPULANTE_CATEGORIA_OPTIONS, TRIPULANTE_FUNCAO_OPTIONS, TRIPULANTE_STATUS_OPTIONS
from ...core.audit_utils import audit_event, rollback_db, tripulante_audit_payload
from ...core.frontend_routes import frontend_compat_enabled, redirect_to_frontend
from ...core.http_utils import (
    get_optional_email,
    get_optional_limited_text,
    get_required_text,
    get_validated_anac_code,
    get_validated_cpf,
    resolve_pagination_state,
    sanitize_photo_base64,
)
from ...core.utils import format_competencia_label
from ...db import ensure_base_exists, fetch_unique_bases, get_db
from ...infra.media_storage import delete_media_ref, read_media_bytes, write_tripulante_photo
from ...repositories.dashboard_cache import (
    clear_panel_cache,
)
from ...repositories.queries import (
    fetch_base_options,
    fetch_upcoming_training_items_by_tripulante,
    find_tripulante_by_cpf,
)
from ...service_layers.domain_validation import (
    sync_linked_pilot_from_tripulante,
    tripulante_status_filter_values,
    validate_tripulante_categoria,
    validate_tripulante_funcao,
    validate_tripulante_status,
)
from ...service_layers.form_builders import (
    build_tripulante_form_state,
)
from ...services import whatsapp_tripulante_link
from . import cadastros_bp

_PHOTO_DATA_URI_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,", re.IGNORECASE)
_KEEP_EXISTING_PHOTO = object()
_REMOVE_PHOTO = object()


def _decode_photo_data_uri(raw_value: str):
    foto_base64 = (raw_value or "").strip()
    match = _PHOTO_DATA_URI_RE.match(foto_base64)
    if not match:
        return None
    image_format = match.group(1).lower()
    mime_type = "image/jpeg" if image_format in {"jpg", "jpeg"} else f"image/{image_format}"
    try:
        raw = base64.b64decode(foto_base64.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error):
        return None
    return raw, mime_type


def _resolve_photo_form_value(form):
    if form.get("remove_foto", "").strip() == "1":
        return _REMOVE_PHOTO
    raw_value = (form.get("foto_base64", "") or "").strip()
    if not raw_value:
        return _KEEP_EXISTING_PHOTO
    return sanitize_photo_base64(form, current_value="")


def _build_tripulante_photo_response(row):
    payload_bytes = read_media_bytes(
        row.get("foto_storage_ref"),
        fallback_bytes=None,
    )
    if payload_bytes:
        mime_type = (row.get("foto_mime_type") or "").strip() or "image/jpeg"
        response = Response(payload_bytes, mimetype=mime_type)
        response.headers["Cache-Control"] = "private, max-age=300"
        return response

    if not row.get("foto_base64"):
        return None
    decoded = _decode_photo_data_uri(row["foto_base64"])
    if not decoded:
        return None
    raw, mime_type = decoded
    response = Response(raw, mimetype=mime_type)
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


def _persist_tripulante_photo(*, tripulante_id: int, tripulante_name: str, submitted_value, existing_row):
    if submitted_value is _KEEP_EXISTING_PHOTO:
        return {
            "foto_base64": existing_row.get("foto_base64"),
            "foto_storage_ref": existing_row.get("foto_storage_ref"),
            "foto_mime_type": existing_row.get("foto_mime_type"),
            "possui_foto": bool(existing_row.get("possui_foto")),
            "new_storage_ref": None,
            "old_storage_ref_to_delete": None,
        }

    if submitted_value is _REMOVE_PHOTO:
        return {
            "foto_base64": None,
            "foto_storage_ref": None,
            "foto_mime_type": None,
            "possui_foto": False,
            "new_storage_ref": None,
            "old_storage_ref_to_delete": existing_row.get("foto_storage_ref"),
        }

    decoded = _decode_photo_data_uri(submitted_value)
    if not decoded:
        raise ValueError("A foto enviada estÃ¡ invÃ¡lida.")
    raw_bytes, mime_type = decoded
    new_storage_ref = write_tripulante_photo(tripulante_id, tripulante_name, raw_bytes, mime_type=mime_type)
    return {
        "foto_base64": None,
        "foto_storage_ref": new_storage_ref,
        "foto_mime_type": mime_type,
        "possui_foto": True,
        "new_storage_ref": new_storage_ref,
        "old_storage_ref_to_delete": existing_row.get("foto_storage_ref"),
    }


def _merge_tripulante_photo_state(row):
    if not row:
        return None
    payload = dict(row)
    payload["possui_foto"] = bool(
        str(payload.get("foto_base64") or "").strip() or str(payload.get("foto_storage_ref") or "").strip()
    )
    return payload


def _load_tripulante_for_form(db, tripulante_id: int):
    row = db.execute(
        "SELECT * FROM tripulantes WHERE id = %s",
        (tripulante_id,),
    ).fetchone()
    return _merge_tripulante_photo_state(row)


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

    clauses = []
    params = []
    if nome:
        clauses.append("nome LIKE %s")
        params.append(f"%{nome}%")
    if status:
        status_values = tripulante_status_filter_values(status)
        if len(status_values) == 1:
            clauses.append("status = %s")
            params.append(status_values[0])
        elif len(status_values) > 1:
            clauses.append("status = ANY(%s)")
            params.append(list(status_values))
        else:
            clauses.append("status = %s")
            params.append(status)
    if base:
        clauses.append("base = %s")
        params.append(base)
    if funcao in TRIPULANTE_FUNCAO_OPTIONS:
        clauses.append("funcao_operacional = %s")
        params.append(funcao)
    if categoria in TRIPULANTE_CATEGORIA_OPTIONS:
        clauses.append("categoria_operacional = %s")
        params.append(categoria)
    if ativo in {"1", "0"}:
        clauses.append("ativo = %s")
        params.append(int(ativo))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = db.execute(
        f"SELECT COUNT(*) AS total FROM tripulantes {where}",
        params,
    ).fetchone()["total"]
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
    tripulantes = db.execute(
        f"""
        SELECT
            id,
            nome,
            cpf,
            licenca_anac,
            email,
            telefone,
            base,
            status,
            ativo,
            funcao_operacional,
            categoria_operacional,
            sdea_ativo,
            instrutor_ativo,
            checador_ativo,
            elegivel_adicional_excepcional,
            COALESCE(
                (
                    (foto_base64 IS NOT NULL AND TRIM(foto_base64) <> '')
                    OR (foto_storage_ref IS NOT NULL AND TRIM(foto_storage_ref) <> '')
                ),
                FALSE
            ) AS possui_foto
        FROM tripulantes
        {where}
        ORDER BY nome
        LIMIT %s OFFSET %s
        """,
        (*params, paging["per_page"], paging["offset"]),
    ).fetchall()
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
@permission_required("tripulantes:view")
def tripulante_foto(tripulante_id):
    db = get_db()
    row = db.execute(
        "SELECT foto_base64, foto_storage_ref, foto_mime_type FROM tripulantes WHERE id = %s",
        (tripulante_id,),
    ).fetchone()
    if not row:
        abort(404)
    response = _build_tripulante_photo_response(row)
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
        new_photo_storage_ref = None
        try:
            nome = get_required_text(request.form, "nome", "Nome")
            cpf = get_validated_cpf(request.form)
            licenca_anac = get_validated_anac_code(request.form)
            email = get_optional_email(request.form, "email", "E-mail")
            telefone = get_optional_limited_text(request.form, "telefone", "Telefone")
            base = get_required_text(request.form, "base", "Base")
            status = validate_tripulante_status(get_required_text(request.form, "status", "Status"))
            funcao_operacional = validate_tripulante_funcao(get_required_text(request.form, "funcao_operacional", "Função operacional"))
            categoria_operacional = validate_tripulante_categoria(get_required_text(request.form, "categoria_operacional", "Categoria operacional"))
            submitted_photo = _resolve_photo_form_value(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template(
                "tripulantes_form.html",
                tripulante=tripulante_state,
                tripulante_foto_url="",
                bases_options=fetch_base_options(db, tripulante_state.get("base")),
                status_options=TRIPULANTE_STATUS_OPTIONS,
                funcoes_options=TRIPULANTE_FUNCAO_OPTIONS,
                categorias_options=TRIPULANTE_CATEGORIA_OPTIONS,
            ), 400
        duplicate = find_tripulante_by_cpf(db, cpf)
        if duplicate:
            flash("Já existe um tripulante cadastrado com este CPF.", "error")
            return render_template(
                "tripulantes_form.html",
                tripulante=tripulante_state,
                tripulante_foto_url="",
                bases_options=fetch_base_options(db, tripulante_state.get("base")),
                status_options=TRIPULANTE_STATUS_OPTIONS,
                funcoes_options=TRIPULANTE_FUNCAO_OPTIONS,
                categorias_options=TRIPULANTE_CATEGORIA_OPTIONS,
            ), 400

        new_photo_storage_ref = None
        try:
            ensure_base_exists(db, base)
            created = db.execute(
                """
                INSERT INTO tripulantes (
                    nome, cpf, licenca_anac, email, telefone, base, status, observacoes, foto_base64,
                    foto_storage_ref, foto_mime_type, possui_foto, ativo, funcao_operacional, categoria_operacional,
                    sdea_ativo, instrutor_ativo, checador_ativo, elegivel_adicional_excepcional
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    nome,
                    cpf,
                    licenca_anac,
                    email,
                    telefone,
                    base,
                    status,
                    get_optional_limited_text(request.form, "observacoes", "Observações"),
                    None,
                    None,
                    None,
                    False,
                    1 if request.form.get("ativo") else 0,
                    funcao_operacional,
                    categoria_operacional,
                    1 if request.form.get("sdea_ativo") else 0,
                    1 if request.form.get("instrutor_ativo") else 0,
                    1 if request.form.get("checador_ativo") else 0,
                    1 if request.form.get("elegivel_adicional_excepcional") else 0,
                ),
            ).fetchone()
            photo_state = _persist_tripulante_photo(
                tripulante_id=created["id"],
                tripulante_name=nome,
                submitted_value=submitted_photo,
                existing_row={},
            )
            db.execute(
                """
                UPDATE tripulantes
                SET foto_base64 = %s,
                    foto_storage_ref = %s,
                    foto_mime_type = %s,
                    possui_foto = %s
                WHERE id = %s
                """,
                (
                    photo_state["foto_base64"],
                    photo_state["foto_storage_ref"],
                    photo_state["foto_mime_type"],
                    photo_state["possui_foto"],
                    created["id"],
                ),
            )
            new_photo_storage_ref = photo_state["new_storage_ref"]
            tripulante_state["foto_base64"] = submitted_photo if isinstance(submitted_photo, str) else ""
            tripulante_state["foto_storage_ref"] = photo_state["foto_storage_ref"]
            sync_linked_pilot_from_tripulante(
                db,
                tripulante_id=created["id"],
                nome=nome,
                licenca_anac=licenca_anac,
                base_nome=base,
                status_text=status,
                is_active=bool(request.form.get("ativo")),
            )
            audit_event(db, "tripulante", created["id"], "create", novo=tripulante_audit_payload(tripulante_state))
            db.commit()
            clear_panel_cache()
            flash("Tripulante cadastrado com sucesso.", "success")
        except psycopg2.IntegrityError:
            rollback_db(db)
            delete_media_ref(new_photo_storage_ref)
            flash("Não foi possível salvar o tripulante. Verifique se o CPF já está em uso.", "error")
            return render_template(
                "tripulantes_form.html",
                tripulante=tripulante_state,
                tripulante_foto_url="",
                bases_options=fetch_base_options(db, tripulante_state.get("base")),
                status_options=TRIPULANTE_STATUS_OPTIONS,
                funcoes_options=TRIPULANTE_FUNCAO_OPTIONS,
                categorias_options=TRIPULANTE_CATEGORIA_OPTIONS,
            ), 400
        except Exception:
            rollback_db(db)
            delete_media_ref(new_photo_storage_ref)
            raise
        return redirect(url_for("cadastros.tripulantes_list"))
    return render_template(
        "tripulantes_form.html",
        tripulante=None,
        tripulante_foto_url="",
        bases_options=fetch_base_options(db),
        status_options=TRIPULANTE_STATUS_OPTIONS,
        funcoes_options=TRIPULANTE_FUNCAO_OPTIONS,
        categorias_options=TRIPULANTE_CATEGORIA_OPTIONS,
    )


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
            nome = get_required_text(request.form, "nome", "Nome")
            cpf = get_validated_cpf(request.form)
            licenca_anac = get_validated_anac_code(request.form)
            email = get_optional_email(request.form, "email", "E-mail")
            telefone = get_optional_limited_text(request.form, "telefone", "Telefone")
            base = get_required_text(request.form, "base", "Base")
            status = validate_tripulante_status(get_required_text(request.form, "status", "Status"))
            funcao_operacional = validate_tripulante_funcao(get_required_text(request.form, "funcao_operacional", "Função operacional"))
            categoria_operacional = validate_tripulante_categoria(get_required_text(request.form, "categoria_operacional", "Categoria operacional"))
            submitted_photo = _resolve_photo_form_value(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template(
                "tripulantes_form.html",
                tripulante=tripulante_state,
                tripulante_foto_url=url_for("cadastros.tripulante_foto", tripulante_id=tripulante_id) if tripulante.get("possui_foto") else "",
                bases_options=fetch_base_options(db, tripulante_state.get("base")),
                status_options=TRIPULANTE_STATUS_OPTIONS,
                funcoes_options=TRIPULANTE_FUNCAO_OPTIONS,
                categorias_options=TRIPULANTE_CATEGORIA_OPTIONS,
            ), 400
        duplicate = find_tripulante_by_cpf(db, cpf, exclude_id=tripulante_id)
        if duplicate:
            flash("Já existe um tripulante cadastrado com este CPF.", "error")
            return render_template(
                "tripulantes_form.html",
                tripulante=tripulante_state,
                tripulante_foto_url=url_for("cadastros.tripulante_foto", tripulante_id=tripulante_id) if tripulante.get("possui_foto") else "",
                bases_options=fetch_base_options(db, tripulante_state.get("base")),
                status_options=TRIPULANTE_STATUS_OPTIONS,
                funcoes_options=TRIPULANTE_FUNCAO_OPTIONS,
                categorias_options=TRIPULANTE_CATEGORIA_OPTIONS,
            ), 400

        new_photo_storage_ref = None
        old_photo_storage_ref_to_delete = None
        try:
            ensure_base_exists(db, base)
            photo_state = _persist_tripulante_photo(
                tripulante_id=tripulante_id,
                tripulante_name=nome,
                submitted_value=submitted_photo,
                existing_row=tripulante,
            )
            new_photo_storage_ref = photo_state["new_storage_ref"]
            old_photo_storage_ref_to_delete = photo_state["old_storage_ref_to_delete"]
            db.execute(
                """
                UPDATE tripulantes
                SET nome = %s, cpf = %s, licenca_anac = %s, email = %s, telefone = %s, base = %s, status = %s,
                    observacoes = %s, foto_base64 = %s, foto_storage_ref = %s, foto_mime_type = %s,
                    possui_foto = %s, ativo = %s, funcao_operacional = %s, categoria_operacional = %s,
                    sdea_ativo = %s, instrutor_ativo = %s, checador_ativo = %s, elegivel_adicional_excepcional = %s
                WHERE id = %s
                """,
                (
                    nome,
                    cpf,
                    licenca_anac,
                    email,
                    telefone,
                    base,
                    status,
                    get_optional_limited_text(request.form, "observacoes", "Observações"),
                    photo_state["foto_base64"],
                    photo_state["foto_storage_ref"],
                    photo_state["foto_mime_type"],
                    photo_state["possui_foto"],
                    1 if request.form.get("ativo") else 0,
                    funcao_operacional,
                    categoria_operacional,
                    1 if request.form.get("sdea_ativo") else 0,
                    1 if request.form.get("instrutor_ativo") else 0,
                    1 if request.form.get("checador_ativo") else 0,
                    1 if request.form.get("elegivel_adicional_excepcional") else 0,
                    tripulante_id,
                ),
            )
            tripulante_state["foto_base64"] = submitted_photo if isinstance(submitted_photo, str) else ""
            tripulante_state["foto_storage_ref"] = photo_state["foto_storage_ref"]
            sync_linked_pilot_from_tripulante(
                db,
                tripulante_id=tripulante_id,
                nome=nome,
                licenca_anac=licenca_anac,
                base_nome=base,
                status_text=status,
                is_active=bool(request.form.get("ativo")),
            )
            audit_event(
                db,
                "tripulante",
                tripulante_id,
                "update",
                anterior=tripulante_audit_payload(tripulante),
                novo=tripulante_audit_payload(tripulante_state),
            )
            db.commit()
            delete_media_ref(old_photo_storage_ref_to_delete)
            clear_panel_cache()
            flash("Tripulante atualizado com sucesso.", "success")
        except psycopg2.IntegrityError:
            rollback_db(db)
            flash("Não foi possível atualizar o tripulante. Verifique se o CPF já está em uso.", "error")
            return render_template(
                "tripulantes_form.html",
                tripulante=tripulante_state,
                tripulante_foto_url=url_for("cadastros.tripulante_foto", tripulante_id=tripulante_id) if tripulante.get("possui_foto") else "",
                bases_options=fetch_base_options(db, tripulante_state.get("base")),
                status_options=TRIPULANTE_STATUS_OPTIONS,
                funcoes_options=TRIPULANTE_FUNCAO_OPTIONS,
                categorias_options=TRIPULANTE_CATEGORIA_OPTIONS,
            ), 400
        except Exception:
            rollback_db(db)
            delete_media_ref(new_photo_storage_ref)
            raise
        return redirect(url_for("cadastros.tripulantes_list"))
    return render_template(
        "tripulantes_form.html",
        tripulante=tripulante,
        tripulante_foto_url=url_for("cadastros.tripulante_foto", tripulante_id=tripulante_id) if tripulante.get("possui_foto") else "",
        bases_options=fetch_base_options(db, tripulante.get("base")),
        status_options=TRIPULANTE_STATUS_OPTIONS,
        funcoes_options=TRIPULANTE_FUNCAO_OPTIONS,
        categorias_options=TRIPULANTE_CATEGORIA_OPTIONS,
    )

