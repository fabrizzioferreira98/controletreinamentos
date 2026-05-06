from datetime import date

from backend.src.controle_treinamentos.services import (
    add_months,
    build_expiry_status,
    calculate_training_status,
    summarize_training_status,
    training_sort_key,
    resolve_expiry_status,
)


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


def test_add_months_preserves_end_of_month_and_leap_year_boundaries():
    assert add_months("2026-01-31", 1) == "2026-02-28"
    assert add_months("2024-01-31", 1) == "2024-02-29"
    assert add_months("2026-02-28", 12) == "2027-02-28"
    assert add_months("2026-03-15", 0) is None
    assert add_months("data-invalida", 6) is None


def test_training_status_summary_counts_known_statuses():
    sem_informacao = calculate_training_status(None, reference=date(2026, 1, 1))
    rows = [
        {"status_calculado": "vencido"},
        {"status_calculado": "a vencer"},
        {"status_calculado": "a vencer"},
        {"status_calculado": "regular"},
        {"status_calculado": sem_informacao},
    ]

    assert summarize_training_status(rows) == {
        "total": 5,
        "vencido": 1,
        "a vencer": 2,
        "regular": 1,
        sem_informacao: 1,
    }


def test_training_sort_key_prioritizes_risk_then_due_date_then_type_name():
    rows = [
        {"status_calculado": "regular", "data_vencimento": "2026-01-01", "tipo_treinamento_nome": "B"},
        {"status_calculado": "vencido", "data_vencimento": "2026-03-01", "tipo_treinamento_nome": "C"},
        {"status_calculado": "a vencer", "data_vencimento": "2026-02-01", "tipo_treinamento_nome": "A"},
        {"status_calculado": "vencido", "data_vencimento": "2026-01-15", "tipo_treinamento_nome": "A"},
    ]

    ordered = sorted(rows, key=training_sort_key)

    assert [item["tipo_treinamento_nome"] for item in ordered] == ["A", "C", "A", "B"]
