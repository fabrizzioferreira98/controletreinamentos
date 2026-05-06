from __future__ import annotations

from datetime import datetime

from flask import Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ...application.relatorios import get_habilitacoes_report_data
from ...application.treinamentos import (
    delete_treinamento,
    delete_treinamento_attachment,
    get_treinamento_attachment,
    save_treinamento,
    upload_treinamento_attachment,
)
from ...application.treinamentos_ssr import (
    TreinamentoSsrNotFoundError,
    get_treinamento_edit_context,
    get_treinamentos_list_context,
)
from ...application.treinamentos_ssr_attachments import (
    delete_treinamento_attachment_from_form,
    get_treinamento_attachment_response_model,
    upload_treinamento_attachment_from_form,
)
from ...application.treinamentos_ssr_reports import (
    build_treinamentos_consolidado_csv_export,
    build_treinamentos_consolidado_pdf_export,
    get_treinamentos_consolidado_context,
    get_treinamentos_consolidado_relatorio_context,
)
from ...auth import permission_required
from ...constants import TRAINING_ATTACHMENT_MAX_MB
from ...contracts.relatorios import (
    habilitacoes_report_to_csv_export,
    habilitacoes_report_to_export_payload,
    habilitacoes_report_to_html_context,
    habilitacoes_report_to_print_context,
)
from ...core.audit_utils import audit_document_generation, audit_relevant_download
from ...core.domain_errors import DomainError
from ...core.file_access_policy import (
    TRAINING_ATTACHMENT_ACCESS_POLICY,
    build_file_access_response,
)
from ...core.frontend_routes import frontend_compat_enabled, redirect_to_frontend
from ...core.http_utils import safe_pdf_filename
from ...core.pdf_document_policy import HABILITACOES_EXPORT_PDF_POLICY, build_pdf_document_response
from ...db import get_db
from ...reports import build_habilitacoes_consolidado_pdf
from ...service_layers.form_builders import build_treinamento_form_state
from ...service_layers.form_options import get_training_form_options
from ...services import business_today
from . import cadastros_bp


def _render_training_form_legacy(treinamento=None, *, options: dict, status_code: int = 200):
    training_data = dict(treinamento) if treinamento else None
    if training_data is not None:
        training_data.setdefault("due_date_mode", "manual" if training_data.get("data_vencimento") else "auto")
    attachments = options.get("attachments", [])
    rendered = render_template(
        "treinamentos_form.html",
        treinamento=training_data,
        attachments=attachments,
        attachment_max_mb=TRAINING_ATTACHMENT_MAX_MB,
        tripulantes=options.get("tripulantes", []),
        equipamentos=options.get("equipamentos", []),
        tipos=options.get("tipos", []),
    )
    return rendered, status_code


def _training_form_options_for_state(db, state: dict | None, *, treinamento_id: int | None = None) -> dict:
    return get_training_form_options(
        db,
        treinamento_id=treinamento_id,
        selected_equipment_id=(state or {}).get("equipamento_id"),
        selected_tipo_id=(state or {}).get("tipo_treinamento_id"),
    )


def _handle_training_form_error(exc: DomainError, *, state: dict, treinamento_id: int | None = None):
    flash(exc.message, "error")
    db = get_db()
    opts = _training_form_options_for_state(db, state, treinamento_id=treinamento_id)
    status_code = 400 if exc.status in {400, 409} else exc.status
    return _render_training_form_legacy(treinamento=state, options=opts, status_code=status_code)


@cadastros_bp.route("/treinamentos")
@login_required
def treinamentos_list():
    if frontend_compat_enabled():
        return redirect_to_frontend(
            "#/treinamentos",
            query={
                "tripulante": request.args.get("tripulante", "").strip(),
                "equipamento": request.args.get("equipamento", "").strip(),
                "tipo": request.args.get("tipo", "").strip(),
                "status": request.args.get("status", "").strip(),
                "periodo": request.args.get("periodo", "").strip(),
            },
        )
    result = get_treinamentos_list_context(
        raw_filters={
            "tripulante": request.args.get("tripulante", "").strip(),
            "equipamento": request.args.get("equipamento", "").strip(),
            "tipo": request.args.get("tipo", "").strip(),
            "status": request.args.get("status", "").strip(),
            "periodo": request.args.get("periodo", "").strip(),
        },
        page=request.args.get("page", "1"),
        today=business_today(),
    )
    for message, category in result["flash_messages"]:
        flash(message, category)
    return render_template(
        "treinamentos_list.html",
        **result["context"],
    )


