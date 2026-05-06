from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_frontend_first_architecture_wave_has_material_boundaries():
    expected_boundaries = {
        "app",
        "shell",
        "services",
        "state",
        "features",
        "compat",
    }

    assert expected_boundaries <= {path.name for path in FRONTEND_SRC.iterdir() if path.is_dir()}

    assert {path.name for path in (FRONTEND_SRC / "app").glob("*.js")} == {
        "bootstrap.js",
        "errors.js",
        "guards.js",
        "route-registry.js",
        "router.js",
    }
    assert {path.name for path in (FRONTEND_SRC / "shell").glob("*.js")} == {
        "login.js",
        "navigation.js",
        "redirects.js",
        "render-shell.js",
    }
    assert {path.name for path in (FRONTEND_SRC / "services").glob("*.js")} == {
        "api-client.js",
        "csrf-service.js",
        "financeiro-bonificacoes-api.js",
        "financeiro-missoes-api.js",
        "financeiro-parametros-api.js",
        "session-service.js",
        "trace-service.js",
    }
    assert {path.name for path in (FRONTEND_SRC / "state").glob("*.js")} == {
        "app-state.js",
        "draft-state.js",
        "flash-state.js",
        "navigation-state.js",
    }
    assert {path.name for path in (FRONTEND_SRC / "compat").glob("*.js")} == {
        "backend-links.js",
        "static-assets.js",
    }


def test_frontend_temporary_wrappers_remain_explicit_and_controlled():
    dashboard_wrapper = _read(FRONTEND_SRC / "pages-dashboard-tripulantes.js")
    financeiro_wrapper = _read(FRONTEND_SRC / "pages-financeiro.js")
    training_wrapper = _read(FRONTEND_SRC / "pages-treinamentos-relatorios.js")
    route_registry = _read(FRONTEND_SRC / "app" / "route-registry.js")
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    assert len(dashboard_wrapper) < 5000
    assert len(financeiro_wrapper) < 1200
    assert len(training_wrapper) < 6000
    assert "./features/dashboard/page.js" in dashboard_wrapper
    assert "./features/financeiro/missoes-page.js" in financeiro_wrapper
    assert "./features/treinamentos/list-page.js" in training_wrapper
    assert "../pages-dashboard-tripulantes.js" in route_registry
    assert "../pages-financeiro.js" in route_registry
    assert "../pages-treinamentos-relatorios.js" in route_registry
    assert "pages-training-workspace.js" not in route_registry
    assert not (FRONTEND_SRC / "pages-training-workspace.js").exists()
    assert "`pages-training-workspace.js` | `artefato_removido`" in architecture


def test_frontend_readiness_is_documented_without_hiding_residual_debt():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    for expected in (
        "`pronta_para_proxima_fase`",
        "`consolidado`",
        "`wrapper_temporario_controlado`",
        "`divida_residual_controlada`",
        "`baseline_fora_do_escopo`",
        "`admin/routes.py:748>725`",
    ):
        assert expected in architecture
