from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import PoolError, ThreadedConnectionPool
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
    PoolError = Exception  # type: ignore[misc,assignment]
    ThreadedConnectionPool = None  # type: ignore[misc,assignment]

from flask import current_app, g

from ..core.utils import env_int as _read_int_env


class DatabaseError(RuntimeError):
    """Base class for database connectivity and configuration failures."""


class DatabaseConfigurationError(DatabaseError):
    """Raised when DB configuration/schema is structurally invalid."""


class DatabaseUnavailableError(DatabaseError):
    """Raised when DB is temporarily unavailable (network/infra)."""


class DatabasePoolExhaustedError(DatabaseUnavailableError):
    """Raised when the connection pool has no available slots."""


class DatabaseWrapper:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, params=None):
        cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(query, params)
        return cursor

    def _execute_script(self, script):
        cursor = self.conn.cursor()
        cursor.execute(script)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

_pg_pool = None
_pg_pool_config = None


def _build_pool_config(url: str) -> dict[str, Any]:
    min_conn = _read_int_env("DB_POOL_MIN_CONN", 1, minimum=1, maximum=200)
    max_conn = _read_int_env("DB_POOL_MAX_CONN", 20, minimum=1, maximum=200)
    if min_conn > max_conn:
        current_app.logger.warning(
            "Configuração de pool inválida (DB_POOL_MIN_CONN=%s > DB_POOL_MAX_CONN=%s). Ajustando automaticamente.",
            min_conn,
            max_conn,
        )
        min_conn, max_conn = max_conn, min_conn

    connect_timeout = _read_int_env("DB_CONNECT_TIMEOUT_SECONDS", 8, minimum=1, maximum=60)
    keepalives_idle = _read_int_env("DB_TCP_KEEPALIVES_IDLE", 30, minimum=1, maximum=3600)
    keepalives_interval = _read_int_env("DB_TCP_KEEPALIVES_INTERVAL", 10, minimum=1, maximum=600)
    keepalives_count = _read_int_env("DB_TCP_KEEPALIVES_COUNT", 5, minimum=1, maximum=20)
    statement_timeout_ms = _read_int_env("DB_STATEMENT_TIMEOUT_MS", 8000, minimum=0, maximum=3_600_000)

    connect_kwargs: dict[str, Any] = {
        "connect_timeout": connect_timeout,
        "keepalives": 1,
        "keepalives_idle": keepalives_idle,
        "keepalives_interval": keepalives_interval,
        "keepalives_count": keepalives_count,
        "application_name": (os.getenv("DB_APPLICATION_NAME", "") or "").strip() or "controle-treinamentos",
    }
    if statement_timeout_ms > 0:
        connect_kwargs["options"] = f"-c statement_timeout={statement_timeout_ms}"
    if "options=" in (url or ""):
        connect_kwargs.pop("options", None)

    return {
        "url": url,
        "min_conn": int(min_conn),
        "max_conn": int(max_conn),
        "connect_kwargs": connect_kwargs,
    }


def _close_pool() -> None:
    global _pg_pool, _pg_pool_config
    if _pg_pool is not None:
        try:
            _pg_pool.closeall()
        except Exception:
            current_app.logger.exception("Falha ao encerrar pool de conexões do PostgreSQL.")
    _pg_pool = None
    _pg_pool_config = None


def _initialize_pool(url: str) -> None:
    global _pg_pool, _pg_pool_config
    _pg_pool_config = _build_pool_config(url)
    _pg_pool = ThreadedConnectionPool(
        _pg_pool_config["min_conn"],
        _pg_pool_config["max_conn"],
        _pg_pool_config["url"],
        **_pg_pool_config["connect_kwargs"],
    )


def _is_connection_broken(conn: Any) -> bool:
    if conn is None:
        return True
    try:
        if getattr(conn, "closed", 0):
            return True
    except Exception:
        return True

    if psycopg2 is None:
        return False
    try:
        tx_status = conn.get_transaction_status()
        return tx_status == psycopg2.extensions.TRANSACTION_STATUS_UNKNOWN
    except Exception:
        return True


def _is_db_configuration_exception(exc: Exception) -> bool:
    if isinstance(exc, DatabaseConfigurationError):
        return True
    message = str(exc).lower()
    message_markers = (
        "database_url",
        "dsn",
        "invalid dsn",
        "does not exist",
        "undefinedtable",
        "undefinedcolumn",
        "configura",
    )
    if any(marker in message for marker in message_markers):
        return True
    if psycopg2 is not None and isinstance(exc, psycopg2.ProgrammingError):
        return True
    return False


