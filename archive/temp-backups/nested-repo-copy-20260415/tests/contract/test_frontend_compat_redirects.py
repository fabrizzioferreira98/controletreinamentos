from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app


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


def _user_row():
    return {
        "id": 61,
        "nome": "Operador Compat",
        "login": "compat_api",
        "email": "compat.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view","tripulantes:view","tripulantes:create","tripulantes:edit","treinamentos:view","treinamentos:create","treinamentos:edit","relatorio_habilitacoes:view","relatorio_produtividade:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, base_url: str = "http://localhost"):
    row = _user_row()
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    csrf_token = client.get("/api/v1/session", base_url=base_url).get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "compat_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        base_url=base_url,
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_dashboard_html_route_redirects_to_frontend_when_enabled(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "https://app.local.test/#/dashboard"


def test_root_route_redirects_to_frontend_app_when_official(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "https://app.local.test/"


def test_login_get_redirects_to_frontend_app_when_official(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()

    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "https://app.local.test/#/dashboard"


def test_logout_get_redirects_to_frontend_app_when_official(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "https://app.local.test/"


def test_tripulantes_html_route_redirects_with_query(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    response = client.get("/tripulantes?base=SSA&status=ativo", follow_redirects=False)

    assert response.status_code == 302
    target = response.headers["Location"]
    parsed = urlsplit(target)

    assert f"{parsed.scheme}://{parsed.netloc}/" == "https://app.local.test/"
    assert parsed.fragment.startswith("/tripulantes")
    fragment_path, _, fragment_query = parsed.fragment.partition("?")
    assert fragment_path == "/tripulantes"
    assert parse_qs(fragment_query) == {"base": ["SSA"], "status": ["ativo"]}


def test_treinamentos_html_route_redirects_to_frontend(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    response = client.get("/treinamentos/15/editar", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "https://app.local.test/#/treinamentos/15"


def test_relatorio_produtividade_html_route_redirects_to_frontend(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    response = client.get("/produtividade?competencia=2026-04", follow_redirects=False)

    assert response.status_code == 302
    target = response.headers["Location"]
    parsed = urlsplit(target)

    assert f"{parsed.scheme}://{parsed.netloc}/" == "https://app.local.test/"
    assert parsed.fragment.startswith("/relatorios/produtividade")
    fragment_path, _, fragment_query = parsed.fragment.partition("?")
    assert fragment_path == "/relatorios/produtividade"
    assert parse_qs(fragment_query) == {
        "competencia": ["2026-04"],
        "ordenacao": ["valor_final"],
    }


def test_relatorio_habilitacoes_html_route_redirects_to_frontend(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    response = client.get("/treinamentos/consolidado?status=vencido", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "https://app.local.test/#/relatorios/habilitacoes?status=vencido"


def test_backend_direct_loopback_prefers_frontend_local_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    monkeypatch.setenv("FRONTEND_LOCAL_ORIGIN", "http://127.0.0.1:8082")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, base_url="http://127.0.0.1:8102")

    response = client.get("/dashboard", base_url="http://127.0.0.1:8102", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "http://127.0.0.1:8082/#/dashboard"


def test_backend_direct_private_ip_prefers_frontend_local_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    monkeypatch.setenv("FRONTEND_LOCAL_ORIGIN", "http://192.168.25.33")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, base_url="http://192.168.25.33:8101")

    response = client.get("/tripulantes", base_url="http://192.168.25.33:8101", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "http://192.168.25.33/#/tripulantes"


def test_public_domain_request_keeps_same_host_even_when_public_origin_differs(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, base_url="http://controle.local.test")

    response = client.get(
        "/treinamentos/consolidado?ordenacao=valor_final",
        base_url="http://controle.local.test",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "http://controle.local.test/#/relatorios/habilitacoes?ordenacao=valor_final"


def test_private_ip_caddy_request_keeps_same_host(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, base_url="http://192.168.25.33")

    response = client.get(
        "/treinamentos/consolidado?status=vencido",
        base_url="http://192.168.25.33",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "http://192.168.25.33/#/relatorios/habilitacoes?status=vencido"
