import time

from flask import session

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.core.auth_contract import touch_auth_session


def test_touch_auth_session_skips_recent_touch():
    app = create_app()
    app.config["AUTH_SESSION_TOUCH_INTERVAL_SECONDS"] = 30

    with app.test_request_context("/"):
        now = int(time.time())
        session["_user_id"] = "7"
        session["auth_session_id"] = "sid"
        session["auth_session_last_seen_at"] = now
        session["auth_session_expires_at"] = now + 3600

        touch_auth_session()

        assert session["auth_session_last_seen_at"] == now
        assert session["auth_session_expires_at"] == now + 3600


def test_touch_auth_session_refreshes_stale_touch():
    app = create_app()
    app.config["AUTH_SESSION_TOUCH_INTERVAL_SECONDS"] = 30

    with app.test_request_context("/"):
        now = int(time.time())
        session["_user_id"] = "8"
        session["auth_session_id"] = "sid"
        session["auth_session_last_seen_at"] = now - 60
        session["auth_session_expires_at"] = now + 60
        old_expires_at = session["auth_session_expires_at"]

        touch_auth_session()

        assert session["auth_session_last_seen_at"] >= now
        assert session["auth_session_expires_at"] > old_expires_at