def get_db():
    if "db" not in g:
        url = current_app.config["DATABASE_URL"]
        if not (url or "").strip():
            raise DatabaseConfigurationError(
                "DATABASE_URL não configurada. Defina a variável de ambiente antes de iniciar o sistema."
            )
        global _pg_pool, _pg_pool_config
        conn = None
        for attempt in range(2):
            if _pg_pool is None and url:
                try:
                    _initialize_pool(url)
                except Exception as exc:
                    _close_pool()
                    current_app.logger.exception("Falha ao inicializar pool de conexões do PostgreSQL.")
                    if _is_db_configuration_exception(exc):
                        raise DatabaseConfigurationError(
                            "Falha ao inicializar conexão com o banco por configuração inválida. "
                            "Verifique DATABASE_URL, schema e parâmetros de conexão."
                        ) from exc
                    if attempt == 0:
                        current_app.logger.warning(
                            "Falha transitória ao inicializar pool de banco; realizando nova tentativa."
                        )
                        continue
                    raise DatabaseUnavailableError(
                        "Falha ao inicializar conexão com o banco por indisponibilidade temporária."
                    ) from exc

            try:
                if _pg_pool:
                    for _wait_attempt in range(50):
                        try:
                            conn = _pg_pool.getconn()
                            break
                        except PoolError:
                            if _wait_attempt == 49:
                                raise
                            time.sleep(0.1)
                else:
                    conn = psycopg2.connect(url)

                if _pg_pool and _is_connection_broken(conn):
                    current_app.logger.warning(
                        "Conexão inválida recebida do pool de banco; descartando e tentando nova conexão."
                    )
                    _pg_pool.putconn(conn, close=True)
                    try:
                        conn = _pg_pool.getconn()
                    except PoolError:
                        time.sleep(0.1)
                        conn = _pg_pool.getconn()
                break
            except PoolError as exc:
                pool_min = (_pg_pool_config or {}).get("min_conn", "?")
                pool_max = (_pg_pool_config or {}).get("max_conn", "?")
                current_app.logger.error(
                    "Exaustão do pool de conexões (min=%s max=%s). Timeout de fila excedido (5s).",
                    pool_min,
                    pool_max,
                    exc_info=True,
                )
                raise DatabasePoolExhaustedError(
                    "Pool de banco esgotado no momento. Servidor sob sobrecarga momentânea."
                ) from exc
            except Exception as exc:
                if _is_db_configuration_exception(exc):
                    current_app.logger.exception("Falha estrutural de configuração ao obter conexão com o banco.")
                    raise DatabaseConfigurationError(
                        "Falha estrutural de configuração ao obter conexão com o banco."
                    ) from exc
                if attempt == 0 and _pg_pool is not None:
                    current_app.logger.warning(
                        "Falha transitória ao obter conexão do pool; reciclando pool e tentando novamente.",
                        exc_info=True,
                    )
                    _close_pool()
                    continue
                current_app.logger.exception("Falha temporária ao obter conexão com o banco.")
                raise DatabaseUnavailableError(
                    "Falha temporária ao obter conexão com o banco."
                ) from exc
        if conn is None:
            raise DatabaseUnavailableError(
                "Falha temporária ao obter conexão com o banco."
            )
        g._pg_conn = conn
        g.db = DatabaseWrapper(conn)
    return g.db

@contextmanager
def db_transaction():
    """
    Executa um bloco em contexto transacional protegido.
    Efetua commit no sucesso e garante rollback imediato em caso de exceção.
    """
    database = get_db()
    try:
        yield database
        database.commit()
    except Exception:
        database.conn.rollback()
        raise

def close_db(_error=None) -> None:
    g.pop("db", None)
    conn = g.pop("_pg_conn", None)
    if conn is not None:
        global _pg_pool
        if _pg_pool:
            should_discard = _is_connection_broken(conn)
            try:
                # Always rollback uncommitted transactions before putting back
                conn.rollback()
            except Exception:
                should_discard = True
            _pg_pool.putconn(conn, close=should_discard)
        else:
            conn.close()

def invalidate_request_db_cache() -> None:
    """
    Descarta a conexão cacheada em g.db / g._pg_conn para forçar
    get_db() a obter uma nova conexão na próxima chamada.

    Deve ser chamado antes de retentativas quando db.execute() falha
    com conexão stale — sem isso, get_db() retorna o mesmo wrapper quebrado.
    """
    g.pop("db", None)
    conn = g.pop("_pg_conn", None)
    if conn is None:
        return
    global _pg_pool
    if _pg_pool:
        try:
            _pg_pool.putconn(conn, close=True)
        except Exception:
            pass
    else:
        try:
            conn.close()
        except Exception:
            pass


def init_app(app) -> None:
    # DATABASE_URL é obrigatório em ambientes seguros; fora deles, pode ficar ausente em fluxos locais.
    configured_url = os.getenv("DATABASE_URL", "").strip()
    secure_envs = {"production", "staging", "homolog"}
    app_env = (app.config.get("APP_ENV") or "").strip().lower()
    if not configured_url:
        if app_env in secure_envs:
            raise RuntimeError(
                f"DATABASE_URL ausente em ambiente seguro ({app_env}). "
                "Defina a variável antes de iniciar a aplicação."
            )
        elif not app.config.get("TESTING"):
            app.logger.warning("DATABASE_URL is not set!")
    app.config.setdefault("DATABASE_URL", configured_url)

    with app.app_context():
        if not current_app.config["DATABASE_URL"]:
            return
        app.logger.info(
            "Bootstrap automático de schema desabilitado em runtime. "
            "Execute migração/consistência por comando operacional dedicado."
        )
