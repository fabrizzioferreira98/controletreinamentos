from datetime import date

from backend.src.controle_treinamentos.services import build_expiry_status, resolve_expiry_status


def test_expiry_status_thresholds():
    assert resolve_expiry_status(-1)["key"] == "vencido"
    assert resolve_expiry_status(0)["key"] == "critico_15"
    assert resolve_expiry_status(15)["key"] == "critico_15"
    assert resolve_expiry_status(16)["key"] == "vencer_30"
    assert resolve_expiry_status(30)["key"] == "vencer_30"
    assert resolve_expiry_status(31)["key"] == "vencer_60"
    assert resolve_expiry_status(60)["key"] == "vencer_60"
    assert resolve_expiry_status(61)["key"] == "vencer_90"
    assert resolve_expiry_status(90)["key"] == "vencer_90"
    assert resolve_expiry_status(91)["key"] == "em_dia"
    assert resolve_expiry_status(None)["key"] == "sem_vencimento"


def test_build_expiry_status_metadata():
    result = build_expiry_status("2026-03-31", reference=date(2026, 3, 23))
    assert result["key"] == "critico_15"
    assert result["days_remaining"] == 8
    assert result["due_date_label"] == "31/03/2026"
