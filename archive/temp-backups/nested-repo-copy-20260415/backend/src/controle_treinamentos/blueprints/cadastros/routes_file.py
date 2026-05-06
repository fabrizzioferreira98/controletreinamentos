from __future__ import annotations

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import Response, abort, current_app, flash, g, redirect, render_template, request, url_for
from flask_login import current_user

from ...auth import permission_required
from ...constants import TRIPULANTE_FILE_MAX_MB
from ...core.audit_utils import audit_event, rollback_db
from ...core.http_utils import get_optional_limited_text, safe_pdf_filename
from ...db import get_db
from ...infra.media_storage import delete_media_ref, read_media_bytes, write_tripulante_document
from ...repositories.tripulante_files import (
    fetch_tripulante_file_rows,
    find_active_duplicate_hash,
    find_training_attachment_by_tripulante,
    find_tripulante_file_by_id,
    insert_tripulante_file,
)
from ...service_layers.domain_validation import validate_tripulante_file_upload
from ...service_layers.tripulante_files import normalize_tipo_documento, status_label
from . import cadastros_bp


def _tripulante_file_table_ready(db) -> bool:
    cached = current_app.config.get("TRIPULANTE_FILE_TABLE_READY")
    if cached is True:
        return True
    try:
        row = db.execute("SELECT to_regclass('public.tripulante_arquivos_pdf') AS table_name").fetchone()
        ready = bool(row and row.get("table_name"))
    except Exception:
        current_app.logger.exception("Falha ao verificar schema da aba File de tripulantes.")
        return False
    # Cacheia somente estado "ready" para não congelar indisponibilidade após migração em runtime.
    if ready:
        current_app.config["TRIPULANTE_FILE_TABLE_READY"] = True
    return ready


def _redirect_when_file_schema_missing(tripulante_id: int):
    flash(
        "A aba File ainda não está disponível neste ambiente. Execute a migração de banco antes de usar documentos.",
        "error",
    )
    if current_user.is_authenticated and current_user.has_permission("tripulantes:edit"):
        return redirect(url_for("cadastros.tripulantes_edit", tripulante_id=tripulante_id))
    return redirect(url_for("cadastros.tripulantes_list"))


def _is_training_source_schema_error(exc: Exception) -> bool:
    message = str(exc).lower()
    schema_tokens = (
        "treinamento_anexos_pdf",
        "tipos_treinamento",
        "tipo_treinamento_id",
        "tpdf.status",
        "tt.nome",
        "undefinedtable",
        "undefinedcolumn",
    )
    return any(token in message for token in schema_tokens)


def _is_training_source_schema_failure(exc: Exception) -> bool:
    if _is_training_source_schema_error(exc):
        return True
    if psycopg2 is not None and isinstance(exc, psycopg2.Error):
        # Classe 42* no PostgreSQL representa erros de sintaxe/schema (undefined table/column etc).
        pgcode = (getattr(exc, "pgcode", "") or "").strip()
        return bool(pgcode.startswith("42"))
    return False


