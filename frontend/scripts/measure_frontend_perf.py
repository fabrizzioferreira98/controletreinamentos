from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend"
STARTUP_JS = (
    "app.js",
    "app/bootstrap.js",
    "app/router.js",
    "app/route-registry.js",
    "app/guards.js",
    "app/errors.js",
    "lib.js",
    "services/api-client.js",
    "services/csrf-service.js",
    "services/session-service.js",
    "services/trace-service.js",
    "state/app-state.js",
    "state/flash-state.js",
    "state/navigation-state.js",
    "shell.js",
    "shell/render-shell.js",
    "shell/navigation.js",
    "shell/login.js",
    "shell/redirects.js",
)
ROUTE_MODULES = {
    "tripulantes": "pages-dashboard-tripulantes.js",
    "treinamentos": "pages-treinamentos-relatorios.js",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _size(root: Path, filename: str) -> int:
    return (root / filename).stat().st_size


def _page_static_imports(startup_source: str) -> list[str]:
    return sorted(
        set(re.findall(r'from\s+["\'](?:\.\/|\.\.\/)(pages-[^"\']+\.js)(?:\?v=[^"\']*)?["\']', startup_source))
    )


def _page_dynamic_imports(startup_source: str) -> list[str]:
    return sorted(
        set(re.findall(r'import\(["\'](?:\.\/|\.\.\/)(pages-[^"\']+\.js)(?:\?v=[^"\']*)?["\']', startup_source))
    )


def measure(root: Path) -> dict[str, object]:
    source_root = FRONTEND_ROOT / "src"
    startup_source = "\n".join(_read(source_root / filename) for filename in STARTUP_JS)
    shell_source = _read(source_root / "shell" / "login.js")
    dashboard_source = _read(source_root / "features" / "dashboard" / "page.js")
    tripulantes_form_source = _read(source_root / "features" / "tripulantes" / "form-page.js")
    training_root_source = _read(source_root / "features" / "training-root" / "page.js")

    static_page_imports = _page_static_imports(startup_source)
    dynamic_page_imports = _page_dynamic_imports(startup_source)
    startup_files = list(STARTUP_JS) + static_page_imports

    return {
        "root": str(root),
        "startup": {
            "canonical_files": list(STARTUP_JS),
            "eager_files": startup_files,
            "eager_js_bytes": sum(_size(root, filename) for filename in startup_files),
            "lazy_route_js_bytes": {
                name: _size(root, filename)
                for name, filename in ROUTE_MODULES.items()
                if filename in dynamic_page_imports
            },
        },
        "route_imports": {
            "static_page_imports": static_page_imports,
            "dynamic_page_imports": dynamic_page_imports,
        },
        "session": {
            "shell_direct_session_fetch": "/api/v1/session`, {" in shell_source,
            "login_refresh_cacheable": "async function refreshLoginSession({ force = false } = {})" in shell_source
            and "if (!force && state.csrfToken)" in shell_source,
            "login_refresh_inflight_dedup": "loginSessionRefreshPromise" in shell_source
            and "if (!force && loginSessionRefreshPromise)" in shell_source,
            "csrf_retry_forces_refresh": "refreshLoginSession({ force: true })" in shell_source,
        },
        "waterfalls": {
            "dashboard_summary_parallel": "Promise.allSettled([" in dashboard_source
            and "/api/v1/dashboard/summary" in dashboard_source,
            "tripulante_detail_parallel": "const detailPromise" in tripulantes_form_source
            and "const filesPromise" in tripulantes_form_source
            and "const defaultOptionsPromise" in tripulantes_form_source
            and "detailPromise,\n      filesPromise,\n      defaultOptionsPromise" in tripulantes_form_source,
            "training_root_edit_parallel": "const editingTypePromise" in training_root_source
            and "editingTypePromise,\n      editingSegmentPromise,\n      editingHourPromise" in training_root_source,
        },
        "frontend_phase_measurement": {
            "window_export": "window.__FRONTEND_PERF__" in _read(source_root / "state" / "app-state.js"),
            "phases": [
                name
                for name in ("startup", "session", "route_resolve", "route_import", "route_render")
                if f'"{name}"' in startup_source
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=str(FRONTEND_ROOT / "dist"),
        help="Diretorio com os artefatos JS a medir. Padrao: frontend/dist.",
    )
    args = parser.parse_args()
    payload = measure(Path(args.root))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
