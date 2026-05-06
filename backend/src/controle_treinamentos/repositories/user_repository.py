try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

from flask import current_app, g

from ..db import get_db, invalidate_request_db_cache
from ..db.connection import DatabaseConfigurationError, DatabaseUnavailableError, DatabasePoolExhaustedError


def _classify_db_failure(exc: Exception) -> str:
    if isinstance(exc, DatabaseConfigurationError):
        return "configuration"
    if isinstance(exc, DatabasePoolExhaustedError):
        return "pool_exhausted"
    if isinstance(exc, DatabaseUnavailableError):
        return "connection_timeout"
    if psycopg2 is not None and isinstance(exc, psycopg2.OperationalError):
        return "connection_timeout"
    if psycopg2 is not None and isinstance(exc, psycopg2.InterfaceError):
        return "connection_timeout"
    if psycopg2 is not None and isinstance(exc, psycopg2.ProgrammingError):
        return "configuration"
    if psycopg2 is not None and isinstance(exc, psycopg2.Error):
        return "database"
    if isinstance(exc, RuntimeError):
        error_text = str(exc).lower()
        if any(marker in error_text for marker in ("database_url", "invalid dsn", "configura", "undefinedtable", "undefinedcolumn")):
            return "configuration"
    return "infrastructure"


# Exceções retentáveis no nível do repository
_RETRYABLE_DB_EXCEPTIONS = (RuntimeError,)
if psycopg2 is not None:
    _RETRYABLE_DB_EXCEPTIONS = (RuntimeError, psycopg2.Error)


class UserRepository:
    @staticmethod
    def get_by_login(login_value: str):
        for attempt in range(2):
            try:
                db = get_db()
                return db.execute(
                    """
                    SELECT id, nome, login, email, perfil, ativo, permissao_modulos_json, senha_hash
                    FROM usuarios
                    WHERE login = %s
                    """,
                    (login_value,),
                ).fetchone()
            except _RETRYABLE_DB_EXCEPTIONS as exc:
                failure_kind = _classify_db_failure(exc)
                if failure_kind not in {"configuration"} and attempt == 0:
                    current_app.logger.warning(
                        "Falha temporária ao consultar usuário de login; invalidando conexão e repetindo consulta. "
                        "request_id=%s login=%s kind=%s exc_type=%s exc_msg=%s",
                        getattr(g, "request_id", None),
                        login_value,
                        failure_kind,
                        type(exc).__name__,
                        str(exc)[:200],
                        exc_info=True,
                    )
                    # Invalidar conexão cacheada para forçar nova conexão no retry
                    invalidate_request_db_cache()
                    continue
                # Anexa o tipo de falha na exceção para o controller decidir
                exc.auth_failure_kind = failure_kind  # type: ignore[attr-defined]
                raise
