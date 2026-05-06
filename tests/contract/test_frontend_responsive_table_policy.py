from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"
MIGRATION_DIR = ROOT / "docs" / "migration"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_exposes_official_responsive_table_policy_without_domain_leak():
    tokens = _read(SHARED_UI_DIR / "tokens.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")
    readme = _read(SHARED_UI_DIR / "README.md")

    for expected in (
        "--size-table-scroll-min",
        "--size-table-scroll-dense-min",
        "--size-table-card-label",
        "--space-table-card-gap",
    ):
        assert expected in tokens

    for expected in (
        ".ui-table-scroll-controlled",
        ".ui-table-density-comfortable",
        ".ui-table-cell-primary",
        ".ui-table-cell-secondary",
        ".ui-table-cell-muted",
        ".ui-table-row-detail",
        ".ui-table-expand-toggle",
        "var(--size-table-scroll-min)",
        "var(--size-touch-target)",
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

    assert "data-responsive-priority" in readme
    assert "data-responsive-density" in readme
    assert "data-label" in readme


def test_table_enhancer_materializes_labels_priorities_density_and_expandable_rows():
    source = _read(FRONTEND_SRC / "lib.js")

    for expected in (
        'const TABLE_PRIORITY_VALUES = new Set(["primary", "secondary", "tertiary", "actions", "detail"])',
        "function normalizeTableLabel(label)",
        "function tableColumnKey(label, index)",
        "function inferTableCellPriority(cell, index, header, totalCells)",
        "function inferTableDensity(table)",
        'table.dataset.operationalSurface = "table-responsive";',
        "table.dataset.responsiveDensity = inferTableDensity(table);",
        "cell.dataset.responsiveColumn = tableColumnKey(",
        "cell.dataset.responsivePriority = inferTableCellPriority(",
        'row.dataset.responsiveExpandable = "true";',
        'cell.setAttribute("data-label", header.label);',
        'cell.setAttribute("headers", header.id);',
    ):
        assert expected in source

    for preserved in (
        "enhanceOperationalSurfaces(root = document)",
        "enhanceFormControlLabels(scope)",
        "enhanceResponsiveTables(scope)",
    ):
        assert preserved in source


def test_responsive_table_css_defines_card_priority_actions_density_and_states():
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        '.data-table[data-responsive-density="compact"] tbody td',
        '.data-table[data-responsive-density="comfortable"] tbody td',
        '.data-table :where([data-responsive-priority="actions"], .actions)',
        '@media (max-width: 900px)',
        '.data-table.responsive-cards tbody tr[data-responsive-row="record"] {\n    display: grid;',
        "grid-template-columns: var(--size-table-card-label);",
        '.data-table.responsive-cards tbody td[data-responsive-priority="primary"]',
        '.data-table.responsive-cards tbody td[data-responsive-priority="secondary"]',
        '.data-table.responsive-cards tbody td[data-responsive-priority="tertiary"]',
        '.data-table.responsive-cards tbody td[data-responsive-priority="detail"]',
        '.data-table.responsive-cards tbody td[data-responsive-priority="actions"]',
        '.data-table.responsive-cards .ui-table-state[data-empty-type="loading"]',
        '.data-table.responsive-cards .ui-table-state[data-empty-type="error"]',
        '@media (max-width: 640px)',
        ".data-table.responsive-cards tbody td:not(.actions) {\n    grid-template-columns: 1fr;",
    ):
        assert expected in css


def test_priority_table_surfaces_remain_on_responsive_cards_pattern():
    sources = {
        "dashboard": FRONTEND_SRC / "features" / "dashboard" / "page.js",
        "tripulantes": FRONTEND_SRC / "features" / "tripulantes" / "list-page.js",
        "habilitacoes": FRONTEND_SRC / "features" / "relatorios" / "habilitacoes-page.js",
        "training_root": FRONTEND_SRC / "features" / "training-root" / "page.js",
    }

    for name, path in sources.items():
        source = _read(path)
        assert "responsive-cards" in source, name
        assert "data-table" in source, name

    for path in sources.values():
        source = _read(path)
        assert "api(" in source or "export function" in source


def test_policy_is_registered_in_migration_readme():
    migration = _read(MIGRATION_DIR / "34.2.4-politica-tabelas-responsivas.md")
    index = _read(MIGRATION_DIR / "README.md")

    for expected in (
        "Politica oficial de tabelas responsivas",
        "`primary`: identificador principal da linha",
        "`secondary`: estado, data, vencimento",
        "`tertiary`: metadados",
        "`detail`: observacoes",
        "`actions`: acoes por linha",
        "`ui-table-scroll-controlled`",
        "`data-responsive-priority`",
        "`ui-table-state`",
        "backend, contratos, rotas e regras de dominio permanecem intactos",
    ):
        assert expected in migration

    assert "34.2.4-politica-tabelas-responsivas.md" in index
