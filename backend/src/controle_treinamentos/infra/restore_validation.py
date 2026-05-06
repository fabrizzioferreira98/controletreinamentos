from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..core.document_storage import FILESYSTEM_STORAGE_PREFIX, storage_reference_kind
from .document_blobs import summarize_document_inventory
from .media_storage import iter_local_media_refs


CANONICAL_RESTORE_COMPONENTS = (
    "dump",
    "assets",
    "config",
    "manifest",
    "post_restore_validation",
)

_ARTIFACT_PATTERNS = {
    "dump": re.compile(r"^db_backup_(?P<stamp>\d{8}_\d{6})\.(dump|json\.gz|sqlite3\.gz)$", re.IGNORECASE),
    "assets": re.compile(r"^assets_backup_(?P<stamp>\d{8}_\d{6})\.tar\.gz$", re.IGNORECASE),
    "config": re.compile(r"^config_backup_(?P<stamp>\d{8}_\d{6})\.tar\.gz$", re.IGNORECASE),
    "manifest": re.compile(r"^backup_manifest_(?P<stamp>\d{8}_\d{6})\.json$", re.IGNORECASE),
}
_PHOTO_DATA_URI_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,", re.IGNORECASE)


@dataclass(frozen=True)
class RestoreArtifact:
    group: str
    path: str
    name: str
    stamp: str


@dataclass(frozen=True)
class RestoreArtifactSet:
    dump: RestoreArtifact | None = None
    assets: RestoreArtifact | None = None
    config: RestoreArtifact | None = None
    manifest: RestoreArtifact | None = None

    @classmethod
    def from_paths(cls, paths: Iterable[str | Path]) -> "RestoreArtifactSet":
        grouped: dict[str, RestoreArtifact | None] = {
            "dump": None,
            "assets": None,
            "config": None,
            "manifest": None,
        }
        for raw_item in paths:
            item_path = Path(str(raw_item))
            item_name = item_path.name
            for group, pattern in _ARTIFACT_PATTERNS.items():
                match = pattern.match(item_name)
                if match and grouped[group] is None:
                    grouped[group] = RestoreArtifact(
                        group=group,
                        path=str(item_path),
                        name=item_name,
                        stamp=match.group("stamp"),
                    )
                    break
        return cls(
            dump=grouped["dump"],
            assets=grouped["assets"],
            config=grouped["config"],
            manifest=grouped["manifest"],
        )

    def grouped(self) -> dict[str, RestoreArtifact | None]:
        return {
            "dump": self.dump,
            "assets": self.assets,
            "config": self.config,
            "manifest": self.manifest,
        }

    def missing_components(self) -> list[str]:
        return [group for group, artifact in self.grouped().items() if artifact is None]

    def missing_files(self) -> list[str]:
        missing: list[str] = []
        for group, artifact in self.grouped().items():
            if artifact is None:
                continue
            path = Path(artifact.path)
            if not path.exists() or not path.is_file():
                missing.append(group)
        return missing

    def window_stamp(self) -> str | None:
        for artifact in self.grouped().values():
            if artifact is not None:
                return artifact.stamp
        return None

    def load_manifest_payload(self) -> tuple[dict | None, str | None]:
        if self.manifest is None:
            return None, None
        path = Path(self.manifest.path)
        if not path.exists() or not path.is_file():
            return None, "manifest_file_missing"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return None, f"manifest_unreadable:{exc}"
        if not isinstance(payload, dict):
            return None, "manifest_invalid_payload"
        return payload, None

    def manifest_artifact_names(self, payload: dict | None) -> set[str]:
        if not payload:
            return set()
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            return set()
        names: set[str] = set()
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                names.add(name)
        return names

    def manifest_stamp(self, payload: dict | None) -> str | None:
        if not payload:
            return None
        stamp = str(payload.get("stamp") or "").strip()
        return stamp or None

    def manifest_missing_entries(self, payload: dict | None) -> list[str]:
        names = self.manifest_artifact_names(payload)
        missing: list[str] = []
        for group in ("dump", "assets", "config"):
            artifact = self.grouped().get(group)
            if artifact is not None and artifact.name not in names:
                missing.append(group)
        return missing

    def window_mismatch_components(self, *, reference_stamp: str | None = None) -> list[str]:
        expected = reference_stamp or self.window_stamp()
        if not expected:
            return []
        mismatches: list[str] = []
        for group, artifact in self.grouped().items():
            if artifact is None:
                continue
            if artifact.stamp != expected:
                mismatches.append(group)
        return mismatches

    def restore_kind(self, *, post_restore_validation_ok: bool) -> str:
        if self.missing_components():
            return "partial"
        if not post_restore_validation_ok:
            return "auxiliary"
        return "canonical"


