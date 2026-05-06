from __future__ import annotations

import ctypes
import gzip
import hashlib
import json
import os
import socket
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

from flask import current_app

from ..core.metrics import record_critical_flow_duration, record_critical_flow_failure
from ..core.postgres_tools import find_postgres_binary
from ..core.workspace_paths import local_backups_root
from ..db import get_db
from .restore_validation import validate_canonical_restore_contract

_SECURE_APP_ENVS = {"production", "prod", "homolog", "hml", "staging"}


@dataclass
class BackupResult:
    success: bool
    status: str
    message: str
    file_path: str | None
    artifacts: list[str]
    size_bytes: int
    duration_ms: int


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _backup_dir() -> Path:
    raw = (os.getenv("BACKUP_DIR", "") or "").strip()
    preferred = Path(raw).expanduser() if raw else local_backups_root().resolve()
    fallback = Path("/tmp/backups").resolve()

    candidates = [preferred]
    if preferred != fallback:
        candidates.append(fallback)

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".backup_write_probe"
            probe.write_text("ok", encoding="utf-8")
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                # Se a remoção falhar, ainda assim já provamos que o diretório é gravável.
                pass
            return candidate
        except OSError:
            continue

    raise RuntimeError("Não foi possível criar diretório de backup em nenhum caminho permitido.")


def _retention_days() -> int:
    return max(1, _env_int("BACKUP_RETENTION_DAYS", 15))


def _backup_operation_lock_stale_seconds() -> int:
    return max(60, _env_int("BACKUP_OPERATION_LOCK_STALE_SECONDS", 14400))


def _read_backup_operation_lock(lock_file: Path) -> dict:
    try:
        fallback_created_at = datetime.utcfromtimestamp(lock_file.stat().st_mtime).isoformat(timespec="seconds") + "Z"
    except OSError:
        fallback_created_at = None
    try:
        raw = lock_file.read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    if not raw:
        return {"created_at": fallback_created_at, "parse_error": "empty_lock_file"}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw, "created_at": fallback_created_at, "parse_error": "json_decode"}
    return payload if isinstance(payload, dict) else {"raw": raw}


