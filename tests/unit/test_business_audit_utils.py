from backend.src.controle_treinamentos.core import audit_utils


class _FakeDB:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


class _Policy:
    key = "relatorio.test"
    kind = "pdf"
    domain = "test"
    renderer = "weasyprint"


def test_audit_document_generation_records_business_event(monkeypatch):
    captured = {}

    def fake_audit_event(db, entidade, entidade_id, acao, anterior=None, novo=None, observacao=None):
        captured.update(
            {
                "db": db,
                "entidade": entidade,
                "entidade_id": entidade_id,
                "acao": acao,
                "anterior": anterior,
                "novo": novo,
                "observacao": observacao,
            }
        )

    db = _FakeDB()
    monkeypatch.setattr(audit_utils, "audit_event", fake_audit_event)

    recorded = audit_utils.audit_document_generation(
        db,
        policy=_Policy,
        filename="relatorio.pdf",
        entity_id="abc",
        filters={"competencia": "2026-04"},
        details={"rows_count": 3},
        commit=True,
    )

    assert recorded is True
    assert db.committed is True
    assert captured["db"] is db
    assert captured["entidade"] == "documento_gerado"
    assert captured["entidade_id"] == 0
    assert captured["acao"] == "document_generate"
    assert captured["novo"]["policy_key"] == "relatorio.test"
    assert captured["novo"]["target_entity_id"] == "abc"
    assert captured["novo"]["filters"] == {"competencia": "2026-04"}
    assert captured["novo"]["rows_count"] == 3


def test_audit_document_generation_accepts_explicit_document_metadata(monkeypatch):
    captured = {}

    def fake_audit_event(db, entidade, entidade_id, acao, anterior=None, novo=None, observacao=None):
        captured.update({"entidade": entidade, "acao": acao, "novo": novo, "observacao": observacao})

    monkeypatch.setattr(audit_utils, "audit_event", fake_audit_event)

    recorded = audit_utils.audit_document_generation(
        _FakeDB(),
        policy_key="habilitacoes_export_csv",
        kind="csv_export",
        domain="relatorios.habilitacoes",
        renderer="habilitacoes_report_to_csv_export",
        filename="habilitacoes.csv",
    )

    assert recorded is True
    assert captured["entidade"] == "documento_gerado"
    assert captured["acao"] == "document_generate"
    assert captured["novo"]["policy_key"] == "habilitacoes_export_csv"
    assert captured["novo"]["kind"] == "csv_export"
    assert captured["novo"]["domain"] == "relatorios.habilitacoes"
    assert captured["novo"]["renderer"] == "habilitacoes_report_to_csv_export"


def test_audit_relevant_download_records_only_explicit_download(monkeypatch):
    calls = []

    def fake_audit_event(db, entidade, entidade_id, acao, anterior=None, novo=None, observacao=None):
        calls.append(
            {
                "entidade": entidade,
                "entidade_id": entidade_id,
                "acao": acao,
                "novo": novo,
                "observacao": observacao,
            }
        )

    db = _FakeDB()
    monkeypatch.setattr(audit_utils, "audit_event", fake_audit_event)

    preview_recorded = audit_utils.audit_relevant_download(
        db,
        entidade="tripulante_arquivo_pdf",
        entidade_id=44,
        policy_key="tripulante.file",
        action="preview",
        filename="documento.pdf",
        subject_id=7,
        source="api.tripulante_file",
        commit=True,
    )
    download_recorded = audit_utils.audit_relevant_download(
        db,
        entidade="tripulante_arquivo_pdf",
        entidade_id=44,
        policy_key="tripulante.file",
        action="download",
        filename="documento.pdf",
        subject_id=7,
        source="api.tripulante_file",
        commit=True,
    )

    assert preview_recorded is False
    assert download_recorded is True
    assert db.committed is True
    assert len(calls) == 1
    assert calls[0]["entidade"] == "tripulante_arquivo_pdf"
    assert calls[0]["entidade_id"] == 44
    assert calls[0]["acao"] == "download"
    assert calls[0]["novo"] == {
        "policy_key": "tripulante.file",
        "filename": "documento.pdf",
        "subject_id": 7,
        "source": "api.tripulante_file",
    }
