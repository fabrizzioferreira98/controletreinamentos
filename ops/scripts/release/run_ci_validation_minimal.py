from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path
from tempfile import gettempdir


PIPELINE_TEST_TARGETS = (
    "tests/unit/test_db_migrations_schema_split.py",
    "tests/unit/test_local_runtime_bootstrap_policy.py",
    "tests/unit/test_environment_parity_policy.py",
    "tests/unit/test_ci_release_pipeline_policy.py",
    "tests/contract/test_frontend_compat_redirects.py",
)


def _python_executable(repo_root: Path) -> str:
    windows_py = repo_root / ".venv" / "Scripts" / "python.exe"
    posix_py = repo_root / ".venv" / "bin" / "python"
    if windows_py.exists():
        return str(windows_py)
    if posix_py.exists():
        return str(posix_py)
    return str(Path(sys.executable))


def _resolve_frontend_output(path_arg: str) -> Path:
    if (path_arg or "").strip():
        candidate = Path(path_arg).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (Path(gettempdir()) / "controle-treinamentos" / "ci-validation" / candidate).resolve()
    return (Path(gettempdir()) / "controle-treinamentos" / "ci-validation" / "frontend-dist").resolve()


def _run(cmd: list[str], *, cwd: Path) -> bool:
    print("$", " ".join(shlex.quote(part) for part in cmd))
    result = subprocess.run(cmd, cwd=str(cwd))
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa a validacao minima oficial de CI/build antes do gate de release.")
    parser.add_argument(
        "--frontend-output-dir",
        default="",
        help="Diretorio externo para o build do frontend. Se omitido, usa temp do sistema fora do checkout.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    py_exec = _python_executable(repo_root)
    frontend_output = _resolve_frontend_output(args.frontend_output_dir)

    frontend_build_cmd = [
        py_exec,
        str(repo_root / "frontend" / "scripts" / "build_frontend.py"),
        "--env-file",
        str(repo_root / "frontend" / ".env.example"),
        "--output-dir",
        str(frontend_output),
    ]
    pytest_cmd = [py_exec, "-m", "pytest", "-q", *PIPELINE_TEST_TARGETS]

    ok = True
    ok &= _run(frontend_build_cmd, cwd=repo_root)
    ok &= _run(pytest_cmd, cwd=repo_root)

    print("\nCI VALIDATION:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
