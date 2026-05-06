from backend.src.controle_treinamentos import create_app


def _build_secure_app(monkeypatch, *, allow_insecure_http: bool = False):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key-long")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/postgres")
    if allow_insecure_http:
        monkeypatch.setenv("ALLOW_INSECURE_HTTP_IN_SECURE_ENV", "1")
    else:
        monkeypatch.delenv("ALLOW_INSECURE_HTTP_IN_SECURE_ENV", raising=False)
    return create_app()


def test_hsts_is_only_sent_on_https_requests(monkeypatch):
    app = _build_secure_app(monkeypatch)
    client = app.test_client()

    response_http = client.get("/login", base_url="http://example.com")
    response_https = client.get("/login", base_url="https://example.com")

    assert "Strict-Transport-Security" not in response_http.headers
    assert response_https.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_hsts_is_disabled_when_insecure_http_override_is_enabled(monkeypatch):
    app = _build_secure_app(monkeypatch, allow_insecure_http=True)
    client = app.test_client()

    response = client.get("/login", base_url="https://example.com")

    assert "Strict-Transport-Security" not in response.headers
