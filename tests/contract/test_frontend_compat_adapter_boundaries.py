from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
COMPAT_DIR = FRONTEND_SRC / "compat"

EXPECTED_COMPAT_MODULES = {
    "backend-links.js",
    "static-assets.js",
}

BACKEND_PATH_MARKERS = (
    "/auditoria",
    "/backups",
    "/bases",
    "/equipamentos",
    "/manual/usuario.pdf",
    "/monitoramento",
    "/notificacoes-email",
    "/pernoites",
    "/pernoites/novo",
    "/tipos-treinamento",
    "/treinamentos/consolidado",
    "/treinamentos/consolidado/export.csv",
    "/treinamentos/consolidado/export.pdf",
    "/treinamentos/consolidado/relatorio",
    "/usuarios",
    "/usuarios/novo",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_frontend_compat_modules_exist_with_explicit_owners():
    assert {path.name for path in COMPAT_DIR.glob("*.js")} == EXPECTED_COMPAT_MODULES

    backend_links_source = _read(COMPAT_DIR / "backend-links.js")
    static_assets_source = _read(COMPAT_DIR / "static-assets.js")

    assert "export const BACKEND_LINKS" in backend_links_source
    assert "export const CANONICAL_FRONTEND_HASHES" in backend_links_source
    assert "export const BACKEND_LINK_BOUNDARIES" in backend_links_source
    assert "export const LEGACY_BACKEND_PATH_ALIASES" in backend_links_source
    assert "export const FRONTEND_HASH_BY_BACKEND_PATH" in backend_links_source
    assert "export function buildBackendHref" in backend_links_source
    assert "export function resolveFrontendHashForBackendPath" in backend_links_source
    assert "export function resolveLoginDestination" in backend_links_source
    assert "export const STATIC_ASSETS" in static_assets_source


def test_static_asset_references_are_centralized_for_javascript_modules():
    for path in FRONTEND_SRC.rglob("*.js"):
        if path == COMPAT_DIR / "static-assets.js":
            continue
        assert "/static/" not in _read(path), path

    index_html = _read(FRONTEND_SRC / "index.html")
    assert "/static/favicon-192.png" in index_html
    assert "/static/site.webmanifest" in index_html


def test_backend_ssr_links_are_centralized_for_javascript_modules():
    for path in FRONTEND_SRC.rglob("*.js"):
        if path == COMPAT_DIR / "backend-links.js":
            continue
        source = _read(path)
        for marker in BACKEND_PATH_MARKERS:
            quoted_markers = (f'"{marker}"', f"'{marker}'", f"`{marker}`")
            assert not any(quoted in source for quoted in quoted_markers), f"{path}: {marker}"


def test_training_root_backend_path_is_redirect_only_and_maps_to_canonical_hash():
    backend_links_source = _read(COMPAT_DIR / "backend-links.js")

    assert 'trainingRoot: "#/treinamentos/raiz"' in backend_links_source
    assert 'tipos: "/tipos-treinamento"' in backend_links_source
    assert '[BACKEND_LINKS.tipos]: "backend_ssr_compat_redirect_only"' in backend_links_source
    assert '"/tipos": CANONICAL_FRONTEND_HASHES.trainingRoot' in backend_links_source
    assert "[BACKEND_LINKS.tipos]: CANONICAL_FRONTEND_HASHES.trainingRoot" in backend_links_source
    assert "resolveFrontendHashForBackendPath(path)" in backend_links_source


def test_compat_adapter_boundaries_are_documented():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")

    for expected in (
        "`frontend/src/compat/backend-links.js`",
        "`frontend/src/compat/static-assets.js`",
        "compat/static/backend adapters",
        "`frontend/src/index.html`",
        "bootstrap HTML",
    ):
        assert expected in architecture
