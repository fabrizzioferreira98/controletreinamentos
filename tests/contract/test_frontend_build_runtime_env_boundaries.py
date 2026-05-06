from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = ROOT / "frontend"
BUILD_SCRIPT = FRONTEND_ROOT / "scripts" / "build_frontend.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_frontend_build_script_declares_output_config_and_backend_css_coupling():
    source = _read(BUILD_SCRIPT)

    assert 'parser.add_argument("--output-dir"' in source
    assert 'parser.add_argument("--env-file"' in source
    assert "BACKEND_STATIC_DIRS" in source
    assert "BACKEND_STYLES_PATH" in source
    assert "SHARED_UI_STYLES" in source
    assert "compose_stylesheet()" in source
    assert "build_asset_payloads(env)" in source
    assert "build_fingerprint_map(asset_payloads, build_version)" in source
    assert "write_fingerprinted_assets(output_dir, rewritten_payloads, fingerprint_map)" in source
    assert "rewrite_html_references(output_dir, fingerprint_map)" in source
    assert '"asset-manifest.json"' in source
    assert "copy_static_tree(output_dir)" in source


def test_frontend_build_env_generates_runtime_config_outside_checkout(tmp_path):
    env_file = tmp_path / "frontend.env"
    output_dir = tmp_path / "frontend-dist"
    env_file.write_text(
        "\n".join(
            [
                "FRONTEND_APP_NAME=Controle B06",
                "FRONTEND_API_BASE_URL=https://api.example.test",
                "FRONTEND_PUBLIC_ORIGIN=https://app.example.test",
                "FRONTEND_ENABLE_DEBUG=1",
            ]
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--env-file",
            str(env_file),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        check=True,
    )

    manifest = json.loads(_read(output_dir / "asset-manifest.json"))
    entrypoints = manifest["entrypoints"]
    config_js = _read(output_dir / entrypoints["config.js"])
    generated_css = _read(output_dir / entrypoints["app.css"])
    index_html = _read(output_dir / "index.html")
    frontend_css = _read(FRONTEND_ROOT / "src" / "app.css")

    assert output_dir.resolve() != (FRONTEND_ROOT / "dist").resolve()
    assert manifest["schema"] == "frontend_asset_manifest_v1"
    assert re.search(r"\.\d{8}-\d{6}\.[0-9a-f]{12}\.js$", entrypoints["app.js"])
    assert re.search(r"\.\d{8}-\d{6}\.[0-9a-f]{12}\.css$", entrypoints["app.css"])
    assert re.search(r"\.\d{8}-\d{6}\.[0-9a-f]{12}\.js$", entrypoints["config.js"])
    assert 'appName: "Controle B06"' in config_js
    assert 'apiBaseUrl: "https://api.example.test"' in config_js
    assert 'publicOrigin: "https://app.example.test"' in config_js
    assert "debug: true" in config_js
    assert "Frontend shared/ui foundation." in generated_css
    assert "Shared UI foundation: semantic tokens" in generated_css
    assert ".ui-stack" in generated_css
    assert "Frontend desacoplado: pequenos ajustes e compatibilidades." in generated_css
    assert len(generated_css) > len(frontend_css)
    assert "?v=" not in index_html
    assert entrypoints["app.js"] in index_html
    assert entrypoints["app.css"] in index_html
    assert entrypoints["config.js"] in index_html
    assert not (output_dir / "app.js").exists()
    assert not (output_dir / "app.css").exists()
    assert not (output_dir / "config.js").exists()


def test_frontend_build_output_has_manifest_closed_js_css_graph(tmp_path):
    output_dir = tmp_path / "frontend-dist"

    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--env-file",
            str(FRONTEND_ROOT / ".env.example"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        check=True,
    )

    manifest = json.loads(_read(output_dir / "asset-manifest.json"))
    manifest_assets = {
        Path(value).as_posix()
        for value in manifest["fingerprinted_assets"].values()
        if Path(value).suffix in {".js", ".css"}
    }
    disk_assets = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file() and path.suffix in {".js", ".css"}
    }

    assert disk_assets == manifest_assets
    assert all(re.search(r"\.\d{8}-\d{6}\.[0-9a-f]{12}\.(?:js|css)$", asset) for asset in disk_assets)

    index_html = _read(output_dir / "index.html")
    index_refs = {
        Path(match).as_posix().removeprefix("./")
        for match in re.findall(r"""(?:src|href)=["']([^"']+\.(?:js|css))["']""", index_html)
    }
    assert index_refs == set(manifest["entrypoints"].values())


