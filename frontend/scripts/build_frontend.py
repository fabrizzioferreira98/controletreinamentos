from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
DIST_DIR = ROOT / "dist"
FINGERPRINT_EXTENSIONS = {".js", ".css"}
SOURCE_REFERENCE_EXTENSIONS = ("js", "css")
BACKEND_STATIC_DIRS = [
    ROOT.parent / "backend" / "src" / "controle_treinamentos" / "static",
    ROOT.parent / "src" / "app" / "static",
]
BACKEND_STYLES_PATH = next(
    (candidate / "styles.css" for candidate in BACKEND_STATIC_DIRS if (candidate / "styles.css").exists()),
    BACKEND_STATIC_DIRS[0] / "styles.css",
)
SHARED_UI_STYLES = [
    SRC_DIR / "shared" / "ui" / "tokens.css",
    SRC_DIR / "shared" / "ui" / "primitives.css",
]


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de ambiente nao encontrado: {path}")
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def build_config(env: dict[str, str]) -> str:
    app_name = env.get("FRONTEND_APP_NAME", "Controle Treinamentos")
    api_base_url = env.get("FRONTEND_API_BASE_URL", "").rstrip("/")
    public_origin = env.get("FRONTEND_PUBLIC_ORIGIN", "").rstrip("/")
    enable_debug = "true" if env.get("FRONTEND_ENABLE_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"} else "false"
    public_origin_expr = f'"{public_origin}"' if public_origin else "window.location.origin"
    return (
        "window.__FRONTEND_CONFIG__ = "
        "{"
        f'appName: "{app_name}", '
        f'apiBaseUrl: "{api_base_url}", '
        f"publicOrigin: {public_origin_expr}, "
        f"debug: {enable_debug}"
        "};\n"
    )


def resolve_output_dir(output_dir: str | None) -> Path:
    if not output_dir:
        return DIST_DIR
    path = Path(output_dir)
    if not path.is_absolute():
        path = ROOT / path
    return path


def copy_static_tree(target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(
        SRC_DIR,
        target_dir,
        ignore=lambda _path, names: [
            name
            for name in names
            if Path(name).suffix.lower() in FINGERPRINT_EXTENSIONS
        ],
    )


def build_asset_version() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _sha256_short_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:12]


def build_asset_payloads(env: dict[str, str]) -> dict[str, str]:
    payloads: dict[str, str] = {}
    for source_path in sorted(SRC_DIR.rglob("*.js")):
        rel = source_path.relative_to(SRC_DIR).as_posix()
        payloads[rel] = source_path.read_text(encoding="utf-8")
    payloads["app.css"] = compose_stylesheet()
    payloads["config.js"] = build_config(env)
    return payloads


def _replace_reference(
    match: re.Match[str],
    *,
    current_rel: str,
    fingerprint_map: dict[str, str],
) -> str:
    quote = match.group("quote")
    raw_reference = match.group("path")
    normalized_reference = raw_reference.split("?", 1)[0]

    if normalized_reference.startswith(("http://", "https://", "data:", "#")):
        return match.group(0)

    current_dir = posixpath.dirname(current_rel)
    if normalized_reference.startswith("/"):
        source_target = posixpath.normpath(normalized_reference.lstrip("/"))
    else:
        source_target = posixpath.normpath(posixpath.join(current_dir, normalized_reference))

    fingerprinted_target = fingerprint_map.get(source_target)
    if not fingerprinted_target:
        return match.group(0)

    if normalized_reference.startswith("/"):
        next_reference = f"/{fingerprinted_target}"
    else:
        base_dir = current_dir or "."
        next_reference = posixpath.relpath(fingerprinted_target, start=base_dir)
        if not next_reference.startswith((".", "..")):
            next_reference = f"./{next_reference}"

    return f"{quote}{next_reference}{quote}"


