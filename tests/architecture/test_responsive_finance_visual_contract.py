from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
APP_CSS = FRONTEND_SRC / "app.css"
SHELL = FRONTEND_SRC / "shell" / "render-shell.js"
JORNADA_PAGE = FRONTEND_SRC / "features" / "financeiro" / "bonificacoes-page.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mobile_sidebar_drawer_open_state_is_visible_and_overlay_is_scoped_to_drawer():
    css = read(APP_CSS)
    shell = read(SHELL)

    assert "overlay.classList.toggle(\"show\", isOpen && isDrawer)" in shell
    assert "document.body.classList.toggle(\"sidebar-open\", isOpen && isDrawer)" in shell
    assert "body.sidebar-open .app-shell[data-sidebar-viewport=\"drawer\"] .sidebar.ui-inverse-surface.open" in css
    assert ".app-shell[data-sidebar-viewport=\"drawer\"] .sidebar.ui-inverse-surface.open" in css
    assert "transform: translate3d(0, 0, 0)" in css
    assert "transform: translate3d(-100%, 0, 0)" in css
    assert "width: min(82vw, 320px)" in css
    assert "max-width: 320px" in css
    assert "pointer-events: auto" in css


def test_jornada_table_has_controlled_horizontal_scroll_and_keyboard_focus():
    css = read(APP_CSS)
    source = read(JORNADA_PAGE)

    assert 'class="jornada-table-scroll-hint"' in source
    assert 'data-jornada-table-wrap tabindex="0"' in source
    assert 'aria-label="Grade de lançamentos de jornada com rolagem horizontal controlada"' in source
    assert ".financeiro-jornada-page .jornada-table-wrap:focus-visible" in css
    assert "overscroll-behavior-inline: contain" in css
    assert "-webkit-overflow-scrolling: touch" in css
    assert ".financeiro-jornada-page .jornada-table tbody tr:not(.jornada-edit-row) > td" in css
    assert "white-space: nowrap" in css


def test_jornada_mobile_actions_and_editable_row_have_responsive_density_contract():
    css = read(APP_CSS)

    assert ".financeiro-jornada-page .jornada-hero-actions" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(190px, 1fr))" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert ".financeiro-jornada-page .jornada-hero-actions > #jornadaExportPdf" in css
    assert "white-space: normal" in css
    assert "@media (max-width: 1400px)" in css
    assert "@media (max-width: 380px)" in css
    assert ".financeiro-jornada-page .jornada-edit-row td:nth-child(6)" in css
    assert ".financeiro-jornada-page .jornada-edit-row td:nth-child(8)" in css
    assert "min-height: 40px" in css
    assert ".financeiro-jornada-page .jornada-row-actions" in css
    assert "flex-wrap: nowrap" in css
    assert ".financeiro-jornada-page .jornada-table td.actions" in css
