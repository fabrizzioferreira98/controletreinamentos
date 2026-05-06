from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend" / "src" / "controle_treinamentos"
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_training_root_spa_surface_remains_canonical() -> None:
    route_registry = _read(FRONTEND_SRC / "app" / "route-registry.js")
    wrapper = _read(FRONTEND_SRC / "pages-treinamentos-relatorios.js")
    page = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")

    assert '"#/treinamentos/raiz": {' in route_registry
    assert 'exportName: "renderTrainingRootPage"' in route_registry
    assert "renderTrainingRootFeaturePage" in wrapper
    assert "training-root-page-shell" in page


def test_training_root_is_not_discovered_through_ssr_dashboard_legacy_card() -> None:
    dashboard = _read(BACKEND_SRC / "templates" / "dashboard.html")
    base = _read(BACKEND_SRC / "templates" / "base.html")

    assert 'href="/#/treinamentos/raiz" hx-boost="false"' in dashboard
    assert "<strong>Tipos ativos</strong>" in dashboard
    assert "url_for('cadastros.tipos_list')" not in dashboard
    assert 'href="/#/treinamentos/raiz"' in base
    assert 'href="{{ url_for(\'cadastros.tipos_list\') }}"' not in base


def test_training_root_legacy_ssr_route_is_compat_redirect_when_frontend_is_enabled() -> None:
    routes = _read(BACKEND_SRC / "blueprints" / "cadastros" / "routes_catalogos.py")

    assert "from ...core.frontend_routes import frontend_compat_enabled, redirect_to_frontend" in routes
    assert "def _redirect_to_training_root():" in routes
    assert 'return redirect_to_frontend("#/treinamentos/raiz")' in routes
    assert "def tipos_list():" in routes
    assert "if frontend_compat_enabled():" in routes
    assert "return _redirect_to_training_root()" in routes
    assert "def _redirect_after_tipo_mutation():" in routes


def test_training_root_backend_link_cannot_be_reused_as_runtime_href() -> None:
    backend_links = _read(FRONTEND_SRC / "compat" / "backend-links.js")

    assert 'tipos: "/tipos-treinamento"' in backend_links
    assert '[BACKEND_LINKS.tipos]: "backend_ssr_compat_redirect_only"' in backend_links
    assert 'trainingRoot: "#/treinamentos/raiz"' in backend_links
    assert '"/tipos": CANONICAL_FRONTEND_HASHES.trainingRoot' in backend_links

    for path in FRONTEND_SRC.rglob("*.js"):
        if path == FRONTEND_SRC / "compat" / "backend-links.js":
            continue
        assert "BACKEND_LINKS.tipos" not in _read(path), path
