import json
import logging

from backend.src.controle_treinamentos.core.logging import JSONFormatter, RequestIdFilter


def test_json_formatter_preserves_operational_extra_fields():
    record = logging.getLogger("tests.structured").makeRecord(
        "tests.structured",
        logging.INFO,
        __file__,
        10,
        "Job completed.",
        (),
        None,
        extra={
            "event": "background_job_completed",
            "job_id": 42,
            "job_type": "run_backup",
            "duration_ms": 123,
        },
    )

    payload = json.loads(JSONFormatter().format(record))

    assert payload["message"] == "Job completed."
    assert payload["event"] == "background_job_completed"
    assert payload["job_id"] == 42
    assert payload["job_type"] == "run_backup"
    assert payload["duration_ms"] == 123


def test_request_id_filter_keeps_explicit_request_id_without_flask_context():
    record = logging.LogRecord(
        name="tests.structured",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Worker log",
        args=(),
        exc_info=None,
    )
    record.request_id = "origin-req-123"

    assert RequestIdFilter().filter(record) is True
    assert record.request_id == "origin-req-123"


def test_request_id_filter_keeps_explicit_correlation_id_without_flask_context():
    record = logging.LogRecord(
        name="tests.structured",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Worker log",
        args=(),
        exc_info=None,
    )
    record.correlation_id = "corr-123"

    assert RequestIdFilter().filter(record) is True
    assert record.correlation_id == "corr-123"
