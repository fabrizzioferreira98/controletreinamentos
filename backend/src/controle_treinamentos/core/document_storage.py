from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final

from .legacy_blob_policy import (
    LEGACY_BLOB_READ_MODE,
    LEGACY_BLOB_WRITE_MODE,
    LEGACY_DATABASE_BLOB_COMPAT_SOURCE,
    LEGACY_PHOTO_BLOB_COMPAT_SOURCE,
)

FILESYSTEM_STORAGE_PREFIX: Final[str] = "fs:"
LEGACY_DATABASE_STORAGE_REF: Final[str] = LEGACY_DATABASE_BLOB_COMPAT_SOURCE
REMOTE_STORAGE_PREFIXES: Final[tuple[str, ...]] = ("s3://", "remote:")


@dataclass(frozen=True)
class DocumentPersistencePolicy:
    key: str
    domain: str
    storage_mode: str
    reference_kind: str
    path_prefix_template: str
    metadata_fields: tuple[str, ...]
    blob_policy: str
    reference_policy: str
    versioning_policy: str
    retention_policy: str
    deletion_policy: str
    orphan_policy: str


DOCUMENT_METADATA_FIELDS: Final[tuple[str, ...]] = (
    "storage_ref",
    "nome_original",
    "nome_interno",
    "mime_type",
    "tamanho_bytes",
    "arquivo_hash",
    "status",
)

TRIPULANTE_DOCUMENT_PERSISTENCE_POLICY: Final[DocumentPersistencePolicy] = DocumentPersistencePolicy(
    key="tripulante_document",
    domain="tripulantes.file",
    storage_mode="local_filesystem",
    reference_kind="filesystem",
    path_prefix_template="tripulantes/tripulante-{tripulante_id}/documentos/",
    metadata_fields=DOCUMENT_METADATA_FIELDS + ("tipo_documento", "enviado_por", "enviado_em"),
    blob_policy=f"new_blobs_in_filesystem; legacy_db_bytea_is_{LEGACY_BLOB_READ_MODE}; {LEGACY_BLOB_WRITE_MODE}",
    reference_policy="fs_relative_path_under_media_storage_root",
    versioning_policy="replace_creates_new_active_record_and_marks_previous_substituido",
    retention_policy="active_replaced_and_soft_deleted_document_blobs_are_retained",
    deletion_policy="soft_delete_metadata; physical_delete_only_for_failed_new_write_or_parent_hard_delete",
    orphan_policy="filesystem_blob_without_metadata_is_orphan_candidate_do_not_serve",
)

TRAINING_ATTACHMENT_PERSISTENCE_POLICY: Final[DocumentPersistencePolicy] = DocumentPersistencePolicy(
    key="training_attachment",
    domain="treinamentos.anexos",
    storage_mode="local_filesystem",
    reference_kind="filesystem",
    path_prefix_template="treinamentos/treinamento-{treinamento_id}/anexos/",
    metadata_fields=DOCUMENT_METADATA_FIELDS + ("treinamento_id", "enviado_por", "enviado_em"),
    blob_policy=f"new_blobs_in_filesystem; legacy_db_bytea_is_{LEGACY_BLOB_READ_MODE}; {LEGACY_BLOB_WRITE_MODE}",
    reference_policy="fs_relative_path_under_media_storage_root",
    versioning_policy="append_only_attachments; no_replace_flow",
    retention_policy="soft_deleted_attachment_blobs_are_retained; parent_training_hard_delete_removes_blobs_after_commit",
    deletion_policy="soft_delete_attachment; physical_delete_only_for_failed_new_write_or_parent_hard_delete",
    orphan_policy="filesystem_blob_without_metadata_is_orphan_candidate_do_not_serve",
)

TRIPULANTE_PHOTO_PERSISTENCE_POLICY: Final[DocumentPersistencePolicy] = DocumentPersistencePolicy(
    key="tripulante_photo",
    domain="tripulantes.foto",
    storage_mode="local_filesystem",
    reference_kind="filesystem",
    path_prefix_template="tripulantes/tripulante-{tripulante_id}/fotos/",
    metadata_fields=("foto_storage_ref", "foto_mime_type", "possui_foto"),
    blob_policy=f"new_blobs_in_filesystem; {LEGACY_PHOTO_BLOB_COMPAT_SOURCE}_is_{LEGACY_BLOB_READ_MODE}; {LEGACY_BLOB_WRITE_MODE}",
    reference_policy="fs_relative_path_under_media_storage_root",
    versioning_policy="replace_current_photo",
    retention_policy="old_photo_blob_deleted_after_successful_commit",
    deletion_policy="physical_delete_after_metadata_commit",
    orphan_policy="photo_blob_without_tripulante_reference_is_orphan_candidate",
)

REMOTE_DOCUMENT_PERSISTENCE_POLICY: Final[DocumentPersistencePolicy] = DocumentPersistencePolicy(
    key="remote_document",
    domain="documentos.remote",
    storage_mode="remote_not_active_for_document_blobs",
    reference_kind="remote",
    path_prefix_template="",
    metadata_fields=DOCUMENT_METADATA_FIELDS,
    blob_policy="remote_document_blob_is_not_read_or_written_by_current_document_layer",
    reference_policy="remote_refs_are_unverified_metadata_until_remote_document_adapter_exists",
    versioning_policy="not_applicable",
    retention_policy="not_applicable",
    deletion_policy="not_applicable",
    orphan_policy="remote_orphan_detection_deferred_to_remote_adapter",
)

