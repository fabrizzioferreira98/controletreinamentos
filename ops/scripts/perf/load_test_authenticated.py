from __future__ import annotations

import argparse
import json
import socket
import os
import sys
import random
import re
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar


CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
LOAD_PHASES = ("login", "sessao", "rota_principal", "json", "fila_jobs", "pdf", "storage", "queries")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = max(0, min(len(values) - 1, int(round((p / 100.0) * (len(values) - 1)))))
    return sorted(values)[idx]


def _extract_csrf(html: str) -> str | None:
    match = CSRF_RE.search(html or "")
    if not match:
        return None
    return match.group(1)


def _looks_like_login_page(html: str) -> bool:
    normalized = (html or "").lower()
    has_credentials_form = 'name="login"' in normalized and 'name="senha"' in normalized
    has_login_marker = (
        "<title>login" in normalized
        or "entrar no sistema" in normalized
        or "login-form-panel" in normalized
    )
    return has_credentials_form and has_login_marker


def _phase_for_endpoint(endpoint: str) -> str:
    normalized = (endpoint or "").strip().lower()
    path = normalized.split("?", 1)[0]
    if path in {"/login", "/api/v1/session/login"}:
        return "login"
    if path == "/api/v1/session":
        return "sessao"
    if path.endswith(".pdf") or "/export.pdf" in path:
        return "pdf"
    if "/foto" in path or "/arquivo" in path or "/anexo" in path or "/download" in path:
        return "storage"
    if path.startswith("/jobs/"):
        return "fila_jobs"
    if path.endswith("/dados") or path.startswith("/api/"):
        return "json"
    if "?" in normalized:
        return "queries"
    return "rota_principal"


def _phase_metrics(samples: list[dict]) -> dict:
    metrics: dict[str, dict] = {}
    for phase in LOAD_PHASES:
        phase_samples = [item for item in samples if item.get("phase") == phase]
        durations = [float(item.get("duration_ms", 0.0) or 0.0) for item in phase_samples]
        statuses = sorted({int(item.get("status", 0) or 0) for item in phase_samples})
        metrics[phase] = {
            "exercised": bool(phase_samples),
            "requests": len(phase_samples),
            "latency_ms": {
                "p50": round(_percentile(durations, 50), 2),
                "p95": round(_percentile(durations, 95), 2),
                "p99": round(_percentile(durations, 99), 2),
                "avg": round(statistics.mean(durations), 2) if durations else 0.0,
            },
            "status_histogram": {
                str(status): sum(1 for item in phase_samples if int(item.get("status", 0) or 0) == status)
                for status in statuses
            },
            "sample_endpoints": sorted({str(item.get("endpoint", "") or "") for item in phase_samples})[:8],
        }
    return metrics


def _build_opener(*, follow_redirects: bool = True) -> urllib.request.OpenerDirector:
    cookie_jar = CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(cookie_jar)]
    if not follow_redirects:
        handlers.insert(0, _NoRedirect())
    return urllib.request.build_opener(*handlers)


def _cookie_jar_from_opener(opener: urllib.request.OpenerDirector) -> CookieJar | None:
    for handler in opener.handlers:
        if isinstance(handler, urllib.request.HTTPCookieProcessor):
            return handler.cookiejar
    return None


def _clone_cookie_jar(source: CookieJar) -> CookieJar:
    cloned = CookieJar()
    for cookie in source:
        cloned.set_cookie(cookie)
    return cloned


def _build_opener_with_cookie_jar(cookie_jar: CookieJar, *, follow_redirects: bool = True) -> urllib.request.OpenerDirector:
    handlers = [urllib.request.HTTPCookieProcessor(cookie_jar)]
    if not follow_redirects:
        handlers.insert(0, _NoRedirect())
    return urllib.request.build_opener(*handlers)


