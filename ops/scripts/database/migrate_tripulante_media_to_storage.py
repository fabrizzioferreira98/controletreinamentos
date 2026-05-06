from __future__ import annotations

import base64
import binascii
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import get_db
from backend.src.controle_treinamentos.infra.media_storage import (
    delete_media_ref,
    write_training_attachment,
    write_tripulante_document,
    write_tripulante_photo,
)

_PHOTO_DATA_URI_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,", re.IGNORECASE)


def _decode_photo_data_uri(raw_value: str):
    value = (raw_value or "").strip()
    match = _PHOTO_DATA_URI_RE.match(value)
    if not match:
        raise ValueError("Foto base64 invalida para migracao.")
    image_format = match.group(1).lower()
    mime_type = "image/jpeg" if image_format in {"jpg", "jpeg"} else f"image/{image_format}"
    try:
        payload = base64.b64decode(value.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Foto base64 corrompida.") from exc
    return payload, mime_type


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    dry_run = "--dry-run" in argv

    app = create_app()
    summary = {
        "dry_run": dry_run,
        "tripulante_fotos_migradas": 0,
        "tripulante_documentos_migrados": 0,
        "treinamento_anexos_migrados": 0,
    }

    with app.app_context():
        db = get_db()

        photo_rows = db.execute(
            """
            SELECT id, nome, foto_base64
            FROM tripulantes
            WHERE foto_base64 IS NOT NULL
              AND TRIM(foto_base64) <> ''
              AND (foto_storage_ref IS NULL OR TRIM(foto_storage_ref) = '')
            ORDER BY id
            """
        ).fetchall()
        for row in photo_rows:
            payload, mime_type = _decode_photo_data_uri(row["foto_base64"])
            if dry_run:
                summary["tripulante_fotos_migradas"] += 1
                continue
            storage_ref = None
            try:
                storage_ref = write_tripulante_photo(int(row["id"]), row.get("nome"), payload, mime_type=mime_type)
                db.execute(
                    """
                    UPDATE tripulantes
                    SET foto_storage_ref = %s,
                        foto_mime_type = %s,
                        foto_base64 = NULL,
                        possui_foto = TRUE
                    WHERE id = %s
                    """,
                    (storage_ref, mime_type, int(row["id"])),
                )
                db.commit()
                summary["tripulante_fotos_migradas"] += 1
            except Exception:
                db.conn.rollback()
                delete_media_ref(storage_ref)
                raise

        file_rows = db.execute(
            """
            SELECT a.id, a.tripulante_id, c.nome, a.nome_interno, a.arquivo_pdf
            FROM tripulante_arquivos_pdf a
            JOIN tripulantes c ON c.id = a.tripulante_id
            WHERE a.arquivo_pdf IS NOT NULL
              AND (
                    a.storage_ref IS NULL
                    OR a.storage_ref = 'db:bytea'
                    OR TRIM(a.storage_ref) = ''
              )
            ORDER BY id
            """
        ).fetchall()
        for row in file_rows:
            if dry_run:
                summary["tripulante_documentos_migrados"] += 1
                continue
            storage_ref = None
            try:
                storage_ref = write_tripulante_document(
                    int(row["tripulante_id"]),
                    row.get("nome"),
                    row["nome_interno"],
                    bytes(row["arquivo_pdf"]),
                )
                db.execute(
                    """
                    UPDATE tripulante_arquivos_pdf
                    SET storage_ref = %s,
                        arquivo_pdf = NULL
                    WHERE id = %s
                    """,
                    (storage_ref, int(row["id"])),
                )
                db.commit()
                summary["tripulante_documentos_migrados"] += 1
            except Exception:
                db.conn.rollback()
                delete_media_ref(storage_ref)
                raise

        training_rows = db.execute(
            """
            SELECT a.id, a.treinamento_id, a.nome_interno, a.arquivo_pdf, t.tripulante_id, c.nome
            FROM treinamento_anexos_pdf a
            JOIN treinamentos t ON t.id = a.treinamento_id
            JOIN tripulantes c ON c.id = t.tripulante_id
            WHERE a.arquivo_pdf IS NOT NULL
              AND (a.storage_ref IS NULL OR a.storage_ref = 'db:bytea' OR TRIM(a.storage_ref) = '')
            ORDER BY a.id
            """
        ).fetchall()
        for row in training_rows:
            if dry_run:
                summary["treinamento_anexos_migrados"] += 1
                continue
            storage_ref = None
            try:
                storage_ref = write_training_attachment(
                    int(row["tripulante_id"]),
                    row.get("nome"),
                    int(row["treinamento_id"]),
                    row["nome_interno"],
                    bytes(row["arquivo_pdf"]),
                )
                db.execute(
                    """
                    UPDATE treinamento_anexos_pdf
                    SET storage_ref = %s,
                        arquivo_pdf = NULL
                    WHERE id = %s
                    """,
                    (storage_ref, int(row["id"])),
                )
                db.commit()
                summary["treinamento_anexos_migrados"] += 1
            except Exception:
                db.conn.rollback()
                delete_media_ref(storage_ref)
                raise

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
