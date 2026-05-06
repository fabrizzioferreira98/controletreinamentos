import io
import re
from dataclasses import replace
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from backend.src.controle_treinamentos.constants import PHOTO_ALLOWED_MIME, PHOTO_PREFIXES
from backend.src.controle_treinamentos.service_layers import pure_validation as validation_module
from backend.src.controle_treinamentos.application import treinamentos as treinamentos_app
from backend.src.controle_treinamentos.application import training_program as training_program_app
from backend.src.controle_treinamentos.application import tripulante_media as tripulante_media_app
from backend.src.controle_treinamentos.service_layers.pure_validation import (
    validate_pdf_upload,
    validate_tripulante_file_upload,
)
from backend.src.controle_treinamentos.service_layers.upload_policy import (
    TRAINING_ATTACHMENT_UPLOAD_POLICY,
    TRAINING_PROGRAM_EVIDENCE_UPLOAD_POLICY,
    TRIPULANTE_FILE_UPLOAD_POLICY,
)


def make_upload(content: bytes, filename: str = "arquivo.pdf", mimetype: str = "application/pdf"):
    return FileStorage(stream=io.BytesIO(content), filename=filename, content_type=mimetype)


def test_photo_allowlist_is_single_source_for_uploads():
    assert PHOTO_ALLOWED_MIME == ("image/jpeg", "image/png", "image/webp")
    assert "data:image/jpeg;base64," in PHOTO_PREFIXES
    assert "data:image/jpg;base64," in PHOTO_PREFIXES
    assert "data:image/png;base64," in PHOTO_PREFIXES
    assert "data:image/webp;base64," in PHOTO_PREFIXES


def test_upload_policy_declares_prioritized_file_domains():
    assert TRAINING_ATTACHMENT_UPLOAD_POLICY.accepted_extensions == (".pdf",)
    assert TRAINING_ATTACHMENT_UPLOAD_POLICY.required_permissions == ("treinamentos_anexos:create",)
    assert TRAINING_ATTACHMENT_UPLOAD_POLICY.deduplication == "reject_same_training_record_hash"
    assert TRAINING_PROGRAM_EVIDENCE_UPLOAD_POLICY.required_permissions == (
        "treinamentos:create",
        "treinamentos_anexos:create",
    )
    assert TRIPULANTE_FILE_UPLOAD_POLICY.required_permissions == ("tripulantes_file:create",)
    assert TRIPULANTE_FILE_UPLOAD_POLICY.deduplication == "reject_same_tripulante_active_hash"


def test_legacy_training_form_uses_configured_attachment_limit():
    source = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "src"
        / "controle_treinamentos"
        / "blueprints"
        / "cadastros"
        / "routes_treinamentos.py"
    ).read_text(encoding="utf-8")

    assert "attachment_max_mb=TRAINING_ATTACHMENT_MAX_MB" in source
    assert "attachment_max_mb=8" not in source


