from __future__ import annotations

from flask import Response, request
from flask_login import current_user

from ....application.tripulante_media import (
    TripulanteFileConflictError,
    TripulanteFileNotFoundError,
    delete_tripulante_file,
    delete_tripulante_photo,
    get_tripulante_file,
    get_tripulante_photo,
    list_tripulante_files,
    save_tripulante_photo,
    upload_tripulante_file,
)
from ....application.treinamentos import (
    TreinamentoAttachmentNotFoundError,
    TreinamentoConflictError,
    TreinamentoNotFoundError,
    delete_treinamento_attachment,
    delete_treinamento,
    get_treinamento_attachment,
    list_treinamento_attachments,
    save_treinamento,
    upload_treinamento_attachment,
)
from ....application.tripulantes import (
    TripulanteConflictError,
    TripulanteNotFoundError,
    TripulanteValidationError,
    delete_tripulante,
    save_tripulante,
)
from ....auth import permission_required
from ....blueprints.cadastros import cadastros_bp
from ....contracts.tripulante_media import serialize_tripulante_file_item, serialize_tripulante_photo_state
from ....contracts.treinamentos import (
    serialize_treinamento_attachment,
    serialize_treinamento_collection,
    serialize_treinamento_detail,
    serialize_treinamento_options,
)
from ....contracts.tripulantes import (
    serialize_tripulante_collection,
    serialize_tripulante_detail,
    serialize_tripulante_options,
)
from ....core.http_utils import error_payload, get_page_arg, safe_pdf_filename
from ....db import get_db
from ....repositories.queries import fetch_base_options, fetch_training_page
from ....repositories.treinamentos import build_training_filters, count_treinamentos, fetch_treinamento_detail, fetch_training_options
from ....repositories.tripulantes import count_tripulantes, fetch_tripulante_detail, fetch_tripulante_list_page


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {}
    return payload


def _file_payload() -> dict:
    if request.files:
        file_storage = request.files.get("arquivo_pdf")
        if file_storage is None:
            file_list = [item for item in request.files.getlist("arquivos_pdf") if item is not None]
            file_storage = file_list[0] if file_list else None
        return {
            "filename": getattr(file_storage, "filename", "") if file_storage is not None else "",
            "arquivo_bytes": file_storage.read() if file_storage is not None else None,
            "tipo_documento": request.form.get("tipo_documento", ""),
        }
    return _json_payload()


def _request_filters() -> dict:
    return {
        "nome": request.args.get("nome", "").strip(),
        "status": request.args.get("status", "").strip(),
        "base": request.args.get("base", "").strip(),
        "funcao": request.args.get("funcao", "").strip(),
        "categoria": request.args.get("categoria", "").strip(),
        "ativo": request.args.get("ativo", "").strip(),
    }


@cadastros_bp.route("/api/v1/tripulantes", methods=["GET"])
@permission_required("tripulantes:view", "relatorio_individual:view")
def api_tripulantes_list():
    db = get_db()
    filters = _request_filters()
    page = get_page_arg()
    per_page = 20
    total = count_tripulantes(db, **filters)
    offset = (page - 1) * per_page
    rows = fetch_tripulante_list_page(db, **filters, limit=per_page, offset=offset)
    payload = serialize_tripulante_collection(items=rows, page=page, per_page=per_page, total=total)
    payload.update(
        {
            "success": True,
            "status": 200,
            "code": "tripulantes_list_ok",
            "filters": filters,
        }
    )
    return payload, 200


@cadastros_bp.route("/api/v1/tripulantes/options", methods=["GET"])
@permission_required("tripulantes:view", "relatorio_individual:view")
def api_tripulantes_options():
    db = get_db()
    bases = fetch_base_options(db, request.args.get("base", "").strip() or None)
    return {
        "success": True,
        "status": 200,
        "code": "tripulantes_options_ok",
        "options": serialize_tripulante_options(bases=bases),
    }, 200


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>", methods=["GET"])
@permission_required("tripulantes:view", "relatorio_individual:view")
def api_tripulante_get(tripulante_id: int):
    db = get_db()
    row = fetch_tripulante_detail(db, tripulante_id=tripulante_id)
    if not row:
        return error_payload("Tripulante não encontrado.", status=404, code="tripulante_not_found")
    return {
        "success": True,
        "status": 200,
        "code": "tripulante_detail_ok",
        "tripulante": serialize_tripulante_detail(row),
    }, 200


