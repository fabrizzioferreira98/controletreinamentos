from pathlib import Path

from backend.src.controle_treinamentos.db.schema import SCHEMA


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_hourly_schema_uses_four_decimal_places_for_converted_night_hours():
    assert "horas_noturnas_convertidas NUMERIC(10,4) NOT NULL DEFAULT 0" in SCHEMA


def test_corrective_migration_preserves_hourly_night_conversion_precision():
    source = (REPO_ROOT / "backend" / "src" / "controle_treinamentos" / "db" / "migrations.py").read_text(
        encoding="utf-8"
    )

    assert "ALTER COLUMN horas_noturnas_convertidas TYPE NUMERIC(10,4)" in source
    assert "USING horas_noturnas_convertidas::NUMERIC(10,4)" in source
