from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, relative_path: str):
    target = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, target)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_e2e_homolog_rounds_updates_manifest_and_checklist(monkeypatch, tmp_path):
    module = _load_module(
        "run_e2e_homolog_rounds_test",
        "ops/scripts/release/run_e2e_homolog_rounds.py",
    )

    manifest_path = tmp_path / "release_evidence_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-20T12:00:00Z",
                "environment": "homolog",
                "release_id": "release_20260420_120000",
                "commit_sha": "workspace-without-git",
                "checks": {},
            }
        ),
        encoding="utf-8",
    )
    checklist_path = tmp_path / "regression_checklist.md"
    checklist_path.write_text(
        "# Checklist de Auditoria de Regressao\n\n## Evidencias anexadas\n- E2E: <placeholder>\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "e2e"
    summary_path = out_dir / "e2e_homolog_summary.json"

    payloads = [
        {
            "success": True,
            "base_url": "http://127.0.0.1:8102",
            "round_index": 1,
            "started_at": "2026-04-20T12:00:00Z",
            "finished_at": "2026-04-20T12:01:00Z",
            "login": "qa_release_e2e",
            "passed_steps": 12,
            "steps": [{"name": "api_login_success", "ok": True, "duration_ms": 120, "detail": "ok"}],
        },
        {
            "success": True,
            "base_url": "http://127.0.0.1:8102",
            "round_index": 2,
            "started_at": "2026-04-20T12:02:00Z",
            "finished_at": "2026-04-20T12:03:00Z",
            "login": "qa_release_e2e",
            "passed_steps": 12,
            "steps": [{"name": "api_logout", "ok": True, "duration_ms": 80, "detail": "ok"}],
        },
    ]

    def fake_run_round(*args, **kwargs):
        return True, payloads.pop(0)

    monkeypatch.setattr(module, "_run_round", fake_run_round)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_e2e_homolog_rounds.py",
            "--base-url",
            "http://127.0.0.1:8102",
            "--rounds",
            "2",
            "--min-passed",
            "10",
            "--out-dir",
            str(out_dir),
            "--summary-json",
            str(summary_path),
            "--manifest",
            str(manifest_path),
            "--regression-checklist",
            str(checklist_path),
        ],
    )

    assert module.main() == 0

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest_payload["checks"]["e2e_homolog"]["artifacts"]
    assert len(artifacts) == 3
    assert Path(artifacts[0]).name == "e2e_run_1.txt"
    assert Path(artifacts[1]).name == "e2e_run_2.txt"
    assert Path(artifacts[2]).name == "e2e_homolog_summary.json"
    assert "12 passed in 0.00s" in (out_dir / "e2e_run_1.txt").read_text(encoding="utf-8")
    assert str(out_dir / "e2e_run_1.txt") in checklist_path.read_text(encoding="utf-8")


def test_release_gate_uses_package_directory_for_e2e_when_manifest_is_provided(monkeypatch, tmp_path):
    module = _load_module(
        "release_gate_test",
        "ops/scripts/release/release_gate.py",
    )

    package_dir = tmp_path / "release_20260420_130000"
    package_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = package_dir / "release_evidence_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-20T13:00:00Z",
                "environment": "homolog",
                "release_id": "release_20260420_130000",
                "commit_sha": "workspace-without-git",
                "checks": {},
            }
        ),
        encoding="utf-8",
    )
    checklist_path = package_dir / "regression_checklist.md"
    checklist_path.write_text("# checklist\n", encoding="utf-8")

    captured: list[list[str]] = []

    monkeypatch.setattr(module, "_git_worktree_is_clean", lambda root: True)
    monkeypatch.setattr(module, "_require_e2e_env", lambda: (True, []))
    monkeypatch.setattr(module, "run", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "_resolve_secret", lambda **kwargs: "")

    def fake_run_capture(cmd, **kwargs):
        captured.append(cmd)
        return True, ""

    monkeypatch.setattr(module, "run_capture", fake_run_capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_gate.py",
            "--gate-profile",
            "basic",
            "--with-e2e",
            "--base-url",
            "http://127.0.0.1:8102",
            "--evidence-manifest",
            str(manifest_path),
            "--regression-checklist",
            str(checklist_path),
        ],
    )

    assert module.main() == 0

    e2e_cmd = next(cmd for cmd in captured if any("run_e2e_homolog_rounds.py" in part for part in cmd))
    out_dir = Path(e2e_cmd[e2e_cmd.index("--out-dir") + 1])
    summary_path = Path(e2e_cmd[e2e_cmd.index("--summary-json") + 1])
    manifest_arg = Path(e2e_cmd[e2e_cmd.index("--manifest") + 1])
    checklist_arg = Path(e2e_cmd[e2e_cmd.index("--regression-checklist") + 1])

    assert out_dir == package_dir / "e2e"
    assert summary_path == package_dir / "e2e" / "e2e_homolog_summary.json"
    assert manifest_arg == manifest_path
    assert checklist_arg == checklist_path


