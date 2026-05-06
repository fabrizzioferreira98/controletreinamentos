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


def test_http_boot_fallback_response_is_sanitized():
    root = Path(__file__).resolve().parents[1]
    module = _load_module("api_index_boot_fallback_test", root / "api" / "index.py")
    app = module._make_fallback_app(error_ref="ref-abc")

    response = app.test_client().get("/qualquer-rota")
    payload = response.get_json()

    assert response.status_code == 500
    assert payload["error"] == "BOOT_FAILURE"
    assert payload["error_ref"] == "ref-abc"
    assert "traceback" not in payload
    assert "python_version" not in payload
    assert "platform" not in payload


def test_cron_boot_failure_response_is_sanitized():
    root = Path(__file__).resolve().parents[1]
    module = _load_module("api_cron_boot_fallback_test", root / "api" / "cron.py")

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        with module.app.app_context():
            response, status_code = module._boot_failure_response(exc)

    payload = response.get_json()
    assert status_code == 500
    assert payload["error"] == "BOOT_FAILURE_CRON"
    assert "error_ref" in payload and payload["error_ref"]
    assert "traceback" not in payload
