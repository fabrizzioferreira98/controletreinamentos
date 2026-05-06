import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_cleanup_execute_requires_explicit_confirmation_before_db_connection():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ops" / "scripts" / "database" / "cleanup_operational_data.py"),
            "--database-url",
            "postgresql://admin:secret@db.example:5432/treinamentos",
            "--preserve-login",
            "admin",
            "--execute",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["success"] is False
    assert payload["error"] == "cleanup_confirmation_required"
    assert payload["classification"] == "manual_unsafe"
    assert payload["required_confirmation"] == "cleanup-operational-data:admin"
    assert payload["target"] == {
        "scheme": "postgresql",
        "host": "db.example",
        "port": 5432,
        "database": "treinamentos",
        "user": "admin",
    }


def test_removed_schema_execute_requires_policy_backup_and_confirmation_before_db_connection():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ops" / "scripts" / "database" / "remove_painel_tv_produtividade_schema.py"),
            "--database-url",
            "postgresql://admin:secret@db.example:5432/treinamentos",
            "--execute",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["success"] is False
    assert payload["error"] == "schema_removal_policy_required"
    assert payload["classification"] == "manual_unsafe"
    assert payload["required_retention_policy"] == "destroy-after-backup"
    assert payload["required_confirmation"] == "remove-painel-tv-produtividade-schema:treinamentos"
    assert payload["missing"] == ["retention_policy", "backup_reference", "confirm_schema_removal"]