def test_run_authenticated_release_matrix_updates_manifest_and_checklist(monkeypatch, tmp_path):
    module = _load_module(
        "run_authenticated_release_matrix_test",
        "ops/scripts/release/run_authenticated_release_matrix.py",
    )

    manifest_path = tmp_path / "release_evidence_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-20T14:00:00Z",
                "environment": "homolog",
                "release_id": "release_20260420_140000",
                "commit_sha": "workspace-without-git",
                "checks": {},
            }
        ),
        encoding="utf-8",
    )
    checklist_path = tmp_path / "regression_checklist.md"
    checklist_path.write_text(
        "# Checklist de Auditoria de Regressao\n\n## Evidencias anexadas\n- Carga autenticada: <placeholder>\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "perf"
    summary_path = out_dir / "load_auth_matrix.json"

    def fake_run_matrix(py_exec, script, cmd_args):
        assert "--output" in cmd_args
        assert str(summary_path) == cmd_args[cmd_args.index("--output") + 1]
        return {
            "success": True,
            "criteria": {
                "availability_min_percent": 99.0,
                "p95_worst_max_ms": 1200.0,
            },
            "_command": "python ops/scripts/perf/run_authenticated_matrix.py --base-url http://127.0.0.1:8102",
            "matrix": [
                {
                    "scenario": "20w/300s",
                    "summary": {
                        "pass": True,
                        "workers": 20,
                        "seconds": 300,
                        "availability_percent": {"worst": 99.91},
                        "percent_5xx": {"worst": 0.0},
                        "latency_ms": {
                            "p50_median": 120.0,
                            "p95_worst": 420.0,
                            "p99_median": 650.0,
                        },
                    },
                    "runs": [
                        {
                            "success": True,
                            "authenticated": True,
                            "workers": 20,
                            "seconds": 300,
                            "requests": 7200,
                            "auth_failures": 0,
                            "permission_failures": 0,
                            "non_http_errors": 0,
                            "login_failures": [],
                            "latency_ms": {"avg": 180.0},
                            "transport_errors": {"recovered_total": 1},
                            "preflight": {"auth_failures": [], "permission_failures": []},
                        }
                    ],
                },
                {
                    "scenario": "30w/300s",
                    "summary": {
                        "pass": True,
                        "workers": 30,
                        "seconds": 300,
                        "availability_percent": {"worst": 99.84},
                        "percent_5xx": {"worst": 0.0},
                        "latency_ms": {
                            "p50_median": 150.0,
                            "p95_worst": 560.0,
                            "p99_median": 810.0,
                        },
                    },
                    "runs": [
                        {
                            "success": True,
                            "authenticated": True,
                            "workers": 30,
                            "seconds": 300,
                            "requests": 9800,
                            "auth_failures": 0,
                            "permission_failures": 0,
                            "non_http_errors": 0,
                            "login_failures": [],
                            "latency_ms": {"avg": 230.0},
                            "transport_errors": {"recovered_total": 2},
                            "preflight": {"auth_failures": [], "permission_failures": []},
                        }
                    ],
                },
            ],
        }

    monkeypatch.setattr(module, "_run_matrix", fake_run_matrix)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_authenticated_release_matrix.py",
            "--base-url",
            "http://127.0.0.1:8102",
            "--login",
            "qa_release_load",
            "--password-env",
            "E2E_PASSWORD",
            "--repeats",
            "1",
            "--out-dir",
            str(out_dir),
            "--summary-json",
            str(summary_path),
            "--manifest",
            str(manifest_path),
            "--regression-checklist",
            str(checklist_path),
        ],
    )

    assert module.main() == 0

    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["release_id"] == "release_20260420_140000"
    assert summary_payload["environment"] == "homolog"
    assert summary_payload["command"]

    load_20_path = out_dir / "load_auth_20w.json"
    load_30_path = out_dir / "load_auth_30w.json"
    load_20_payload = json.loads(load_20_path.read_text(encoding="utf-8"))
    load_30_payload = json.loads(load_30_path.read_text(encoding="utf-8"))
    assert load_20_payload["workers"] == 20
    assert load_20_payload["requests"] == 7200
    assert load_20_payload["authenticated"] is True
    assert load_20_payload["percent_5xx"] == 0.0
    assert load_30_payload["workers"] == 30
    assert load_30_payload["requests"] == 9800
    assert load_30_payload["authenticated"] is True
    assert load_30_payload["percent_5xx"] == 0.0

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts_20 = manifest_payload["checks"]["load_authenticated_20w"]["artifacts"]
    artifacts_30 = manifest_payload["checks"]["load_authenticated_30w"]["artifacts"]
    assert manifest_payload["checks"]["load_authenticated_20w"]["status"] == "PASS"
    assert manifest_payload["checks"]["load_authenticated_30w"]["status"] == "PASS"
    assert Path(artifacts_20[0]).name == "load_auth_20w.json"
    assert Path(artifacts_20[1]).name == "load_auth_matrix.json"
    assert Path(artifacts_30[0]).name == "load_auth_30w.json"
    assert Path(artifacts_30[1]).name == "load_auth_matrix.json"
    assert str(summary_path) in checklist_path.read_text(encoding="utf-8")


