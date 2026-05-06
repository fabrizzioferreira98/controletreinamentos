from __future__ import annotations

from pathlib import Path

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend" / "src" / "controle_treinamentos"
FRONTEND_SRC = ROOT / "frontend" / "src"


class _SingleCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _SingleUserDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params=None):
        return _SingleCursor(self._row)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _training_root_user_row():
    return {
        "id": 93,
        "nome": "Release Training Root",
        "login": "release_training_root",
        "email": "release.training.root@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": (
            '["dashboard:view","treinamentos:view","tipos_treinamento:view",'
            '"tipos_treinamento:create","tipos_treinamento:edit"]'
        ),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch):
    fake_db = _SingleUserDB(_training_root_user_row())
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "release_training_root", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_release_gate_first_entry_resolves_to_new_training_root_surface() -> None:
    navigation = _read(FRONTEND_SRC / "shell" / "navigation.js")
    route_registry = _read(FRONTEND_SRC / "app" / "route-registry.js")
    wrapper = _read(FRONTEND_SRC / "pages-treinamentos-relatorios.js")
    page = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")

    assert '{ label: "Cadastro raiz treinamentos", href: "#/treinamentos/raiz"' in navigation
    assert '"#/treinamentos/raiz": {' in route_registry
    assert 'exportName: "renderTrainingRootPage"' in route_registry
    assert "renderTrainingRootFeaturePage" in wrapper
    assert "training-root-page-shell" in page
    assert "tipos_list.html" not in route_registry
    assert "tipos_list.html" not in wrapper


def test_release_gate_exit_to_dashboard_and_reentry_keep_training_root_canonical() -> None:
    route_registry = _read(FRONTEND_SRC / "app" / "route-registry.js")
    dashboard_spa = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")
    dashboard_operacional = _read(FRONTEND_SRC / "features" / "dashboard-operacional" / "page.js")
    dashboard_ssr = _read(BACKEND_SRC / "templates" / "dashboard.html")

    assert '"#/dashboard": {' in route_registry
    assert 'href: "#/treinamentos/raiz"' in dashboard_spa
    assert 'href: "#/treinamentos/raiz"' in dashboard_operacional
    assert 'href="/#/treinamentos/raiz" hx-boost="false"' in dashboard_ssr
    assert "url_for('cadastros.tipos_list')" not in dashboard_ssr
    assert "/tipos-treinamento" not in dashboard_ssr


def test_release_gate_compat_redirects_do_not_render_legacy_training_root(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://app.local.test")
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    for path in ("/tipos-treinamento", "/tipos-treinamento/novo", "/tipos-treinamento/4/editar"):
        response = client.get(path, follow_redirects=False)
        body = response.get_data(as_text=True)

        assert response.status_code == 302
        assert response.headers["Location"] == "https://app.local.test/#/treinamentos/raiz"
        assert "Tipos de Treinamento" not in body
        assert "tipos_list.html" not in body


def test_release_gate_legacy_paths_cannot_be_restored_or_reused_as_normal_navigation() -> None:
    backend_links = _read(FRONTEND_SRC / "compat" / "backend-links.js")
    navigation_state = _read(FRONTEND_SRC / "state" / "navigation-state.js")
    bootstrap = _read(FRONTEND_SRC / "app" / "bootstrap.js")

    assert 'trainingRoot: "#/treinamentos/raiz"' in backend_links
    assert 'tipos: "/tipos-treinamento"' in backend_links
    assert '[BACKEND_LINKS.tipos]: "backend_ssr_compat_redirect_only"' in backend_links
    assert '"/tipos": CANONICAL_FRONTEND_HASHES.trainingRoot' in backend_links
    assert "[BACKEND_LINKS.tipos]: CANONICAL_FRONTEND_HASHES.trainingRoot" in backend_links
    assert 'import { resolveFrontendHashForBackendPath } from "../compat/backend-links.js";' in navigation_state
    assert "const canonicalHash = resolveFrontendHashForBackendPath(pathname);" in navigation_state
    assert "return route.startsWith(\"#/\") ? route : \"\";" in navigation_state
    assert "routePath() || routeFromCurrentPathname()" in bootstrap
    assert "peekLastSuccessfulRoute()" in bootstrap

    for path in FRONTEND_SRC.rglob("*.js"):
        if path == FRONTEND_SRC / "compat" / "backend-links.js":
            continue
        assert "BACKEND_LINKS.tipos" not in _read(path), path
