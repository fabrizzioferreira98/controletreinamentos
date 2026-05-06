from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.application.tripulante_media import load_tripulante_photo_payload
from backend.src.controle_treinamentos.db import get_db
from backend.src.controle_treinamentos.infra.media_storage import delete_media_ref, write_tripulante_photo


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(f"Arquivo de ambiente nao encontrado: {env_path}")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _mime_from_path(path: Path, fallback: str = "image/jpeg") -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return fallback


def _legacy_path_for_ref(storage_ref: str, legacy_root: Path | None) -> Path | None:
    if not legacy_root or not storage_ref.startswith("fs:"):
        return None
    relative = storage_ref[3:].replace("\\", "/").lstrip("/")
    if not relative or ".." in Path(relative).parts:
        return None
    candidate = legacy_root / relative
    return candidate if candidate.exists() and candidate.is_file() else None


def _all_photo_rows(db) -> list[dict]:
    rows = db.execute(
        """
        SELECT
            id,
            nome,
            foto_base64,
            foto_storage_ref,
            foto_mime_type,
            possui_foto
        FROM tripulantes
        WHERE COALESCE(possui_foto, FALSE) = TRUE
           OR (foto_base64 IS NOT NULL AND TRIM(foto_base64) <> '')
           OR (foto_storage_ref IS NOT NULL AND TRIM(foto_storage_ref) <> '')
        ORDER BY id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _update_photo_state(
    db,
    *,
    tripulante_id: int,
    foto_storage_ref,
    foto_mime_type,
    possui_foto: bool,
) -> None:
    db.execute(
        """
        UPDATE tripulantes
        SET foto_storage_ref = %s,
            foto_mime_type = %s,
            foto_base64 = NULL,
            possui_foto = %s
        WHERE id = %s
        """,
        (foto_storage_ref, foto_mime_type, bool(possui_foto), int(tripulante_id)),
    )


def reconcile_tripulante_photos(*, apply: bool, legacy_root: Path | None) -> dict:
    app = create_app()
    summary = {
        "apply": apply,
        "checked": 0,
        "servible_storage": 0,
        "migrated_base64": 0,
        "migrated_legacy_file": 0,
        "marked_without_photo": 0,
        "unchanged": 0,
        "inconsistent": [],
    }

    with app.app_context():
        db = get_db()
        for row in _all_photo_rows(db):
            summary["checked"] += 1
            tripulante_id = int(row["id"])
            storage_ref = str(row.get("foto_storage_ref") or "").strip()
            payload = load_tripulante_photo_payload(row)
            if payload and payload.get("source") == "storage":
                summary["servible_storage"] += 1
                if not row.get("possui_foto") or not row.get("foto_mime_type"):
                    if apply:
                        _update_photo_state(
                            db,
                            tripulante_id=tripulante_id,
                            foto_storage_ref=storage_ref,
                            foto_mime_type=payload["mime_type"],
                            possui_foto=True,
                        )
                    else:
                        summary["unchanged"] += 1
                continue

            if payload and payload.get("source") == "base64":
                new_ref = None
                if apply:
                    try:
                        new_ref = write_tripulante_photo(
                            tripulante_id,
                            row.get("nome"),
                            payload["payload_bytes"],
                            mime_type=payload["mime_type"],
                        )
                        _update_photo_state(
                            db,
                            tripulante_id=tripulante_id,
                            foto_storage_ref=new_ref,
                            foto_mime_type=payload["mime_type"],
                            possui_foto=True,
                        )
                    except Exception:
                        delete_media_ref(new_ref)
                        raise
                summary["migrated_base64"] += 1
                continue

            legacy_path = _legacy_path_for_ref(storage_ref, legacy_root)
            if legacy_path:
                mime_type = _mime_from_path(legacy_path, fallback=(row.get("foto_mime_type") or "image/jpeg"))
                new_ref = None
                if apply:
                    try:
                        new_ref = write_tripulante_photo(
                            tripulante_id,
                            row.get("nome"),
                            legacy_path.read_bytes(),
                            mime_type=mime_type,
                        )
                        _update_photo_state(
                            db,
                            tripulante_id=tripulante_id,
                            foto_storage_ref=new_ref,
                            foto_mime_type=mime_type,
                            possui_foto=True,
                        )
                    except Exception:
                        delete_media_ref(new_ref)
                        raise
                summary["migrated_legacy_file"] += 1
                continue

            if apply and row.get("possui_foto"):
                _update_photo_state(
                    db,
                    tripulante_id=tripulante_id,
                    foto_storage_ref=storage_ref or None,
                    foto_mime_type=row.get("foto_mime_type") or None,
                    possui_foto=False,
                )
            summary["marked_without_photo"] += 1
            summary["inconsistent"].append(
                {
                    "tripulante_id": tripulante_id,
                    "foto_storage_ref": storage_ref,
                    "reason": "photo_reference_not_servible",
                }
            )

        if apply:
            db.commit()

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcilia sinais e midia de fotos de Tripulantes.")
    parser.add_argument("--apply", action="store_true", help="Persiste as correcoes. Sem esta flag, roda em dry-run.")
    parser.add_argument("--env-file", help="Arquivo .env do ambiente alvo.")
    parser.add_argument("--legacy-root", help="Raiz de storage antigo para recuperar refs fs: quebradas.")
    args = parser.parse_args(argv)

    _load_env_file(args.env_file)
    legacy_root = Path(args.legacy_root).resolve() if args.legacy_root else None
    summary = reconcile_tripulante_photos(apply=bool(args.apply), legacy_root=legacy_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
