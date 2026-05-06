from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"
MIGRATION_DIR = ROOT / "docs" / "migration"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_exposes_official_responsive_state_policy_without_domain_leak():
    tokens = _read(SHARED_UI_DIR / "tokens.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")
    readme = _read(SHARED_UI_DIR / "README.md")

    for expected in (
        "--size-state-panel-min-height",
        "--size-state-compact-min-height",
        "--size-state-content-max",
        "--space-state-gap",
        "--space-state-padding",
        "--space-state-actions-gap",
        "--space-alert-gap",
        "--space-alert-padding-block",
        "--space-alert-padding-inline",
    ):
        assert expected in tokens

    for expected in (
        ".ui-state",
        ".ui-state[data-state=\"loading\"]",
        ".ui-state[data-state=\"empty\"]",
        ".ui-state[data-state=\"error\"]",
        ".ui-state[data-state=\"no-permission\"]",
        ".ui-state[data-state=\"no-results\"]",
        ".ui-state-inline",
        ".ui-state-actions",
        ".ui-alert",
        ".ui-alert[data-kind=\"loading\"]",
        ".ui-alert[data-kind=\"error\"]",
        ".ui-alert[data-kind=\"warning\"]",
        "@media (max-width: 900px)",
        "@media (max-width: 640px)",
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

    assert "Estados responsivos oficiais" in readme
    assert "ui-state" in readme
    assert "ui-alert" in readme
    assert "responsiveStateMarkup" in readme


def test_state_helpers_materialize_markup_aria_and_table_empty_without_contract_drift():
    source = _read(FRONTEND_SRC / "lib.js")

    for expected in (
        "const UI_STATE_VALUES = new Set",
        "function normalizeUiStateType",
        "function responsiveStateAccessibility",
        "export function responsiveStateContentMarkup",
        "export function responsiveStateMarkup",
        "export function responsiveAlertMarkup",
        'data-state="${escapeAttr(normalizedType)}"',
        'role="${role}" aria-live="${live}"',
        "ui-state-actions",
        "ui-alert",
        "empty operational-empty ui-table-state ui-state",
        "data-empty-type",
        "data-state",
        "responsiveStateContentMarkup({",
    ):
        assert expected in source

    for preserved in (
        "export function emptyTableRowMarkup",
        "export function feedbackMarkup",
        "export function renderInlineFeedback",
        "export function enhanceOperationalSurfaces(root = document)",
    ):
        assert preserved in source


def test_route_permission_session_and_shell_flash_states_use_official_policy():
    bootstrap = _read(FRONTEND_SRC / "app" / "bootstrap.js")
    errors = _read(FRONTEND_SRC / "app" / "errors.js")
    guards = _read(FRONTEND_SRC / "app" / "guards.js")
    shell = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for expected in (
        "responsiveStateMarkup",
        'type: "empty"',
        'className: "empty route-state"',
        "renderRouteFailure(error, startApp);",
    ):
        assert expected in bootstrap

    for expected in (
        "responsiveStateMarkup",
        "renderSessionValidationUnavailable",
        "renderRouteFailure",
        'type: "error"',
        'actionId: "session-retry-button"',
        'actionId: "route-retry-button"',
    ):
        assert expected in errors

    for expected in (
        "renderForbiddenRoute",
        "responsiveStateMarkup",
        'type: "no-permission"',
        'className: "empty route-state"',
    ):
        assert expected in guards

    for expected in (
        "flash ${kind} ui-alert",
        "flash ${normalizedKind} ui-alert",
        'data-kind="${kind}"',
        'data-kind="${normalizedKind}"',
    ):
        assert expected in shell


def test_dashboard_and_reports_adopt_responsive_state_policy_without_api_drift():
    dashboard = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")
    report_ui = _read(FRONTEND_SRC / "features" / "relatorios" / "report-ui.js")

    for expected in (
        "responsiveAlertMarkup",
        "responsiveStateMarkup",
        'responsiveAlertMarkup(message, "warning", "dashboard-widget-feedback")',
        'className: "empty dashboard-widget-empty"',
        "flash loading dashboard-widget-feedback ui-alert",
        "dashboard-mid-surface-loading ui-alert",
        'className: "empty route-state"',
        'api("/api/v1/dashboard/summary")',
        'api("/api/v1/dashboard/calendar")',
        'api("/api/v1/dashboard/critical-trainings")',
    ):
        assert expected in dashboard

    for expected in (
        "responsiveStateMarkup",
        "renderReportLoadingState",
        "renderReportErrorState",
        'type: "loading"',
        'type: "error"',
        "report-state-panel ui-surface",
        "renderReportContextStrip",
        "renderReportEvidencePanel",
    ):
        assert expected in report_ui


def test_state_policy_css_and_migration_are_registered():
    css = _read(FRONTEND_SRC / "app.css")
    migration = _read(MIGRATION_DIR / "34.2.11-politica-estados-responsivos.md")
    index = _read(MIGRATION_DIR / "README.md")

    for expected in (
        "34.2.11: responsive state policy bridges legacy empty/flash aliases to shared primitives.",
        ".empty.ui-state",
        ".operational-empty.ui-state",
        ".route-state.ui-state",
        ".flash.ui-alert",
        ".dashboard-widget-feedback.ui-alert",
        "@media (max-width: 640px)",
    ):
        assert expected in css

    for expected in (
        "Politica de estados responsivos",
        "`loading`: usa `ui-state` ou `ui-alert`",
        "`empty`: comunica ausencia estrutural",
        "`no-results`: comunica resultado vazio",
        "`error`: comunica falha",
        "`no-permission`: comunica bloqueio por permissao",
        "`ui-alert`",
        "`responsiveStateMarkup`",
        "`responsiveAlertMarkup`",
        "backend, contratos, rotas e regras de dominio permanecem intactos",
    ):
        assert expected in migration

    assert "34.2.11-politica-estados-responsivos.md" in index
