from pathlib import Path

from backend.src.controle_treinamentos.infra.document_blobs import find_orphan_media_refs
from backend.src.controle_treinamentos.infra.restore_validation import (
    RestoreArtifactSet,
    summarize_photo_inventory,
    summarize_restore_metadata_blob_consistency,
    validate_canonical_restore_contract,
)


def _write_manifest(target: Path, *, stamp: str, artifact_names: list[str]) -> None:
    target.write_text(
        (
            "{\n"
            '  "generated_at": "2026-04-16T12:00:00",\n'
            f'  "stamp": "{stamp}",\n'
            '  "artifacts": [\n'
            + ",\n".join(f'    {{"name": "{name}"}}' for name in artifact_names)
            + "\n  ]\n}\n"
        ),
        encoding="utf-8",
    )


def test_restore_artifact_set_detects_core_components(tmp_path):
    stamp = "20260416_120000"
    paths = [
        tmp_path / f"db_backup_{stamp}.dump",
        tmp_path / f"assets_backup_{stamp}.tar.gz",
        tmp_path / f"config_backup_{stamp}.tar.gz",
        tmp_path / f"backup_manifest_{stamp}.json",
    ]
    for path in paths[:3]:
        path.write_bytes(b"ok")
    _write_manifest(paths[3], stamp=stamp, artifact_names=[path.name for path in paths[:3]])

    artifact_set = RestoreArtifactSet.from_paths(paths)

    assert artifact_set.missing_components() == []
    assert artifact_set.missing_files() == []
    assert artifact_set.window_stamp() == stamp


def test_validate_canonical_restore_contract_requires_post_restore_validation(tmp_path):
    stamp = "20260416_120000"
    dump = tmp_path / f"db_backup_{stamp}.dump"
    assets = tmp_path / f"assets_backup_{stamp}.tar.gz"
    config = tmp_path / f"config_backup_{stamp}.tar.gz"
    manifest = tmp_path / f"backup_manifest_{stamp}.json"
    for path in (dump, assets, config):
        path.write_bytes(b"ok")
    _write_manifest(manifest, stamp=stamp, artifact_names=[dump.name, assets.name, config.name])

    result = validate_canonical_restore_contract([dump, assets, config, manifest])

    assert result["artifact_bundle_ready"] is True
    assert result["restore_kind"] == "auxiliary"
    assert result["success"] is False
    assert result["missing_components"] == []


def test_validate_canonical_restore_contract_rejects_mixed_window(tmp_path):
    dump = tmp_path / "db_backup_20260416_120000.dump"
    assets = tmp_path / "assets_backup_20260416_120500.tar.gz"
    config = tmp_path / "config_backup_20260416_120000.tar.gz"
    manifest = tmp_path / "backup_manifest_20260416_120000.json"
    for path in (dump, assets, config):
        path.write_bytes(b"ok")
    _write_manifest(manifest, stamp="20260416_120000", artifact_names=[dump.name, assets.name, config.name])

    result = validate_canonical_restore_contract([dump, assets, config, manifest])

    assert result["artifact_bundle_ready"] is False
    assert result["window_mismatch_components"] == ["assets"]
    assert result["success"] is False


def test_summarize_photo_inventory_marks_legacy_but_keeps_it_visible(tmp_path):
    existing = tmp_path / "tripulantes" / "tripulante-7" / "fotos" / "foto.webp"
    orphan = tmp_path / "tripulantes" / "tripulante-8" / "fotos" / "orfao.webp"
    existing.parent.mkdir(parents=True)
    orphan.parent.mkdir(parents=True)
    existing.write_bytes(b"img")
    orphan.write_bytes(b"img")

    summary = summarize_photo_inventory(
        [
            {
                "id": 7,
                "foto_storage_ref": "fs:tripulantes/tripulante-7/fotos/foto.webp",
                "foto_base64": "",
                "possui_foto": True,
            },
            {
                "id": 9,
                "foto_storage_ref": "",
                "foto_base64": "data:image/png;base64,aGVsbG8=",
                "possui_foto": True,
            },
        ],
        local_storage_refs=[
            "fs:tripulantes/tripulante-7/fotos/foto.webp",
            "fs:tripulantes/tripulante-8/fotos/orfao.webp",
        ],
    )

    assert summary["status_key"] == "attention"
    assert summary["counts"]["consistent"] == 1
    assert summary["counts"]["consistent_legacy"] == 1
    assert summary["counts"]["orphan_blobs"] == 1
    assert summary["compat_residual_count"] == 1


def test_restore_metadata_blob_summary_detects_broken_refs_without_hiding_legacy():
    summary = summarize_restore_metadata_blob_consistency(
        [
            {"storage_ref": "fs:tripulantes/tripulante-7/documentos/ausente.pdf", "has_db_blob": False},
        ],
        [
            {
                "id": 7,
                "foto_storage_ref": "fs:tripulantes/tripulante-7/fotos/ausente.webp",
                "foto_base64": "data:image/png;base64,aGVsbG8=",
                "possui_foto": True,
            },
            {
                "id": 8,
                "foto_storage_ref": "",
                "foto_base64": "data:image/png;base64,aGVsbG8=",
                "possui_foto": True,
            },
        ],
        local_storage_refs=[],
    )

    assert summary["status_key"] == "degraded"
    assert summary["critical_count"] == 2
    assert summary["warning_count"] == 1
    assert summary["documents"]["counts"]["metadata_without_blob"] == 1
    assert summary["photos"]["counts"]["metadata_without_blob"] == 1
    assert summary["photos"]["counts"]["consistent_legacy"] == 1


def test_validate_canonical_restore_contract_accepts_validation_with_only_warnings(tmp_path):
    stamp = "20260416_120000"
    dump = tmp_path / f"db_backup_{stamp}.dump"
    assets = tmp_path / f"assets_backup_{stamp}.tar.gz"
    config = tmp_path / f"config_backup_{stamp}.tar.gz"
    manifest = tmp_path / f"backup_manifest_{stamp}.json"
    for path in (dump, assets, config):
        path.write_bytes(b"ok")
    _write_manifest(manifest, stamp=stamp, artifact_names=[dump.name, assets.name, config.name])

    metadata_blob_summary = {
        "status_key": "attention",
        "critical_count": 0,
        "warning_count": 2,
    }
    result = validate_canonical_restore_contract(
        [dump, assets, config, manifest],
        metadata_blob_summary=metadata_blob_summary,
    )

    assert result["restore_kind"] == "canonical"
    assert result["success"] is True
    assert result["metadata_blob_status"] == "attention"


def test_find_orphan_media_refs_ignores_photo_refs_for_document_inventory():
    orphan_refs = find_orphan_media_refs(
        ["fs:tripulantes/tripulante-2/documentos/documento-pre291.pdf"],
        local_storage_refs=[
            "fs:tripulantes/tripulante-2/documentos/documento-pre291.pdf",
            "fs:tripulantes/tripulante-2/fotos/foto-pre291.webp",
        ],
    )

    assert orphan_refs == []
