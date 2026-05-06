from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_exposes_minimal_table_and_form_patterns_without_domain_leak():
    tokens = _read(SHARED_UI_DIR / "tokens.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")
    readme = _read(SHARED_UI_DIR / "README.md")

    assert "--size-action-min-height" in tokens

    for expected in (
        ".ui-table-wrap",
        ".ui-table-density-compact",
        ".ui-table-actions",
        ".ui-table-state",
        ".ui-form-toolbar",
        ".ui-form-grid",
        ".ui-form-actions",
        ".ui-field-help",
        "var(--space-stack",
        "var(--radius-surface)",
        "var(--color-state-default-surface)",
        "var(--size-action-min-height)",
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

    assert "ui-table-wrap" in readme
    assert "ui-form-toolbar" in readme
    assert "nao deve virar biblioteca ornamental" in readme


def test_table_patterns_are_adopted_in_priority_surfaces_without_route_or_api_drift():
    tripulantes = _read(FRONTEND_SRC / "features" / "tripulantes" / "list-page.js")
    training_program_helpers = _read(FRONTEND_SRC / "features" / "treinamentos" / "program-helpers.js")
    training_root = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")
    habilitacoes = _read(FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js")
    lib = _read(FRONTEND_SRC / "lib.js")

    for source in (tripulantes, training_program_helpers, training_root, habilitacoes):
        assert "ui-table-wrap ui-table-density-compact" in source

    for source in (tripulantes, training_program_helpers, training_root):
        assert "actions ui-table-actions" in source

    assert '<th>Ações</th>' not in habilitacoes
    assert 'data-label="Ações"' not in habilitacoes

    assert "EvidÃªncia" not in habilitacoes
    assert "evidÃªncia" not in habilitacoes
    assert "Evid\u00eancia" not in habilitacoes
    assert "evid\u00eancia" not in habilitacoes
    assert "Exporta\u00e7\u00f5es do recorte" in habilitacoes

    assert "empty operational-empty ui-table-state" in lib
    assert "empty ui-table-state" in training_program_helpers

    for preserved in (
        'api(`/api/v1/tripulantes?',
        'id="tripulantes-filters-form"',
        "tripulante-delete",
    ):
        assert preserved in tripulantes

    for preserved in (
        "renderTrainingProgramRecordsTable(records, capabilities)",
        'href="#/treinamentos/${item.id}"',
    ):
        assert preserved in training_program_helpers or preserved in _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js")

    assert "data-training-root-tab" in training_root
    assert "treinamentosConsolidadoExportPdf" in habilitacoes


def test_form_patterns_are_adopted_without_changing_submit_or_filter_contracts():
    tripulantes = _read(FRONTEND_SRC / "features" / "tripulantes" / "list-page.js")
    tripulante_form = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")
    training_program = _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js")
    training_form = _read(FRONTEND_SRC / "features" / "treinamentos" / "form-page.js")
    attachments = _read(FRONTEND_SRC / "features" / "treinamentos" / "attachments.js")
    training_root = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")
    habilitacoes = _read(FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js")

    for source in (tripulantes, training_program, training_root, habilitacoes, attachments):
        assert "ui-form-toolbar" in source

    for source in (tripulante_form, training_form, training_root, habilitacoes):
        assert "ui-form-grid" in source

    for source in (tripulantes, training_program, tripulante_form, training_form, training_root, habilitacoes):
        assert "ui-form-actions" in source

    for preserved in (
        'id="training-program-selection-form"',
        'id="trainingProgramContinueButton"',
        'id="trainingProgramResetButton"',
    ):
        assert preserved in training_program

    assert 'id="training-root-type-submit"' in training_root
    assert 'id="habilitacoes-filter-form"' in habilitacoes
    assert 'id="tripulante-form"' in tripulante_form
    assert 'id="training-program-record-form"' in training_form


def test_table_form_css_uses_shared_patterns_and_keeps_legacy_alias_controlled():
    app_css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        ".table-wrap:not(.ui-table-wrap)",
        "padding: var(--space-stack-sm) var(--space-stack-md);",
        "gap: var(--space-stack-sm);",
        "min-height: var(--size-action-min-height);",
    ):
        assert expected in app_css

    assert ".tripulantes-page-shell .tripulantes-table-wrap {\n  border:" not in app_css
    assert ".training-reports-page-shell .training-reports-table-wrap {\n  border:" not in app_css