def _backup_lock_created_at(payload: dict) -> datetime | None:
    raw = (payload.get("created_at") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_int
        ctypes.set_last_error(0)
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if handle:
            exit_code = ctypes.c_uint32()
            try:
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == still_active
                return True
            finally:
                kernel32.CloseHandle(handle)
        return ctypes.get_last_error() == 5
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _backup_lock_process_alive(payload: dict) -> bool | None:
    raw_pid = payload.get("pid")
    try:
        pid = int(raw_pid)
    except (TypeError, ValueError):
        return None

    host = str(payload.get("host") or "").strip()
    current_host = socket.gethostname().strip()
    if host and host.casefold() != current_host.casefold():
        return None
    if pid <= 0:
        return None

    return _process_exists(pid)


def _backup_lock_is_stale(payload: dict, *, stale_seconds: int) -> bool:
    process_alive = _backup_lock_process_alive(payload)
    if process_alive is False:
        return True
    created_at = _backup_lock_created_at(payload)
    if created_at is None:
        return False
    return (datetime.utcnow() - created_at).total_seconds() > stale_seconds


def _build_backup_operation_lock_payload(*, backup_type: str, lock_file: Path) -> dict:
    return {
        "lock": "run_backup",
        "token": uuid4().hex,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "backup_type": backup_type,
        "app_env": _normalized_app_env(),
        "lock_file": str(lock_file),
        "stale_after_seconds": _backup_operation_lock_stale_seconds(),
    }


def _acquire_backup_operation_lock(backup_dir: Path, *, backup_type: str) -> tuple[Path, dict | None, dict | None]:
    lock_file = backup_dir / ".run_backup.lock"
    stale_seconds = _backup_operation_lock_stale_seconds()

    for _ in range(2):
        payload = _build_backup_operation_lock_payload(backup_type=backup_type, lock_file=lock_file)
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing = _read_backup_operation_lock(lock_file)
            if _backup_lock_is_stale(existing, stale_seconds=stale_seconds):
                try:
                    lock_file.unlink()
                except OSError:
                    return lock_file, None, existing
                current_app.logger.warning(
                    "Removed stale backup operation lock.",
                    extra={
                        "job_type": "run_backup",
                        "lock_file": str(lock_file),
                        "stale_after_seconds": stale_seconds,
                        "previous_lock": existing,
                    },
                )
                continue
            return lock_file, None, existing
        except OSError:
            raise

        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n")
        return lock_file, payload, None

    return lock_file, None, _read_backup_operation_lock(lock_file)


def _release_backup_operation_lock(lock_file: Path, lock_payload: dict) -> None:
    expected_token = lock_payload.get("token")
    existing = _read_backup_operation_lock(lock_file)
    if existing.get("token") != expected_token:
        current_app.logger.warning(
            "Backup operation lock was not released because token changed.",
            extra={
                "job_type": "run_backup",
                "lock_file": str(lock_file),
                "expected_token": expected_token,
                "existing_lock": existing,
            },
        )
        return
    try:
        lock_file.unlink()
    except FileNotFoundError:
        return
    except OSError:
        current_app.logger.exception(
            "Failed to release backup operation lock.",
            extra={"job_type": "run_backup", "lock_file": str(lock_file)},
        )


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalized_app_env() -> str:
    value = (current_app.config.get("APP_ENV") or os.getenv("APP_ENV", "") or "").strip().lower()
    if value in {"prod", "production"}:
        return "prod"
    if value in {"homolog", "hml", "staging"}:
        return "hml"
    return value


def _is_secure_app_env() -> bool:
    return _normalized_app_env() in _SECURE_APP_ENVS


def _backup_example_env_file() -> Path | None:
    app_env = _normalized_app_env()
    if app_env not in {"prod", "hml"}:
        return None
    candidate = Path(current_app.root_path).resolve().parents[2] / "ops" / "windows" / "env" / f"{app_env}.env.example"
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def _parse_env_file(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            payload[name.strip()] = value.strip()
    except OSError:
        return {}
    return payload


def _example_backup_values() -> dict[str, str]:
    env_file = _backup_example_env_file()
    if env_file is None:
        return {}
    return _parse_env_file(env_file)


def _split_backup_specs(raw: str) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for item in paths:
        key = str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _resolve_backup_targets(*, env_name: str, defaults: list[Path] | None = None) -> tuple[list[Path], list[str], list[str]]:
    defaults = defaults or []
    explicit_specs = _split_backup_specs((os.getenv(env_name, "") or "").strip())
    missing_specs: list[str] = []
    existing_paths: list[Path] = list(defaults)
    used_specs: list[str] = []

    if explicit_specs:
        used_specs = explicit_specs
    else:
        used_specs = _split_backup_specs(_example_backup_values().get(env_name, ""))

    for item in used_specs:
        candidate = Path(item).expanduser()
        if candidate.exists():
            existing_paths.append(candidate.resolve())
        else:
            missing_specs.append(item)

    return _unique_paths(existing_paths), missing_specs, used_specs


def _include_paths() -> tuple[list[Path], list[str], list[str]]:
    default = Path(current_app.root_path) / "static"
    defaults = [default.resolve()] if default.exists() else []
    return _resolve_backup_targets(env_name="BACKUP_INCLUDE_PATHS", defaults=defaults)


def _config_paths() -> tuple[list[Path], list[str], list[str]]:
    return _resolve_backup_targets(env_name="BACKUP_CONFIG_PATHS", defaults=[])


def _safe_db_parts(url: str) -> tuple[str, str, str, str]:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = str(parsed.port or 5432)
    dbname = (parsed.path or "/").lstrip("/") or "postgres"
    user = unquote(parsed.username or "")
    return host, port, dbname, user


def _run_pg_dump(target_file: Path) -> tuple[bool, str]:
    url = current_app.config.get("DATABASE_URL", "")
    if not url:
        return False, "DATABASE_URL não configurada."
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        return False, "Tipo de banco não suportado para backup automático por dump."

    host, port, dbname, user = _safe_db_parts(url)
    password = unquote(parsed.password or "")
    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password
    pg_dump_binary = find_postgres_binary("pg_dump")
    if not pg_dump_binary:
        return False, (
            "pg_dump n?o encontrado no ambiente. "
            "Adicione o binario ao PATH ou configure PG_BIN_DIR/PG_DUMP_PATH."
        )
    command = [
        str(pg_dump_binary),
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--host",
        host,
        "--port",
        port,
        "--username",
        user,
        "--file",
        str(target_file),
        dbname,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=900,
        )
    except FileNotFoundError:
        return False, "pg_dump não encontrado no ambiente."
    except subprocess.TimeoutExpired:
        return False, "Tempo limite excedido ao executar pg_dump."

    if completed.returncode != 0:
        msg = (completed.stderr or completed.stdout or "Falha ao executar pg_dump.").strip()
        return False, msg[:500]
    return True, "Backup de banco concluído."


def _list_user_tables(db) -> list[tuple[str, str]]:
    rows = db.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name
        """
    ).fetchall()
    return [(row["table_schema"], row["table_name"]) for row in rows]


def _run_logical_backup(target_file: Path) -> tuple[bool, str]:
    """Fallback para ambientes sem pg_dump disponivel.

    Gera snapshot lógico em JSON compactado por gzip.
    """
    try:
        db = get_db()
        snapshot = {
            "generated_at": datetime.now().isoformat(),
            "schema": "logical_json_v1",
            "tables": {},
        }
        for schema_name, table_name in _list_user_tables(db):
            key = f"{schema_name}.{table_name}"
            rows = db.execute(
                f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT %s',
                (1_000_000,),
            ).fetchall()
            serialized = []
            for row in rows:
                item = {}
                for col in row.keys():
                    value = row[col]
                    if hasattr(value, "isoformat"):
                        item[col] = value.isoformat()
                    elif isinstance(value, (bytes, bytearray, memoryview)):
                        item[col] = f"<binary:{len(bytes(value))}bytes>"
                    else:
                        item[col] = value
                serialized.append(item)
            snapshot["tables"][key] = serialized

        raw = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        with gzip.open(target_file, "wb") as gz:
            gz.write(raw)
        return True, "Backup lógico JSON (fallback) concluído."
    except Exception as exc:
        return False, f"Falha no backup lógico fallback: {exc}"


def _run_sqlite_file_backup(target_file: Path) -> tuple[bool, str]:
    """Fallback para ambientes de desenvolvimento sem DATABASE_URL."""
    raw = (os.getenv("BACKUP_SQLITE_FILE", "") or "").strip()
    sqlite_file = Path(raw).expanduser() if raw else (Path(current_app.root_path).parent.parent / "data.sqlite3")
    if not sqlite_file.exists():
        return False, "Banco local SQLite de fallback não encontrado."
    try:
        with sqlite_file.open("rb") as src, gzip.open(target_file, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return True, "Backup SQLite local (fallback) concluído."
    except Exception as exc:
        return False, f"Falha no backup SQLite local: {exc}"


def _create_assets_archive(target_file: Path, paths: list[Path]) -> tuple[bool, str]:
    if not paths:
        return True, "Sem diretórios adicionais para backup."
    try:
        with tarfile.open(target_file, "w:gz") as tar:
            for path in paths:
                tar.add(path, arcname=path.name)
        return True, "Backup de arquivos concluído."
    except Exception as exc:
        return False, f"Falha ao gerar backup de arquivos: {exc}"


def _cleanup_old_backups(directory: Path, retention_days: int) -> None:
    cutoff = datetime.now() - timedelta(days=retention_days)
    for item in directory.glob("*"):
        if not item.is_file():
            continue
        mtime = datetime.fromtimestamp(item.stat().st_mtime)
        if mtime < cutoff:
            try:
                item.unlink()
            except OSError:
                continue


def _create_config_archive(target_file: Path, paths: list[Path]) -> tuple[bool, str]:
    if not paths:
        return True, "Sem caminhos adicionais para backup de configuracoes."
    try:
        with tarfile.open(target_file, "w:gz") as tar:
            for path in paths:
                tar.add(path, arcname=path.name)
        return True, "Backup de configuracoes concluido."
    except Exception as exc:
        return False, f"Falha ao gerar backup de configuracoes: {exc}"


def _archive_member_names(target_file: Path) -> list[str]:
    if not target_file.exists() or not target_file.is_file():
        return []
    try:
        with tarfile.open(target_file, "r:gz") as tar:
            return [member.name for member in tar.getmembers() if member.name]
    except Exception:
        return []


def _archive_has_top_level(member_names: list[str], name: str) -> bool:
    expected = name.strip("/").lower()
    return any(member.split("/", 1)[0].strip("/").lower() == expected for member in member_names)


def _archive_has_non_example_env(member_names: list[str]) -> bool:
    for member in member_names:
        lowered = member.strip("/").lower()
        if not lowered.startswith("env/") or lowered.endswith("/"):
            continue
        if not lowered.endswith(".example") and ".example." not in lowered:
            return True
    return False


def _path_specs_contain_fragment(specs: list[str], fragment: str) -> bool:
    needle = fragment.strip("\\/").lower()
    return any(needle in spec.replace("/", "\\").lower() for spec in specs)


def _backup_scope_requires_restore_ready(*, backup_type: str) -> bool:
    if _env_flag("BACKUP_REQUIRE_CANONICAL_SCOPE", default=False):
        return True
    if _is_secure_app_env():
        return True
    return (backup_type or "").strip().lower() in {"drill"}


def _validate_backup_scope(
    *,
    include_specs: list[str],
    missing_include_specs: list[str],
    assets_file: Path,
    config_specs: list[str],
    missing_config_specs: list[str],
    config_file: Path,
    require_restore_ready: bool = False,
) -> tuple[bool, list[str]]:
    if not require_restore_ready and not _is_secure_app_env():
        return True, []

    issues: list[str] = []
    assets_members = _archive_member_names(assets_file)
    config_members = _archive_member_names(config_file)

    if require_restore_ready:
        if not include_specs:
            issues.append("Backup guard canonico exige BACKUP_INCLUDE_PATHS apontando para uploads restauraveis.")
        elif not _path_specs_contain_fragment(include_specs, "uploads"):
            issues.append("Backup guard canonico exige trilha real de uploads em BACKUP_INCLUDE_PATHS.")
        if not config_specs:
            issues.append(
                "Backup guard canonico exige BACKUP_CONFIG_PATHS com env, caddy e tasks da mesma janela operacional."
            )
        else:
            for required_fragment in ("env", "caddy", "tasks"):
                if not _path_specs_contain_fragment(config_specs, required_fragment):
                    issues.append(
                        f"Backup guard canonico exige {required_fragment} explicito em BACKUP_CONFIG_PATHS."
                    )

    if missing_include_specs:
        issues.append(
            "Caminhos obrigat?rios de arquivos n?o encontrados para backup: "
            + ", ".join(sorted(missing_include_specs))
        )
    if _path_specs_contain_fragment(include_specs, "uploads") and not _archive_has_top_level(assets_members, "uploads"):
        issues.append("Arquivo de backup n?o cont?m o diret?rio uploads exigido pelo ambiente atual.")

    if missing_config_specs:
        issues.append(
            "Caminhos obrigat?rios de configura??o n?o encontrados para backup: "
            + ", ".join(sorted(missing_config_specs))
        )
    if config_specs:
        for top_level in ("env", "caddy", "tasks"):
            if not _archive_has_top_level(config_members, top_level):
                issues.append(f"Backup de configura??o n?o cont?m o diret?rio obrigat?rio {top_level}.")
        if _archive_has_top_level(config_members, "env") and not _archive_has_non_example_env(config_members):
            issues.append("Backup de configura??o cont?m apenas arquivos .example em env, sem configura??o real restaur?vel.")

    return not issues, issues


def _external_mirror_dir() -> Path | None:
    raw = (os.getenv("BACKUP_EXTERNAL_MIRROR_DIR", "") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _external_mirror_required() -> bool:
    return _env_flag("BACKUP_EXTERNAL_MIRROR_REQUIRED", default=False)


def _remote_enabled() -> bool:
    return _env_flag("BACKUP_REMOTE_ENABLED", default=False)


def _remote_required() -> bool:
    return _env_flag("BACKUP_REMOTE_REQUIRED", default=False)


def _remote_bucket() -> str:
    return (os.getenv("BACKUP_S3_BUCKET", "") or "").strip()


def _remote_prefix() -> str:
    prefix = (os.getenv("BACKUP_S3_PREFIX", "treinamentos-backups") or "").strip().strip("/")
    return prefix or "treinamentos-backups"


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _build_s3_client():
    import boto3

    endpoint_url = (os.getenv("BACKUP_S3_ENDPOINT_URL", "") or "").strip() or None
    region_name = (os.getenv("BACKUP_S3_REGION", "") or "").strip() or None
    return boto3.client("s3", endpoint_url=endpoint_url, region_name=region_name)


def _remote_upload_artifacts(local_artifacts: list[str], stamp: str) -> tuple[list[str], list[str]]:
    if not _remote_enabled():
        return [], []
    bucket = _remote_bucket()
    if not bucket:
        return [], ["Storage remoto habilitado, mas BACKUP_S3_BUCKET não configurado."]

    try:
        client = _build_s3_client()
    except Exception as exc:
        return [], [f"Falha ao inicializar cliente S3: {exc}"]
    prefix = _remote_prefix()
    sse = (os.getenv("BACKUP_S3_SSE", "AES256") or "").strip()
    kms_key = (os.getenv("BACKUP_S3_KMS_KEY_ID", "") or "").strip()

    uploaded = []
    messages = []
    for item in local_artifacts:
        path = Path(item)
        if not path.exists():
            continue
        key = f"{prefix}/{stamp}/{path.name}"
        extra_args = {
            "ContentType": "application/octet-stream",
            "Metadata": {
                "sha256": _sha256_of_file(path),
                "generated_at": datetime.now().isoformat(),
            },
        }
        if sse:
            extra_args["ServerSideEncryption"] = sse
            if sse == "aws:kms" and kms_key:
                extra_args["SSEKMSKeyId"] = kms_key

        try:
            client.upload_file(str(path), bucket, key, ExtraArgs=extra_args)
            uploaded.append(f"s3://{bucket}/{key}")
        except Exception as exc:
            messages.append(f"Falha no upload remoto de {path.name}: {exc}")
    if uploaded:
        messages.append(f"{len(uploaded)} artefato(s) enviado(s) para storage remoto.")
    return uploaded, messages


def _mirror_artifacts_to_external(local_artifacts: list[str], stamp: str) -> tuple[list[str], list[str]]:
    mirror_root = _external_mirror_dir()
    if mirror_root is None:
        return [], []

    messages: list[str] = []
    mirrored: list[str] = []
    try:
        target_dir = mirror_root / stamp
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return [], [f"Falha ao preparar diretório de cópia externa: {exc}"]

    for item in local_artifacts:
        source = Path(item)
        if not source.exists() or not source.is_file():
            continue
        try:
            target = target_dir / source.name
            shutil.copy2(source, target)
            mirrored.append(str(target))
        except Exception as exc:
            messages.append(f"Falha ao copiar {source.name} para backup externo: {exc}")

    if mirrored:
        messages.append(f"{len(mirrored)} artefato(s) copiado(s) para backup externo.")
    return mirrored, messages


def _write_backup_manifest(target_file: Path, artifacts: list[str], *, stamp: str) -> tuple[bool, str]:
    try:
        payload = {
            "generated_at": datetime.now().isoformat(),
            "stamp": stamp,
            "artifacts": [],
        }
        for item in artifacts:
            path = Path(item)
            if not path.exists() or not path.is_file():
                continue
            payload["artifacts"].append(
                {
                    "path": str(path),
                    "name": path.name,
                    "size_bytes": int(path.stat().st_size),
                    "sha256": _sha256_of_file(path),
                }
            )
        target_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True, "Manifesto de backup gerado."
    except Exception as exc:
        return False, f"Falha ao gerar manifesto do backup: {exc}"


def _cleanup_old_remote_backups(retention_days: int) -> None:
    if not _remote_enabled():
        return
    bucket = _remote_bucket()
    if not bucket:
        return

    try:
        client = _build_s3_client()
        prefix = _remote_prefix() + "/"
        cutoff = datetime.now() - timedelta(days=retention_days)
        paginator = client.get_paginator("list_objects_v2")
        to_delete = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                last_modified = item.get("LastModified")
                if not last_modified:
                    continue
                if last_modified.replace(tzinfo=None) < cutoff:
                    to_delete.append({"Key": item["Key"]})
                    if len(to_delete) >= 1000:
                        client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})
                        to_delete = []
        if to_delete:
            client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})
    except Exception:
        current_app.logger.exception("Failed to cleanup old remote backups.")


def _record_backup_history(result: BackupResult, backup_type: str = "manual") -> None:
    db_url = (current_app.config.get("DATABASE_URL", "") or "").strip()
    if not db_url:
        current_app.logger.info("Histórico de backup não registrado porque DATABASE_URL não está configurada.")
        return
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO backups_execucoes
            (tipo, status, arquivo_principal, artefatos, tamanho_bytes, duracao_ms, mensagem)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                backup_type,
                result.status,
                result.file_path,
                json.dumps(result.artifacts),
                int(result.size_bytes),
                int(result.duration_ms),
                result.message,
            ),
        )
        db.commit()
    except Exception:
        current_app.logger.exception("Falha ao registrar histórico de backup.")


def run_backup_job(*, backup_type: str = "manual") -> BackupResult:
    start = time.time()
    backup_dir: Path | None = None
    lock_file: Path | None = None
    lock_payload: dict | None = None
    lock_acquired = False
    current_app.logger.info(
        "Backup operation started.",
        extra={
            "event": "backup_start",
            "job_type": "run_backup",
            "backup_type": backup_type,
            "remote_enabled": _remote_enabled(),
            "remote_required": _remote_required(),
            "external_mirror_required": _external_mirror_required(),
        },
    )
    try:
        backup_dir = _backup_dir()
        lock_file, lock_payload, existing_lock = _acquire_backup_operation_lock(backup_dir, backup_type=backup_type)
        if lock_payload is None:
            result = BackupResult(
                success=False,
                status="falha",
                message="Backup ja esta em execucao por outra trilha operacional.",
                file_path=None,
                artifacts=[],
                size_bytes=0,
                duration_ms=int((time.time() - start) * 1000),
            )
            current_app.logger.warning(
                "Backup operation skipped because exclusive lock is already held.",
                extra={
                    "event": "backup_skipped_lock_held",
                    "job_type": "run_backup",
                    "backup_type": backup_type,
                    "lock_file": str(lock_file),
                    "existing_lock": existing_lock,
                    "duration_ms": result.duration_ms,
                },
            )
            _record_backup_history(result, backup_type=backup_type)
            record_critical_flow_duration("backup", result.status, result.duration_ms)
            record_critical_flow_failure("backup", "lock_held")
            return result

        lock_acquired = True
        current_app.logger.info(
            "Backup operation lock acquired.",
            extra={
                "event": "backup_lock_acquired",
                "job_type": "run_backup",
                "backup_type": backup_type,
                "lock_file": str(lock_file),
                "lock_token": lock_payload.get("token"),
            },
        )
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        db_file = backup_dir / f"db_backup_{stamp}.dump"
        fallback_db_file = backup_dir / f"db_backup_{stamp}.json.gz"
        assets_file = backup_dir / f"assets_backup_{stamp}.tar.gz"
        config_file = backup_dir / f"config_backup_{stamp}.tar.gz"
        manifest_file = backup_dir / f"backup_manifest_{stamp}.json"
        artifacts: list[str] = []
        messages = []
        total_size = 0

        ok_db, msg_db = _run_pg_dump(db_file)
        messages.append(msg_db)
        if ok_db and db_file.exists():
            artifacts.append(str(db_file))
            total_size += db_file.stat().st_size
        elif _env_flag("BACKUP_ALLOW_LOGICAL_FALLBACK", default=True):
            ok_fallback, msg_fallback = _run_logical_backup(fallback_db_file)
            messages.append(msg_fallback)
            if ok_fallback and fallback_db_file.exists():
                ok_db = True
                artifacts.append(str(fallback_db_file))
                total_size += fallback_db_file.stat().st_size
            else:
                sqlite_fallback_file = backup_dir / f"db_backup_{stamp}.sqlite3.gz"
                ok_sqlite, msg_sqlite = _run_sqlite_file_backup(sqlite_fallback_file)
                messages.append(msg_sqlite)
                if ok_sqlite and sqlite_fallback_file.exists():
                    ok_db = True
                    artifacts.append(str(sqlite_fallback_file))
                    total_size += sqlite_fallback_file.stat().st_size

        include_paths, missing_include_specs, include_specs = _include_paths()
        ok_assets, msg_assets = _create_assets_archive(assets_file, include_paths)
        messages.append(msg_assets)
        if ok_assets and assets_file.exists():
            artifacts.append(str(assets_file))
            total_size += assets_file.stat().st_size

        config_paths, missing_config_specs, config_specs = _config_paths()
        ok_config, msg_config = _create_config_archive(config_file, config_paths)
        messages.append(msg_config)
        if ok_config and config_file.exists():
            artifacts.append(str(config_file))
            total_size += config_file.stat().st_size

        require_restore_ready = _backup_scope_requires_restore_ready(backup_type=backup_type)
        ok_scope, scope_messages = _validate_backup_scope(
            include_specs=include_specs,
            missing_include_specs=missing_include_specs,
            assets_file=assets_file,
            config_specs=config_specs,
            missing_config_specs=missing_config_specs,
            config_file=config_file,
            require_restore_ready=require_restore_ready,
        )
        messages.extend(scope_messages)

        ok_manifest, msg_manifest = _write_backup_manifest(manifest_file, artifacts, stamp=stamp)
        messages.append(msg_manifest)
        if ok_manifest and manifest_file.exists():
            artifacts.append(str(manifest_file))
            total_size += manifest_file.stat().st_size

        artifact_contract = validate_canonical_restore_contract(artifacts)
        messages.append(
            "Backup artifact bundle ready."
            if artifact_contract["artifact_bundle_ready"]
            else "Backup artifact bundle is not restore-ready."
        )
        if require_restore_ready and not artifact_contract["artifact_bundle_ready"]:
            if artifact_contract["missing_components"]:
                messages.append(
                    "Missing restore components: " + ", ".join(artifact_contract["missing_components"])
                )
            if artifact_contract["missing_files"]:
                messages.append(
                    "Missing restore files: " + ", ".join(artifact_contract["missing_files"])
                )
            if artifact_contract["window_mismatch_components"]:
                messages.append(
                    "Artifacts outside restore window: "
                    + ", ".join(artifact_contract["window_mismatch_components"])
                )
            if artifact_contract["manifest_missing_entries"]:
                messages.append(
                    "Manifest missing artifact entries: "
                    + ", ".join(artifact_contract["manifest_missing_entries"])
                )
            if artifact_contract["manifest_error"]:
                messages.append(f"Manifest error: {artifact_contract['manifest_error']}")

        success = (
            ok_db
            and ok_assets
            and ok_config
            and ok_manifest
            and ok_scope
            and (artifact_contract["artifact_bundle_ready"] or not require_restore_ready)
        )
        status = "sucesso" if success else "falha"
        duration_ms = int((time.time() - start) * 1000)
        file_path = artifacts[0] if artifacts else None
        remote_artifacts, remote_messages = _remote_upload_artifacts(artifacts, stamp=stamp)
        if remote_messages:
            messages.extend(remote_messages)
        mirrored_artifacts, mirror_messages = _mirror_artifacts_to_external(artifacts, stamp=stamp)
        if mirror_messages:
            messages.extend(mirror_messages)
        if _remote_enabled():
            if remote_artifacts:
                messages.append("Backup remoto confirmado.")
            elif _remote_required():
                success = False
                status = "falha"
                messages.append("Backup remoto obrigatório não foi concluído.")
            else:
                messages.append("Backup remoto indisponível; backup local mantido com sucesso.")
        if _external_mirror_dir() is not None:
            if mirrored_artifacts:
                messages.append("Cópia externa local confirmada.")
            elif _external_mirror_required():
                success = False
                status = "falha"
                messages.append("Cópia externa obrigatória não foi concluída.")
            else:
                messages.append("Cópia externa indisponível; backup local mantido com sucesso.")
        all_artifacts = artifacts + remote_artifacts + mirrored_artifacts
        result = BackupResult(
            success=success,
            status=status,
            message=" | ".join(messages),
            file_path=file_path,
            artifacts=all_artifacts,
            size_bytes=total_size,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        result = BackupResult(
            success=False,
            status="falha",
            message=f"Falha inesperada ao executar backup: {exc}",
            file_path=None,
            artifacts=[],
            size_bytes=0,
            duration_ms=int((time.time() - start) * 1000),
        )
        current_app.logger.exception(
            "Falha inesperada na execução do backup.",
            extra={
                "event": "backup_unexpected_failure",
                "job_type": "run_backup",
                "backup_type": backup_type,
                "duration_ms": result.duration_ms,
            },
        )

    finally:
        if lock_file is not None and lock_payload is not None:
            _release_backup_operation_lock(lock_file, lock_payload)

    _record_backup_history(result, backup_type=backup_type)
    if lock_acquired and backup_dir is not None:
        _cleanup_old_backups(backup_dir, _retention_days())
    if lock_acquired:
        _cleanup_old_remote_backups(_retention_days())
    current_app.logger.info(
        "Backup operation completed.",
        extra={
            "event": "backup_complete",
            "job_type": "run_backup",
            "backup_type": backup_type,
            "success": bool(result.success),
            "status": result.status,
            "file_path": result.file_path,
            "artifacts_count": len(result.artifacts),
            "size_bytes": int(result.size_bytes),
            "duration_ms": int(result.duration_ms),
            "lock_acquired": bool(lock_acquired),
        },
    )
    record_critical_flow_duration("backup", result.status, result.duration_ms)
    if not result.success:
        record_critical_flow_failure("backup", result.status)
    return result


def list_backup_history(limit: int = 50):
    db = get_db()
    return db.execute(
        """
        SELECT id, tipo, status, arquivo_principal, tamanho_bytes, duracao_ms, mensagem, executado_em
        FROM backups_execucoes
        ORDER BY executado_em DESC
        LIMIT %s
        """,
        (max(1, min(limit, 500)),),
    ).fetchall()
