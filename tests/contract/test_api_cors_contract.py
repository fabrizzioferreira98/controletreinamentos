from __future__ import annotations

from backend.src.controle_treinamentos import create_app


def test_api_cors_allows_configured_frontend_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_ALLOWED_ORIGINS", "https://app.local.test")
    app = create_app()
    client = app.test_client()

    response = client.get(
        "/api/v1/session",
        headers={"Origin": "https://app.local.test"},
    )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "https://app.local.test"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"
    assert "X-Request-ID" in response.headers.get("Access-Control-Expose-Headers", "")
    assert "X-Correlation-ID" in response.headers.get("Access-Control-Expose-Headers", "")


def test_api_cors_preflight_returns_204_for_allowed_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_ALLOWED_ORIGINS", "https://app.local.test")
    app = create_app()
    client = app.test_client()

    response = client.options(
        "/api/v1/session/login",
        headers={
            "Origin": "https://app.local.test",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 204
    assert response.headers.get("Access-Control-Allow-Origin") == "https://app.local.test"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"
    assert "X-Correlation-ID" in response.headers.get("Access-Control-Allow-Headers", "")


def test_programmatic_bases_api_cors_allows_configured_frontend_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_ALLOWED_ORIGINS", "https://app.local.test")
    app = create_app()
    client = app.test_client()

    response = client.get(
        "/bases/api/dados",
        headers={"Origin": "https://app.local.test"},
    )

    assert response.status_code == 401
    assert response.content_type.startswith("application/json")
    assert response.headers.get("Access-Control-Allow-Origin") == "https://app.local.test"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"


def test_programmatic_bases_mutation_preflight_returns_204_for_allowed_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_ALLOWED_ORIGINS", "https://app.local.test")
    app = create_app()
    client = app.test_client()

    response = client.options(
        "/bases/pilotos/adicionar",
        headers={
            "Origin": "https://app.local.test",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 204
    assert response.headers.get("Access-Control-Allow-Origin") == "https://app.local.test"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"


def test_api_cors_does_not_reflect_unknown_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_ALLOWED_ORIGINS", "https://app.local.test")
    app = create_app()
    client = app.test_client()

    response = client.get(
        "/api/v1/session",
        headers={"Origin": "https://unknown.local.test"},
    )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") is None
