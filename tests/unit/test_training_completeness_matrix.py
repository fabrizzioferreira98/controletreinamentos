from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend.src.controle_treinamentos.application import training_program as training_program_app
from backend.src.controle_treinamentos.contracts.training_program import (
    serialize_training_program_record_summary,
    serialize_training_program_template,
)
from backend.src.controle_treinamentos.contracts.treinamentos import serialize_treinamento_summary
from backend.src.controle_treinamentos.service_layers.training_completeness import (
    TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT,
    TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC,
    TRAINING_COMPLETENESS_MODE_SIMPLE,
    TRAINING_CTAC_FIELDS,
    TRAINING_STRUCTURE_CONSTRAINT_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT,
    TRAINING_STRUCTURE_CONSTRAINT_PROGRAM_FORBIDS_EQUIPMENT,
    TRAINING_STRUCTURE_DB_CHECKS,
    TrainingCompletenessError,
    ensure_program_training_completeness,
    ensure_simple_training_completeness,
    resolve_training_structural_mode,
    training_completeness_matrix_contract,
)
from backend.src.controle_treinamentos.training_aircraft_model import (
    LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD,
    TRAINING_AIRCRAFT_MODEL_REFERENCE_OWNER,
    TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD,
)


def _program_record(**overrides):
    payload = {
        "id": 88,
        "tripulante_id": 7,
        "tripulante_nome": "Lucas Silva",
        "tripulante_matricula": "123456",
        "tipo_treinamento_id": 4,
        "tipo_treinamento_nome": "Treinamento Periodico",
        "tipo_treinamento_codigo": "T4",
        "segmento_teorico_id": 26,
        "nome_segmento": "Operacoes Autorizadas",
        "modelo_segmento": "Gerais",
        "aeronave_modelo_snapshot": "King Air B200/200/C90A/C90GT",
        "data_realizacao": "2026-04-01",
        "data_vencimento": "2027-04-01",
        "observacao": "",
        "periodicidade_meses": 12,
        "status_calculado": "regular",
        "ctac_required": False,
        "ctac_solo_horas": None,
        "ctac_voo_pic_sic_horas": None,
        "ctac_voo_crew_horas": None,
        "total_anexos": 0,
    }
    payload.update(overrides)
    return payload


def test_resolve_training_structural_mode_identifies_real_modes():
    assert resolve_training_structural_mode({"id": 1, "tripulante_id": 7, "tipo_treinamento_id": 2}) == TRAINING_COMPLETENESS_MODE_SIMPLE
    assert resolve_training_structural_mode(_program_record()) == TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT
    assert (
        resolve_training_structural_mode(_program_record(ctac_required=True))
        == TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC
    )


def test_training_completeness_matrix_declares_required_optional_forbidden_and_snapshot_fields():
    matrix = training_completeness_matrix_contract()

    assert set(matrix) == {
        TRAINING_COMPLETENESS_MODE_SIMPLE,
        TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT,
        TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC,
    }

    simple = matrix[TRAINING_COMPLETENESS_MODE_SIMPLE]
    assert "segmento_teorico_id" in simple["forbidden"]
    assert TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD in simple["forbidden"]
    assert LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD in simple["forbidden"]
    assert all(field in simple["forbidden"] for field in TRAINING_CTAC_FIELDS)
    assert simple["snapshot"] == ()

    program = matrix[TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT]
    assert "segmento_teorico_id" in program["required"]
    assert any(TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD in item for item in program["required"])
    assert "equipamento_id" in program["forbidden"]
    assert TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD in program["snapshot"]
    assert TRAINING_STRUCTURE_CONSTRAINT_PROGRAM_FORBIDS_EQUIPMENT in program["db_checks"]

    program_ctac = matrix[TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC]
    assert all(field in program_ctac["optional"] for field in TRAINING_CTAC_FIELDS)
    assert program_ctac["forbidden"] == ("equipamento_id",)


def test_training_completeness_contract_separates_db_checks_application_invariants_and_compat():
    no_program_fields_check = TRAINING_STRUCTURE_DB_CHECKS[
        TRAINING_STRUCTURE_CONSTRAINT_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT
    ]
    program_forbids_equipment_check = TRAINING_STRUCTURE_DB_CHECKS[
        TRAINING_STRUCTURE_CONSTRAINT_PROGRAM_FORBIDS_EQUIPMENT
    ]

    assert "segmento_teorico_id IS NOT NULL" in no_program_fields_check
    assert "aeronave_modelo" in no_program_fields_check
    assert "ctac_solo_horas IS NULL" in no_program_fields_check
    assert "segmento_teorico_id IS NULL OR equipamento_id IS NULL" in program_forbids_equipment_check

    matrix = training_completeness_matrix_contract()
    program = matrix[TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT]

    assert any(TRAINING_AIRCRAFT_MODEL_REFERENCE_OWNER in item for item in program["application_invariants"])
    assert any("segmento_teorico_id pertence" in item for item in program["application_invariants"])
    assert any("exige_equipamento" in item for item in program["application_invariants"])
    assert any("treinamentos.aeronave_modelo persiste fisicamente" in item for item in program["compat_residual"])


