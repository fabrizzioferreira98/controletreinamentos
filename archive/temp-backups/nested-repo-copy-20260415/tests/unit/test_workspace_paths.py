from pathlib import Path

import pytest

from backend.src.controle_treinamentos.core import workspace_paths


def test_runtime_root_defaults_outside_repository(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("WORKSPACE_RUNTIME_ROOT", raising=False)

    runtime_root = workspace_paths.runtime_root()

    assert runtime_root != workspace_paths.workspace_root() / "runtime"
    assert workspace_paths.workspace_root() not in runtime_root.resolve(strict=False).parents


def test_secure_env_rejects_runtime_root_inside_repository(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "WORKSPACE_RUNTIME_ROOT",
        str(workspace_paths.workspace_root() / "runtime"),
    )

    with pytest.raises(RuntimeError):
        workspace_paths.runtime_root()


def test_media_storage_root_without_app_context_uses_external_instance(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("MEDIA_STORAGE_ROOT", raising=False)
    monkeypatch.delenv("UPLOAD_ROOT", raising=False)
    monkeypatch.delenv("APP_INSTANCE_PATH", raising=False)
    monkeypatch.delenv("WORKSPACE_RUNTIME_ROOT", raising=False)

    from backend.src.controle_treinamentos.infra import media_storage

    root = media_storage.media_storage_root()

    assert root.name == "uploads"
    assert workspace_paths.workspace_root() not in root.resolve(strict=False).parents


def test_media_storage_root_rejects_repository_path_in_secure_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "MEDIA_STORAGE_ROOT",
        str(workspace_paths.workspace_root() / "runtime" / "instance" / "uploads"),
    )

    from backend.src.controle_treinamentos.infra import media_storage

    with pytest.raises(RuntimeError):
        media_storage.media_storage_root()