def test_frontend_env_templates_are_classified_as_templates_not_real_environment():
    frontend_env = _read(FRONTEND_ROOT / ".env.example")
    root_env = _read(ROOT / ".env.example")
    hml_env = _read(ROOT / "ops" / "windows" / "env" / "hml.env.example")
    prod_env = _read(ROOT / "ops" / "windows" / "env" / "prod.env.example")

    for key in (
        "FRONTEND_APP_NAME",
        "FRONTEND_API_BASE_URL",
        "FRONTEND_PUBLIC_ORIGIN",
        "FRONTEND_ENABLE_DEBUG",
    ):
        assert f"{key}=" in frontend_env

    for key in (
        "FRONTEND_PUBLIC_ORIGIN",
        "FRONTEND_LOCAL_ORIGIN",
        "FRONTEND_ALLOWED_ORIGINS",
    ):
        assert f"{key}=" in root_env
        assert f"{key}=" in hml_env
        assert f"{key}=" in prod_env


def test_backend_runtime_owns_frontend_origin_and_cors_contracts():
    frontend_routes = _read(ROOT / "backend" / "src" / "controle_treinamentos" / "core" / "frontend_routes.py")
    cors = _read(ROOT / "backend" / "src" / "controle_treinamentos" / "core" / "cors.py")

    assert "FRONTEND_PUBLIC_ORIGIN" in frontend_routes
    assert "FRONTEND_LOCAL_ORIGIN" in frontend_routes
    assert "FRONTEND_COMPAT_REDIRECTS" in frontend_routes
    assert "FRONTEND_ALLOWED_ORIGINS" in cors
    assert "Access-Control-Allow-Credentials" in cors


def test_frontend_build_runtime_env_boundaries_are_documented():
    architecture = _read(ROOT / "docs" / "architecture" / "FRONTEND_ARCHITECTURE.md")
    frontend_readme = _read(FRONTEND_ROOT / "README.md")

    for expected in (
        "Build nao e runtime",
        "`config_de_build`",
        "`config_de_runtime`",
        "`acoplamento_backend_frontend`",
        "`publicacao_local_ou_homolog`",
        "`ambiguidade_pendente`",
        "`backend/src/controle_treinamentos/static/styles.css`",
        "`frontend/dist/config.js`",
        "Caddyfile.example",
    ):
        assert expected in architecture
    assert "nao autonomo em runtime" in frontend_readme


def test_frontend_edge_entry_html_cache_contract_in_caddy():
    caddyfile = _read(ROOT / "ops" / "windows" / "caddy" / "Caddyfile.example")

    assert caddyfile.count("path / /login /logout /index.html") >= 2
    assert caddyfile.count('Cache-Control "no-store, no-cache, must-revalidate, max-age=0"') >= 2
    assert 'Pragma "no-cache"' in caddyfile
    assert 'Expires "0"' in caddyfile
    assert caddyfile.count("@frontend_assets_immutable") >= 2
    assert caddyfile.count("path_regexp frontend_immutable") >= 2
    assert caddyfile.count('Cache-Control "public, max-age=31536000, immutable"') >= 2
    assert caddyfile.count("@frontend_assets_unfingerprinted") >= 2
    assert caddyfile.count("stale frontend asset path") >= 2
    assert caddyfile.count("@frontend_assets_mutable {") >= 2
    assert caddyfile.count("path /asset-manifest.json /login-citation-jet.jpg") >= 2
    assert caddyfile.count('Cache-Control "no-cache, max-age=0, must-revalidate"') >= 2
    assert "@frontend_assets_mutable path /index.html" not in caddyfile
    assert "/app.js /app.css /config.js" not in caddyfile


def test_frontend_publish_script_uses_atomic_swap_and_manifest_contract():
    publish_script = _read(ROOT / "ops" / "windows" / "scripts" / "Publish-Frontend.ps1")

    for expected in (
        "asset-manifest.json",
        "frontend_asset_manifest_v1",
        "Build ainda usa query string de versionamento (?v=)",
        "Assert-NoOrphanFrontendAssets",
        "Build contem JS/CSS fora do asset-manifest.json",
        "Assert-IndexReferencesManifestGraph",
        "manifest_sha256",
        'Rename-Item -LiteralPath $resolvedDestination -NewName (Split-Path -Leaf $previousDir)',
        'Rename-Item -LiteralPath $stagingDir -NewName $destinationLeaf',
    ):
        assert expected in publish_script


def test_frontend_asset_graph_closure_migration_is_indexed():
    readme = _read(ROOT / "README.md")
    migration = ROOT / "docs" / "migration" / "59.frontend-asset-graph-closed-publish-contract.md"

    assert migration.exists()
    assert "59.frontend-asset-graph-closed-publish-contract.md" in readme


def test_tripulante_pdf_preview_keeps_global_frame_deny_with_scoped_sameorigin_exception():
    caddyfile = _read(ROOT / "ops" / "windows" / "caddy" / "Caddyfile.example")

    assert 'X-Frame-Options "DENY"' in caddyfile
    assert "(tripulante_pdf_preview_embedding)" in caddyfile
    assert "path /api/v1/tripulantes/*/files/*" in caddyfile
    assert '>X-Frame-Options "SAMEORIGIN"' in caddyfile
    assert "frame-ancestors 'self'" in caddyfile
    assert caddyfile.count("import tripulante_pdf_preview_embedding") >= 2
