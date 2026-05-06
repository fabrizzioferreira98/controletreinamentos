from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence

import psycopg2
from psycopg2 import sql


CANONICAL_TEST_USERS: dict[str, str] = {
    "qa_admin": "admin/gestora para desenvolvimento, QA manual e smoke autenticado",
    "qa_operador": "usuario padrao autenticado",
    "qa_inativo": "usuario inativo para contrato de autenticacao",
    "qa_restrito": "usuario ativo com permissao restrita para contrato de autorizacao",
}

TEST_LOGIN_PATTERNS = (
    re.compile(r"^qa_"),
    re.compile(r"^e2e_"),
    re.compile(r"^test_"),
    re.compile(r"^teste_"),
    re.compile(r"^smoke"),
    re.compile(r"^loadtest"),
    re.compile(r"^auth_contract_"),
    re.compile(r".*_test$"),
)

EXPLICIT_TEST_LOGINS = {
    "operador_api",
    "ativo_logout",
    "ativo_logout_api",
    "inativo",
    "limitado",
    "probe_user",
    "release-bot",
    "snapshot_user",
}

ROLE_DUPLICATE_FRAGMENTS = (
    "admin",
    "gestora",
    "operador",
    "inactive",
    "inativo",
    "limited",
    "limitado",
    "restricted",
    "restrito",
)


@dataclass(frozen=True)
class UserRecord:
    id: int
    login: str
    nome: str
    email: str
    perfil: str
    ativo: int


@dataclass(frozen=True)
class UserReference:
    table_schema: str
    table_name: str
    column_name: str


@dataclass(frozen=True)
class ClassifiedTestUser:
    id: int
    login: str
    nome: str
    email: str
    perfil: str
    ativo: int
    classification: str
    planned_action: str
    reference_count: int
    reason: str


def _normalize_login(value: object) -> str:
    return str(value or "").strip().lower()


def is_test_login(login: object) -> bool:
    normalized = _normalize_login(login)
    if not normalized:
        return False
    if normalized in EXPLICIT_TEST_LOGINS:
        return True
    return any(pattern.match(normalized) for pattern in TEST_LOGIN_PATTERNS)


def build_keep_logins(extra_keep_logins: Iterable[str] | None = None) -> set[str]:
    keep = set(CANONICAL_TEST_USERS)
    for login in extra_keep_logins or ():
        normalized = _normalize_login(login)
        if normalized:
            keep.add(normalized)
    return keep


def _to_user_record(row: Mapping[str, object]) -> UserRecord:
    return UserRecord(
        id=int(row["id"]),
        login=str(row.get("login") or ""),
        nome=str(row.get("nome") or ""),
        email=str(row.get("email") or ""),
        perfil=str(row.get("perfil") or ""),
        ativo=int(row.get("ativo") or 0),
    )


def _looks_like_role_duplicate(login: str) -> bool:
    return any(fragment in login for fragment in ROLE_DUPLICATE_FRAGMENTS)


def classify_user_record(
    row: Mapping[str, object],
    *,
    reference_count: int,
    keep_logins: Iterable[str],
    allow_delete: bool,
) -> ClassifiedTestUser | None:
    user = _to_user_record(row)
    login = _normalize_login(user.login)
    keep = {_normalize_login(item) for item in keep_logins}

    if login in keep:
        return ClassifiedTestUser(
            id=user.id,
            login=user.login,
            nome=user.nome,
            email=user.email,
            perfil=user.perfil,
            ativo=user.ativo,
            classification="manter",
            planned_action="none",
            reference_count=int(reference_count),
            reason="usuario canonico da frente 19.1",
        )

    if not is_test_login(login):
        return None

    if int(reference_count) <= 0 and allow_delete:
        return ClassifiedTestUser(
            id=user.id,
            login=user.login,
            nome=user.nome,
            email=user.email,
            perfil=user.perfil,
            ativo=user.ativo,
            classification="remover",
            planned_action="delete",
            reference_count=0,
            reason="usuario de teste nao canonico sem referencias",
        )

    if _looks_like_role_duplicate(login):
        return ClassifiedTestUser(
            id=user.id,
            login=user.login,
            nome=user.nome,
            email=user.email,
            perfil=user.perfil,
            ativo=user.ativo,
            classification="consolidar",
            planned_action="deactivate" if user.ativo else "none",
            reference_count=int(reference_count),
            reason="papel de teste duplicado deve apontar para usuario canonico",
        )

    return ClassifiedTestUser(
        id=user.id,
        login=user.login,
        nome=user.nome,
        email=user.email,
        perfil=user.perfil,
        ativo=user.ativo,
        classification="desativar",
        planned_action="deactivate" if user.ativo else "none",
        reference_count=int(reference_count),
        reason="usuario de teste nao canonico preservado por seguranca referencial",
    )


def build_sanitization_plan(
    rows: Sequence[Mapping[str, object]],
    *,
    reference_counts: Mapping[int, int],
    keep_logins: Iterable[str],
    allow_delete: bool,
) -> list[ClassifiedTestUser]:
    plan: list[ClassifiedTestUser] = []
    for row in rows:
        user_id = int(row["id"])
        classified = classify_user_record(
            row,
            reference_count=int(reference_counts.get(user_id, 0)),
            keep_logins=keep_logins,
            allow_delete=allow_delete,
        )
        if classified is not None:
            plan.append(classified)
    return sorted(plan, key=lambda item: item.login.lower())


