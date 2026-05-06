import logging
from pathlib import Path
from types import SimpleNamespace

from ops.windows.scripts import run_waitress_server


def test_waitress_runner_uses_repo_root_on_sys_path():
    expected_repo_root = Path(__file__).resolve().parents[2]
    assert run_waitress_server.REPO_ROOT == expected_repo_root


def test_waitress_runner_configures_queue_logger_level(monkeypatch):
    logger = logging.getLogger("waitress.queue")
    previous_level = logger.level
    monkeypatch.setenv("WAITRESS_QUEUE_LOG_LEVEL", "ERROR")
    fake_app = SimpleNamespace(logger=SimpleNamespace(info=lambda *_args, **_kwargs: None))

    try:
        run_waitress_server._configure_waitress_queue_logger(fake_app)
        assert logger.level == logging.ERROR
    finally:
        logger.setLevel(previous_level)
