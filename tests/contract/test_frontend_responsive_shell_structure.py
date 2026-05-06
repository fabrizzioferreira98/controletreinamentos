from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SHARED_UI_DIR = FRONTEND_SRC / "shared" / "ui"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_responsive_shell_tokens_define_fluid_gutters_without_domain_leak():
    tokens = _read(SHARED_UI_DIR / "tokens.css")

    for expected in (
        "--space-layout-content-fluid",
        "--space-layout-content-narrow",
        "clamp(var(--space-4), 1.6vw, var(--space-6))",
    ):
        assert expected in tokens


def test_page_header_primitive_collapses_before_mobile_breakpoint():
    primitives = _read(SHARED_UI_DIR / "primitives.css")

    for expected in (
        ".ui-page-header",
        "grid-template-columns: minmax(0, 1fr) auto;",
        ".ui-page-header > *",
        ".ui-page-header :where(.page-header-actions)",
        "@media (max-width: 900px)",
        "grid-template-columns: minmax(0, 1fr);",
    ):
        assert expected in primitives

    for forbidden in (
        "dashboard",
        "tripulante",
        "treinamento",
        "relatorio",
    ):
        assert forbidden not in primitives


def test_shell_content_and_topbar_use_intermediate_breakpoint_guards():
    app_css = _read(FRONTEND_SRC / "app.css")

    for expected in (
        ".topbar.ui-sticky-surface",
        "grid-template-columns: minmax(0, 1fr) auto;",
        "padding: var(--space-section-gap) var(--space-layout-content-fluid);",
        ".content.ui-content-region",
        "width: min(100%, var(--size-content-wide));",
        "padding-inline: var(--space-layout-content-fluid);",
        "@media (max-width: 1180px)",
        ".page-header.ui-page-header",
        ".dashboard-top-cluster > .priority-page-header.ui-page-header.ui-surface",
        "@media (max-width: 640px)",
        "padding-inline: var(--space-layout-content-narrow);",
    ):
        assert expected in app_css


def test_shell_markup_contract_is_not_reclassified_by_responsive_adjustment():
    render_shell = _read(FRONTEND_SRC / "shell" / "render-shell.js")

    for preserved in (
        'class="app-shell ui-app-frame"',
        'class="sidebar ui-inverse-surface"',
        'class="topbar ui-sticky-surface"',
        'class="content ui-content-region"',
        "renderNavigation(activeRoute)",
        "BACKEND_LINKS.notificacoesEmail",
        'api("/api/v1/session/logout", { method: "POST", handleAuth: false })',
    ):
        assert preserved in render_shell
