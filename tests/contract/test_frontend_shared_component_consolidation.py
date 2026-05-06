from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_promotes_only_real_reused_page_components_without_domain_leak():
    primitives = _read(SHARED_UI_DIR / "primitives.css")
    readme = _read(SHARED_UI_DIR / "README.md")

    for expected in (
        ".ui-page-shell",
        ".ui-page-header",
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

    assert "ui-page-shell" in readme
    assert "ui-page-header" in readme
    assert "promocao para shared/ui exige reutilizacao material" in readme


def test_page_shell_and_header_are_adopted_across_real_surfaces():
    sources = {
        "dashboard": _read(FRONTEND_SRC / "features" / "dashboard" / "page.js"),
        "tripulantes": _read(FRONTEND_SRC / "features" / "tripulantes" / "list-page.js"),
        "treinamentos": _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js"),
        "training_root": _read(FRONTEND_SRC / "features" / "training-root" / "page.js"),
        "habilitacoes": _read(FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js"),
        "tripulante_form_detail": _read(FRONTEND_SRC / "features" / "tripulantes" / "form-page.js"),
    }

    for source in sources.values():
        assert "priority-page-surface ui-page-shell ui-stack" in source
        assert "priority-page-header ui-page-header ui-surface" in source

    assert len(sources) >= 2


def test_local_aliases_remain_controlled_without_new_global_domain_component():
    app_css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        ".priority-page-surface:not(.ui-page-shell)",
        ".priority-page-header:not(.ui-page-header)",
        ".dashboard-page-shell",
        ".training-reports-page-shell",
        ".tripulante-detail-page-shell",
    ):
        assert expected in app_css

    for forbidden in (
        ".ui-section-header",
        ".ui-action-toolbar",
        ".ui-summary-card",
    ):
        assert forbidden not in app_css
        assert forbidden not in _read(SHARED_UI_DIR / "primitives.css")


def test_g08_decision_is_documented_with_non_promoted_candidates():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")
    migration = _read(ROOT / "docs" / "migration" / "31.g08-consolidacao-minima-componentes-compartilhados-reais.md")
    migration_readme = _read(ROOT / "docs" / "migration" / "README.md")

    for expected in (
        "Consolidacao minima de componentes compartilhados reais apos G08",
        "`ui-page-shell`",
        "`ui-page-header`",
        "`nao_promovido_agora`",
        "`fechado`",
    ):
        assert expected in architecture
        assert expected in migration

    assert "31.g08-consolidacao-minima-componentes-compartilhados-reais.md" in migration_readme
