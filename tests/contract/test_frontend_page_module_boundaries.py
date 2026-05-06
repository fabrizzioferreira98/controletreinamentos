from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"

PAGE_MODULE_BOUNDARIES = {
    "pages-dashboard-tripulantes.js": {
        "classification": "pagina_spa_viva",
        "loader": "tripulantes",
        "router_exports": {
            "renderDashboardPage",
            "renderOperationalDashboardPage",
            "renderOperationalDashboardTvPage",
            "renderTripulantesListPage",
            "renderRelatorioIndividualPage",
            "renderTripulanteFormPage",
        },
    },
    "pages-financeiro.js": {
        "classification": "pagina_spa_viva",
        "loader": "financeiro",
        "router_exports": {
            "renderFinanceiroMissoesPage",
            "renderFinanceiroLancamentosJornadaPage",
            "renderFinanceiroFechamentoParametrosPage",
        },
    },
    "pages-treinamentos-relatorios.js": {
        "classification": "pagina_spa_viva",
        "loader": "treinamentos",
        "router_exports": {
            "renderTreinamentosListPage",
            "renderTrainingRootPage",
            "renderTreinamentoFormPage",
            "renderRelatorioHabilitacoesPage",
        },
    },
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _page_modules() -> set[str]:
    return {path.name for path in FRONTEND_SRC.glob("pages-*.js")}


def _app_source() -> str:
    return _read(FRONTEND_SRC / "app.js")


def _route_registry_source() -> str:
    return _read(FRONTEND_SRC / "app" / "route-registry.js")


def _router_page_imports() -> set[str]:
    return set(re.findall(r'import\("\.\./(pages-[^"?]+\.js)(?:\?v=[^"]*)?"\)', _route_registry_source()))


def _router_export_refs() -> dict[str, set[str]]:
    route_registry_source = _route_registry_source()
    refs: dict[str, set[str]] = defaultdict(set)
    for loader, export_name in re.findall(
        r'moduleName:\s*"([^"]+)",\s*exportName:\s*"([^"]+)"',
        route_registry_source,
    ):
        refs[loader].add(export_name)
    return refs


def _frontend_page_import_refs() -> dict[str, set[str]]:
    refs: dict[str, set[str]] = defaultdict(set)
    pattern = re.compile(r'(?:import\(|from\s+)["\'](?:\./|\../)(pages-[^"\']+\.js)(?:\?v=[^"\']*)?["\']')
    for path in FRONTEND_SRC.rglob("*.js"):
        source = _read(path)
        for module_name in pattern.findall(source):
            refs[module_name].add(path.relative_to(FRONTEND_SRC).as_posix())
    return refs


def _exported_functions(module_name: str) -> set[str]:
    source = _read(FRONTEND_SRC / module_name)
    return set(re.findall(r"export async function ([A-Za-z0-9_]+)\(", source))


def test_all_frontend_page_modules_have_explicit_boundary_status():
    assert _page_modules() == set(PAGE_MODULE_BOUNDARIES)


def test_only_spa_page_modules_are_imported_by_the_frontend_router():
    expected_imports = {
        module_name
        for module_name, metadata in PAGE_MODULE_BOUNDARIES.items()
        if metadata["classification"] == "pagina_spa_viva"
    }
    assert _router_page_imports() == expected_imports


def test_spa_page_module_exports_match_router_references():
    router_refs = _router_export_refs()
    for module_name, metadata in PAGE_MODULE_BOUNDARIES.items():
        loader = metadata["loader"]
        if metadata["classification"] != "pagina_spa_viva":
            assert loader is None
            continue
        assert metadata["router_exports"] <= _exported_functions(module_name)
        assert router_refs[loader] == metadata["router_exports"]


def test_non_routed_page_modules_have_no_frontend_importers():
    refs = _frontend_page_import_refs()
    for module_name, metadata in PAGE_MODULE_BOUNDARIES.items():
        if metadata["classification"] == "pagina_spa_viva":
            assert refs[module_name] == {"app/route-registry.js"}
        else:
            assert module_name not in refs


def test_removed_training_workspace_module_does_not_return_as_residual_surface():
    assert not (FRONTEND_SRC / "pages-training-workspace.js").exists()
    assert "pages-training-workspace.js" not in _route_registry_source()
    assert "pages-training-workspace.js" not in _app_source()


def test_page_module_boundaries_are_documented_in_frontend_architecture():
    architecture_doc = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")
    for module_name, metadata in PAGE_MODULE_BOUNDARIES.items():
        assert f"| `{module_name}` | `{metadata['classification']}` |" in architecture_doc
