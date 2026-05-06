from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import get_db


def _resolve_password(args: argparse.Namespace) -> str:
    if args.password:
        return args.password
    if args.password_env:
        value = os.getenv(args.password_env, "").strip()
        if value:
            return value
    raise SystemExit("Informe --password ou defina a variavel de ambiente informada em --password-env.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria ou atualiza um usuario administrador.")
    parser.add_argument("--login", required=True, help="Login do usuario administrador.")
    parser.add_argument("--password", help="Senha em texto claro para aplicar no usuario.")
    parser.add_argument(
        "--password-env",
        default="ADMIN_PASSWORD",
        help="Nome da variavel de ambiente que contem a senha quando --password nao for informado.",
    )
    parser.add_argument("--email", default="admin@localhost", help="Email do usuario administrador.")
    parser.add_argument("--name", default="Administradora", help="Nome do usuario administrador.")
    parser.add_argument("--perfil", default="gestora", help="Perfil do usuario.")
    parser.add_argument("--inactive", action="store_true", help="Cria/atualiza o usuario como inativo.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Imprime o resultado em JSON.")
    args = parser.parse_args()

    password = _resolve_password(args)
    app = create_app()

    with app.app_context():
        db = get_db()
        existing = db.execute(
            "SELECT id, login, email, perfil, ativo FROM usuarios WHERE login = %s",
            (args.login,),
        ).fetchone()
        active_flag = 0 if args.inactive else 1
        password_hash = generate_password_hash(password, method="pbkdf2:sha256")

        if existing:
            db.execute(
                """
                UPDATE usuarios
                SET nome = %s,
                    email = %s,
                    senha_hash = %s,
                    perfil = %s,
                    ativo = %s
                WHERE id = %s
                """,
                (
                    args.name,
                    args.email,
                    password_hash,
                    args.perfil,
                    active_flag,
                    existing["id"],
                ),
            )
            action = "updated"
            user_id = existing["id"]
        else:
            created = db.execute(
                """
                INSERT INTO usuarios (nome, login, email, senha_hash, perfil, ativo)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    args.name,
                    args.login,
                    args.email,
                    password_hash,
                    args.perfil,
                    active_flag,
                ),
            ).fetchone()
            action = "created"
            user_id = created["id"]

        db.commit()

    result = {
        "ok": True,
        "action": action,
        "id": int(user_id),
        "login": args.login,
        "email": args.email,
        "perfil": args.perfil,
        "ativo": active_flag,
    }
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"Admin {action}: id={result['id']} login={result['login']} "
            f"perfil={result['perfil']} ativo={result['ativo']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