def _classify_transport_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, TimeoutError) or isinstance(exc, socket.timeout):
        return "timeout", str(exc)
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError) or isinstance(reason, socket.timeout):
            return "timeout", str(reason)
        reason_text = str(reason or exc).lower()
        if "name or service not known" in reason_text or "temporary failure in name resolution" in reason_text:
            return "dns_error", str(reason or exc)
        if "connection reset" in reason_text:
            return "connection_reset", str(reason or exc)
        if "connection refused" in reason_text:
            return "connection_refused", str(reason or exc)
        return "url_error", str(reason or exc)
    if isinstance(exc, ConnectionResetError):
        return "connection_reset", str(exc)
    if isinstance(exc, ConnectionRefusedError):
        return "connection_refused", str(exc)
    if isinstance(exc, socket.gaierror):
        return "dns_error", str(exc)
    return exc.__class__.__name__.lower(), str(exc)


def _request(
    opener,
    url: str,
    *,
    method: str = "GET",
    data: dict | None = None,
    json_payload: dict | None = None,
    headers: dict | None = None,
    timeout: int = 15,
) -> tuple[int, str, str | None, str, str]:
    payload = None
    request_headers = dict(headers or {})
    if data is not None and json_payload is not None:
        raise ValueError("data e json_payload sÃ£o mutuamente exclusivos")
    if data is not None:
        payload = urllib.parse.urlencode(data).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_payload is not None:
        payload = json.dumps(json_payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, method=method, data=payload, headers=request_headers)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="ignore"), None, "", response.geturl()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        return exc.code, body, None, "", url
    except Exception as exc:
        error_type, error_detail = _classify_transport_error(exc)
        return 0, "", error_type, error_detail, url


def _request_with_transport_retries(
    opener,
    url: str,
    *,
    method: str = "GET",
    data: dict | None = None,
    json_payload: dict | None = None,
    headers: dict | None = None,
    timeout: int = 15,
    transport_retries: int = 1,
) -> tuple[int, str, str | None, str, str, int]:
    max_retries = max(0, int(transport_retries))
    attempts = 0
    while True:
        attempts += 1
        status, body, error_type, error_detail, final_url = _request(
            opener,
            url,
            method=method,
            data=data,
            json_payload=json_payload,
            headers=headers,
            timeout=timeout,
        )
        if status != 0 or attempts > (max_retries + 1):
            return status, body, error_type, error_detail, final_url, attempts
        # Backoff curto para absorver jitter de rede sem mascarar instabilidade persistente.
        time.sleep(min(0.2 * attempts, 0.8))


def _json_request_with_transport_retries(
    opener,
    url: str,
    *,
    method: str = "GET",
    data: dict | None = None,
    json_payload: dict | None = None,
    headers: dict | None = None,
    timeout: int = 15,
    transport_retries: int = 1,
) -> tuple[int, dict | None, str | None, str, str, int]:
    status, body, error_type, error_detail, final_url, attempts = _request_with_transport_retries(
        opener,
        url,
        method=method,
        data=data,
        json_payload=json_payload,
        headers=headers,
        timeout=timeout,
        transport_retries=transport_retries,
    )
    if status == 0:
        return status, None, error_type, error_detail, final_url, attempts
    try:
        payload = json.loads(body or "{}")
    except json.JSONDecodeError:
        return status, None, "invalid_json", "response_not_json", final_url, attempts
    if not isinstance(payload, dict):
        return status, None, "invalid_json_shape", "response_not_dict", final_url, attempts
    return status, payload, error_type, error_detail, final_url, attempts


