import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .db import get_db

CACHE_TTL_SECONDS = 30
OPTIONS_CACHE_TTL_SECONDS = 600
NAV_CACHE_TTL_SECONDS = 120
DASHBOARD_CACHE_TTL_SECONDS = 20

def _cleanup_expired(db):
    db.execute(
        """
        DELETE FROM sistema_controle
        WHERE chave LIKE 'cache:%'
          AND valor IS NOT NULL
          AND (valor::jsonb->>'expires_at')::timestamp < CURRENT_TIMESTAMP
        """
    )

def _get_cache(key: str) -> object | None:
    db = get_db()
    row = db.execute(
        "SELECT valor FROM sistema_controle WHERE chave = %s",
        (f"cache:{key}",)
    ).fetchone()

    if not row or not row["valor"]:
        return None

    try:
        data = json.loads(row["valor"])
        expires_at = datetime.fromisoformat(data["expires_at"])
        if datetime.now(ZoneInfo("America/Sao_Paulo")) > expires_at:
            db.execute("DELETE FROM sistema_controle WHERE chave = %s", (f"cache:{key}",))
            db.commit()
            return None
        return data["payload"]
    except (json.JSONDecodeError, KeyError, ValueError):
        return None

def _set_cache(key: str, payload: object, ttl_seconds: int):
    db = get_db()
    _cleanup_expired(db)

    expires_at = datetime.now(ZoneInfo("America/Sao_Paulo"))
    expires_at += timedelta(seconds=max(1, ttl_seconds))

    data = {
        "expires_at": expires_at.isoformat(),
        "payload": payload
    }
    dumped = json.dumps(data, ensure_ascii=False, default=str)

    db.execute(
        """
        INSERT INTO sistema_controle (chave, valor)
        VALUES (%s, %s)
        ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor
        """,
        (f"cache:{key}", dumped)
    )
    db.commit()

def _delete_cache(prefix: str):
    db = get_db()
    db.execute(
        "DELETE FROM sistema_controle WHERE chave LIKE %s",
        (f"cache:{prefix}%",)
    )
    db.commit()
