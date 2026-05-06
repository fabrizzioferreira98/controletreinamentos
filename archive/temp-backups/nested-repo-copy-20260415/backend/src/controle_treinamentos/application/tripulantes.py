from __future__ import annotations

import base64
import binascii
import re

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from ..core.audit_utils import audit_event, rollback_db, tripulante_audit_payload
from ..core.http_utils import (
    get_optional_email,
    get_optional_limited_text,
    get_required_text,
    get_validated_anac_code,
    get_validated_cpf,
)
from ..constants import MAX_PHOTO_BYTES, PHOTO_PREFIXES
from ..db import ensure_base_exists, get_db
from ..infra.media_storage import delete_media_ref, write_tripulante_photo
from ..repositories.dashboard_cache import clear_panel_cache
from ..repositories.tripulantes import (
    create_tripulante,
    delete_historico_status_piloto_by_pilot_ids,
    delete_pilotos_by_ids,
    delete_tripulante as delete_tripulante_row,
    fetch_tripulante_dependencies,
    fetch_tripulante_delete_target,
    fetch_tripulante_detail,
    fetch_tripulante_for_write,
    inactivate_tripulante,
    find_linked_pilot_ids,
    find_tripulante_by_cpf,
    update_tripulante,
    update_tripulante_photo_state,
)
from ..service_layers.domain_validation import (
    sync_linked_pilot_from_tripulante,
    validate_tripulante_categoria,
    validate_tripulante_funcao,
    validate_tripulante_status,
)

_PHOTO_DATA_URI_RE = re.compile(r"^data:image/(png|jpe?g);base64,", re.IGNORECASE)
_KEEP_EXISTING_PHOTO = object()
_REMOVE_PHOTO = object()


class TripulanteValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "tripulante_validation_error", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


