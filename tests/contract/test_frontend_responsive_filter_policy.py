from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"
MIGRATION_DIR = ROOT / "docs" / "migration"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_exposes_official_responsive_filter_policy_without_domain_leak():
    tokens = _read(SHARED_UI_DIR / "tokens.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")
    readme = _read(SHARED_UI_DIR / "README.md")

    for expected in (
        "--size-filter-field-min",
        "--size-filter-primary-min",
        "--size-filter-drawer-max-height",
        "--space-filter-gap",
    ):
        assert expected in tokens

    for expected in (
        ".ui-filter-bar",
        ".ui-filter-row",
        ".ui-filter-actions",
        ".ui-filter-summary",
        ".ui-filter-chip",
        ".ui-filter-panel",
        ".ui-filter-advanced",
        ".ui-filter-drawer",
        ".ui-filter-panel.ui-filter-drawer:not([hidden]):not(.collapsed)",
        "overscroll-behavior: contain;",
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

    assert "Filtros responsivos oficiais" in readme
    assert "ui-filter-drawer" in readme
    assert "persistencia visual local" in readme


def test_filter_helpers_materialize_summary_metadata_and_local_persistence():
    source = _read(FRONTEND_SRC / "lib.js")

    for expected in (
        "ui-filter-summary",
        "ui-filter-chip",
        'data-filter-persistence="visual"',
        "function inferResponsiveFilterDensity(form)",
        "function enhanceResponsiveFilters(scope)",
        "form.dataset.responsiveFilter = form.dataset.responsiveFilter || \"bar\";",
        "form.dataset.filterDensity = inferResponsiveFilterDensity(form);",
        "actions.dataset.filterActions = \"true\";",
        "panel.dataset.filterPanel = panel.dataset.filterPanel || \"advanced\";",
        "toggle.dataset.filterToggle = toggle.dataset.filterToggle || \"advanced\";",
        "function filterPanelStorageKey(panelId)",
        "window.sessionStorage?.getItem",
        "window.sessionStorage?.setItem",
        "export function wireResponsiveFilterPanel",
        "enhanceResponsiveFilters(scope);",
    ):
        assert expected in source

    for preserved in (
        "export function filterSummaryMarkup(filters = {}, labels = {}, defaults = {})",
        "export function enhanceOperationalSurfaces(root = document)",
        "enhanceResponsiveForms(scope);",
        "enhanceResponsiveTables(scope);",
    ):
        assert preserved in source


def test_priority_filter_surfaces_adopt_filter_primitives_without_query_or_action_drift():
    tripulantes = _read(FRONTEND_SRC / "features" / "tripulantes" / "list-page.js")
    habilitacoes = _read(FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js")
    report_ui = _read(FRONTEND_SRC / "features" / "relatorios" / "report-ui.js")

    for source in (tripulantes, habilitacoes):
        for expected in (
            'data-responsive-filter="bar"',
            "ui-filter-row",
            "ui-filter-actions",
        ):
            assert expected in source

    for source in (tripulantes, habilitacoes):
        for expected in (
            "ui-filter-panel",
            "ui-filter-drawer",
            "ui-filter-advanced",
            "ui-filter-toggle",
        ):
            assert expected in source

    assert "wireResponsiveFilterPanel" in tripulantes
    assert "wireResponsiveFilterPanel(toggleId, panelId, expandedText, collapsedText);" in report_ui

    for preserved in (
        'id="tripulantes-filters-form"',
        'buildHashHref(baseHash, Object.fromEntries(form.entries()))',
        'id="tripulantesDenseFiltersToggle"',
    ):
        assert preserved in tripulantes

    for source, route in ((habilitacoes, "#/relatorios/habilitacoes"),):
        assert "new FormData" in source
        assert route in source


def test_filter_policy_css_bridges_legacy_aliases_to_shared_rules():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        ".filters-bar.ui-filter-bar",
        ".filters-bar-main.ui-filter-row",
        ".filters-main-grid.ui-filter-row",
        ".filters-bar-actions.ui-filter-actions",
        ".filter-actions.ui-filter-actions",
        ".filters-panel.ui-filter-panel",
        ".filters-panel.ui-filter-panel.collapsed",
        ".filters-panel .filters",
    ):
        assert expected in css

    for preserved in (
        ".filters-bar-main {\n  display: grid;",
        ".filters-bar-actions {\n  display: flex;",
        ".filters-state-chip",
        "@media (max-width: 900px)",
    ):
        assert preserved in css


def test_filter_policy_is_registered_in_migration_readme():
    migration = _read(MIGRATION_DIR / "34.2.6-politica-filtros-responsivos.md")
    index = _read(MIGRATION_DIR / "README.md")

    for expected in (
        "Politica oficial de filtros responsivos",
        "`ui-filter-bar`: barra principal",
        "`ui-filter-row`: controles primarios",
        "`ui-filter-actions`: aplicar, limpar e alternar",
        "`ui-filter-panel`: painel avancado",
        "`ui-filter-drawer`: painel denso",
        "`ui-filter-summary` e `ui-filter-chip`: persistencia visual local",
        "backend, contratos, rotas e regras de dominio permanecem intactos",
    ):
        assert expected in migration

    assert "34.2.6-politica-filtros-responsivos.md" in index
