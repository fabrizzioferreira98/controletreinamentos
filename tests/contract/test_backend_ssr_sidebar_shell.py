from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_TEMPLATE = ROOT / "backend" / "src" / "controle_treinamentos" / "templates" / "base.html"
BACKEND_STYLES = ROOT / "backend" / "src" / "controle_treinamentos" / "static" / "styles.css"


def test_backend_ssr_sidebar_uses_official_expanded_collapsed_contract():
    source = BASE_TEMPLATE.read_text(encoding="utf-8")

    expected = [
        'data-sidebar-contract="sidebar-v1"',
        'data-sidebar-state="expanded"',
        'class="sidebar-mode-toggle"',
        'id="sidebarModeToggle"',
        "data-sidebar-mode-toggle",
        "sidebar-mode-icon-collapse",
        "sidebar-mode-icon-expand",
        "nextSidebarState",
        "syncSidebarModeToggle",
        "const sidebarStates = new Set(['expanded', 'iconic']);",
        "['compact', 'iconic']",
        "controle-treinamentos:ssr-sidebar-state:v1:",
        "defaultSidebarStateForViewport",
        "resolveSidebarStateForViewport",
        "notebookCollapsedQuery",
        "tabletRailQuery",
        "setSidebarState(readSidebarState(), { persist: false });",
    ]

    for marker in expected:
        assert marker in source

    assert '<span class="nav-icon" aria-hidden="true">{{ code }}</span>' not in source
    assert 'class="nav-icon" data-nav-icon="{{ nav_icon_code }}"' in source
    assert "nav_icon_code in ['PG', 'DB']" in source
    assert "nav_icon_code == 'TV'" in source
    assert "nav_icon_code == 'PDF'" in source
    assert "root.querySelectorAll('span.nav-icon')" in source
    assert "legacyNavIconAliases" in source

    removed_prototype_markers = [
        'class="sidebar-state-controls"',
        'data-sidebar-state-option="expanded"',
        'data-sidebar-state-option="compact"',
        'data-sidebar-state-option="iconic"',
    ]

    for marker in removed_prototype_markers:
        assert marker not in source

    assert "return 'compact';" not in source


def test_backend_ssr_sidebar_preserves_route_and_permission_contracts():
    source = BASE_TEMPLATE.read_text(encoding="utf-8")

    expected = [
        "can_access('dashboard:view')",
        'href="/#/dashboard"',
        "can_access('bases:view')",
        "url_for('bases.index')",
        'href="/#/relatorios/habilitacoes"',
        'href="/#/relatorios/individual"',
        "financeiro_visible",
        "can_access('finance:bonuses:read')",
        "can_access('finance:parameters:read')",
        "can_access('finance:periods:read')",
        'href="/#/tripulantes"',
        'href="/#/treinamentos"',
        'href="/#/treinamentos/raiz"',
        'href="/#/financeiro/lancamentos-jornada"',
        'href="/#/financeiro/fechamento-parametros"',
        "can_access('notificacoes:view')",
        "url_for('admin.notificacoes_list')",
        'hx-boost="false"',
    ]

    for marker in expected:
        assert marker in source

    for forbidden in (
        "href=\"{{ url_for('dashboard.dashboard') }}\"",
        "href=\"{{ url_for('cadastros.treinamentos_consolidado') }}\"",
        "href=\"{{ url_for('cadastros.tripulantes_list') }}\"",
        "href=\"{{ url_for('cadastros.treinamentos_list') }}\"",
        "href=\"{{ url_for('cadastros.tipos_list') }}\"",
        "href=\"/tipos\"",
    ):
        assert forbidden not in source


def test_backend_ssr_sidebar_exposes_active_and_footer_surfaces():
    source = BASE_TEMPLATE.read_text(encoding="utf-8")

    expected = [
        "nav-primary-link",
        "Painel Geral",
        "data-nav-active-child",
        "nav-active-indicator",
        "session-card",
        "session-profile-summary",
        "logout-button",
        "sidebar-ssr-20260426-5",
        "upgradeLegacyNavIcons",
        "legacyNavIconMarkup",
        "document.body.addEventListener('htmx:afterSwap'",
    ]

    for marker in expected:
        assert marker in source


def test_backend_ssr_sidebar_css_supports_modes_drawer_and_flyouts():
    css = BACKEND_STYLES.read_text(encoding="utf-8")

    expected = [
        "SSR sidebar parity",
        "--size-sidebar-width",
        "--size-sidebar-compact-width",
        "--size-sidebar-iconic-width",
        ".sidebar-state-controls {\n    display: none !important;",
        ".sidebar-mode-toggle",
        ".sidebar-mode-toggle::before",
        ".sidebar-mode-toggle::after",
        '.sidebar-mode-toggle[data-sidebar-mode-state="iconic"]::before',
        ".sidebar-mode-icon-expand",
        '.sidebar-mode-toggle[data-sidebar-mode-state="iconic"] .sidebar-mode-icon-expand',
        "svg.nav-icon",
        "span.nav-icon::before",
        '.app-shell[data-sidebar-state="compact"]',
        '.app-shell[data-sidebar-state="iconic"]',
        ".nav-group.flyout-open .nav-group-links",
        "@media (min-width: 1024px) and (max-width: 1279px)",
        "@media (min-width: 768px) and (max-width: 1023px)",
        "@media (max-width: 767px)",
        ".sidebar.ui-inverse-surface.open",
    ]

    for marker in expected:
        assert marker in css

    assert '.sidebar-mode-toggle[data-sidebar-mode-state="iconic"] .sidebar-mode-icon-expand {\n    opacity: 1;' in css
    assert '.sidebar-mode-toggle[data-sidebar-mode-state="iconic"] .sidebar-mode-icon-expand {\n    display: block;' not in css
    assert ".sidebar-mode-toggle-icon {\n    position: absolute;" in css
    assert "pointer-events: none;" in css
    assert "font-size: 0;" in css
