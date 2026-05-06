try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
import os
import time
from flask import current_app, g, has_request_context, session
from flask_login import UserMixin

from .auth import ALL_PERMISSION_KEYS, normalize_permissions
from .db import get_db, invalidate_request_db_cache


def _snapshot_max_age_seconds() -> int:
    raw = current_app.config.get("AUTH_SNAPSHOT_MAX_AGE_SECONDS", 300)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 300
    return max(30, value)


def _snapshot_refresh_interval_seconds() -> int:
    raw = current_app.config.get(
        "AUTH_SNAPSHOT_REFRESH_INTERVAL_SECONDS",
        os.getenv("AUTH_SNAPSHOT_REFRESH_INTERVAL_SECONDS", "300"),
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 300
    return max(0, value)


def _load_user_from_session_snapshot(user_id) -> "User | None":
    if not has_request_context():
        return None
    snapshot = session.get("auth_user_snapshot")
    snapshot_ts = session.get("auth_user_snapshot_ts")
    if not isinstance(snapshot, dict):
        return None
    if str(snapshot.get("id") or "") != str(user_id):
        return None
    try:
        captured_at = int(snapshot_ts if snapshot_ts is not None else snapshot.get("captured_at", 0))
    except (TypeError, ValueError):
        return None
    if captured_at <= 0:
        return None
    age_seconds = int(time.time()) - captured_at
    if age_seconds < 0 or age_seconds > _snapshot_max_age_seconds():
        return None
    try:
        ativo = int(snapshot.get("ativo") or 0)
    except (TypeError, ValueError):
        return None
    if ativo != 1:
        return None
    g.auth_session_snapshot_used = True
    g.auth_session_snapshot_age_seconds = age_seconds
    return User(
        snapshot.get("id"),
        snapshot.get("nome") or "",
        snapshot.get("login") or "",
        snapshot.get("email") or "",
        snapshot.get("perfil") or "",
        ativo,
        snapshot.get("permissao_modulos_json", "[]"),
    )


def _store_user_snapshot(user_row) -> None:
    if not has_request_context():
        return
    try:
        user_id = str(user_row["id"])
        now = int(time.time())
        current_snapshot = session.get("auth_user_snapshot")
        current_snapshot_ts = session.get("auth_user_snapshot_ts")
        if isinstance(current_snapshot, dict) and str(current_snapshot.get("id") or "") == user_id:
            try:
                captured_at = int(
                    current_snapshot_ts
                    if current_snapshot_ts is not None
                    else current_snapshot.get("captured_at", 0)
                )
            except (TypeError, ValueError):
                captured_at = 0
            refresh_interval = _snapshot_refresh_interval_seconds()
            if refresh_interval > 0 and captured_at > 0 and 0 <= now - captured_at < refresh_interval:
                return
        payload = {
            "id": user_id,
            "nome": user_row["nome"] or "",
            "login": user_row["login"] or "",
            "email": user_row["email"] or "",
            "perfil": user_row["perfil"] or "",
            "ativo": int(user_row["ativo"] or 0),
            "permissao_modulos_json": user_row.get("permissao_modulos_json", "[]"),
            "captured_at": now,
        }
    except Exception:
        return
    session["auth_user_snapshot"] = payload
    session["auth_user_snapshot_ts"] = payload["captured_at"]


def _request_user_cache_get(user_id):
    if not has_request_context():
        return None
    cache = getattr(g, "_auth_user_cache", None)
    if not isinstance(cache, dict):
        return None
    return cache.get(str(user_id))


def _request_user_cache_set(user_id, user_obj) -> None:
    if not has_request_context():
        return
    cache = getattr(g, "_auth_user_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        g._auth_user_cache = cache
    cache[str(user_id)] = user_obj


# Exceções de banco retentáveis para o user_loader
_DB_EXCEPTIONS = (Exception,)  # fallback mínimo
if psycopg2 is not None:
    _DB_EXCEPTIONS_PSYCOPG2 = (psycopg2.Error,)
else:
    _DB_EXCEPTIONS_PSYCOPG2 = ()


class User(UserMixin):
    def __init__(self, id, nome, login, email, perfil, ativo, permissao_modulos_json=None):
        self.id = str(id)
        self.nome = nome
        self.login = login
        self.email = email
        self.perfil = perfil
        self.ativo = ativo
        self.permissoes = normalize_permissions(permissao_modulos_json, perfil=perfil)

    @property
    def is_active(self):
        return self.ativo == 1

    def has_permission(self, permission_key: str) -> bool:
        if self.perfil == "gestora":
            return True
        if permission_key in {"", None}:
            return False
        return permission_key in self.permissoes

    def is_allowed(self, permission_key: str) -> bool:
        return self.has_permission(permission_key)

    @property
    def granted_permissions(self):
        if self.perfil == "gestora":
            return set(ALL_PERMISSION_KEYS)
        return set(self.permissoes)

    @staticmethod
    def get(user_id):
        cached_user = _request_user_cache_get(user_id)
        if cached_user is not None:
            return cached_user
        request_id = getattr(g, "request_id", None) if has_request_context() else None

        # Tentativa com retry: se a primeira falha por conexão stale,
        # invalida o cache e tenta uma segunda vez com conexão nova.
        for attempt in range(2):
            try:
                db = get_db()
                user_row = db.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,)).fetchone()
                break  # Sucesso — sai do loop
            except _DB_EXCEPTIONS_PSYCOPG2:
                if attempt == 0:
                    current_app.logger.warning(
                        "Transient DB failure loading user; invalidating connection and retrying. "
                        "request_id=%s user_id=%s attempt=%s",
                        request_id, user_id, attempt,
                        exc_info=True,
                    )
                    invalidate_request_db_cache()
                    continue
                # Segunda tentativa falhou — tentar snapshot
                fallback_user = _load_user_from_session_snapshot(user_id)
                if fallback_user is not None:
                    _request_user_cache_set(user_id, fallback_user)
                    current_app.logger.warning(
                        "Using auth session snapshot after DB retry exhausted. "
                        "request_id=%s user_id=%s",
                        request_id, user_id,
                    )
                    return fallback_user
                if has_request_context():
                    g.auth_backend_unavailable = True
                current_app.logger.exception(
                    "Failed to load authenticated user from database after retry. "
                    "request_id=%s user_id=%s",
                    request_id, user_id,
                )
                return None
            except RuntimeError as exc:
                if attempt == 0:
                    current_app.logger.warning(
                        "Runtime DB failure loading user; invalidating connection and retrying. "
                        "request_id=%s user_id=%s error=%s attempt=%s",
                        request_id, user_id, str(exc)[:200], attempt,
                        exc_info=True,
                    )
                    invalidate_request_db_cache()
                    continue
                # Segunda tentativa falhou — tentar snapshot
                fallback_user = _load_user_from_session_snapshot(user_id)
                if fallback_user is not None:
                    _request_user_cache_set(user_id, fallback_user)
                    current_app.logger.warning(
                        "Using auth session snapshot after runtime DB retry exhausted. "
                        "request_id=%s user_id=%s error=%s",
                        request_id, user_id, str(exc)[:200],
                    )
                    return fallback_user
                if has_request_context():
                    g.auth_backend_unavailable = True
                current_app.logger.warning(
                    "Authenticated user reload unavailable after runtime DB retry. "
                    "request_id=%s user_id=%s error=%s",
                    request_id, user_id, str(exc)[:200],
                )
                return None
        else:
            # Loop terminou sem break (improvável, mas defensivo)
            return None

        if not user_row:
            if has_request_context():
                g.auth_session_invalid = True
                g.auth_session_invalid_user_id = str(user_id)
            return None
        try:
            user_is_active = int(user_row["ativo"]) == 1
        except (TypeError, ValueError):
            user_is_active = False
        if not user_is_active:
            if has_request_context():
                g.auth_user_inactive = True
                g.auth_inactive_user_id = str(user_id)
            return None
        _store_user_snapshot(user_row)
        user_obj = User(
            user_row["id"], user_row["nome"], user_row["login"],
            user_row["email"], user_row["perfil"], user_row["ativo"], user_row.get("permissao_modulos_json", "[]")
        )
        _request_user_cache_set(user_id, user_obj)
        return user_obj
