from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SERVICES_DIR = FRONTEND_SRC / "services"
STATE_DIR = FRONTEND_SRC / "state"

EXPECTED_SERVICE_MODULES = {
    "api-client.js",
    "financeiro-missoes-api.js",
    "session-service.js",
    "csrf-service.js",
    "trace-service.js",
}

EXPECTED_STATE_MODULES = {
    "app-state.js",
    "draft-state.js",
    "flash-state.js",
    "navigation-state.js",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_frontend_services_and_state_modules_exist_with_explicit_owners():
    assert {path.name for path in SERVICES_DIR.glob("*.js")} == EXPECTED_SERVICE_MODULES
    assert {path.name for path in STATE_DIR.glob("*.js")} == EXPECTED_STATE_MODULES

    assert "export async function api" in _read(SERVICES_DIR / "api-client.js")
    assert "export async function listFinanceiroMissoes" in _read(SERVICES_DIR / "financeiro-missoes-api.js")
    assert "export async function refreshSession" in _read(SERVICES_DIR / "session-service.js")
    assert "export function applyCsrfHeader" in _read(SERVICES_DIR / "csrf-service.js")
    assert "export function clientCorrelationId" in _read(SERVICES_DIR / "trace-service.js")
    assert "export const state" in _read(STATE_DIR / "app-state.js")
    assert "export function writeDraft" in _read(STATE_DIR / "draft-state.js")
    assert "export function showFlash" in _read(STATE_DIR / "flash-state.js")
    assert "export function rememberReturnRoute" in _read(STATE_DIR / "navigation-state.js")


def test_lib_is_a_compat_facade_not_the_owner_of_services_or_state():
    lib_source = _read(FRONTEND_SRC / "lib.js")

    assert len(lib_source) < 42000
    assert 'export { api } from "./services/api-client.js' in lib_source
    assert 'export { refreshSession } from "./services/session-service.js' in lib_source
    assert 'export {' in lib_source and './state/app-state.js' in lib_source
    assert './state/flash-state.js' in lib_source
    assert './state/navigation-state.js' in lib_source
    for forbidden in (
        "export async function api(",
        "export async function refreshSession(",
        "const DEFAULT_API_TIMEOUT_MS",
        "const FLASH_STORAGE_KEY",
        "const CORRELATION_STORAGE_KEY",
        "window.__FRONTEND_PERF__",
    ):
        assert forbidden not in lib_source


def test_services_do_not_render_or_import_shell_pages_or_features():
    forbidden_fragments = (
        "renderShell",
        "renderLoginPage",
        "innerHTML",
        "querySelector",
        "pages-",
        "/features/",
        "shell.js",
        "../shell",
        "../pages",
    )
    for path in list(SERVICES_DIR.glob("*.js")) + list(STATE_DIR.glob("*.js")):
        if path.name == "trace-service.js":
            continue
        source = _read(path)
        for fragment in forbidden_fragments:
            assert fragment not in source, f"{path.name} must not own UI/page concerns"


def test_service_state_boundaries_are_documented():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    for expected in (
        "`frontend/src/services/api-client.js`",
        "`frontend/src/services/financeiro-missoes-api.js`",
        "`frontend/src/services/session-service.js`",
        "`frontend/src/services/csrf-service.js`",
        "`frontend/src/services/trace-service.js`",
        "`frontend/src/state/app-state.js`",
        "`frontend/src/state/draft-state.js`",
        "`frontend/src/state/flash-state.js`",
        "`frontend/src/state/navigation-state.js`",
        "facade temporaria",
    ):
        assert expected in architecture