def _as_dict_row(row) -> dict:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def _valid_legacy_photo_payload(raw_value: str | None) -> bool:
    value = str(raw_value or "").strip()
    if not value:
        return False
    if not _PHOTO_DATA_URI_RE.match(value):
        return False
    try:
        payload = value.split(",", 1)[1]
        return bool(base64.b64decode(payload, validate=True))
    except (IndexError, ValueError, binascii.Error):
        return False


def _normalize_local_storage_refs(
    local_storage_refs: list[str] | tuple[str, ...] | set[str] | None = None,
) -> set[str]:
    if local_storage_refs is None:
        return set(iter_local_media_refs())
    return {str(item or "").strip() for item in local_storage_refs if str(item or "").strip()}


def _annotate_photo_blob_state(row: dict, *, local_storage_refs: set[str]) -> dict:
    item = dict(row)
    storage_ref = str(item.get("foto_storage_ref") or "").strip()
    reference_kind = storage_reference_kind(storage_ref)
    has_legacy_blob = _valid_legacy_photo_payload(item.get("foto_base64"))
    declared_photo = bool(item.get("possui_foto"))

    if reference_kind == "filesystem":
        blob_available = storage_ref in local_storage_refs
        item.update(
            {
                "reference_kind": reference_kind,
                "blob_storage": "filesystem",
                "blob_available": blob_available,
                "blob_status": "ok" if blob_available else "missing_blob",
                "consistency_status": "consistent" if blob_available else "metadata_without_blob",
                "compat_residual": has_legacy_blob,
                "compat_source": "foto_base64" if has_legacy_blob else "",
            }
        )
        return item

    if reference_kind == "remote":
        item.update(
            {
                "reference_kind": reference_kind,
                "blob_storage": "remote",
                "blob_available": False,
                "blob_status": "remote_unverified",
                "consistency_status": "remote_reference_unverified",
                "compat_residual": False,
                "compat_source": "",
            }
        )
        return item

    if reference_kind == "missing":
        if has_legacy_blob:
            item.update(
                {
                    "reference_kind": reference_kind,
                    "blob_storage": "database",
                    "blob_available": True,
                    "blob_status": "legacy_db_blob",
                    "consistency_status": "consistent_legacy",
                    "compat_residual": True,
                    "compat_source": "foto_base64",
                }
            )
            return item
        if declared_photo:
            item.update(
                {
                    "reference_kind": reference_kind,
                    "blob_storage": "missing",
                    "blob_available": False,
                    "blob_status": "missing_reference",
                    "consistency_status": "metadata_without_reference",
                    "compat_residual": False,
                    "compat_source": "",
                }
            )
            return item
        item.update(
            {
                "reference_kind": reference_kind,
                "blob_storage": "empty",
                "blob_available": False,
                "blob_status": "not_applicable",
                "consistency_status": "empty",
                "compat_residual": False,
                "compat_source": "",
            }
        )
        return item

    item.update(
        {
            "reference_kind": reference_kind,
            "blob_storage": reference_kind,
            "blob_available": False,
            "blob_status": "unsupported_reference",
            "consistency_status": "metadata_with_unsupported_reference",
            "compat_residual": False,
            "compat_source": "",
        }
    )
    return item


