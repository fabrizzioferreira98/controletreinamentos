from __future__ import annotations

from flask import g, request
from flask_login import current_user

from ....application.equipamentos_reads import get_equipamentos_options_read_model
from ....application.treinamentos import (
    TreinamentoAttachmentNotFoundError,
    delete_treinamento,
    delete_treinamento_attachment,
    get_treinamento_attachment,
    list_treinamento_attachments,
    save_treinamento,
    upload_treinamento_attachment,
)
from ....application.treinamentos_reads import (
    get_treinamento_detail_read_model,
    get_treinamentos_options_read_model,
    list_treinamentos_read_model,
)
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
from ....application.tripulantes import (
    TripulanteConflictError,
    TripulanteNotFoundError,
    TripulanteValidationError,
    delete_tripulante,
    save_tripulante,
)
from ....application.tripulantes_reads import (
    get_tripulante_detail_read_model,
    get_tripulantes_options_read_model,
    list_tripulantes_read_model,
)
from ....auth import permission_required
from ....blueprints.cadastros import cadastros_bp
from ....contracts.equipamentos import serialize_equipamento_options
from ....contracts.treinamentos import (
    serialize_treinamento_attachment,
    serialize_treinamento_collection,
    serialize_treinamento_detail,
    serialize_treinamento_options,
)
from ....contracts.tripulante_media import serialize_tripulante_file_item, serialize_tripulante_photo_state
from ....contracts.tripulantes import (
    serialize_tripulante_collection,
    serialize_tripulante_detail,
    serialize_tripulante_options,
)
from ....core.audit_utils import audit_relevant_download
from ....core.domain_errors import DomainError
from ....core.file_access_policy import (
    TRAINING_ATTACHMENT_ACCESS_POLICY,
    TRIPULANTE_FILE_ACCESS_POLICY,
    TRIPULANTE_PHOTO_ACCESS_POLICY,
    build_file_access_response,
    resolve_file_access_action,
)
from ....core.http_utils import domain_error_payload, error_payload, get_page_arg, safe_pdf_filename


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {}
    return payload


def _normalize_file_payload(payload: dict, *, source: str) -> dict:
    normalized = dict(payload)
    content_base64 = str(normalized.get("content_base64") or normalized.get("arquivo_base64") or "").strip()
    if content_base64:
        normalized["content_base64"] = content_base64
        normalized["arquivo_base64"] = content_base64
    content_type = str(normalized.get("content_type") or normalized.get("mime_type") or "").strip()
    normalized["content_type"] = content_type
    normalized["content_type_source"] = "upload" if content_type else "fallback"
    normalized["upload_source"] = source
    return normalized


def _upload_contract(payload: dict) -> dict:
    filename = payload.get("filename_effective") or payload.get("filename") or payload.get("filename_fallback") or ""
    filename_was_fallback = bool(
        payload.get("filename_was_fallback") or (not payload.get("filename") and payload.get("filename_fallback"))
    )
    return {
        "source": payload.get("upload_source") or "json",
        "filename": filename,
        "original_filename": payload.get("filename") or "",
        "filename_source": payload.get("filename_source") or ("upload" if payload.get("filename") else "fallback"),
        "filename_was_fallback": filename_was_fallback,
        "content_type": payload.get("content_type") or "application/pdf",
        "content_type_source": payload.get("content_type_source") or "fallback",
        "encoding": "binary" if payload.get("arquivo_bytes") is not None else "base64",
    }


