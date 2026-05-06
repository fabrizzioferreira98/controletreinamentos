from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app

from ..core.workspace_paths import artifacts_root, evidence_root, local_backups_root, runtime_instance_root

STATUS_META = {
    "healthy": {"label": "Saudável", "class": "status-green"},
    "attention": {"label": "Atenção", "class": "status-yellow"},
    "critical": {"label": "Crítico", "class": "status-red"},
    "unavailable": {"label": "Indisponível", "class": "status-gray"},
    "not_configured": {"label": "Não configurado", "class": "status-gray"},
    "operational": {"label": "Operacional", "class": "status-green"},
    "degraded": {"label": "Degradado", "class": "status-red"},
}


def format_bytes_human(value: int | float | None) -> str:
    if value is None:
        return "Não disponível"
    size = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.2f} {units[idx]}"


def _status_payload(status_key: str) -> dict:
    meta = STATUS_META.get(status_key, STATUS_META["unavailable"])
    return {
        "status_key": status_key,
        "status_label": meta["label"],
        "status_class": meta["class"],
    }


def _status_rank(status_key: str) -> int:
    order = {
        "critical": 0,
        "degraded": 1,
        "attention": 2,
        "healthy": 3,
        "operational": 3,
        "not_configured": 4,
        "unavailable": 5,
    }
    return order.get(status_key, 5)


def _worst_status_key(*status_keys: str | None) -> str:
    keys = [key for key in status_keys if key]
    if not keys:
        return "unavailable"
    return min(keys, key=_status_rank)


def format_duration_human(seconds: int | float | None) -> str:
    if seconds is None:
        return "N/A"
    total_seconds = int(max(0, float(seconds)))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{secs}s")
    return " ".join(parts[:3])


def _safe_count(db, query: str, params: tuple = ()) -> tuple[int | None, str | None]:
    try:
        row = db.execute(query, params).fetchone()
        if row is None:
            return 0, None
        if hasattr(row, "keys"):
            keys = list(row.keys())
            if "total" in keys:
                value = row["total"]
            else:
                value = row[keys[0]] if keys else 0
        else:
            value = row[0]
        return int(value or 0), None
    except Exception as exc:
        return None, str(exc)


def _safe_scalar(db, query: str, params: tuple = ()):
    try:
        row = db.execute(query, params).fetchone()
        if row is None:
            return None, None
        value = row[0] if not hasattr(row, "keys") else row[next(iter(row.keys()))]
        return value, None
    except Exception as exc:
        return None, str(exc)


def _directory_size_bytes(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    total = 0
    for current_root, _dirs, files in os.walk(path):
        root_path = Path(current_root)
        for filename in files:
            file_path = root_path / filename
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def _resolve_backup_dir(project_root: Path) -> Path | None:
    configured = (os.getenv("BACKUP_DIR", "") or "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(local_backups_root())
    candidates.append((project_root / "backups").resolve())
    candidates.append(Path("/tmp/backups"))

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    return None


def _read_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return int(default)
    try:
        return max(0, int(raw))
    except ValueError:
        return int(default)


def _read_float_env(name: str, default: float) -> float:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return float(default)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(default)


def _status_from_usage_percent(usage_percent: float | None, *, warning_percent: float, critical_percent: float) -> str:
    if usage_percent is None:
        return "unavailable"
    if usage_percent >= critical_percent:
        return "critical"
    if usage_percent >= warning_percent:
        return "attention"
    return "healthy"


def _windows_memory_snapshot() -> tuple[int | None, int | None, int | None, float | None]:
    if os.name != "nt":
        return None, None, None, None

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        memory_status = MEMORYSTATUSEX()
        memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status)):
            return None, None, None, None
        total = int(memory_status.ullTotalPhys)
        available = int(memory_status.ullAvailPhys)
        used = max(0, total - available)
        percent = round((used / total) * 100, 1) if total > 0 else None
        return total, used, available, percent
    except Exception:
        return None, None, None, None


def _windows_cpu_percent(sample_seconds: float = 0.2) -> float | None:
    if os.name != "nt":
        return None

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", ctypes.c_ulong),
            ("dwHighDateTime", ctypes.c_ulong),
        ]

    def _read_times() -> tuple[int, int, int] | None:
        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        idle_value = (int(idle.dwHighDateTime) << 32) | int(idle.dwLowDateTime)
        kernel_value = (int(kernel.dwHighDateTime) << 32) | int(kernel.dwLowDateTime)
        user_value = (int(user.dwHighDateTime) << 32) | int(user.dwLowDateTime)
        return idle_value, kernel_value, user_value

    try:
        first = _read_times()
        if first is None:
            return None
        time.sleep(max(0.05, float(sample_seconds)))
        second = _read_times()
        if second is None:
            return None
        idle_delta = second[0] - first[0]
        kernel_delta = second[1] - first[1]
        user_delta = second[2] - first[2]
        total_delta = kernel_delta + user_delta
        if total_delta <= 0:
            return None
        busy_delta = max(0, total_delta - idle_delta)
        return round(min(100.0, max(0.0, (busy_delta / total_delta) * 100.0)), 1)
    except Exception:
        return None


def _system_uptime_seconds() -> int | None:
    if os.name == "nt":
        try:
            return int(ctypes.windll.kernel32.GetTickCount64() / 1000)
        except Exception:
            return None
    return None


def _run_subprocess(command: list[str], *, timeout_seconds: float = 2.0) -> tuple[str, str | None]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as exc:
        return "", str(exc)
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
    if completed.returncode != 0 and not output:
        return "", f"exit={completed.returncode}"
    return output, None