def classify_photo_inventory(
    metadata_rows: list[dict] | tuple[dict, ...],
    *,
    local_storage_refs: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict:
    local_refs = _normalize_local_storage_refs(local_storage_refs)
    annotated = [_annotate_photo_blob_state(row, local_storage_refs=local_refs) for row in metadata_rows]
    referenced_refs = {
        str(row.get("foto_storage_ref") or "").strip()
        for row in metadata_rows
        if str(row.get("foto_storage_ref") or "").strip().startswith(FILESYSTEM_STORAGE_PREFIX)
    }
    orphan_blobs = sorted(
        ref for ref in local_refs if "/fotos/" in ref and ref.startswith(FILESYSTEM_STORAGE_PREFIX) and ref not in referenced_refs
    )
    return {
        "consistent": [row for row in annotated if row.get("consistency_status") == "consistent"],
        "consistent_legacy": [row for row in annotated if row.get("consistency_status") == "consistent_legacy"],
        "empty": [row for row in annotated if row.get("consistency_status") == "empty"],
        "metadata_without_blob": [row for row in annotated if row.get("consistency_status") == "metadata_without_blob"],
        "metadata_without_reference": [
            row for row in annotated if row.get("consistency_status") == "metadata_without_reference"
        ],
        "remote_reference_unverified": [
            row for row in annotated if row.get("consistency_status") == "remote_reference_unverified"
        ],
        "unsupported_reference": [
            row for row in annotated if row.get("consistency_status") == "metadata_with_unsupported_reference"
        ],
        "orphan_blobs": orphan_blobs,
    }


def summarize_photo_inventory(
    metadata_rows: list[dict] | tuple[dict, ...],
    *,
    local_storage_refs: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict:
    inventory = classify_photo_inventory(metadata_rows, local_storage_refs=local_storage_refs)
    counts = {
        "consistent": len(inventory["consistent"]),
        "consistent_legacy": len(inventory["consistent_legacy"]),
        "empty": len(inventory["empty"]),
        "metadata_without_blob": len(inventory["metadata_without_blob"]),
        "metadata_without_reference": len(inventory["metadata_without_reference"]),
        "remote_reference_unverified": len(inventory["remote_reference_unverified"]),
        "unsupported_reference": len(inventory["unsupported_reference"]),
        "orphan_blobs": len(inventory["orphan_blobs"]),
    }
    critical_count = (
        counts["metadata_without_blob"]
        + counts["metadata_without_reference"]
        + counts["unsupported_reference"]
    )
    warning_count = counts["consistent_legacy"] + counts["remote_reference_unverified"] + counts["orphan_blobs"]
    if critical_count:
        status_key = "degraded"
    elif warning_count:
        status_key = "attention"
    else:
        status_key = "operational"
    return {
        "inventory": inventory,
        "counts": counts,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "compat_residual_count": counts["consistent_legacy"],
        "problem_count": critical_count + warning_count,
        "status_key": status_key,
    }


def summarize_restore_metadata_blob_consistency(
    document_rows: list[dict] | tuple[dict, ...],
    photo_rows: list[dict] | tuple[dict, ...],
    *,
    local_storage_refs: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict:
    local_refs = _normalize_local_storage_refs(local_storage_refs)
    documents = summarize_document_inventory(document_rows, local_storage_refs=local_refs)
    photos = summarize_photo_inventory(photo_rows, local_storage_refs=local_refs)
    critical_count = int(documents["critical_count"]) + int(photos["critical_count"])
    warning_count = int(documents["warning_count"]) + int(photos["warning_count"])
    if critical_count:
        status_key = "degraded"
    elif warning_count:
        status_key = "attention"
    else:
        status_key = "operational"
    return {
        "documents": documents,
        "photos": photos,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "compat_residual_count": int(photos["compat_residual_count"]),
        "problem_count": critical_count + warning_count,
        "status_key": status_key,
    }


def fetch_restore_metadata_rows(db) -> dict:
    errors: list[str] = []
    document_rows: list[dict] = []
    photo_rows: list[dict] = []

    document_queries = (
        """
        SELECT
            id,
            'treinamento_anexos_pdf' AS source_table,
            storage_ref,
            (arquivo_pdf IS NOT NULL) AS has_db_blob
        FROM treinamento_anexos_pdf
        """,
        """
        SELECT
            id,
            'tripulante_arquivos_pdf' AS source_table,
            storage_ref,
            (arquivo_pdf IS NOT NULL) AS has_db_blob
        FROM tripulante_arquivos_pdf
        """,
    )
    for query in document_queries:
        try:
            document_rows.extend(_as_dict_row(row) for row in db.execute(query).fetchall())
        except Exception as exc:
            errors.append(str(exc))

    try:
        rows = db.execute(
            """
            SELECT
                id,
                foto_storage_ref,
                foto_base64,
                COALESCE(possui_foto, FALSE) AS possui_foto
            FROM tripulantes
            """
        ).fetchall()
        photo_rows = [_as_dict_row(row) for row in rows]
    except Exception as exc:
        errors.append(str(exc))

    return {
        "document_rows": document_rows,
        "photo_rows": photo_rows,
        "query_errors": errors,
    }


def run_restore_metadata_blob_validation(
    db,
    *,
    local_storage_refs: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict:
    snapshot = fetch_restore_metadata_rows(db)
    summary = summarize_restore_metadata_blob_consistency(
        snapshot["document_rows"],
        snapshot["photo_rows"],
        local_storage_refs=local_storage_refs,
    )
    query_errors = list(snapshot["query_errors"])
    if query_errors:
        summary["query_errors"] = query_errors
        summary["query_error_count"] = len(query_errors)
        summary["warning_count"] = int(summary["warning_count"]) + len(query_errors)
        summary["problem_count"] = int(summary["critical_count"]) + int(summary["warning_count"])
        if not snapshot["document_rows"] and not snapshot["photo_rows"]:
            summary["status_key"] = "unavailable"
        elif summary["status_key"] == "operational":
            summary["status_key"] = "attention"
    else:
        summary["query_errors"] = []
        summary["query_error_count"] = 0
    summary["document_row_count"] = len(snapshot["document_rows"])
    summary["photo_row_count"] = len(snapshot["photo_rows"])
    return summary


def validate_canonical_restore_contract(
    artifacts: Iterable[str | Path],
    *,
    metadata_blob_summary: dict | None = None,
) -> dict:
    artifact_set = RestoreArtifactSet.from_paths(artifacts)
    missing_components = artifact_set.missing_components()
    missing_files = artifact_set.missing_files()
    manifest_payload, manifest_error = artifact_set.load_manifest_payload()
    manifest_stamp = artifact_set.manifest_stamp(manifest_payload)
    window_reference_stamp = manifest_stamp or artifact_set.window_stamp()
    window_mismatch_components = artifact_set.window_mismatch_components(reference_stamp=window_reference_stamp)
    manifest_missing_entries = artifact_set.manifest_missing_entries(manifest_payload)
    post_restore_validation_ok = metadata_blob_summary is not None and int(metadata_blob_summary.get("critical_count") or 0) == 0
    artifact_bundle_ready = (
        not missing_components
        and not missing_files
        and not manifest_error
        and not window_mismatch_components
        and not manifest_missing_entries
    )
    restore_kind = artifact_set.restore_kind(post_restore_validation_ok=post_restore_validation_ok)
    return {
        "success": bool(artifact_bundle_ready and post_restore_validation_ok),
        "restore_kind": restore_kind,
        "required_components": list(CANONICAL_RESTORE_COMPONENTS),
        "artifact_bundle_ready": artifact_bundle_ready,
        "missing_components": missing_components,
        "missing_files": missing_files,
        "window_reference_stamp": window_reference_stamp or "",
        "window_mismatch_components": window_mismatch_components,
        "manifest_error": manifest_error or "",
        "manifest_missing_entries": manifest_missing_entries,
        "post_restore_validation_ok": post_restore_validation_ok,
        "metadata_blob_status": (metadata_blob_summary or {}).get("status_key") or "",
        "metadata_blob_critical_count": int((metadata_blob_summary or {}).get("critical_count") or 0),
        "metadata_blob_warning_count": int((metadata_blob_summary or {}).get("warning_count") or 0),
    }
