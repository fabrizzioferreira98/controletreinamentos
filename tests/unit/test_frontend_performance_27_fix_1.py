from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_measure_module():
    path = REPO_ROOT / "frontend" / "scripts" / "measure_frontend_perf.py"
    spec = importlib.util.spec_from_file_location("measure_frontend_perf", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_modules_are_lazy_and_startup_stays_canonical():
    app_source = _read(FRONTEND_SRC / "app.js")
    route_registry_source = _read(FRONTEND_SRC / "app" / "route-registry.js")
    measure_frontend_perf = _load_measure_module()

    metrics = measure_frontend_perf.measure(FRONTEND_SRC)

    assert 'from "./pages-dashboard-tripulantes.js' not in app_source
    assert 'from "./pages-treinamentos-relatorios.js' not in app_source
    assert 'import("../pages-dashboard-tripulantes.js")' in route_registry_source
    assert 'import("../pages-treinamentos-relatorios.js")' in route_registry_source
    assert metrics["startup"]["eager_files"] == [
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
    ]
    assert metrics["route_imports"]["static_page_imports"] == []
    assert set(metrics["route_imports"]["dynamic_page_imports"]) == {
        "pages-dashboard-tripulantes.js",
        "pages-financeiro.js",
        "pages-treinamentos-relatorios.js",
    }


def test_frontend_measures_startup_phases_in_the_client():
    app_source = _read(FRONTEND_SRC / "app.js")
    bootstrap_source = _read(FRONTEND_SRC / "app" / "bootstrap.js")
    router_source = _read(FRONTEND_SRC / "app" / "router.js")
    app_state_source = _read(FRONTEND_SRC / "state" / "app-state.js")
    measure_frontend_perf = _load_measure_module()

    metrics = measure_frontend_perf.measure(FRONTEND_SRC)

    assert "window.__FRONTEND_PERF__" in app_state_source
    assert "startApp" in app_source
    assert "resetFrontendPerf()" in bootstrap_source
    assert 'withFrontendPhase("session"' in bootstrap_source
    assert "withFrontendPhase(" in bootstrap_source
    assert '"route_resolve"' in bootstrap_source
    assert 'withFrontendPhase("route_render"' in bootstrap_source
    assert "route_import" in router_source
    assert metrics["frontend_phase_measurement"]["phases"] == [
        "startup",
        "session",
        "route_resolve",
        "route_import",
        "route_render",
    ]


def test_login_session_refresh_is_cached_and_forced_only_on_csrf_retry():
    shell_source = _read(FRONTEND_SRC / "shell" / "login.js")

    assert "refreshSession," in shell_source
    assert "let loginSessionRefreshPromise = null;" in shell_source
    assert "async function refreshLoginSession({ force = false } = {})" in shell_source
    assert "if (!force && state.csrfToken)" in shell_source
    assert "if (!force && loginSessionRefreshPromise)" in shell_source
    assert "refreshLoginSession({ force: true })" in shell_source
    assert "fetch(`${config.apiBaseUrl}/api/v1/session`" not in shell_source


def test_dashboard_and_detail_waterfalls_are_reduced_without_hiding_compat_fallback():
    dashboard_source = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")
    tripulantes_form_source = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")
    training_root_source = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")

    assert "Promise.allSettled([" in dashboard_source
    assert "const detailPromise" in tripulantes_form_source
    assert "const filesPromise" in tripulantes_form_source
    assert "const defaultOptionsPromise" in tripulantes_form_source
    assert "detailPromise,\n      filesPromise,\n      defaultOptionsPromise" in tripulantes_form_source
    assert "optionsContainBase(options, tripulante.base)" in tripulantes_form_source

    assert "const editingTypePromise" in training_root_source
    assert "const editingSegmentPromise" in training_root_source
    assert "const editingHourPromise" in training_root_source
    assert "editingTypePromise,\n      editingSegmentPromise,\n      editingHourPromise" in training_root_source


def test_frontend_performance_gain_and_startup_policy_are_documented():
    evidence = _read(REPO_ROOT / "docs" / "migration" / "27.fix.1-performance-residual-frontend.md")
    architecture = _read(REPO_ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    assert "288482" in evidence
    assert "52819" in evidence
    assert "-81.7%" in evidence
    assert "startup/session/route_resolve/route_import/route_render" in evidence
    assert "Startup canonico do frontend" in architecture
    assert "import()" in architecture
