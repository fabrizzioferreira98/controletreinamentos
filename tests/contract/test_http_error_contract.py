import time
from urllib.parse import parse_qs, urlparse

import pytest
from flask import abort
from flask_login import login_required
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.core.domain_errors import (
    DomainConflictError,
    DomainForbiddenError,
    DomainNotFoundError,
    DomainUnavailableError,
    DomainUnexpectedError,
    DomainValidationError,
)


class _EmptyCursor:
    def fetchone(self):
        return None


class _InactiveCursor:
    def fetchone(self):
        return {
            "id": 7,
            "nome": "Inativo",
            "login": "inativo",
            "email": "inativo@local.test",
            "perfil": "operador",
            "ativo": 0,
            "permissao_modulos_json": "[]",
            "senha_hash": "",
        }


class _EmptyDB:
    def execute(self, _query, _params):
        return _EmptyCursor()


class _InactiveDB:
    def execute(self, _query, _params):
        return _InactiveCursor()


class _SingleCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _SingleUserDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params):
        return _SingleCursor(self._row)


def test_api_500_returns_json_contract():
    app = create_app()

    @app.route('/api/test-error-contract-500')
    def _test_error_500():
        raise RuntimeError('boom')

    client = app.test_client()
    response = client.get('/api/test-error-contract-500')

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 500
    assert payload["code"] == "internal_error"
    assert "request_id" in payload


def test_api_error_roundtrips_request_and_correlation_ids():
    app = create_app()

    @app.route('/api/test-error-correlation-contract')
    def _test_error_correlation():
        raise RuntimeError('boom-correlation')

    client = app.test_client()
    response = client.get(
        '/api/test-error-correlation-contract',
        headers={"X-Request-ID": "req-contract-123", "X-Correlation-ID": "corr-contract-456"},
    )

    assert response.status_code == 500
    assert response.headers.get("X-Request-ID") == "req-contract-123"
    assert response.headers.get("X-Correlation-ID") == "corr-contract-456"
    payload = response.get_json()
    assert payload["request_id"] == "req-contract-123"
    assert payload["correlation_id"] == "corr-contract-456"


def test_html_500_returns_stable_error_page_without_redirect():
    app = create_app()

    @app.route('/_test/html-error-contract-500')
    def _test_html_error_500():
        raise RuntimeError('boom-html-500')

    client = app.test_client()
    response = client.get('/_test/html-error-contract-500', follow_redirects=False)

    assert response.status_code == 500
    assert (response.headers.get("Location", "") or "") == ""
    body = response.get_data(as_text=True)
    assert "Erro interno do sistema" in body
    assert "Código de rastreio" in body


def test_html_503_returns_stable_error_page_without_redirect():
    app = create_app()

    @app.route('/_test/html-error-contract-503')
    def _test_html_error_503():
        abort(503)

    client = app.test_client()
    response = client.get('/_test/html-error-contract-503', follow_redirects=False)

    assert response.status_code == 503
    assert (response.headers.get("Location", "") or "") == ""
    body = response.get_data(as_text=True)
    assert "Serviço temporariamente indisponível" in body
    assert "Código de rastreio" in body


def test_binary_asset_503_does_not_redirect_or_return_html():
    app = create_app()

    @app.route('/_test/asset-error-contract-503')
    def _test_asset_error_503():
        abort(503)

    client = app.test_client()
    response = client.get(
        '/_test/asset-error-contract-503',
        headers={"Sec-Fetch-Dest": "image", "Accept": "image/avif,image/webp,*/*"},
        follow_redirects=False,
    )

    assert response.status_code == 503
    assert (response.headers.get("Location", "") or "") == ""
    assert response.get_data() == b""


