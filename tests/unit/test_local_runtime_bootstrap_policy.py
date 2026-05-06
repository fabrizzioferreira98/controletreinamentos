from __future__ import annotations

from pathlib import Path

from backend.src.controle_treinamentos import create_app


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_env_example_keeps_frontend_redirects_disabled_by_default(monkeypatch):
    for key, value in _load_env_example().items():
        monkeypatch.setenv(key, value)

    app = create_app()
    client = app.test_client()

    login_response = client.get("/login", base_url="http://127.0.0.1:5000", follow_redirects=False)
    root_response = client.get("/", base_url="http://127.0.0.1:5000", follow_redirects=False)

    assert login_response.status_code == 200
    assert login_response.content_type.startswith("text/html")
    assert root_response.status_code == 302
    assert root_response.headers["Location"].endswith("/login")


def test_seed_bootstrap_entrypoint_is_documented_as_maintenance_flow():
    source = (REPO_ROOT / "backend" / "tools" / "maintenance" / "bootstrap_seed_data.py").read_text(encoding="utf-8")
    canonical_commands = (REPO_ROOT / "docs" / "operations" / "canonical-commands.md").read_text(encoding="utf-8")
    local_runtime = (REPO_ROOT / "docs" / "operations" / "LOCAL_RUNTIME.md").read_text(encoding="utf-8")

    assert "execute_seed_bootstrap" in source
    assert "bootstrap_seed_data.py" in canonical_commands
    assert "bootstrap_seed_data.py" in local_runtime
