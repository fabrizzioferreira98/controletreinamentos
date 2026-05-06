from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ci_release_pipeline_doc_covers_required_stages_and_classification():
    pipeline_doc = (REPO_ROOT / "docs" / "operations" / "CI_RELEASE_PIPELINE.md").read_text(encoding="utf-8")

    for stage in (
        "lint",
        "typecheck",
        "testes unitarios",
        "testes de integracao",
        "testes de contrato",
        "smoke",
        "build frontend",
        "build backend",
        "artefatos",
        "evidencias",
        "wrappers finos",
        "caminhos concorrentes de gate",
    ):
        assert stage in pipeline_doc

    for classification in (
        "Gate obrigatorio",
        "Validacao importante mas nao bloqueante",
        "Redundancia historica",
        "Wrapper aceitavel",
        "Legado perigoso",
        "Evidencia insuficiente",
    ):
        assert classification in pipeline_doc


def test_ci_release_pipeline_is_indexed_and_exposes_canonical_command():
    operations_index = (REPO_ROOT / "docs" / "operations" / "README.md").read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    canonical_commands = (REPO_ROOT / "docs" / "operations" / "canonical-commands.md").read_text(encoding="utf-8")
    release_gates = (REPO_ROOT / "docs" / "operations" / "RELEASE_GATES.md").read_text(encoding="utf-8")

    assert "CI_RELEASE_PIPELINE.md" in operations_index
    assert "CI_RELEASE_PIPELINE.md" in docs_index
    assert "run_ci_validation_minimal.py" in canonical_commands
    assert "run_ci_validation_minimal.py" in release_gates


def test_release_workflows_install_dev_dependencies_and_run_minimal_validation_bundle():
    validation_workflow = (REPO_ROOT / ".github" / "workflows" / "validation-ci.yml").read_text(encoding="utf-8")
    release_workflow = (REPO_ROOT / ".github" / "workflows" / "release-strict-gate.yml").read_text(encoding="utf-8")
    promotion_workflow = (REPO_ROOT / ".github" / "workflows" / "promotion-ci.yml").read_text(encoding="utf-8")

    for workflow in (validation_workflow, release_workflow, promotion_workflow):
        assert "requirements-dev.txt" in workflow
        assert "run_ci_validation_minimal.py" in workflow

    assert "run_release_strict.py" in release_workflow
    assert "run_release_strict.py" in promotion_workflow


def test_minimal_ci_validation_bundle_builds_frontend_and_runs_pipeline_contract_tests():
    source = (REPO_ROOT / "ops" / "scripts" / "release" / "run_ci_validation_minimal.py").read_text(encoding="utf-8")

    assert "build_frontend.py" in source
    assert "test_ci_release_pipeline_policy.py" in source
    assert "test_frontend_compat_redirects.py" in source
