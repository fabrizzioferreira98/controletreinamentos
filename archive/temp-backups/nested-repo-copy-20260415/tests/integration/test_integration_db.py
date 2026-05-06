"""Integration test scaffold — requires DATABASE_URL pointing to a real test DB.

Run: DATABASE_URL=postgresql://... pytest tests/e2e/ -v
"""
import os

import pytest

SKIP_REASON = "DATABASE_URL not set or not pointing to test DB"


def has_test_db() -> bool:
    url = (os.getenv("DATABASE_URL", "") or "").strip()
    return bool(url) and "test" in url.lower()


@pytest.mark.skipif(not has_test_db(), reason=SKIP_REASON)
class TestDatabaseIntegration:
    """Integration tests that run against a real PostgreSQL database."""

    def test_connection_pool_creates_and_returns(self):
        from backend.src.controle_treinamentos import create_app
        app = create_app()
        with app.app_context():
            from backend.src.controle_treinamentos.db import close_db, get_db
            db = get_db()
            row = db.execute("SELECT 1 AS ok").fetchone()
            assert row is not None
            close_db()

    def test_schema_tables_exist(self):
        from backend.src.controle_treinamentos import create_app
        app = create_app()
        with app.app_context():
            from backend.src.controle_treinamentos.db import get_db
            db = get_db()
            row = db.execute(
                "SELECT COUNT(*) AS total FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchone()
            assert row is not None
            assert int(row["total"] or 0) > 0

    def test_healthcheck_endpoint_returns_ok(self):
        from backend.src.controle_treinamentos import create_app
        app = create_app()
        with app.test_client() as client:
            response = client.get("/healthz")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "ok"
