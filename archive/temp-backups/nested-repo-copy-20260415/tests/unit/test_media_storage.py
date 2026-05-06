from pathlib import Path

import pytest

from backend.src.controle_treinamentos.infra import media_storage


def test_write_tripulante_photo_uses_tripulante_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))

    storage_ref = media_storage.write_tripulante_photo(48, "João da Silva", b"photo-bytes", mime_type="image/png")

    assert storage_ref.startswith("fs:tripulantes/48-joao-da-silva/foto/")
    target = media_storage.storage_ref_to_path(storage_ref)
    assert target == Path(tmp_path) / "tripulantes" / "48-joao-da-silva" / "foto" / target.name
    assert media_storage.read_media_bytes(storage_ref) == b"photo-bytes"


def test_write_documents_and_training_attachments_are_grouped_by_tripulante(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))

    tripulante_ref = media_storage.write_tripulante_document(48, "José Ávila", "abc_documento.pdf", b"pdf")
    treinamento_ref = media_storage.write_training_attachment(48, "José Ávila", 99, "xyz_anexo.pdf", b"pdf-training")

    assert tripulante_ref == "fs:tripulantes/48-jose-avila/documentos/abc_documento.pdf"
    assert treinamento_ref == "fs:tripulantes/48-jose-avila/treinamentos/99/xyz_anexo.pdf"
    assert media_storage.read_media_bytes(tripulante_ref) == b"pdf"
    assert media_storage.read_media_bytes(treinamento_ref) == b"pdf-training"


def test_tripulante_slug_falls_back_when_name_is_empty():
    assert media_storage.tripulante_storage_dirname(7, "") == "7-tripulante"


def test_storage_ref_to_path_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))

    with pytest.raises(ValueError):
        media_storage.storage_ref_to_path("fs:../segredo.txt")