def _load_tripulante_or_404(db, tripulante_id: int):
    tripulante = db.execute(
        """
        SELECT id, nome, cpf, licenca_anac, base, status, ativo
        FROM tripulantes
        WHERE id = %s
        """,
        (tripulante_id,),
    ).fetchone()
    if not tripulante:
        abort(404)
    return tripulante


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/file")
@permission_required("tripulantes_file:view")
def tripulante_file_tab(tripulante_id):
    db = get_db()
    if not _tripulante_file_table_ready(db):
        return _redirect_when_file_schema_missing(tripulante_id)
    tripulante = _load_tripulante_or_404(db, tripulante_id)
    training_source_degraded = False
    try:
        rows = fetch_tripulante_file_rows(db, tripulante_id=tripulante_id, include_training=True)
    except Exception as exc:
        if _is_training_source_schema_failure(exc):
            training_source_degraded = True
            current_app.logger.exception(
                "Aba File degradada para origem local por inconsistência de schema na integração de treinamentos. "
                "request_id=%s tripulante_id=%s",
                getattr(g, "request_id", None),
                tripulante_id,
            )
            rows = fetch_tripulante_file_rows(db, tripulante_id=tripulante_id, include_training=False)
        else:
            raise
    arquivos = []
    for row in rows:
        item = dict(row)
        item["status_label"] = status_label(row.get("status"))
        arquivos.append(item)
    if training_source_degraded:
        flash(
            "A integração Treinamentos → File está temporariamente indisponível neste ambiente por inconsistência de schema. "
            "Execute migração para restaurar a consolidação completa.",
            "error",
        )
    return render_template(
        "tripulantes_file.html",
        tripulante=tripulante,
        arquivos=arquivos,
        attachment_max_mb=TRIPULANTE_FILE_MAX_MB,
    )


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/file/upload", methods=["POST"])
@permission_required("tripulantes_file:create")
def tripulante_file_upload(tripulante_id):
    db = get_db()
    if not _tripulante_file_table_ready(db):
        return _redirect_when_file_schema_missing(tripulante_id)
    tripulante = _load_tripulante_or_404(db, tripulante_id)
    tipo_documento = normalize_tipo_documento(get_optional_limited_text(request.form, "tipo_documento", "Tipo do documento"))

    files = [item for item in request.files.getlist("arquivos_pdf") if item is not None]
    if not files:
        single = request.files.get("arquivo_pdf")
        if single is not None:
            files = [single]
    if not files:
        flash("Selecione ao menos um arquivo PDF.", "error")
        return redirect(url_for("cadastros.tripulante_file_tab", tripulante_id=tripulante_id))

    success_count = 0
    errors: list[str] = []
    fatal_db_error = False

    for file_storage in files:
        display_name = safe_pdf_filename(getattr(file_storage, "filename", ""), fallback="documento.pdf")
        payload = None
        try:
            payload = validate_tripulante_file_upload(file_storage)
            duplicate = find_active_duplicate_hash(
                db,
                tripulante_id=tripulante_id,
                arquivo_hash=payload["arquivo_hash"],
            )
            if duplicate:
                raise ValueError(f"Duplicado: já existe um documento ativo com o mesmo conteúdo ({duplicate['nome_original']}).")

            payload["storage_ref"] = write_tripulante_document(
                tripulante_id,
                tripulante.get("nome"),
                payload["nome_interno"],
                payload["arquivo_pdf"],
            )
            db.execute("SAVEPOINT tripulante_file_upload_sp")
            created = insert_tripulante_file(
                db,
                tripulante_id=tripulante_id,
                tipo_documento=tipo_documento,
                payload=payload,
                enviado_por=int(current_user.id),
            )
            audit_event(
                db,
                "tripulante_arquivo_pdf",
                created["id"],
                "create",
                novo={
                    "tripulante_id": tripulante_id,
                    "tipo_documento": tipo_documento,
                    "nome_original": payload["nome_original"],
                    "mime_type": payload["mime_type"],
                    "tamanho_bytes": payload["tamanho_bytes"],
                },
            )
            db.execute("RELEASE SAVEPOINT tripulante_file_upload_sp")
            success_count += 1
        except ValueError as exc:
            errors.append(f"{display_name}: {exc}")
        except psycopg2.Error:
            delete_media_ref(payload.get("storage_ref") if payload else None)
            try:
                db.execute("ROLLBACK TO SAVEPOINT tripulante_file_upload_sp")
            except Exception:
                fatal_db_error = True
                errors.append("Falha transacional no banco durante upload em lote.")
                break
            errors.append(f"{display_name}: falha ao persistir arquivo no banco.")
        except Exception:
            delete_media_ref(payload.get("storage_ref") if payload else None)
            try:
                db.execute("ROLLBACK TO SAVEPOINT tripulante_file_upload_sp")
            except Exception:
                fatal_db_error = True
                errors.append("Falha transacional inesperada no banco durante upload em lote.")
                break
            current_app.logger.exception("Falha inesperada no upload de documento de tripulante.")
            errors.append(f"{display_name}: falha inesperada durante o upload.")

    if fatal_db_error:
        rollback_db(db)
        success_count = 0
    elif success_count:
        db.commit()
        flash(f"{success_count} arquivo(s) enviado(s) com sucesso.", "success")
    else:
        rollback_db(db)

    for item in errors[:8]:
        flash(item, "error")
    if len(errors) > 8:
        flash(f"{len(errors) - 8} arquivo(s) com falha adicional não exibida.", "error")

    return redirect(url_for("cadastros.tripulante_file_tab", tripulante_id=tripulante_id))


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/file/<int:arquivo_id>")
@permission_required("tripulantes_file:view")
def tripulante_file_get(tripulante_id, arquivo_id):
    db = get_db()
    if not _tripulante_file_table_ready(db):
        abort(503)
    row = find_tripulante_file_by_id(db, tripulante_id=tripulante_id, arquivo_id=arquivo_id)
    if not row or row.get("status") == "removido":
        abort(404)
    safe_name = safe_pdf_filename(row["nome_original"], fallback=f"tripulante_{tripulante_id}_documento.pdf")
    disposition = "attachment" if request.args.get("download", "").strip() == "1" else "inline"
    payload_bytes = read_media_bytes(
        row.get("storage_ref"),
        fallback_bytes=bytes(row["arquivo_pdf"]) if row.get("arquivo_pdf") is not None else None,
    )
    if not payload_bytes:
        abort(404)
    response = Response(payload_bytes, mimetype=row["mime_type"] or "application/pdf")
    response.headers["Content-Disposition"] = f"{disposition}; filename={safe_name}"
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/file/origem/<string:origem>/<int:arquivo_id>")
@permission_required("tripulantes_file:view")
def tripulante_file_get_by_source(tripulante_id, origem, arquivo_id):
    db = get_db()
    if origem == "tripulante_file":
        row = find_tripulante_file_by_id(db, tripulante_id=tripulante_id, arquivo_id=arquivo_id)
        if not row or row.get("status") == "removido":
            abort(404)
        safe_name = safe_pdf_filename(row["nome_original"], fallback=f"tripulante_{tripulante_id}_documento.pdf")
        mime_type = row.get("mime_type") or "application/pdf"
        payload_bytes = read_media_bytes(
            row.get("storage_ref"),
            fallback_bytes=bytes(row["arquivo_pdf"]) if row.get("arquivo_pdf") is not None else None,
        )
    elif origem == "treinamento":
        try:
            row = find_training_attachment_by_tripulante(db, tripulante_id=tripulante_id, anexo_id=arquivo_id)
        except Exception as exc:
            if _is_training_source_schema_failure(exc):
                current_app.logger.exception(
                    "Download/visualização de anexo de treinamento indisponível por inconsistência de schema. "
                    "request_id=%s tripulante_id=%s anexo_id=%s",
                    getattr(g, "request_id", None),
                    tripulante_id,
                    arquivo_id,
                )
                abort(503)
            raise
        if not row:
            abort(404)
        safe_name = safe_pdf_filename(row["nome_original"], fallback=f"tripulante_{tripulante_id}_treinamento_{arquivo_id}.pdf")
        mime_type = row.get("mime_type") or "application/pdf"
        payload_bytes = read_media_bytes(
            row.get("storage_ref"),
            fallback_bytes=bytes(row["arquivo_pdf"]) if row.get("arquivo_pdf") is not None else None,
        )
    else:
        abort(404)
    if not payload_bytes:
        abort(404)

    disposition = "attachment" if request.args.get("download", "").strip() == "1" else "inline"
    response = Response(payload_bytes, mimetype=mime_type)
    response.headers["Content-Disposition"] = f"{disposition}; filename={safe_name}"
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/file/<int:arquivo_id>/excluir", methods=["POST"])
@permission_required("tripulantes_file:delete")
def tripulante_file_delete(tripulante_id, arquivo_id):
    db = get_db()
    if not _tripulante_file_table_ready(db):
        return _redirect_when_file_schema_missing(tripulante_id)
    row = find_tripulante_file_by_id(db, tripulante_id=tripulante_id, arquivo_id=arquivo_id)
    if not row:
        abort(404)
    if row.get("status") == "removido":
        flash("Este documento já foi removido anteriormente.", "error")
        return redirect(url_for("cadastros.tripulante_file_tab", tripulante_id=tripulante_id))

    try:
        db.execute(
            """
            UPDATE tripulante_arquivos_pdf
            SET status = 'removido',
                removido_por = %s,
                removido_em = CURRENT_TIMESTAMP,
                motivo_status = %s
            WHERE id = %s AND tripulante_id = %s
            """,
            (int(current_user.id), "Removido manualmente na aba File.", arquivo_id, tripulante_id),
        )
        audit_event(
            db,
            "tripulante_arquivo_pdf",
            arquivo_id,
            "delete",
            anterior={
                "tripulante_id": tripulante_id,
                "nome_original": row.get("nome_original"),
                "status": row.get("status"),
                "tamanho_bytes": row.get("tamanho_bytes"),
            },
            novo={"status": "removido"},
        )
        db.commit()
        flash("Documento removido com sucesso.", "success")
    except Exception:
        rollback_db(db)
        current_app.logger.exception("Falha ao remover documento de tripulante.")
        flash("Não foi possível remover o documento no momento.", "error")
    return redirect(url_for("cadastros.tripulante_file_tab", tripulante_id=tripulante_id))


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/file/<int:arquivo_id>/substituir", methods=["POST"])
@permission_required("tripulantes_file:replace")
def tripulante_file_replace(tripulante_id, arquivo_id):
    db = get_db()
    if not _tripulante_file_table_ready(db):
        return _redirect_when_file_schema_missing(tripulante_id)
    row = find_tripulante_file_by_id(db, tripulante_id=tripulante_id, arquivo_id=arquivo_id)
    if not row:
        abort(404)
    tripulante = _load_tripulante_or_404(db, tripulante_id)
    if row.get("status") != "ativo":
        flash("A substituição só é permitida para documentos ativos.", "error")
        return redirect(url_for("cadastros.tripulante_file_tab", tripulante_id=tripulante_id))

    try:
        payload = None
        payload = validate_tripulante_file_upload(request.files.get("arquivo_pdf"))
        duplicate = find_active_duplicate_hash(
            db,
            tripulante_id=tripulante_id,
            arquivo_hash=payload["arquivo_hash"],
            exclude_id=arquivo_id,
        )
        if duplicate:
            raise ValueError(f"Já existe um documento ativo com o mesmo conteúdo ({duplicate['nome_original']}).")

        next_tipo_documento = normalize_tipo_documento(
            get_optional_limited_text(request.form, "tipo_documento", "Tipo do documento")
        ) or normalize_tipo_documento(row.get("tipo_documento"))
        payload["storage_ref"] = write_tripulante_document(
            tripulante_id,
            tripulante.get("nome"),
            payload["nome_interno"],
            payload["arquivo_pdf"],
        )
        db.execute("SAVEPOINT tripulante_file_replace_sp")
        created = insert_tripulante_file(
            db,
            tripulante_id=tripulante_id,
            tipo_documento=next_tipo_documento,
            payload=payload,
            enviado_por=int(current_user.id),
            substitui_arquivo_id=arquivo_id,
        )
        db.execute(
            """
            UPDATE tripulante_arquivos_pdf
            SET status = 'substituido',
                motivo_status = %s
            WHERE id = %s
              AND tripulante_id = %s
            """,
            (f"Substituído pelo documento #{created['id']}.", arquivo_id, tripulante_id),
        )
        audit_event(
            db,
            "tripulante_arquivo_pdf",
            created["id"],
            "create",
            novo={
                "tripulante_id": tripulante_id,
                "tipo_documento": next_tipo_documento,
                "nome_original": payload["nome_original"],
                "mime_type": payload["mime_type"],
                "tamanho_bytes": payload["tamanho_bytes"],
                "substitui_arquivo_id": arquivo_id,
            },
        )
        audit_event(
            db,
            "tripulante_arquivo_pdf",
            arquivo_id,
            "update",
            anterior={
                "status": row.get("status"),
                "nome_original": row.get("nome_original"),
            },
            novo={
                "status": "substituido",
                "substituido_por_arquivo_id": created["id"],
            },
        )
        db.execute("RELEASE SAVEPOINT tripulante_file_replace_sp")
        db.commit()
        flash("Documento substituído com sucesso.", "success")
    except ValueError as exc:
        rollback_db(db)
        delete_media_ref(payload.get("storage_ref") if payload else None)
        flash(str(exc), "error")
    except Exception:
        delete_media_ref(payload.get("storage_ref") if payload else None)
        try:
            db.execute("ROLLBACK TO SAVEPOINT tripulante_file_replace_sp")
        except Exception:
            rollback_db(db)
        current_app.logger.exception("Falha ao substituir documento de tripulante.")
        flash("Não foi possível substituir o documento no momento.", "error")
    return redirect(url_for("cadastros.tripulante_file_tab", tripulante_id=tripulante_id))
