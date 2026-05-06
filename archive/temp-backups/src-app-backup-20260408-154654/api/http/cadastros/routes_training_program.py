from __future__ import annotations

from flask import request
from flask_login import current_user

from ....application.training_program import (
    TrainingProgramAttachmentError,
    TrainingProgramConflictError,
    TrainingProgramNotFoundError,
    TrainingProgramValidationError,
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
from ....core.http_utils import error_payload
from ....db import get_db
from ....repositories.training_program import (
    fetch_training_master_hour_detail,
    fetch_training_master_hours,
    fetch_training_master_segment_detail,
    fetch_training_master_segments,
    fetch_training_master_type_detail,
    fetch_training_master_types,
    fetch_training_program_active_types,
    fetch_training_program_aircraft_models,
    fetch_training_program_record_detail,
    fetch_training_program_record_list,
    fetch_training_program_tripulantes,
)
from ....repositories.treinamentos import fetch_treinamento_attachments


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {}
    return payload


def _handle_error(exc: Exception):
    if isinstance(exc, (TrainingProgramValidationError, TrainingProgramAttachmentError, TrainingProgramConflictError, TrainingProgramNotFoundError)):
        return error_payload(str(exc), status=exc.status, code=exc.code)
    raise exc


@cadastros_bp.route("/api/v1/treinamento-raiz/options", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_options():
    db = get_db()
    tipos = fetch_training_master_types(db)
    modelos = fetch_training_program_aircraft_models(db)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_options_ok",
        "options": serialize_training_program_master_options(tipos=tipos, modelos_aeronave=modelos),
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/tipos", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_types_list():
    db = get_db()
    return {
        "success": True,
        "status": 200,
        "code": "training_master_types_ok",
        "items": [serialize_training_master_type_summary(item) for item in fetch_training_master_types(db)],
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/tipos/<int:tipo_treinamento_id>", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_type_get(tipo_treinamento_id: int):
    db = get_db()
    row = fetch_training_master_type_detail(db, tipo_treinamento_id=tipo_treinamento_id)
    if not row:
        return error_payload("Tipo de treinamento nao encontrado.", status=404, code="training_program_type_not_found")
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
    db = get_db()
    tipo_treinamento_id = request.args.get("tipo_treinamento_id", type=int)
    items = fetch_training_master_segments(db, tipo_treinamento_id=tipo_treinamento_id)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_segments_ok",
        "items": [serialize_training_master_segment(item) for item in items],
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/segmentos/<int:segmento_id>", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_segment_get(segmento_id: int):
    db = get_db()
    row = fetch_training_master_segment_detail(db, segmento_id=segmento_id)
    if not row:
        return error_payload("Segmento teorico nao encontrado.", status=404, code="training_program_segment_not_found")
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
    db = get_db()
    tipo_treinamento_id = request.args.get("tipo_treinamento_id", type=int)
    items = fetch_training_master_hours(db, tipo_treinamento_id=tipo_treinamento_id)
    return {
        "success": True,
        "status": 200,
        "code": "training_master_hours_ok",
        "items": [serialize_training_master_hour(item) for item in items],
    }, 200


@cadastros_bp.route("/api/v1/treinamento-raiz/horas-voo/<int:hora_id>", methods=["GET"])
@permission_required("tipos_treinamento:view")
def api_training_master_hour_get(hora_id: int):
    db = get_db()
    row = fetch_training_master_hour_detail(db, hora_id=hora_id)
    if not row:
        return error_payload("Registro de horas de voo nao encontrado.", status=404, code="training_program_hour_not_found")
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
    db = get_db()
    return {
        "success": True,
        "status": 200,
        "code": "training_program_tripulantes_options_ok",
        "options": serialize_training_program_tripulante_options(
            tripulantes=fetch_training_program_tripulantes(db),
            tipos=fetch_training_program_active_types(db),
            modelos_aeronave=fetch_training_program_aircraft_models(db),
        ),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/template", methods=["GET"])
@permission_required("treinamentos:view")
def api_training_program_template():
    tipo_treinamento_id = request.args.get("tipo_treinamento_id", type=int)
    aeronave_modelo = (request.args.get("aeronave_modelo", "") or "").strip()
    if not tipo_treinamento_id:
        return error_payload("Tipo de treinamento ? obrigat?rio.", status=400, code="training_program_missing_type")
    try:
        template = build_training_program_template(
            tipo_treinamento_id=tipo_treinamento_id,
            aeronave_modelo=aeronave_modelo or None,
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
    db = get_db()
    items = fetch_training_program_record_list(
        db,
        tripulante_id=request.args.get("tripulante_id", type=int),
        tipo_treinamento_id=request.args.get("tipo_treinamento_id", type=int),
        aeronave_modelo=(request.args.get("aeronave_modelo", "") or "").strip() or None,
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
    db = get_db()
    row = fetch_training_program_record_detail(db, treinamento_id=treinamento_id)
    if not row:
        return error_payload("Registro de treinamento nao encontrado.", status=404, code="training_program_record_not_found")
    attachments = [serialize_treinamento_attachment(item) for item in fetch_treinamento_attachments(db, treinamento_id=treinamento_id)]
    return {
        "success": True,
        "status": 200,
        "code": "training_program_record_detail_ok",
        "item": serialize_training_program_record_detail(row, attachments=attachments),
    }, 200


@cadastros_bp.route("/api/v1/treinamentos-tripulantes/batch", methods=["POST"])
@permission_required("treinamentos:create")
def api_training_program_batch_create():
    try:
        result = create_tripulante_training_batch(_json_payload(), criado_por=int(current_user.id))
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
    attachments = [serialize_treinamento_attachment(item) for item in fetch_treinamento_attachments(db, treinamento_id=treinamento_id)]
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
