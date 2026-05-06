from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_third_wave_shared_ui_stays_neutral_and_reused():
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
        ".ui-form-toolbar",
        ".ui-feedback",
        ".ui-surface",
        "var(--space-panel-gap)",
        "var(--space-layout-content-mobile)",
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


def test_third_wave_surfaces_converge_without_single_surface_coupling():
    render_shell = _read(FRONTEND_SRC / "shell" / "render-shell.js")
    surfaces = {
        "dashboard": _read(FRONTEND_SRC / "features" / "dashboard" / "page.js"),
        "tripulantes": _read(FRONTEND_SRC / "features" / "tripulantes" / "list-page.js"),
        "treinamentos": _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js"),
        "training_root": _read(FRONTEND_SRC / "features" / "training-root" / "page.js"),
        "habilitacoes": _read(FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js"),
        "tripulante_form_detail": _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js"),
    }

    for expected in (
        'class="app-shell ui-app-frame"',
        'class="nav ui-navigation-list"',
        'class="content ui-content-region"',
    ):
        assert expected in render_shell

    for source in surfaces.values():
        assert "priority-page-surface ui-page-shell ui-stack" in source
        assert "priority-page-header ui-page-header ui-surface" in source
        assert "ui-surface" in source

    for source in (
        surfaces["tripulantes"],
        surfaces["treinamentos"],
        surfaces["training_root"],
        surfaces["habilitacoes"],
        surfaces["tripulante_form_detail"],
    ):
        assert "ui-form-" in source

    for source in (
        surfaces["tripulantes"],
        surfaces["training_root"],
        surfaces["habilitacoes"],
        surfaces["tripulante_form_detail"],
    ):
        assert "ui-table-" in source


def test_third_wave_residual_visual_debt_remains_controlled_not_promoted():
    app_css = _read(FRONTEND_SRC / "app.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")

    for expected in (
        ".priority-page-surface:not(.ui-page-shell)",
        ".priority-page-header:not(.ui-page-header)",
        ".table-wrap:not(.ui-table-wrap)",
        ".dashboard-page-shell",
        ".training-reports-page-shell",
        ".tripulante-detail-page-shell",
    ):
        assert expected in app_css

    for not_promoted in (
        ".ui-section-header",
        ".ui-action-toolbar",
        ".ui-summary-card",
        ".ui-preview-card",
    ):
        assert not_promoted not in primitives


def test_third_wave_readiness_is_documented_without_false_green():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")
    frontend_readme = _read(ROOT / "frontend" / "README.md")
    migration = _read(ROOT / "docs" / "migration" / "31.g09-consolidacao-terceira-onda-readiness-expansao.md")
    migration_readme = _read(ROOT / "docs" / "migration" / "README.md")

    for expected in (
        "Readiness visual da terceira onda apos G09",
        "`pronta_para_expansao_visual`",
        "`componente_compartilhado_real`",
        "`adocao_visual_controlada`",
        "`divida_visual_controlada`",
        "`baseline_fora_do_escopo`",
        "`0` item material",
    ):
        assert expected in architecture
        assert expected in migration

    assert "Visual readiness third wave" in frontend_readme
    assert "31.g09-consolidacao-terceira-onda-readiness-expansao.md" in migration_readme
