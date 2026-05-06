from __future__ import annotations

import unicodedata
from datetime import datetime

from flask import current_app, has_app_context

from ..audit import record_audit_event
from ..core.domain_errors import DomainConflictError, DomainError, DomainNotFoundError, DomainValidationError
from ..db import get_db
from ..repositories.bases import (
    fetch_active_base,
    fetch_pilot_detail,
    fetch_pilot_history,
    fetch_tripulante_for_pilot_link,
    find_pilot_by_matricula,
    find_pilot_by_tripulante_id,
    insert_pilot,
    insert_pilot_history,
    update_pilot_base,
    update_pilot_status,
    update_tripulante_from_pilot,
)
from ..repositories.dashboard_cache import clear_panel_cache

PILOT_STATUS_META = {
    "ativo": {"key": "ativo", "label": "Ativo", "class": "status-green", "marker_class": "status-marker-green"},
    "folga": {"key": "folga", "label": "Folga", "class": "status-yellow", "marker_class": "status-marker-yellow"},
    "ferias": {"key": "ferias", "label": "F\u00e9rias", "class": "status-blue", "marker_class": "status-marker-blue"},
    "atestado": {"key": "atestado", "label": "Atestado", "class": "status-red", "marker_class": "status-marker-red"},
    "afastado": {"key": "afastado", "label": "Afastado", "class": "status-dark", "marker_class": "status-marker-dark"},
    "treinamento": {"key": "treinamento", "label": "Treinamento", "class": "status-purple", "marker_class": "status-marker-purple"},
}
UNKNOWN_PILOT_STATUS_KEY = "desconhecido"
UNKNOWN_PILOT_STATUS_META = {
    "key": UNKNOWN_PILOT_STATUS_KEY,
    "label": "Status nao mapeado",
    "class": "status-dark",
    "marker_class": "status-marker-dark",
}
_STATUS_CANONICAL_MAP = {
    "ativo": "ativo",
    "folga": "folga",
    "ferias": "ferias",
    "atestado": "atestado",
    "afastado": "afastado",
    "treinamento": "treinamento",
}


