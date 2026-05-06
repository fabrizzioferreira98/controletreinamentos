from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_TEMPLATES = ROOT / "backend" / "src" / "controle_treinamentos" / "templates"
FRONTEND_SRC = ROOT / "frontend" / "src"
OPERACOES_ROUTES = ROOT / "backend" / "src" / "controle_treinamentos" / "blueprints" / "operacoes" / "routes.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_missoes_removed_from_navigation_and_compat_links():
    base = _read(BACKEND_TEMPLATES / "base.html")
    navigation = _read(FRONTEND_SRC / "shell" / "navigation.js")
    backend_links = _read(FRONTEND_SRC / "compat" / "backend-links.js")
    dashboard_ssr = _read(BACKEND_TEMPLATES / "dashboard.html")
    dashboard_spa = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")

    for source in (base, navigation, backend_links, dashboard_ssr, dashboard_spa):
        assert 'href="/missoes' not in source
        assert "href='/missoes" not in source
        assert '"#/missoes"' not in source
        assert "'#/missoes'" not in source
        assert "missoes:" not in source
        assert "operacoes.missoes" not in source
    assert "Missões Operacionais" not in base
    assert "Miss&atilde;o" not in dashboard_spa


def test_pernoites_remain_standalone_without_missao_linking():
    routes = _read(OPERACOES_ROUTES)
    form = _read(BACKEND_TEMPLATES / "pernoites_form.html")
    listing = _read(BACKEND_TEMPLATES / "pernoites_list.html")

    assert "def pernoites_list" in routes
    assert "LEFT JOIN missoes_operacionais" not in routes
    assert "missao_id" not in routes
    assert 'name="missao_id"' not in form
    assert 'name="missao_id_display"' not in form
    assert "Missão" not in listing
