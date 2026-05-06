from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLISH_SCRIPT = REPO_ROOT / "ops" / "windows" / "scripts" / "Publish-Frontend.ps1"
HML_SCRIPT = REPO_ROOT / "ops" / "windows" / "scripts" / "Publish-Frontend-Hml.ps1"


def _run_publish(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PUBLISH_SCRIPT),
            *args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_publish_frontend_without_environment_fails() -> None:
    result = _run_publish("-ValidateOnly")

    assert result.returncode != 0
    assert "Environment ausente" in (result.stderr + result.stdout)


def test_publish_frontend_hml_resolves_to_hml_destination() -> None:
    result = _run_publish("-Environment", "hml", "-ValidateOnly")

    assert result.returncode == 0
    assert r"Environment: hml" in result.stdout
    assert r"Destination: C:\srv\controle-treinamentos\frontend\hml" in result.stdout
    assert r"EnvFile: C:\srv\controle-treinamentos\env\hml.env" in result.stdout


def test_publish_frontend_hml_rejects_production_destination() -> None:
    result = _run_publish(
        "-Environment",
        "hml",
        "-Destination",
        r"C:\srv\controle-treinamentos\frontend\prod",
        "-ValidateOnly",
    )

    assert result.returncode != 0
    assert "Environment=hml nao pode publicar em destino de producao" in (result.stderr + result.stdout)


def test_publish_frontend_hml_rejects_prod_env_file() -> None:
    result = _run_publish(
        "-Environment",
        "hml",
        "-EnvFile",
        r"C:\srv\controle-treinamentos\env\prod.env",
        "-ValidateOnly",
    )

    assert result.returncode != 0
    assert "Environment=hml nao pode usar prod.env" in (result.stderr + result.stdout)


def test_publish_frontend_prod_requires_literal_confirmation() -> None:
    result = _run_publish("-Environment", "prod", "-ValidateOnly")

    assert result.returncode != 0
    assert 'Environment=prod exige -ConfirmProdPublish "publish-prod"' in (result.stderr + result.stdout)


def test_publish_frontend_prod_with_literal_confirmation_validates() -> None:
    result = _run_publish(
        "-Environment",
        "prod",
        "-ConfirmProdPublish",
        "publish-prod",
        "-ValidateOnly",
    )

    assert result.returncode == 0
    assert r"Environment: prod" in result.stdout
    assert r"Destination: C:\srv\controle-treinamentos\frontend\prod" in result.stdout
    assert r"EnvFile: C:\srv\controle-treinamentos\env\prod.env" in result.stdout


def test_hml_wrapper_never_mentions_production_destination() -> None:
    source = HML_SCRIPT.read_text(encoding="utf-8").lower()

    assert r"frontend\prod" not in source
    assert "prod.env" not in source
    assert "confirmprodpublish" not in source
    assert '"hml"' in source


def test_main_publisher_has_no_production_defaults() -> None:
    source = PUBLISH_SCRIPT.read_text(encoding="utf-8")
    param_block = source.split(")", 1)[0]

    assert '[string]$Destination = "C:\\srv\\controle-treinamentos\\frontend\\prod"' not in param_block
    assert '[string]$EnvFile = "C:\\srv\\controle-treinamentos\\env\\prod.env"' not in param_block
    assert '[ValidateSet("hml", "prod")]' in source
    assert '$ProdDestination = "C:\\srv\\controle-treinamentos\\frontend\\prod"' in source


def test_powershell_scripts_parse() -> None:
    command = (
        "$ErrorActionPreference='Stop'; "
        "$tokens=$null; $errors=$null; $tokens2=$null; $errors2=$null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{PUBLISH_SCRIPT}', [ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { throw ($errors | Out-String) }; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{HML_SCRIPT}', [ref]$tokens2, [ref]$errors2) | Out-Null; "
        "if ($errors2.Count -gt 0) { throw ($errors2 | Out-String) }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