def _login_via_api(
    opener,
    *,
    base_url: str,
    login: str,
    password: str,
    timeout: int,
) -> tuple[bool, str]:
    session_url = f"{base_url}/api/v1/session"
    status, payload, error_type, error_detail, _final_url, _attempts = _json_request_with_transport_retries(
        opener,
        session_url,
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        timeout=timeout,
        transport_retries=1,
    )
    if status != 200 or not payload:
        suffix = error_type or error_detail or status
        return False, f"api_session_status:{status}:{suffix}"

    csrf_token = str(payload.get("csrf_token", "") or "").strip()
    if not csrf_token:
        return False, "api_csrf_missing"

    status, payload, error_type, error_detail, _final_url, _attempts = _json_request_with_transport_retries(
        opener,
        f"{base_url}/api/v1/session/login",
        method="POST",
        json_payload={"login": login, "senha": password},
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": csrf_token,
        },
        timeout=timeout,
        transport_retries=1,
    )
    if status != 200 or not payload:
        suffix = error_type or error_detail or status
        return False, f"api_login_status:{status}:{suffix}"
    if str(payload.get("code", "") or "").strip() != "auth_ok":
        return False, f"api_login_code:{payload.get('code')}"
    if not bool(payload.get("authenticated")):
        return False, "api_login_authenticated_false"

    verify_status, verify_payload, error_type, error_detail, _final_url, _attempts = _json_request_with_transport_retries(
        opener,
        session_url,
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        timeout=timeout,
        transport_retries=1,
    )
    if verify_status != 200 or not verify_payload:
        suffix = error_type or error_detail or verify_status
        return False, f"session_after_api_login_status:{verify_status}:{suffix}"
    if not bool(verify_payload.get("authenticated")):
        return False, "session_after_api_login_authenticated_false"
    return True, "ok"


def _login(
    opener,
    *,
    base_url: str,
    login: str,
    password: str,
    timeout: int,
    retries: int = 4,
) -> tuple[bool, str]:
    login_url = f"{base_url}/login"
    no_redirect_opener = _build_opener(follow_redirects=False)
    for handler in opener.handlers:
        if isinstance(handler, urllib.request.HTTPCookieProcessor):
            # Compartilha o mesmo cookie jar entre openers para manter sessão/CSRF.
            no_redirect_opener = urllib.request.build_opener(_NoRedirect(), handler)
            break
    attempts = max(1, int(retries))
    last_reason = "unknown_login_failure"
    for attempt_idx in range(1, attempts + 1):
        status, html, _error_type, _error_detail, _final_url, _transport_attempts = _request_with_transport_retries(
            opener,
            login_url,
            timeout=timeout,
            transport_retries=1,
        )
        if status != 200:
            api_ok, api_reason = _login_via_api(
                opener,
                base_url=base_url,
                login=login,
                password=password,
                timeout=timeout,
            )
            if api_ok:
                return True, "ok"
            last_reason = f"login_page_status:{status};api_fallback:{api_reason}"
            if status == 429:
                # Evita falso negativo por janela curta de rate-limit no endpoint de login.
                time.sleep(min(15.0, 1.5 * attempt_idx))
            else:
                time.sleep(0.25)
            continue
        csrf = _extract_csrf(html)
        if not csrf:
            api_ok, api_reason = _login_via_api(
                opener,
                base_url=base_url,
                login=login,
                password=password,
                timeout=timeout,
            )
            if api_ok:
                return True, "ok"
            last_reason = f"csrf_missing;api_fallback:{api_reason}"
            time.sleep(0.25)
            continue
        status, body, _error_type, _error_detail, _final_url, _transport_attempts = _request_with_transport_retries(
            no_redirect_opener,
            login_url,
            method="POST",
            data={"csrf_token": csrf, "login": login, "senha": password},
            headers={"Referer": login_url, "Origin": base_url},
            timeout=timeout,
            transport_retries=1,
        )
        if status not in {200, 302, 303}:
            last_reason = f"login_post_status:{status}"
            if status == 429:
                time.sleep(min(15.0, 1.5 * attempt_idx))
            else:
                time.sleep(0.25)
            continue
        if status == 200 and _looks_like_login_page(body):
            last_reason = "invalid_credentials_or_auth_rejected"
            time.sleep(0.25)
            continue
        dash_status, dash_body, _error_type, _error_detail, _final_url, _transport_attempts = _request_with_transport_retries(
            opener,
            f"{base_url}/dashboard",
            timeout=timeout,
            transport_retries=1,
        )
        if dash_status != 200:
            last_reason = f"dashboard_after_login_status:{dash_status}"
            time.sleep(0.25)
            continue
        if _looks_like_login_page(dash_body):
            last_reason = "dashboard_redirected_to_login"
            time.sleep(0.25)
            continue
        return True, "ok"
    return False, last_reason


