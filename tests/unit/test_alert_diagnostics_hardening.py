from flask import Flask

from backend.src.controle_treinamentos.blueprints.auth import routes as auth_routes
from backend.src.controle_treinamentos.monitoring._monitoring_impl import _build_recent_error_signal


class _SingleCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _RecentErrorsDB:
    def __init__(self, row):
        self._row = row
        self.params = None

    def execute(self, query, params=()):
        assert "request_error_events" in query
        self.params = params
        return _SingleCursor(self._row)


def test_recent_error_signal_warns_only_for_repeated_contract_failures(monkeypatch):
    monkeypatch.setenv("MONITORING_ERROR_ALERT_WINDOW_MINUTES", "15")
    monkeypatch.setenv("MONITORING_ERROR_WARNING_THRESHOLD", "10")
    monkeypatch.setenv("MONITORING_ERROR_CRITICAL_THRESHOLD", "30")
    monkeypatch.setenv("MONITORING_CONTRACT_ERROR_WARNING_THRESHOLD", "3")
    monkeypatch.setenv("MONITORING_CONTRACT_ERROR_CRITICAL_THRESHOLD", "8")
    db = _RecentErrorsDB(
        {
            "total_errors": 4,
            "server_errors": 1,
            "contract_errors": 3,
            "last_request_id": "req-contract-123",
            "last_path": "/api/relatorios/pdf",
            "last_code": "contract_invalid",
        }
    )

    signal = _build_recent_error_signal(db)

    assert db.params == (15,)
    assert signal["status_key"] == "attention"
    assert signal["problem_count"] == 3
    assert signal["alert"]["severity_key"] == "warning"
    assert "req-contract-123" in signal["message"]


def test_recent_error_signal_escalates_repeated_5xx_failures(monkeypatch):
    monkeypatch.setenv("MONITORING_ERROR_WARNING_THRESHOLD", "5")
    monkeypatch.setenv("MONITORING_ERROR_CRITICAL_THRESHOLD", "7")
    monkeypatch.setenv("MONITORING_CONTRACT_ERROR_WARNING_THRESHOLD", "3")
    monkeypatch.setenv("MONITORING_CONTRACT_ERROR_CRITICAL_THRESHOLD", "8")

    signal = _build_recent_error_signal(
        _RecentErrorsDB(
            {
                "total_errors": 9,
                "server_errors": 7,
                "contract_errors": 0,
                "last_request_id": "req-500-999",
                "last_path": "/api/tripulantes",
                "last_code": "internal_error",
            }
        )
    )

    assert signal["status_key"] == "degraded"
    assert signal["alert"]["severity_key"] == "critical"
    assert signal["server_errors"] == 7


def test_auth_failure_surge_snapshot_classifies_recent_failures():
    app = Flask(__name__)
    app.config.update(
        AUTH_FAILURE_ALERT_THRESHOLD=6,
        AUTH_FAILURE_ALERT_WINDOW_SECONDS=60,
        AUTH_FAILURE_ALERT_MIN_INTERVAL_SECONDS=15,
    )

    with app.app_context():
        try:
            with auth_routes._AUTH_FAILURE_LOCK:
                auth_routes._AUTH_FAILURE_TIMESTAMPS.clear()
                auth_routes._AUTH_FAILURE_TIMESTAMPS.extend([941.0, 950.0, 960.0, 970.0, 980.0, 990.0])
                auth_routes._LAST_AUTH_ALERT_AT = 970.0

            signal = auth_routes.auth_failure_surge_snapshot(now=1000.0)

            assert signal["status_key"] == "degraded"
            assert signal["count"] == 6
            assert signal["threshold"] == 6
            assert signal["last_alert_age_seconds"] == 30.0
        finally:
            with auth_routes._AUTH_FAILURE_LOCK:
                auth_routes._AUTH_FAILURE_TIMESTAMPS.clear()
                auth_routes._LAST_AUTH_ALERT_AT = 0.0
