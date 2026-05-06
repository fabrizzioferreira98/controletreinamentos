from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_second_wave_surfaces_converge_on_shared_visual_foundation():
    render_shell = _read(FRONTEND_SRC / "shell" / "render-shell.js")
    dashboard = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")
    tripulantes = _read(FRONTEND_SRC / "features" / "tripulantes" / "list-page.js")
    treinamentos = _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js")
    training_root = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")
    habilitacoes = _read(FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js")
    report_ui = _read(FRONTEND_SRC / "features" / "relatorios" / "report-ui.js")

    for expected in (
        'class="app-shell ui-app-frame"',
        'class="nav ui-navigation-list"',
        'class="content ui-content-region"',
    ):
        assert expected in render_shell

    for source in (dashboard, tripulantes, treinamentos, training_root, habilitacoes):
        assert "priority-page-surface ui-page-shell ui-stack" in source
        assert "priority-page-header ui-page-header ui-surface" in source

    for source in (dashboard, tripulantes, treinamentos, training_root, habilitacoes, report_ui):
        assert "ui-surface" in source

    for source in (habilitacoes, report_ui):
        assert "ui-feedback" in source


def test_second_wave_visual_css_is_scoped_token_based_and_not_promoted_to_shared_ui():
    app_css = _read(FRONTEND_SRC / "app.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")

    for expected in (
        "G02: shell layout adopts shared/ui foundation",
        "G03: priority dashboard/tripulantes surface adopts shared/ui",
        "G04: training/reports priority surface adopts shared/ui",
        ".app-shell.ui-app-frame",
        ".dashboard-page-shell",
        ".tripulantes-page-shell",
        ".training-reports-page-shell",
        ".training-program-panel.ui-surface",
        ".training-root-panel.ui-surface",
        ".training-report-panel.ui-surface",
        "var(--space-panel-gap)",
        "var(--radius-surface)",
        "var(--shadow-surface)",
        "var(--color-state-default-surface)",
        "var(--transition-state)",
    ):
        assert expected in app_css

    for forbidden in (
        "dashboard",
        "tripulante",
        "treinamento",
        "relatorio",
        "training-reports",
        "priority-page",
    ):
        assert forbidden not in primitives


def test_second_wave_readiness_is_documented_with_residual_visual_debt():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")
    frontend_readme = _read(ROOT / "frontend" / "README.md")
    migration_readme = _read(ROOT / "docs" / "migration" / "README.md")

    for expected in (
        "Readiness visual apos G05",
        "`pronta_para_proxima_fase_visual`",
        "`consolidado`",
        "`adocao_visual_controlada`",
        "`divida_visual_controlada`",
        "`baseline_fora_do_escopo`",
        "`0` item material",
    ):
        assert expected in architecture

    assert "Visual readiness second wave" in frontend_readme
    assert "31.g05-consolidacao-visual-readiness-segunda-onda.md" in migration_readme
