from backend.src.controle_treinamentos.db.migrations import _schema_statements


def test_schema_statements_split_tables_and_indexes():
    table_statements = _schema_statements(kind="tables")
    index_statements = _schema_statements(kind="indexes")

    assert table_statements
    assert index_statements
    assert all(statement.startswith("CREATE TABLE IF NOT EXISTS") for statement in table_statements)
    assert all("INDEX IF NOT EXISTS" in statement for statement in index_statements)
    assert any("tipos_treinamento" in statement for statement in table_statements)
    assert any("uq_tipos_treinamento_codigo" in statement for statement in index_statements)