def build_fingerprint_map(asset_payloads: dict[str, str], build_version: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for rel in sorted(asset_payloads):
        rel_path = Path(rel)
        if rel_path.suffix.lower() not in FINGERPRINT_EXTENSIONS:
            continue
        digest = _sha256_short_bytes(asset_payloads[rel].encode("utf-8"))
        fingerprinted_name = f"{rel_path.stem}.{build_version}.{digest}{rel_path.suffix}"
        if rel_path.parent == Path("."):
            fingerprinted_rel = fingerprinted_name
        else:
            fingerprinted_rel = (rel_path.parent / fingerprinted_name).as_posix()
        mapping[rel] = fingerprinted_rel
    return mapping


def rewrite_payload_references(
    asset_payloads: dict[str, str],
    fingerprint_map: dict[str, str],
) -> dict[str, str]:
    rewritten: dict[str, str] = {}
    pattern = re.compile(
        r'(?P<quote>["\'])(?P<path>[^"\']+\.(?:' + "|".join(SOURCE_REFERENCE_EXTENSIONS) + r'))(?:\?v=[^"\']*)?(?P=quote)'
    )
    for rel, source in sorted(asset_payloads.items()):
        if Path(rel).suffix.lower() != ".js":
            rewritten[rel] = source
            continue
        rewritten[rel] = pattern.sub(
            lambda match: _replace_reference(
                match,
                current_rel=rel,
                fingerprint_map=fingerprint_map,
            ),
            source,
        )
    return rewritten


def write_fingerprinted_assets(
    target_dir: Path,
    asset_payloads: dict[str, str],
    fingerprint_map: dict[str, str],
) -> None:
    for source_rel, content in sorted(asset_payloads.items()):
        fingerprinted_rel = fingerprint_map[source_rel]
        fingerprinted_path = target_dir / fingerprinted_rel
        fingerprinted_path.parent.mkdir(parents=True, exist_ok=True)
        fingerprinted_path.write_text(content, encoding="utf-8")


def rewrite_html_references(target_dir: Path, fingerprint_map: dict[str, str]) -> None:
    pattern = re.compile(
        r'(?P<quote>["\'])(?P<path>[^"\']+\.(?:' + "|".join(SOURCE_REFERENCE_EXTENSIONS) + r'))(?:\?v=[^"\']*)?(?P=quote)'
    )
    for html_path in sorted(target_dir.rglob("*.html")):
        rel = html_path.relative_to(target_dir).as_posix()
        source = html_path.read_text(encoding="utf-8")
        updated = pattern.sub(
            lambda match: _replace_reference(
                match,
                current_rel=rel,
                fingerprint_map=fingerprint_map,
            ),
            source,
        )
        if updated != source:
            html_path.write_text(updated, encoding="utf-8")


def write_asset_manifest(target_dir: Path, *, version: str, fingerprint_map: dict[str, str]) -> None:
    entrypoint_files = {
        "app.js": fingerprint_map.get("app.js", ""),
        "app.css": fingerprint_map.get("app.css", ""),
        "config.js": fingerprint_map.get("config.js", ""),
    }
    manifest_payload = {
        "schema": "frontend_asset_manifest_v1",
        "build_version_utc": version,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "entrypoints": entrypoint_files,
        "fingerprinted_assets": fingerprint_map,
    }
    (target_dir / "asset-manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def compose_stylesheet() -> str:
    legacy_styles = BACKEND_STYLES_PATH.read_text(encoding="utf-8")
    shared_ui_styles = "\n\n".join(path.read_text(encoding="utf-8").rstrip() for path in SHARED_UI_STYLES)
    frontend_overrides = (SRC_DIR / "app.css").read_text(encoding="utf-8")
    return (
        legacy_styles.rstrip()
        + "\n\n/* Frontend shared/ui foundation. */\n"
        + shared_ui_styles
        + "\n\n/* Frontend desacoplado: pequenos ajustes e compatibilidades. */\n"
        + frontend_overrides.lstrip()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", help="Arquivo .env para injetar configuracao do frontend.")
    parser.add_argument("--output-dir", help="Diretorio de saida do build. O padrao continua sendo ./dist.")
    args = parser.parse_args()

    env = dict(os.environ)
    if args.env_file:
        env_path = Path(args.env_file)
        if not env_path.is_absolute():
            env_path = ROOT / env_path
            if not env_path.exists():
                repo_relative_env_path = ROOT.parent / args.env_file
                if repo_relative_env_path.exists():
                    env_path = repo_relative_env_path
        env.update(load_env_file(env_path))

    output_dir = resolve_output_dir(args.output_dir)
    copy_static_tree(output_dir)
    build_version = build_asset_version()
    asset_payloads = build_asset_payloads(env)
    fingerprint_map = build_fingerprint_map(asset_payloads, build_version)
    rewritten_payloads = rewrite_payload_references(asset_payloads, fingerprint_map)
    write_fingerprinted_assets(output_dir, rewritten_payloads, fingerprint_map)
    rewrite_html_references(output_dir, fingerprint_map)
    write_asset_manifest(output_dir, version=build_version, fingerprint_map=fingerprint_map)
    print(f"Frontend build generated at: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
