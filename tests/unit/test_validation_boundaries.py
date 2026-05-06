from pathlib import Path

from backend.src.controle_treinamentos.service_layers import domain_validation, pure_validation


def test_pure_validation_has_no_db_write_or_sync_dependencies():
    source = Path(pure_validation.__file__).read_text(encoding="utf-8")

    assert "get_db" not in source
    assert "db.execute" not in source
    assert ".commit(" not in source
    assert "sync_" not in source
    assert "ensure_base_exists" not in source


def test_domain_validation_legacy_surface_does_not_expose_commands():
    assert not hasattr(domain_validation, "sync_linked_pilot_from_tripulante")
    assert not hasattr(domain_validation, "_sync_auto_pernoites_for_missao")
    assert not hasattr(domain_validation, "resolve_due_date")
    assert not hasattr(domain_validation, "validate_training_references")


def test_production_code_no_longer_imports_domain_validation():
    root = Path(__file__).resolve().parents[2] / "backend" / "src" / "controle_treinamentos"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "domain_validation.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "domain_validation" in text:
            offenders.append(path.relative_to(root).as_posix())

    assert offenders == []
