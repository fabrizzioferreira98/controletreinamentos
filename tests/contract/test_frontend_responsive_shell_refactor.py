from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shell_drawer_uses_mobile_breakpoint_in_js():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    assert 'const SHELL_DRAWER_QUERY = "(max-width: 1024px)";' in source
    assert "window.matchMedia(SHELL_DRAWER_QUERY)" in source
    assert 'window.matchMedia("(max-width: 900px)")' not in source

    for expected in (
        'id="mobileMenuBtn"',
        'id="sidebarCloseBtn"',
        'aria-controls="appSidebar"',
        "closeBtn?.addEventListener",
        'sidebar.setAttribute("role", "dialog")',
        'sidebar.setAttribute("aria-modal", "true")',
        'sidebar.removeAttribute("role")',
        "if (drawerQuery.matches) {\n      setMenuState(false);",
        "mainColumn.inert = isInert",
        "firstVisibleFocusable(sidebar",
        'data-sidebar-contract="sidebar-v1"',
    ):
        assert expected in source

    for preserved in (
        "renderNavigation(activeRoute)",
        "resolveActiveNavigation(activeRoute)",
        "BACKEND_LINKS.notificacoesEmail",
        'api("/api/v1/session/logout", { method: "POST", handleAuth: false })',
    ):
        assert preserved in source


def test_shell_css_moves_sidebar_to_drawer_at_mobile_breakpoint():
    css = _read(FRONTEND_SRC / "app.css")
    tokens = _read(SHARED_UI_DIR / "tokens.css")

    assert "--size-touch-target: 44px;" in tokens

    for expected in (
        ".app-shell.ui-app-frame",
        "display: grid;",
        "grid-template-columns: var(--sidebar-current-width) minmax(0, 1fr);",
        ".main-column",
        "overflow-x: clip;",
        ".sidebar-overlay.show",
        ".sidebar-close-btn",
        ".mobile-menu-btn",
        "@media (max-width: 1024px)",
        "body.sidebar-open",
        "body.sidebar-open .main-column",
        ".app-shell.ui-app-frame {\n    grid-template-columns: minmax(0, 1fr);",
        ".sidebar.ui-inverse-surface {\n    position: fixed;",
        "transform: translateX(-100%);",
        ".sidebar.ui-inverse-surface.open",
        "transform: translateX(0);",
        '.app-shell[data-sidebar-viewport="drawer"] .sidebar.ui-inverse-surface[aria-hidden="true"]:not(.open)',
        ".sidebar-close-btn {\n    display: inline-flex;",
        ".mobile-menu-btn {\n    display: inline-flex;",
    ):
        assert expected in css


def test_shell_content_mobile_rules_remain_scoped_without_page_redesign():
    css = _read(FRONTEND_SRC / "app.css")
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for expected in (
        "@media (max-width: 900px)",
        ".topbar.ui-sticky-surface",
        ".content.ui-content-region",
        "@media (max-width: 640px)",
        ".route-context-chip,\n  .topbar-context .topbar-action",
    ):
        assert expected in css

    for forbidden in (
        "NAV_GROUPS",
        "permission:",
        "permissions:",
    ):
        assert forbidden not in source