def _query_windows_service(service_name: str, *, required: bool) -> dict:
    unavailable_status = "degraded" if required else "attention"
    if os.name != "nt":
        return {
            "name": service_name,
            "service_name": service_name,
            "state_label": "N/A",
            "message": "Consulta de serviços disponível apenas no Windows.",
            **_status_payload("unavailable"),
        }

    output, error = _run_subprocess(["sc.exe", "query", service_name], timeout_seconds=2.0)
    if error is not None:
        return {
            "name": service_name,
            "service_name": service_name,
            "state_label": "Indisponível",
            "message": "Não foi possível consultar o serviço no host local.",
            **_status_payload("unavailable"),
        }

    normalized = output.upper()
    if "FAILED 1060" in normalized or "DOES NOT EXIST" in normalized:
        return {
            "name": service_name,
            "service_name": service_name,
            "state_label": "Não instalado",
            "message": "Serviço não encontrado neste servidor.",
            **_status_payload("not_configured"),
        }

    state_label = "Desconhecido"
    status_key = "unavailable"
    message = "Sem diagnóstico de estado."
    for raw_state, label, key, note in [
        ("RUNNING", "Em execução", "operational", "Respondendo no SCM do Windows."),
        ("STOPPED", "Parado", unavailable_status, "Serviço parado no SCM do Windows."),
        ("START_PENDING", "Iniciando", "attention", "Serviço em processo de inicialização."),
        ("STOP_PENDING", "Finalizando", "attention", "Serviço em processo de desligamento."),
        ("PAUSED", "Pausado", "attention", "Serviço pausado no SCM do Windows."),
    ]:
        if raw_state in normalized:
            state_label = label
            status_key = key
            message = note
            break

    return {
        "name": service_name.replace("CT-", "").replace("-", " "),
        "service_name": service_name,
        "state_label": state_label,
        "message": message,
        **_status_payload(status_key),
    }


def _probe_tcp_endpoint(label: str, host: str, port: int, *, required: bool) -> dict:
    started_at = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=1.2):
            latency_ms = round((time.perf_counter() - started_at) * 1000, 1)
            return {
                "label": label,
                "address": f"{host}:{port}",
                "latency_ms": latency_ms,
                "message": f"Conexão TCP respondendo em {latency_ms:.1f} ms.",
                **_status_payload("operational"),
            }
    except OSError:
        return {
            "label": label,
            "address": f"{host}:{port}",
            "latency_ms": None,
            "message": "Sem resposta TCP no host local.",
            **_status_payload("degraded" if required else "attention"),
        }


def _build_local_server_context(project_root: Path, storage_overview: dict) -> dict:
    cpu_warning = _read_float_env("MONITORING_CPU_WARNING_PERCENT", 75.0)
    cpu_critical = _read_float_env("MONITORING_CPU_CRITICAL_PERCENT", 90.0)
    memory_warning = _read_float_env("MONITORING_MEMORY_WARNING_PERCENT", 80.0)
    memory_critical = _read_float_env("MONITORING_MEMORY_CRITICAL_PERCENT", 92.0)

    host = socket.gethostname()
    uptime_seconds = _system_uptime_seconds()
    cpu_percent = _windows_cpu_percent()
    memory_total, memory_used, memory_free, memory_percent = _windows_memory_snapshot()
    disk_percent = storage_overview.get("disk_usage_percent")
    disk_free_bytes = storage_overview.get("disk_free_bytes")

    cpu_status = _status_from_usage_percent(cpu_percent, warning_percent=cpu_warning, critical_percent=cpu_critical)
    memory_status = _status_from_usage_percent(
        memory_percent,
        warning_percent=memory_warning,
        critical_percent=memory_critical,
    )
    disk_status = _status_from_usage_percent(
        disk_percent,
        warning_percent=_read_float_env("MONITORING_STORAGE_WARNING_PERCENT", 75.0),
        critical_percent=_read_float_env("MONITORING_STORAGE_CRITICAL_PERCENT", 90.0),
    )

    uptime_status = "operational"
    if uptime_seconds is not None and uptime_seconds < 900:
        uptime_status = "attention"

    metrics = [
        {
            "label": "CPU",
            "value_label": f"{cpu_percent:.1f}%" if cpu_percent is not None else "N/D",
            "meta": "uso total do host",
            "percent": cpu_percent or 0.0,
            **_status_payload(cpu_status),
        },
        {
            "label": "Memória",
            "value_label": f"{memory_percent:.1f}%" if memory_percent is not None else "N/D",
            "meta": (
                f"{format_bytes_human(memory_used)} / {format_bytes_human(memory_total)}"
                if memory_total is not None and memory_used is not None
                else "indisponível"
            ),
            "percent": memory_percent or 0.0,
            **_status_payload(memory_status),
        },
        {
            "label": "Disco do volume",
            "value_label": f"{disk_percent:.1f}%" if disk_percent is not None else "N/D",
            "meta": (
                f"{format_bytes_human(disk_free_bytes)} livres"
                if disk_free_bytes is not None
                else "indisponível"
            ),
            "percent": disk_percent or 0.0,
            **_status_payload(disk_status),
        },
        {
            "label": "Uptime",
            "value_label": format_duration_human(uptime_seconds),
            "meta": "tempo desde o último boot",
            "percent": None,
            **_status_payload(uptime_status),
        },
    ]

    overall_key = _worst_status_key(cpu_status, memory_status, disk_status, uptime_status)
    return {
        "hostname": host,
        "platform_label": f"{platform.system()} {platform.release()}",
        "python_label": f"Python {platform.python_version()}",
        "workspace_label": str(project_root),
        "uptime_label": format_duration_human(uptime_seconds),
        "disk_anchor_label": storage_overview.get("disk_anchor", str(runtime_instance_root())),
        "metrics": metrics,
        **_status_payload(overall_key),
    }


