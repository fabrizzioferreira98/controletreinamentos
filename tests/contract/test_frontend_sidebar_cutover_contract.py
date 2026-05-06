from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sidebar_cutover_marks_new_contract_as_official_shell_surface():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for expected in (
        'data-sidebar-contract="sidebar-v1"',
        'data-sidebar-state="${escapeAttr(sidebarState)}"',
        "const SIDEBAR_STATES = new Set",
        '["expanded", "iconic"]',
        '["compact", "iconic"]',
        "sidebarStorageKey()",
        "renderNavigation(activeRoute)",
        "resolveActiveNavigation(activeRoute)",
    ):
        assert expected in source


def test_sidebar_cutover_has_no_transitional_focus_or_layout_fallbacks():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")
    css = _read(FRONTEND_SRC / "app.css")

    assert 'sidebar.querySelector(".sidebar-close-btn, .nav-group-toggle, .nav a, .logout-button")' not in source
    assert "grid-template-columns: var(--size-sidebar-width) minmax(0, 1fr);" not in css
    assert "grid-template-columns: var(--sidebar-current-width) minmax(0, 1fr);" in css
    assert "firstVisibleFocusable(sidebar" in source


def test_sidebar_cutover_cleans_runtime_listeners_between_shell_renders():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for expected in (
        "let shellInteractionAbortController = null;",
        "shellInteractionAbortController?.abort();",
        "new AbortController()",
        "listenerOptions",
        "passiveListenerOptions",
        'window.addEventListener("resize", syncOpenFlyoutPositions, passiveListenerOptions);',
    ):
        assert expected in source

    assert "SIDEBAR_STATE_OPTIONS" not in source
    assert "data-sidebar-state-option" not in source
    assert "sidebarStateOption" not in source


def test_sidebar_uses_discreet_mode_toggle_with_safe_persistence():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "const SIDEBAR_STATE_ALIASES = new Map",
        "function nextSidebarState(value)",
        "function sidebarModeToggleLabel(value)",
        'id="sidebarModeToggle"',
        "data-sidebar-mode-toggle",
        "sidebar-mode-icon-collapse",
        "sidebar-mode-icon-expand",
        "modeToggle?.addEventListener(\"click\"",
        "if (drawerQuery.matches) return;",
        "setSidebarState(nextSidebarState(sidebar.dataset.sidebarState), { persist: true });",
        "window.localStorage.setItem(sidebarStorageKey(), normalizeSidebarState(value));",
        "window.matchMedia(SHELL_DRAWER_QUERY).matches",
        "return SIDEBAR_DEFAULT_STATE;",
    ):
        assert expected in source

    for expected in (
        ".sidebar-state-controls",
        "display: none !important;",
        ".sidebar-mode-toggle",
        ".sidebar-mode-toggle::before",
        ".sidebar-mode-toggle::after",
        '.sidebar-mode-toggle[data-sidebar-mode-state="iconic"]::before',
        ".sidebar-mode-icon-expand",
        '.sidebar-mode-toggle[data-sidebar-mode-state="iconic"] .sidebar-mode-icon-expand',
        ".app-shell[data-sidebar-state] .sidebar-mode-toggle",
    ):
        assert expected in css

    assert "data-sidebar-state-option" not in source
    assert 'title="${escapeAttr(sidebarModeLabel)}"' not in source
    assert 'if (normalizedState === "compact")' not in source
    assert 'return "compact";' not in source
    assert '.sidebar-mode-toggle[data-sidebar-mode-state="iconic"] .sidebar-mode-icon-expand {\n  opacity: 1;' in css
    assert '.sidebar-mode-toggle[data-sidebar-mode-state="iconic"] .sidebar-mode-icon-expand {\n  display: block;' not in css
    assert ".sidebar-mode-toggle-icon {\n  position: absolute;" in css
    assert "pointer-events: none;" in css


def test_sidebar_cutover_keeps_navigation_source_and_compat_classification():
    source = _read(FRONTEND_SRC / "shell" / "navigation.js")

    for expected in (
        "export const NAV_GROUPS",
        "capabilitySet()",
        "BACKEND_LINKS",
        "BACKEND_LINK_BOUNDARIES",
        "data-nav-boundary",
        "data-nav-active",
        "aria-current=\"page\"",
    ):
        assert expected in source
