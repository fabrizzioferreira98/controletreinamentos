from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_final_expansion_shared_ui_remains_small_neutral_and_reused():
    assert {path.name for path in SHARED_UI_DIR.iterdir() if path.is_file()} == {
        "README.md",
        "primitives.css",
        "tokens.css",
    }

    primitives = _read(SHARED_UI_DIR / "primitives.css")

    for expected in (
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
        "var(--space-panel-gap)",
        "var(--color-state-default-surface)",
    ):
        assert expected in primitives

    for forbidden in (
        "dashboard",
        "tripulante",
        "treinamento",
        "relatorio",
        "priority-page",
        "api(",
        "renderShell",
        "innerHTML",
    ):
        assert forbidden not in primitives


def test_final_expansion_surfaces_converge_on_shared_visual_language():
    render_shell = _read(FRONTEND_SRC / "shell" / "render-shell.js")
    surfaces = {
        "dashboard": _read(FRONTEND_SRC / "features" / "dashboard" / "page.js"),
        "tripulantes": _read(FRONTEND_SRC / "features" / "tripulantes" / "list-page.js"),
        "treinamentos": _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js"),
        "training_root": _read(FRONTEND_SRC / "features" / "training-root" / "page.js"),
        "habilitacoes": _read(FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js"),
        "tripulante_form_detail": _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js"),
        "training_record_detail": _read(FRONTEND_SRC / "features" / "treinamentos" / "form-page.js"),
        "training_record_attachments": _read(FRONTEND_SRC / "features" / "treinamentos" / "attachments.js"),
    }

    for expected in (
        'class="app-shell ui-app-frame"',
        'class="nav ui-navigation-list"',
        'class="content ui-content-region"',
    ):
        assert expected in render_shell

    for name, source in surfaces.items():
        if name == "training_record_attachments":
            continue
        assert "ui-surface" in source

    for name in (
        "dashboard",
        "tripulantes",
        "treinamentos",
        "training_root",
        "habilitacoes",
        "tripulante_form_detail",
        "training_record_detail",
    ):
        assert "priority-page-surface ui-page-shell ui-stack" in surfaces[name]
        assert "priority-page-header ui-page-header ui-surface" in surfaces[name]

    for name in (
        "tripulantes",
        "treinamentos",
        "training_root",
        "habilitacoes",
        "tripulante_form_detail",
        "training_record_detail",
        "training_record_attachments",
    ):
        assert "ui-form-" in surfaces[name]

    for name in (
        "tripulantes",
        "training_root",
        "habilitacoes",
        "tripulante_form_detail",
        "training_record_attachments",
    ):
        assert "ui-table-" in surfaces[name]


def test_final_expansion_residual_debt_is_controlled_not_promoted():
    app_css = _read(FRONTEND_SRC / "app.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")

    for expected in (
        ".priority-page-surface:not(.ui-page-shell)",
        ".priority-page-header:not(.ui-page-header)",
        ".table-wrap:not(.ui-table-wrap)",
        ".dashboard-page-shell",
        ".training-reports-page-shell",
        ".tripulante-detail-page-shell",
        ".training-record-detail-page-shell",
    ):
        assert expected in app_css

    for not_promoted in (
        ".ui-section-header",
        ".ui-action-toolbar",
        ".ui-summary-card",
        ".ui-preview-card",
        ".ui-training-record",
    ):
        assert not_promoted not in primitives

    # The former legacy generic training form is no longer part of the routed SPA surface.
    training_form = _read(FRONTEND_SRC / "features" / "treinamentos" / "form-page.js")
    assert "legacyRenderTreinamentoFormPage" not in training_form


def test_final_expansion_readiness_is_documented_without_false_green():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")
    frontend_readme = _read(ROOT / "frontend" / "README.md")
    migration = _read(ROOT / "docs" / "migration" / "31.g11-consolidacao-visual-final-expansao.md")
    migration_readme = _read(ROOT / "docs" / "migration" / "README.md")

    for expected in (
        "Consolidacao visual final da expansao apos G11",
        "`pronta_para_encerramento_da_fase`",
        "`componente_compartilhado_real`",
        "`adocao_visual_controlada`",
        "`divida_visual_controlada`",
        "`baseline_fora_do_escopo`",
        "`bloqueio_para_encerramento`",
        "`0` item material",
    ):
        assert expected in architecture
        assert expected in migration

    assert "Visual final expansion readiness" in frontend_readme
    assert "31.g11-consolidacao-visual-final-expansao.md" in migration_readme