def _build_local_services_context() -> dict:
    service_definitions = [
        {"name": "CT-Caddy", "required": True},
        {"name": "CT-App-Prod", "required": True},
        {"name": "CT-App-Hml", "required": False},
    ]
    windows_services = [
        _query_windows_service(item["name"], required=bool(item["required"]))
        for item in service_definitions
    ]

    endpoint_definitions = [
        {"label": "Frontend produção", "host": "127.0.0.1", "port": 80, "required": True},
        {"label": "Backend produção", "host": "127.0.0.1", "port": 8101, "required": True},
        {"label": "Frontend homologação", "host": "127.0.0.1", "port": 8082, "required": False},
        {"label": "Backend homologação", "host": "127.0.0.1", "port": 8102, "required": False},
    ]
    endpoints = [
        _probe_tcp_endpoint(
            item["label"],
            item["host"],
            int(item["port"]),
            required=bool(item["required"]),
        )
        for item in endpoint_definitions
    ]

    required_statuses = [item["status_key"] for item in windows_services[:2]] + [item["status_key"] for item in endpoints[:2]]
    optional_issues = sum(1 for item in [*windows_services[2:], *endpoints[2:]] if item["status_key"] != "operational")
    running_required = sum(1 for item in [*windows_services[:2], *endpoints[:2]] if item["status_key"] == "operational")
    overview_key = _worst_status_key(*required_statuses)
    return {
        "windows_services": windows_services,
        "endpoints": endpoints,
        "running_required": running_required,
        "required_total": 4,
        "optional_issues": optional_issues,
        **_status_payload(overview_key),
    }


def _database_size_bytes(db, project_root: Path) -> tuple[int | None, str | None, str]:
    size_bytes, error = _safe_scalar(db, "SELECT pg_database_size(current_database()) AS bytes")
    if size_bytes is not None and error is None:
        return int(size_bytes), None, "postgres"

    sqlite_fallback = project_root / "data.sqlite3"
    if sqlite_fallback.exists():
        try:
            return int(sqlite_fallback.stat().st_size), None, "sqlite"
        except OSError as exc:
            return None, str(exc), "sqlite"

    return None, error or "Tamanho do banco não disponível.", "desconhecido"


def _build_integrity_checks(db) -> tuple[dict, list[dict], list[dict]]:
    now_label = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    checks_config = [
        {
            "key": "tripulantes_incompletos",
            "title": "Tripulantes com campos obrigatórios ausentes",
            "query": (
                """
                SELECT COUNT(*) AS total
                FROM tripulantes
                WHERE TRIM(COALESCE(nome, '')) = ''
                   OR TRIM(COALESCE(cpf, '')) = ''
                   OR TRIM(COALESCE(licenca_anac, '')) = ''
                   OR TRIM(COALESCE(base, '')) = ''
                """
            ),
            "severity": "critical",
        },
        {
            "key": "tripulantes_perfil_invalido",
            "title": "Função/categoria operacional fora do padrão",
            "query": (
                """
                SELECT COUNT(*) AS total
                FROM tripulantes
                WHERE funcao_operacional NOT IN ('comandante', 'copiloto', 'outro')
                   OR categoria_operacional NOT IN ('A', 'B', 'N/A')
                """
            ),
            "severity": "critical",
        },
        {
            "key": "missoes_sem_tripulante",
            "title": "Missões sem tripulante vinculado",
            "query": (
                """
                SELECT COUNT(*) AS total
                FROM missoes_operacionais m
                LEFT JOIN missao_tripulantes mt ON mt.missao_id = m.id
                WHERE mt.id IS NULL
                """
            ),
            "severity": "attention",
        },
        {
            "key": "pernoites_quantidade_invalida",
            "title": "Pernoites com quantidade inválida",
            "query": "SELECT COUNT(*) AS total FROM pernoites_operacionais WHERE quantidade <= 0",
            "severity": "critical",
        },
        {
            "key": "treinamentos_sem_vencimento",
            "title": "Treinamentos sem data de vencimento",
            "query": "SELECT COUNT(*) AS total FROM treinamentos WHERE data_vencimento IS NULL",
            "severity": "attention",
        },
        {
            "key": "licencas_duplicadas",
            "title": "Licenças ANAC duplicadas",
            "query": (
                """
                SELECT COUNT(*) AS total
                FROM (
                    SELECT licenca_anac
                    FROM tripulantes
                    WHERE TRIM(COALESCE(licenca_anac, '')) <> ''
                    GROUP BY licenca_anac
                    HAVING COUNT(*) > 1
                ) dup
                """
            ),
            "severity": "critical",
        },
        {
            "key": "tripulante_file_schema_ausente",
            "title": "Aba File sem tabela de documentos",
            "query": (
                """
                SELECT CASE
                    WHEN to_regclass('public.tripulante_arquivos_pdf') IS NULL THEN 1
                    ELSE 0
                END AS total
                """
            ),
            "severity": "critical",
        },
    ]

    checks = []
    alerts = []
    total_issues = 0
    critical_issues = 0
    unavailable_checks = 0

    for config in checks_config:
        issues_count, error = _safe_count(db, config["query"])
        if error is not None:
            status_key = "unavailable"
            unavailable_checks += 1
            message = "Não foi possível calcular automaticamente esta verificação."
            issues_count = None
        else:
            if issues_count == 0:
                status_key = "healthy"
                message = "Nenhuma inconsistência detectada."
            else:
                total_issues += int(issues_count)
                if config["severity"] == "critical":
                    critical_issues += int(issues_count)
                    status_key = "critical"
                else:
                    status_key = "attention"
                message = f"{issues_count} item(ns) com inconsistência."
                alerts.append(
                    {
                        "severity_key": "critical" if config["severity"] == "critical" else "warning",
                        "title": config["title"],
                        "message": message,
                        "source": "integridade",
                    }
                )

        checks.append(
            {
                "key": config["key"],
                "title": config["title"],
                "issues_count": issues_count,
                "last_check_label": now_label,
                "message": message,
                **_status_payload(status_key),
            }
        )

    if critical_issues > 0:
        overall_key = "critical"
    elif total_issues > 0:
        overall_key = "attention"
    elif unavailable_checks == len(checks):
        overall_key = "unavailable"
    else:
        overall_key = "healthy"

    overview = {
        "total_checks": len(checks),
        "total_issues": total_issues,
        "critical_issues": critical_issues,
        "unavailable_checks": unavailable_checks,
        **_status_payload(overall_key),
    }
    return overview, checks, alerts


