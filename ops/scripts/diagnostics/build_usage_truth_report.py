#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import psycopg2
except ImportError:  # pragma: no cover - depende do ambiente
    psycopg2 = None  # type: ignore[assignment]


INTERNAL_PATH_PREFIXES = (
    "/api/internal/",
    "/healthz",
    "/static/",
)

SPA_COMPAT_PREFIXES = (
    "/",
    "/login",
    "/dashboard",
    "/tripulantes",
    "/treinamentos",
)

SSR_PREFIXES = (
    "/missoes",
    "/pernoites",
    "/bases",
    "/usuarios",
    "/auditoria",
    "/monitoramento",
    "/backups",
    "/notificacoes-email",
    "/manual",
)


@dataclass(frozen=True)
class UserProfile:
    user_id: int
    login: str
    perfil: str


def _parse_iso_timestamp(raw_value: str) -> datetime | None:
    raw = (raw_value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _iter_json_logs(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    yield payload


def _normalize_path(path: str) -> str:
    value = (path or "").strip()
    if not value:
        return "/"
    if "?" in value:
        value = value.split("?", 1)[0]
    return value.rstrip("/") or "/"


def _looks_internal(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in INTERNAL_PATH_PREFIXES)


def _surface_for(path: str, status: int) -> str:
    if path.startswith("/api/"):
        return "api"
    if any(path == prefix or path.startswith(prefix + "/") for prefix in SSR_PREFIXES):
        return "server_rendered"
    if any(path == prefix or path.startswith(prefix + "/") for prefix in SPA_COMPAT_PREFIXES):
        return "spa_compat" if status in {301, 302, 303, 307, 308} else "hybrid"
    return "indeterminada"


def _module_for(path: str) -> str:
    if path in {"/", "/login", "/logout"} or path.startswith("/api/v1/session"):
        return "auth_sessao"
    if path.startswith("/dashboard"):
        return "dashboard"
    if path.startswith("/tripulantes"):
        return "tripulantes"
    if path.startswith("/treinamentos"):
        return "treinamentos"
    if path.startswith("/missoes") or path.startswith("/pernoites"):
        return "operacoes"
    if path.startswith("/bases"):
        return "bases"
    if path.startswith("/usuarios"):
        return "usuarios_permissoes"
    if path.startswith("/auditoria"):
        return "auditoria"
    if path.startswith("/notificacoes-email"):
        return "notificacoes"
    if path.startswith("/backups"):
        return "backups"
    if path.startswith("/monitoramento"):
        return "monitoramento"
    if path.startswith("/api/v1/dashboard"):
        return "api_dashboard"
    if path.startswith("/api/v1/tripulantes"):
        return "api_tripulantes"
    if path.startswith("/api/v1/treinamentos"):
        return "api_treinamentos"
    if path.startswith("/api/v1/relatorios"):
        return "api_relatorios"
    if path.startswith("/api/"):
        return "api_outros"
    return "outros"


def _resolve_user_profiles(
    db_url: str | None,
    *,
    exclude_login_prefixes: list[str],
) -> tuple[dict[int, UserProfile], set[int], str]:
    if not db_url:
        return {}, set(), "nao_configurado"
    if psycopg2 is None:
        return {}, set(), "psycopg2_ausente"
    try:
        connection = psycopg2.connect(db_url)
    except Exception:
        return {}, set(), "conexao_falhou"

    by_id: dict[int, UserProfile] = {}
    excluded_ids: set[int] = set()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, login, perfil FROM usuarios")
                for row in cursor.fetchall():
                    user_id = int(row[0])
                    login = str(row[1] or "")
                    perfil = str(row[2] or "")
                    by_id[user_id] = UserProfile(user_id=user_id, login=login, perfil=perfil)
                    login_lc = login.strip().lower()
                    if any(login_lc.startswith(prefix) for prefix in exclude_login_prefixes):
                        excluded_ids.add(user_id)
    finally:
        connection.close()
    return by_id, excluded_ids, "ok"


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_report(
    records: list[dict[str, Any]],
    *,
    users_by_id: dict[int, UserProfile],
    excluded_user_ids: set[int],
) -> dict[str, Any]:
    total_records = len(records)
    surface_counter: Counter[str] = Counter()
    module_counter: Counter[str] = Counter()
    profile_counter: Counter[str] = Counter()
    profile_module_counter: dict[str, Counter[str]] = defaultdict(Counter)
    daily_module_counter: dict[str, Counter[str]] = defaultdict(Counter)

    for record in records:
        path = _normalize_path(str(record.get("path") or ""))
        status = _safe_int(record.get("status")) or 0
        surface = _surface_for(path, status)
        module = _module_for(path)
        user_id = _safe_int(record.get("user_id"))
        profile = "anonimo"
        if user_id is not None:
            profile = users_by_id.get(user_id, UserProfile(user_id=user_id, login="", perfil="desconhecido")).perfil or "desconhecido"

        timestamp = _parse_iso_timestamp(str(record.get("timestamp") or ""))
        day_key = (timestamp or datetime.now(timezone.utc)).date().isoformat()

        surface_counter[surface] += 1
        module_counter[module] += 1
        profile_counter[profile] += 1
        profile_module_counter[profile][module] += 1
        daily_module_counter[day_key][module] += 1

    frontend_surface_total = (
        surface_counter.get("spa_compat", 0)
        + surface_counter.get("server_rendered", 0)
        + surface_counter.get("hybrid", 0)
        + surface_counter.get("indeterminada", 0)
    )
    spa_share = (
        round((surface_counter.get("spa_compat", 0) / frontend_surface_total) * 100.0, 2)
        if frontend_surface_total > 0
        else None
    )
    ssr_share = (
        round((surface_counter.get("server_rendered", 0) / frontend_surface_total) * 100.0, 2)
        if frontend_surface_total > 0
        else None
    )

    ranking_modules = [
        {"module": key, "requests": value}
        for key, value in module_counter.most_common()
    ]
    ranking_profiles = [
        {"profile": key, "requests": value}
        for key, value in profile_counter.most_common()
    ]
    usage_by_profile = {
        profile: [{"module": key, "requests": value} for key, value in counter.most_common()]
        for profile, counter in profile_module_counter.items()
    }
    daily_frequency = {
        day: [{"module": key, "requests": value} for key, value in counter.most_common()]
        for day, counter in sorted(daily_module_counter.items())
    }

    return {
        "scope": {
            "total_human_records": total_records,
            "excluded_user_ids": sorted(excluded_user_ids),
        },
        "surface_share": {
            "raw_counts": dict(surface_counter),
            "frontend_surface_total": frontend_surface_total,
            "spa_percent": spa_share,
            "ssr_percent": ssr_share,
        },
        "module_ranking": ranking_modules,
        "profile_ranking": ranking_profiles,
        "usage_by_profile": usage_by_profile,
        "daily_frequency_by_area": daily_frequency,
    }


def _collect_human_records(
    payloads: Iterable[dict[str, Any]],
    *,
    since: datetime | None,
    excluded_user_ids: set[int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        if str(payload.get("event") or "") != "http_request":
            continue

        path = _normalize_path(str(payload.get("path") or ""))
        if _looks_internal(path):
            continue

        timestamp = _parse_iso_timestamp(str(payload.get("timestamp") or ""))
        if since and timestamp and timestamp < since:
            continue

        user_id = _safe_int(payload.get("user_id"))
        if user_id is not None and user_id in excluded_user_ids:
            continue

        rows.append(
            {
                "timestamp": (timestamp.isoformat() if timestamp else ""),
                "path": path,
                "status": _safe_int(payload.get("status")) or 0,
                "endpoint": str(payload.get("endpoint") or ""),
                "method": str(payload.get("method") or ""),
                "user_id": user_id,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Gera relatorio de uso real (SPA vs SSR, ranking por modulo, uso por perfil e frequencia diaria) "
            "a partir de logs estruturados de http_request."
        )
    )
    parser.add_argument(
        "--app-log",
        action="append",
        required=True,
        help="Arquivo de log JSONL da aplicacao (pode repetir).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Janela de dias para analise (default: 30).",
    )
    parser.add_argument(
        "--db-url",
        default="",
        help="DATABASE_URL para mapear user_id -> perfil/login.",
    )
    parser.add_argument(
        "--exclude-login-prefix",
        action="append",
        default=["e2e_", "qa_", "loadtest", "smoke", "release-bot"],
        help="Prefixos de login tecnico a excluir da analise humana (pode repetir).",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Arquivo de saida JSON (opcional).",
    )
    args = parser.parse_args()

    log_paths = [Path(item).expanduser().resolve() for item in args.app_log]
    since = datetime.now(timezone.utc) - timedelta(days=max(1, int(args.days)))
    db_url = (args.db_url or os.getenv("DATABASE_URL", "") or "").strip()
    prefixes = [str(item or "").strip().lower() for item in args.exclude_login_prefix if str(item or "").strip()]

    users_by_id, excluded_user_ids, user_mapping_status = _resolve_user_profiles(
        db_url,
        exclude_login_prefixes=prefixes,
    )
    raw_payloads = list(_iter_json_logs(log_paths))
    human_records = _collect_human_records(raw_payloads, since=since, excluded_user_ids=excluded_user_ids)
    report = _build_report(human_records, users_by_id=users_by_id, excluded_user_ids=excluded_user_ids)
    report["meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": max(1, int(args.days)),
        "since": since.isoformat(),
        "app_logs": [str(path) for path in log_paths],
        "raw_payloads_scanned": len(raw_payloads),
        "user_mapping_status": user_mapping_status,
        "db_mapping_enabled": bool(db_url),
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
