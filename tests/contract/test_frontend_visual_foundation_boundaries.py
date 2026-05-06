from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_foundation_exists_with_minimal_owners():
    assert {path.name for path in SHARED_UI_DIR.iterdir() if path.is_file()} == {
        "README.md",
        "primitives.css",
        "tokens.css",
    }

    readme = _read(SHARED_UI_DIR / "README.md")
    assert "tokens.css" in readme
    assert "primitives.css" in readme
    assert "nao e um design system completo" in readme
    assert "nao deve virar biblioteca ornamental" in readme


def test_shared_ui_tokens_cover_required_semantic_categories():
    tokens = _read(SHARED_UI_DIR / "tokens.css")

    for expected in (
        "--color-text",
        "--color-text-muted",
        "--color-danger",
        "--color-state-default-surface",
        "--color-state-hover-surface",
        "--color-state-focus-ring",
        "--color-state-disabled-text",
        "--color-state-error-surface",
        "--color-state-success-surface",
        "--color-state-warning-surface",
        "--font-ui-title",
        "--font-ui-body",
        "--space-stack-xs",
        "--space-section-gap",
        "--radius-control",
        "--radius-surface",
        "--shadow-surface",
        "--shadow-overlay",
        "--layer-sticky",
        "--layer-modal",
        "--transition-state",
    ):
        assert expected in tokens


def test_shared_ui_primitives_are_domain_neutral_and_token_based():
    primitives = _read(SHARED_UI_DIR / "primitives.css")

    for expected in (
        ".ui-stack",
        ".ui-cluster",
        ".ui-panel-offset",
        ".ui-heading-reset",
        ".ui-surface",
        ".ui-feedback",
        ".ui-badge",
        ".ui-page-shell",
        ".ui-page-header",
        ".ui-table-wrap",
        ".ui-table-density-compact",
        ".ui-table-actions",
        ".ui-table-state",
        ".ui-form-toolbar",
        ".ui-form-grid",
        ".ui-form-actions",
        ".ui-field-help",
    ):
        assert expected in primitives

    for expected_token in (
        "var(--space-stack",
        "var(--color-state",
        "var(--radius-",
        "var(--shadow-",
        "var(--size-action-min-height)",
    ):
        assert expected_token in primitives

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


def test_visual_foundation_is_documented_and_adopted_without_redesign():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")
    attachments = _read(FRONTEND_SRC / "features" / "treinamentos" / "attachments.js")
    tripulantes_form = _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js")

    for expected in (
        "`frontend/src/shared/ui/tokens.css`",
        "`frontend/src/shared/ui/primitives.css`",
        "`adocao_gradual`",
        "`nao_redesign`",
        "`divida_visual_controlada`",
    ):
        assert expected in architecture

    assert "ui-panel-offset" in attachments
    assert "ui-heading-reset" in attachments
    assert "ui-panel-offset" in tripulantes_form
    assert "ui-heading-reset" in tripulantes_form
