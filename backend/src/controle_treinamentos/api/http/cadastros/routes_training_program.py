from __future__ import annotations

from flask import request
from flask_login import current_user

from ....application.treinamentos import (
    TreinamentoAttachmentNotFoundError,
    delete_treinamento_attachment,
    get_treinamento_attachment,
    list_treinamento_attachments,
    upload_treinamento_attachment,
)
from ....application.training_program import (
    build_training_program_template,
    create_tripulante_training_batch,
    delete_training_master_hour,
    delete_training_master_segment,
    delete_training_master_type,
    delete_tripulante_training_record,
    save_training_master_hour,
    save_training_master_segment,
    save_training_master_type,
    update_tripulante_training_record,
)
from ....application.training_program_reads import (
    get_training_master_entity_detail_read_model,
    get_training_master_options_read_model,
    get_tripulante_program_options_read_model,
    get_tripulante_program_record_detail_read_model,
    list_training_master_entities_read_model,
    list_tripulante_program_records_read_model,
)
from ....auth import permission_required
from ....blueprints.cadastros import cadastros_bp
from ....contracts.training_program import (
    serialize_training_master_hour,
    serialize_training_master_segment,
    serialize_training_master_type_summary,
    serialize_training_program_master_options,
    serialize_training_program_record_detail,
    serialize_training_program_record_summary,
    serialize_training_program_template,
    serialize_training_program_tripulante_options,
)
from ....contracts.treinamentos import serialize_treinamento_attachment
from ....core.audit_utils import audit_relevant_download
from ....core.domain_errors import DomainError, DomainForbiddenError, DomainNotFoundError, DomainValidationError
from ....core.file_access_policy import (
    TRAINING_ATTACHMENT_ACCESS_POLICY,
    build_file_access_response,
    resolve_file_access_action,
)
from ....core.http_utils import domain_error_payload, safe_pdf_filename
from ....db import get_db
from ....infra.document_blobs import annotate_document_blob_state
from ....repositories.treinamentos import fetch_treinamento_attachments
from ....training_aircraft_model import (
    resolve_training_aircraft_model_reference,
    resolve_training_aircraft_model_snapshot,
)
from .routes import _file_payload, _upload_contract


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {}
    return payload


def _handle_error(exc: Exception):
    if isinstance(exc, DomainError):
        return domain_error_payload(exc)
    raise exc


def _payload_has_training_evidence_upload(payload: dict) -> bool:
    segmentos = payload.get("segmentos")
    if not isinstance(segmentos, list):
        return False
    return any(isinstance(item, dict) and str(item.get("arquivo_base64") or "").strip() for item in segmentos)


def _training_program_attachment_links_base(treinamento_id: int) -> str:
    return f"/api/v1/treinamentos-tripulantes/{int(treinamento_id)}/attachments"


def _serialize_training_program_attachment(row: dict) -> dict:
    return serialize_treinamento_attachment(
        row,
        links_base_path=_training_program_attachment_links_base(int(row["treinamento_id"])),
    )