@cadastros_bp.route("/api/v1/tripulantes", methods=["POST"])
@permission_required("tripulantes:create")
def api_tripulante_create():
    try:
        result = save_tripulante(_json_payload())
    except TripulanteValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteConflictError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    tripulante = result["tripulante"]
    return {
        "success": True,
        "status": 201,
        "code": "tripulante_created",
        "operation": result["operation"],
        "tripulante": serialize_tripulante_detail(tripulante),
    }, 201


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>", methods=["PUT"])
@permission_required("tripulantes:edit")
def api_tripulante_update(tripulante_id: int):
    try:
        result = save_tripulante(_json_payload(), tripulante_id=tripulante_id)
    except TripulanteValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteConflictError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    tripulante = result["tripulante"]
    return {
        "success": True,
        "status": 200,
        "code": "tripulante_updated",
        "operation": result["operation"],
        "tripulante": serialize_tripulante_detail(tripulante),
    }, 200


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>", methods=["DELETE"])
@permission_required("tripulantes:delete")
def api_tripulante_delete(tripulante_id: int):
    try:
        result = delete_tripulante(tripulante_id=tripulante_id)
    except TripulanteConflictError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    response = {
        "success": True,
        "status": 200,
        "code": "tripulante_deleted" if result["operation"] == "deleted" else "tripulante_inactivated",
        "operation": result["operation"],
        "message": result["message"],
    }
    if result["operation"] == "inactivated" and result.get("tripulante"):
        response["tripulante"] = serialize_tripulante_detail(result["tripulante"])
    else:
        response["tripulante_id"] = tripulante_id
    return response, 200


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/photo", methods=["GET"])
@permission_required("tripulantes:view", "relatorio_individual:view")
def api_tripulante_photo_get(tripulante_id: int):
    try:
        payload = get_tripulante_photo(tripulante_id=tripulante_id)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteFileNotFoundError:
        return "", 404
    response = Response(payload["payload_bytes"], mimetype=payload["mime_type"])
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/photo", methods=["POST"])
@permission_required("tripulantes:edit")
def api_tripulante_photo_post(tripulante_id: int):
    try:
        result = save_tripulante_photo(_json_payload(), tripulante_id=tripulante_id)
    except TripulanteValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 200,
        "code": "tripulante_photo_saved",
        "photo": serialize_tripulante_photo_state(tripulante_id=tripulante_id, has_photo=result["has_photo"]),
    }, 200


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/photo", methods=["DELETE"])
@permission_required("tripulantes:edit")
def api_tripulante_photo_delete(tripulante_id: int):
    try:
        result = delete_tripulante_photo(tripulante_id=tripulante_id)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteFileNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 200,
        "code": "tripulante_photo_deleted",
        "photo": serialize_tripulante_photo_state(tripulante_id=tripulante_id, has_photo=result["has_photo"]),
    }, 200


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/files", methods=["GET"])
@permission_required("tripulantes_file:view")
def api_tripulante_files_list(tripulante_id: int):
    try:
        rows = list_tripulante_files(tripulante_id=tripulante_id)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 200,
        "code": "tripulante_files_ok",
        "items": [serialize_tripulante_file_item(row) for row in rows],
    }, 200


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/files", methods=["POST"])
@permission_required("tripulantes_file:create")
def api_tripulante_files_upload(tripulante_id: int):
    try:
        row = upload_tripulante_file(
            _file_payload(),
            tripulante_id=tripulante_id,
            enviado_por=int(current_user.id),
        )
    except TripulanteValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteFileConflictError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 201,
        "code": "tripulante_file_created",
        "file": serialize_tripulante_file_item(row),
    }, 201


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/files/<int:file_id>", methods=["GET"])
@permission_required("tripulantes_file:view")
def api_tripulante_file_get(tripulante_id: int, file_id: int):
    try:
        row = get_tripulante_file(tripulante_id=tripulante_id, arquivo_id=file_id)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteFileNotFoundError:
        return "", 404
    safe_name = safe_pdf_filename(
        row.get("nome_original"),
        fallback=f"tripulante_{tripulante_id}_documento.pdf",
    )
    disposition = "attachment" if request.args.get("download", "").strip() == "1" else "inline"
    response = Response(row["payload_bytes"], mimetype=row.get("mime_type") or "application/pdf")
    response.headers["Content-Disposition"] = f"{disposition}; filename={safe_name}"
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/files/<int:file_id>", methods=["DELETE"])
@permission_required("tripulantes_file:delete")
def api_tripulante_file_delete(tripulante_id: int, file_id: int):
    try:
        row = delete_tripulante_file(
            tripulante_id=tripulante_id,
            arquivo_id=file_id,
            removido_por=int(current_user.id),
        )
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteFileNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteFileConflictError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 200,
        "code": "tripulante_file_deleted",
        "file": serialize_tripulante_file_item(row),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos", methods=["GET"])
