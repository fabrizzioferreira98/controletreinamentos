from __future__ import annotations

import argparse
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
DIST_DIR = ROOT / "dist"
BACKEND_STATIC_DIR = ROOT.parent / "src" / "app" / "static"
BACKEND_STYLES_PATH = BACKEND_STATIC_DIR / "styles.css"


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
    shutil.copytree(SRC_DIR, target_dir)


def build_asset_version() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def stamp_dist_assets(target_dir: Path, version: str) -> None:
    pattern = re.compile(r"\?v=[0-9A-Za-z._-]+")
    for path in list(target_dir.rglob("*.html")) + list(target_dir.rglob("*.js")):
        raw = path.read_text(encoding="utf-8")
        updated = pattern.sub(f"?v={version}", raw)
        if updated != raw:
            path.write_text(updated, encoding="utf-8")


def compose_stylesheet() -> str:
    legacy_styles = BACKEND_STYLES_PATH.read_text(encoding="utf-8")
    frontend_overrides = (SRC_DIR / "app.css").read_text(encoding="utf-8")
    return (
        legacy_styles.rstrip()
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
        env.update(load_env_file(env_path))

    output_dir = resolve_output_dir(args.output_dir)
    copy_static_tree(output_dir)
    (output_dir / "app.css").write_text(compose_stylesheet(), encoding="utf-8")
    (output_dir / "config.js").write_text(build_config(env), encoding="utf-8")
    stamp_dist_assets(output_dir, build_asset_version())
    print(f"Frontend build generated at: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
