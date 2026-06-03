from __future__ import annotations

from datetime import date, datetime

from flask import current_app, has_app_context

from ..core.audit_utils import audit_event, rollback_db
from ..core.domain_errors import DomainConflictError, DomainError, DomainNotFoundError, DomainValidationError
from ..db import get_db
from ..repositories.tripulante_operational_periods import (
    cancel_operational_period,
    fetch_operational_period,
    fetch_operational_periods_by_tripulante,
    find_overlapping_operational_period,
    insert_operational_period,
    tripulante_exists,
)
from ..services import parse_date

PERIODO_TIPO_FERIAS = "ferias"
PERIODO_STATUS_ATIVO = "ativo"
PERIODO_STATUS_CANCELADO = "cancelado"
OBSERVACAO_MAX_LENGTH = 180


class TripulanteOperationalPeriodValidationError(DomainValidationError):
    code = "tripulante_periodo_operacional_validation_error"


class TripulanteOperationalPeriodConflictError(DomainConflictError):
    code = "tripulante_periodo_operacional_conflict"


class TripulanteOperationalPeriodTripulanteNotFoundError(DomainNotFoundError):
    code = "tripulante_not_found"

    def __init__(self, message: str = "Tripulante n\u00e3o encontrado."):
        super().__init__(message, code=self.code, status=self.status)


class TripulanteOperationalPeriodNotFoundError(DomainNotFoundError):
    code = "tripulante_periodo_operacional_not_found"

    def __init__(self, message: str = "Per\u00edodo operacional n\u00e3o encontrado."):
        super().__init__(message, code=self.code, status=self.status)


def _clean_text(value) -> str:
    return str(value or "").strip()


def _date_iso(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)


def _datetime_iso(value) -> str | None:
    if value in (None, ""):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _required_date(payload: dict, key: str, label: str) -> date:
    raw = _clean_text(payload.get(key))
    if not raw:
        raise TripulanteOperationalPeriodValidationError(f"{label} \u00e9 obrigat\u00f3ria.")
    parsed = parse_date(raw)
    if parsed is None:
        raise TripulanteOperationalPeriodValidationError(f"{label} deve estar no formato YYYY-MM-DD.")
    return parsed


def _parse_period_payload(payload: dict) -> dict:
    tipo = _clean_text(payload.get("tipo")) or PERIODO_TIPO_FERIAS
    if tipo != PERIODO_TIPO_FERIAS:
        raise TripulanteOperationalPeriodValidationError("Tipo de per\u00edodo operacional inv\u00e1lido.")

    data_inicio = _required_date(payload, "data_inicio", "Data de in\u00edcio")
    data_fim = _required_date(payload, "data_fim", "Data de fim")
    if data_fim < data_inicio:
        raise TripulanteOperationalPeriodValidationError(
            "Data de fim das f\u00e9rias n\u00e3o pode ser anterior \u00e0 data de in\u00edcio."
        )

    observacao = _clean_text(payload.get("observacao")) or None
    if observacao and len(observacao) > OBSERVACAO_MAX_LENGTH:
        raise TripulanteOperationalPeriodValidationError(
            f"Observa\u00e7\u00e3o deve ter no m\u00e1ximo {OBSERVACAO_MAX_LENGTH} caracteres."
        )

    return {
        "tipo": tipo,
        "data_inicio": data_inicio.isoformat(),
        "data_fim": data_fim.isoformat(),
        "observacao": observacao,
    }


def serialize_operational_period(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "tripulante_id": int(row["tripulante_id"]),
        "tipo": _clean_text(row.get("tipo")) or PERIODO_TIPO_FERIAS,
        "data_inicio": _date_iso(row.get("data_inicio")),
        "data_fim": _date_iso(row.get("data_fim")),
        "status": _clean_text(row.get("status")) or PERIODO_STATUS_ATIVO,
        "observacao": row.get("observacao") or "",
        "criado_em": _datetime_iso(row.get("criado_em")),
        "cancelado_em": _datetime_iso(row.get("cancelado_em")),
    }


def _ensure_tripulante_exists(db, *, tripulante_id: int) -> None:
    if not tripulante_exists(db, tripulante_id=tripulante_id):
        raise TripulanteOperationalPeriodTripulanteNotFoundError()


def list_tripulante_operational_periods(*, tripulante_id: int) -> dict:
    db = get_db()
    _ensure_tripulante_exists(db, tripulante_id=tripulante_id)
    rows = fetch_operational_periods_by_tripulante(db, tripulante_id=tripulante_id)
    return {"items": [serialize_operational_period(row) for row in rows]}


def create_tripulante_operational_period(*, tripulante_id: int, payload: dict, actor_user_id: int | None) -> dict:
    db = get_db()
    _ensure_tripulante_exists(db, tripulante_id=tripulante_id)
    data = _parse_period_payload(payload)
    overlap = find_overlapping_operational_period(
        db,
        tripulante_id=tripulante_id,
        data_inicio=data["data_inicio"],
        data_fim=data["data_fim"],
    )
    if overlap:
        raise TripulanteOperationalPeriodConflictError(
            "J\u00e1 existe per\u00edodo de f\u00e9rias ativo que se sobrep\u00f5e ao intervalo informado.",
            code="tripulante_periodo_operacional_overlap",
        )

    try:
        created = insert_operational_period(
            db,
            data={
                **data,
                "tripulante_id": tripulante_id,
                "criado_por": actor_user_id,
            },
        )
        item = serialize_operational_period(created)
        audit_event(db, "tripulante_periodo_operacional", item["id"], "create", novo=item)
        db.commit()
    except DomainError:
        rollback_db(db)
        raise
    except Exception as exc:
        rollback_db(db)
        if has_app_context():
            current_app.logger.exception("Falha ao salvar periodo operacional do tripulante.")
        raise DomainError(
            "N\u00e3o foi poss\u00edvel salvar o per\u00edodo operacional.",
            status=500,
            code="tripulante_periodo_operacional_save_failed",
        ) from exc

    return {"item": item}


def cancel_tripulante_operational_period(*, tripulante_id: int, periodo_id: int, actor_user_id: int | None) -> dict:
    db = get_db()
    _ensure_tripulante_exists(db, tripulante_id=tripulante_id)
    current = fetch_operational_period(db, tripulante_id=tripulante_id, periodo_id=periodo_id)
    if not current:
        raise TripulanteOperationalPeriodNotFoundError()

    if _clean_text(current.get("status")) == PERIODO_STATUS_CANCELADO:
        return {"item": serialize_operational_period(current), "operation": "unchanged"}

    try:
        updated = cancel_operational_period(
            db,
            tripulante_id=tripulante_id,
            periodo_id=periodo_id,
            cancelado_por=actor_user_id,
        )
        if not updated:
            raise TripulanteOperationalPeriodNotFoundError()
        item = serialize_operational_period(updated)
        audit_event(
            db,
            "tripulante_periodo_operacional",
            item["id"],
            "cancel",
            anterior=serialize_operational_period(current),
            novo=item,
        )
        db.commit()
    except DomainError:
        rollback_db(db)
        raise
    except Exception as exc:
        rollback_db(db)
        if has_app_context():
            current_app.logger.exception("Falha ao cancelar periodo operacional do tripulante.")
        raise DomainError(
            "N\u00e3o foi poss\u00edvel cancelar o per\u00edodo operacional.",
            status=500,
            code="tripulante_periodo_operacional_cancel_failed",
        ) from exc

    return {"item": item, "operation": "cancelled"}
