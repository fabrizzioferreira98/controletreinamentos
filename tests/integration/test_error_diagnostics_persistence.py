import json
import time

from backend.src.controle_treinamentos import create_app


class _Cursor:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _RequestErrorEventsDB:
    def __init__(self):
        self.events = {}
        self.commits = 0

    def execute(self, query, params=()):
        normalized_query = " ".join(query.lower().split())
        if "insert into request_error_events" in normalized_query:
            context_json = json.loads(params[9])
            captured_at = int(time.time())
            self.events[params[0]] = {
                "request_id": params[0],
                "status": params[1],
                "code": params[2],
                "error_type": params[3],
                "error_message": params[4],
                "path": params[5],
                "endpoint": params[6],
                "method": params[7],
                "user_id": params[8],
                "context_json": context_json,
                "captured_at": captured_at,
            }
            return _Cursor()

        if "from request_error_events" in normalized_query and "where request_id = %s" in normalized_query:
            return _Cursor(row=self.events.get(params[0]))

        if "from request_error_events" in normalized_query and "order by captured_at desc" in normalized_query:
            limit = int(params[0])
            rows = sorted(
                self.events.values(),
                key=lambda item: item["captured_at"],
                reverse=True,
            )
            return _Cursor(rows=rows[:limit])

        raise AssertionError(f"Unexpected query: {query}")

    def commit(self):
        self.commits += 1


def test_http_500_is_persisted_and_returned_by_internal_error_trace(monkeypatch):
    monkeypatch.setenv("APP_RELEASE_ID", "release-int-23-2")
    monkeypatch.setenv("METRICS_TOKEN", "token-23-2")
    fake_db = _RequestErrorEventsDB()
    monkeypatch.setattr("backend.src.controle_treinamentos.db.get_db", lambda: fake_db)

    app = create_app()

    @app.route("/_test/error-diagnostics-persistence")
    def _test_error_diagnostics_persistence():
        raise RuntimeError("integration persistence boom")

    client = app.test_client()

    failed = client.get(
        "/_test/error-diagnostics-persistence",
        headers={
            "Accept": "application/json",
            "X-Correlation-ID": "corr-int-23-2",
        },
    )

    assert failed.status_code == 500
    request_id = (failed.headers.get("X-Request-ID") or "").strip()
    assert request_id
    assert fake_db.commits == 1
    assert fake_db.events[request_id]["path"] == "/_test/error-diagnostics-persistence"
    assert fake_db.events[request_id]["endpoint"] == "_test_error_diagnostics_persistence"
    assert fake_db.events[request_id]["context_json"]["correlation_id"] == "corr-int-23-2"

    trace = client.get(
        f"/api/internal/errors/{request_id}",
        headers={"X-Metrics-Token": "token-23-2"},
    )

    assert trace.status_code == 200
    payload = trace.get_json()
    assert payload["code"] == "error_event_found"
    event = payload["event"]
    assert event["request_id"] == request_id
    assert event["correlation_id"] == "corr-int-23-2"
    assert event["release_id"] == "release-int-23-2"
    assert event["status"] == 500
    assert event["code"] == "internal_error"
    assert event["error_type"] == "InternalServerError"
    assert event["error_message"].startswith("500 Internal Server Error")
    assert event["path"] == "/_test/error-diagnostics-persistence"
    assert event["endpoint"] == "_test_error_diagnostics_persistence"
    assert event["method"] == "GET"
    assert event["user_id"] is None
    assert event["captured_at"] == fake_db.events[request_id]["captured_at"]
    assert payload["recent"][0]["request_id"] == request_id
