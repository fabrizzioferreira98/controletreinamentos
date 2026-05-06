from __future__ import annotations

from collections.abc import Mapping

LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD = "aeronave_modelo"
TRAINING_AIRCRAFT_MODEL_REFERENCE_FIELD = "aeronave_modelo_referencia"
TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD = "aeronave_modelo_snapshot"
TRAINING_AIRCRAFT_MODEL_ROLE_FIELD = "aeronave_modelo_role"

TRAINING_AIRCRAFT_MODEL_REFERENCE_ROLE = "referencia_programa"
TRAINING_AIRCRAFT_MODEL_SNAPSHOT_ROLE = "snapshot_realizado"
TRAINING_AIRCRAFT_MODEL_COMPAT_ALIAS_ROLE = "compat_alias_residual"

TRAINING_AIRCRAFT_MODEL_REFERENCE_OWNER = "horas_voo_aeronave(tipo_treinamento_id, aeronave_modelo)"
TRAINING_AIRCRAFT_MODEL_TRAINING_STORAGE_COLUMN = "treinamentos.aeronave_modelo"
TRAINING_AIRCRAFT_MODEL_FUTURE_EXIT_CONDITION = (
    "renomear fisicamente treinamentos.aeronave_modelo para aeronave_modelo_snapshot "
    "depois que serializers, filtros, relatorios, imports e consumidores externos usarem apenas o campo explicito"
)

TRAINING_AIRCRAFT_MODEL_SEMANTIC_CONTRACT = {
    "reference_owner": TRAINING_AIRCRAFT_MODEL_REFERENCE_OWNER,
    "training_storage_column": TRAINING_AIRCRAFT_MODEL_TRAINING_STORAGE_COLUMN,
    "training_storage_role": TRAINING_AIRCRAFT_MODEL_SNAPSHOT_ROLE,
    "reference_field": TRAINING_AIRCRAFT_MODEL_REFERENCE_FIELD,
    "snapshot_field": TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD,
    "legacy_alias": LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD,
    "legacy_alias_role": TRAINING_AIRCRAFT_MODEL_COMPAT_ALIAS_ROLE,
    "future_exit_condition": TRAINING_AIRCRAFT_MODEL_FUTURE_EXIT_CONDITION,
}

TRAINING_RECORD_ORIGIN_FIELD = "origem_registro"
TRAINING_RECORD_ORIGIN_GENERAL = "treinamento_geral"
TRAINING_RECORD_ORIGIN_PROGRAM = "programa_tripulante"


def normalize_training_aircraft_model(value) -> str | None:
    raw = str(value or "").strip()
    return raw or None


def resolve_training_aircraft_model_reference(source: Mapping[str, object] | None) -> str | None:
    if source is None:
        return None
    return normalize_training_aircraft_model(
        source.get(TRAINING_AIRCRAFT_MODEL_REFERENCE_FIELD) or source.get(LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD)
    )


def resolve_training_aircraft_model_snapshot(source: Mapping[str, object] | None) -> str | None:
    if source is None:
        return None
    return normalize_training_aircraft_model(
        source.get(TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD) or source.get(LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD)
    )


def build_training_aircraft_reference_contract(value) -> dict[str, str]:
    reference = normalize_training_aircraft_model(value) or ""
    return {
        TRAINING_AIRCRAFT_MODEL_REFERENCE_FIELD: reference,
        LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD: reference,
        TRAINING_AIRCRAFT_MODEL_ROLE_FIELD: TRAINING_AIRCRAFT_MODEL_REFERENCE_ROLE if reference else "",
    }


def build_training_aircraft_snapshot_contract(source: Mapping[str, object] | None) -> dict[str, str]:
    snapshot = resolve_training_aircraft_model_snapshot(source) or ""
    return {
        TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD: snapshot,
        LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD: snapshot,
        TRAINING_AIRCRAFT_MODEL_ROLE_FIELD: TRAINING_AIRCRAFT_MODEL_SNAPSHOT_ROLE if snapshot else "",
    }


def training_aircraft_model_semantic_contract() -> dict[str, str]:
    return dict(TRAINING_AIRCRAFT_MODEL_SEMANTIC_CONTRACT)


def is_training_program_record(source: Mapping[str, object] | None) -> bool:
    if source is None:
        return False
    if source.get("segmento_teorico_id") is not None:
        return True
    if resolve_training_aircraft_model_snapshot(source):
        return True
    return any(
        source.get(field) is not None
        for field in (
            "ctac_solo_horas",
            "ctac_voo_pic_sic_horas",
            "ctac_voo_crew_horas",
        )
    )


def resolve_training_record_origin(source: Mapping[str, object] | None) -> str:
    return TRAINING_RECORD_ORIGIN_PROGRAM if is_training_program_record(source) else TRAINING_RECORD_ORIGIN_GENERAL
