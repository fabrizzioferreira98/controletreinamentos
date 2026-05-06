from __future__ import annotations

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from ..constants import PHOTO_PREFIXES
from ..core.audit_utils import audit_event, rollback_db, tripulante_audit_payload
from ..core.domain_errors import DomainConflictError, DomainNotFoundError, DomainUnavailableError, DomainValidationError
from ..core.http_utils import (
    get_optional_date,
    get_optional_email,
    get_optional_limited_text,
    get_required_text,
    get_validated_anac_code,
    get_validated_cpf,
)
from ..db import ensure_base_exists, get_db
from ..infra.media_storage import delete_media_ref, read_media_bytes, write_tripulante_photo
from ..repositories.bases import fetch_active_base
from ..repositories.dashboard_cache import clear_panel_cache
from ..repositories.queries import resolve_tripulante_pilot_matricula
from ..repositories.tripulantes import (
    create_tripulante,
    delete_historico_status_piloto_by_pilot_ids,
    delete_pilotos_by_ids,
    fetch_tripulante_delete_target,
    fetch_tripulante_dependencies,
    fetch_tripulante_detail,
    fetch_tripulante_for_write,
    find_linked_pilot_ids,
    find_tripulante_by_cpf,
    inactivate_tripulante,
    update_tripulante,
    update_tripulante_photo_state,
)
from ..repositories.tripulantes import (
    delete_tripulante as delete_tripulante_row,
)
from ..service_layers.pure_validation import (
    validate_tripulante_categoria,
    validate_tripulante_funcao,
    validate_photo_data_uri,
    validate_tripulante_status,
)
from ..service_layers.tripulante_operational_status import (
    canonical_pilot_status,
    tripulante_base_snapshot_compat,
    tripulante_status_snapshot_from_pilot_status,
)

_KEEP_EXISTING_PHOTO = object()
_REMOVE_PHOTO = object()


