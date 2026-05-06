from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from backend.src.controle_treinamentos.core.workspace_paths import evidence_root

def run(cmd: list[str], *, required: bool = True, env: dict | None = None) -> bool:
    print(f"\n$ {' '.join(cmd)}")
    subprocess_env = os.environ.copy()
    if env:
        subprocess_env.update({str(key): str(value) for key, value in env.items()})
    result = subprocess.run(cmd, env=subprocess_env)
    if result.returncode != 0 and required:
        print(f"FAIL: comando retornou {result.returncode}")
        return False
    return result.returncode == 0


def run_capture(cmd: list[str], *, env: dict | None = None) -> tuple[bool, str]:
    print(f"\n$ {' '.join(cmd)}")
    subprocess_env = os.environ.copy()
    if env:
        subprocess_env.update({str(key): str(value) for key, value in env.items()})
    result = subprocess.run(cmd, capture_output=True, text=True, env=subprocess_env)
    output = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    if output:
        print(output)
    ok = result.returncode == 0
    if not ok:
        print(f"FAIL: comando retornou {result.returncode}")
    return ok, output


def _require_e2e_env() -> tuple[bool, list[str]]:
    required = ["E2E_DATABASE_URL", "E2E_LOGIN", "E2E_PASSWORD"]
    missing = [name for name in required if not (os.getenv(name, "") or "").strip()]
    return len(missing) == 0, missing


def _extract_passed_count(pytest_output: str) -> int:
    # Examples: "3 passed in ..." | "1 passed, 2 skipped in ..."
    match = re.search(r"(?P<count>\d+)\s+passed", pytest_output)
    if not match:
        return 0
    try:
        return int(match.group("count"))
    except ValueError:
        return 0


def _require_loadtest_env() -> tuple[bool, list[str]]:
    required = ["E2E_LOGIN", "E2E_PASSWORD"]
    missing = [name for name in required if not (os.getenv(name, "") or "").strip()]
    return len(missing) == 0, missing


def _load_manifest_metadata(path: str) -> tuple[str, str]:
    manifest_path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return "", ""
    release_id = str(payload.get("release_id", "") or "").strip()
    environment = str(payload.get("environment", "") or "").strip().lower()
    return release_id, environment


def _resolve_secret(*, cli_value: str, file_path: str, env_name: str, label: str) -> str:
    if (cli_value or "").strip():
        print(f"WARN: {label} via CLI pode vazar no histórico. Prefira arquivo/env.", file=sys.stderr)
        return (cli_value or "").strip()
    if (file_path or "").strip():
        try:
            return (Path(file_path).expanduser().read_text(encoding="utf-8") or "").strip()
        except OSError as exc:
            print(f"FAIL: não foi possível ler {label} em arquivo: {exc}")
            return ""
    key = (env_name or "").strip()
    if not key:
        return ""
    return (os.getenv(key, "") or "").strip()


