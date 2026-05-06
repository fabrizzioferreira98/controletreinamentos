from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHELL_DIR = FRONTEND_SRC / "shell"


EXPECTED_SHELL_MODULES = {
    "render-shell.js",
    "navigation.js",
    "login.js",
    "redirects.js",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shell_facade_is_thin_and_delegates_to_owned_modules():
    shell_source = _read(FRONTEND_SRC / "shell.js")
    meaningful_lines = [line for line in shell_source.splitlines() if line.strip()]

    assert len(meaningful_lines) <= 2
    assert 'export { renderLoginPage } from "./shell/login.js";' in shell_source
    assert 'export { renderShell } from "./shell/render-shell.js";' in shell_source
    for forbidden in (
        "NAV_GROUPS",
        "FRONTEND_HASH_BY_BACKEND_PATH",
        "function renderShell",
        "function renderLoginPage",
        "function handleLogout",
        "innerHTML",
    ):
        assert forbidden not in shell_source


def test_shell_modules_exist_with_explicit_responsibilities():
    assert {path.name for path in SHELL_DIR.glob("*.js")} == EXPECTED_SHELL_MODULES

    render_shell_source = _read(SHELL_DIR / "render-shell.js")
    navigation_source = _read(SHELL_DIR / "navigation.js")
    login_source = _read(SHELL_DIR / "login.js")
    redirects_source = _read(SHELL_DIR / "redirects.js")

    assert "export function renderShell" in render_shell_source
    assert "export function renderFlashMarkup" in render_shell_source
    assert "export function renderInlineFlash" in render_shell_source
    assert "function wireShellInteractions" in render_shell_source
    assert "function handleLogout" in render_shell_source

    assert "export const NAV_GROUPS" in navigation_source
    assert "export function resolveActiveNavigation" in navigation_source
    assert "export function renderNavigation" in navigation_source

    assert "export function renderLoginPage" in login_source
    assert "async function submitLoginRequest" in login_source
    assert "async function refreshLoginSession" in login_source
    assert "resolveLoginDestination" in login_source

    assert 'from "../compat/backend-links.js";' in redirects_source
    assert "FRONTEND_HASH_BY_BACKEND_PATH" in redirects_source
    assert "resolveLoginDestination" in redirects_source


def test_shell_responsibilities_do_not_slide_back_across_boundaries():
    render_shell_source = _read(SHELL_DIR / "render-shell.js")
    navigation_source = _read(SHELL_DIR / "navigation.js")
    login_source = _read(SHELL_DIR / "login.js")
    redirects_source = _read(SHELL_DIR / "redirects.js")

    assert "NAV_GROUPS" not in render_shell_source
    assert "renderLoginPage" not in render_shell_source
    assert "submitLoginRequest" not in render_shell_source

    assert "renderLoginPage" not in navigation_source
    assert "api(\"/api/v1/session/login\"" not in navigation_source
    assert "api(\"/api/v1/session/logout\"" not in navigation_source

    assert "NAV_GROUPS" not in login_source
    assert "renderShell" not in login_source
    assert "api(\"/api/v1/session/logout\"" not in login_source

    assert "innerHTML" not in redirects_source
    assert "api(" not in redirects_source
    assert "NAV_GROUPS" not in redirects_source


def test_shell_architecture_is_documented():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    for expected in (
        "`frontend/src/shell.js`",
        "`frontend/src/shell/render-shell.js`",
        "`frontend/src/shell/navigation.js`",
        "`frontend/src/shell/login.js`",
        "`frontend/src/shell/redirects.js`",
        "facade temporaria",
        "shell nao define pertencimento a SPA",
    ):
        assert expected in architecture
