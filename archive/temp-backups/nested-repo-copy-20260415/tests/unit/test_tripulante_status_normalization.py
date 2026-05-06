from backend.src.controle_treinamentos.service_layers.domain_validation import (
    tripulante_status_filter_values,
    validate_tripulante_status,
)


def test_validate_tripulante_status_normalizes_legacy_value():
    assert validate_tripulante_status("Ferias") == "Férias"


def test_validate_tripulante_status_accepts_accented_value():
    assert validate_tripulante_status("Férias") == "Férias"


def test_tripulante_status_filter_values_keeps_legacy_compatibility():
    assert tripulante_status_filter_values("Ferias") == ("Férias", "Ferias")
