import os

from backend.src.controle_treinamentos.core.postgres_tools import find_postgres_binary


def _binary_name(base_name: str) -> str:
    return f"{base_name}.exe" if os.name == "nt" else base_name


def test_find_postgres_binary_uses_explicit_env_override(monkeypatch, tmp_path):
    binary_path = tmp_path / _binary_name("pg_dump")
    binary_path.write_text("stub", encoding="utf-8")
    monkeypatch.setenv("PG_DUMP_PATH", str(binary_path))
    monkeypatch.delenv("PG_BIN_DIR", raising=False)

    resolved = find_postgres_binary("pg_dump")

    assert resolved == binary_path.resolve()


def test_find_postgres_binary_uses_pg_bin_dir_when_path_not_set(monkeypatch, tmp_path):
    bin_dir = tmp_path / "postgres" / "bin"
    bin_dir.mkdir(parents=True)
    binary_path = bin_dir / _binary_name("pg_restore")
    binary_path.write_text("stub", encoding="utf-8")
    monkeypatch.delenv("PG_RESTORE_PATH", raising=False)
    monkeypatch.setenv("PG_BIN_DIR", str(bin_dir))

    resolved = find_postgres_binary("pg_restore")

    assert resolved == binary_path.resolve()
