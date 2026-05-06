from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, relative_path: str):
    target = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, target)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _DummyOpener:
    def __init__(self):
        self.handlers = []


def test_login_falls_back_to_api_session_when_html_csrf_missing(monkeypatch):
    module = _load_module(
        "load_test_authenticated_test",
        "ops/scripts/perf/load_test_authenticated.py",
    )

    opener = _DummyOpener()
    sequence: list[tuple[str, str]] = []

    monkeypatch.setattr(module, "_build_opener", lambda **kwargs: _DummyOpener())

    def fake_request(opener_arg, url, **kwargs):
        method = kwargs.get("method", "GET")
        sequence.append((method, url))
        if url.endswith("/login") and method == "GET":
            return 200, "<html><body>no csrf here</body></html>", None, "", url, 1
        if url.endswith("/api/v1/session") and method == "GET":
            authenticated = sequence.count((method, url)) > 1
            return 200, json.dumps({"csrf_token": "api-csrf-token", "authenticated": authenticated}), None, "", url, 1
        if url.endswith("/api/v1/session/login") and method == "POST":
            assert kwargs["json_payload"] == {"login": "qa_release_load", "senha": "secret"}
            assert kwargs["headers"]["X-CSRFToken"] == "api-csrf-token"
            return 200, json.dumps({"code": "auth_ok", "authenticated": True}), None, "", url, 1
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(module, "_request_with_transport_retries", fake_request)

    ok, reason = module._login(
        opener,
        base_url="http://127.0.0.1:8102",
        login="qa_release_load",
        password="secret",
        timeout=15,
        retries=1,
    )

    assert ok is True
    assert reason == "ok"
    assert sequence == [
        ("GET", "http://127.0.0.1:8102/login"),
        ("GET", "http://127.0.0.1:8102/api/v1/session"),
        ("POST", "http://127.0.0.1:8102/api/v1/session/login"),
        ("GET", "http://127.0.0.1:8102/api/v1/session"),
    ]


def test_login_reports_api_fallback_failure_when_html_csrf_is_missing(monkeypatch):
    module = _load_module(
        "load_test_authenticated_test_failure",
        "ops/scripts/perf/load_test_authenticated.py",
    )

    opener = _DummyOpener()
    monkeypatch.setattr(module, "_build_opener", lambda **kwargs: _DummyOpener())

    def fake_request(opener_arg, url, **kwargs):
        method = kwargs.get("method", "GET")
        if url.endswith("/login") and method == "GET":
            return 200, "<html><body>still no csrf</body></html>", None, "", url, 1
        if url.endswith("/api/v1/session") and method == "GET":
            return 200, json.dumps({"csrf_token": "api-csrf-token"}), None, "", url, 1
        if url.endswith("/api/v1/session/login") and method == "POST":
            return 401, json.dumps({"code": "auth_invalid_credentials", "authenticated": False}), None, "", url, 1
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(module, "_request_with_transport_retries", fake_request)

    ok, reason = module._login(
        opener,
        base_url="http://127.0.0.1:8102",
        login="qa_release_load",
        password="secret",
        timeout=15,
        retries=1,
    )

    assert ok is False
    assert reason == "csrf_missing;api_fallback:api_login_status:401:401"


def test_login_falls_back_to_api_when_frontend_redirect_is_unreachable(monkeypatch):
    module = _load_module(
        "load_test_authenticated_test_frontend_redirect_failure",
        "ops/scripts/perf/load_test_authenticated.py",
    )

    opener = _DummyOpener()
    sequence: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "_build_opener", lambda **kwargs: _DummyOpener())

    def fake_request(opener_arg, url, **kwargs):
        method = kwargs.get("method", "GET")
        sequence.append((method, url))
        if url.endswith("/login") and method == "GET":
            return 0, "", "connection_refused", "frontend_local_origin_refused", url, 2
        if url.endswith("/api/v1/session") and method == "GET":
            authenticated = sequence.count((method, url)) > 1
            return 200, json.dumps({"csrf_token": "api-csrf-token", "authenticated": authenticated}), None, "", url, 1
        if url.endswith("/api/v1/session/login") and method == "POST":
            assert kwargs["json_payload"] == {"login": "loadtest_2933b", "senha": "secret"}
            return 200, json.dumps({"code": "auth_ok", "authenticated": True}), None, "", url, 1
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(module, "_request_with_transport_retries", fake_request)

    ok, reason = module._login(
        opener,
        base_url="http://127.0.0.1:8102",
        login="loadtest_2933b",
        password="secret",
        timeout=15,
        retries=1,
    )

    assert ok is True
    assert reason == "ok"
    assert sequence == [
        ("GET", "http://127.0.0.1:8102/login"),
        ("GET", "http://127.0.0.1:8102/api/v1/session"),
        ("POST", "http://127.0.0.1:8102/api/v1/session/login"),
        ("GET", "http://127.0.0.1:8102/api/v1/session"),
    ]


def test_authenticated_matrix_preserves_zero_percent_5xx():
    module = _load_module(
        "run_authenticated_matrix_test",
        "ops/scripts/perf/run_authenticated_matrix.py",
    )

    result = module.ScenarioResult(
        workers=20,
        seconds=300,
        run_index=1,
        success=True,
        report={
            "latency_ms": {"p50": 120.0, "p95": 420.0, "p99": 610.0},
            "availability_percent": 100.0,
            "percent_5xx": 0.0,
            "non_http_errors": 0,
            "auth_failures": 0,
            "permission_failures": 0,
            "login_failures": [],
            "preflight": {"auth_failures": []},
            "per_endpoint": {
                "/dashboard": {
                    "latency_ms": {"p95": 420.0},
                }
            },
        },
    )

    summary = module._summarize([result])

    assert summary["percent_5xx"]["median"] == 0.0
    assert summary["percent_5xx"]["worst"] == 0.0
    assert module._scenario_pass(summary) is True


def test_load_test_authenticated_classifies_phase_metrics():
    module = _load_module(
        "load_test_authenticated_phase_test",
        "ops/scripts/perf/load_test_authenticated.py",
    )

    assert module._phase_for_endpoint("/login") == "login"
    assert module._phase_for_endpoint("/api/v1/session") == "sessao"
    assert module._phase_for_endpoint("/dashboard") == "rota_principal"
    assert module._phase_for_endpoint("/bases/api/dados") == "json"
    assert module._phase_for_endpoint("/jobs/5/status") == "fila_jobs"
    assert module._phase_for_endpoint("/treinamentos/consolidado/export.pdf?status=vencido") == "pdf"
    assert module._phase_for_endpoint("/tripulantes/1/foto") == "storage"
    assert module._phase_for_endpoint("/pernoites?tipo=cobertura_base") == "queries"

    metrics = module._phase_metrics(
        [
            {"phase": "json", "duration_ms": 100.0, "status": 200, "endpoint": "/bases/api/dados"},
            {"phase": "json", "duration_ms": 200.0, "status": 200, "endpoint": "/bases/api/dados"},
            {"phase": "fila_jobs", "duration_ms": 175.0, "status": 200, "endpoint": "/jobs/5/status"},
            {"phase": "queries", "duration_ms": 150.0, "status": 200, "endpoint": "/pernoites?tipo=cobertura_base"},
        ]
    )

    assert metrics["json"]["requests"] == 2
    assert metrics["json"]["latency_ms"]["p95"] == 200.0
    assert metrics["fila_jobs"]["requests"] == 1
    assert metrics["queries"]["requests"] == 1
    assert metrics["pdf"]["exercised"] is False
