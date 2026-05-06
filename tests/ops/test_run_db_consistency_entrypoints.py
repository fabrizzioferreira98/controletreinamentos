import json
import subprocess
import sys
from pathlib import Path

from backend.tools.manual_unsafe.run_db_repair import _forward_args
from ops.scripts.database.run_db_consistency import REPAIR_ACK_TOKEN


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_maintenance_run_db_consistency_blocks_repair_flag():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "backend" / "tools" / "maintenance" / "run_db_consistency.py"),
            "--repair",
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["ok"] is False
    assert payload["error"] == "repair_removed_from_canonical_maintenance_path"
    assert payload["redirect_command"] == "backend/tools/manual_unsafe/run_db_repair.py"


def test_manual_run_db_repair_wrapper_injects_manual_ack_once():
    forwarded = _forward_args(["--json", "--repair", "--repair-ack", "ignored", "--foo"])

    assert forwarded[:3] == ["--repair", "--repair-ack", REPAIR_ACK_TOKEN]
    assert forwarded.count("--repair") == 1
    assert forwarded.count("--repair-ack") == 1
    assert "--json" in forwarded
    assert "--foo" in forwarded
