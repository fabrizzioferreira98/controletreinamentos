from backend.src.controle_treinamentos.training_aircraft_model import (
    LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD,
    TRAINING_AIRCRAFT_MODEL_COMPAT_ALIAS_ROLE,
    TRAINING_AIRCRAFT_MODEL_REFERENCE_FIELD,
    TRAINING_AIRCRAFT_MODEL_REFERENCE_OWNER,
    TRAINING_AIRCRAFT_MODEL_REFERENCE_ROLE,
    TRAINING_AIRCRAFT_MODEL_ROLE_FIELD,
    TRAINING_AIRCRAFT_MODEL_SEMANTIC_CONTRACT,
    TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD,
    TRAINING_AIRCRAFT_MODEL_SNAPSHOT_ROLE,
    TRAINING_AIRCRAFT_MODEL_TRAINING_STORAGE_COLUMN,
    TRAINING_RECORD_ORIGIN_GENERAL,
    TRAINING_RECORD_ORIGIN_PROGRAM,
    build_training_aircraft_reference_contract,
    build_training_aircraft_snapshot_contract,
    is_training_program_record,
    resolve_training_aircraft_model_reference,
    resolve_training_aircraft_model_snapshot,
    resolve_training_record_origin,
    training_aircraft_model_semantic_contract,
)


def test_aircraft_reference_prefers_reference_field_over_legacy_alias():
    source = {
        TRAINING_AIRCRAFT_MODEL_REFERENCE_FIELD: "  King Air B200  ",
        LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD: "Legacy C90",
    }

    assert resolve_training_aircraft_model_reference(source) == "King Air B200"


def test_aircraft_snapshot_prefers_snapshot_field_over_legacy_alias():
    source = {
        TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD: "  AW119  ",
        LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD: "Legacy AW109",
    }

    assert resolve_training_aircraft_model_snapshot(source) == "AW119"


def test_aircraft_contracts_preserve_legacy_alias_with_explicit_role():
    reference_contract = build_training_aircraft_reference_contract("King Air")
    snapshot_contract = build_training_aircraft_snapshot_contract(
        {TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD: "AW119"}
    )

    assert reference_contract == {
        TRAINING_AIRCRAFT_MODEL_REFERENCE_FIELD: "King Air",
        LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD: "King Air",
        TRAINING_AIRCRAFT_MODEL_ROLE_FIELD: TRAINING_AIRCRAFT_MODEL_REFERENCE_ROLE,
    }
    assert snapshot_contract == {
        TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD: "AW119",
        LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD: "AW119",
        TRAINING_AIRCRAFT_MODEL_ROLE_FIELD: TRAINING_AIRCRAFT_MODEL_SNAPSHOT_ROLE,
    }


def test_aircraft_model_semantic_contract_demotes_training_column_to_snapshot():
    contract = training_aircraft_model_semantic_contract()

    assert contract == TRAINING_AIRCRAFT_MODEL_SEMANTIC_CONTRACT
    assert contract["reference_owner"] == TRAINING_AIRCRAFT_MODEL_REFERENCE_OWNER
    assert contract["reference_owner"].startswith("horas_voo_aeronave(")
    assert contract["training_storage_column"] == TRAINING_AIRCRAFT_MODEL_TRAINING_STORAGE_COLUMN
    assert contract["training_storage_role"] == TRAINING_AIRCRAFT_MODEL_SNAPSHOT_ROLE
    assert contract["snapshot_field"] == TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD
    assert contract["legacy_alias"] == LEGACY_TRAINING_AIRCRAFT_MODEL_FIELD
    assert contract["legacy_alias_role"] == TRAINING_AIRCRAFT_MODEL_COMPAT_ALIAS_ROLE
    assert "renomear fisicamente treinamentos.aeronave_modelo" in contract["future_exit_condition"]


def test_training_program_record_detection_matrix():
    assert is_training_program_record(None) is False
    assert is_training_program_record({"equipamento_id": 7}) is False
    assert is_training_program_record({"segmento_teorico_id": 3}) is True
    assert is_training_program_record({TRAINING_AIRCRAFT_MODEL_SNAPSHOT_FIELD: "King Air"}) is True
    assert is_training_program_record({"ctac_solo_horas": 0}) is True


def test_training_record_origin_uses_program_detection_matrix():
    assert resolve_training_record_origin({"equipamento_id": 7}) == TRAINING_RECORD_ORIGIN_GENERAL
    assert resolve_training_record_origin({"segmento_teorico_id": 3}) == TRAINING_RECORD_ORIGIN_PROGRAM
