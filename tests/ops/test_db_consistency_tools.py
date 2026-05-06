from backend.src.controle_treinamentos.db import _expected_tables_from_schema, schema_consistency_report


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, tables: set[str], columns: dict[str, set[str]]):
        self._tables = tables
        self._columns = columns

    def execute(self, query, params=None):
        params = params or ()
        compact_query = " ".join(query.split())
        if "FROM information_schema.tables" in compact_query:
            return _FakeCursor([{"table_name": table} for table in sorted(self._tables)])
        if "FROM information_schema.columns" in compact_query:
            table_name = params[0]
            return _FakeCursor([{"column_name": col} for col in sorted(self._columns.get(table_name, set()))])
        raise AssertionError(f"Unexpected query: {query}")


def test_expected_tables_extracts_core_tables():
    tables = _expected_tables_from_schema()
    assert "usuarios" in tables
    assert "tripulantes" in tables
    assert "pernoites_operacionais" in tables
    assert "treinamento_anexos_pdf" in tables
    assert len(tables) == len(set(tables))


def test_schema_consistency_report_flags_missing_tables_and_columns():
    fake_db = _FakeDB(
        tables={"usuarios", "tripulantes", "treinamentos"},
        columns={
            "usuarios": {"id", "nome", "login", "email", "senha_hash", "perfil", "ativo"},
            "tripulantes": {"id", "nome", "cpf", "licenca_anac", "base", "status"},
            "treinamentos": {"id", "tripulante_id", "tipo_treinamento_id"},
        },
    )

    report = schema_consistency_report(fake_db)

    assert report["is_consistent"] is False
    assert "pernoites_operacionais" in report["missing_tables"]
    assert "usuarios" in report["missing_columns"]
    assert "permissao_modulos_json" in report["missing_columns"]["usuarios"]
