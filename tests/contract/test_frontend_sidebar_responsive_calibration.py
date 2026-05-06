from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sidebar_responsive_js_separates_rail_and_drawer_modes():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for expected in (
        'const SHELL_DRAWER_QUERY = "(max-width: 1024px)";',
        'const SHELL_TABLET_RAIL_QUERY = "(min-width: 1025px) and (max-width: 1279px)";',
        'const SHELL_NOTEBOOK_COLLAPSED_QUERY = "(min-width: 1025px) and (max-width: 1279px)";',
        'if (window.matchMedia(SHELL_NOTEBOOK_COLLAPSED_QUERY).matches) return "iconic";',
        "function defaultSidebarStateForViewport()",
        "function resolveSidebarStateForViewport(value)",
        'appShell.dataset.sidebarViewport = isDrawer ? "drawer" : "rail";',
        'sidebar.dataset.sidebarViewport = isDrawer ? "drawer" : "rail";',
        "function firstVisibleFocusable(root, selectors)",
        "function positionNavFlyout(navGroupEl)",
        "function syncOpenFlyoutPositions()",
        'links.style.setProperty("--nav-flyout-left"',
        'links.style.setProperty("--nav-flyout-top"',
        'links.style.setProperty("--nav-flyout-max-height"',
        'navScrollRegion?.addEventListener("scroll", syncOpenFlyoutPositions',
        'window.addEventListener("resize", syncOpenFlyoutPositions',
    ):
        assert expected in source


def test_sidebar_responsive_css_keeps_scroll_and_flyouts_mature():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "scrollbar-gutter: stable;",
        '.app-shell[data-sidebar-state="iconic"] .nav.ui-navigation-list',
        "overflow-y: auto;",
        '.app-shell[data-sidebar-state="iconic"] .nav-group-links',
        "position: fixed;",
        "left: var(--nav-flyout-left",
        "top: var(--nav-flyout-top",
        "max-height: var(--nav-flyout-max-height",
        "width: var(--nav-flyout-width",
    ):
        assert expected in css


def test_sidebar_responsive_breakpoints_cover_notebook_drawer_and_motion():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "@media (min-width: 1280px) and (max-width: 1360px)",
        "@media (min-width: 1024px) and (max-width: 1279px)",
        "@media (min-width: 768px) and (max-width: 1023px)",
        "--sidebar-current-width: 280px;",
        "--sidebar-current-width: var(--size-sidebar-iconic-width);",
        "@media (prefers-reduced-motion: reduce)",
        "@media (max-width: 1024px)",
        "body.sidebar-open",
        ".app-shell[data-sidebar-state] .sidebar-state-controls",
        "display: none;",
        ".app-shell[data-sidebar-state] .nav-group-links",
        "position: static;",
    ):
        assert expected in css


def test_sidebar_mobile_uses_temporary_drawer_not_fixed_navigation_column():
    css = _read(FRONTEND_SRC / "app.css")
    shell = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for expected in (
        'const SHELL_DRAWER_QUERY = "(max-width: 1024px)";',
        'id="mobileMenuBtn"',
        'aria-controls="appSidebar"',
        'aria-expanded="false"',
        'id="sidebarOverlay"',
        'sidebar.setAttribute("role", "dialog");',
        'sidebar.setAttribute("aria-modal", "true");',
        'sidebar.setAttribute("aria-hidden", isOpen ? "false" : "true");',
        "sidebar.inert = isDrawer && !isOpen;",
        "setMainColumnInert(isOpen && isDrawer);",
        "trapFocusWithin(sidebar, event);",
        'sidebar.addEventListener("click", (event) => {',
        "if (link && drawerQuery.matches) setMenuState(false);",
        'overlay.addEventListener("click", () => setMenuState(false)',
        'if (event.key === "Escape")',
    ):
        assert expected in shell

    for expected in (
        "@media (max-width: 1024px)",
        ".app-shell.ui-app-frame {\n    grid-template-columns: minmax(0, 1fr);",
        ".sidebar.ui-inverse-surface {\n    position: fixed;",
        "width: var(--size-sidebar-mobile-width);",
        "height: 100dvh;",
        "transform: translateX(-100%);",
        ".sidebar.ui-inverse-surface.open",
        "transform: translateX(0);",
        ".sidebar-overlay {\n    display: block;",
        "body.sidebar-open",
        ".mobile-menu-btn {\n    display: inline-flex;",
    ):
        assert expected in css


def test_sidebar_iconic_rail_keeps_minimal_width_tooltips_and_flyouts():
    css = _read(FRONTEND_SRC / "app.css")
    tokens = _read(FRONTEND_SRC / "shared" / "ui" / "tokens.css")
    navigation = _read(FRONTEND_SRC / "shell" / "navigation.js")
    shell = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for expected in (
        "--size-sidebar-iconic-width: 72px;",
        ".sidebar-rail-tooltip",
        '.app-shell[data-sidebar-state="iconic"] .nav-group.flyout-open > .nav-group-toggle',
    ):
        assert expected in tokens + css

    for expected in (
        'data-tooltip="${escapeAttr(group.label)}"',
        'data-tooltip="${escapeAttr(item.label)}"',
        'aria-haspopup="true"',
    ):
        assert expected in navigation

    for expected in (
        "function isIconRailMode()",
        "function showRailTooltip(trigger)",
        'tooltip.setAttribute("role", "tooltip");',
        'sidebar?.querySelectorAll("[data-tooltip]")',
        'trigger.addEventListener("focusin", () => showRailTooltip(trigger)',
    ):
        assert expected in shell