def _git_worktree_is_clean(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    return not bool((result.stdout or "").strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate de release pré-produção")
    parser.add_argument(
        "--gate-profile",
        choices=("strict", "basic"),
        default="strict",
        help="Perfil do gate. strict endurece requisitos e bloqueia bypasses (padrão).",
    )
    parser.add_argument("--base-url", default="", help="Executa smoke HTTP se informado")
    parser.add_argument("--metrics-token", default="", help="Token opcional para smoke de métricas (evite CLI).")
    parser.add_argument(
        "--metrics-token-file",
        default="",
        help="Arquivo contendo METRICS_TOKEN para smoke.",
    )
    parser.add_argument(
        "--metrics-token-env",
        default="METRICS_TOKEN",
        help="Variável de ambiente com token de métricas (padrão: METRICS_TOKEN).",
    )
    parser.add_argument("--with-e2e", action="store_true", help="Executa também marcador e2e")
    parser.add_argument(
        "--e2e-rounds",
        type=int,
        default=2,
        help="Quantidade de rodadas E2E obrigatórias quando --with-e2e estiver ativo (padrão: 2).",
    )
    parser.add_argument(
        "--min-e2e-passed",
        type=int,
        default=4,
        help="Quantidade mínima de testes E2E com status passed por rodada.",
    )
    parser.add_argument(
        "--require-operational-evidence",
        action="store_true",
        help="Exige manifest de evidências operacionais com todos os checks obrigatórios em PASS.",
    )
    parser.add_argument(
        "--evidence-manifest",
        default="",
        help="Caminho para JSON de evidências operacionais (usado com --require-operational-evidence).",
    )
    parser.add_argument(
        "--evidence-max-age-hours",
        type=int,
        default=24,
        help="Idade máxima permitida para o manifest operacional.",
    )
    parser.add_argument(
        "--evidence-signing-key-env",
        default="RELEASE_EVIDENCE_SIGNING_KEY",
        help="Variável de ambiente da chave HMAC de assinatura do manifest.",
    )
    parser.add_argument(
        "--require-regression-checklist",
        action="store_true",
        help="Exige checklist de regressão preenchido e validado.",
    )
    parser.add_argument(
        "--regression-checklist",
        default=str(Path("docs") / "operations" / "REGRESSION_AUDIT_CHECKLIST.md"),
        help="Caminho para checklist de regressão (markdown).",
    )
    parser.add_argument(
        "--checklist-allowed-results",
        default="GO,GO CONDICIONAL",
        help="Resultados aceitos no checklist (campo Resultado), separados por vírgula.",
    )
    parser.add_argument(
        "--require-db-consistency",
        action="store_true",
        help="Exige validação de consistência do banco via ops/scripts/database/run_db_consistency.py.",
    )
    parser.add_argument(
        "--allow-dirty-worktree",
        action="store_true",
        help="Permite executar gate mesmo com worktree suja (não recomendado).",
    )
    parser.add_argument(
        "--allow-cli-secrets",
        action="store_true",
        help="Permite uso explícito de segredo via CLI (--metrics-token). Use apenas em cenários controlados.",
    )
    parser.add_argument(
        "--db-consistency-repair",
        action="store_true",
        help="Executa consistência com --repair (uso controlado em homologação).",
    )
    parser.add_argument(
        "--require-mobile-session-matrix",
        action="store_true",
        help="Exige matriz E2E de sessão/mobile (multi-aba, mobile, sessão expirada html/json).",
    )
    parser.add_argument(
        "--require-authenticated-load-matrix",
        action="store_true",
        help="Executa matriz de carga autenticada 20w/300s, 30w/300s e soak 30w/1800s.",
    )
    parser.add_argument(
        "--load-matrix-repeats",
        type=int,
        default=1,
        help="Quantidade de repetições por cenário na matriz de carga autenticada.",
    )
    args = parser.parse_args()

    strict_profile = (args.gate_profile or "strict").strip().lower() == "strict"
    if strict_profile:
        args.with_e2e = True
        args.require_db_consistency = True
        args.require_operational_evidence = True
        args.require_regression_checklist = True
        args.e2e_rounds = max(2, int(args.e2e_rounds))
        args.min_e2e_passed = max(10, int(args.min_e2e_passed))
        args.require_mobile_session_matrix = True
        args.require_authenticated_load_matrix = True

    root = Path(__file__).resolve().parents[2]
    py = str(root / ".venv" / "bin" / "python")
    if not Path(py).exists():
        py = sys.executable

    ok = True
    if strict_profile and args.allow_dirty_worktree:
        print("FAIL: --allow-dirty-worktree é proibido no perfil strict.")
        ok = False

    if strict_profile and args.allow_cli_secrets:
        print("FAIL: --allow-cli-secrets é proibido no perfil strict.")
        ok = False

    if not args.allow_dirty_worktree and not _git_worktree_is_clean(root):
        print("FAIL: worktree git não está limpa. Faça commit/stash das mudanças antes do release gate.")
        ok = False

    if args.metrics_token and not args.allow_cli_secrets:
        print("FAIL: --metrics-token via CLI bloqueado por padrão de segurança. Use --metrics-token-file/env.")
        ok = False

    ok &= run([py, "-m", "pytest", "-q"])

    if args.with_e2e:
        env_ok, missing_env = _require_e2e_env()
        if not env_ok:
            print(f"FAIL: --with-e2e solicitado sem variáveis obrigatórias: {', '.join(missing_env)}")
            ok = False
        else:
            rounds = max(1, int(args.e2e_rounds))
            min_e2e_passed = max(1, int(args.min_e2e_passed))
            for round_idx in range(1, rounds + 1):
                print(f"\n=== E2E Round {round_idx}/{rounds} ===")
                e2e_ok, e2e_output = run_capture([py, "-m", "pytest", "-q", "-m", "e2e", "-rs"])
                ok &= e2e_ok
                passed_count = _extract_passed_count(e2e_output)
                if passed_count < min_e2e_passed:
                    print(
                        f"FAIL: E2E round {round_idx} executou apenas {passed_count} passed "
                        f"(mínimo exigido: {min_e2e_passed})."
                    )
                    ok = False

    if args.require_mobile_session_matrix:
        mobile_session_cmd = [
            py,
            "-m",
            "pytest",
            "-q",
            "tests/e2e/test_critical_journeys.py::test_e2e_multiple_tabs_keep_same_authenticated_session",
            "tests/e2e/test_critical_journeys.py::test_e2e_mobile_user_agent_authenticated_flow",
            "tests/e2e/test_critical_journeys.py::test_e2e_session_expired_redirects_to_login",
            "tests/e2e/test_critical_journeys.py::test_e2e_session_expired_on_programmatic_route_returns_json_401",
            "-rs",
        ]
        mobile_ok, _ = run_capture(mobile_session_cmd)
        ok &= mobile_ok

    if args.require_authenticated_load_matrix:
        load_env_ok, load_missing = _require_loadtest_env()
        if not load_env_ok:
            print(
                "FAIL: --require-authenticated-load-matrix exige variáveis: "
                + ", ".join(load_missing)
            )
            ok = False
        elif not (args.base_url or "").strip():
            print("FAIL: --require-authenticated-load-matrix exige --base-url.")
            ok = False
        else:
            load_cmd = [
                py,
                str(root / "scripts" / "perf" / "run_authenticated_matrix.py"),
                "--base-url",
                (args.base_url or "").strip(),
                "--login",
                (os.getenv("E2E_LOGIN", "") or "").strip(),
                "--password-env",
                "E2E_PASSWORD",
                "--repeats",
                str(max(1, int(args.load_matrix_repeats))),
                "--include-soak-30w-1800s",
                "--output",
                str(evidence_root() / "perf" / "load_auth_matrix.json"),
            ]
            load_ok, _ = run_capture(load_cmd)
            ok &= load_ok

    ui_baseline_cmd = [
        py,
        str(root / "scripts" / "qa" / "validate_ui_baseline.py"),
        "--baseline",
        str(root / "docs" / "operations" / "ui_baseline_hashes.json"),
    ]
    ui_baseline_ok, _ = run_capture(ui_baseline_cmd)
    ok &= ui_baseline_ok

    if args.require_db_consistency:
        database_url = (os.getenv("DATABASE_URL", "") or "").strip()
        if not database_url:
            print("FAIL: --require-db-consistency exige DATABASE_URL configurada.")
            ok = False
        else:
            db_cmd = [
                py,
                str(root / "scripts" / "database" / "run_db_consistency.py"),
                "--json",
            ]
            if args.db_consistency_repair:
                db_cmd.insert(-1, "--repair")
            db_ok, _ = run_capture(db_cmd)
            ok &= db_ok

    if strict_profile and not (args.base_url or "").strip():
        print("FAIL: perfil strict exige --base-url para smoke pós-deploy no alvo do release.")
        ok = False

    metrics_token = _resolve_secret(
        cli_value=args.metrics_token,
        file_path=args.metrics_token_file,
        env_name=args.metrics_token_env,
        label="metrics token",
    )

    if args.base_url:
        smoke_cmd = [py, str(root / "scripts" / "smoke" / "post_deploy_smoke.py"), "--base-url", args.base_url]
        smoke_env = {}
        if metrics_token:
            smoke_env["RELEASE_GATE_METRICS_TOKEN"] = metrics_token
            smoke_cmd.extend(["--metrics-token-env", "RELEASE_GATE_METRICS_TOKEN"])
        ok &= run(smoke_cmd, env=smoke_env or None)

    if args.require_operational_evidence:
        manifest = (args.evidence_manifest or "").strip()
        if not manifest:
            print("FAIL: --require-operational-evidence exige --evidence-manifest.")
            ok = False
        else:
            signing_env = (args.evidence_signing_key_env or "").strip() or "RELEASE_EVIDENCE_SIGNING_KEY"
            if strict_profile and not (os.getenv(signing_env, "") or "").strip():
                print(f"FAIL: perfil strict exige {signing_env} configurada para validar assinatura HMAC.")
                ok = False
            evidence_cmd = [
                py,
                str(root / "scripts" / "release" / "validate_operational_evidence.py"),
                "--manifest",
                manifest,
                "--max-age-hours",
                str(max(1, int(args.evidence_max_age_hours))),
                "--require-hashes",
                "--require-signature",
                "--signing-key-env",
                signing_env,
                "--require-rollback-runtime-ids",
                "--require-alert-ack",
            ]
            evidence_ok, _ = run_capture(evidence_cmd)
            ok &= evidence_ok

    if args.require_regression_checklist or args.require_operational_evidence:
        checklist_path = (args.regression_checklist or "").strip()
        if not checklist_path:
            print("FAIL: checklist de regressão obrigatório sem caminho configurado.")
            ok = False
        else:
            expected_release_id = ""
            expected_environment = ""
            manifest = (args.evidence_manifest or "").strip()
            if manifest:
                expected_release_id, expected_environment = _load_manifest_metadata(manifest)
            checklist_cmd = [
                py,
                str(root / "scripts" / "release" / "validate_regression_checklist.py"),
                "--checklist",
                checklist_path,
                "--allowed-results",
                (args.checklist_allowed_results or "").strip() or "GO,GO CONDICIONAL",
                "--skip-head-commit-check",
            ]
            if expected_release_id:
                checklist_cmd.extend(["--expected-release-id", expected_release_id])
            if expected_environment:
                checklist_cmd.extend(["--expected-environment", expected_environment])
            checklist_ok, _ = run_capture(checklist_cmd)
            ok &= checklist_ok

    print("\nRELEASE GATE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
