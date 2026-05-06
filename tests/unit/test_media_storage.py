import re
from pathlib import Path

import pytest

from backend.src.controle_treinamentos.infra import media_storage


def test_write_tripulante_photo_uses_tripulante_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))

    storage_ref = media_storage.write_tripulante_photo(48, "João da Silva", b"photo-bytes", mime_type="image/png")

    assert re.match(r"^fs:tripulantes/tripulante-48/fotos/foto-[0-9a-f]{32}\.png$", storage_ref)
    target = media_storage.storage_ref_to_path(storage_ref)
    assert target == Path(tmp_path) / "tripulantes" / "tripulante-48" / "fotos" / target.name
    assert media_storage.read_media_bytes(storage_ref) == b"photo-bytes"


def test_write_documents_and_training_attachments_are_grouped_by_tripulante(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))

    tripulante_ref = media_storage.write_tripulante_document(48, "José Ávila", "abc_documento.pdf", b"pdf")
    treinamento_ref = media_storage.write_training_attachment(48, "José Ávila", 99, "xyz_anexo.pdf", b"pdf-training")

    assert tripulante_ref == "fs:tripulantes/tripulante-48/documentos/abc_documento.pdf"
    assert treinamento_ref == "fs:treinamentos/treinamento-99/anexos/xyz_anexo.pdf"
    assert media_storage.read_media_bytes(tripulante_ref) == b"pdf"
    assert media_storage.read_media_bytes(treinamento_ref) == b"pdf-training"
    assert media_storage.iter_local_media_refs() == [
        "fs:treinamentos/treinamento-99/anexos/xyz_anexo.pdf",
        "fs:tripulantes/tripulante-48/documentos/abc_documento.pdf",
    ]


def test_tripulante_dirname_is_canonical_and_legacy_helper_is_explicit():
    assert media_storage.tripulante_storage_dirname(7, "Nome Atual") == "tripulante-7"
    assert media_storage.legacy_tripulante_storage_dirname(7, "") == "7-tripulante"


def test_storage_ref_to_path_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))

    with pytest.raises(ValueError):
        media_storage.storage_ref_to_path("fs:../segredo.txt")


def test_storage_ref_to_path_rejects_windows_separator(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))

    with pytest.raises(ValueError):
        media_storage.storage_ref_to_path("fs:tripulantes\\tripulante-7\\documentos\\doc.pdf")


def test_storage_ref_to_path_keeps_legacy_refs_readable(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    legacy_file = tmp_path / "tripulantes" / "48-joao-da-silva" / "foto" / "abc.jpg"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_bytes(b"legacy")

    assert media_storage.read_media_bytes("fs:tripulantes/48-joao-da-silva/foto/abc.jpg") == b"legacy"


def test_write_document_rejects_path_like_physical_names(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))

    with pytest.raises(ValueError):
        media_storage.write_tripulante_document(48, "Joao", "../documento.pdf", b"pdf")