def _get_habilitacoes_report_from_request():
    filters = _habilitacoes_filters_from_request()
    return get_habilitacoes_report_data(
        get_db(),
        nome=filters["nome"],
        base=filters["base"],
        status=filters["status"],
        tipo=filters["tipo"],
        ordenacao=filters["ordenacao"],
    )


def _habilitacoes_filters_from_request() -> dict[str, str]:
    return {
        "nome": request.args.get("nome", "").strip(),
        "base": request.args.get("base", "").strip(),
        "status": request.args.get("status", "").strip(),
        "tipo": request.args.get("tipo", "").strip(),
        "ordenacao": request.args.get("ordenacao", "").strip(),
    }


@cadastros_bp.route("/treinamentos/consolidado")
@login_required
def treinamentos_consolidado():
    if frontend_compat_enabled():
        return redirect_to_frontend(
            "#/relatorios/habilitacoes",
            query=_habilitacoes_filters_from_request(),
        )
    context = get_treinamentos_consolidado_context(
        raw_filters=_habilitacoes_filters_from_request(),
        get_db_fn=get_db,
        report_loader=get_habilitacoes_report_data,
        html_context_builder=habilitacoes_report_to_html_context,
    )
    return render_template("treinamentos_consolidado.html", **context)


@cadastros_bp.route("/treinamentos/consolidado/relatorio")
@login_required
def treinamentos_consolidado_relatorio():
    context = get_treinamentos_consolidado_relatorio_context(
        raw_filters=_habilitacoes_filters_from_request(),
        get_db_fn=get_db,
        report_loader=get_habilitacoes_report_data,
        print_context_builder=habilitacoes_report_to_print_context,
    )
    return render_template("treinamentos_consolidado_relatorio.html", **context)


@cadastros_bp.route("/treinamentos/consolidado/export.pdf")
@login_required
def treinamentos_consolidado_export_pdf():
    export_result = build_treinamentos_consolidado_pdf_export(
        raw_filters=_habilitacoes_filters_from_request(),
        now=datetime.now(),
        get_db_fn=get_db,
        report_loader=get_habilitacoes_report_data,
        export_payload_builder=habilitacoes_report_to_export_payload,
        pdf_builder=build_habilitacoes_consolidado_pdf,
        safe_pdf_filename_fn=safe_pdf_filename,
        audit_document_generation_fn=audit_document_generation,
        pdf_policy=HABILITACOES_EXPORT_PDF_POLICY,
    )
    return build_pdf_document_response(
        policy=HABILITACOES_EXPORT_PDF_POLICY,
        payload_bytes=export_result["pdf_bytes"],
        filename=export_result["filename"],
    )


@cadastros_bp.route("/treinamentos/consolidado/export.csv")
@login_required
def treinamentos_consolidado_export_csv():
    export_result = build_treinamentos_consolidado_csv_export(
        raw_filters=_habilitacoes_filters_from_request(),
        now=datetime.now(),
        get_db_fn=get_db,
        report_loader=get_habilitacoes_report_data,
        csv_export_builder=habilitacoes_report_to_csv_export,
        export_payload_builder=habilitacoes_report_to_export_payload,
        audit_document_generation_fn=audit_document_generation,
    )
    response = Response(export_result["content"], content_type=export_result["content_type"])
    response.headers["Content-Disposition"] = f"attachment; filename={export_result['filename']}"
    return response


@cadastros_bp.route("/treinamentos/novo", methods=["GET", "POST"])
@login_required
def treinamentos_new():
    if request.method == "GET" and frontend_compat_enabled():
        return redirect_to_frontend("#/treinamentos/new")
    if request.method == "POST":
        treinamento_state = build_treinamento_form_state(request.form)
        try:
            result = save_treinamento(request.form)
        except DomainError as exc:
            return _handle_training_form_error(exc, state=treinamento_state)
        flash(
            "Treinamento cadastrado com sucesso."
            if result["operation"] == "created"
            else "Treinamento salvo com sucesso.",
            "success",
        )
        return redirect(url_for("cadastros.treinamentos_list"))

    db = get_db()
    opts = get_training_form_options(db)
    return _render_training_form_legacy(treinamento=None, options=opts)