def _preflight_authenticated_endpoints(
    *,
    opener,
    base_url: str,
    endpoints: list[str],
    timeout: int,
    transport_retries: int,
) -> list[dict]:
    checks: list[dict] = []
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        status, body, error_type, error_detail, final_url, _attempts = _request_with_transport_retries(
            opener,
            url,
            timeout=timeout,
            transport_retries=transport_retries,
        )
        final_url_lower = (final_url or "").lower()
        if status in {301, 302, 303, 307, 308} and "/login" in final_url_lower:
            status = 401
        if status == 200 and ("/login" in final_url_lower or _looks_like_login_page(body)):
            status = 401
        checks.append(
            {
                "endpoint": endpoint,
                "status": int(status),
                "error_type": error_type,
                "error_detail": (error_detail or "")[:160],
            }
        )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste de carga autenticado para jornadas críticas.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--login", required=True)
    parser.add_argument("--password", default="", help="Senha do usuário de carga (evite CLI).")
    parser.add_argument(
        "--password-file",
        default="",
        help="Arquivo contendo senha do usuário de carga.",
    )
    parser.add_argument(
        "--password-env",
        default="LOADTEST_PASSWORD",
        help="Variável de ambiente com senha do usuário de carga (padrão: LOADTEST_PASSWORD).",
    )
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--login-retries", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--transport-retries",
        type=int,
        default=2,
        help="Quantidade de retries para erros de transporte (status=0) por requisição.",
    )
    parser.add_argument(
        "--max-recovered-transport-errors",
        type=int,
        default=50,
        help="Máximo aceitável de erros de transporte recuperados por retry antes de considerar FAIL.",
    )
    parser.add_argument(
        "--job-id",
        type=int,
        default=1,
        help="Job id usado no endpoint /jobs/<id>/status durante a carga autenticada.",
    )
    parser.add_argument(
        "--endpoints",
        default="",
        help="Lista opcional de endpoints separados por vírgula. Ex.: /dashboard,/treinamentos,/jobs/{job_id}/status",
    )
    parser.add_argument(
        "--max-non-http-errors",
        type=int,
        default=0,
        help="Máximo aceitável de requisições sem status HTTP (status=0).",
    )
    parser.add_argument(
        "--max-permission-failures",
        type=int,
        default=0,
        help="Máximo aceitável de respostas 403 (permissão insuficiente).",
    )
    parser.add_argument(
        "--require-preflight-auth",
        action="store_true",
        help="Falha o teste se o preflight detectar 401 em endpoint da jornada autenticada.",
    )
    parser.add_argument(
        "--include-bases-endpoint",
        action="store_true",
        help="Inclui /bases/api/dados?status=ativo no mix de endpoints autenticados.",
    )
    parser.add_argument(
        "--auth-mode",
        choices=("shared-session", "per-worker-login"),
        default="shared-session",
        help=(
            "shared-session reutiliza a sessão autenticada do preflight; "
            "per-worker-login faz login por worker."
        ),
    )
    args = parser.parse_args()
    password = ""
    if args.password:
        password = args.password
        print(
            "WARN: --password via CLI pode vazar no histórico. Prefira --password-file ou variável de ambiente.",
            file=sys.stderr,
        )
    elif args.password_file:
        try:
            password = (open(args.password_file, "r", encoding="utf-8").read() or "").strip()
        except OSError as exc:
            print(json.dumps({"success": False, "error": "password_file_error", "detail": str(exc)}, ensure_ascii=False, indent=2))
            return 1
    else:
        password_env = (args.password_env or "").strip() or "LOADTEST_PASSWORD"
        password = (os.getenv(password_env, "") or "").strip()
    if not password:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "missing_password",
                    "message": "Senha não informada. Use --password-file ou variável de ambiente.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    random.seed(args.seed)
    base_url = args.base_url.rstrip("/")
    if args.endpoints.strip():
        endpoints = [item.strip() for item in args.endpoints.split(",") if item.strip()]
    else:
        endpoints = [
            "/dashboard",
            "/treinamentos?status=vencido&periodo=30",
            "/treinamentos?periodo=expired&status=vencido",
            "/missoes?page=1",
            "/missoes?busca=voo&contratante=saude",
            "/notificacoes-email",
            "/monitoramento",
            "/usuarios?page=1",
            "/backups",
            "/jobs/{job_id}/status",
            "/treinamentos/consolidado?ordenacao=criticidade",
        ]
        if args.include_bases_endpoint:
            endpoints.append("/bases/api/dados?status=ativo")
    endpoints = [item.replace("{job_id}", str(max(1, int(args.job_id)))) for item in endpoints]

    preflight_opener = _build_opener()
    phase_samples: list[dict] = []
    login_started = time.perf_counter()
    preflight_login_ok, preflight_login_reason = _login(
        preflight_opener,
        base_url=base_url,
        login=args.login,
        password=password,
        timeout=max(3, int(args.timeout)),
        retries=max(1, int(args.login_retries)),
    )
    phase_samples.append(
        {
            "phase": "login",
            "duration_ms": (time.perf_counter() - login_started) * 1000.0,
            "endpoint": "/login",
            "status": 200 if preflight_login_ok else 0,
            "source": "preflight_login",
        }
    )
    preflight_checks: list[dict] = []
    if preflight_login_ok:
        session_started = time.perf_counter()
        session_status, _session_body, _session_error_type, _session_error_detail, _session_final_url, _session_attempts = (
            _request_with_transport_retries(
                preflight_opener,
                f"{base_url}/api/v1/session",
                headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
                timeout=max(3, int(args.timeout)),
                transport_retries=max(0, int(args.transport_retries)),
            )
        )
        phase_samples.append(
            {
                "phase": "sessao",
                "duration_ms": (time.perf_counter() - session_started) * 1000.0,
                "endpoint": "/api/v1/session",
                "status": int(session_status),
                "source": "preflight_session_probe",
            }
        )
        preflight_checks = _preflight_authenticated_endpoints(
            opener=preflight_opener,
            base_url=base_url,
            endpoints=endpoints,
            timeout=max(3, int(args.timeout)),
            transport_retries=max(0, int(args.transport_retries)),
        )
    preflight_auth_failures = [item for item in preflight_checks if int(item.get("status", 0)) == 401]
    preflight_permission_failures = [item for item in preflight_checks if int(item.get("status", 0)) == 403]
    preflight_cookie_jar = _cookie_jar_from_opener(preflight_opener) if preflight_login_ok else None
    if args.require_preflight_auth and (not preflight_login_ok or preflight_auth_failures):
        report = {
            "success": False,
            "authenticated": False,
            "base_url": base_url,
            "workers": int(args.workers),
            "seconds": int(args.seconds),
            "error": "preflight_auth_failed",
            "preflight": {
                "login_ok": preflight_login_ok,
                "login_reason": preflight_login_reason,
                "checks": preflight_checks,
                "auth_failures": preflight_auth_failures,
                "permission_failures": preflight_permission_failures,
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    deadline = time.time() + max(5, int(args.seconds))
    lock = threading.Lock()
    samples: list[dict] = []
    login_failures: list[str] = []
    failure_samples: list[dict] = []
    transport_error_counter: Counter[str] = Counter()
    transport_error_recovered_counter: Counter[str] = Counter()
    recovered_transport_errors_box = {"count": 0}

    def _worker(worker_id: int):
        if args.auth_mode == "shared-session" and preflight_cookie_jar is not None:
            opener = _build_opener_with_cookie_jar(_clone_cookie_jar(preflight_cookie_jar))
        else:
            opener = _build_opener()
            ok, reason = _login(
                opener,
                base_url=base_url,
                login=args.login,
                password=password,
                timeout=max(3, int(args.timeout)),
                retries=max(1, int(args.login_retries)),
            )
            if not ok:
                with lock:
                    login_failures.append(f"worker_{worker_id}:{reason}")
                return

        while time.time() < deadline:
            endpoint = random.choice(endpoints)
            url = f"{base_url}{endpoint}"
            started = time.perf_counter()
            status, body, error_type, error_detail, final_url, transport_attempts = _request_with_transport_retries(
                opener,
                url,
                timeout=max(3, int(args.timeout)),
                transport_retries=max(0, int(args.transport_retries)),
            )
            # Se houver expiração de sessão/redirecionamento silencioso para login,
            # considera como falha de autenticação da trilha protegida.
            final_url_lower = (final_url or "").lower()
            if status in {301, 302, 303, 307, 308} and "/login" in final_url_lower:
                status = 401
            if status == 200 and ("/login" in final_url_lower or _looks_like_login_page(body)):
                status = 401
            duration_ms = (time.perf_counter() - started) * 1000.0
            with lock:
                samples.append(
                    {
                        "status": int(status),
                        "duration_ms": duration_ms,
                        "endpoint": endpoint,
                        "phase": _phase_for_endpoint(endpoint),
                    }
                )
                if transport_attempts > 1 and status != 0:
                    recovered_transport_errors_local = transport_attempts - 1
                    recovered_transport_errors_box["count"] += recovered_transport_errors_local
                    if error_type:
                        transport_error_recovered_counter[error_type] += recovered_transport_errors_local
                if status == 0:
                    transport_error_counter[error_type or "unknown_transport_error"] += 1
                if (status in {0, 401, 403} or status >= 500) and len(failure_samples) < 30:
                    failure_samples.append(
                        {
                            "endpoint": endpoint,
                            "status": int(status),
                            "error_type": error_type,
                            "error_detail": (error_detail or "")[:160],
                            "body_snippet": (body or "")[:160].replace("\n", " ").strip(),
                        }
                    )

    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        for idx in range(max(1, int(args.workers))):
            pool.submit(_worker, idx + 1)

    durations = [item["duration_ms"] for item in samples]
    total = len(samples)
    non_http_errors = sum(1 for item in samples if item["status"] == 0)
    status_histogram = {
        str(status): sum(1 for item in samples if item["status"] == status)
        for status in sorted({item["status"] for item in samples})
    }
    auth_failures = sum(1 for item in samples if item["status"] == 401)
    permission_failures = sum(1 for item in samples if item["status"] == 403)
    total_5xx = sum(1 for item in samples if 500 <= item["status"] <= 599)
    status_non_error = [item for item in samples if item["status"] and item["status"] < 500]
    availability = (len(status_non_error) / total * 100.0) if total else 0.0
    percent_5xx = (total_5xx / total * 100.0) if total else 100.0

    report = {
        "authenticated": True,
        "base_url": base_url,
        "seconds": int(args.seconds),
        "workers": int(args.workers),
        "requests": total,
        "endpoints": endpoints,
        "login_failures": login_failures,
        "auth_failures": auth_failures,
        "permission_failures": permission_failures,
        "non_http_errors": non_http_errors,
        "availability_percent": round(availability, 2),
        "percent_5xx": round(percent_5xx, 3),
        "latency_ms": {
            "p50": round(_percentile(durations, 50), 2),
            "p95": round(_percentile(durations, 95), 2),
            "p99": round(_percentile(durations, 99), 2),
            "avg": round(statistics.mean(durations), 2) if durations else 0.0,
        },
        "status_histogram": status_histogram,
        "failure_samples": failure_samples,
        "transport_errors": {
            "non_http_by_type": dict(sorted(transport_error_counter.items())),
            "recovered_by_type": dict(sorted(transport_error_recovered_counter.items())),
            "recovered_total": int(recovered_transport_errors_box["count"]),
            "transport_retries": int(args.transport_retries),
        },
        "thresholds": {
            "availability_min_percent": 99.0,
            "p95_max_ms": 1200.0,
            "percent_5xx_max": 0.5,
            "login_failures_max": 0,
            "auth_failures_max": 0,
            "permission_failures_max": max(0, int(args.max_permission_failures)),
            "non_http_errors_max": max(0, int(args.max_non_http_errors)),
            "recovered_transport_errors_max": max(0, int(args.max_recovered_transport_errors)),
            "login_retries_per_worker": int(args.login_retries),
        },
    }
    report["phase_metrics"] = _phase_metrics([*phase_samples, *samples])
    report["slowest_phases_by_p95"] = [
        {"phase": key, "p95_ms": value["latency_ms"]["p95"], "requests": value["requests"]}
        for key, value in sorted(
            report["phase_metrics"].items(),
            key=lambda item: item[1]["latency_ms"]["p95"],
            reverse=True,
        )
        if value["requests"]
    ]
    endpoint_metrics = {}
    for endpoint in endpoints:
        endpoint_samples = [item for item in samples if item["endpoint"] == endpoint]
        endpoint_durations = [item["duration_ms"] for item in endpoint_samples]
        endpoint_hist = {
            str(status): sum(1 for item in endpoint_samples if item["status"] == status)
            for status in sorted({item["status"] for item in endpoint_samples})
        }
        endpoint_metrics[endpoint] = {
            "requests": len(endpoint_samples),
            "latency_ms": {
                "p50": round(_percentile(endpoint_durations, 50), 2),
                "p95": round(_percentile(endpoint_durations, 95), 2),
                "p99": round(_percentile(endpoint_durations, 99), 2),
                "avg": round(statistics.mean(endpoint_durations), 2) if endpoint_durations else 0.0,
            },
            "status_histogram": endpoint_hist,
            "auth_failures": sum(1 for item in endpoint_samples if item["status"] in {401, 403}),
            "non_http_errors": sum(1 for item in endpoint_samples if item["status"] == 0),
        }
    report["per_endpoint"] = endpoint_metrics
    report["preflight"] = {
        "login_ok": preflight_login_ok,
        "login_reason": preflight_login_reason,
        "checks": preflight_checks,
        "auth_failures": preflight_auth_failures,
        "permission_failures": preflight_permission_failures,
    }
    report["slowest_endpoints_by_p95"] = [
        {"endpoint": key, "p95_ms": value["latency_ms"]["p95"], "requests": value["requests"]}
        for key, value in sorted(
            endpoint_metrics.items(),
            key=lambda item: item[1]["latency_ms"]["p95"],
            reverse=True,
        )[:5]
    ]

    pass_conditions = (
        total > 0
        and not login_failures
        and auth_failures == 0
        and permission_failures <= max(0, int(args.max_permission_failures))
        and non_http_errors <= max(0, int(args.max_non_http_errors))
        and recovered_transport_errors_box["count"] <= max(0, int(args.max_recovered_transport_errors))
        and report["availability_percent"] >= 99.0
        and report["latency_ms"]["p95"] <= 1200.0
        and report["percent_5xx"] <= 0.5
    )
    report["success"] = bool(pass_conditions)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if pass_conditions else 1


if __name__ == "__main__":
    raise SystemExit(main())