def test_release_gate_uses_package_directory_for_authenticated_load_when_manifest_is_provided(monkeypatch, tmp_path):
    module = _load_module(
        "release_gate_load_test",
        "ops/scripts/release/release_gate.py",
    )

    package_dir = tmp_path / "release_20260420_150000"
    package_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = package_dir / "release_evidence_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-20T15:00:00Z",
                "environment": "homolog",
                "release_id": "release_20260420_150000",
                "commit_sha": "workspace-without-git",
                "checks": {},
            }
        ),
        encoding="utf-8",
    )
    checklist_path = package_dir / "regression_checklist.md"
    checklist_path.write_text("# checklist\n", encoding="utf-8")

    captured: list[list[str]] = []

    monkeypatch.setattr(module, "_git_worktree_is_clean", lambda root: True)
    monkeypatch.setattr(module, "_require_loadtest_env", lambda: (True, []))
    monkeypatch.setattr(module, "run", lambda *args, **kwargs: True)
    monkeypatch.setattr(module, "_resolve_secret", lambda **kwargs: "")
    monkeypatch.setenv("E2E_LOGIN", "qa_release_load")
    monkeypatch.setenv("E2E_PASSWORD", "not-used-in-test")

    def fake_run_capture(cmd, **kwargs):
        captured.append(cmd)
        return True, ""

    monkeypatch.setattr(module, "run_capture", fake_run_capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_gate.py",
            "--gate-profile",
            "basic",
            "--require-authenticated-load-matrix",
            "--base-url",
            "http://127.0.0.1:8102",
            "--evidence-manifest",
            str(manifest_path),
            "--regression-checklist",
            str(checklist_path),
        ],
    )

    assert module.main() == 0

    load_cmd = next(cmd for cmd in captured if any("run_authenticated_release_matrix.py" in part for part in cmd))
    out_dir = Path(load_cmd[load_cmd.index("--out-dir") + 1])
    summary_path = Path(load_cmd[load_cmd.index("--summary-json") + 1])
    manifest_arg = Path(load_cmd[load_cmd.index("--manifest") + 1])
    checklist_arg = Path(load_cmd[load_cmd.index("--regression-checklist") + 1])
    login_arg = load_cmd[load_cmd.index("--login") + 1]
    password_env_arg = load_cmd[load_cmd.index("--password-env") + 1]

    assert out_dir == package_dir / "perf"
    assert summary_path == package_dir / "perf" / "load_auth_matrix.json"
    assert manifest_arg == manifest_path
    assert checklist_arg == checklist_path
    assert login_arg == "qa_release_load"
    assert password_env_arg == "E2E_PASSWORD"


def test_harden_release_manifest_falls_back_when_workspace_has_no_git_repo():
    module = _load_module(
        "harden_release_manifest_test",
        "ops/scripts/release/harden_release_manifest.py",
    )

    assert module._git_head(REPO_ROOT) == "workspace-without-git"
