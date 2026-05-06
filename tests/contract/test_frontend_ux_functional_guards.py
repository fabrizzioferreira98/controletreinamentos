from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


@pytest.fixture(scope="module")
def built_frontend_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_dir = tmp_path_factory.mktemp("frontend-dist")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "frontend" / "scripts" / "build_frontend.py"),
            "--env-file",
            str(ROOT / "frontend" / ".env.example"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert output_dir != ROOT / "frontend" / "dist"
    return output_dir


def _read_frontend_source(filename: str) -> str:
    return (FRONTEND_SRC / filename).read_text(encoding="utf-8")


def _resolve_built_frontend_asset(dist_dir: Path, filename: str) -> Path:
    direct_path = dist_dir / filename
    if direct_path.exists():
        return direct_path

    manifest = json.loads((dist_dir / "asset-manifest.json").read_text(encoding="utf-8"))
    fingerprinted_assets = manifest.get("fingerprinted_assets", {})
    mapped_path = fingerprinted_assets.get(filename.replace("\\", "/"))
    if not mapped_path:
        raise FileNotFoundError(f"asset nao encontrado no manifest: {filename}")
    resolved_path = dist_dir / mapped_path
    if not resolved_path.exists():
        raise FileNotFoundError(f"asset fingerprintado ausente no build: {resolved_path}")
    return resolved_path


def _read_built_frontend(dist_dir: Path, filename: str) -> str:
    return _resolve_built_frontend_asset(dist_dir, filename).read_text(encoding="utf-8")


def test_frontend_build_script_resolves_current_paths():
    source = (ROOT / "frontend" / "scripts" / "build_frontend.py").read_text(encoding="utf-8")

    assert '"backend" / "src" / "controle_treinamentos" / "static"' in source
    assert "repo_relative_env_path" in source


def test_frontend_api_feedback_and_error_guards_are_present(built_frontend_dist: Path):
    api_source = _read_frontend_source("services/api-client.js")
    flash_source = _read_frontend_source("state/flash-state.js")
    lib_source = _read_frontend_source("lib.js")
    dist_api_source = _read_built_frontend(built_frontend_dist, "services/api-client.js")
    dist_flash_source = _read_built_frontend(built_frontend_dist, "state/flash-state.js")
    dist_lib_source = _read_built_frontend(built_frontend_dist, "lib.js")

    for content in (flash_source, dist_flash_source):
        assert "FLASH_STORAGE_KEY" in content
    for content in (api_source, dist_api_source):
        assert "DEFAULT_API_TIMEOUT_MS" in content
        assert "AbortController" in content
        assert 'cache: options.cache || "no-store"' in content
        assert "handleApiErrorSideEffects" in content
        assert "status !== 401" in content
    for content in (lib_source, dist_lib_source):
        assert "auth_session_expired" in content
        assert "auth_session_invalid" in content
        assert "renderInlineFeedback" in content
        assert "withActionBusy" in content
        assert "confirmAction" in content


def test_spa_session_and_logout_contracts_do_not_depend_on_html_flows(built_frontend_dist: Path):
    bootstrap_source = _read_frontend_source("app/bootstrap.js")
    errors_source = _read_frontend_source("app/errors.js")
    render_shell_source = _read_frontend_source("shell/render-shell.js")
    dist_bootstrap_source = _read_built_frontend(built_frontend_dist, "app/bootstrap.js")
    dist_errors_source = _read_built_frontend(built_frontend_dist, "app/errors.js")
    dist_render_shell_source = _read_built_frontend(built_frontend_dist, "shell/render-shell.js")

    for source in (errors_source, dist_errors_source):
        assert "isSessionValidationUnavailable" in source
        assert "renderSessionValidationUnavailable" in source
        assert "auth_backend_unavailable" in source
        assert "service_unavailable" in source
        assert "network_error" in source
        validation_block = source.split("function isSessionValidationUnavailable", 1)[1].split(
            "function renderSessionValidationUnavailable", 1
        )[0]
        assert "auth_session_expired" not in validation_block
        assert "auth_session_invalid" not in validation_block
    for source in (bootstrap_source, dist_bootstrap_source):
        assert "state.session = null;" in source
        assert 'state.csrfToken = "";' in source
    for source in (render_shell_source, dist_render_shell_source):
        assert 'api("/api/v1/session/logout", { method: "POST", handleAuth: false })' in source
        assert "renderLogoutError" in source
        assert "window.location.replace(`${window.location.origin}/#/login`)" in source


def test_spa_route_render_failures_leave_navigable_error_state(built_frontend_dist: Path):
    bootstrap_source = _read_frontend_source("app/bootstrap.js")
    errors_source = _read_frontend_source("app/errors.js")
    dist_bootstrap_source = _read_built_frontend(built_frontend_dist, "app/bootstrap.js")
    dist_errors_source = _read_built_frontend(built_frontend_dist, "app/errors.js")

    for source in (errors_source, dist_errors_source):
        assert "function renderRouteFailure(error, retry)" in source
        assert "const message = buildErrorMessage(error);" in source
        assert 'showFlash(message, "error");' in source
        assert "Não foi possível carregar esta tela." in source
        assert 'id="route-retry-button"' in source
        assert 'document.getElementById("route-retry-button")?.addEventListener("click", () => void retry())' in source
    for source in (bootstrap_source, dist_bootstrap_source):
        assert 'withFrontendPhase("route_render", () => routeConfig.render()' in source
        assert "renderRouteFailure(error, startApp);" in source


def test_login_flow_has_inline_feedback_busy_state_and_destination_guard(built_frontend_dist: Path):
    login_source = _read_frontend_source("shell/login.js")
    dist_login_source = _read_built_frontend(built_frontend_dist, "shell/login.js")

    for source in (login_source, dist_login_source):
        assert 'class="login-feedback" role="status" aria-live="polite"' in source
        assert "submitLoginRequest(payload)" in source
        assert 'error?.code === "csrf_error"' in source
        assert 'renderInlineFlash(feedbackEl, message, "error")' in source
        assert 'document.getElementById("login-password")?.focus()' in source
        assert "submitButton.disabled = true" in source
        assert "submitButton.disabled = false" in source
        assert "resolveLoginDestination(data?.next || data?.capabilities?.landing_url)" in source
        assert "window.location.assign(destination.value)" in source
        assert "window.location.hash = destination.value" in source


def test_dashboard_uses_partial_error_adapters_instead_of_single_promise_all():
    source = _read_frontend_source("features/dashboard/page.js")

    assert "adaptDashboardSummary" in source
    assert "adaptDashboardCalendar" in source
    assert "adaptDashboardCriticalTrainings" in source
    assert "dashboardBlockFromResult" in source
    assert "Promise.allSettled" in source
    assert "renderDashboardPartialFeedback" in source
    assert "const [{ data: summary }, { data: calendar }, { data: critical }] = await Promise.all" not in source


def test_active_frontend_pages_do_not_use_destructive_reload_or_native_confirm():
    dashboard_source = "\n".join(
        _read_frontend_source(filename)
        for filename in (
            "features/dashboard/page.js",
            "features/tripulantes/list-page.js",
            "features/tripulantes/form-page.js",
            "features/relatorio-individual/page.js",
        )
    )
    training_source = "\n".join(
        _read_frontend_source(filename)
        for filename in (
            "features/treinamentos/list-page.js",
            "features/treinamentos/form-page.js",
            "features/training-root/page.js",
            "features/relatorios/habilitacoes-page.js",
        )
    )

    for source in (dashboard_source, training_source):
        assert "window.location.reload()" not in source
        assert "window.confirm(" not in source
        assert "confirmAction({" in source
        assert "withActionBusy(" in source


def test_training_program_has_narrow_adapters_and_hash_filter_source_of_truth():
    source = "\n".join(
        _read_frontend_source(filename)
        for filename in (
            "features/treinamentos/program-helpers.js",
            "features/training-root/page.js",
        )
    )

    assert "readTrainingProgramFilters" in source
    assert "navigateTrainingProgramFilters" in source
    assert "adaptTrainingProgramOptions" in source
    assert "adaptTrainingProgramRecords" in source
    assert "loadRequiredItem" in source
    assert "loadOptionalItem" not in source


def test_tripulantes_flow_has_contract_adapters_and_inline_recovery():
    source = "\n".join(
        _read_frontend_source(filename)
        for filename in (
            "features/tripulantes/data-adapters.js",
            "features/tripulantes/list-page.js",
            "features/tripulantes/form-page.js",
        )
    )

    assert "adaptTripulantesListPayload" in source
    assert "adaptTripulantesOptionsPayload" in source
    assert "tripulante-form-feedback" in source
    assert "tripulantes-action-feedback" in source
    assert "renderInlineFeedback(formFeedback, buildErrorMessage(error), \"error\")" in source


def test_critical_frontend_forms_keep_validation_busy_and_error_feedback():
    dashboard_source = _read_frontend_source("features/tripulantes/form-page.js")
    training_source = "\n".join(
        _read_frontend_source(filename)
        for filename in (
            "features/treinamentos/list-page.js",
            "features/treinamentos/form-page.js",
            "features/treinamentos/program-helpers.js",
            "features/training-root/page.js",
        )
    )

    assert "tripulante-form-feedback" in dashboard_source
    assert "tripulante-file-form" in dashboard_source
    assert "Revise os campos destacados antes de salvar." in dashboard_source
    assert 'withActionBusy(submitButton, "Salvando...", async () => {' in dashboard_source
    assert 'renderInlineFeedback(formFeedback, buildErrorMessage(error), "error")' in dashboard_source
    assert "Envie uma imagem JPG, PNG ou WEBP." in dashboard_source

    assert "training-program-feedback" in training_source
    assert "training-record-feedback" in training_source
    assert "trainingProgramSelectionFeedback" in training_source
    assert "Revise os campos destacados antes de salvar." in training_source
    assert 'withActionBusy(submitButton, "Salvando...", async () => {' in training_source
    assert 'setSelectionFeedback(buildErrorMessage(error), "error")' in training_source
    assert 'wireExplicitSubmit("training-root-type-form"' in training_source
    assert 'form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }))' in training_source