def test_schema_and_legacy_migration_install_structural_training_checks():
    schema = Path("backend/src/controle_treinamentos/db/schema.py").read_text(encoding="utf-8")
    migrations = Path("backend/src/controle_treinamentos/db/migrations.py").read_text(encoding="utf-8")

    for constraint_name in (
        TRAINING_STRUCTURE_CONSTRAINT_NO_PROGRAM_FIELDS_WITHOUT_SEGMENT,
        TRAINING_STRUCTURE_CONSTRAINT_PROGRAM_FORBIDS_EQUIPMENT,
    ):
        assert f"CONSTRAINT {constraint_name}" in schema
        assert f"conname = '{constraint_name}'" in migrations
        assert f"ADD CONSTRAINT {constraint_name}" in migrations

    assert "NULLIF(TRIM(COALESCE(aeronave_modelo, '')), '') IS NULL" in schema
    assert "NULLIF(TRIM(COALESCE(aeronave_modelo, '')), '') IS NULL" in migrations
    assert "segmento_teorico_id IS NULL OR equipamento_id IS NULL" in schema
    assert "segmento_teorico_id IS NULL OR equipamento_id IS NULL" in migrations
    assert "NOT VALID" in migrations


def test_simple_training_completeness_rejects_program_fields():
    with pytest.raises(TrainingCompletenessError) as exc:
        ensure_simple_training_completeness(
            {
                "tripulante_id": 7,
                "tipo_treinamento_id": 2,
                "segmento_teorico_id": 26,
            }
        )

    assert exc.value.code == "training_program_fields_forbidden"


def test_program_training_completeness_requires_segment_and_forbids_equipment_mix():
    with pytest.raises(TrainingCompletenessError) as missing_segment:
        ensure_program_training_completeness(
            {
                "tripulante_id": 7,
                "tipo_treinamento_id": 4,
                "equipamento_id": None,
                "data_realizacao": "2026-04-01",
            },
            requires_aircraft_model=False,
            ctac_required=False,
        )

    assert missing_segment.value.code == "training_program_missing_segment"

    with pytest.raises(TrainingCompletenessError) as mixed_equipment:
        ensure_program_training_completeness(
            {
                "tripulante_id": 7,
                "tipo_treinamento_id": 4,
                "segmento_teorico_id": 26,
                "equipamento_id": 3,
                "data_realizacao": "2026-04-01",
            },
            requires_aircraft_model=False,
            ctac_required=False,
        )

    assert mixed_equipment.value.code == "training_program_equipment_not_allowed"


def test_program_training_completeness_rejects_ctac_when_reference_does_not_require_it():
    with pytest.raises(TrainingCompletenessError) as exc:
        ensure_program_training_completeness(
            _program_record(),
            requires_aircraft_model=True,
            ctac_required=False,
            raw_source={
                "segmento_id": 26,
                "data_realizacao": "2026-04-01",
                "ctac_solo_horas": "1.5",
            },
        )

    assert exc.value.code == "training_program_ctac_not_allowed"


def test_parse_batch_segment_item_preserves_ctac_null_until_explicit_input():
    segment_lookup = {
        26: {
            "id": 26,
            "nome_segmento": "Operacoes Autorizadas",
            "periodicidade_meses": 12,
        }
    }

    item = training_program_app._parse_batch_segment_item(
        {"segmento_id": 26, "data_realizacao": "2026-04-01"},
        segment_lookup=segment_lookup,
        ctac_required=True,
    )

    assert item["ctac_solo_horas"] is None
    assert item["ctac_voo_pic_sic_horas"] is None
    assert item["ctac_voo_crew_horas"] is None

    explicit_item = training_program_app._parse_batch_segment_item(
        {
            "segmento_id": 26,
            "data_realizacao": "2026-04-01",
            "ctac_solo_horas": "1.5",
        },
        segment_lookup=segment_lookup,
        ctac_required=True,
    )

    assert explicit_item["ctac_solo_horas"] == Decimal("1.5")


def test_training_contracts_expose_structural_mode_without_hiding_legacy_snapshot():
    simple_payload = serialize_treinamento_summary(
        {
            "id": 55,
            "tripulante_id": 7,
            "equipamento_id": 3,
            "tipo_treinamento_id": 2,
            "tripulante_nome": "Lucas Silva",
            "equipamento_nome": "AS350",
            "tipo_treinamento_nome": "CQ IFR",
            "data_realizacao": "2026-04-01",
            "data_vencimento": "2026-10-01",
            "observacao": "",
            "status_calculado": "regular",
        }
    )
    program_payload = serialize_training_program_record_summary(_program_record())
    program_ctac_payload = serialize_training_program_record_summary(_program_record(ctac_required=True))
    template_payload = serialize_training_program_template(
        {
            "tipo": {
                "id": 4,
                "nome": "Treinamento Periodico",
                "codigo": "T4",
                "descricao": "",
                "periodicidade_meses": 24,
                "exige_equipamento": 1,
                "ativo": 1,
                "total_segmentos": 1,
                "total_horas_voo": 1,
            },
            "aeronave_modelo_referencia": "King Air B200/200/C90A/C90GT",
            "ctac_required": True,
            "horas_voo": None,
            "segmentos": [],
        }
    )

    assert simple_payload["modo_estrutura"] == TRAINING_COMPLETENESS_MODE_SIMPLE
    assert program_payload["modo_estrutura"] == TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT
    assert program_ctac_payload["modo_estrutura"] == TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC
    assert template_payload["modo_estrutura"] == TRAINING_COMPLETENESS_MODE_PROGRAM_SEGMENT_CTAC
