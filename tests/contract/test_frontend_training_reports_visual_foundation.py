from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_training_program_surface_adopts_shared_ui_without_functional_drift():
    source = _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js")
    helpers = _read(FRONTEND_SRC / "features" / "treinamentos" / "program-helpers.js")

    for expected in (
        "training-reports-page-shell training-program-page-shell priority-page-surface ui-page-shell ui-stack",
        "page-header priority-page-header ui-page-header ui-surface",
        "panel training-program-panel ui-surface ui-stack",
        'id="training-program-selection-form" class="filters filters-wide ui-form-toolbar ui-stack-sm"',
        "training-workbench-pane ui-surface",
        "summary-card ui-surface",
        "ui-form-actions",
    ):
        assert expected in source

    for expected in (
        "ui-table-wrap ui-table-density-compact",
        "actions ui-table-actions",
        "<th>Anexos</th>",
        'data-label="Anexos"',
        "training-program-group-row",
        "training-evidence-chip--missing",
        "Regularizar",
    ):
        assert expected in helpers

    for preserved in (
        'api("/api/v1/tripulantes/options")',
        'api("/api/v1/treinamentos-tripulantes/options")',
        "api(`/api/v1/treinamentos-tripulantes?",
        'api("/api/v1/treinamentos-tripulantes/batch"',
        'id="trainingProgramBase"',
        "base: event.currentTarget.value",
        'id="trainingProgramContinueButton"',
        'id="trainingProgramResetButton"',
        "renderTrainingProgramRecordsTable(records, capabilities)",
        "buildTrainingProgramOperationalSummary(records)",
        "training-program-operational-summary",
        "<strong>Vencidos</strong>",
        "<strong>A vencer</strong>",
        "<strong>Regulares</strong>",
        "<strong>Sem informação</strong>",
        "<strong>Sem anexo</strong>",
    ):
        assert preserved in source

    for contract_guard in (
        'api("/api/v1/tripulantes/options")',
        'api("/api/v1/treinamentos-tripulantes/options")',
        "api(`/api/v1/treinamentos-tripulantes?",
        'api("/api/v1/treinamentos-tripulantes/batch"',
        "/api/v1/pernoites",
    ):
        if contract_guard.startswith("/api/v1/"):
            assert contract_guard not in source
            assert contract_guard not in helpers
        else:
            assert contract_guard in source


def test_training_root_surface_adopts_shared_ui_without_tab_or_api_drift():
    source = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")

    for expected in (
        "training-reports-page-shell training-root-page-shell priority-page-surface ui-page-shell ui-stack",
        "page-header priority-page-header ui-page-header ui-surface",
        "panel training-root-filter-panel ui-surface ui-stack",
        "panel training-root-panel ui-surface ui-stack",
        "training-root-filter-bar ui-form-toolbar ui-stack-sm",
        "training-root-form-grid ui-form-grid ui-stack-sm",
        "type-card ui-surface",
        "summary-card training-root-summary-card ui-surface",
        "training-reports-table-wrap ui-table-wrap ui-table-density-compact",
    ):
        assert expected in source

    for preserved in (
        'api("/api/v1/treinamento-raiz/options")',
        'api("/api/v1/treinamento-raiz/tipos")',
        "data-training-root-tab",
        "wireExplicitSubmit",
        "training-root-type-delete",
        "training-root-hour-delete",
    ):
        assert preserved in source


def test_reports_surface_adopts_shared_ui_without_export_or_action_drift():
    habilitacoes = _read(FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js")
    report_ui = _read(FRONTEND_SRC / "features" / "relatorios" / "report-ui.js")

    for source in (habilitacoes,):
        for expected in (
            "training-reports-page-shell report-priority-page-shell priority-page-surface ui-page-shell ui-stack",
            "report-shell-header priority-page-header ui-page-header ui-surface",
            "panel report-shell training-report-panel ui-surface ui-stack",
            "state-note print-hide ui-block-end-sm ui-feedback",
            "filters-bar print-hide ui-form-toolbar ui-stack-sm",
            "filters filters-wide ui-form-grid",
            "summary-card ui-surface",
            "training-reports-table-wrap ui-table-wrap ui-table-density-compact",
        ):
            assert expected in source

    assert '<th>Ações</th>' not in habilitacoes
    assert 'data-label="Ações"' not in habilitacoes
    assert 'href="#/treinamentos/${item.treinamento_id}">Evidência</a>' not in habilitacoes
    assert "EvidÃªncia" not in habilitacoes
    assert "evidÃªncia" not in habilitacoes
    assert "Evid\u00eancia" not in habilitacoes
    assert "evid\u00eancia" not in habilitacoes
    assert "Exporta\u00e7\u00f5es do recorte" in habilitacoes
    assert 'colspan="4"' in habilitacoes
    assert "emptyTableRowMarkup(4" in habilitacoes

    for preserved in (
        "treinamentosConsolidadoExportCsv",
        "treinamentosConsolidadoExportPdf",
        "habilitacoes-filter-form",
        "consolidatedFiltersToggle",
    ):
        assert preserved in habilitacoes

    for expected in (
        "report-state-panel ui-surface",
        "feedback info ui-feedback",
        "report-context-strip ui-surface",
        "report-context-item ui-surface",
        "report-evidence-panel print-hide ui-surface",
        "report-evidence-item ui-surface",
    ):
        assert expected in report_ui


def test_training_reports_visual_css_is_scoped_and_token_based():
    app_css = _read(FRONTEND_SRC / "app.css")
    primitives = _read(FRONTEND_SRC / "shared" / "ui" / "primitives.css")

    for expected in (
        "G04: training/reports priority surface adopts shared/ui",
        ".training-reports-page-shell",
        ".training-reports-page-shell > .priority-page-header",
        ".training-reports-page-shell .training-program-panel.ui-surface",
        ".training-reports-page-shell .training-root-panel.ui-surface",
        ".training-reports-page-shell .training-report-panel.ui-surface",
        "var(--space-panel-gap)",
        "var(--radius-surface)",
        "var(--shadow-surface)",
        "var(--color-state-default-surface)",
        "var(--transition-state)",
    ):
        assert expected in app_css

    assert ".ui-table-wrap" in primitives
    assert ".ui-form-toolbar" in primitives
