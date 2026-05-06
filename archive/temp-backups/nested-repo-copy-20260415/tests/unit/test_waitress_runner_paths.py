from pathlib import Path

from ops.windows.scripts import run_waitress_server


def test_waitress_runner_uses_repo_root_on_sys_path():
    expected_repo_root = Path(__file__).resolve().parents[2]
    assert run_waitress_server.REPO_ROOT == expected_repo_root
