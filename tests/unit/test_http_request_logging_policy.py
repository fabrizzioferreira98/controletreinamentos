from backend.src.controle_treinamentos.core.security import _should_emit_http_request_log


def test_http_request_log_skips_fast_success_by_default(monkeypatch):
    monkeypatch.delenv("HTTP_ACCESS_LOG_ENABLED", raising=False)
    monkeypatch.delenv("HTTP_ACCESS_LOG_SLOW_MS", raising=False)

    assert _should_emit_http_request_log(200, 42) is False


def test_http_request_log_keeps_errors_and_slow_requests(monkeypatch):
    monkeypatch.delenv("HTTP_ACCESS_LOG_ENABLED", raising=False)
    monkeypatch.delenv("HTTP_ACCESS_LOG_SLOW_MS", raising=False)

    assert _should_emit_http_request_log(500, 42) is True
    assert _should_emit_http_request_log(200, 1000) is True


def test_http_request_log_can_be_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("HTTP_ACCESS_LOG_ENABLED", "1")

    assert _should_emit_http_request_log(200, 1) is True