class TripulanteValidationError(DomainValidationError, ValueError):
    def __init__(self, message: str, *, code: str = "tripulante_validation_error", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


class TripulanteConflictError(DomainConflictError):
    def __init__(self, message: str):
        super().__init__(message)
        self.code = "tripulante_conflict"
        self.status = 409


class TripulanteNotFoundError(DomainNotFoundError):
    code = "tripulante_not_found"
    status = 404


def _normalize_pilot_status(value: str | None):
    return canonical_pilot_status(value)


def sync_linked_pilot_from_tripulante(
    db,
    *,
    tripulante_id: int,
    nome: str,
    licenca_anac: str,
    base_nome: str,
    status_text: str,
    is_active: bool,
):
    linked_pilot = db.execute(
        "SELECT id, base_id, status FROM pilotos WHERE tripulante_id = %s",
        (tripulante_id,),
    ).fetchone()

    current_linked_base = fetch_active_base(db, linked_pilot["base_id"]) if linked_pilot and linked_pilot["base_id"] else None
    ensured_base = None
    next_base_id = current_linked_base["id"] if current_linked_base else (linked_pilot["base_id"] if linked_pilot else None)
    snapshot_base_compat = current_linked_base["nome"] if current_linked_base else tripulante_base_snapshot_compat(base_nome)
    if not linked_pilot:
        ensured_base = ensure_base_exists(db, base_nome)
        next_base_id = ensured_base["id"] if ensured_base else None
        mapped_base = db.execute(
            "SELECT id FROM bases WHERE ativa = TRUE AND LOWER(nome) = LOWER(%s)",
            (base_nome,),
        ).fetchone()
        if mapped_base:
            next_base_id = mapped_base["id"]
        resolved_base = fetch_active_base(db, next_base_id) if next_base_id else None
        if resolved_base:
            snapshot_base_compat = resolved_base["nome"]

    current_pilot_status = canonical_pilot_status(linked_pilot["status"] if linked_pilot else None)
    submitted_pilot_status = _normalize_pilot_status(status_text)
    if is_active:
        next_status = current_pilot_status or submitted_pilot_status or "ativo"
    else:
        next_status = "afastado"
    snapshot_status_compat = tripulante_status_snapshot_from_pilot_status(next_status)
    if linked_pilot:
        next_matricula = resolve_tripulante_pilot_matricula(
            db,
            tripulante_id=tripulante_id,
            licenca_anac=licenca_anac,
            current_pilot_id=linked_pilot["id"],
        )
        db.execute(
            """
            UPDATE pilotos
            SET nome = %s, matricula = %s, base_id = %s, status = %s
            WHERE id = %s
            """,
            (nome, next_matricula, next_base_id, next_status, linked_pilot["id"]),
        )
        db.execute(
            "UPDATE tripulantes SET base = %s, status = %s WHERE id = %s",
            (snapshot_base_compat, snapshot_status_compat, tripulante_id),
        )
        return

    db.execute(
        "UPDATE tripulantes SET base = %s, status = %s WHERE id = %s",
        (snapshot_base_compat, snapshot_status_compat, tripulante_id),
    )
    if next_base_id is None:
        return

    db.execute(
        """
        INSERT INTO pilotos (nome, matricula, tripulante_id, base_id, status)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (tripulante_id) DO NOTHING
        """,
        (
            nome,
            resolve_tripulante_pilot_matricula(db, tripulante_id=tripulante_id, licenca_anac=licenca_anac),
            tripulante_id,
            next_base_id,
            next_status,
        ),
    )


def _bool_value(payload, key: str) -> bool:
    raw = payload.get(key)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    return str(raw or "").strip().lower() in {"1", "true", "on", "yes", "sim"}


def _decode_photo_data_uri(raw_value: str):
    try:
        return validate_photo_data_uri(raw_value)
    except ValueError as exc:
        raise TripulanteValidationError(str(exc), code="tripulante_invalid_photo") from exc


def _resolve_photo_submission(payload):
    if _bool_value(payload, "remove_foto"):
        return _REMOVE_PHOTO
    raw_value = str(payload.get("foto_base64") or "").strip()
    if not raw_value:
        return _KEEP_EXISTING_PHOTO
    if not any(raw_value.startswith(prefix) for prefix in PHOTO_PREFIXES):
        raise TripulanteValidationError("A foto deve estar em JPG, PNG ou WEBP.", code="tripulante_invalid_photo")
    return raw_value


def _persist_tripulante_photo(*, tripulante_id: int, tripulante_name: str, submitted_value, existing_row: dict):
    if submitted_value is _KEEP_EXISTING_PHOTO:
        return {
            "foto_storage_ref": existing_row.get("foto_storage_ref"),
            "foto_mime_type": existing_row.get("foto_mime_type"),
            "possui_foto": bool(existing_row.get("possui_foto")),
            "new_storage_ref": None,
            "old_storage_ref_to_delete": None,
            "clear_legacy_photo_base64": False,
        }
    if submitted_value is _REMOVE_PHOTO:
        return {
            "foto_storage_ref": None,
            "foto_mime_type": None,
            "possui_foto": False,
            "new_storage_ref": None,
            "old_storage_ref_to_delete": existing_row.get("foto_storage_ref"),
            "clear_legacy_photo_base64": True,
        }
    raw_bytes, mime_type = _decode_photo_data_uri(submitted_value)
    new_storage_ref = write_tripulante_photo(tripulante_id, tripulante_name, raw_bytes, mime_type=mime_type)
    if read_media_bytes(new_storage_ref, fallback_bytes=None) != raw_bytes:
        delete_media_ref(new_storage_ref)
        raise DomainUnavailableError(
            "Nao foi possivel confirmar a persistencia fisica da foto.",
            code="tripulante_photo_blob_unavailable",
        )
    return {
        "foto_storage_ref": new_storage_ref,
        "foto_mime_type": mime_type,
        "possui_foto": True,
        "new_storage_ref": new_storage_ref,
        "old_storage_ref_to_delete": existing_row.get("foto_storage_ref"),
        "clear_legacy_photo_base64": True,
    }


def _parse_tripulante_payload(payload: dict) -> dict:
    try:
        data = {
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
            "sdea_icao_validade": get_optional_date(payload, "sdea_icao_validade", "Validade SDEA/ICAO"),
            "instrutor_ativo": _bool_value(payload, "instrutor_ativo"),
            "instrutor_inicio": get_optional_date(payload, "instrutor_inicio", "Início da designação de instrutor"),
            "instrutor_fim": get_optional_date(payload, "instrutor_fim", "Fim da designação de instrutor"),
            "checador_ativo": _bool_value(payload, "checador_ativo"),
            "checador_inicio": get_optional_date(payload, "checador_inicio", "Início da designação de checador"),
            "checador_fim": get_optional_date(payload, "checador_fim", "Fim da designação de checador"),
            "checador_carta_designacao": get_optional_limited_text(
                payload,
                "checador_carta_designacao",
                "Carta/designação de checador",
            ),
            "elegivel_adicional_excepcional": _bool_value(payload, "elegivel_adicional_excepcional"),
            "submitted_photo": _resolve_photo_submission(payload),
        }
        if data["instrutor_inicio"] and data["instrutor_fim"] and data["instrutor_fim"] < data["instrutor_inicio"]:
            raise ValueError("A vigência final de instrutor não pode ser anterior ao início.")
        if data["checador_inicio"] and data["checador_fim"] and data["checador_fim"] < data["checador_inicio"]:
            raise ValueError("A vigência final de checador não pode ser anterior ao início.")
        return data
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
        should_ensure_base = tripulante_id is None or not existing_row.get("piloto_base_id")
        if should_ensure_base:
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
        detail = fetch_tripulante_detail(db, tripulante_id=tripulante_id)
        audit_payload = tripulante_audit_payload(detail or {})
        if action == "create":
            audit_event(db, "tripulante", tripulante_id, "create", novo=audit_payload)
        else:
            audit_event(
                db,
                "tripulante",
                tripulante_id,
                "update",
                anterior=tripulante_audit_payload(existing_row),
                novo=audit_payload,
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
        for key in ("treinamentos", "pernoites", "arquivos_file")
    )

    try:
        if has_business_dependencies:
            if int(tripulante["ativo"] or 0) == 0:
                raise TripulanteConflictError(
                    "Este tripulante já está inativo e possui vínculos históricos; a exclusão física foi bloqueada."
                )

            inactivate_tripulante(db, tripulante_id=tripulante_id, status_snapshot_compat="Afastado")
            sync_linked_pilot_from_tripulante(
                db,
                tripulante_id=tripulante_id,
                nome=tripulante["nome"],
                licenca_anac=tripulante["licenca_anac"],
                base_nome=tripulante["base"],
                status_text="Afastado",
                is_active=False,
            )
            detail = fetch_tripulante_detail(db, tripulante_id=tripulante_id)
            audit_event(
                db,
                "tripulante",
                tripulante_id,
                "status_change",
                anterior=tripulante_audit_payload(tripulante),
                novo=tripulante_audit_payload(detail),
                observacao="Inativação automática aplicada porque existem vínculos históricos.",
            )
            db.commit()
            clear_panel_cache()
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
