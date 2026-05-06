from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"
MIGRATION_DIR = ROOT / "docs" / "migration"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_exposes_official_responsive_card_grid_policy_without_domain_leak():
    tokens = _read(SHARED_UI_DIR / "tokens.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")
    readme = _read(SHARED_UI_DIR / "README.md")

    for expected in (
        "--size-card-grid-min",
        "--size-card-grid-compact-min",
        "--size-card-grid-wide-min",
        "--size-card-min-height",
        "--size-card-compact-min-height",
        "--space-card-grid-gap",
        "--space-card-inner-gap",
    ):
        assert expected in tokens

    for expected in (
        ".ui-card-grid",
        ".ui-card-grid[data-density=\"compact\"]",
        ".ui-card-grid-compact",
        ".ui-card-grid[data-density=\"wide\"]",
        ".ui-card-grid-wide",
        ".ui-card-grid[data-equal-height=\"true\"] > *",
        ".ui-card-equal-height > *",
        ".ui-card",
        ".ui-card-compact",
        ".ui-card-inset",
        ".ui-card-metric",
        ".ui-card-actions",
        "grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--size-card-grid-min)), 1fr));",
        "overflow-wrap: anywhere;",
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

    assert "Cards e grids responsivos oficiais" in readme
    assert "ui-card-grid" in readme
    assert "ui-card-actions" in readme


def test_dashboard_adopts_card_grid_policy_without_loader_or_api_drift():
    source = _read(FRONTEND_SRC / "features" / "dashboard" / "page.js")

    for expected in (
        "dashboard-stat-grid ui-card-grid ui-card-equal-height",
        "dashboard-kpi-card dashboard-kpi-card--${card.tone} ui-surface ui-card",
        "dashboard-status-grid ui-card-grid ui-card-grid-compact ui-card-equal-height",
        "dashboard-status-item dashboard-status-item--${item.tone} ui-card ui-card-compact",
        "dashboard-base-grid ui-card-grid ui-card-grid-compact ui-card-equal-height",
        "summary-card summary-link-card dashboard-base-card ui-card ui-card-compact",
        "dashboard-agenda-item ui-surface ui-card ui-card-compact",
        "dashboard-calendar-detail-card ui-surface ui-card ui-card-compact",
    ):
        assert expected in source

    for preserved in (
        "export async function renderDashboardPage()",
        'renderShell(renderDashboardLoadingMarkup(capabilities), "Dashboard");',
        'api("/api/v1/dashboard/summary")',
        'api("/api/v1/dashboard/calendar")',
        'api("/api/v1/dashboard/critical-trainings")',
    ):
        assert preserved in source


def test_training_and_report_surfaces_adopt_card_grid_policy_without_contract_drift():
    training_root = _read(FRONTEND_SRC / "features" / "training-root" / "page.js")
    training_list = _read(FRONTEND_SRC / "features" / "treinamentos" / "list-page.js")
    report_ui = _read(FRONTEND_SRC / "features" / "relatorios" / "report-ui.js")
    habilitacoes = _read(FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js")

    for expected in (
        "type-card ui-surface ui-card",
        "type-card-actions ui-card-actions",
        "training-root-summary-grid ui-card-grid ui-card-grid-compact ui-card-equal-height",
        "summary-card training-root-summary-card ui-surface ui-card ui-card-compact",
        "type-card-grid ui-card-grid ui-card-equal-height",
        'api("/api/v1/treinamento-raiz/options")',
        'api("/api/v1/treinamento-raiz/tipos")',
    ):
        assert expected in training_root

    assert "training-program-operational-summary ui-card-grid ui-card-grid-compact ui-card-equal-height" in training_list
    assert "report-context-items ui-card-grid ui-card-grid-compact ui-card-equal-height" in report_ui
    assert "report-context-item ui-surface ui-card ui-card-compact" in report_ui
    assert "report-evidence-list ui-card-grid ui-card-equal-height" in report_ui
    assert "report-evidence-item ui-surface ui-card" in report_ui

    for source in (habilitacoes,):
        assert "summary-grid" in source
        assert "ui-card-grid ui-card-grid-compact ui-card-equal-height" in source
        assert "api(" in source or "export function" in source


def test_card_grid_policy_css_bridges_real_surfaces_and_nested_cards():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "34.2.7: card/grid responsive policy bridges shared/ui primitives to real surfaces.",
        ".summary-grid.ui-card-grid",
        ".compact-summary-grid.ui-card-grid",
        ".dashboard-stat-grid.ui-card-grid",
        ".dashboard-status-grid.ui-card-grid",
        ".dashboard-base-grid.ui-card-grid",
        ".type-card-grid.ui-card-grid",
        ".training-program-operational-summary.ui-card-grid",
        ".report-context-items.ui-card-grid",
        ".report-evidence-list.ui-card-grid",
        ".summary-card.ui-surface",
        ".type-card.ui-surface",
        ".dashboard-kpi-card.ui-surface",
        ".dashboard-status-item.ui-card",
        ".dashboard-base-card.summary-card",
        ".training-program-summary-card.ui-surface",
        ".ui-card .summary-card",
        ".ui-card .ui-card",
        ".ui-card-metric",
        ".ui-card-actions",
    ):
        assert expected in css


def test_card_grid_policy_is_registered_in_migration_readme():
    migration = _read(MIGRATION_DIR / "34.2.7-politica-cards-grids-responsivos.md")
    index = _read(MIGRATION_DIR / "README.md")

    for expected in (
        "Politica oficial de cards e grids responsivos",
        "`ui-card-grid`: grid fluido oficial",
        "`ui-card-grid-compact`: grids densos",
        "`ui-card-grid-wide`: cards de leitura larga",
        "`ui-card-equal-height`: equalizacao controlada",
        "`ui-card`: base semantica de card",
        "`ui-card-compact`: densidade reduzida",
        "`ui-card-inset`: card interno",
        "`ui-card-actions`: CTAs e acoes",
        "backend, contratos, rotas e regras de dominio permanecem intactos",
    ):
        assert expected in migration

    assert "34.2.7-politica-cards-grids-responsivos.md" in index