class TripulanteConflictError(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.code = "tripulante_conflict"
        self.status = 409


class TripulanteNotFoundError(RuntimeError):
    code = "tripulante_not_found"
    status = 404


def _bool_value(payload, key: str) -> bool:
    raw = payload.get(key)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    return str(raw or "").strip().lower() in {"1", "true", "on", "yes", "sim"}


def _decode_photo_data_uri(raw_value: str):
    foto_base64 = (raw_value or "").strip()
    match = _PHOTO_DATA_URI_RE.match(foto_base64)
    if not match:
        raise TripulanteValidationError("A foto deve estar em JPG ou PNG.", code="tripulante_invalid_photo")
    try:
        decoded = base64.b64decode(foto_base64.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise TripulanteValidationError("A foto enviada está inválida.", code="tripulante_invalid_photo") from exc
    if len(decoded) > MAX_PHOTO_BYTES:
        raise TripulanteValidationError("A foto deve ter no máximo 1 MB.", code="tripulante_invalid_photo")
    image_format = match.group(1).lower()
    mime_type = "image/jpeg" if image_format in {"jpg", "jpeg"} else "image/png"
    return decoded, mime_type


def _resolve_photo_submission(payload):
    if _bool_value(payload, "remove_foto"):
        return _REMOVE_PHOTO
    raw_value = str(payload.get("foto_base64") or "").strip()
    if not raw_value:
        return _KEEP_EXISTING_PHOTO
    if not any(raw_value.startswith(prefix) for prefix in PHOTO_PREFIXES):
        raise TripulanteValidationError("A foto deve estar em JPG ou PNG.", code="tripulante_invalid_photo")
    return raw_value


def _persist_tripulante_photo(*, tripulante_id: int, tripulante_name: str, submitted_value, existing_row: dict):
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
    raw_bytes, mime_type = _decode_photo_data_uri(submitted_value)
    new_storage_ref = write_tripulante_photo(tripulante_id, tripulante_name, raw_bytes, mime_type=mime_type)
    return {
        "foto_base64": None,
        "foto_storage_ref": new_storage_ref,
        "foto_mime_type": mime_type,
        "possui_foto": True,
        "new_storage_ref": new_storage_ref,
        "old_storage_ref_to_delete": existing_row.get("foto_storage_ref"),
    }


def _parse_tripulante_payload(payload: dict) -> dict:
    try:
        return {
            "nome": get_required_text(payload, "nome", "Nome"),
            "cpf": get_validated_cpf(payload),
            "licenca_anac": get_validated_anac_code(payload),
            "email": get_optional_email(payload, "email", "E-mail"),
            "telefone": get_optional_limited_text(payload, "telefone", "Telefone"),
            "base": get_required_text(payload, "base", "Base"),
            "status": validate_tripulante_status(get_required_text(payload, "status", "Status")),
            "funcao_operacional": validate_tripulante_funcao(
                get_required_text(payload, "funcao_operacional", "Função operacional")
            ),
            "categoria_operacional": validate_tripulante_categoria(
                get_required_text(payload, "categoria_operacional", "Categoria operacional")
            ),
            "observacoes": get_optional_limited_text(payload, "observacoes", "Observações"),
            "ativo": _bool_value(payload, "ativo"),
            "sdea_ativo": _bool_value(payload, "sdea_ativo"),
            "instrutor_ativo": _bool_value(payload, "instrutor_ativo"),
            "checador_ativo": _bool_value(payload, "checador_ativo"),
            "elegivel_adicional_excepcional": _bool_value(payload, "elegivel_adicional_excepcional"),
            "submitted_photo": _resolve_photo_submission(payload),
        }
    except ValueError as exc:
        raise TripulanteValidationError(str(exc)) from exc


def save_tripulante(payload: dict, *, tripulante_id: int | None = None) -> dict:
    db = get_db()
    data = _parse_tripulante_payload(payload)

    existing_row = {}
    if tripulante_id is not None:
        existing_row = fetch_tripulante_for_write(db, tripulante_id=tripulante_id) or {}
        if not existing_row:
            raise TripulanteNotFoundError("Tripulante não encontrado.")

    duplicate = find_tripulante_by_cpf(db, data["cpf"], exclude_id=tripulante_id)
    if duplicate:
        raise TripulanteConflictError("Já existe um tripulante cadastrado com este CPF.")

    new_photo_storage_ref = None
    old_photo_storage_ref_to_delete = None
    try:
        ensure_base_exists(db, data["base"])
        if tripulante_id is None:
            tripulante_id = create_tripulante(db, data=data)
            photo_state = _persist_tripulante_photo(
                tripulante_id=tripulante_id,
                tripulante_name=data["nome"],
                submitted_value=data["submitted_photo"],
                existing_row={},
            )
            update_tripulante_photo_state(db, tripulante_id=tripulante_id, photo_state=photo_state)
            action = "create"
        else:
            photo_state = _persist_tripulante_photo(
                tripulante_id=tripulante_id,
                tripulante_name=data["nome"],
                submitted_value=data["submitted_photo"],
                existing_row=existing_row,
            )
            update_tripulante(db, tripulante_id=tripulante_id, data=data, photo_state=photo_state)
            action = "update"

        new_photo_storage_ref = photo_state["new_storage_ref"]
        old_photo_storage_ref_to_delete = photo_state["old_storage_ref_to_delete"]

        sync_linked_pilot_from_tripulante(
            db,
            tripulante_id=tripulante_id,
            nome=data["nome"],
            licenca_anac=data["licenca_anac"],
            base_nome=data["base"],
            status_text=data["status"],
            is_active=data["ativo"],
        )

        audit_payload = {
            **data,
            "foto_base64": "" if photo_state["foto_storage_ref"] else None,
            "foto_storage_ref": photo_state["foto_storage_ref"],
            "possui_foto": photo_state["possui_foto"],
        }
        if action == "create":
            audit_event(db, "tripulante", tripulante_id, "create", novo=tripulante_audit_payload(audit_payload))
        else:
            audit_event(
                db,
                "tripulante",
                tripulante_id,
                "update",
                anterior=tripulante_audit_payload(existing_row),
                novo=tripulante_audit_payload(audit_payload),
            )

        db.commit()
        delete_media_ref(old_photo_storage_ref_to_delete)
        clear_panel_cache()
    except TripulanteValidationError:
        rollback_db(db)
        delete_media_ref(new_photo_storage_ref)
        raise
    except TripulanteConflictError:
        rollback_db(db)
        delete_media_ref(new_photo_storage_ref)
        raise
    except Exception as exc:
        rollback_db(db)
        delete_media_ref(new_photo_storage_ref)
        if psycopg2 is not None and isinstance(exc, psycopg2.IntegrityError):
            raise TripulanteConflictError("Não foi possível salvar o tripulante. Verifique se o CPF já está em uso.") from exc
        raise

    detail = fetch_tripulante_detail(db, tripulante_id=tripulante_id)
    return {
        "operation": "created" if action == "create" else "updated",
        "tripulante": detail,
    }


def delete_tripulante(*, tripulante_id: int) -> dict:
    db = get_db()
    tripulante = fetch_tripulante_delete_target(db, tripulante_id=tripulante_id)
    if not tripulante:
        raise TripulanteNotFoundError("Tripulante não encontrado.")
    dependency_counts = fetch_tripulante_dependencies(db, tripulante_id=tripulante_id)
    has_business_dependencies = any(
        int(dependency_counts.get(key) or 0) > 0
        for key in ("treinamentos", "missoes", "pernoites", "adicionais", "conferencias", "arquivos_file")
    )

    try:
        if has_business_dependencies:
            if int(tripulante["ativo"] or 0) == 0:
                raise TripulanteConflictError(
                    "Este tripulante já está inativo e possui vínculos históricos; a exclusão física foi bloqueada."
                )

            inactivate_tripulante(db, tripulante_id=tripulante_id, status="Afastado")
            sync_linked_pilot_from_tripulante(
                db,
                tripulante_id=tripulante_id,
                nome=tripulante["nome"],
                licenca_anac=tripulante["licenca_anac"],
                base_nome=tripulante["base"],
                status_text="Afastado",
                is_active=False,
            )
            audit_event(
                db,
                "tripulante",
                tripulante_id,
                "status_change",
                anterior=tripulante_audit_payload(tripulante),
                novo={**tripulante_audit_payload(tripulante), "ativo": False, "status": "Afastado"},
                observacao="Inativação automática aplicada porque existem vínculos históricos.",
            )
            db.commit()
            clear_panel_cache()
            detail = fetch_tripulante_detail(db, tripulante_id=tripulante_id)
            return {
                "operation": "inactivated",
                "tripulante": detail,
                "message": "Tripulante inativado porque existem vínculos históricos.",
            }

        linked_pilot_ids = find_linked_pilot_ids(db, tripulante_id=tripulante_id)
        if linked_pilot_ids:
            delete_historico_status_piloto_by_pilot_ids(db, linked_pilot_ids=linked_pilot_ids)
            delete_pilotos_by_ids(db, linked_pilot_ids=linked_pilot_ids)

        audit_event(db, "tripulante", tripulante_id, "delete", anterior=tripulante_audit_payload(tripulante))
        delete_tripulante_row(db, tripulante_id=tripulante_id)
        db.commit()
        delete_media_ref(tripulante.get("foto_storage_ref"))
        clear_panel_cache()
        return {
            "operation": "deleted",
            "tripulante_id": tripulante_id,
            "message": "Tripulante excluído com sucesso.",
        }
    except TripulanteConflictError:
        rollback_db(db)
        raise
    except Exception:
        rollback_db(db)
        raise
