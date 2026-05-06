from __future__ import annotations

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
from flask_login import current_user

from ...application.tripulante_media import delete_tripulante_file, get_tripulante_file, upload_tripulante_file
from ...auth import permission_required
from ...constants import TRIPULANTE_FILE_MAX_MB
from ...core.audit_utils import audit_relevant_download
from ...core.domain_errors import DomainError, DomainNotFoundError, DomainUnavailableError
from ...core.file_access_policy import (
    TRIPULANTE_FILE_ACCESS_POLICY,
    TRIPULANTE_FILE_CONSOLIDATED_ACCESS_POLICY,
    build_file_access_response,
    resolve_file_access_action,
)
from ...core.http_utils import get_optional_limited_text, safe_pdf_filename
from ...db import get_db
from ...infra.document_blobs import annotate_document_blob_state, read_document_blob
from ...repositories.tripulante_files import (
    fetch_tripulante_file_rows,
    find_training_attachment_by_tripulante,
)
from ...repositories.tripulantes import fetch_tripulante_detail
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


def _tripulante_file_upload_payload(file_storage, *, tipo_documento: str | None, substitui_arquivo_id: int | None = None) -> dict:
    return {
        "filename": getattr(file_storage, "filename", "") if file_storage is not None else "",
        "arquivo_bytes": file_storage.read() if file_storage is not None else b"",
        "content_type": getattr(file_storage, "content_type", "") if file_storage is not None else "",
        "tipo_documento": tipo_documento,
        "substitui_arquivo_id": substitui_arquivo_id,
    }


def _flash_domain_error(error: DomainError) -> None:
    flash(error.message, "error")


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
    tripulante = fetch_tripulante_detail(db, tripulante_id=tripulante_id)
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
        item = annotate_document_blob_state(dict(row))
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
    _load_tripulante_or_404(db, tripulante_id)
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

    for file_storage in files:
        display_name = safe_pdf_filename(getattr(file_storage, "filename", ""), fallback="documento.pdf")
        try:
            upload_tripulante_file(
                _tripulante_file_upload_payload(file_storage, tipo_documento=tipo_documento),
                tripulante_id=tripulante_id,
                enviado_por=int(current_user.id),
            )
            success_count += 1
        except DomainError as exc:
            errors.append(f"{display_name}: {exc.message}")

    if success_count:
        flash(f"{success_count} arquivo(s) enviado(s) com sucesso.", "success")

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
    try:
        row = get_tripulante_file(tripulante_id=tripulante_id, arquivo_id=arquivo_id)
    except DomainError as exc:
        abort(exc.status)
    safe_name = safe_pdf_filename(row["nome_original"], fallback=f"tripulante_{tripulante_id}_documento.pdf")
    action = resolve_file_access_action(request.args)
    response = build_file_access_response(
        policy=TRIPULANTE_FILE_ACCESS_POLICY,
        action=action,
        payload_bytes=row["payload_bytes"],
        mime_type=row["mime_type"] or "application/pdf",
        filename=safe_name,
        entity_id=arquivo_id,
        subject_id=tripulante_id,
        source="ssr.tripulante_file",
    )
    audit_relevant_download(
        entidade="tripulante_arquivo_pdf",
        entidade_id=arquivo_id,
        policy_key=TRIPULANTE_FILE_ACCESS_POLICY.key,
        action=action,
        filename=safe_name,
        subject_id=tripulante_id,
        source="ssr.tripulante_file",
        commit=True,
    )
    return response


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/file/origem/<string:origem>/<int:arquivo_id>")
@permission_required("tripulantes_file:view")
def tripulante_file_get_by_source(tripulante_id, origem, arquivo_id):
    db = get_db()
    if origem == "tripulante_file":
        try:
            row = get_tripulante_file(tripulante_id=tripulante_id, arquivo_id=arquivo_id)
        except DomainError as exc:
            abort(exc.status)
        safe_name = safe_pdf_filename(row["nome_original"], fallback=f"tripulante_{tripulante_id}_documento.pdf")
        mime_type = row.get("mime_type") or "application/pdf"
        payload_bytes = row["payload_bytes"]
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
                raise DomainUnavailableError(
                    "Anexo de treinamento temporariamente indisponivel.",
                    code="tripulante_file_training_source_unavailable",
                ) from exc
            raise
        if not row:
            raise DomainNotFoundError("Documento nao encontrado.", code="tripulante_file_not_found")
        safe_name = safe_pdf_filename(row["nome_original"], fallback=f"tripulante_{tripulante_id}_treinamento_{arquivo_id}.pdf")
        mime_type = row.get("mime_type") or "application/pdf"
        payload_bytes = read_document_blob(dict(row))
    else:
        raise DomainNotFoundError("Origem de documento nao encontrada.", code="tripulante_file_source_not_found")
    if not payload_bytes:
        raise DomainNotFoundError("Documento nao encontrado.", code="tripulante_file_not_found")

    action = resolve_file_access_action(request.args)
    response = build_file_access_response(
        policy=TRIPULANTE_FILE_CONSOLIDATED_ACCESS_POLICY,
        action=action,
        payload_bytes=payload_bytes,
        mime_type=mime_type,
        filename=safe_name,
        entity_id=arquivo_id,
        subject_id=tripulante_id,
        source=f"ssr.tripulante_file.{origem}",
    )
    audit_relevant_download(
        entidade="treinamento_anexo_pdf" if origem == "treinamento" else "tripulante_arquivo_pdf",
        entidade_id=arquivo_id,
        policy_key=TRIPULANTE_FILE_CONSOLIDATED_ACCESS_POLICY.key,
        action=action,
        filename=safe_name,
        subject_id=tripulante_id,
        source=f"ssr.tripulante_file.{origem}",
        commit=True,
    )
    return response


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/file/<int:arquivo_id>/excluir", methods=["POST"])
@permission_required("tripulantes_file:delete")
def tripulante_file_delete(tripulante_id, arquivo_id):
    db = get_db()
    if not _tripulante_file_table_ready(db):
        return _redirect_when_file_schema_missing(tripulante_id)
    try:
        delete_tripulante_file(
            tripulante_id=tripulante_id,
            arquivo_id=arquivo_id,
            removido_por=int(current_user.id),
        )
        flash("Documento removido com sucesso.", "success")
    except DomainError as exc:
        if exc.status == 404:
            abort(404)
        _flash_domain_error(exc)
    return redirect(url_for("cadastros.tripulante_file_tab", tripulante_id=tripulante_id))


@cadastros_bp.route("/tripulantes/<int:tripulante_id>/file/<int:arquivo_id>/substituir", methods=["POST"])
@permission_required("tripulantes_file:replace")
def tripulante_file_replace(tripulante_id, arquivo_id):
    db = get_db()
    if not _tripulante_file_table_ready(db):
        return _redirect_when_file_schema_missing(tripulante_id)
    try:
        next_tipo_documento = normalize_tipo_documento(
            get_optional_limited_text(request.form, "tipo_documento", "Tipo do documento")
        )
        upload_tripulante_file(
            _tripulante_file_upload_payload(
                request.files.get("arquivo_pdf"),
                tipo_documento=next_tipo_documento,
                substitui_arquivo_id=arquivo_id,
            ),
            tripulante_id=tripulante_id,
            enviado_por=int(current_user.id),
        )
        flash("Documento substituído com sucesso.", "success")
    except DomainError as exc:
        if exc.status == 404:
            abort(404)
        _flash_domain_error(exc)
    return redirect(url_for("cadastros.tripulante_file_tab", tripulante_id=tripulante_id))
