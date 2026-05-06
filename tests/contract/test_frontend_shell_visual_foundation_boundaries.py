from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shell_markup_adopts_shared_ui_primitives_without_changing_navigation_contract():
    render_shell = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for expected in (
        'class="app-shell ui-app-frame"',
        'class="sidebar ui-inverse-surface"',
        'class="brand-wrap ui-stack-xs"',
        'class="nav ui-navigation-list"',
        'class="sidebar-footer ui-stack-xs"',
        'class="topbar ui-sticky-surface"',
        'class="topbar-context ui-cluster"',
        'class="content ui-content-region"',
    ):
        assert expected in render_shell

    for preserved in (
        'id="mobileMenuBtn"',
        'id="appSidebar"',
        'id="logout-button"',
        "renderNavigation(activeRoute)",
        "BACKEND_LINKS.notificacoesEmail",
    ):
        assert preserved in render_shell


def test_shell_visual_tokens_are_semantic_and_used_by_structural_shell_css():
    tokens = _read(SHARED_UI_DIR / "tokens.css")
    app_css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "--color-layout-surface-translucent",
        "--color-layout-backdrop",
        "--color-inverse-surface",
        "--color-inverse-text",
        "--color-navigation-active-surface",
        "--space-layout-content",
        "--space-navigation-gap",
        "--shadow-navigation-panel",
        "--size-sidebar-width",
        "--size-content-wide",
    ):
        assert expected in tokens

    for expected in (
        ".app-shell.ui-app-frame",
        ".sidebar.ui-inverse-surface",
        ".nav.ui-navigation-list",
        ".topbar.ui-sticky-surface",
        ".content.ui-content-region",
        "var(--color-inverse-",
        "var(--space-layout-",
        "var(--space-navigation-",
        "var(--layer-overlay)",
        "var(--layer-modal)",
    ):
        assert expected in app_css


def test_shared_ui_structural_primitives_stay_domain_neutral():
    primitives = _read(SHARED_UI_DIR / "primitives.css")

    for expected in (
        ".ui-app-frame",
        ".ui-inverse-surface",
        ".ui-sticky-surface",
        ".ui-content-region",
        ".ui-navigation-list",
    ):
        assert expected in primitives

    for forbidden in (
        "dashboard",
        "tripulante",
        "treinamento",
        "relatorio",
        "api(",
        "renderShell",
        "innerHTML",
    ):
        assert forbidden not in primitives