def test_validate_pdf_upload_accepts_valid_pdf():
    upload = make_upload(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF")
    parsed = validate_pdf_upload(upload)
    assert parsed["mime_type"] == "application/pdf"
    assert parsed["detected_mime_type"] == "application/pdf"
    assert parsed["upload_policy"] == "training_attachment_pdf"
    assert parsed["nome_original"].endswith(".pdf")
    assert re.match(r"^anexo-[0-9a-f]{32}\.pdf$", parsed["nome_interno"])
    assert parsed["tamanho_bytes"] > 0
    assert parsed["arquivo_pdf"].startswith(b"%PDF")


def test_validate_pdf_upload_rejects_non_pdf_signature():
    upload = make_upload(b"not-a-pdf-content", filename="x.pdf", mimetype="application/pdf")
    with pytest.raises(ValueError):
        validate_pdf_upload(upload)


def test_validate_pdf_upload_rejects_invalid_extension():
    upload = make_upload(b"%PDF-1.4\n...", filename="x.txt", mimetype="application/pdf")
    with pytest.raises(ValueError):
        validate_pdf_upload(upload)


def test_validate_pdf_upload_rejects_mismatched_declared_mime():
    upload = make_upload(
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
        filename="x.pdf",
        mimetype="text/plain",
    )
    with pytest.raises(ValueError):
        validate_pdf_upload(upload)


def test_validate_pdf_upload_accepts_octet_stream_only_after_content_checks():
    upload = make_upload(
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
        filename="x.pdf",
        mimetype="application/octet-stream",
    )
    parsed = validate_pdf_upload(upload)
    assert parsed["mime_type"] == "application/pdf"
    assert parsed["declared_mime_type"] == "application/octet-stream"


def test_validate_pdf_upload_rejects_pdf_without_eof_marker():
    upload = make_upload(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", filename="x.pdf", mimetype="application/pdf")
    with pytest.raises(ValueError):
        validate_pdf_upload(upload)


def test_validate_pdf_upload_accepts_limit_size(monkeypatch):
    monkeypatch.setattr(
        validation_module,
        "TRAINING_ATTACHMENT_UPLOAD_POLICY",
        replace(TRAINING_ATTACHMENT_UPLOAD_POLICY, max_bytes=64),
    )
    upload = make_upload(b"%PDF-1.4\n" + b"x" * (64 - 14) + b"%%EOF", filename="limite.pdf")
    parsed = validate_pdf_upload(upload)
    assert parsed["tamanho_bytes"] <= 64


def test_validate_pdf_upload_rejects_above_limit(monkeypatch):
    monkeypatch.setattr(
        validation_module,
        "TRAINING_ATTACHMENT_UPLOAD_POLICY",
        replace(TRAINING_ATTACHMENT_UPLOAD_POLICY, max_bytes=32),
    )
    upload = make_upload(b"%PDF-1.4\n" + b"x" * 32 + b"%%EOF", filename="acima.pdf")
    with pytest.raises(ValueError):
        validate_pdf_upload(upload)


def test_validate_tripulante_file_upload_accepts_valid_pdf():
    upload = make_upload(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF", filename="documento.pdf")
    parsed = validate_tripulante_file_upload(upload)
    assert parsed["mime_type"] == "application/pdf"
    assert parsed["nome_original"] == "documento.pdf"
    assert re.match(r"^documento-[0-9a-f]{32}\.pdf$", parsed["nome_interno"])
    assert parsed["arquivo_hash"]


def test_pdf_physical_name_does_not_embed_display_name():
    upload = make_upload(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF", filename="Minha Escala Assinada.pdf")
    parsed = validate_tripulante_file_upload(upload)

    assert parsed["nome_original"] == "Minha_Escala_Assinada.pdf"
    assert "Minha" not in parsed["nome_interno"]
    assert "Escala" not in parsed["nome_interno"]


def test_validate_tripulante_file_upload_rejects_empty():
    upload = make_upload(b"", filename="vazio.pdf")
    with pytest.raises(ValueError):
        validate_tripulante_file_upload(upload)


def test_tripulante_file_payload_preserves_mime_for_validator():
    payload = {
        "arquivo_bytes": b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
        "filename": "documento.pdf",
        "content_type": "application/octet-stream",
    }

    upload = tripulante_media_app._file_storage_from_payload(payload)

    assert upload.mimetype == "application/octet-stream"
    parsed = validate_tripulante_file_upload(upload)
    assert parsed["mime_type"] == "application/pdf"


def test_training_attachment_payload_sanitizes_effective_filename():
    payload = {
        "arquivo_bytes": b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
        "filename": "../Minha Evidencia.pdf",
        "content_type": "application/pdf",
    }

    upload = treinamentos_app._file_storage_from_payload(payload)

    assert upload.filename == "Minha_Evidencia.pdf"
    assert payload["filename_effective"] == "Minha_Evidencia.pdf"


def test_training_program_data_url_preserves_declared_mime_for_policy():
    encoded = "data:text/plain;base64,JVBERi0xLjQKJSVFT0Y="
    upload = training_program_app._data_url_to_file_storage(encoded, filename="evidencia.pdf")

    assert upload.mimetype == "text/plain"
    with pytest.raises(ValueError):
        validate_pdf_upload(upload)
