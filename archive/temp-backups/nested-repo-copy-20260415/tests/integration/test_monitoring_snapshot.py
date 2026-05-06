from __future__ import annotations

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.monitoring._monitoring_impl import collect_system_monitoring_snapshot, format_duration_human


class _EmptyResult:
    def fetchall(self):
        return []


class _FakeDB:
    def execute(self, *_args, **_kwargs):
        return _EmptyResult()


def test_format_duration_human_handles_short_and_long_windows():
    assert format_duration_human(45) == "45s"
    assert format_duration_human(3665) == "1h 1m"
    assert format_duration_human(90061) == "1d 1h 1m"


def test_collect_system_monitoring_snapshot_exposes_local_operations_panels(monkeypatch):
    app = create_app()

    monkeypatch.setattr(
        "src.app.monitoring._monitoring_impl._build_integrity_checks",
        lambda _db: (
            {
                "status_key": "healthy",
                "status_label": "Saudável",
                "status_class": "status-green",
                "total_issues": 0,
                "critical_issues": 0,
            },
            [],
            [],
        ),
    )
    monkeypatch.setattr(
        "src.app.monitoring._monitoring_impl._build_local_storage_metrics",
        lambda _db, _root: (
            {
                "status_key": "healthy",
                "status_label": "Saudável",
                "status_class": "status-green",
                "disk_total_bytes": 1000,
                "disk_used_bytes": 200,
                "disk_free_bytes": 800,
                "disk_usage_percent": 20.0,
                "disk_anchor": "C:\\",
                "message": "Volume local com capacidade saudável.",
            },
            [],
            [],
        ),
    )
    monkeypatch.setattr(
        "src.app.monitoring._monitoring_impl._build_local_server_context",
        lambda _root, _storage: {
            "status_key": "operational",
            "status_label": "Operacional",
            "status_class": "status-green",
            "hostname": "srv-local",
            "platform_label": "Windows",
            "python_label": "Python 3.11",
            "disk_anchor_label": "C:\\",
            "metrics": [],
        },
    )
    monkeypatch.setattr(
        "src.app.monitoring._monitoring_impl._build_local_services_context",
        lambda: {
            "status_key": "operational",
            "status_label": "Operacional",
            "status_class": "status-green",
            "running_required": 4,
            "required_total": 4,
            "windows_services": [],
            "endpoints": [],
        },
    )
    monkeypatch.setattr(
        "src.app.monitoring._monitoring_impl._build_module_statuses",
        lambda _db, *, integrity, storage: (
            [
                {
                    "name": "Banco de dados",
                    "category": "Infraestrutura",
                    "status_key": "operational",
                    "status_label": "Operacional",
                    "status_class": "status-green",
                    "problem_count": 0,
                    "last_check_label": "02/04/2026 10:00:00",
                    "message": "Conexão e leitura básicas respondendo.",
                },
                {
                    "name": "Filas e jobs",
                    "category": "Confiabilidade",
                    "status_key": "attention",
                    "status_label": "Atenção",
                    "status_class": "status-yellow",
                    "problem_count": 1,
                    "last_check_label": "02/04/2026 10:00:00",
                    "message": "Fila: 2 pendentes.",
                },
            ],
            [
                {
                    "severity_key": "warning",
                    "title": "Fila em atenção",
                    "message": "Há jobs aguardando.",
                    "source": "fila",
                }
            ],
            {
                "critical_modules": 0,
                "notification": {
                    "status_key": "operational",
                    "status_label": "Operacional",
                    "status_class": "status-green",
                    "provider": "smtp",
                    "email_ready": True,
                    "recipients_count": 2,
                    "last_run": "",
                    "last_sent_at": "",
                    "last_error": "",
                    "last_job_error": "",
                    "missing_config_fields": [],
                },
            },
        ),
    )

    with app.app_context():
        snapshot = collect_system_monitoring_snapshot(_FakeDB())

    assert snapshot["overview"]["services_running_label"] == "4/4"
    assert snapshot["server"]["hostname"] == "srv-local"
    assert snapshot["services"]["required_total"] == 4
    assert snapshot["operational_focus"][0]["title"] == "Banco de dados"
    assert snapshot["primary_alerts"][0]["title"] == "Fila em atenção"
