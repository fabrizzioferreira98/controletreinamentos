from backend.src.controle_treinamentos.core.document_storage import (
    database_blob_for_persistence,
    document_blob_state,
    expected_storage_ref_prefix,
    storage_reference_kind,
    storage_ref_matches_policy,
)
from backend.src.controle_treinamentos.infra.document_blobs import (
    annotate_document_blob_state,
    classify_document_inventory,
    read_document_blob,
    summarize_document_inventory,
)


def test_filesystem_reference_does_not_persist_database_blob():
    payload = {
        "storage_ref": "fs:tripulantes/tripulante-7/documentos/documento-abc.pdf",
        "arquivo_pdf": b"%PDF-1.4\n%%EOF",
    }

    assert database_blob_for_persistence(payload) is None


def test_legacy_database_reference_requires_explicit_compat_write_flag():
    payload = {
        "storage_ref": "db:bytea",
        "arquivo_pdf": b"%PDF-1.4\n%%EOF",
    }

    assert database_blob_for_persistence(payload) is None
    assert database_blob_for_persistence(payload, allow_legacy_database_blob=True) == b"%PDF-1.4\n%%EOF"


def test_missing_or_external_reference_does_not_persist_database_blob():
    assert database_blob_for_persistence({"storage_ref": "", "arquivo_pdf": b"blob"}) is None
    assert database_blob_for_persistence({"storage_ref": "s3://bucket/doc.pdf", "arquivo_pdf": b"blob"}) is None
    assert database_blob_for_persistence({"storage_ref": "custom:doc", "arquivo_pdf": b"blob"}) is None


def test_document_blob_state_marks_missing_filesystem_blob():
    state = document_blob_state(
        {"storage_ref": "fs:tripulantes/tripulante-7/documentos/missing.pdf"},
        filesystem_exists=False,
    )

    assert state["blob_storage"] == "filesystem"
    assert state["blob_available"] is False
    assert state["blob_status"] == "missing_blob"
    assert state["consistency_status"] == "metadata_without_blob"


def test_remote_document_reference_is_unverified_not_available():
    state = document_blob_state({"storage_ref": "s3://bucket/path/documento.pdf", "arquivo_pdf": b"fallback"})

    assert storage_reference_kind("s3://bucket/path/documento.pdf") == "remote"
    assert state["blob_storage"] == "remote"
    assert state["blob_available"] is False
    assert state["blob_status"] == "remote_unverified"
    assert state["consistency_status"] == "remote_reference_unverified"
    assert state["compat_residual"] is False


def test_document_blob_state_marks_legacy_db_blob_as_compat_residual():
    state = document_blob_state({"storage_ref": "db:bytea", "arquivo_pdf": b"%PDF-1.4\n%%EOF"})

    assert state["blob_storage"] == "database"
    assert state["blob_available"] is True
    assert state["blob_status"] == "legacy_db_blob"
    assert state["compat_residual"] is True
    assert state["compat_source"] == "db:bytea"


def test_persistence_policy_matches_canonical_training_attachment_path():
    storage_ref = "fs:treinamentos/treinamento-55/anexos/anexo-abc.pdf"

    assert expected_storage_ref_prefix("training_attachment", treinamento_id=55) == (
        "fs:treinamentos/treinamento-55/anexos/"
    )
    assert storage_ref_matches_policy("training_attachment", storage_ref, treinamento_id=55) is True
    assert storage_ref_matches_policy("training_attachment", storage_ref, treinamento_id=56) is False


def test_persistence_policy_rejects_improvised_or_nested_storage_refs():
    assert storage_ref_matches_policy(
        "tripulante_document",
        "fs:tripulantes/tripulante-7/documentos/../escape.pdf",
        tripulante_id=7,
    ) is False
    assert storage_ref_matches_policy(
        "tripulante_document",
        "fs:tripulantes/tripulante-7/documentos/nested/documento.pdf",
        tripulante_id=7,
    ) is False
    assert storage_ref_matches_policy(
        "tripulante_document",
        "fs:tripulantes\\tripulante-7\\documentos\\documento.pdf",
        tripulante_id=7,
    ) is False


