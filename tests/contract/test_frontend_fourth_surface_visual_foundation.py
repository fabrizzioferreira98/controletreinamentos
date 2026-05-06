from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fourth_surface_choice_is_live_routed_and_documented():
    route_registry = _read(FRONTEND_SRC / "app" / "route-registry.js")
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")
    migration = _read(ROOT / "docs" / "migration" / "31.g10-quarta-superficie-prioritaria.md")

    assert 'pattern: /^#\\/treinamentos\\/\\d+$/' in route_registry
    assert "renderTreinamentoFormPage" in route_registry
    assert 'permissions: ["treinamentos:edit"]' in route_registry

    for expected in (
        "Aplicacao da fundacao visual na quarta superficie",
        "`training_record_detail`",
        "`#/treinamentos/<id>`",
        "`fechado`",
    ):
        assert expected in architecture
        assert expected in migration


def test_training_record_detail_adopts_foundation_shared_patterns_and_g08_components():
    form_page = _read(FRONTEND_SRC / "features" / "treinamentos" / "form-page.js")
    attachments = _read(FRONTEND_SRC / "features" / "treinamentos" / "attachments.js")

    for expected in (
        "training-record-detail-page-shell priority-page-surface ui-page-shell ui-stack",
        "page-header entity-detail-header priority-page-header ui-page-header ui-surface",
        "entity-status-row ui-cluster",
        "training-record-form-panel ui-surface ui-stack",
        "training-record-form ui-form-grid",
        "entity-form-section ui-surface ui-stack",
        "section-feedback ui-field-help",
        "field-feedback ui-field-help",
        "field-help ui-field-help",
        "entity-sticky-actions ui-form-actions",
    ):
        assert expected in form_page

    for expected in (
        "training-record-attachment-panel ui-surface ui-stack",
        "document-upload-form ui-form-toolbar",
        "field-help ui-field-help",
        "ui-table-wrap ui-table-density-compact",
        "actions ui-table-actions",
        "empty ui-table-state",
    ):
        assert expected in attachments


def test_training_record_detail_preserves_functional_contracts():
    form_page = _read(FRONTEND_SRC / "features" / "treinamentos" / "form-page.js")
    attachments = _read(FRONTEND_SRC / "features" / "treinamentos" / "attachments.js")

    for preserved in (
        'id="training-program-record-form"',
        'id="training-program-record-submit"',
        'id="training-program-record-delete"',
        "api(`/api/v1/treinamentos-tripulantes/${treinamentoId}`",
        'api("/api/v1/treinamentos-tripulantes/options")',
        "withActionBusy(",
        "validateTrainingRecordForm()",
        "syncRecordHints()",
        "renderTrainingAttachmentSection(treinamentoId, record.attachments || [], capabilities)",
    ):
        assert preserved in form_page

    for preserved in (
        'id="treinamento-attachment-form"',
        'id="treinamentoAttachmentInput"',
        "treinamento-attachment-delete",
        'href="${item.links.self}"',
        'href="${item.links.download}"',
    ):
        assert preserved in attachments


def test_training_record_detail_css_is_scoped_and_token_based():
    app_css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "G10: training record detail adopts shared visual foundation",
        ".training-record-detail-page-shell",
        ".training-record-detail-page-shell > .priority-page-header",
        ".training-record-detail-page-shell .training-record-form.ui-form-grid",
        ".training-record-detail-page-shell .entity-form-section.ui-surface",
        ".training-record-detail-page-shell .training-record-attachment-panel.ui-surface",
        ".training-record-detail-page-shell .section-feedback.ui-field-help",
        "var(--space-panel-gap)",
        "var(--space-stack-sm)",
        "var(--space-layout-content-mobile)",
        "var(--radius-surface)",
        "var(--shadow-surface)",
        "var(--color-state-default-surface)",
    ):
        assert expected in app_css
