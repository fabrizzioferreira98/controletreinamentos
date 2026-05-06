from backend.src.controle_treinamentos.repositories.tripulante_files import fetch_tripulante_file_rows


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, query, params):
        self.executed.append((query, params))
        return _FakeCursor(self.rows)


def test_fetch_tripulante_file_rows_uses_consolidated_sources():
    expected_rows = [{"id": 10, "origem": "tripulante_file"}, {"id": 99, "origem": "treinamento"}]
    db = _FakeDB(expected_rows)

    rows = fetch_tripulante_file_rows(db, tripulante_id=42)

    assert rows == expected_rows
    assert len(db.executed) == 1
    query, params = db.executed[0]
    assert "FROM tripulante_arquivos_pdf" in query
    assert "FROM treinamento_anexos_pdf" in query
    assert "UNION ALL" in query
    assert params == (42, 42)


def test_fetch_tripulante_file_rows_can_disable_training_source():
    expected_rows = [{"id": 10, "origem": "tripulante_file"}]
    db = _FakeDB(expected_rows)

    rows = fetch_tripulante_file_rows(db, tripulante_id=42, include_training=False)

    assert rows == expected_rows
    assert len(db.executed) == 1
    query, params = db.executed[0]
    assert "FROM tripulante_arquivos_pdf" in query
    assert "treinamento_anexos_pdf" not in query
    assert "UNION ALL" not in query
    assert params == (42,)
