from __future__ import annotations

from collections.abc import Mapping

from ..training_aircraft_model import (
    LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD,
    TRAINING_AIRCRAFT_MODEL_REFERENCE_OWNER,
    TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD,
    resolve_training_aircraft_model_snapshot,
)

TRAINING_COMPLETENESS_MODE_FIELD = "modo_estrutura"
TRAINING_COMPLETENESS_MODE_SIMPLE = "simples"
TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT = "programa_segmentado"
TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC = "programa_segmentado_ctac"

TRAINING_CTAC_FIELDS = (
    "ctac_solo_horas",
    "ctac_voo_pic_sic_horas",
    "ctac_voo_crew_horas",
)

TRAINING_STRUCTURE_CONSTRAINT_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT = (
    "treinamentos_structure_no_program_fields_without_segment"
)
TRAINING_STRUCTURE_CONSTRAINT_PROGRAM_FORBIDS_EQUIPMENT = "treinamentos_structure_program_forbids_equipment"

TRAINING_STRUCTURE_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT_CHECK = """(
    segmento_teorico_id IS NOT NULL
    OR (
        NULLIF(TRIM(COALESCE(aeronave_modelo, '')), '') IS NULL
        AND ctac_solo_horas IS NULL
        AND ctac_voo_pic_sic_horas IS NULL
        AND ctac_voo_crew_horas IS NULL
    )
)"""
TRAINING_STRUCTURE_PROGRAM_FORBIDS_EQUIPMENT_CHECK = "(segmento_teorico_id IS NULL OR equipamento_id IS NULL)"

TRAINING_STRUCTURE_DB_CHECKS = {
    TRAINING_STRUCTURE_CONSTRAINT_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT: TRAINING_STRUCTURE_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT_CHECK,
    TRAINING_STRUCTURE_CONSTRAINT_PROGRAM_FORBIDS_EQUIPMENT: TRAINING_STRUCTURE_PROGRAM_FORBIDS_EQUIPMENT_CHECK,
}

TRAINING_COMPLETENESS_MATRIX = {
    TRAINING_COMPLETENESS_MODE_SIMPLE: {
        "required": (
            "tripulante_id",
            "tipo_treinamento_id",
            "data_vencimento ou data_realizacao+periodicidade_meses",
            "equipamento_id quando tipos_treinamento.exige_equipamento",
        ),
        "optional": (
            "data_realizacao",
            "observacao",
            "anexos",
            "equipamento_id quando tipos_treinamento.exige_equipamento = false",
        ),
        "forbidden": (
            "segmento_teorico_id",
            TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD,
            LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD,
            *TRAINING_CTAC_FIELDS,
        ),
        "snapshot": (),
        "db_checks": (TRAINING_STRUCTURE_CONSTRAINT_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT,),
        "application_invariants": (
            "tipo_treinamento ativo ou selecionado em edicao",
            "equipamento existe/ativo quando informado",
            "exige_equipamento decide obrigatoriedade de equipamento_id",
            "data_realizacao nao pode ser posterior a data_vencimento",
        ),
        "compat_residual": (
            "aeronave_modelo como alias legado e rejeitado em escrita generica",
        ),
    },
    TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT: {
        "required": (
            "tripulante_id",
            "tipo_treinamento_id",
            "segmento_teorico_id",
            "data_realizacao",
            f"{TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD} quando tipos_treinamento.exige_equipamento",
        ),
        "optional": (
            "data_vencimento derivada pela periodicidade do segmento",
            "observacao",
            "anexos",
        ),
        "forbidden": (
            "equipamento_id",
            "campos CTAC quando a referencia de horas nao exige CTAC",
        ),
        "snapshot": (TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD,),
        "db_checks": (
            TRAINING_STRUCTURE_CONSTRAINT_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT,
            TRAINING_STRUCTURE_CONSTRAINT_PROGRAM_FORBIDS_EQUIPMENT,
        ),
        "application_invariants": (
            "segmento_teorico_id pertence ao tipo_treinamento_id",
            f"referencia canonica de aeronave vem de {TRAINING_AIRCRAFT_MODEL_REFERENCE_OWNER}",
            "exige_equipamento decide obrigatoriedade de snapshot de aeronave",
            "CTAC so pode aparecer quando a referencia de horas exigir CTAC",
            "data_realizacao nao pode ser posterior a data_vencimento",
        ),
        "compat_residual": (
            "treinamentos.aeronave_modelo persiste fisicamente o snapshot ate rename futuro",
        ),
    },
    TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC: {
        "required": (
            "tripulante_id",
            "tipo_treinamento_id",
            "segmento_teorico_id",
            "data_realizacao",
            f"{TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD} quando tipos_treinamento.exige_equipamento",
        ),
        "optional": (
            "data_vencimento derivada pela periodicidade do segmento",
            "observacao",
            "anexos",
            *TRAINING_CTAC_FIELDS,
        ),
        "forbidden": ("equipamento_id",),
        "snapshot": (TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD,),
        "db_checks": (
            TRAINING_STRUCTURE_CONSTRAINT_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT,
            TRAINING_STRUCTURE_CONSTRAINT_PROGRAM_FORBIDS_EQUIPMENT,
        ),
        "application_invariants": (
            "segmento_teorico_id pertence ao tipo_treinamento_id",
            f"referencia canonica de aeronave vem de {TRAINING_AIRCRAFT_MODEL_REFERENCE_OWNER}",
            "exige_equipamento decide obrigatoriedade de snapshot de aeronave",
            "valores CTAC sao opcionais mesmo quando CTAC esta habilitado pela referencia",
            "data_realizacao nao pode ser posterior a data_vencimento",
        ),
        "compat_residual": (
            "treinamentos.aeronave_modelo persiste fisicamente o snapshot ate rename futuro",
        ),
    },
}