@cadastros_bp.route("/api/v1/treinamento-raiz/options", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_options():
    result = get_training_master_options_read_model()
    return {
        "success": True,
        "status": 200,
        "code": "training_master_options_ok",
        "options": serialize_training_program_master_options(
            tipos=result["tipos"],
            modelos_aeronave=result["modelos_aeronave"],
        ),
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/tipos", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_types_list():
    items = list_training_master_entities_read_model(entity="types")
    return {
        "success": True,
        "status": 200,
        "code": "training_master_types_ok",
        "items": [serialize_training_master_type_summary(item) for item in items],
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/tipos/<int:tipo_treinamento_id>", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_type_get(tipo_treinamento_id: int):
    row = get_training_master_entity_detail_read_model(entity="types", entity_id=tipo_treinamento_id)
    if not row:
        return domain_error_payload(
            DomainNotFoundError("Tipo de treinamento nao encontrado.", code="training_program_type_not_found")
        )
    return {
        "success": True,
        "status": 200,
        "code": "training_master_type_detail_ok",
        "item": serialize_training_master_type_summary(row),
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/tipos", methods=["POST"])
@permission_required("tipos_treinamento:create")
def api_training_master_type_create():
    try:
        result = save_training_master_type(_json_payload())
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 201,
        "code": "training_master_type_created",
        "operation": result["operation"],
        "item": serialize_training_master_type_summary(result["tipo"]),
    }, 201


@cadastros_bp.route("/api/v1/treinamento-raiz/tipos/<int:tipo_treinamento_id>", methods=["PUT"])
@permission_required("tipos_treinamento:edit")
def api_training_master_type_update(tipo_treinamento_id: int):
    try:
        result = save_training_master_type(_json_payload(), tipo_treinamento_id=tipo_treinamento_id)
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_type_updated",
        "operation": result["operation"],
        "item": serialize_training_master_type_summary(result["tipo"]),
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/tipos/<int:tipo_treinamento_id>", methods=["DELETE"])
@permission_required("tipos_treinamento:delete")
def api_training_master_type_delete(tipo_treinamento_id: int):
    try:
        result = delete_training_master_type(tipo_treinamento_id=tipo_treinamento_id)
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_type_deleted",
        "deleted_id": result["deleted_id"],
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/segmentos", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_segments_list():
    tipo_treinamento_id = request.args.get("tipo_treinamento_id", type=int)
    items = list_training_master_entities_read_model(entity="segments", tipo_treinamento_id=tipo_treinamento_id)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_segments_ok",
        "items": [serialize_training_master_segment(item) for item in items],
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/segmentos/<int:segmento_id>", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_segment_get(segmento_id: int):
    row = get_training_master_entity_detail_read_model(entity="segments", entity_id=segmento_id)
    if not row:
        return domain_error_payload(
            DomainNotFoundError("Segmento teorico nao encontrado.", code="training_program_segment_not_found")
        )
    return {
        "success": True,
        "status": 200,
        "code": "training_master_segment_detail_ok",
        "item": serialize_training_master_segment(row),
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/segmentos", methods=["POST"])
@permission_required("tipos_treinamento:create")
def api_training_master_segment_create():
    try:
        result = save_training_master_segment(_json_payload())
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 201,
        "code": "training_master_segment_created",
        "operation": result["operation"],
        "item": serialize_training_master_segment(result["segmento"]),
    }, 201


@cadastros_bp.route("/api/v1/treinamento-raiz/segmentos/<int:segmento_id>", methods=["PUT"])
@permission_required("tipos_treinamento:edit")
def api_training_master_segment_update(segmento_id: int):
    try:
        result = save_training_master_segment(_json_payload(), segmento_id=segmento_id)
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_segment_updated",
        "operation": result["operation"],
        "item": serialize_training_master_segment(result["segmento"]),
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/segmentos/<int:segmento_id>", methods=["DELETE"])
@permission_required("tipos_treinamento:delete")
def api_training_master_segment_delete(segmento_id: int):
    try:
        result = delete_training_master_segment(segmento_id=segmento_id)
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_segment_deleted",
        "deleted_id": result["deleted_id"],
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/horas-voo", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_hours_list():
    tipo_treinamento_id = request.args.get("tipo_treinamento_id", type=int)
    items = list_training_master_entities_read_model(entity="hours", tipo_treinamento_id=tipo_treinamento_id)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_hours_ok",
        "items": [serialize_training_master_hour(item) for item in items],
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/horas-voo/<int:hora_id>", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_hour_get(hora_id: int):
    row = get_training_master_entity_detail_read_model(entity="hours", entity_id=hora_id)
    if not row:
        return domain_error_payload(
            DomainNotFoundError("Registro de horas de voo nao encontrado.", code="training_program_hour_not_found")
        )
    return {
        "success": True,
        "status": 200,
        "code": "training_master_hour_detail_ok",
        "item": serialize_training_master_hour(row),
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/horas-voo", methods=["POST"])
@permission_required("tipos_treinamento:create")
def api_training_master_hour_create():
    try:
        result = save_training_master_hour(_json_payload())
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 201,
        "code": "training_master_hour_created",
        "operation": result["operation"],
        "item": serialize_training_master_hour(result["hora_voo"]),
    }, 201


@cadastros_bp.route("/api/v1/treinamento-raiz/horas-voo/<int:hora_id>", methods=["PUT"])
@permission_required("tipos_treinamento:edit")
def api_training_master_hour_update(hora_id: int):
    try:
        result = save_training_master_hour(_json_payload(), hora_id=hora_id)
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_hour_updated",
        "operation": result["operation"],
        "item": serialize_training_master_hour(result["hora_voo"]),
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/horas-voo/<int:hora_id>", methods=["DELETE"])
@permission_required("tipos_treinamento:delete")
def api_training_master_hour_delete(hora_id: int):
    try:
        result = delete_training_master_hour(hora_id=hora_id)
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_hour_deleted",
        "deleted_id": result["deleted_id"],
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/options", methods=["GET"])
@permission_required("treinamentos:view")
def api_training_program_tripulantes_options():
    base_filter = request.args.get("base", "").strip() or None
    options = get_tripulante_program_options_read_model(base=base_filter)
    return {
        "success": True,
        "status": 200,
        "code": "training_program_tripulantes_options_ok",
        "options": serialize_training_program_tripulante_options(
            tripulantes=options["tripulantes"],
            tipos=options["tipos"],
            modelos_aeronave=options["modelos_aeronave"],
        ),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/template", methods=["GET"])
@permission_required("treinamentos:view")
def api_training_program_template():
    tipo_treinamento_id = request.args.get("tipo_treinamento_id", type=int)
    aeronave_modelo_referencia = resolve_training_aircraft_model_reference(request.args)
    if not tipo_treinamento_id:
        return domain_error_payload(
            DomainValidationError("Tipo de treinamento e obrigatorio.", code="training_program_missing_type")
        )
    try:
        template = build_training_program_template(
            tipo_treinamento_id=tipo_treinamento_id,
            aeronave_modelo_referencia=aeronave_modelo_referencia,
        )
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_program_template_ok",
        "template": serialize_training_program_template(template),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes", methods=["GET"])
@permission_required("treinamentos:view")
def api_training_program_records_list():
    items = list_tripulante_program_records_read_model(
        tripulante_id=request.args.get("tripulante_id", type=int),
        tipo_treinamento_id=request.args.get("tipo_treinamento_id", type=int),
        aeronave_modelo_snapshot=resolve_training_aircraft_model_snapshot(request.args),
        base=request.args.get("base", "").strip() or None,
    )
    return {
        "success": True,
        "status": 200,
        "code": "training_program_records_ok",
        "items": [serialize_training_program_record_summary(item) for item in items],
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/<int:treinamento_id>", methods=["GET"])
@permission_required("treinamentos:view")
def api_training_program_record_get(treinamento_id: int):
    result = get_tripulante_program_record_detail_read_model(treinamento_id=treinamento_id)
    row = result["item"]
    if not row:
        return domain_error_payload(
            DomainNotFoundError("Registro de treinamento nao encontrado.", code="training_program_record_not_found")
        )
    attachments = [_serialize_training_program_attachment(item) for item in result["attachments"]]
    return {
        "success": True,
        "status": 200,
        "code": "training_program_record_detail_ok",
        "item": serialize_training_program_record_detail(row, attachments=attachments),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/batch", methods=["POST"])
@permission_required("treinamentos:create")
def api_training_program_batch_create():
    payload = _json_payload()
    if _payload_has_training_evidence_upload(payload) and not current_user.has_permission("treinamentos_anexos:create"):
        return domain_error_payload(
            DomainForbiddenError(
                "Sem permissao para enviar evidencias PDF neste batch de treinamento.",
                code="training_program_evidence_upload_forbidden",
            )
        )
    try:
        result = create_tripulante_training_batch(payload, criado_por=int(current_user.id))
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 201,
        "code": "training_program_batch_created",
        "created_ids": result["created_ids"],
        "items": [serialize_training_program_record_summary(item) for item in result["items"]],
        "template": serialize_training_program_template(result["template"]),
    }, 201


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/<int:treinamento_id>", methods=["PUT"])
@permission_required("treinamentos:edit")
def api_training_program_record_update(treinamento_id: int):
    try:
        result = update_tripulante_training_record(_json_payload(), treinamento_id=treinamento_id)
    except Exception as exc:
        return _handle_error(exc)
    db = get_db()
    attachments = [
        _serialize_training_program_attachment(annotate_document_blob_state(item))
        for item in fetch_treinamento_attachments(db, treinamento_id=treinamento_id)
    ]
    return {
        "success": True,
        "status": 200,
        "code": "training_program_record_updated",
        "item": serialize_training_program_record_detail(result["item"], attachments=attachments),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/<int:treinamento_id>", methods=["DELETE"])
@permission_required("treinamentos:delete")
def api_training_program_record_delete(treinamento_id: int):
    try:
        result = delete_tripulante_training_record(treinamento_id=treinamento_id)
    except Exception as exc:
        return _handle_error(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_program_record_deleted",
        "deleted_id": result["deleted_id"],
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/<int:treinamento_id>/attachments", methods=["GET"])
@permission_required("treinamentos_anexos:view")
def api_training_program_record_attachments_list(treinamento_id: int):
    try:
        attachments = list_treinamento_attachments(treinamento_id=treinamento_id)
    except DomainError as exc:
        return domain_error_payload(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_program_record_attachments_ok",
        "items": [_serialize_training_program_attachment(item) for item in attachments],
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/<int:treinamento_id>/attachments", methods=["POST"])
@permission_required("treinamentos_anexos:create")
def api_training_program_record_attachments_upload(treinamento_id: int):
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
        "code": "training_program_record_attachment_created",
        "upload": _upload_contract(payload),
        "attachment": _serialize_training_program_attachment(attachment),
    }, 201


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/<int:treinamento_id>/attachments/<int:attachment_id>", methods=["GET"])
@permission_required("treinamentos_anexos:view")
def api_training_program_record_attachment_get(treinamento_id: int, attachment_id: int):
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
        source="api.training_program_attachment",
    )
    audit_relevant_download(
        entidade="treinamento_anexo_pdf",
        entidade_id=attachment_id,
        policy_key=TRAINING_ATTACHMENT_ACCESS_POLICY.key,
        action=action,
        filename=safe_name,
        subject_id=treinamento_id,
        source="api.training_program_attachment",
        commit=True,
    )
    return response


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/<int:treinamento_id>/attachments/<int:attachment_id>", methods=["DELETE"])
@permission_required("treinamentos_anexos:delete")
def api_training_program_record_attachment_delete(treinamento_id: int, attachment_id: int):
    try:
        attachment = delete_treinamento_attachment(treinamento_id=treinamento_id, anexo_id=attachment_id)
    except DomainError as exc:
        return domain_error_payload(exc)
    return {
        "success": True,
        "status": 200,
        "code": "training_program_record_attachment_deleted",
        "attachment": _serialize_training_program_attachment(attachment),
    }, 200
