from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"
MIGRATION_DIR = ROOT / "docs" / "migration"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_exposes_official_responsive_overlay_policy_without_domain_leak():
    tokens = _read(SHARED_UI_DIR / "tokens.css")
    primitives = _read(SHARED_UI_DIR / "primitives.css")
    readme = _read(SHARED_UI_DIR / "README.md")

    for expected in (
        "--size-overlay-modal-max",
        "--size-overlay-modal-wide-max",
        "--size-overlay-drawer-width",
        "--size-overlay-side-panel-width",
        "--size-overlay-max-height",
        "--space-overlay-gutter",
        "--space-overlay-panel-padding",
        "--space-overlay-actions-gap",
    ):
        assert expected in tokens

    for expected in (
        "body.ui-overlay-open",
        "body.ui-scroll-locked",
        ".ui-overlay-root",
        ".ui-overlay-backdrop",
        ".ui-overlay-panel",
        ".ui-modal",
        ".ui-drawer",
        ".ui-side-panel",
        ".ui-overlay-header",
        ".ui-overlay-body",
        ".ui-overlay-actions",
        ".ui-overlay-close",
        "overscroll-behavior: contain;",
        "position: sticky;",
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

    assert "Modais, drawers e overlays responsivos oficiais" in readme
    assert "ui-overlay-root" in readme
    assert "scroll lock" in readme


def test_overlay_helpers_define_scroll_lock_focus_trap_escape_and_return_focus():
    source = _read(FRONTEND_SRC / "lib.js")

    for expected in (
        "const OVERLAY_FOCUSABLE_SELECTOR",
        "const activeScrollLocks = new Set();",
        "function syncDocumentScrollLockState()",
        "export function setDocumentScrollLock",
        'body.classList.toggle("ui-overlay-open", hasLocks);',
        "export function getFocusableElements",
        "export function trapFocusWithin",
        "event.key !== \"Tab\"",
        "document.activeElement === first",
        "document.activeElement === last",
        "export function wireResponsiveOverlay",
        "panelEl.dataset.overlayState = open ? \"open\" : \"closed\";",
        "panelEl.setAttribute(\"aria-hidden\", open ? \"false\" : \"true\");",
        "panelEl.setAttribute(\"role\", panelEl.getAttribute(\"role\") || \"dialog\");",
        "panelEl.setAttribute(\"aria-modal\", \"true\");",
        "backdropEl.dataset.overlayState = open ? \"open\" : \"closed\";",
        "setDocumentScrollLock(lockKey, open && modal);",
        "requestAnimationFrame(() => focusTarget?.focus?.());",
        "event.key === \"Escape\"",
        "trapFocusWithin(panelEl, event);",
    ):
        assert expected in source

    for preserved in (
        "export function enhanceOperationalSurfaces(root = document)",
        "enhanceResponsiveForms(scope);",
        "enhanceResponsiveFilters(scope);",
        "enhanceResponsiveTables(scope);",
    ):
        assert preserved in source


def test_shell_drawer_adopts_overlay_policy_without_navigation_or_permission_drift():
    source = _read(FRONTEND_SRC / "shell" / "render-shell.js")
    css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        "setDocumentScrollLock",
        "trapFocusWithin",
        'setDocumentScrollLock("shell-sidebar", isOpen && isDrawer);',
        "trapFocusWithin(sidebar, event);",
        'data-overlay-backdrop="shell"',
        'data-overlay-panel="navigation-drawer"',
        'data-overlay-state="closed"',
        'sidebar.dataset.overlayState = isOpen && isDrawer ? "open" : "closed";',
        'sidebar.dataset.overlaySurface = isDrawer ? "modal-drawer" : "persistent-navigation";',
        'overlay.dataset.overlayState = isOpen && isDrawer ? "open" : "closed";',
        'document.body.classList.toggle("sidebar-open", isOpen && isDrawer);',
        'sidebar.setAttribute("role", "dialog")',
        'sidebar.setAttribute("aria-modal", "true")',
        'mainColumn.inert = isInert',
    ):
        assert expected in source

    for preserved in (
        "renderNavigation(activeRoute)",
        "resolveActiveNavigation(activeRoute)",
        "BACKEND_LINKS.notificacoesEmail",
        'api("/api/v1/session/logout", { method: "POST", handleAuth: false })',
    ):
        assert preserved in source

    for expected in (
        "34.2.8: overlay policy bridges shell drawer and inline filter drawers to shared/ui primitives.",
        ".sidebar-overlay.ui-overlay-backdrop",
        ".sidebar[data-overlay-panel]",
        ".filters-panel.ui-filter-panel.ui-filter-drawer.ui-overlay-inline-drawer",
        ".filters-main-grid.ui-filter-panel.ui-filter-drawer.ui-overlay-inline-drawer",
    ):
        assert expected in css


def test_inline_filter_drawers_receive_overlay_state_without_becoming_modal():
    source = _read(FRONTEND_SRC / "lib.js")

    for expected in (
        'panel.dataset.overlayState = expanded ? "open" : "closed";',
        'panel.dataset.overlaySurface = panel.classList.contains("ui-filter-drawer")',
        '"inline-drawer"',
        'panel.setAttribute("aria-hidden", expanded ? "false" : "true");',
        'panel.setAttribute("role", "region");',
        'panel.classList.add("ui-overlay-inline-drawer");',
        'toggle.dataset.overlayTrigger = toggle.dataset.overlayTrigger || "inline-drawer";',
    ):
        assert expected in source

    assert 'panelEl.setAttribute("aria-modal", "true");' in source
    assert 'panel.dataset.filterPanel = panel.dataset.filterPanel || "advanced";' in source


def test_overlay_policy_is_registered_in_migration_readme():
    migration = _read(MIGRATION_DIR / "34.2.8-politica-modais-drawers-overlays-responsivos.md")
    index = _read(MIGRATION_DIR / "README.md")

    for expected in (
        "Politica oficial de modais, drawers e overlays responsivos",
        "`ui-overlay-root`: raiz fixa",
        "`ui-overlay-backdrop`: camada de bloqueio",
        "`ui-modal`: dialogo central",
        "`ui-drawer`: painel lateral",
        "`ui-side-panel`: painel lateral largo",
        "`ui-overlay-actions`: acoes fixas",
        "`setDocumentScrollLock`: scroll lock tokenizado",
        "`trapFocusWithin`: foco contido",
        "`wireResponsiveOverlay`: contrato comportamental",
        "backend, contratos, rotas e regras de dominio permanecem intactos",
    ):
        assert expected in migration

    assert "34.2.8-politica-modais-drawers-overlays-responsivos.md" in index
