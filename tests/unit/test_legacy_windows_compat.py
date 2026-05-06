from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_legacy_windows_compat_entrypoints_exist():
    expected_paths = [
        "scripts/windows/Invoke-AppService.ps1",
        "scripts/windows/Invoke-OperationalPython.ps1",
        "scripts/backup/run_backups.py",
        "scripts/database/run_db_consistency.py",
        "scripts/jobs/run_jobs_worker.py",
        "scripts/jobs/run_notifications.py",
    ]

    missing = [path for path in expected_paths if not (REPO_ROOT / path).exists()]
    assert not missing, f"Missing legacy compatibility shims: {missing}"
