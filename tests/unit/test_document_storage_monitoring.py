from backend.src.controle_treinamentos.monitoring._monitoring_impl import _build_document_storage_risk_context


class _RowsCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _DocumentRiskDB:
    def execute(self, query, _params=()):
        if "treinamento_anexos_pdf" in query:
            return _RowsCursor(
                [
                    {
                        "id": 55,
                        "source_table": "treinamento_anexos_pdf",
                        "storage_ref": "fs:treinamentos/treinamento-55/anexos/ausente.pdf",
                        "has_db_blob": False,
                    }
                ]
            )
        if "tripulante_arquivos_pdf" in query:
            return _RowsCursor([])
        raise AssertionError(f"Unexpected query: {query}")


def test_document_storage_monitoring_exposes_metadata_without_blob(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))

    context = _build_document_storage_risk_context(_DocumentRiskDB())

    assert context["status_key"] == "degraded"
    assert context["problem_count"] == 1
    assert context["critical_count"] == 1
    assert context["counts"]["metadata_without_blob"] == 1
    assert "metadata sem blob" in context["message"]