def canonical_pilot_status(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.strip().lower()
    return _STATUS_CANONICAL_MAP.get(normalized)


def pilot_status_meta(value: str | None, *, pilot_id: int | None = None) -> dict:
    canonical = canonical_pilot_status(value)
    if canonical:
        return PILOT_STATUS_META[canonical]
    if has_app_context():
        current_app.logger.warning(
            "Status de piloto nao canonico detectado em Gestao de Bases. pilot_id=%s status_raw=%r",
            pilot_id,
            value,
        )
    return UNKNOWN_PILOT_STATUS_META


def _text(payload: dict, key: str, default: str = "") -> str:
    return str(payload.get(key, default) or "").strip()


def _optional_int(raw_value, *, message: str) -> int | None:
    raw = str(raw_value or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError(message) from exc


def _required_int(raw_value, *, message: str) -> int:
    parsed = _optional_int(raw_value, message=message)
    if parsed is None:
        raise DomainValidationError(message)
    return parsed


def _audit_event(db, *, entidade: str, entidade_id: int, acao: str, realizado_por: int, anterior=None, novo=None, observacao=None) -> None:
    strict_mode = bool(current_app.config.get("AUDIT_STRICT_MODE", False)) if has_app_context() else False
    try:
        db.execute("SAVEPOINT audit_event_bases_use_case_sp")
        record_audit_event(
            db,
            entidade=entidade,
            entidade_id=entidade_id,
            acao=acao,
            realizado_por=realizado_por,
            payload_anterior=anterior,
            payload_novo=novo,
            observacao=observacao,
        )
        db.execute("RELEASE SAVEPOINT audit_event_bases_use_case_sp")
    except Exception as exc:
        try:
            db.execute("ROLLBACK TO SAVEPOINT audit_event_bases_use_case_sp")
        except Exception:
            db.conn.rollback()
        if strict_mode:
            raise DomainError("Falha ao persistir auditoria em modo estrito.", status=500, code="audit_failed") from exc
        if has_app_context():
            current_app.logger.exception("Falha ao registrar evento de auditoria em bases.")


def _sync_tripulante_from_pilot(db, *, tripulante_id: int, nome: str, base_id: int, status: str) -> None:
    base = fetch_active_base(db, base_id)
    if not base:
        return
    canonical_status = canonical_pilot_status(status)
    if canonical_status:
        status_label = PILOT_STATUS_META[canonical_status]["label"]
    else:
        status_label = (status or "").strip() or UNKNOWN_PILOT_STATUS_META["label"]
        if has_app_context():
            current_app.logger.warning(
                "Status legado mantido ao sincronizar tripulante a partir de piloto. tripulante_id=%s status_raw=%r",
                tripulante_id,
                status,
            )
    update_tripulante_from_pilot(
        db,
        tripulante_id=tripulante_id,
        nome=nome,
        base_snapshot_compat_nome=base["nome"],
        status_snapshot_compat_label=status_label,
        ativo=0 if canonical_status == "afastado" else 1,
    )


def add_pilot_to_base(payload: dict, *, actor_user_id: int) -> dict:
    db = get_db()
    nome = _text(payload, "nome")
    matricula = _text(payload, "matricula").upper()
    status = canonical_pilot_status(payload.get("status")) or ""
    base_id = _required_int(payload.get("base_id"), message="Base invalida.")
    tripulante_id = _optional_int(payload.get("tripulante_id"), message="Tripulante invalido.")
    observacao = _text(payload, "observacao")

    if not nome:
        raise DomainValidationError("Nome do piloto e obrigatorio.")
    if len(nome) > 160:
        raise DomainValidationError("Nome do piloto excede o limite de 160 caracteres.")
    if not status:
        raise DomainValidationError("Status invalido para o piloto.")
    if not fetch_active_base(db, base_id):
        raise DomainValidationError("A base informada nao existe ou esta inativa.")

    if tripulante_id is not None:
        tripulante = fetch_tripulante_for_pilot_link(db, tripulante_id)
        if not tripulante:
            raise DomainValidationError("Tripulante informado nao existe.")
        if find_pilot_by_tripulante_id(db, tripulante_id):
            raise DomainConflictError("Este tripulante ja esta vinculado a um piloto.")
        if not matricula:
            matricula = ((tripulante["licenca_anac"] or "").strip() or f"TRIP-{tripulante_id:06d}").upper()

    if not matricula:
        raise DomainValidationError("Matricula e obrigatoria para cadastro de piloto.")
    if len(matricula) > 32:
        raise DomainValidationError("Matricula excede o limite de 32 caracteres.")
    if find_pilot_by_matricula(db, matricula):
        raise DomainConflictError("Ja existe piloto com esta matricula.")

    try:
        created = insert_pilot(db, nome=nome, matricula=matricula, tripulante_id=tripulante_id, base_id=base_id, status=status)
        if tripulante_id:
            _sync_tripulante_from_pilot(db, tripulante_id=tripulante_id, nome=nome, base_id=base_id, status=status)
        insert_pilot_history(
            db,
            pilot_id=created["id"],
            status_anterior=None,
            status_novo=status,
            base_anterior_id=None,
            base_nova_id=base_id,
            alterado_por=actor_user_id,
            observacao=observacao or "Cadastro inicial de piloto",
        )
        _audit_event(
            db,
            entidade="piloto",
            entidade_id=created["id"],
            acao="create",
            realizado_por=actor_user_id,
            novo={"nome": nome, "matricula": matricula, "tripulante_id": tripulante_id, "base_id": base_id, "status": status},
            observacao=observacao,
        )
        db.commit()
        clear_panel_cache("bases:payload:")
    except DomainError:
        db.conn.rollback()
        raise
    except Exception as exc:
        db.conn.rollback()
        if has_app_context():
            current_app.logger.exception("Falha ao cadastrar piloto na gestao de bases.")
        raise DomainError("Nao foi possivel cadastrar o piloto.", status=500, code="base_pilot_create_failed") from exc
    return {"pilot_id": int(created["id"]), "message": "Piloto cadastrado com sucesso."}


def change_pilot_status(pilot_id: int, payload: dict, *, actor_user_id: int) -> dict:
    db = get_db()
    pilot = fetch_pilot_detail(db, pilot_id)
    if not pilot:
        raise DomainNotFoundError("Piloto nao encontrado.")
    status_novo = canonical_pilot_status(payload.get("status_novo"))
    if not status_novo:
        raise DomainValidationError("Status invalido.")
    if status_novo == pilot["status"]:
        raise DomainValidationError("O piloto ja esta com esse status.")
    observacao = _text(payload, "observacao")
    try:
        update_pilot_status(db, pilot_id=pilot_id, status=status_novo)
        if pilot["tripulante_id"]:
            _sync_tripulante_from_pilot(
                db,
                tripulante_id=pilot["tripulante_id"],
                nome=pilot["nome"],
                base_id=pilot["base_id"],
                status=status_novo,
            )
        insert_pilot_history(
            db,
            pilot_id=pilot_id,
            status_anterior=pilot["status"],
            status_novo=status_novo,
            base_anterior_id=pilot["base_id"],
            base_nova_id=pilot["base_id"],
            alterado_por=actor_user_id,
            observacao=observacao,
        )
        _audit_event(
            db,
            entidade="piloto",
            entidade_id=pilot_id,
            acao="status_update",
            realizado_por=actor_user_id,
            anterior={"status": pilot["status"], "base_id": pilot["base_id"]},
            novo={"status": status_novo, "base_id": pilot["base_id"]},
            observacao=observacao,
        )
        db.commit()
        clear_panel_cache("bases:payload:")
    except DomainError:
        db.conn.rollback()
        raise
    except Exception as exc:
        db.conn.rollback()
        if has_app_context():
            current_app.logger.exception("Falha ao atualizar status de piloto na gestao de bases.")
        raise DomainError("Nao foi possivel atualizar o status do piloto.", status=500, code="base_pilot_status_failed") from exc
    return {"message": "Status atualizado com sucesso."}


def move_pilot_to_base(pilot_id: int, payload: dict, *, actor_user_id: int) -> dict:
    db = get_db()
    pilot = fetch_pilot_detail(db, pilot_id)
    if not pilot:
        raise DomainNotFoundError("Piloto nao encontrado.")
    base_nova_id = _required_int(payload.get("base_nova_id"), message="Base de destino invalida.")
    if base_nova_id == pilot["base_id"]:
        raise DomainValidationError("Selecione uma base diferente da atual.")
    if not fetch_active_base(db, base_nova_id):
        raise DomainValidationError("A base de destino nao existe ou esta inativa.")
    observacao = _text(payload, "observacao")
    try:
        update_pilot_base(db, pilot_id=pilot_id, base_id=base_nova_id)
        if pilot["tripulante_id"]:
            _sync_tripulante_from_pilot(
                db,
                tripulante_id=pilot["tripulante_id"],
                nome=pilot["nome"],
                base_id=base_nova_id,
                status=pilot["status"],
            )
        insert_pilot_history(
            db,
            pilot_id=pilot_id,
            status_anterior=pilot["status"],
            status_novo=pilot["status"],
            base_anterior_id=pilot["base_id"],
            base_nova_id=base_nova_id,
            alterado_por=actor_user_id,
            observacao=observacao,
        )
        _audit_event(
            db,
            entidade="piloto",
            entidade_id=pilot_id,
            acao="move",
            realizado_por=actor_user_id,
            anterior={"status": pilot["status"], "base_id": pilot["base_id"]},
            novo={"status": pilot["status"], "base_id": base_nova_id},
            observacao=observacao,
        )
        db.commit()
        clear_panel_cache("bases:payload:")
    except DomainError:
        db.conn.rollback()
        raise
    except Exception as exc:
        db.conn.rollback()
        if has_app_context():
            current_app.logger.exception("Falha ao mover piloto na gestao de bases.")
        raise DomainError("Nao foi possivel mover o piloto para a nova base.", status=500, code="base_pilot_move_failed") from exc
    return {"message": "Piloto movido com sucesso."}


def _format_timestamp(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


def _format_timestamp_iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    raw = str(value).strip()
    return raw or None


def get_pilot_history(pilot_id: int) -> dict:
    db = get_db()
    pilot = fetch_pilot_detail(db, pilot_id)
    if not pilot:
        raise DomainNotFoundError("Piloto nao encontrado.")
    history = []
    for row in fetch_pilot_history(db, pilot_id):
        base_changed = row["base_anterior_id"] != row["base_nova_id"]
        status_changed = row["status_anterior"] != row["status_novo"]
        if row["status_anterior"] is None and row["base_anterior_id"] is None:
            event_type = "Cadastro inicial"
        elif base_changed and status_changed:
            event_type = "Movimentacao e atualizacao de status"
        elif base_changed:
            event_type = "Movimentacao de base"
        else:
            event_type = "Mudanca de status"
        history.append(
            {
                "id": row["id"],
                "event_type": event_type,
                "status_anterior": row["status_anterior"],
                "status_novo": row["status_novo"],
                "base_anterior_nome": row["base_anterior_nome"],
                "base_nova_nome": row["base_nova_nome"],
                "alterado_por": row["alterado_por_nome"] or "Sistema",
                "alterado_em": _format_timestamp(row["alterado_em"]),
                "alterado_em_iso": _format_timestamp_iso(row["alterado_em"]),
                "observacao": row["observacao"] or "",
            }
        )
    return {"piloto": {"id": pilot["id"], "nome": pilot["nome"], "matricula": pilot["matricula"]}, "historico": history}