def _fetch_dicts(cursor) -> list[dict[str, object]]:
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_users(conn) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, login, nome, email, perfil, ativo
            FROM usuarios
            ORDER BY lower(login)
            """
        )
        return _fetch_dicts(cur)


def fetch_user_reference_columns(conn) -> list[UserReference]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                tc.table_schema,
                tc.table_name,
                kcu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND ccu.table_name = 'usuarios'
              AND ccu.column_name = 'id'
            ORDER BY tc.table_schema, tc.table_name, kcu.column_name
            """
        )
        return [
            UserReference(
                table_schema=str(row["table_schema"]),
                table_name=str(row["table_name"]),
                column_name=str(row["column_name"]),
            )
            for row in _fetch_dicts(cur)
        ]


def count_user_references(conn, *, user_ids: Iterable[int], references: Sequence[UserReference]) -> dict[int, int]:
    counts = {int(user_id): 0 for user_id in user_ids}
    if not counts or not references:
        return counts

    with conn.cursor() as cur:
        for ref in references:
            query = sql.SQL("SELECT COUNT(*) FROM {}.{} WHERE {} = %s").format(
                sql.Identifier(ref.table_schema),
                sql.Identifier(ref.table_name),
                sql.Identifier(ref.column_name),
            )
            for user_id in counts:
                cur.execute(query, (user_id,))
                counts[user_id] += int(cur.fetchone()[0])
    return counts


def apply_plan(conn, plan: Sequence[ClassifiedTestUser]) -> dict[str, int]:
    totals = {"deleted": 0, "deactivated": 0, "kept": 0, "unchanged": 0}
    with conn.cursor() as cur:
        for item in plan:
            if item.planned_action == "delete":
                cur.execute("DELETE FROM usuarios WHERE id = %s", (item.id,))
                totals["deleted"] += int(cur.rowcount or 0)
            elif item.planned_action == "deactivate":
                cur.execute("UPDATE usuarios SET ativo = 0 WHERE id = %s AND ativo <> 0", (item.id,))
                totals["deactivated"] += int(cur.rowcount or 0)
            elif item.classification == "manter":
                totals["kept"] += 1
            else:
                totals["unchanged"] += 1
    return totals


def _connect(database_url: str):
    return psycopg2.connect(database_url)


def _database_url_from_args(args: argparse.Namespace) -> str:
    if args.database_url:
        return str(args.database_url).strip()
    env_name = str(args.database_url_env or "DATABASE_URL").strip()
    return (os.getenv(env_name, "") or "").strip()


def _result_payload(plan: Sequence[ClassifiedTestUser], *, applied: bool, totals: Mapping[str, int]) -> dict[str, object]:
    return {
        "applied": applied,
        "canonical_test_users": CANONICAL_TEST_USERS,
        "inventory": [asdict(item) for item in plan],
        "totals": {
            "inventory": len(plan),
            "manter": sum(1 for item in plan if item.classification == "manter"),
            "consolidar": sum(1 for item in plan if item.classification == "consolidar"),
            "desativar": sum(1 for item in plan if item.classification == "desativar"),
            "remover": sum(1 for item in plan if item.classification == "remover"),
            **dict(totals),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inventaria e saneia usuarios de teste da frente 19.1 sem tocar usuarios reais."
    )
    parser.add_argument("--database-url", default="", help="DATABASE_URL explicita. Nao sera impressa.")
    parser.add_argument(
        "--database-url-env",
        default="DATABASE_URL",
        help="Variavel de ambiente com DATABASE_URL quando --database-url nao for informado.",
    )
    parser.add_argument(
        "--keep-login",
        action="append",
        default=[],
        help="Login adicional a preservar, por exemplo o E2E_LOGIN canonico do ambiente.",
    )
    parser.add_argument("--apply", action="store_true", help="Aplica o plano. Sem esta flag, roda em dry-run.")
    parser.add_argument(
        "--allow-delete",
        action="store_true",
        help="Permite remover usuarios de teste nao canonicos sem referencias.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Imprime payload JSON.")
    args = parser.parse_args(argv)

    database_url = _database_url_from_args(args)
    if not database_url:
        raise SystemExit("DATABASE_URL ausente. Informe --database-url ou --database-url-env.")

    keep_logins = build_keep_logins([*args.keep_login, os.getenv("E2E_LOGIN", "")])
    with _connect(database_url) as conn:
        rows = fetch_users(conn)
        candidate_ids = [
            int(row["id"])
            for row in rows
            if is_test_login(row.get("login")) or _normalize_login(row.get("login")) in keep_logins
        ]
        references = fetch_user_reference_columns(conn)
        reference_counts = count_user_references(conn, user_ids=candidate_ids, references=references)
        plan = build_sanitization_plan(
            rows,
            reference_counts=reference_counts,
            keep_logins=keep_logins,
            allow_delete=bool(args.allow_delete),
        )
        totals = apply_plan(conn, plan) if args.apply else {"deleted": 0, "deactivated": 0, "kept": 0, "unchanged": 0}
        if args.apply:
            conn.commit()
        else:
            conn.rollback()

    payload = _result_payload(plan, applied=bool(args.apply), totals=totals)
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Inventario de usuarios de teste: {payload['totals']['inventory']}")
        print(f"Canonicos mantidos: {payload['totals']['manter']}")
        print(f"Consolidar: {payload['totals']['consolidar']}")
        print(f"Desativar: {payload['totals']['desativar']}")
        print(f"Remover: {payload['totals']['remover']}")
        print(f"Aplicado: {payload['applied']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
