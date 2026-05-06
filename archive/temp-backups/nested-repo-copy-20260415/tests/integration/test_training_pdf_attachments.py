import io

import pytest
from werkzeug.datastructures import FileStorage

from backend.src.controle_treinamentos.service_layers.domain_validation import validate_pdf_upload, validate_tripulante_file_upload


def make_upload(content: bytes, filename: str = "arquivo.pdf", mimetype: str = "application/pdf"):
    return FileStorage(stream=io.BytesIO(content), filename=filename, content_type=mimetype)


def test_validate_pdf_upload_accepts_valid_pdf():
    upload = make_upload(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF")
    parsed = validate_pdf_upload(upload)
    assert parsed["mime_type"] == "application/pdf"
    assert parsed["nome_original"].endswith(".pdf")
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


def test_validate_pdf_upload_rejects_pdf_without_eof_marker():
    upload = make_upload(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", filename="x.pdf", mimetype="application/pdf")
    with pytest.raises(ValueError):
        validate_pdf_upload(upload)


def test_validate_tripulante_file_upload_accepts_valid_pdf():
    upload = make_upload(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF", filename="documento.pdf")
    parsed = validate_tripulante_file_upload(upload)
    assert parsed["mime_type"] == "application/pdf"
    assert parsed["nome_original"] == "documento.pdf"
    assert parsed["arquivo_hash"]


def test_validate_tripulante_file_upload_rejects_empty():
    upload = make_upload(b"", filename="vazio.pdf")
    with pytest.raises(ValueError):
        validate_tripulante_file_upload(upload)