class TrainingCompletenessError(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def _value_present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _field_present(source: Mapping[str, object] | None, field_name: str) -> bool:
    if source is None:
        return False
    return _value_present(source.get(field_name))


def training_ctac_values_present(source: Mapping[str, object] | None) -> bool:
    return any(_field_present(source, field_name) for field_name in TRAINING_CTAC_FIELDS)


def training_completeness_matrix_contract() -> dict[str, dict[str, tuple[str, ...]]]:
    return {mode: dict(contract) for mode, contract in TRAINING_COMPLETENESS_MATRIX.items()}


def resolve_training_structural_mode(source: Mapping[str, object] | None) -> str:
    if source is None:
        return TRAINING_COMPLETENESS_MODE_SIMPLE
    if source.get("segmento_teorico_id") is not None:
        if bool(source.get("ctac_required")) or training_ctac_values_present(source):
            return TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC
        return TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT
    return TRAINING_COMPLETENESS_MODE_SIMPLE


def resolve_training_template_mode(*, ctac_required: bool) -> str:
    if bool(ctac_required):
        return TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC
    return TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT


def ensure_simple_training_completeness(source: Mapping[str, object] | None) -> None:
    if _field_present(source, "segmento_teorico_id"):
        raise TrainingCompletenessError(
            "Segmento teorico pertence ao fluxo de programa. Use treinamentos-tripulantes.",
            code="training_program_fields_forbidden",
        )
    if resolve_training_aircraft_model_snapshot(source):
        raise TrainingCompletenessError(
            "Snapshot de modelo de aeronave pertence ao fluxo de programa. Use treinamentos-tripulantes.",
            code="training_program_fields_forbidden",
        )
    if training_ctac_values_present(source):
        raise TrainingCompletenessError(
            "Campos CTAC pertencem ao fluxo de programa. Use treinamentos-tripulantes.",
            code="training_program_fields_forbidden",
        )


def ensure_program_training_completeness(
    source: Mapping[str, object] | None,
    *,
    requires_aircraft_model: bool,
    ctac_required: bool,
    raw_source: Mapping[str, object] | None = None,
) -> None:
    if source is None or source.get("segmento_teorico_id") is None:
        raise TrainingCompletenessError(
            "Segmento teorico e obrigatorio para treinamentos do fluxo de programa.",
            code="training_program_missing_segment",
        )

    payload = raw_source or source
    if _field_present(payload, "equipamento_id") or source.get("equipamento_id") is not None:
        raise TrainingCompletenessError(
            "Treinamentos do fluxo de programa nao aceitam equipamento_id.",
            code="training_program_equipment_not_allowed",
        )

    if requires_aircraft_model and not resolve_training_aircraft_model_snapshot(source):
        raise TrainingCompletenessError(
            "Modelo de aeronave de referencia e obrigatorio para este tipo de treinamento.",
            code="training_program_missing_aircraft_model",
        )

    if not ctac_required and (training_ctac_values_present(payload) or training_ctac_values_present(source)):
        raise TrainingCompletenessError(
            "Campos CTAC so podem ser informados quando a referencia de horas do programa exigir CTAC.",
            code="training_program_ctac_not_allowed",
        )
