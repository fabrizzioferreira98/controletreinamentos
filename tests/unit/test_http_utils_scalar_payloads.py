from decimal import Decimal

from backend.src.controle_treinamentos.core.http_utils import get_optional_decimal, get_optional_int, get_optional_text, get_required_int, get_required_text


def test_get_required_text_accepts_scalar_json_values():
    payload = {"tipo_treinamento_id": 42}

    assert get_required_text(payload, "tipo_treinamento_id", "Tipo") == "42"


def test_get_required_int_accepts_numeric_json_values():
    payload = {"tipo_treinamento_id": 42}

    assert get_required_int(payload, "tipo_treinamento_id", "Tipo") == 42


def test_get_optional_text_accepts_boolean_scalar_values():
    payload = {"ativo": True}

    assert get_optional_text(payload, "ativo") == "True"


def test_get_optional_int_accepts_numeric_json_values():
    payload = {"tripulante_id": 7}

    assert get_optional_int(payload, "tripulante_id", "Tripulante") == 7


def test_get_optional_decimal_preserves_integer_json_values():
    payload = {"solo_horas": 2}

    assert get_optional_decimal(payload, "solo_horas", "Solo horas") == Decimal("2")


def test_get_optional_decimal_preserves_float_json_values():
    payload = {"solo_horas": 2.5}

    assert get_optional_decimal(payload, "solo_horas", "Solo horas") == Decimal("2.5")

