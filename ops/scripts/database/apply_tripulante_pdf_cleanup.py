from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

import dry_run_tripulante_pdf_cleanup as dryrun


CONFIRMATION_PHRASE = "pode apagar os PDFs de tripulantes"


def _now_utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


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


def _execution_signature(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_ids": sorted(int(item["id"]) for item in inventory.get("items", [])),
        "physical_paths": sorted(str(path) for path in inventory.get("dry_run", {}).get("physical_paths_that_would_be_deleted", [])),
        "rows": sorted(
            ({
                "id": int(item["id"]),
                "tripulante_id": int(item["tripulante_id"]),
                "status": str(item.get("status") or ""),
                "storage_ref": str(item.get("storage_ref") or ""),
                "arquivo_hash": str(item.get("arquivo_hash") or ""),
                "tamanho_bytes": int(item.get("tamanho_bytes") or 0),
                "has_db_blob": bool(item.get("has_db_blob")),
                "db_blob_bytes": int(item.get("db_blob_bytes") or 0),
                "blob_available": bool(item.get("blob_available")),
                "target_path": str(item.get("target_path") or ""),
                "classification": str(item.get("classification") or ""),
            }
            for item in inventory.get("items", [])
            ),
            key=lambda item: item["id"],
        ),
    }


def _assert_same_signature(confirmed: dict[str, Any], current: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    confirmed_sig = _execution_signature(confirmed)
    current_sig = _execution_signature(current)
    return confirmed_sig == current_sig, {
        "confirmed": confirmed_sig,
        "current": current_sig,
    }


def _query_locked_signature(conn) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("LOCK TABLE tripulante_arquivos_pdf IN ACCESS EXCLUSIVE MODE")
        cur.execute(
            """
            SELECT
                id,
                tripulante_id,
                COALESCE(NULLIF(TRIM(status), ''), 'ativo') AS status,
                storage_ref,
                arquivo_hash,
                tamanho_bytes,
                (arquivo_pdf IS NOT NULL) AS has_db_blob,
                CASE WHEN arquivo_pdf IS NULL THEN 0 ELSE octet_length(arquivo_pdf) END AS db_blob_bytes
            FROM tripulante_arquivos_pdf
            ORDER BY id
            """
        )
        return [dict(row) for row in cur.fetchall()]


def _locked_rows_compatible(locked_rows: list[dict[str, Any]], inventory: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    expected = sorted(
        ({
            "id": int(item["id"]),
            "tripulante_id": int(item["tripulante_id"]),
            "status": str(item.get("status") or ""),
            "storage_ref": str(item.get("storage_ref") or ""),
            "arquivo_hash": str(item.get("arquivo_hash") or ""),
            "tamanho_bytes": int(item.get("tamanho_bytes") or 0),
            "has_db_blob": bool(item.get("has_db_blob")),
            "db_blob_bytes": int(item.get("db_blob_bytes") or 0),
        }
        for item in inventory.get("items", [])
        ),
        key=lambda item: item["id"],
    )
    actual = sorted(
        ({
            "id": int(item["id"]),
            "tripulante_id": int(item["tripulante_id"]),
            "status": str(item.get("status") or ""),
            "storage_ref": str(item.get("storage_ref") or ""),
            "arquivo_hash": str(item.get("arquivo_hash") or ""),
            "tamanho_bytes": int(item.get("tamanho_bytes") or 0),
            "has_db_blob": bool(item.get("has_db_blob")),
            "db_blob_bytes": int(item.get("db_blob_bytes") or 0),
        }
        for item in locked_rows
        ),
        key=lambda item: item["id"],
    )
    return actual == expected, {"expected": expected, "actual": actual}


def _safe_path(path: str, media_root: Path) -> Path:
    target = Path(path)
    root = media_root.resolve(strict=False)
    try:
        target.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"Caminho fora de MEDIA_STORAGE_ROOT: {target}") from exc
    return target


def _stage_physical_files(paths: list[str], media_root: Path, operation_id: str) -> list[dict[str, Any]]:
    staged: list[dict[str, Any]] = []
    try:
        for raw_path in paths:
            source = _safe_path(raw_path, media_root)
            target = source.with_name(f"{source.name}.delete-{operation_id}.quarantine")
            item = {
                "original_path": str(source),
                "quarantine_path": str(target),
                "stage_status": "",
                "final_delete_status": "",
                "error": "",
            }
            if not source.exists():
                item["stage_status"] = "already_missing"
                staged.append(item)
                continue
            if target.exists():
                raise RuntimeError(f"Quarentena ja existe: {target}")
            source.rename(target)
            item["stage_status"] = "staged"
            staged.append(item)
        return staged
    except Exception:
        for item in reversed(staged):
            if item.get("stage_status") == "staged":
                quarantine = Path(item["quarantine_path"])
                original = Path(item["original_path"])
                if quarantine.exists() and not original.exists():
                    quarantine.rename(original)
                    item["stage_status"] = "restored_after_stage_failure"
        raise


def _restore_staged_files(staged: list[dict[str, Any]]) -> None:
    for item in reversed(staged):
        if item.get("stage_status") != "staged":
            continue
        quarantine = Path(item["quarantine_path"])
        original = Path(item["original_path"])
        if quarantine.exists() and not original.exists():
            quarantine.rename(original)
            item["stage_status"] = "restored_after_db_failure"


def _delete_staged_files(staged: list[dict[str, Any]]) -> None:
    for item in staged:
        if item.get("stage_status") == "already_missing":
            item["final_delete_status"] = "not_needed_already_missing"
            continue
        quarantine = Path(item["quarantine_path"])
        try:
            if quarantine.exists():
                quarantine.unlink()
                item["final_delete_status"] = "deleted"
            else:
                item["final_delete_status"] = "already_missing_after_commit"
        except Exception as exc:  # noqa: BLE001 - evidence must preserve concrete failure.
            item["final_delete_status"] = "failed"
            item["error"] = f"{type(exc).__name__}: {exc}"


def _delete_rows_with_audit(conn, *, items: list[dict[str, Any]], actor_user_id: int, operation_id: str) -> list[int]:
    ids = sorted(int(item["id"]) for item in items)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM usuarios WHERE id = %s", (actor_user_id,))
        if cur.fetchone() is None:
            raise RuntimeError(f"Usuario de auditoria nao encontrado: {actor_user_id}")
        for item in items:
            audit_payload = {
                "operation_id": operation_id,
                "reason": "vida_nova_tripulante_pdf_cleanup",
                "id": item.get("id"),
                "tripulante_id": item.get("tripulante_id"),
                "nome_original": item.get("nome_original"),
                "status": item.get("status"),
                "storage_ref": item.get("storage_ref"),
                "target_path": item.get("target_path"),
                "classification": item.get("classification"),
                "blob_available": item.get("blob_available"),
                "has_db_blob": item.get("has_db_blob"),
                "tamanho_bytes": item.get("tamanho_bytes"),
                "arquivo_hash": item.get("arquivo_hash"),
            }
            cur.execute(
                """
                INSERT INTO auditoria_eventos
                    (entidade, entidade_id, acao, payload_anterior, payload_novo, realizado_por, observacao)
                VALUES
                    (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                """,
                (
                    "tripulante_arquivo_pdf",
                    int(item["id"]),
                    "delete",
                    json.dumps(audit_payload, ensure_ascii=False),
                    json.dumps({"status": "hard_deleted_by_cleanup", "operation_id": operation_id}, ensure_ascii=False),
                    actor_user_id,
                    "Limpeza total de PDFs de tripulantes confirmada explicitamente pelo operador.",
                ),
            )
        cur.execute(
            "DELETE FROM tripulante_arquivos_pdf WHERE id = ANY(%s) RETURNING id",
            (ids,),
        )
        deleted = sorted(int(row["id"]) for row in cur.fetchall())
    if deleted != ids:
        raise RuntimeError(f"Delete retornou ids divergentes. expected={ids} deleted={deleted}")
    return deleted


def _postcheck(conn, *, physical_paths: list[str], quarantine_paths: list[str]) -> dict[str, Any]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT COUNT(*) AS total FROM tripulante_arquivos_pdf")
        total = int(cur.fetchone()["total"])
        cur.execute(
            """
            SELECT entidade_id, realizado_em
            FROM auditoria_eventos
            WHERE entidade = 'tripulante_arquivo_pdf'
              AND observacao = 'Limpeza total de PDFs de tripulantes confirmada explicitamente pelo operador.'
            ORDER BY realizado_em DESC, entidade_id
            LIMIT 30
            """
        )
        audit_rows = [dict(row) for row in cur.fetchall()]
    return {
        "tripulante_arquivos_pdf_count": total,
        "physical_paths_exist_after": {path: Path(path).exists() for path in physical_paths},
        "quarantine_paths_exist_after": {path: Path(path).exists() for path in quarantine_paths},
        "recent_cleanup_audit_rows": audit_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Aplica limpeza destrutiva de PDFs de tripulantes com gate rigido.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--env-file", default=r"C:\srv\controle-treinamentos\env\prod.env")
    parser.add_argument("--dry-run-evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--actor-user-id", type=int, default=1)
    args = parser.parse_args()

    output = Path(args.output)
    operation_id = _now_utc_compact()
    result: dict[str, Any] = {
        "generated_at": _now_utc(),
        "operation_id": operation_id,
        "mode": "apply_tripulante_pdf_cleanup",
        "confirmed": args.confirm == CONFIRMATION_PHRASE,
        "destructive_execution_started": False,
        "status": "not_started",
    }

    try:
        if args.confirm != CONFIRMATION_PHRASE:
            raise RuntimeError("Confirmacao textual invalida.")

        repo_root = Path(args.repo_root).resolve()
        env_file = Path(args.env_file)
        dry_run_evidence = Path(args.dry_run_evidence)
        confirmed_inventory = _load_json(dry_run_evidence)
        current_inventory = dryrun.build_inventory(repo_root=repo_root, env_file=env_file)
        same, signature_diff = _assert_same_signature(confirmed_inventory, current_inventory)
        result["preflight"] = {
            "dry_run_evidence": str(dry_run_evidence),
            "same_signature": same,
            "signature_diff": signature_diff if not same else {},
            "current_summary": current_inventory.get("summary"),
            "current_dry_run": current_inventory.get("dry_run"),
        }
        if not same:
            result["status"] = "aborted_inventory_changed"
            _write_json(output, result)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
            return 2

        env = dict(os.environ)
        env.update(_load_env_file(env_file))
        database_url = (env.get("DATABASE_URL") or "").strip()
        media_root = Path((env.get("MEDIA_STORAGE_ROOT") or env.get("UPLOAD_ROOT") or "").strip())
        if not database_url:
            raise RuntimeError("DATABASE_URL ausente.")
        if not str(media_root):
            raise RuntimeError("MEDIA_STORAGE_ROOT/UPLOAD_ROOT ausente.")

        physical_paths = list(current_inventory.get("dry_run", {}).get("physical_paths_that_would_be_deleted", []))
        items = list(current_inventory.get("items", []))
        result["destructive_execution_started"] = True
        staged: list[dict[str, Any]] = []
        deleted_ids: list[int] = []
        with psycopg2.connect(database_url) as conn:
            conn.autocommit = False
            try:
                locked_rows = _query_locked_signature(conn)
                locked_ok, locked_diff = _locked_rows_compatible(locked_rows, current_inventory)
                result["locked_preflight"] = {
                    "locked_rows_compatible": locked_ok,
                    "locked_diff": locked_diff if not locked_ok else {},
                }
                if not locked_ok:
                    conn.rollback()
                    result["status"] = "aborted_locked_inventory_changed"
                    _write_json(output, result)
                    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
                    return 3

                staged = _stage_physical_files(physical_paths, media_root, operation_id)
                deleted_ids = _delete_rows_with_audit(
                    conn,
                    items=items,
                    actor_user_id=int(args.actor_user_id),
                    operation_id=operation_id,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                _restore_staged_files(staged)
                raise

        _delete_staged_files(staged)
        quarantine_paths = [str(item.get("quarantine_path") or "") for item in staged if item.get("quarantine_path")]
        with psycopg2.connect(database_url) as conn:
            postcheck = _postcheck(conn, physical_paths=physical_paths, quarantine_paths=quarantine_paths)
        final_inventory = dryrun.build_inventory(repo_root=repo_root, env_file=env_file)

        result.update(
            {
                "status": "completed",
                "deleted_ids": deleted_ids,
                "physical_files": staged,
                "postcheck": postcheck,
                "final_inventory_summary": final_inventory.get("summary"),
                "final_inventory_dry_run": final_inventory.get("dry_run"),
            }
        )
        _write_json(output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
        return 0
    except Exception as exc:  # noqa: BLE001 - operation evidence must capture exact failure.
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        _write_json(output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