def _build_local_storage_metrics(db, project_root: Path) -> tuple[dict, list[dict], list[dict]]:
    alerts = []
    runtime_dir = runtime_instance_root()
    backup_dir = _resolve_backup_dir(project_root)
    evidence_dir = evidence_root()
    artifacts_dir = artifacts_root()
    volume_anchor = runtime_dir if runtime_dir.exists() else (backup_dir or project_root)

    warning_percent = _read_float_env("MONITORING_STORAGE_WARNING_PERCENT", 75.0)
    critical_percent = _read_float_env("MONITORING_STORAGE_CRITICAL_PERCENT", 90.0)
    if critical_percent <= warning_percent:
        critical_percent = max(warning_percent + 5.0, 90.0)

    db_size, db_size_error, db_size_source = _database_size_bytes(db, project_root)
    runtime_bytes = _directory_size_bytes(runtime_dir) if runtime_dir.exists() else None
    backup_bytes = _directory_size_bytes(backup_dir) if backup_dir and backup_dir.exists() else None
    evidence_bytes = _directory_size_bytes(evidence_dir) if evidence_dir.exists() else None
    artifacts_bytes = _directory_size_bytes(artifacts_dir) if artifacts_dir.exists() else None

    breakdown = [
        {
            "name": "Banco de dados",
            "bytes": int(db_size) if db_size is not None else None,
            "message": f"Origem: {db_size_source}." if db_size_error is None else "Medição do banco indisponível.",
            **_status_payload("healthy" if db_size is not None else "unavailable"),
        },
        {
            "name": "Runtime e uploads locais",
            "bytes": int(runtime_bytes) if runtime_bytes is not None else None,
            "message": str(runtime_dir) if runtime_dir.exists() else "Diretório de runtime local não encontrado.",
            **_status_payload("healthy" if runtime_bytes is not None else "not_configured"),
        },
        {
            "name": "Backups locais",
            "bytes": int(backup_bytes) if backup_bytes is not None else None,
            "message": str(backup_dir) if backup_dir else "Diretório local de backup não encontrado.",
            **_status_payload("healthy" if backup_bytes is not None else "not_configured"),
        },
        {
            "name": "Evidências operacionais",
            "bytes": int(evidence_bytes) if evidence_bytes is not None else None,
            "message": str(evidence_dir) if evidence_dir.exists() else "Diretório de evidências não encontrado.",
            **_status_payload("healthy" if evidence_bytes is not None else "not_configured"),
        },
        {
            "name": "Artefatos e snapshots",
            "bytes": int(artifacts_bytes) if artifacts_bytes is not None else None,
            "message": str(artifacts_dir) if artifacts_dir.exists() else "Diretório de artefatos não encontrado.",
            **_status_payload("healthy" if artifacts_bytes is not None else "not_configured"),
        },
    ]

    disk_total = disk_used = disk_free = None
    disk_percent = None
    disk_error = None
    try:
        usage = shutil.disk_usage(str(volume_anchor))
        disk_total = int(usage.total)
        disk_used = int(usage.used)
        disk_free = int(usage.free)
        disk_percent = round((disk_used / disk_total) * 100, 2) if disk_total else 0.0
    except OSError as exc:
        disk_error = str(exc)

    status_key = _status_from_usage_percent(
        disk_percent,
        warning_percent=warning_percent,
        critical_percent=critical_percent,
    )
    if disk_percent is None:
        status_message = "Não foi possível calcular o uso do volume monitorado."
    elif status_key == "critical":
        status_message = "Volume local em nível crítico de consumo."
        alerts.append(
            {
                "severity_key": "critical",
                "title": "Armazenamento local em nível crítico",
                "message": f"Uso atual em {disk_percent:.2f}% do volume monitorado.",
                "source": "armazenamento",
            }
        )
    elif status_key == "attention":
        status_message = "Volume local em atenção de capacidade."
        alerts.append(
            {
                "severity_key": "warning",
                "title": "Armazenamento local em atenção",
                "message": f"Uso atual em {disk_percent:.2f}% do volume monitorado.",
                "source": "armazenamento",
            }
        )
    else:
        status_message = "Volume local com capacidade saudável."

    overview = {
        "disk_anchor": str(volume_anchor),
        "disk_total_bytes": disk_total,
        "disk_used_bytes": disk_used,
        "disk_free_bytes": disk_free,
        "disk_usage_percent": disk_percent,
        "disk_error": disk_error,
        "message": status_message,
        **_status_payload(status_key),
    }
    return overview, breakdown, alerts