def _file_payload() -> dict:
    if request.files:
        file_storage = request.files.get("arquivo_pdf")
        if file_storage is None:
            file_list = [item for item in request.files.getlist("arquivos_pdf") if item is not None]
            file_storage = file_list[0] if file_list else None
        content_type = getattr(file_storage, "content_type", "") if file_storage is not None else ""
        return _normalize_file_payload({
            "filename": getattr(file_storage, "filename", "") if file_storage is not None else "",
            "arquivo_bytes": file_storage.read() if file_storage is not None else None,
            "content_type": content_type,
            "tipo_documento": request.form.get("tipo_documento", ""),
            "substitui_arquivo_id": request.form.get("substitui_arquivo_id", ""),
        }, source="multipart")
    return _normalize_file_payload(_json_payload(), source="json")


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
    filters = _request_filters()
    page = get_page_arg()
    per_page = 20
    result = list_tripulantes_read_model(filters=filters, page=page, per_page=per_page)
    payload = serialize_tripulante_collection(
        items=result["items"],
        page=result["page"],
        per_page=result["per_page"],
        total=result["total"],
    )
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
    result = get_tripulantes_options_read_model(base=request.args.get("base", "").strip() or None)
    return {
        "success": True,
        "status": 200,
        "code": "tripulantes_options_ok",
        "options": serialize_tripulante_options(bases=result["bases"]),
    }, 200


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>", methods=["GET"])
@permission_required("tripulantes:view", "relatorio_individual:view")
def api_tripulante_get(tripulante_id: int):
    row = get_tripulante_detail_read_model(tripulante_id=tripulante_id)
    if not row:
        return error_payload("Tripulante não encontrado.", status=404, code="tripulante_not_found")
    return {
        "success": True,
        "status": 200,
        "code": "tripulante_detail_ok",
        "tripulante": serialize_tripulante_detail(row),
    }, 200


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/periodos-operacionais", methods=["GET"])
@permission_required("tripulantes:view", "relatorio_individual:view")
def api_tripulante_operational_periods_list(tripulante_id: int):
    row = get_tripulante_detail_read_model(tripulante_id=tripulante_id)
    if not row:
        return error_payload("Tripulante nÃ£o encontrado.", status=404, code="tripulante_not_found")
    return {
        "success": True,
        "status": 200,
        "code": "tripulante_periodos_operacionais_ok",
        "items": [],
    }, 200


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/periodos-operacionais", methods=["POST"])
@permission_required("tripulantes:edit")
def api_tripulante_operational_periods_create(tripulante_id: int):
    row = get_tripulante_detail_read_model(tripulante_id=tripulante_id)
    if not row:
        return error_payload("Tripulante nÃ£o encontrado.", status=404, code="tripulante_not_found")
    return error_payload(
        "Cadastro de perÃ­odos operacionais ainda nÃ£o estÃ¡ habilitado neste backend.",
        status=501,
        code="tripulante_periodos_operacionais_not_implemented",
    )


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/periodos-operacionais/<int:periodo_id>", methods=["DELETE"])
@permission_required("tripulantes:edit")
def api_tripulante_operational_periods_delete(tripulante_id: int, periodo_id: int):
    row = get_tripulante_detail_read_model(tripulante_id=tripulante_id)
    if not row:
        return error_payload("Tripulante nÃ£o encontrado.", status=404, code="tripulante_not_found")
    return error_payload(
        "Cadastro de perÃ­odos operacionais ainda nÃ£o estÃ¡ habilitado neste backend.",
        status=501,
        code="tripulante_periodos_operacionais_not_implemented",
    )


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
    return build_file_access_response(
        policy=TRIPULANTE_PHOTO_ACCESS_POLICY,
        action="preview",
        payload_bytes=payload["payload_bytes"],
        mime_type=payload["mime_type"],
        entity_id=tripulante_id,
        subject_id=tripulante_id,
        source="api.tripulante_photo",
    )


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/photo", methods=["POST"])
@permission_required("tripulantes:edit")
def api_tripulante_photo_post(tripulante_id: int):
    try:
        result = save_tripulante_photo(_json_payload(), tripulante_id=tripulante_id)
    except TripulanteValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except DomainError as exc:
        return domain_error_payload(exc)
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
    payload = _file_payload()
    payload.setdefault("filename_fallback", "documento_tripulante.pdf")
    if payload.get("substitui_arquivo_id") and not current_user.has_permission("tripulantes_file:replace"):
        return error_payload(
            "Sem permissao para substituir documentos PDF deste tripulante.",
            status=403,
            code="tripulante_file_replace_forbidden",
        )
    try:
        row = upload_tripulante_file(
            payload,
            tripulante_id=tripulante_id,
            enviado_por=int(current_user.id),
        )
    except TripulanteValidationError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteFileNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteFileConflictError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    return {
        "success": True,
        "status": 201,
        "code": "tripulante_file_created",
        "upload": _upload_contract(payload),
        "file": serialize_tripulante_file_item(row),
    }, 201


@cadastros_bp.route("/api/v1/tripulantes/<int:tripulante_id>/files/<int:file_id>", methods=["GET"])
@permission_required("tripulantes_file:view")
def api_tripulante_file_get(tripulante_id: int, file_id: int):
    try:
        row = get_tripulante_file(tripulante_id=tripulante_id, arquivo_id=file_id)
    except TripulanteNotFoundError as exc:
        return error_payload(str(exc), status=exc.status, code=exc.code)
    except TripulanteFileNotFoundError as exc:
        return domain_error_payload(exc)
    safe_name = safe_pdf_filename(
        row.get("nome_original"),
        fallback=f"tripulante_{tripulante_id}_documento.pdf",
    )
    action = resolve_file_access_action(request.args)
    response = build_file_access_response(
        policy=TRIPULANTE_FILE_ACCESS_POLICY,
        action=action,
        payload_bytes=row["payload_bytes"],
        mime_type=row.get("mime_type") or "application/pdf",
        filename=safe_name,
        entity_id=file_id,
        subject_id=tripulante_id,
        source="api.tripulante_file",
    )
    if action == "preview":
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'self'"
        )
    audit_relevant_download(
        entidade="tripulante_arquivo_pdf",
        entidade_id=file_id,
        policy_key=TRIPULANTE_FILE_ACCESS_POLICY.key,
        action=action,
        filename=safe_name,
        subject_id=tripulante_id,
        source="api.tripulante_file",
        commit=True,
    )
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


