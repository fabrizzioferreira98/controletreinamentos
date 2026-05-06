from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


FS_PREFIX = "fs:"
LEGACY_RECOVERY_EVIDENCE = Path(
    "docs/migration/evidence/43.tripulante-pdfs-legado-recuperacao-system.json"
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _safe_storage_ref_path(media_root: Path, storage_ref: str | None) -> tuple[Path | None, str]:
    raw = (storage_ref or "").strip()
    if not raw.startswith(FS_PREFIX):
        return None, "not_filesystem"
    relative_raw = raw[len(FS_PREFIX) :].strip().lstrip("/")
    if not relative_raw or "\\" in relative_raw or "\x00" in relative_raw:
        return None, "invalid_ref"
    relative = PurePosixPath(relative_raw)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != relative_raw:
        return None, "invalid_ref"
    root = media_root.resolve(strict=False)
    target = root / Path(*relative.parts)
    try:
        target.resolve(strict=False).relative_to(root)
    except ValueError:
        return None, "outside_media_root"
    return target, "ok"


def _file_probe(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "exists": False,
        "readable": False,
        "size_bytes": None,
        "sha256": "",
        "pdf_signature": False,
        "error": "",
        "classification": "missing",
    }
    try:
        if not path.exists():
            return result
        if not path.is_file():
            result["exists"] = True
            result["classification"] = "not_file"
            return result
        result["exists"] = True
        result["size_bytes"] = path.stat().st_size
        digest = hashlib.sha256()
        first = b""
        with path.open("rb") as handle:
            first = handle.read(5)
            digest.update(first)
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        result["readable"] = True
        result["sha256"] = digest.hexdigest()
        result["pdf_signature"] = first == b"%PDF-"
        result["classification"] = "readable_pdf" if result["pdf_signature"] else "readable_not_pdf"
        return result
    except PermissionError as exc:
        result["error"] = f"PermissionError: {exc}"
        result["classification"] = "blocked_by_acl"
        return result
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["classification"] = "os_error"
        return result


def _canonical_ref_prefix(tripulante_id: int) -> str:
    return f"{FS_PREFIX}tripulantes/tripulante-{int(tripulante_id)}/documentos/"


def _load_legacy_recovery(repo_root: Path) -> dict[int, dict[str, Any]]:
    evidence_path = repo_root / LEGACY_RECOVERY_EVIDENCE
    if not evidence_path.exists():
        return {}
    data = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    loaded: dict[int, dict[str, Any]] = {}
    for item in data.get("items") or []:
        try:
            loaded[int(item["id"])] = item
        except (KeyError, TypeError, ValueError):
            continue
    return loaded


def _query_rows(conn) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                a.id,
                a.tripulante_id,
                t.nome AS tripulante_nome,
                a.tipo_documento,
                a.nome_original,
                a.nome_interno,
                a.mime_type,
                a.tamanho_bytes,
                a.storage_ref,
                a.arquivo_hash,
                (a.arquivo_pdf IS NOT NULL) AS has_db_blob,
                CASE WHEN a.arquivo_pdf IS NULL THEN 0 ELSE octet_length(a.arquivo_pdf) END AS db_blob_bytes,
                COALESCE(NULLIF(TRIM(a.status), ''), 'ativo') AS status,
                a.enviado_por,
                a.enviado_em,
                a.substitui_arquivo_id,
                a.removido_por,
                a.removido_em,
                a.motivo_status
            FROM tripulante_arquivos_pdf a
            LEFT JOIN tripulantes t ON t.id = a.tripulante_id
            ORDER BY a.tripulante_id, a.id
            """
        )
        rows = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT
                conrelid::regclass::text AS table_name,
                conname,
                pg_get_constraintdef(oid) AS definition
            FROM pg_constraint
            WHERE confrelid = 'public.tripulante_arquivos_pdf'::regclass
            ORDER BY table_name, conname
            """
        )
        fk_rows = [dict(row) for row in cur.fetchall()]
    return rows, fk_rows


