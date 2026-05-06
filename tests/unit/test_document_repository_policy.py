from backend.src.controle_treinamentos.repositories.treinamentos import (
    create_treinamento_attachment_record,
    delete_treinamento_attachment_record,
    fetch_treinamento_attachments,
)
from backend.src.controle_treinamentos.repositories.tripulante_files import insert_tripulante_file


class _FakeCursor:
    def __init__(self, row=None, rows=None):
        self._row = row or {"id": 123}
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self):
        self.executed = []

    def execute(self, query, params=()):
        self.executed.append((query, params))
        return _FakeCursor()


def _pdf_payload():
    return {
        "nome_original": "Documento.pdf",
        "nome_interno": "documento-abc.pdf",
        "mime_type": "application/pdf",
        "tamanho_bytes": 18,
        "storage_ref": "fs:tripulantes/tripulante-7/documentos/documento-abc.pdf",
        "arquivo_pdf": b"%PDF-1.4\n%%EOF",
        "arquivo_hash": "hash",
    }


def test_insert_tripulante_file_does_not_store_database_blob_for_filesystem_ref():
    db = _FakeDB()

    insert_tripulante_file(
        db,
        tripulante_id=7,
        tipo_documento="geral",
        payload=_pdf_payload(),
        enviado_por=3,
    )

    _query, params = db.executed[0]
    assert params[6] == "fs:tripulantes/tripulante-7/documentos/documento-abc.pdf"
    assert params[7] is None


def test_create_treinamento_attachment_record_does_not_store_database_blob_for_filesystem_ref():
    db = _FakeDB()
    payload = _pdf_payload()
    payload["nome_interno"] = "anexo-abc.pdf"
    payload["storage_ref"] = "fs:treinamentos/treinamento-55/anexos/anexo-abc.pdf"

    create_treinamento_attachment_record(db, treinamento_id=55, parsed=payload, enviado_por=3)

    _query, params = db.executed[0]
    assert params[5] == "fs:treinamentos/treinamento-55/anexos/anexo-abc.pdf"
    assert params[6] is None


def test_insert_tripulante_file_does_not_rehydrate_legacy_db_blob_without_explicit_opt_in():
    db = _FakeDB()
    payload = _pdf_payload()
    payload["storage_ref"] = "db:bytea"

    insert_tripulante_file(
        db,
        tripulante_id=7,
        tipo_documento="geral",
        payload=payload,
        enviado_por=3,
    )

    _query, params = db.executed[0]
    assert params[6] == "db:bytea"
    assert params[7] is None


def test_delete_treinamento_attachment_record_is_soft_delete():
    db = _FakeDB()

    delete_treinamento_attachment_record(db, treinamento_id=55, anexo_id=77, removido_por=3)

    query, params = db.executed[0]
    assert "UPDATE treinamento_anexos_pdf" in query
    assert "status = 'removido'" in query
    assert "DELETE FROM treinamento_anexos_pdf" not in query
    assert params == (3, "Removido manualmente.", 77, 55)


def test_fetch_treinamento_attachments_hides_removed_by_default():
    db = _FakeDB()

    fetch_treinamento_attachments(db, treinamento_id=55)

    query, params = db.executed[0]
    assert "removido" in query
    assert params == (55,)