@cadastros_bp.route("/treinamentos/<int:treinamento_id>/editar", methods=["GET", "POST"])
@login_required
def treinamentos_edit(treinamento_id):
    if request.method == "GET" and frontend_compat_enabled():
        return redirect_to_frontend(f"#/treinamentos/{treinamento_id}")
    if request.method == "POST":
        treinamento_state = build_treinamento_form_state(request.form)
        try:
            result = save_treinamento(request.form, treinamento_id=treinamento_id)
        except DomainError as exc:
            if exc.status == 404:
                abort(404)
            return _handle_training_form_error(exc, state=treinamento_state, treinamento_id=treinamento_id)
        flash(
            "Treinamento atualizado com sucesso."
            if result["operation"] == "updated"
            else "Treinamento salvo com sucesso.",
            "success",
        )
        return redirect(url_for("cadastros.treinamentos_list"))

    try:
        context = get_treinamento_edit_context(treinamento_id=treinamento_id)
    except TreinamentoSsrNotFoundError:
        abort(404)
    return _render_training_form_legacy(treinamento=context["treinamento"], options=context["options"])

@cadastros_bp.route("/treinamentos/<int:treinamento_id>/excluir", methods=["POST"])
@permission_required("treinamentos:delete")
def treinamentos_delete(treinamento_id):
    try:
        delete_treinamento(treinamento_id=treinamento_id)
    except DomainError as exc:
        if exc.status == 404:
            abort(404)
        flash(exc.message, "error")
        return redirect(url_for("cadastros.treinamentos_list"))
    flash("Treinamento excluido com sucesso.", "success")
    return redirect(url_for("cadastros.treinamentos_list"))

@cadastros_bp.route("/treinamentos/<int:treinamento_id>/anexos/upload", methods=["POST"])
@permission_required("treinamentos_anexos:create")
def treinamentos_anexo_upload(treinamento_id):
    try:
        upload_treinamento_attachment_from_form(
            file_storage=request.files.get("arquivo_pdf"),
            treinamento_id=treinamento_id,
            enviado_por=int(current_user.id),
            upload_attachment_fn=upload_treinamento_attachment,
        )
    except DomainError as exc:
        if exc.status == 404:
            abort(404)
        flash(exc.message, "error")
    else:
        flash("PDF anexado com sucesso.", "success")
    return redirect(url_for("cadastros.treinamentos_edit", treinamento_id=treinamento_id))

@cadastros_bp.route("/treinamentos/<int:treinamento_id>/anexos/<int:anexo_id>")
@permission_required("treinamentos_anexos:view")
def treinamentos_anexo_get(treinamento_id, anexo_id):
    try:
        response_model = get_treinamento_attachment_response_model(
            treinamento_id=treinamento_id,
            anexo_id=anexo_id,
            query_args=request.args,
            get_attachment_fn=get_treinamento_attachment,
        )
    except DomainError:
        abort(404)

    response = build_file_access_response(
        policy=TRAINING_ATTACHMENT_ACCESS_POLICY,
        action=response_model["action"],
        payload_bytes=response_model["payload_bytes"],
        mime_type=response_model["mime_type"],
        filename=response_model["safe_name"],
        entity_id=anexo_id,
        subject_id=treinamento_id,
        source="ssr.training_attachment",
    )
    audit_relevant_download(
        entidade="treinamento_anexo_pdf",
        entidade_id=anexo_id,
        policy_key=TRAINING_ATTACHMENT_ACCESS_POLICY.key,
        action=response_model["action"],
        filename=response_model["safe_name"],
        subject_id=treinamento_id,
        source="ssr.training_attachment",
        commit=True,
    )
    return response

@cadastros_bp.route("/treinamentos/<int:treinamento_id>/anexos/<int:anexo_id>/excluir", methods=["POST"])
@permission_required("treinamentos_anexos:delete")
def treinamentos_anexo_delete(treinamento_id, anexo_id):
    try:
        delete_treinamento_attachment_from_form(
            treinamento_id=treinamento_id,
            anexo_id=anexo_id,
            delete_attachment_fn=delete_treinamento_attachment,
        )
    except DomainError as exc:
        if exc.status == 404:
            abort(404)
        flash(exc.message, "error")
    else:
        flash("Anexo removido com sucesso.", "success")
    return redirect(url_for("cadastros.treinamentos_edit", treinamento_id=treinamento_id))