@cadastros_bp.route("/api/v1/equipamentos/options", methods=["GET"])
@permission_required("equipamentos:view")
def api_equipamentos_options():
    options = get_equipamentos_options_read_model(
        selected_equipment_id=request.args.get("equipamento_id", type=int),
    )
    return {
        "success": True,
        "status": 200,
        "code": "equipamentos_options_ok",
        "message": "Opcoes de equipamentos listadas com sucesso.",
        "request_id": getattr(g, "request_id", None),
        "correlation_id": getattr(g, "correlation_id", None),
        "options": serialize_equipamento_options(options),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos", methods=["GET"])
@permission_required("treinamentos:view")
def api_treinamentos_list():
    filters = {
        "tripulante": request.args.get("tripulante", "").strip(),
        "equipamento": request.args.get("equipamento", "").strip(),
        "tipo": request.args.get("tipo", "").strip(),
        "status": request.args.get("status", "").strip(),
        "periodo": request.args.get("periodo", "").strip(),
    }
    page = get_page_arg()
    per_page = 20
    try:
        result = list_treinamentos_read_model(filters=filters, page=page, per_page=per_page)
    except ValueError as exc:
        return error_payload(str(exc), status=400, code="treinamento_bad_filter")
    payload = serialize_treinamento_collection(
        items=result["items"],
        page=result["page"],
        per_page=result["per_page"],
        total=result["total"],
        resumo=result["resumo"],
    )
    payload.update({"success": True, "status": 200, "code": "treinamentos_list_ok", "filters": filters})
    return payload, 200


@cadastros_bp.route("/api/v1/treinamentos/options", methods=["GET"])
@permission_required("treinamentos:view")
def api_treinamentos_options():
    options = get_treinamentos_options_read_model(
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
    row, attachments = get_treinamento_detail_read_model(treinamento_id=treinamento_id)
    if not row:
        return error_payload("Treinamento não encontrado.", status=404, code="treinamento_not_found")
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
    except DomainError as exc:
        return domain_error_payload(exc)
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
    except DomainError as exc:
        return domain_error_payload(exc)
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
    except DomainError as exc:
        return domain_error_payload(exc)
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
    except DomainError as exc:
        return domain_error_payload(exc)
    return {
        "success": True,
        "status": 200,
        "code": "treinamento_attachments_ok",
        "items": [serialize_treinamento_attachment(item) for item in attachments],
    }, 200


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>/attachments", methods=["POST"])
@permission_required("treinamentos_anexos:create")
def api_treinamento_attachments_upload(treinamento_id: int):
    payload = _file_payload()
    payload.setdefault("filename_fallback", "anexo.pdf")
    try:
        attachment = upload_treinamento_attachment(
            payload,
            treinamento_id=treinamento_id,
            enviado_por=int(current_user.id),
        )
    except DomainError as exc:
        return domain_error_payload(exc)
    return {
        "success": True,
        "status": 201,
        "code": "treinamento_attachment_created",
        "upload": _upload_contract(payload),
        "attachment": serialize_treinamento_attachment(attachment),
    }, 201


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>/attachments/<int:attachment_id>", methods=["GET"])
@permission_required("treinamentos_anexos:view")
def api_treinamento_attachment_get(treinamento_id: int, attachment_id: int):
    try:
        row = get_treinamento_attachment(treinamento_id=treinamento_id, anexo_id=attachment_id)
    except TreinamentoAttachmentNotFoundError as exc:
        return domain_error_payload(exc)
    safe_name = safe_pdf_filename(
        row.get("nome_original"),
        fallback=f"treinamento_{treinamento_id}_anexo.pdf",
    )
    action = resolve_file_access_action(request.args)
    response = build_file_access_response(
        policy=TRAINING_ATTACHMENT_ACCESS_POLICY,
        action=action,
        payload_bytes=row["payload_bytes"],
        mime_type=row.get("mime_type") or "application/pdf",
        filename=safe_name,
        entity_id=attachment_id,
        subject_id=treinamento_id,
        source="api.training_attachment",
    )
    audit_relevant_download(
        entidade="treinamento_anexo_pdf",
        entidade_id=attachment_id,
        policy_key=TRAINING_ATTACHMENT_ACCESS_POLICY.key,
        action=action,
        filename=safe_name,
        subject_id=treinamento_id,
        source="api.training_attachment",
        commit=True,
    )
    return response


@cadastros_bp.route("/api/v1/treinamentos/<int:treinamento_id>/attachments/<int:attachment_id>", methods=["DELETE"])
@permission_required("treinamentos_anexos:delete")
def api_treinamento_attachment_delete(treinamento_id: int, attachment_id: int):
    try:
        attachment = delete_treinamento_attachment(treinamento_id=treinamento_id, anexo_id=attachment_id)
    except DomainError as exc:
        return domain_error_payload(exc)
    return {
        "success": True,
        "status": 200,
        "code": "treinamento_attachment_deleted",
        "attachment": serialize_treinamento_attachment(attachment),
    }, 200
