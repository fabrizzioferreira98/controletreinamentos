import json
import subprocess
import sys
from pathlib import Path

from ops.scripts.database.sync_tripulantes_snapshot import _load_env_file, _sanitize_database_target


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_load_env_file_ignores_comments_and_blank_lines(tmp_path: Path):
    env_file = tmp_path / "sample.env"
    env_file.write_text(
        "\n".join(
            [
                "# comentario",
                "",
                "DATABASE_URL=postgresql://user:secret@127.0.0.1:5432/dbname",
                "APP_ENV=homolog",
            ]
        ),
        encoding="utf-8",
    )

    env = _load_env_file(env_file)

    assert env["DATABASE_URL"].startswith("postgresql://user:secret@127.0.0.1:5432/")
    assert env["APP_ENV"] == "homolog"
    assert len(env) == 2


def test_sanitize_database_target_hides_password():
    payload = _sanitize_database_target("postgresql://user:supersecret@127.0.0.1:5432/ct_hml")

    assert payload == {
        "host": "127.0.0.1",
        "port": 5432,
        "database": "ct_hml",
        "user": "user",
    }


def test_sync_apply_requires_explicit_residual_ack():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ops" / "scripts" / "database" / "sync_tripulantes_snapshot.py"),
            "--source-env-file",
            "source.env",
            "--target-env-file",
            "target.env",
            "--apply",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert result.returncode == 1
    assert payload["ok"] is False
    assert payload["classification"] == "compat_residual"
    assert payload["error"] == "compat_apply_ack_required"
    assert payload["required_ack"] == "sync-tripulantes-snapshot-compat-residual"