@permission_required("treinamentos:view")
def api_treinamentos_list():
    db = get_db()
    filters = {
        "tripulante": request.args.get("tripulante", "").strip(),
        "equipamento": request.args.get("equipamento", "").strip(),
        "tipo": request.args.get("tipo", "").strip(),
        "status": request.args.get("status", "").strip(),
        "periodo": request.args.get("periodo", "").strip(),
    }
    try:
        resumo = count_treinamentos(db, **filters)
    except ValueError as exc:
        return error_payload(str(exc), status=400, code="treinamento_bad_filter")
    page = get_page_arg()
    per_page = 20
    where_clause, params = build_training_filters(**filters)
    items = fetch_training_page(
        db,
        where_clause,
        params,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    payload = serialize_treinamento_collection(
        items=items,
        page=page,
        per_page=per_page,
        total=int(resumo["total"] or 0),
        resumo=resumo,
    )
    payload.update({"success": True, "status": 200, "code": "treinamentos_list_ok", "filters": filters})
    return payload, 200


@cadastros_bp.route("/api/v1/treinamentos/options", methods=["GET"])
@permission_required("treinamentos:view")
def api_treinamentos_options():
    db = get_db()
    options = fetch_training_options(
        db,
        treinamento_id=request.args.get("treinamento_id", type=int),
        selected_equipment_id=request.args.get("equipamento_id", type=int),
        selected_tipo_id=request.args.get("tipo_treinamento_id", type=int),
    )
    return {
        "success": True,
        "status": 200,
        "code": "treinamentos_options_ok",
        "options": serialize_treinamento_options(options),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>", methods=["GET"])
@permission_required("treinamentos:view")
def api_treinamento_get(treinamento_id: int):
    db = get_db()
    row = fetch_treinamento_detail(db, treinamento_id=treinamento_id)
    if not row:
        return error_payload("Treinamento não encontrado.", status=404, code="treinamento_not_found")
    attachments = list_treinamento_attachments(treinamento_id=treinamento_id)
    return {
        "success": True,
        "status": 200,
        "code": "treinamento_detail_ok",
        "treinamento": serialize_treinamento_detail(row, attachments=attachments),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos", methods=["POST"])
@permission_required("treinamentos:create")
def api_treinamento_create():
    try:
        result = save_treinamento(_json_payload())
    except TripulanteValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TreinamentoConflictError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 201,
        "code": "treinamento_created",
        "operation": result["operation"],
        "treinamento": serialize_treinamento_detail(result["treinamento"], attachments=result["attachments"]),
    }, 201


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>", methods=["PUT"])
@permission_required("treinamentos:edit")
def api_treinamento_update(treinamento_id: int):
    try:
        result = save_treinamento(_json_payload(), treinamento_id=treinamento_id)
    except TripulanteValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TreinamentoConflictError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TreinamentoNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 200,
        "code": "treinamento_updated",
        "operation": result["operation"],
        "treinamento": serialize_treinamento_detail(result["treinamento"], attachments=result["attachments"]),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>", methods=["DELETE"])
@permission_required("treinamentos:delete")
def api_treinamento_delete(treinamento_id: int):
    try:
        result = delete_treinamento(treinamento_id=treinamento_id)
    except TreinamentoConflictError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TreinamentoNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 200,
        "code": "treinamento_deleted",
        "operation": result["operation"],
        "treinamento_id": result["treinamento_id"],
    }, 200


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>/attachments", methods=["GET"])
@permission_required("treinamentos_anexos:view")
def api_treinamento_attachments_list(treinamento_id: int):
    try:
        attachments = list_treinamento_attachments(treinamento_id=treinamento_id)
    except TreinamentoNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 200,
        "code": "treinamento_attachments_ok",
        "items": [serialize_treinamento_attachment(item) for item in attachments],
    }, 200


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>/attachments", methods=["POST"])
@permission_required("treinamentos_anexos:create")
def api_treinamento_attachments_upload(treinamento_id: int):
    try:
        attachment = upload_treinamento_attachment(
            _file_payload(),
            treinamento_id=treinamento_id,
            enviado_por=int(current_user.id),
        )
    except TripulanteValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TreinamentoNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 201,
        "code": "treinamento_attachment_created",
        "attachment": serialize_treinamento_attachment(attachment),
    }, 201


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>/attachments/<int:attachment_id>", methods=["GET"])
@permission_required("treinamentos_anexos:view")
def api_treinamento_attachment_get(treinamento_id: int, attachment_id: int):
    try:
        row = get_treinamento_attachment(treinamento_id=treinamento_id, anexo_id=attachment_id)
    except TreinamentoAttachmentNotFoundError:
        return "", 404
    safe_name = safe_pdf_filename(
        row.get("nome_original"),
        fallback=f"treinamento_{treinamento_id}_anexo.pdf",
    )
    disposition = "attachment" if request.args.get("download", "").strip() == "1" else "inline"
    response = Response(row["payload_bytes"], mimetype=row.get("mime_type") or "application/pdf")
    response.headers["Content-Disposition"] = f"{disposition}; filename={safe_name}"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>/attachments/<int:attachment_id>", methods=["DELETE"])
@permission_required("treinamentos_anexos:delete")
def api_treinamento_attachment_delete(treinamento_id: int, attachment_id: int):
    try:
        attachment = delete_treinamento_attachment(treinamento_id=treinamento_id, anexo_id=attachment_id)
    except TreinamentoNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TreinamentoAttachmentNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 200,
        "code": "treinamento_attachment_deleted",
        "attachment": serialize_treinamento_attachment(attachment),
    }, 200