DOCUMENT_PERSISTENCE_POLICIES: Final[dict[str, DocumentPersistencePolicy]] = {
    policy.key: policy
    for policy in (
        TRIPULANTE_DOCUMENT_PERSISTENCE_POLICY,
        TRAINING_ATTACHMENT_PERSISTENCE_POLICY,
        TRIPULANTE_PHOTO_PERSISTENCE_POLICY,
        REMOTE_DOCUMENT_PERSISTENCE_POLICY,
    )
}


def get_document_persistence_policy(key: str) -> DocumentPersistencePolicy:
    policy = DOCUMENT_PERSISTENCE_POLICIES.get((key or "").strip())
    if policy is None:
        raise KeyError(f"Politica de persistencia documental desconhecida: {key}")
    return policy


def storage_reference_kind(storage_ref: str | None) -> str:
    raw = (storage_ref or "").strip()
    if raw.startswith(FILESYSTEM_STORAGE_PREFIX):
        return "filesystem"
    if raw == LEGACY_DATABASE_STORAGE_REF:
        return "database"
    if any(raw.startswith(prefix) for prefix in REMOTE_STORAGE_PREFIXES):
        return "remote"
    if not raw:
        return "missing"
    return "external"


def database_blob_for_persistence(payload: dict, *, allow_legacy_database_blob: bool = False) -> bytes | None:
    if storage_reference_kind(payload.get("storage_ref")) != "database":
        return None
    if not allow_legacy_database_blob:
        return None
    blob = payload.get("arquivo_pdf")
    return blob if isinstance(blob, bytes) else None


def has_database_blob(row: dict) -> bool:
    if "has_db_blob" in row:
        return bool(row.get("has_db_blob"))
    return row.get("arquivo_pdf") is not None


def expected_storage_ref_prefix(policy_key: str, **context) -> str:
    policy = get_document_persistence_policy(policy_key)
    if policy.reference_kind != "filesystem":
        raise ValueError("Politica nao possui prefixo local filesystem.")
    return f"{FILESYSTEM_STORAGE_PREFIX}{policy.path_prefix_template.format(**context)}"


def _canonical_filesystem_relative_path(storage_ref: str | None) -> PurePosixPath | None:
    raw = (storage_ref or "").strip()
    if not raw.startswith(FILESYSTEM_STORAGE_PREFIX):
        return None
    relative_raw = raw[len(FILESYSTEM_STORAGE_PREFIX) :]
    if not relative_raw or "\\" in relative_raw or "\x00" in relative_raw:
        return None
    path = PurePosixPath(relative_raw)
    if path.is_absolute() or ".." in path.parts:
        return None
    if path.as_posix() != relative_raw or not path.name:
        return None
    return path


def storage_ref_matches_policy(policy_key: str, storage_ref: str | None, **context) -> bool:
    expected_prefix = expected_storage_ref_prefix(policy_key, **context)
    raw = (storage_ref or "").strip()
    if not raw.startswith(expected_prefix):
        return False
    path = _canonical_filesystem_relative_path(raw)
    if path is None:
        return False
    expected_relative = expected_prefix[len(FILESYSTEM_STORAGE_PREFIX) :].rstrip("/")
    return path.parent.as_posix() == expected_relative


def assert_storage_ref_matches_policy(policy_key: str, storage_ref: str | None, **context) -> None:
    if not storage_ref_matches_policy(policy_key, storage_ref, **context):
        raise ValueError("Referencia de storage fora da politica documental.")


def _state(
    *,
    reference_kind: str,
    blob_storage: str,
    blob_available: bool,
    blob_status: str,
    consistency_status: str,
    compat_residual: bool,
    compat_source: str,
) -> dict:
    return {
        "reference_kind": reference_kind,
        "blob_storage": blob_storage,
        "blob_available": blob_available,
        "blob_status": blob_status,
        "consistency_status": consistency_status,
        "compat_residual": compat_residual,
        "compat_source": compat_source,
    }


def document_blob_state(row: dict, *, filesystem_exists: bool | None = None) -> dict:
    reference_kind = storage_reference_kind(row.get("storage_ref"))
    if reference_kind == "filesystem":
        available = filesystem_exists is True
        return _state(
            reference_kind=reference_kind,
            blob_storage="filesystem",
            blob_available=available,
            blob_status="ok" if available else "missing_blob",
            consistency_status="consistent" if available else "metadata_without_blob",
            compat_residual=False,
            compat_source="",
        )
    if reference_kind == "database":
        available = has_database_blob(row)
        return _state(
            reference_kind=reference_kind,
            blob_storage="database",
            blob_available=available,
            blob_status="legacy_db_blob" if available else "missing_blob",
            consistency_status="consistent_legacy" if available else "metadata_without_blob",
            compat_residual=available,
            compat_source=LEGACY_DATABASE_BLOB_COMPAT_SOURCE if available else "",
        )
    if reference_kind == "remote":
        return _state(
            reference_kind=reference_kind,
            blob_storage="remote",
            blob_available=False,
            blob_status="remote_unverified",
            consistency_status="remote_reference_unverified",
            compat_residual=False,
            compat_source="",
        )
    if reference_kind == "missing":
        return _state(
            reference_kind=reference_kind,
            blob_storage="missing",
            blob_available=False,
            blob_status="missing_reference",
            consistency_status="metadata_without_reference",
            compat_residual=False,
            compat_source="",
        )
    return _state(
        reference_kind=reference_kind,
        blob_storage=reference_kind,
        blob_available=False,
        blob_status="unsupported_reference",
        consistency_status="metadata_with_unsupported_reference",
        compat_residual=False,
        compat_source="",
    )
