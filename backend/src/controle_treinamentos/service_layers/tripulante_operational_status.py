from __future__ import annotations

import unicodedata

from .pure_validation import normalize_tripulante_status

PILOT_STATUS_LABELS = {
    "ativo": "Ativo",
    "folga": "Folga",
    "ferias": "F\u00e9rias",
    "atestado": "Atestado",
    "afastado": "Afastado",
    "treinamento": "Treinamento",
}
TRIPULANTE_OPERATIONAL_STATUS_OWNER_PILOTOS = "pilotos.status"
TRIPULANTE_OPERATIONAL_BASE_OWNER_PILOTOS = "pilotos.base_id"
TRIPULANTE_OPERATIONAL_STATUS_OWNER = TRIPULANTE_OPERATIONAL_STATUS_OWNER_PILOTOS
TRIPULANTE_OPERATIONAL_BASE_OWNER = TRIPULANTE_OPERATIONAL_BASE_OWNER_PILOTOS
TRIPULANTE_STATUS_SNAPSHOT_COMPAT_SOURCE = "tripulantes.status"
TRIPULANTE_BASE_SNAPSHOT_COMPAT_SOURCE = "tripulantes.base"
TRIPULANTE_STATUS_BASE_OWNER_DECISION = {
    "status": {
        "canonical_owner": TRIPULANTE_OPERATIONAL_STATUS_OWNER,
        "snapshot_compat_source": TRIPULANTE_STATUS_SNAPSHOT_COMPAT_SOURCE,
        "snapshot_role": "compat_residual",
        "future_exit_condition": "remover tripulantes.status quando nao houver leitor/escritor residual nem rotina de bootstrap dependente",
    },
    "base": {
        "canonical_owner": TRIPULANTE_OPERATIONAL_BASE_OWNER,
        "snapshot_compat_source": TRIPULANTE_BASE_SNAPSHOT_COMPAT_SOURCE,
        "snapshot_role": "compat_residual",
        "future_exit_condition": "remover tripulantes.base quando pilotos.base_id estiver completo e restore/homologacao nao dependerem do snapshot",
    },
}
_STATUS_CANONICAL_MAP = {key: key for key in PILOT_STATUS_LABELS}


def canonical_pilot_status(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.strip().lower()
    return _STATUS_CANONICAL_MAP.get(normalized)


def pilot_status_label(value: str | None) -> str:
    canonical = canonical_pilot_status(value)
    if canonical:
        return PILOT_STATUS_LABELS[canonical]
    return (value or "").strip()


def tripulante_status_snapshot_compat(value: str | None) -> str:
    normalized = normalize_tripulante_status(value)
    if normalized:
        return normalized
    return (value or "").strip()


def tripulante_status_snapshot_from_pilot_status(value: str | None) -> str:
    return pilot_status_label(value) or tripulante_status_snapshot_compat(value)


def tripulante_base_snapshot_compat(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def build_tripulante_operational_base_contract(row: dict) -> dict:
    snapshot_compat = tripulante_base_snapshot_compat(row.get("base_snapshot_compat"))
    if not snapshot_compat:
        snapshot_compat = tripulante_base_snapshot_compat(row.get("base"))

    pilot_base_id = row.get("piloto_base_id")
    pilot_base_nome = tripulante_base_snapshot_compat(row.get("piloto_base_nome"))
    if pilot_base_id and pilot_base_nome:
        base_operacional = pilot_base_nome
    else:
        base_operacional = ""

    return {
        "base": base_operacional,
        "base_operacional": base_operacional,
        "base_operacional_id": int(pilot_base_id) if pilot_base_id is not None else None,
        "base_operacional_owner": TRIPULANTE_OPERATIONAL_BASE_OWNER,
        "base_snapshot_compat": snapshot_compat,
        "base_snapshot_compat_source": TRIPULANTE_BASE_SNAPSHOT_COMPAT_SOURCE,
    }


def build_tripulante_operational_status_contract(row: dict) -> dict:
    snapshot_compat = tripulante_status_snapshot_compat(row.get("status_snapshot_compat"))
    if not snapshot_compat:
        snapshot_compat = tripulante_status_snapshot_compat(row.get("status"))

    pilot_status = canonical_pilot_status(row.get("piloto_status"))
    if pilot_status:
        status_operacional = PILOT_STATUS_LABELS[pilot_status]
    else:
        status_operacional = ""

    return {
        "status": status_operacional,
        "status_operacional": status_operacional,
        "status_operacional_owner": TRIPULANTE_OPERATIONAL_STATUS_OWNER,
        "status_snapshot_compat": snapshot_compat,
        "status_snapshot_compat_source": TRIPULANTE_STATUS_SNAPSHOT_COMPAT_SOURCE,
    }
