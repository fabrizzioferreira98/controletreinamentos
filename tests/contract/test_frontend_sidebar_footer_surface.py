from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sidebar_footer_remains_local_session_surface():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for expected in (
        "data-session-footer",
        "data-session-surface",
        "session-presence",
        "session-profile-summary",
        "renderProfileIcon()",
        'id="logout-button"',
        'document.getElementById("logout-button")?.addEventListener("click", handleLogout);',
    ):
        assert expected in source


def test_sidebar_footer_does_not_create_profile_or_auth_flow():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for preserved in (
        'api("/api/v1/session/logout", { method: "POST", handleAuth: false })',
        "state.session = null;",
        'state.csrfToken = "";',
        'window.location.replace(`${window.location.origin}/#/login`);',
    ):
        assert preserved in source

    for forbidden in (
        "BACKEND_LINKS.perfil",
        "#/perfil",
        "/perfil",
        "/api/v1/perfil",
        "/api/v1/profile",
        "/api/v1/session/profile",
    ):
        assert forbidden not in source


def test_sidebar_footer_has_state_specific_ux_rules():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        ".session-actions",
        ".session-presence",
        ".session-profile-summary",
        '.app-shell[data-sidebar-state="compact"] .sidebar-footer.ui-stack-xs',
        '.app-shell[data-sidebar-state="compact"] .session-presence-label',
        '.app-shell[data-sidebar-state="iconic"] .session-profile-summary',
        '.app-shell[data-sidebar-state="iconic"] .session-actions',
        ".app-shell[data-sidebar-state] .session-profile-summary",
    ):
        assert expected in css
