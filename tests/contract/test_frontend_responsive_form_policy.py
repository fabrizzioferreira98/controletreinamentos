from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"
MIGRATION_DIR = ROOT / "docs" / "migration"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_exposes_official_responsive_form_policy_without_domain_leak():
    tokens = _read(SHARED_UI_DIR / "tokens.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")
    readme = _read(SHARED_UI_DIR / "README.md")

    for expected in (
        "--size-form-field-min",
        "--size-form-field-compact-min",
        "--size-form-upload-min",
        "--size-form-long-field-min-height",
        "--space-form-field-gap",
        "--space-form-section-gap",
    ):
        assert expected in tokens

    for expected in (
        ".ui-form-section",
        ".ui-form-grid",
        ".ui-form-density-compact",
        ".ui-form-grid > :where(.full-width, .ui-form-field-long, [data-field-width=\"full\"])",
        ".ui-form-upload-grid",
        ".ui-form-upload-grid[data-upload-layout=\"single\"]",
        ".ui-form-upload-field",
        ".ui-form-upload-state",
        ".ui-form-sticky-actions",
        ".ui-form-actions > :where(a, button, .button-link)",
        ".ui-form-grid :where([aria-invalid=\"true\"])",
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

    assert "Formularios responsivos oficiais" in readme
    assert "ui-form-sticky-actions" in readme
    assert "ui-form-upload-grid" in readme


def test_form_enhancer_materializes_responsive_metadata_without_submit_drift():
    source = _read(FRONTEND_SRC / "lib.js")

    for expected in (
        "const FORM_CONTROL_SELECTOR = \"input:not([type='hidden']), select, textarea\";",
        "function inferResponsiveFieldKind(control)",
        "function inferResponsiveFormDensity(form)",
        "function enhanceResponsiveForms(scope)",
        'form.dataset.responsiveForm = form.dataset.responsiveForm || "true";',
        "form.dataset.formDensity = inferResponsiveFormDensity(form);",
        "control.dataset.responsiveField = inferResponsiveFieldKind(control);",
        'control.dataset.validationHint = "described";',
        "enhanceFormControlLabels(scope);",
        "enhanceResponsiveForms(scope);",
        "enhanceResponsiveTables(scope);",
    ):
        assert expected in source

    for preserved in (
        "export function enhanceOperationalSurfaces(root = document)",
        "withActionBusy(button, busyLabel, action)",
        "renderInlineFeedback(target, message, kind = \"error\")",
    ):
        assert preserved in source


def test_priority_forms_adopt_responsive_form_primitives_without_contract_drift():
    tripulante_form = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")
    training_form = _read(FRONTEND_SRC / "features" / "treinamentos" / "form-page.js")
    attachments = _read(FRONTEND_SRC / "features" / "treinamentos" / "attachments.js")
    training_root = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")

    for expected in (
        "ui-form-section",
        "ui-form-density-compact",
        "ui-form-field-long",
        "ui-form-sticky-actions",
        "ui-form-upload-grid",
        "ui-form-upload-field",
        "ui-form-upload-state",
        'id="tripulante-form"',
        'id="tripulante-file-form"',
        'id="tripulanteFormSubmit"',
        'id="tripulanteFileSubmit"',
        'api(`/api/v1/tripulantes/${tripulanteId}`',
        'api(`/api/v1/tripulantes/${tripulanteId}/files`',
    ):
        assert expected in tripulante_form

    for expected in (
        "ui-form-section",
        "ui-form-density-compact",
        "ui-form-field-long",
        "ui-form-sticky-actions",
        'id="training-program-record-form"',
        'id="training-program-record-submit"',
        'api(`/api/v1/treinamentos-tripulantes/${treinamentoId}`',
    ):
        assert expected in training_form

    for expected in (
        "ui-form-upload-grid",
        'data-upload-layout="single"',
        "ui-form-upload-field",
        "ui-form-upload-state",
        'id="treinamento-attachment-form"',
        'id="treinamentoAttachmentInput"',
    ):
        assert expected in attachments

    for expected in (
        'id="training-root-type-form"',
        'id="training-root-segment-form"',
        'id="training-root-hour-form"',
        "ui-form-density-compact",
        "ui-form-field-long",
        'id="training-root-type-submit"',
    ):
        assert expected in training_root


def test_form_policy_css_keeps_legacy_aliases_and_shared_rules_compatible():
    app_css = _read(FRONTEND_SRC / "app.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")

    for expected in (
        ".entity-form-grid input[aria-invalid=\"true\"]",
        ".document-upload-form",
        ".document-upload-input input[type=\"file\"]",
        ".entity-sticky-actions",
        ".tripulante-detail-page-shell .document-upload-form.ui-form-toolbar",
        ".training-record-detail-page-shell .document-upload-form.ui-form-toolbar",
    ):
        assert expected in app_css

    for expected in (
        "grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--size-form-field-min)), 1fr));",
        "grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--size-form-field-compact-min)), 1fr));",
        "grid-template-columns: minmax(var(--size-form-field-min), 0.85fr) minmax(var(--size-form-field-min), 0.85fr) minmax(var(--size-form-upload-min), 1.2fr) auto;",
        "position: sticky;",
        "bottom: 0;",
        "env(safe-area-inset-bottom)",
    ):
        assert expected in primitives


def test_form_policy_is_registered_in_migration_readme():
    migration = _read(MIGRATION_DIR / "34.2.5-politica-formularios-responsivos.md")
    index = _read(MIGRATION_DIR / "README.md")

    for expected in (
        "Politica oficial de formularios responsivos",
        "`ui-form-section`: grupo semantico de campos",
        "`ui-form-grid`: grid fluido oficial",
        "`ui-form-sticky-actions`: acoes persistentes",
        "`ui-form-upload-grid`: layout responsivo de upload",
        "`ui-form-field-long`: campos de texto longo",
        "`ui-field-help`: ajuda, erro, sucesso e aviso",
        "backend, contratos, rotas e regras de dominio permanecem intactos",
    ):
        assert expected in migration

    assert "34.2.5-politica-formularios-responsivos.md" in index