def test_read_document_blob_does_not_fallback_when_filesystem_reference_is_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    row = {
        "storage_ref": "fs:tripulantes/tripulante-7/documentos/missing.pdf",
        "arquivo_pdf": b"legacy-fallback",
    }

    assert read_document_blob(row) is None


def test_read_document_blob_does_not_fallback_for_remote_or_unsupported_refs():
    assert read_document_blob({"storage_ref": "s3://bucket/doc.pdf", "arquivo_pdf": b"fallback"}) is None
    assert read_document_blob({"storage_ref": "custom:doc", "arquivo_pdf": b"fallback"}) is None


def test_read_document_blob_keeps_legacy_database_fallback_available():
    assert read_document_blob({"storage_ref": "db:bytea", "arquivo_pdf": b"%PDF-1.4\n%%EOF"}) == b"%PDF-1.4\n%%EOF"


def test_annotate_document_blob_state_marks_existing_filesystem_blob(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    target = tmp_path / "tripulantes" / "tripulante-7" / "documentos" / "documento.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4\n%%EOF")

    row = annotate_document_blob_state(
        {"storage_ref": "fs:tripulantes/tripulante-7/documentos/documento.pdf", "has_db_blob": False}
    )

    assert row["blob_storage"] == "filesystem"
    assert row["blob_available"] is True
    assert row["blob_status"] == "ok"
    assert row["consistency_status"] == "consistent"
    assert row["compat_residual"] is False


def test_classify_document_inventory_separates_metadata_and_orphan_blobs(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    existing = tmp_path / "tripulantes" / "tripulante-7" / "documentos" / "documento.pdf"
    orphan = tmp_path / "treinamentos" / "treinamento-55" / "anexos" / "orfao.pdf"
    existing.parent.mkdir(parents=True)
    orphan.parent.mkdir(parents=True)
    existing.write_bytes(b"%PDF-1.4\n%%EOF")
    orphan.write_bytes(b"%PDF-1.4\n%%EOF")

    inventory = classify_document_inventory(
        [
            {"storage_ref": "fs:tripulantes/tripulante-7/documentos/documento.pdf", "has_db_blob": False},
            {"storage_ref": "fs:tripulantes/tripulante-7/documentos/ausente.pdf", "has_db_blob": False},
            {"storage_ref": "db:bytea", "arquivo_pdf": b"%PDF-1.4\n%%EOF"},
            {"storage_ref": "s3://bucket/remoto.pdf", "arquivo_pdf": b"fallback"},
        ],
        local_storage_refs=[
            "fs:tripulantes/tripulante-7/documentos/documento.pdf",
            "fs:treinamentos/treinamento-55/anexos/orfao.pdf",
        ],
    )

    assert len(inventory["consistent"]) == 2
    assert len(inventory["metadata_without_blob"]) == 1
    assert len(inventory["remote_reference_unverified"]) == 1
    assert inventory["orphan_blobs"] == ["fs:treinamentos/treinamento-55/anexos/orfao.pdf"]


def test_summarize_document_inventory_turns_classic_risks_into_counts(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    orphan = tmp_path / "treinamentos" / "treinamento-55" / "anexos" / "orfao.pdf"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"%PDF-1.4\n%%EOF")

    summary = summarize_document_inventory(
        [
            {"storage_ref": "fs:tripulantes/tripulante-7/documentos/ausente.pdf", "has_db_blob": False},
            {"storage_ref": "", "has_db_blob": False},
            {"storage_ref": "custom:doc", "has_db_blob": False},
        ],
        local_storage_refs=["fs:treinamentos/treinamento-55/anexos/orfao.pdf"],
    )

    assert summary["status_key"] == "degraded"
    assert summary["critical_count"] == 3
    assert summary["warning_count"] == 1
    assert summary["counts"]["metadata_without_blob"] == 1
    assert summary["counts"]["metadata_without_reference"] == 1
    assert summary["counts"]["unsupported_reference"] == 1
    assert summary["counts"]["orphan_blobs"] == 1