def _scan_storage(media_root: Path, referenced_paths: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    storage_files: list[dict[str, Any]] = []
    scan_errors: list[dict[str, Any]] = []
    tripulantes_root = media_root / "tripulantes"
    try:
        candidates = list(tripulantes_root.glob("*/documentos/*.pdf"))
    except PermissionError as exc:
        scan_errors.append(
            {
                "path": str(tripulantes_root),
                "classification": "blocked_by_acl",
                "error": f"PermissionError: {exc}",
            }
        )
        return [], scan_errors
    except OSError as exc:
        scan_errors.append(
            {
                "path": str(tripulantes_root),
                "classification": "os_error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return [], scan_errors

    for path in candidates:
        probe = _file_probe(path)
        probe["referenced_by_db"] = str(path.resolve(strict=False)) in referenced_paths
        if not probe["referenced_by_db"]:
            probe["classification"] = "orphan_storage" if probe.get("readable") else probe["classification"]
        storage_files.append(probe)
    return storage_files, scan_errors


def build_inventory(repo_root: Path, env_file: Path) -> dict[str, Any]:
    env = dict(os.environ)
    env.update(_load_env_file(env_file))
    database_url = (env.get("DATABASE_URL") or "").strip()
    media_root_raw = (env.get("MEDIA_STORAGE_ROOT") or env.get("UPLOAD_ROOT") or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL ausente.")
    if not media_root_raw:
        raise RuntimeError("MEDIA_STORAGE_ROOT/UPLOAD_ROOT ausente.")
    media_root = Path(media_root_raw)
    legacy_recovery = _load_legacy_recovery(repo_root)

    with psycopg2.connect(database_url) as conn:
        rows, fk_rows = _query_rows(conn)

    referenced_paths: set[str] = set()
    items: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    for row in rows:
        storage_ref = str(row.get("storage_ref") or "")
        status = str(row.get("status") or "ativo")
        ref_kind = "filesystem" if storage_ref.startswith(FS_PREFIX) else "database" if storage_ref == "db:bytea" else "missing" if not storage_ref else "other"
        target, ref_status = _safe_storage_ref_path(media_root, storage_ref)
        probe = _file_probe(target) if target else {
            "path": "",
            "exists": False,
            "readable": False,
            "size_bytes": None,
            "sha256": "",
            "pdf_signature": False,
            "error": "",
            "classification": ref_status,
        }
        if target and probe.get("exists"):
            referenced_paths.add(str(target.resolve(strict=False)))

        db_blob_available = bool(row.get("has_db_blob"))
        filesystem_available = bool(probe.get("readable") and probe.get("pdf_signature"))
        blob_available = filesystem_available or db_blob_available
        canonical_ref = storage_ref.startswith(_canonical_ref_prefix(int(row["tripulante_id"])))
        legacy_ref = bool(storage_ref.startswith(FS_PREFIX) and not canonical_ref)
        legacy_item = legacy_recovery.get(int(row["id"]))
        irrecoverable_confirmed = bool(
            legacy_item
            and str(legacy_item.get("classification") or "").startswith("irrecuperavel_confirmado")
            and not blob_available
        )
        if probe.get("classification") == "blocked_by_acl":
            blocked_items.append({"id": row["id"], "path": probe.get("path"), "error": probe.get("error")})

        if status == "ativo" and blob_available:
            classification = "ativo_com_blob_disponivel"
        elif status == "ativo":
            classification = "ativo_sem_blob"
        elif status == "removido":
            classification = "removido_logicamente"
        elif status == "substituido":
            classification = "substituido"
        else:
            classification = f"status_{status}"
        if irrecoverable_confirmed:
            classification = "irrecuperavel_confirmado"

        item = {
            **row,
            "reference_kind": ref_kind,
            "target_path": str(target) if target else "",
            "storage_ref_status": ref_status,
            "canonical_tripulante_ref": canonical_ref,
            "legacy_fs_ref": legacy_ref,
            "filesystem_probe": probe,
            "blob_available": blob_available,
            "classification": classification,
            "irrecoverable_confirmed": irrecoverable_confirmed,
        }
        items.append(item)

    storage_files, storage_scan_errors = _scan_storage(media_root, referenced_paths)
    orphans = [item for item in storage_files if item.get("classification") == "orphan_storage"]

    by_status = Counter(str(item["status"]) for item in items)
    by_classification = Counter(str(item["classification"]) for item in items)
    referenced_existing_paths = {
        item["target_path"]
        for item in items
        if item.get("target_path")
        and item.get("filesystem_probe", {}).get("exists")
        and item.get("filesystem_probe", {}).get("readable")
    }
    referenced_existing_files = [
        item
        for item in items
        if item.get("target_path") in referenced_existing_paths
    ]
    physical_delete_paths = sorted(set(referenced_existing_paths) | {str(Path(o["path"])) for o in orphans})
    db_blob_rows = [item for item in items if item.get("has_db_blob")]

    active_rows = [item for item in items if item.get("status") == "ativo"]
    removed_rows = [item for item in items if item.get("status") == "removido"]
    missing_blob_rows = [item for item in items if not item.get("blob_available")]
    summary = {
        "records_total": len(items),
        "records_by_status": dict(sorted(by_status.items())),
        "records_by_classification": dict(sorted(by_classification.items())),
        "active_with_blob_available": len([item for item in active_rows if item.get("blob_available")]),
        "active_without_blob": len([item for item in active_rows if not item.get("blob_available")]),
        "removed_logically": by_classification.get("removido_logicamente", 0),
        "removed_logically_with_blob": len([item for item in removed_rows if item.get("blob_available")]),
        "removed_logically_without_blob": len([item for item in removed_rows if not item.get("blob_available")]),
        "substituido": by_classification.get("substituido", 0),
        "legacy_fs_refs": sum(1 for item in items if item.get("legacy_fs_ref")),
        "legacy_fs_refs_available": sum(1 for item in items if item.get("legacy_fs_ref") and item.get("blob_available")),
        "legacy_fs_refs_missing_blob": sum(1 for item in items if item.get("legacy_fs_ref") and not item.get("blob_available")),
        "canonical_fs_refs": sum(1 for item in items if item.get("canonical_tripulante_ref")),
        "db_blob_rows": len(db_blob_rows),
        "db_blob_bytes": sum(int(item.get("db_blob_bytes") or 0) for item in db_blob_rows),
        "referenced_physical_files_existing": len(referenced_existing_paths),
        "referenced_physical_bytes": sum(
            int(item.get("filesystem_probe", {}).get("size_bytes") or 0)
            for item in referenced_existing_files
            if item.get("target_path") in referenced_existing_paths
        ),
        "orphan_storage_files": len(orphans),
        "orphan_storage_bytes": sum(int(item.get("size_bytes") or 0) for item in orphans),
        "blocked_by_acl": len(blocked_items) + len([e for e in storage_scan_errors if e.get("classification") == "blocked_by_acl"]),
        "missing_blob_records": len(missing_blob_rows),
        "irrecoverable_confirmed": sum(1 for item in items if item.get("irrecoverable_confirmed")),
    }
    dry_run = {
        "destructive_execution": False,
        "strategy_candidate": "hard_delete_metadata_after_evidence_plus_physical_delete_available_blobs",
        "database_rows_that_would_be_deleted": len(items),
        "database_blob_rows_that_would_be_removed_by_row_delete": len(db_blob_rows),
        "physical_files_that_would_be_deleted": len(physical_delete_paths),
        "physical_paths_that_would_be_deleted": physical_delete_paths,
        "metadata_only_rows_due_to_missing_blob": len(missing_blob_rows),
        "already_removed_records_that_would_be_deleted_from_metadata": by_classification.get("removido_logicamente", 0),
        "pending_due_to_acl": summary["blocked_by_acl"],
        "pending_due_to_missing_blob": 0,
        "pending_total": summary["blocked_by_acl"],
    }
    return {
        "generated_at": _now_utc(),
        "mode": "dry_run_no_destructive_action",
        "environment": {
            "repo_root": str(repo_root),
            "env_file": str(env_file),
            "app_env": env.get("APP_ENV", ""),
            "database_url": "<redacted>",
            "media_storage_root": str(media_root),
            "upload_root": env.get("UPLOAD_ROOT", ""),
            "app_instance_path": env.get("APP_INSTANCE_PATH", ""),
            "workspace_runtime_root": env.get("WORKSPACE_RUNTIME_ROOT", ""),
        },
        "surface": {
            "table": "tripulante_arquivos_pdf",
            "storage_domain": "tripulantes/<tripulante>/documentos/*.pdf",
            "endpoints": [
                "GET /api/v1/tripulantes/<tripulante_id>/files",
                "POST /api/v1/tripulantes/<tripulante_id>/files",
                "GET /api/v1/tripulantes/<tripulante_id>/files/<file_id>",
                "DELETE /api/v1/tripulantes/<tripulante_id>/files/<file_id>",
            ],
            "foreign_keys_referencing_tripulante_arquivos_pdf": fk_rows,
        },
        "summary": summary,
        "dry_run": dry_run,
        "items": items,
        "storage_files": storage_files,
        "storage_scan_errors": storage_scan_errors,
        "orphans": orphans,
        "blocked_items": blocked_items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run seguro para limpeza de PDFs de tripulantes.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--env-file", default=r"C:\srv\controle-treinamentos\env\prod.env")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    env_file = Path(args.env_file)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    inventory = build_inventory(repo_root=repo_root, env_file=env_file)
    output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print(json.dumps({"output": str(output), "summary": inventory["summary"], "dry_run": inventory["dry_run"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
