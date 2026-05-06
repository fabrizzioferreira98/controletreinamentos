from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_runtime_id_prefers_explicit_instance_header(tmp_path):
    root = Path(__file__).resolve().parents[1]
    module = _load_module("build_rollback_metadata_test", root / "scripts" / "release" / "build_rollback_metadata.py")

    header_file = tmp_path / "headers.txt"
    header_file.write_text(
        "Server: Caddy\r\n"
        "X-Release-Instance-Id: local-prod-20260402\r\n"
        "Date: Thu, 02 Apr 2026 22:00:00 GMT\r\n",
        encoding="utf-8",
    )

    assert module._extract_runtime_id(header_file) == "local-prod-20260402"


def test_extract_runtime_id_falls_back_to_stable_header_fingerprint(tmp_path):
    root = Path(__file__).resolve().parents[1]
    module = _load_module("build_rollback_metadata_hash_test", root / "scripts" / "release" / "build_rollback_metadata.py")

    header_a = tmp_path / "headers-a.txt"
    header_b = tmp_path / "headers-b.txt"
    header_a.write_text(
        "Server: Caddy\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Date: Thu, 02 Apr 2026 22:00:00 GMT\r\n"
        "X-Request-Id: req-a\r\n",
        encoding="utf-8",
    )
    header_b.write_text(
        "Content-Type: text/html; charset=utf-8\r\n"
        "X-Request-Id: req-b\r\n"
        "Date: Thu, 02 Apr 2026 22:00:05 GMT\r\n"
        "Server: Caddy\r\n",
        encoding="utf-8",
    )

    runtime_a = module._extract_runtime_id(header_a)
    runtime_b = module._extract_runtime_id(header_b)

    assert runtime_a is not None and runtime_a.startswith("runtime:")
    assert runtime_a == runtime_b
