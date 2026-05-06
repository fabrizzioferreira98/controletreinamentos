from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


SHELL_NAV_BOUNDARIES = {
    "#/dashboard": "spa_viva",
    "#/dashboard-operacional": "spa_viva",
    "/bases": "backend_ssr_compat",
    "#/relatorios/habilitacoes": "spa_viva",
    "#/relatorios/individual": "spa_viva",
    "#/tripulantes": "spa_viva",
    "#/treinamentos": "spa_viva",
    "#/financeiro/lancamentos-jornada": "spa_viva",
    "#/financeiro/fechamento-parametros": "spa_viva",
    "/equipamentos": "backend_ssr_compat",
    "#/treinamentos/raiz": "spa_viva",
    "/usuarios": "backend_ssr_compat",
    "/monitoramento": "backend_ssr_compat",
    "/manual/usuario.pdf": "externo_operacional",
    "/notificacoes-email": "backend_ssr_compat",
    "/backups": "backend_ssr_compat",
    "/auditoria": "backend_ssr_compat",
}

NON_SIDEBAR_COMPAT_BOUNDARIES = {
    "/pernoites": "ssr_ui_current_with_api_read_model",
    "/pernoites/novo": "ssr_write_canonical_current_direct",
    "/usuarios/novo": "backend_ssr_compat",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _shell_nav_hrefs() -> set[str]:
    navigation_source = _read(FRONTEND_SRC / "shell" / "navigation.js")
    render_shell_source = _read(FRONTEND_SRC / "shell" / "render-shell.js")
    backend_links_source = _read(FRONTEND_SRC / "compat" / "backend-links.js")
    backend_links = dict(re.findall(r"\s+([a-zA-Z0-9]+):\s*\"(/[^\"]+)\"", backend_links_source))
    nav_group_hrefs = set(re.findall(r'href:\s*"([^"]+)"', navigation_source))
    static_template_hrefs = {
        href
        for href in re.findall(r'href="([^"]+)"', render_shell_source)
        if href.startswith(("/", "#"))
    }
    compat_hrefs = {
        href
        for key, href in backend_links.items()
        if f"BACKEND_LINKS.{key}" in navigation_source or f"BACKEND_LINKS.{key}" in render_shell_source
    }
    return nav_group_hrefs | static_template_hrefs | compat_hrefs


def _registered_static_hash_routes() -> set[str]:
    route_registry_source = _read(FRONTEND_SRC / "app" / "route-registry.js")
    return set(re.findall(r'"(#[^"]+)":\s*{', route_registry_source))


def test_shell_navigation_entries_have_explicit_boundary_classification():
    assert _shell_nav_hrefs() == set(SHELL_NAV_BOUNDARIES)


def test_non_sidebar_compat_routes_stay_classified_without_visible_nav_entry():
    backend_links_source = _read(FRONTEND_SRC / "compat" / "backend-links.js")
    backend_links = dict(re.findall(r"\s+([a-zA-Z0-9]+):\s*\"(/[^\"]+)\"", backend_links_source))
    key_by_href = {href: key for key, href in backend_links.items()}

    for href, classification in NON_SIDEBAR_COMPAT_BOUNDARIES.items():
        assert f'"{href}"' in backend_links_source
        assert f'[BACKEND_LINKS.{key_by_href[href]}]: "{classification}"' in backend_links_source
        assert href not in _shell_nav_hrefs()


def test_shell_spa_entries_are_registered_static_hash_routes():
    spa_hrefs = {href for href, classification in SHELL_NAV_BOUNDARIES.items() if classification == "spa_viva"}

    assert spa_hrefs <= _registered_static_hash_routes()


def test_shell_navigation_boundaries_are_documented_in_frontend_architecture():
    architecture_doc = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    assert "`ambigua_pendente`" in architecture_doc
    for href, classification in (SHELL_NAV_BOUNDARIES | NON_SIDEBAR_COMPAT_BOUNDARIES).items():
        assert f"| `{href}` | `{classification}` |" in architecture_doc