def _build_module_statuses(db, *, integrity: dict, storage: dict) -> tuple[list[dict], list[dict], dict]:
    now = datetime.now()
    now_label = now.strftime("%d/%m/%Y %H:%M:%S")
    alerts = []

    modules: list[dict] = []
    notification_context = {
        "provider": "smtp",
        "email_ready": False,
        "recipients_count": 0,
        "missing_config_fields": [],
        "last_run": "",
        "last_sent_at": "",
        "last_error": "",
        "last_job_status": "",
        "last_job_error": "",
        "last_job_at": "",
        "status_key": "unavailable",
        "status_label": STATUS_META["unavailable"]["label"],
        "status_class": STATUS_META["unavailable"]["class"],
    }

    def add_module(name: str, category: str, status_key: str, message: str, problem_count: int = 0):
        modules.append(
            {
                "name": name,
                "category": category,
                "last_check_label": now_label,
                "message": message,
                "problem_count": int(max(0, problem_count)),
                **_status_payload(status_key),
            }
        )

    ping, ping_error = _safe_scalar(db, "SELECT 1 AS ok")
    if ping_error is None and int(ping or 0) == 1:
        add_module("Banco de dados", "Infraestrutura", "operational", "Conexão e leitura básicas respondendo.")
    else:
        add_module("Banco de dados", "Infraestrutura", "unavailable", "Falha ao validar conexão com o banco.", 1)
        alerts.append(
            {
                "severity_key": "critical",
                "title": "Banco de dados indisponível para diagnóstico",
                "message": "A consulta de verificação básica falhou.",
                "source": "infraestrutura",
            }
        )

    active_users, users_error = _safe_count(db, "SELECT COUNT(*) AS total FROM usuarios WHERE ativo = 1")
    if users_error is None and (active_users or 0) > 0:
        add_module("Autenticação", "Segurança", "operational", f"{active_users} usuário(s) ativo(s) aptos para login.")
    elif users_error is None:
        add_module("Autenticação", "Segurança", "degraded", "Nenhum usuário ativo encontrado.", 1)
        alerts.append(
            {
                "severity_key": "critical",
                "title": "Nenhum usuário ativo para autenticação",
                "message": "Sem usuários ativos, o acesso operacional pode ficar indisponível.",
                "source": "segurança",
            }
        )
    else:
        add_module("Autenticação", "Segurança", "unavailable", "Não foi possível verificar usuários ativos.", 1)

    permission_rows = []
    permission_error = None
    try:
        permission_rows = db.execute("SELECT id, permissao_modulos_json FROM usuarios").fetchall()
    except Exception as exc:
        permission_error = str(exc)
    invalid_permissions = 0
    if permission_error is None:
        for row in permission_rows:
            if hasattr(row, "keys"):
                raw = (row["permissao_modulos_json"] or "").strip() if "permissao_modulos_json" in row.keys() else ""
            else:
                raw = ""
            if not raw:
                continue
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                invalid_permissions += 1

    if permission_error is not None:
        add_module("Usuários e permissões", "Segurança", "unavailable", "Não foi possível validar permissões dos usuários.", 1)
    elif invalid_permissions > 0:
        add_module(
            "Usuários e permissões",
            "Segurança",
            "degraded",
            f"{invalid_permissions} usuário(s) com JSON de permissões inválido.",
            invalid_permissions,
        )
        alerts.append(
            {
                "severity_key": "warning",
                "title": "Permissões inconsistentes",
                "message": f"{invalid_permissions} usuário(s) possuem permissões com formato inválido.",
                "source": "segurança",
            }
        )
    else:
        add_module("Usuários e permissões", "Segurança", "operational", "Estrutura de permissões sem inconsistências detectadas.")

    tripulantes_total, _ = _safe_count(db, "SELECT COUNT(*) AS total FROM tripulantes")
    trainings_total, _ = _safe_count(db, "SELECT COUNT(*) AS total FROM treinamentos")
    missoes_total, _ = _safe_count(db, "SELECT COUNT(*) AS total FROM missoes_operacionais")
    pernoites_total, _ = _safe_count(db, "SELECT COUNT(*) AS total FROM pernoites_operacionais")

    if integrity["critical_issues"] > 0:
        integrity_module_key = "degraded"
    elif integrity["total_issues"] > 0:
        integrity_module_key = "attention"
    else:
        integrity_module_key = "operational"

    add_module(
        "Cadastros e integralidade",
        "Dados",
        integrity_module_key,
        (
            f"Tripulantes: {tripulantes_total or 0} · Treinamentos: {trainings_total or 0} · "
            f"Missões: {missoes_total or 0} · Pernoites: {pernoites_total or 0}."
        ),
        integrity["total_issues"],
    )

    if storage["status_key"] == "healthy":
        storage_module_key = "operational"
    elif storage["status_key"] == "attention":
        storage_module_key = "attention"
    elif storage["status_key"] == "critical":
        storage_module_key = "degraded"
    else:
        storage_module_key = "unavailable"

    add_module("Storage", "Infraestrutura", storage_module_key, storage.get("message", "Sem diagnóstico de storage disponível."))

    last_backup = None
    backup_error = None
    try:
        last_backup = db.execute(
            """
            SELECT status, executado_em, mensagem
            FROM backups_execucoes
            ORDER BY executado_em DESC
            LIMIT 1
            """
        ).fetchone()
    except Exception as exc:
        backup_error = str(exc)

    if backup_error is not None:
        add_module("Backups", "Continuidade", "unavailable", "Não foi possível consultar o histórico de backups.", 1)
    elif not last_backup:
        add_module("Backups", "Continuidade", "not_configured", "Ainda não há execução de backup registrada.")
        alerts.append(
            {
                "severity_key": "warning",
                "title": "Backups sem execução registrada",
                "message": "Nenhum backup foi registrado no histórico até o momento.",
                "source": "continuidade",
            }
        )
    else:
        backup_time = last_backup["executado_em"]
        age_hours = (now - backup_time).total_seconds() / 3600 if backup_time else None
        if last_backup["status"] != "sucesso":
            add_module("Backups", "Continuidade", "degraded", "Último backup registrado com falha.", 1)
            alerts.append(
                {
                    "severity_key": "critical",
                    "title": "Falha no último backup",
                    "message": (last_backup["mensagem"] or "Última execução retornou falha.")[:220],
                    "source": "continuidade",
                }
            )
        elif age_hours is not None and age_hours > 36:
            add_module(
                "Backups",
                "Continuidade",
                "attention",
                f"Último backup com sucesso há {age_hours:.1f} hora(s).",
            )
            alerts.append(
                {
                    "severity_key": "warning",
                    "title": "Backup desatualizado",
                    "message": f"A última execução bem-sucedida ocorreu há {age_hours:.1f} hora(s).",
                    "source": "continuidade",
                }
            )
        else:
            add_module("Backups", "Continuidade", "operational", "Último backup registrado com sucesso.")

    try:
        from ..jobs import collect_job_queue_snapshot

        job_snapshot = collect_job_queue_snapshot(db)
        queue_warning_size = max(1, _read_int_env("MONITORING_JOB_QUEUE_WARNING_SIZE", 20))
        queue_critical_size = max(queue_warning_size + 1, _read_int_env("MONITORING_JOB_QUEUE_CRITICAL_SIZE", 100))
        oldest_warning_minutes = max(1, _read_int_env("MONITORING_JOB_QUEUE_OLDEST_WARNING_MINUTES", 30))
        oldest_critical_minutes = max(oldest_warning_minutes + 1, _read_int_env("MONITORING_JOB_QUEUE_OLDEST_CRITICAL_MINUTES", 120))

        queued = int(job_snapshot.get("queued", 0) or 0)
        running = int(job_snapshot.get("running", 0) or 0)
        dead_letter = int(job_snapshot.get("dead_letter", 0) or 0)
        stale_running = int(job_snapshot.get("stale_running", 0) or 0)
        oldest_queued = job_snapshot.get("oldest_queued_minutes")

        jobs_status = "operational"
        jobs_problems = 0
        jobs_message = (
            f"Fila: {queued} pendente(s), {running} em execução, "
            f"{dead_letter} dead-letter, {stale_running} lock(s) potencialmente stale."
        )

        if dead_letter > 0:
            jobs_status = "degraded"
            jobs_problems += dead_letter
            alerts.append(
                {
                    "severity_key": "critical",
                    "title": "Jobs em dead-letter",
                    "message": f"{dead_letter} job(s) exigem reprocessamento manual.",
                    "source": "fila",
                }
            )
        if stale_running > 0:
            jobs_status = "degraded" if jobs_status != "unavailable" else jobs_status
            jobs_problems += stale_running
            alerts.append(
                {
                    "severity_key": "critical",
                    "title": "Jobs com lock stale",
                    "message": f"{stale_running} job(s) com lock acima do tempo esperado.",
                    "source": "fila",
                }
            )
        if queued >= queue_critical_size:
            jobs_status = "degraded"
            jobs_problems += queued
            alerts.append(
                {
                    "severity_key": "critical",
                    "title": "Fila de jobs em nível crítico",
                    "message": f"{queued} job(s) pendentes na fila.",
                    "source": "fila",
                }
            )
        elif queued >= queue_warning_size and jobs_status == "operational":
            jobs_status = "attention"
            jobs_problems += queued
            alerts.append(
                {
                    "severity_key": "warning",
                    "title": "Fila de jobs em atenção",
                    "message": f"{queued} job(s) pendentes na fila.",
                    "source": "fila",
                }
            )

        if oldest_queued is not None:
            if oldest_queued >= oldest_critical_minutes:
                jobs_status = "degraded"
                jobs_problems += 1
                alerts.append(
                    {
                        "severity_key": "critical",
                        "title": "Fila de jobs envelhecida",
                        "message": f"O job pendente mais antigo está há {oldest_queued:.1f} minuto(s) aguardando.",
                        "source": "fila",
                    }
                )
            elif oldest_queued >= oldest_warning_minutes and jobs_status == "operational":
                jobs_status = "attention"
                jobs_problems += 1
                alerts.append(
                    {
                        "severity_key": "warning",
                        "title": "Latência na fila de jobs",
                        "message": f"O job pendente mais antigo está há {oldest_queued:.1f} minuto(s) aguardando.",
                        "source": "fila",
                    }
                )
            jobs_message += f" Mais antigo na fila: {oldest_queued:.1f} min."

        add_module(
            "Filas e jobs",
            "Confiabilidade",
            jobs_status,
            jobs_message,
            jobs_problems,
        )
    except Exception:
        add_module(
            "Filas e jobs",
            "Confiabilidade",
            "unavailable",
            "Não foi possível consultar o estado da fila de jobs.",
            1,
        )

    notification_status = "operational"
    notification_problems = 0
    notification_message_parts: list[str] = []
    try:
        from ..mailer import validate_notification_dispatch_readiness

        readiness = validate_notification_dispatch_readiness()
        provider = (readiness.get("provider") or "smtp").strip().lower()
        recipients_count = int(readiness.get("recipients_count", 0) or 0)
        email_ready = bool(readiness.get("email_ready"))
        missing_fields = [str(item) for item in (readiness.get("missing_config_fields") or []) if str(item).strip()]

        control_rows = db.execute(
            """
            SELECT chave, valor
            FROM sistema_controle
            WHERE chave IN ('notification_last_run', 'notification_last_sent_at', 'notification_last_error')
            """
        ).fetchall()
        control_map = {row["chave"]: (row["valor"] or "").strip() for row in control_rows}

        last_job = db.execute(
            """
            SELECT status, last_error, updated_at
            FROM background_jobs
            WHERE job_type = %s
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            ("send_daily_notifications",),
        ).fetchone()

        notification_context.update(
            {
                "provider": provider or "smtp",
                "email_ready": email_ready,
                "recipients_count": recipients_count,
                "missing_config_fields": missing_fields,
                "last_run": control_map.get("notification_last_run", ""),
                "last_sent_at": control_map.get("notification_last_sent_at", ""),
                "last_error": control_map.get("notification_last_error", ""),
                "last_job_status": (last_job["status"] if last_job else "") or "",
                "last_job_error": ((last_job["last_error"] if last_job else "") or "")[:220],
                "last_job_at": (
                    last_job["updated_at"].strftime("%d/%m/%Y %H:%M:%S")
                    if last_job and last_job.get("updated_at")
                    else ""
                ),
            }
        )

        notification_message_parts.append(
            f"Provider {notification_context['provider'].upper()} · {recipients_count} destinatário(s) ativo(s)."
        )
        if recipients_count <= 0:
            notification_status = "attention"
            notification_problems += 1
            notification_message_parts.append("Nenhum destinatário ativo configurado.")
            alerts.append(
                {
                    "severity_key": "warning",
                    "title": "Notificações sem destinatários ativos",
                    "message": "Não há e-mails ativos para receber alertas diários.",
                    "source": "comunicação",
                }
            )
        if not email_ready:
            notification_status = "degraded"
            notification_problems += 1
            missing_text = ", ".join(missing_fields) if missing_fields else "configuração de provider ausente"
            notification_message_parts.append(f"Configuração de entrega incompleta: {missing_text}.")
            alerts.append(
                {
                    "severity_key": "critical",
                    "title": "Canal de e-mail não configurado",
                    "message": f"Entrega de notificações indisponível. Ajuste: {missing_text}.",
                    "source": "comunicação",
                }
            )

        if last_job:
            status = (last_job["status"] or "").strip().lower()
            if status in {"dead_letter", "failed"}:
                notification_status = "degraded"
                notification_problems += 1
                notification_message_parts.append(f"Último job de notificação terminou em {status}.")
                alerts.append(
                    {
                        "severity_key": "critical",
                        "title": "Falha no job de notificação",
                        "message": (notification_context["last_job_error"] or "Erro sem detalhe no job de notificação.")[:220],
                        "source": "comunicação",
                    }
                )
            elif status in {"queued", "running"} and notification_status == "operational":
                notification_status = "attention"
                notification_message_parts.append(f"Job de notificação em {status}.")

        if notification_context["last_run"]:
            try:
                last_run_dt = datetime.strptime(notification_context["last_run"], "%d/%m/%Y %H:%M")
                if now - last_run_dt > timedelta(hours=30) and notification_status == "operational":
                    notification_status = "attention"
                    notification_problems += 1
                    notification_message_parts.append("Rotina diária sem execução recente.")
                    alerts.append(
                        {
                            "severity_key": "warning",
                            "title": "Rotina de notificações desatualizada",
                            "message": "A rotina diária de e-mail não executa há mais de 30 horas.",
                            "source": "comunicação",
                        }
                    )
            except ValueError:
                pass

        notification_context.update(_status_payload(notification_status))
        add_module(
            "Notificações por e-mail",
            "Comunicação",
            notification_status,
            " ".join(part for part in notification_message_parts if part),
            notification_problems,
        )
    except Exception:
        notification_context.update(_status_payload("unavailable"))
        add_module(
            "Notificações por e-mail",
            "Comunicação",
            "unavailable",
            "Não foi possível avaliar o estado operacional das notificações.",
            1,
        )

    pdf_status = "operational"
    pdf_message = "Geração de PDF operacional."
    try:
        from ..reports import build_auditoria_pdf

        payload = build_auditoria_pdf(
            emitted_at=now_label,
            filtros_aplicados={"entidade": "-", "acao": "-", "autor": "-", "busca": "-"},
            rows=[],
        )
        if not payload.startswith(b"%PDF"):
            raise RuntimeError("Payload sem assinatura PDF")
    except Exception:
        pdf_status = "degraded"
        pdf_message = "Falha na verificação de geração de PDF."
        alerts.append(
            {
                "severity_key": "critical",
                "title": "Falha na geração de PDF",
                "message": "A verificação automática do motor de PDF falhou.",
                "source": "relatórios",
            }
        )
    add_module("Relatórios e PDFs", "Relatórios", pdf_status, pdf_message, 0 if pdf_status == "operational" else 1)

    due_rows, due_err = _safe_count(
        db,
        """
        SELECT COUNT(*) AS total
        FROM treinamentos
        WHERE data_vencimento IS NOT NULL
          AND data_vencimento <= CURRENT_DATE + INTERVAL '30 days'
        """,
    )
    if due_err is None:
        add_module(
            "Dashboards / Painéis TV",
            "Operação",
            "operational",
            f"Dados operacionais disponíveis. {due_rows or 0} vencimento(s) em até 30 dias.",
        )
    else:
        add_module("Dashboards / Painéis TV", "Operação", "degraded", "Falha ao consolidar dados para dashboards.", 1)

    anexo_count, anexo_error = _safe_count(db, "SELECT COUNT(*) AS total FROM treinamento_anexos_pdf WHERE status = 'ativo'")
    if anexo_error is None:
        add_module("Anexos de treinamentos", "Dados", "operational", f"{anexo_count or 0} anexo(s) ativo(s) em armazenamento.")
    else:
        add_module("Anexos de treinamentos", "Dados", "unavailable", "Não foi possível consultar anexos de treinamento.", 1)

    tripulante_file_count, tripulante_file_error = _safe_count(
        db,
        "SELECT COUNT(*) AS total FROM tripulante_arquivos_pdf WHERE status = 'ativo'",
    )
    if tripulante_file_error is None:
        add_module("Documentos File de tripulantes", "Dados", "operational", f"{tripulante_file_count or 0} documento(s) ativo(s) em armazenamento.")
    else:
        add_module("Documentos File de tripulantes", "Dados", "unavailable", "Não foi possível consultar documentos da aba File.", 1)

    critical_count = sum(1 for item in modules if item["status_key"] in {"degraded", "unavailable"})
    return modules, alerts, {"critical_modules": critical_count, "notification": notification_context}


def collect_system_monitoring_snapshot(db) -> dict:
    now = datetime.now()
    now_label = now.strftime("%d/%m/%Y %H:%M:%S")
    project_root = (Path(current_app.root_path).parent.parent).resolve()

    integrity_overview, integrity_checks, integrity_alerts = _build_integrity_checks(db)
    storage_overview, storage_breakdown, storage_alerts = _build_local_storage_metrics(db, project_root)
    server = _build_local_server_context(project_root, storage_overview)
    services = _build_local_services_context()
    modules, module_alerts, module_totals = _build_module_statuses(
        db,
        integrity=integrity_overview,
        storage=storage_overview,
    )

    backup_history_rows = []
    try:
        rows = db.execute(
            """
            SELECT status, tipo, executado_em, mensagem, tamanho_bytes, duracao_ms
            FROM backups_execucoes
            ORDER BY executado_em DESC
            LIMIT 10
            """
        ).fetchall()
        for row in rows:
            status_key = "operational" if row["status"] == "sucesso" else "degraded"
            backup_history_rows.append(
                {
                    "tipo": row["tipo"],
                    "executado_em_label": row["executado_em"].strftime("%d/%m/%Y %H:%M") if row["executado_em"] else "-",
                    "mensagem": (row["mensagem"] or "-")[:220],
                    "tamanho_bytes": int(row["tamanho_bytes"] or 0),
                    "duracao_ms": int(row["duracao_ms"] or 0),
                    **_status_payload(status_key),
                }
            )
    except Exception:
        backup_history_rows = []

    alerts = sorted(
        integrity_alerts + storage_alerts + module_alerts,
        key=lambda item: (0 if item.get("severity_key") == "critical" else 1, item.get("source", ""), item.get("title", "")),
    )
    critical_alerts = sum(1 for item in alerts if item.get("severity_key") == "critical")

    if critical_alerts > 0:
        alerts_key = "critical"
    elif alerts:
        alerts_key = "attention"
    else:
        alerts_key = "healthy"

    overall_key = _worst_status_key(alerts_key, server["status_key"], services["status_key"])

    if critical_alerts > 0:
        summary_message = f"{critical_alerts} alerta(s) crítico(s) exigem ação imediata."
    elif alerts:
        summary_message = f"{len(alerts)} ponto(s) de atenção monitorados sem impacto crítico neste momento."
    else:
        summary_message = "Sem alertas ativos. Operação local sob controle."

    headline_alert = alerts[0] if alerts else None
    primary_alerts = alerts[:4]
    remaining_alerts = max(0, len(alerts) - len(primary_alerts))
    last_backup_label = backup_history_rows[0]["executado_em_label"] if backup_history_rows else "Sem histórico"
    module_map = {item["name"]: item for item in modules}
    notification_module = next(
        (item for item in modules if "notifica" in (item.get("name", "").lower())),
        None,
    )
    operational_focus = [
        {
            "title": "Banco de dados",
            **module_map.get(
                "Banco de dados",
                {"message": "Sem diagnóstico do banco.", **_status_payload("unavailable")},
            ),
        },
        {
            "title": "Filas e jobs",
            **module_map.get(
                "Filas e jobs",
                {"message": "Sem diagnóstico da fila.", **_status_payload("unavailable")},
            ),
        },
        {
            "title": "Backups",
            **module_map.get(
                "Backups",
                {"message": "Sem diagnóstico dos backups.", **_status_payload("unavailable")},
            ),
        },
        {
            "title": "Notificações por e-mail",
            **module_map.get(
                "Notificações por e-mail",
                {"message": "Sem diagnóstico de notificações.", **_status_payload("unavailable")},
            ),
        },
        {
            "title": "Integridade dos dados",
            "message": (
                f"{integrity_overview['total_issues']} inconsistência(s), "
                f"{integrity_overview['critical_issues']} crítica(s)."
            ),
            **_status_payload(
                "operational"
                if integrity_overview["status_key"] == "healthy"
                else integrity_overview["status_key"]
            ),
        },
        {
            "title": "Storage local",
            "message": storage_overview.get("message", "Sem leitura do volume local."),
            **_status_payload(
                "operational" if storage_overview["status_key"] == "healthy" else storage_overview["status_key"]
            ),
        },
    ]
    if notification_module:
        operational_focus[3].update(notification_module)
        operational_focus[3]["title"] = "Notificações por e-mail"

    overview = {
        "updated_at_label": now_label,
        "alerts_count": len(alerts),
        "critical_failures_count": critical_alerts,
        "integrity_label": integrity_overview["status_label"],
        "integrity_key": integrity_overview["status_key"],
        "storage_total_bytes": storage_overview["disk_total_bytes"],
        "storage_used_bytes": storage_overview["disk_used_bytes"],
        "storage_free_bytes": storage_overview["disk_free_bytes"],
        "storage_usage_percent": storage_overview["disk_usage_percent"],
        "summary_message": summary_message,
        "headline_alert": headline_alert,
        "last_backup_label": last_backup_label,
        "services_running_label": f"{services['running_required']}/{services['required_total']}",
        "auto_refresh_seconds": max(15, _read_int_env("MONITORAMENTO_CACHE_TTL_SECONDS", 90)),
        **_status_payload(overall_key),
    }

    return {
        "overview": overview,
        "server": server,
        "services": services,
        "primary_alerts": primary_alerts,
        "remaining_alerts": remaining_alerts,
        "operational_focus": operational_focus,
        "integrity": {
            "overview": integrity_overview,
            "checks": integrity_checks,
        },
        "storage": {
            "overview": storage_overview,
            "breakdown": storage_breakdown,
        },
        "modules": modules,
        "alerts": alerts,
        "history": {
            "backup_rows": backup_history_rows,
            "critical_modules": module_totals["critical_modules"],
        },
        "notification": module_totals.get("notification", {}),
    }