def test_api_csrf_returns_json_contract():
    app = create_app()

    @app.route('/api/test-error-contract-csrf', methods=['POST'])
    def _test_error_csrf():
        return {"ok": True}, 200

    client = app.test_client()
    response = client.post('/api/test-error-contract-csrf', data={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 400
    assert payload["code"] == "csrf_error"


def test_api_error_handlers_return_stable_json_contract_for_common_statuses():
    app = create_app()
    status_to_code = {
        400: "bad_request",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "unprocessable_entity",
        503: "service_unavailable",
    }

    for status in status_to_code:
        route = f"/api/test-error-contract-{status}"
        endpoint = f"_test_error_{status}"

        def _factory(error_status):
            def _raise_error():
                abort(error_status)

            return _raise_error

        app.add_url_rule(route, endpoint, _factory(status))

    client = app.test_client()
    for status, expected_code in status_to_code.items():
        response = client.get(f"/api/test-error-contract-{status}")
        assert response.status_code == status
        payload = response.get_json()
        assert payload["success"] is False
        assert payload["status"] == status
        assert payload["code"] == expected_code
        assert "request_id" in payload


def test_domain_error_taxonomy_has_stable_minimum_codes():
    cases = [
        (DomainValidationError("validacao"), 400, "validation"),
        (DomainNotFoundError("nao encontrado"), 404, "not_found"),
        (DomainConflictError("conflito"), 409, "conflict"),
        (DomainForbiddenError("negado"), 403, "forbidden"),
        (DomainUnavailableError("indisponivel"), 503, "unavailable"),
        (DomainUnexpectedError("inesperado"), 500, "unexpected"),
    ]

    for error, expected_status, expected_code in cases:
        assert error.status == expected_status
        assert error.code == expected_code
        assert error.message


def test_api_domain_error_handler_returns_stable_json_contract_for_taxonomy():
    app = create_app()
    cases = {
        "validation": DomainValidationError("Falha de validacao."),
        "not-found": DomainNotFoundError("Registro nao encontrado."),
        "conflict": DomainConflictError("Conflito de dados."),
        "forbidden": DomainForbiddenError("Acesso negado."),
        "unavailable": DomainUnavailableError("Servico indisponivel."),
        "unexpected": DomainUnexpectedError("Falha inesperada."),
    }

    for name, error in cases.items():
        route = f"/api/test-domain-error-{name}"
        endpoint = f"_test_domain_error_{name.replace('-', '_')}"

        def _factory(exc):
            def _raise_domain_error():
                raise exc

            return _raise_domain_error

        app.add_url_rule(route, endpoint, _factory(error))

    client = app.test_client()
    for name, error in cases.items():
        response = client.get(
            f"/api/test-domain-error-{name}",
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == error.status
        payload = response.get_json()
        assert payload["success"] is False
        assert payload["status"] == error.status
        assert payload["code"] == error.code
        assert payload["message"] == error.message
        assert "request_id" in payload


def test_api_domain_error_handler_preserves_explicit_details():
    app = create_app()

    @app.route("/api/test-domain-error-details")
    def _test_domain_error_details():
        raise DomainValidationError(
            "Campo invalido.",
            code="field_invalid",
            details={"field": "base_id", "reason": "invalid"},
        )

    client = app.test_client()
    response = client.get(
        "/api/test-domain-error-details",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 400
    assert payload["code"] == "field_invalid"
    assert payload["details"] == {"field": "base_id", "reason": "invalid"}
    assert "request_id" in payload


def test_html_domain_validation_redirects_with_flash():
    app = create_app()

    @app.route("/_test/domain-validation-html")
    def _test_domain_validation_html():
        raise DomainValidationError("Revise os dados informados.", code="test_validation")

    client = app.test_client()
    response = client.get("/_test/domain-validation-html", follow_redirects=False)

    assert response.status_code in {302, 303}
    assert "/login" in (response.headers.get("Location", "") or "")
    with client.session_transaction() as session:
        assert ("error", "Revise os dados informados.") in session.get("_flashes", [])


def test_html_domain_unavailable_returns_stable_error_page():
    app = create_app()

    @app.route("/_test/domain-unavailable-html")
    def _test_domain_unavailable_html():
        raise DomainUnavailableError("Dependencia externa indisponivel.", code="test_unavailable")

    client = app.test_client()
    response = client.get("/_test/domain-unavailable-html", follow_redirects=False)

    assert response.status_code == 503
    assert (response.headers.get("Location", "") or "") == ""
    body = response.get_data(as_text=True)
    assert "Dependencia externa indisponivel." in body
    assert "Código de rastreio" in body or "Codigo de rastreio" in body or "CÃ³digo de rastreio" in body


def test_binary_domain_error_does_not_redirect_to_html():
    app = create_app()

    @app.route("/_test/domain-image-error")
    def _test_domain_image_error():
        raise DomainNotFoundError("Imagem nao encontrada.", code="test_image_not_found")

    client = app.test_client()
    response = client.get(
        "/_test/domain-image-error",
        headers={"Sec-Fetch-Dest": "image", "Accept": "image/avif,image/webp,*/*"},
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert (response.headers.get("Location", "") or "") == ""
    assert response.get_data() == b""


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        ("/sw.js", {"Sec-Fetch-Dest": "serviceworker", "Accept": "*/*"}),
        ("/browserconfig.xml", {"Sec-Fetch-Dest": "empty", "Accept": "*/*"}),
    ],
)
def test_non_document_not_found_probes_do_not_flash_or_redirect(path, headers):
    app = create_app()
    client = app.test_client()

    response = client.get(path, headers=headers, follow_redirects=False)

    assert response.status_code == 404
    assert (response.headers.get("Location", "") or "") == ""
    assert response.get_data() == b""
    with client.session_transaction() as session:
        assert session.get("_flashes", []) == []


def test_document_not_found_keeps_html_flash_redirect_contract():
    app = create_app()
    client = app.test_client()

    response = client.get(
        "/_test/not-found-document-contract",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
        },
        follow_redirects=False,
    )

    assert response.status_code in {302, 303}
    assert "/login" in (response.headers.get("Location", "") or "")
    with client.session_transaction() as session:
        assert ("error", "Recurso não encontrado.") in session.get("_flashes", [])


def test_internal_metrics_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "token-123")
    app = create_app()
    client = app.test_client()

    forbidden = client.get('/api/internal/metrics')
    assert forbidden.status_code == 403

    allowed = client.get('/api/internal/metrics', headers={"X-Metrics-Token": "token-123"})
    assert allowed.status_code == 200
    assert "TYPE http_requests_total counter" in allowed.get_data(as_text=True)


def test_internal_error_trace_requires_auth_or_metrics_token(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "token-123")
    app = create_app()
    client = app.test_client()

    forbidden = client.get("/api/internal/errors/naoexiste")
    assert forbidden.status_code == 401
    payload = forbidden.get_json()
    assert payload["code"] == "auth_required"


def test_internal_error_trace_returns_event_for_known_request_id(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "token-123")
    monkeypatch.setenv("APP_RELEASE_ID", "release-test-1")
    app = create_app()

    @app.route('/_test/internal-error-trace-source')
    def _test_internal_error_trace_source():
        raise RuntimeError("boom-trace")

    client = app.test_client()
    failed = client.get(
        '/_test/internal-error-trace-source',
        headers={"X-Correlation-ID": "corr-error-trace-123"},
        follow_redirects=False,
    )
    assert failed.status_code == 500
    request_id = (failed.headers.get("X-Request-ID", "") or "").strip()
    assert request_id

    trace = client.get(
        f"/api/internal/errors/{request_id}",
        headers={"X-Metrics-Token": "token-123"},
    )
    assert trace.status_code == 200
    payload = trace.get_json()
    assert payload["success"] is True
    assert payload["code"] == "error_event_found"
    assert payload["event"]["request_id"] == request_id
    assert payload["event"]["correlation_id"] == "corr-error-trace-123"
    assert payload["event"]["release_id"] == "release-test-1"
    assert payload["event"]["status"] == 500
    assert payload["event"]["code"] == "internal_error"


def test_programmatic_request_without_session_returns_json_401():
    app = create_app()
    client = app.test_client()
    response = client.get(
        "/tripulantes",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 401
    assert payload["code"] == "auth_required"


def test_programmatic_protected_route_returns_403_when_session_user_is_inactive(monkeypatch):
    app = create_app()
    client = app.test_client()
    monkeypatch.setattr("src.app.models.get_db", lambda: _InactiveDB())

    with client.session_transaction() as sess:
        sess["_user_id"] = "7"
        sess["_fresh"] = True

    response = client.get(
        "/tripulantes",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 403
    assert payload["code"] == "auth_user_inactive"
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None


def test_html_protected_route_redirects_to_login_when_session_user_is_inactive(monkeypatch):
    app = create_app()
    client = app.test_client()
    monkeypatch.setattr("src.app.models.get_db", lambda: _InactiveDB())

    with client.session_transaction() as sess:
        sess["_user_id"] = "7"
        sess["_fresh"] = True

    response = client.get("/tripulantes?page=2", follow_redirects=False)

    assert response.status_code in {302, 303}
    location = response.headers.get("Location", "") or ""
    assert "/login" in location
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert query.get("auth_issue") == ["user_inactive"]
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None


def test_internal_metrics_is_blocked_in_production_without_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-for-test-long")
    monkeypatch.setenv("DATABASE_URL", "postgresql://local-user:local-pass@db.example.com:5432/postgres")
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    app = create_app()
    client = app.test_client()

    response = client.get("/api/internal/metrics")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 503
    assert payload["code"] == "metrics_unconfigured"


def test_internal_metrics_is_blocked_without_token_even_outside_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "dev-secret-for-test")
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    app = create_app()
    client = app.test_client()

    response = client.get("/api/internal/metrics")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 503
    assert payload["code"] == "metrics_unconfigured"


def test_programmatic_jobs_status_without_session_returns_json_401():
    app = create_app()
    client = app.test_client()

    response = client.get("/jobs/999/status")

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 401
    assert payload["code"] == "auth_required"


def test_programmatic_bases_history_without_session_returns_json_401():
    app = create_app()
    client = app.test_client()

    response = client.get("/bases/pilotos/1/historico")

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 401
    assert payload["code"] == "auth_required"


def test_programmatic_permission_required_route_without_session_returns_json_401():
    app = create_app()
    client = app.test_client()

    response = client.get(
        "/usuarios",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["code"] == "auth_required"


def test_programmatic_post_without_session_prefers_auth_required_over_csrf():
    app = create_app()
    client = app.test_client()

    response = client.post("/jobs/1/reativar")

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 401
    assert payload["code"] == "auth_required"


def test_non_programmatic_binary_route_without_session_returns_401_without_html_redirect():
    app = create_app()
    client = app.test_client()

    response = client.get("/bases/pilotos/1/foto", follow_redirects=False)

    assert response.status_code == 401
    assert (response.headers.get("Location", "") or "") == ""


def test_tripulante_photo_without_session_returns_401_without_html_redirect():
    app = create_app()
    client = app.test_client()

    response = client.get("/tripulantes/1/foto", follow_redirects=False)

    assert response.status_code == 401
    assert (response.headers.get("Location", "") or "") == ""


def test_html_protected_route_redirects_to_login_with_next():
    app = create_app()
    client = app.test_client()

    response = client.get("/tripulantes?page=2", follow_redirects=False)

    assert response.status_code in {302, 303}
    location = response.headers.get("Location", "") or ""
    assert "/login" in location
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert query.get("next") == ["/tripulantes?page=2"]


def test_html_protected_route_with_browser_accept_header_still_redirects():
    app = create_app()
    client = app.test_client()

    response = client.get(
        "/tripulantes?page=2",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
        },
        follow_redirects=False,
    )

    assert response.status_code in {302, 303}
    location = response.headers.get("Location", "") or ""
    assert "/login" in location


def test_api_logout_without_session_is_json_idempotent():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/v1/session/logout",
        headers={"Accept": "text/html", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "logout_ok"
    assert payload["authenticated"] is False


def test_logout_html_without_session_redirects_to_login():
    app = create_app()
    client = app.test_client()

    page = client.get("/login")
    html = page.get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    csrf = html.split(marker, 1)[1].split('"', 1)[0]

    response = client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)

    assert response.status_code in {302, 303}
    assert "/login" in (response.headers.get("Location", "") or "")


def test_logout_html_get_without_session_redirects_to_login():
    app = create_app()
    client = app.test_client()

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code in {302, 303}
    assert "/login" in (response.headers.get("Location", "") or "")


def test_api_logout_authenticated_returns_json_200(monkeypatch):
    app = create_app()
    client = app.test_client()

    row = {
        "id": 8,
        "nome": "Ativo",
        "login": "ativo_logout",
        "email": "ativo_logout@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf = client.get("/api/v1/session").get_json()["csrf_token"]
    login_resp = client.post(
        "/api/v1/session/login",
        json={"login": "ativo_logout", "senha": "secret"},
        headers={"X-CSRFToken": csrf},
        follow_redirects=False,
    )
    assert login_resp.status_code == 200

    response = client.post(
        "/api/v1/session/logout",
        headers={"Accept": "text/html", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "logout_ok"
    assert payload["next"] == "/login"
    assert payload["authenticated"] is False


def test_logout_html_get_authenticated_does_not_terminate_session(monkeypatch):
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    row = {
        "id": 8,
        "nome": "Ativo",
        "login": "ativo_logout_get",
        "email": "ativo_logout_get@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    page = client.get("/login")
    html = page.get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    csrf = html.split(marker, 1)[1].split('"', 1)[0]
    login_resp = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "ativo_logout_get", "senha": "secret"},
        follow_redirects=False,
    )
    assert login_resp.status_code in {302, 303}

    logout_resp = client.get("/logout", follow_redirects=False)
    assert logout_resp.status_code in {302, 303}
    location = logout_resp.headers.get("Location", "") or ""
    assert "/login" not in location

    with client.session_transaction() as sess:
        assert sess.get("_user_id") == "8"


def test_logout_html_get_with_programmatic_headers_still_redirects_to_login(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "dev-secret-for-test")
    app = create_app()
    client = app.test_client()

    response = client.get(
        "/logout",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303}
    assert response.get_json(silent=True) is None
    assert "/login" in (response.headers.get("Location", "") or "")

    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None


def test_logout_html_post_with_invalid_csrf_still_terminates_session(monkeypatch):
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    row = {
        "id": 9,
        "nome": "Ativo",
        "login": "ativo_logout_csrf",
        "email": "ativo_logout_csrf@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    page = client.get("/login")
    html = page.get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    csrf = html.split(marker, 1)[1].split('"', 1)[0]
    login_resp = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "ativo_logout_csrf", "senha": "secret"},
        follow_redirects=False,
    )
    assert login_resp.status_code in {302, 303}

    app.config["WTF_CSRF_ENABLED"] = True
    logout_resp = client.post("/logout", data={"csrf_token": "invalid-token"}, follow_redirects=False)
    assert logout_resp.status_code in {302, 303}
    assert "/login" in (logout_resp.headers.get("Location", "") or "")

    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None


def test_logout_html_post_with_programmatic_headers_and_invalid_csrf_still_redirects(monkeypatch):
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    row = {
        "id": 10,
        "nome": "Ativo",
        "login": "ativo_logout_csrf_json",
        "email": "ativo_logout_csrf_json@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    page = client.get("/login")
    html = page.get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    csrf = html.split(marker, 1)[1].split('"', 1)[0]
    login_resp = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "ativo_logout_csrf_json", "senha": "secret"},
        follow_redirects=False,
    )
    assert login_resp.status_code in {302, 303}

    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post(
        "/logout",
        data={"csrf_token": "invalid-token"},
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}
    assert response.get_json(silent=True) is None
    assert "/login" in (response.headers.get("Location", "") or "")

    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None


def test_login_programmatic_invalid_credentials_returns_json_401(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: _EmptyDB())

    csrf = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "invalido", "senha": "x"},
        headers={"X-CSRFToken": csrf, "Accept": "text/html", "X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["code"] == "auth_invalid_credentials"


def test_login_programmatic_inactive_user_returns_json_403(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: _InactiveDB())

    csrf = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "inativo", "senha": "x"},
        headers={"X-CSRFToken": csrf, "Accept": "text/html", "X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["code"] == "auth_user_inactive"


def test_login_programmatic_success_returns_json_200(monkeypatch):
    app = create_app()
    client = app.test_client()

    row = {
        "id": 7,
        "nome": "Ativo",
        "login": "ativo",
        "email": "ativo@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: _SingleUserDB(row))
    monkeypatch.setattr("src.app.models.get_db", lambda: _SingleUserDB(row))

    csrf = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "ativo", "senha": "secret"},
        headers={"X-CSRFToken": csrf, "Accept": "text/html", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "auth_ok"
    assert payload["next"].startswith("/")


def test_programmatic_protected_route_returns_503_when_auth_backend_is_unavailable(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _boom():
        raise RuntimeError("db_unavailable")

    monkeypatch.setattr("src.app.models.get_db", _boom)

    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
        sess["_fresh"] = True

    response = client.get(
        "/tripulantes",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["code"] == "auth_backend_unavailable"


def test_html_protected_route_redirects_to_login_when_auth_backend_is_unavailable(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _boom():
        raise RuntimeError("db_unavailable")

    monkeypatch.setattr("src.app.models.get_db", _boom)

    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
        sess["_fresh"] = True

    response = client.get("/tripulantes?page=2", follow_redirects=False)

    assert response.status_code in {302, 303}
    location = response.headers.get("Location", "") or ""
    assert "/login" in location
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert query.get("auth_issue") == ["backend_unavailable"]
    assert query.get("next") == ["/tripulantes?page=2"]
    with client.session_transaction() as sess:
        # Falha transitória de backend não deve destruir sessão do cliente.
        assert sess.get("_user_id") == "1"


def test_transient_auth_backend_failure_does_not_cause_permanent_logout(monkeypatch):
    app = create_app()

    @app.route("/_test/auth/probe")
    @login_required
    def _auth_probe():
        return {"ok": True}, 200

    client = app.test_client()
    row = {
        "id": 9,
        "nome": "Probe User",
        "login": "probe_user",
        "email": "probe@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    fake_db = _SingleUserDB(row)
    state = {"fail_once": True}

    def _transient_get_db():
        if state["fail_once"]:
            state["fail_once"] = False
            raise RuntimeError("temporary_db_unavailable")
        return fake_db

    monkeypatch.setattr("src.app.models.get_db", _transient_get_db)

    with client.session_transaction() as sess:
        sess["_user_id"] = "9"
        sess["_fresh"] = True

    first = client.get("/_test/auth/probe", follow_redirects=False)
    # Com o novo retry no middleware (enforce_endpoint_permissions), a falha
    # transitória inicial é absorvida dentro da mesma requisição.
    # Em vez de retornar 302 com auth_issue, retorna 200 diretamente.
    assert first.status_code == 200
    payload = first.get_json()
    assert payload["ok"] is True


def test_auth_snapshot_keeps_session_on_db_reload_failure(monkeypatch):
    app = create_app()

    @app.route("/_test/auth/snapshot-probe")
    @login_required
    def _auth_snapshot_probe():
        return {"ok": True}, 200

    client = app.test_client()

    def _boom():
        raise RuntimeError("temporary_db_unavailable")

    monkeypatch.setattr("src.app.models.get_db", _boom)

    with client.session_transaction() as sess:
        sess["_user_id"] = "42"
        sess["_fresh"] = True
        sess["auth_user_snapshot"] = {
            "id": "42",
            "nome": "Snapshot User",
            "login": "snapshot_user",
            "email": "snapshot@local.test",
            "perfil": "operador",
            "ativo": 1,
            "permissao_modulos_json": '["dashboard:view"]',
            "captured_at": int(time.time()),
        }
        sess["auth_user_snapshot_ts"] = int(time.time())

    response = client.get("/_test/auth/snapshot-probe", follow_redirects=False)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/jobs/999/status"),
        ("POST", "/jobs/1/reativar"),
        ("GET", "/bases/api/dados"),
        ("POST", "/bases/pilotos/adicionar"),
        ("POST", "/bases/pilotos/1/status"),
        ("POST", "/bases/pilotos/1/mover"),
        ("GET", "/bases/pilotos/1/historico"),
    ],
)
def test_cataloged_programmatic_routes_without_session_always_return_json_auth_required(method, path):
    app = create_app()
    client = app.test_client()

    response = client.open(path, method=method)

    assert response.status_code == 401
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 401
    assert payload["code"] == "auth_required"


def test_healthz_does_not_leak_database_exception_details(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _boom():
        raise RuntimeError("db password leaked marker")

    monkeypatch.setattr("src.app.db.get_db", _boom)

    response = client.get("/healthz")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["database"] == "unavailable"


def test_html_forbidden_returns_explicit_403_page(monkeypatch):
    app = create_app()
    client = app.test_client()

    row = {
        "id": 11,
        "nome": "Operador Restrito",
        "login": "operador_restrito",
        "email": "operador_restrito@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    with client.session_transaction() as sess:
        sess["_user_id"] = "11"
        sess["_fresh"] = True

    response = client.get("/usuarios", follow_redirects=False)

    assert response.status_code == 403
    assert (response.headers.get("Location", "") or "") == ""
    body = response.get_data(as_text=True)
    assert "Acesso negado" in body
    assert "Código de rastreio" in body
