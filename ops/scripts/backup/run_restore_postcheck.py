"""IMPLEMENTATION: validacao pos-restore usada pela entrada canonica.

Comando oficial: backend/tools/maintenance/run_restore_postcheck.py.
Execucao direta fica despriorizada para evitar ambiguidade operacional.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import get_db
from backend.src.controle_treinamentos.infra.restore_validation import (
    run_restore_metadata_blob_validation,
    validate_canonical_restore_contract,
)


DIRECT_ENTRY_NOTICE = (
    "Entrada direta despriorizada: ops/scripts/backup/run_restore_postcheck.py e implementacao; "
    "use backend/tools/maintenance/run_restore_postcheck.py."
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida metadata/blob apos restore de continuidade.")
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Artefato restaurado. Repita para dump, assets, config e manifest.",
    )
    parser.add_argument(
        "--media-root",
        default="",
        help="Raiz restaurada de uploads para validar refs filesystem.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Imprime saida em JSON.")
    args = parser.parse_args()

    media_root = (args.media_root or "").strip()
    if media_root:
        os.environ["MEDIA_STORAGE_ROOT"] = media_root

    app = create_app()
    app.logger.info(
        "Restore postcheck command started.",
        extra={
            "event": "restore_postcheck_start",
            "component": "restore_postcheck_cli",
            "artifact_count": len(args.artifact or []),
            "media_root": media_root,
        },
    )
    try:
        with app.app_context():
            summary = run_restore_metadata_blob_validation(get_db())
    except Exception as exc:
        app.logger.exception(
            "Restore postcheck validation failed unexpectedly.",
            extra={
                "event": "restore_postcheck_unexpected_failure",
                "component": "restore_postcheck_cli",
                "artifact_count": len(args.artifact or []),
            },
        )
        payload = {"ok": False, "error": f"Falha ao validar restore: {exc}"}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    contract = None
    ok = summary.get("status_key") != "unavailable" and int(summary.get("critical_count") or 0) == 0
    if args.artifact:
        contract = validate_canonical_restore_contract(args.artifact, metadata_blob_summary=summary)
        ok = bool(contract["success"])

    result = {
        "ok": ok,
        "post_restore_validation": summary,
    }
    if contract is not None:
        result["restore_contract"] = contract

    log_payload = {
        "event": "restore_postcheck_complete",
        "component": "restore_postcheck_cli",
        "success": bool(ok),
        "status_key": summary.get("status_key"),
        "critical_count": int(summary.get("critical_count") or 0),
        "warning_count": int(summary.get("warning_count") or 0),
        "document_row_count": int(summary.get("document_row_count") or 0),
        "photo_row_count": int(summary.get("photo_row_count") or 0),
        "artifact_count": len(args.artifact or []),
    }
    if contract is not None:
        log_payload.update(
            {
                "restore_kind": contract.get("restore_kind"),
                "missing_components": contract.get("missing_components"),
                "window_mismatch_components": contract.get("window_mismatch_components"),
                "manifest_error": contract.get("manifest_error"),
            }
        )
    if ok:
        app.logger.info("Restore postcheck command completed.", extra=log_payload)
    else:
        app.logger.warning("Restore postcheck command completed with issues.", extra=log_payload)

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=== Restore Postcheck ===")
        print(f"Status metadata/blob: {summary['status_key']}")
        print(f"Criticos: {summary['critical_count']}")
        print(f"Avisos: {summary['warning_count']}")
        print(f"Documentos inventariados: {summary['document_row_count']}")
        print(f"Fotos inventariadas: {summary['photo_row_count']}")
        if contract is not None:
            print(f"Restore canonico: {'sim' if contract['success'] else 'nao'}")
            print(f"Tipo de restore: {contract['restore_kind']}")
            print(f"Componentes faltantes: {contract['missing_components'] or 'nenhum'}")
            print(f"Componentes fora da janela: {contract['window_mismatch_components'] or 'nenhum'}")
            print(f"Manifesto inconsistente: {contract['manifest_error'] or 'nao'}")
        if summary["query_errors"]:
            print(f"Erros de consulta: {summary['query_errors']}")

    return 0 if ok else 2


if __name__ == "__main__":
    print(DIRECT_ENTRY_NOTICE, file=sys.stderr)
    raise SystemExit(main())
