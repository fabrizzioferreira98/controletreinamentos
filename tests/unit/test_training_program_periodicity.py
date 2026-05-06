from backend.src.controle_treinamentos.application.training_program import _normalize_periodicity


def test_normalize_periodicity_accepts_36_months():
    assert _normalize_periodicity("36") == 36
    assert _normalize_periodicity("36 meses") == 36
