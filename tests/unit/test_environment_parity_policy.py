from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_environment_parity_doc_covers_required_axes_and_risk_classes():
    parity_doc = (REPO_ROOT / "docs" / "operations" / "ENVIRONMENT_PARITY.md").read_text(encoding="utf-8")

    for axis in (
        "auth",
        "banco",
        "storage",
        "worker",
        "scheduler",
        "notificacoes",
        "PDFs",
        "uploads/downloads",
        "build frontend",
        "variaveis de ambiente",
        "integracoes externas",
        "massa de dados",
    ):
        assert axis in parity_doc

    for risk_class in (
        "diferenca aceitavel",
        "diferenca toleravel temporaria",
        "diferenca perigosa",
        "falso verde direto",
        "bloqueador de validacao real",
    ):
        assert risk_class in parity_doc


def test_ops_indexes_and_regression_checklist_reference_environment_parity():
    operations_index = (REPO_ROOT / "docs" / "operations" / "README.md").read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    local_runtime = (REPO_ROOT / "docs" / "operations" / "LOCAL_RUNTIME.md").read_text(encoding="utf-8")
    checklist = (REPO_ROOT / "docs" / "operations" / "REGRESSION_AUDIT_CHECKLIST.md").read_text(encoding="utf-8")

    assert "ENVIRONMENT_PARITY.md" in operations_index
    assert "ENVIRONMENT_PARITY.md" in docs_index
    assert "ENVIRONMENT_PARITY.md" in local_runtime
    assert "Paridade minima local/homolog/producao" in checklist
    assert "Worker ativo consumindo fila real" in checklist
    assert "Storage, uploads/downloads e PDFs validados em raiz real do ambiente." in checklist


def test_env_example_exposes_parity_sensitive_runtime_paths():
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for key in (
        "WORKSPACE_RUNTIME_ROOT=",
        "WORKSPACE_EVIDENCE_ROOT=",
        "WORKSPACE_LOCAL_BACKUPS_ROOT=",
        "APP_INSTANCE_PATH=",
        "MEDIA_STORAGE_ROOT=",
        "METRICS_TOKEN=",
        "BACKUP_DIR=",
    ):
        assert key in env_example

    assert "BACKUP_DIR=./backups" not in env_example
