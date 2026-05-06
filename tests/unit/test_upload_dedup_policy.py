from backend.src.controle_treinamentos.repositories.treinamentos import find_active_training_attachment_duplicate_hash


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self.row = row
        self.executed = []

    def execute(self, query, params):
        self.executed.append((query, params))
        return _FakeCursor(self.row)


def test_training_attachment_duplicate_policy_uses_training_record_and_active_hash():
    db = _FakeDB({"id": 7, "nome_original": "evidencia.pdf"})

    duplicate = find_active_training_attachment_duplicate_hash(
        db,
        treinamento_id=99,
        arquivo_hash="abc123",
    )

    assert duplicate["id"] == 7
    query, params = db.executed[0]
    assert "treinamento_id = %s" in query
    assert "arquivo_hash = %s" in query
    assert "status" in query
    assert "removido" in query
    assert params == (99, "abc123")
