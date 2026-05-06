from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.src.controle_treinamentos import create_app


CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
DEFAULT_USER_LOGIN = "pre29_admin"
DEFAULT_USER_PASSWORD = "Pre29!Admin#2026"
DEFAULT_TRIPULANTE_CPF = "29000000001"
DEFAULT_TREINAMENTO_CODIGO = "PRE293"


def _extract_csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    if not match:
        raise AssertionError("csrf_token not found in HTML response")
    return match.group(1)


def _ensure_file(media_root: Path, storage_ref: str, content: bytes) -> str:
    relative_path = storage_ref.removeprefix("fs:")
    target = media_root / Path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return str(target)


def _seed_operational_records(*, db_url: str, media_root: Path) -> dict[str, object]:
    photo_bytes = b"RIFF\x18\x00\x00\x00WEBPVP8 \x0c\x00\x00\x000\x01\x00\x9d\x01*\x01\x00\x01\x00\x00\x02\x00"
    trip_document_bytes = b"%PDF-1.4\n% pre29.3 trip document\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    training_document_bytes = (
        b"%PDF-1.4\n% pre29.3 training attachment\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    )

    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM usuarios WHERE login = %s", (DEFAULT_USER_LOGIN,))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"bootstrap user {DEFAULT_USER_LOGIN!r} not found")
            user_id = int(row[0])

            cur.execute("SELECT id FROM tipos_treinamento WHERE codigo = %s", (DEFAULT_TREINAMENTO_CODIGO,))
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    """
                    INSERT INTO tipos_treinamento (
                        nome,
                        codigo,
                        descricao,
                        periodicidade_meses,
                        modalidade,
                        exige_equipamento,
                        ativo
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        "Pre29 Operacional",
                        DEFAULT_TREINAMENTO_CODIGO,
                        "Seed operacional pre29.3",
                        12,
                        "segmentado",
                        0,
                        1,
                    ),
                )
                tipo_treinamento_id = int(cur.fetchone()[0])
            else:
                tipo_treinamento_id = int(row[0])

            cur.execute(
                """
                INSERT INTO tripulantes (
                    nome,
                    cpf,
                    licenca_anac,
                    email,
                    telefone,
                    base,
                    status,
                    ativo,
                    funcao_operacional,
                    categoria_operacional,
                    sdea_ativo,
                    instrutor_ativo,
                    checador_ativo,
                    elegivel_adicional_excepcional,
                    observacoes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cpf) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    licenca_anac = EXCLUDED.licenca_anac,
                    email = EXCLUDED.email,
                    telefone = EXCLUDED.telefone,
                    base = EXCLUDED.base,
                    status = EXCLUDED.status,
                    ativo = EXCLUDED.ativo,
                    funcao_operacional = EXCLUDED.funcao_operacional,
                    categoria_operacional = EXCLUDED.categoria_operacional,
                    sdea_ativo = EXCLUDED.sdea_ativo,
                    instrutor_ativo = EXCLUDED.instrutor_ativo,
                    checador_ativo = EXCLUDED.checador_ativo,
                    elegivel_adicional_excepcional = EXCLUDED.elegivel_adicional_excepcional,
                    observacoes = EXCLUDED.observacoes
                RETURNING id
                """,
                (
                    "Tripulante Pre29.3",
                    DEFAULT_TRIPULANTE_CPF,
                    "290001",
                    "tripulante.pre293@example.com",
                    "11999990001",
                    "São Paulo",
                    "ativo",
                    1,
                    "copiloto",
                    "A",
                    0,
                    0,
                    0,
                    0,
                    "Seed operacional pre29.3",
                ),
            )
            tripulante_id = int(cur.fetchone()[0])

            photo_ref = f"fs:tripulantes/tripulante-{tripulante_id}/fotos/foto-pre293.webp"
            trip_document_ref = (
                f"fs:tripulantes/tripulante-{tripulante_id}/documentos/documento-pre293.pdf"
            )
            photo_path = _ensure_file(media_root, photo_ref, photo_bytes)
            trip_document_path = _ensure_file(media_root, trip_document_ref, trip_document_bytes)
            trip_document_hash = hashlib.sha256(trip_document_bytes).hexdigest()

            cur.execute(
                """
                UPDATE tripulantes
                SET foto_storage_ref = %s,
                    foto_mime_type = %s,
                    possui_foto = TRUE,
                    foto_base64 = NULL
                WHERE id = %s
                """,
                (photo_ref, "image/webp", tripulante_id),
            )

            cur.execute(
                "DELETE FROM tripulante_arquivos_pdf WHERE tripulante_id = %s AND nome_interno = %s",
                (tripulante_id, "documento-pre293.pdf"),
            )
            cur.execute(
                """
                INSERT INTO tripulante_arquivos_pdf (
                    tripulante_id,
                    tipo_documento,
                    nome_original,
                    nome_interno,
                    mime_type,
                    tamanho_bytes,
                    storage_ref,
                    arquivo_hash,
                    status,
                    enviado_por
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tripulante_id,
                    "geral",
                    "documento-pre293.pdf",
                    "documento-pre293.pdf",
                    "application/pdf",
                    len(trip_document_bytes),
                    trip_document_ref,
                    trip_document_hash,
                    "ativo",
                    user_id,
                ),
            )

            cur.execute(
                """
                SELECT id
                FROM treinamentos
                WHERE tripulante_id = %s
                  AND observacao = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (tripulante_id, "Seed operacional pre29.3"),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    """
                    INSERT INTO treinamentos (
                        tripulante_id,
                        tipo_treinamento_id,
                        data_realizacao,
                        data_vencimento,
                        observacao
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        tripulante_id,
                        tipo_treinamento_id,
                        date.today(),
                        date.today() + timedelta(days=365),
                        "Seed operacional pre29.3",
                    ),
                )
                treinamento_id = int(cur.fetchone()[0])
            else:
                treinamento_id = int(row[0])

            training_document_ref = f"fs:treinamentos/treinamento-{treinamento_id}/anexos/anexo-pre293.pdf"
            training_document_path = _ensure_file(media_root, training_document_ref, training_document_bytes)
            training_document_hash = hashlib.sha256(training_document_bytes).hexdigest()

            cur.execute(
                "DELETE FROM treinamento_anexos_pdf WHERE treinamento_id = %s AND nome_interno = %s",
                (treinamento_id, "anexo-pre293.pdf"),
            )
            cur.execute(
                """
                INSERT INTO treinamento_anexos_pdf (
                    treinamento_id,
                    nome_original,
                    nome_interno,
                    mime_type,
                    tamanho_bytes,
                    storage_ref,
                    arquivo_hash,
                    status,
                    enviado_por
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    treinamento_id,
                    "anexo-pre293.pdf",
                    "anexo-pre293.pdf",
                    "application/pdf",
                    len(training_document_bytes),
                    training_document_ref,
                    training_document_hash,
                    "ativo",
                    user_id,
                ),
            )
        conn.commit()

    return {
        "user_login": DEFAULT_USER_LOGIN,
        "tripulante_id": tripulante_id,
        "treinamento_id": treinamento_id,
        "tipo_treinamento_id": tipo_treinamento_id,
        "photo_ref": photo_ref,
        "photo_path": photo_path,
        "trip_document_ref": trip_document_ref,
        "trip_document_path": trip_document_path,
        "training_document_ref": training_document_ref,
        "training_document_path": training_document_path,
    }


def _probe_auth_session() -> dict[str, object]:
    app = create_app()
    client = app.test_client()

    login_page = client.get("/login")
    login_html = login_page.get_data(as_text=True)
    login_csrf = _extract_csrf(login_html)
    login_response = client.post(
        "/login",
        data={
            "csrf_token": login_csrf,
            "login": DEFAULT_USER_LOGIN,
            "senha": DEFAULT_USER_PASSWORD,
        },
        follow_redirects=False,
    )

    session_response = client.get("/api/v1/session")
    session_payload = session_response.get_json() or {}
    csrf_token = str(session_payload.get("csrf_token") or "")

    dashboard_response = client.get("/dashboard", follow_redirects=False)
    logout_response = client.post("/api/v1/session/logout", headers={"X-CSRFToken": csrf_token})
    logout_payload = logout_response.get_json() or {}
    post_logout_dashboard = client.get("/dashboard", follow_redirects=False)
    post_logout_session = client.get("/api/v1/session")
    post_logout_session_payload = post_logout_session.get_json() or {}

    return {
        "success": (
            login_page.status_code == 200
            and login_response.status_code in {302, 303}
            and bool(session_payload.get("authenticated"))
            and bool(csrf_token)
            and dashboard_response.status_code in {200, 302, 303}
            and logout_response.status_code == 200
            and bool(logout_payload.get("success"))
            and not bool(post_logout_session_payload.get("authenticated"))
            and post_logout_dashboard.status_code in {302, 303}
        ),
        "login_page_ok": login_page.status_code == 200,
        "login_success_redirect": (
            login_response.status_code in {302, 303}
            and "/login" not in str(login_response.headers.get("Location") or "")
        ),
        "session_authenticated": bool(session_payload.get("authenticated")),
        "csrf_token_present": bool(csrf_token),
        "dashboard_authenticated_status": dashboard_response.status_code,
        "logout_ok": logout_response.status_code == 200 and bool(logout_payload.get("success")),
        "post_logout_redirect_ok": (
            post_logout_dashboard.status_code in {302, 303}
            and "/login" in str(post_logout_dashboard.headers.get("Location") or "")
        ),
        "login_redirect_location": str(login_response.headers.get("Location") or ""),
        "post_logout_dashboard_location": str(post_logout_dashboard.headers.get("Location") or ""),
        "session_payload": session_payload,
        "logout_payload": logout_payload,
        "post_logout_session_payload": post_logout_session_payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed operacional minimo + prova real de auth/session para pre29.")
    parser.add_argument("--auth-output", required=True, help="Arquivo JSON de evidencia auth/session.")
    parser.add_argument("--seed-output", required=True, help="Arquivo JSON com o seed operacional aplicado.")
    parser.add_argument(
        "--media-root",
        default=os.getenv("MEDIA_STORAGE_ROOT", ""),
        help="Raiz do storage filesystem.",
    )
    args = parser.parse_args()

    db_url = (os.getenv("DATABASE_URL", "") or "").strip()
    if not db_url:
        print(json.dumps({"success": False, "error": "DATABASE_URL not configured"}))
        return 1

    media_root_raw = (args.media_root or "").strip()
    if not media_root_raw:
        print(json.dumps({"success": False, "error": "MEDIA_STORAGE_ROOT not configured"}))
        return 1

    media_root = Path(media_root_raw).expanduser().resolve()
    media_root.mkdir(parents=True, exist_ok=True)

    seed_payload = _seed_operational_records(db_url=db_url, media_root=media_root)
    auth_payload = _probe_auth_session()

    auth_output = Path(args.auth_output).expanduser().resolve()
    seed_output = Path(args.seed_output).expanduser().resolve()
    auth_output.parent.mkdir(parents=True, exist_ok=True)
    seed_output.parent.mkdir(parents=True, exist_ok=True)
    auth_output.write_text(json.dumps(auth_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    seed_output.write_text(json.dumps(seed_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "success": bool(auth_payload.get("success")),
                "auth_output": str(auth_output),
                "seed_output": str(seed_output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if auth_payload.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
