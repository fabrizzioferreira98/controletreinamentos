from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.backup import run_backup_job


def main() -> int:
    app = create_app()
    with app.app_context():
        result = run_backup_job(backup_type="agendado")
        print(
            json.dumps(
                {
                    "success": result.success,
                    "status": result.status,
                    "message": result.message,
                    "file_path": result.file_path,
                    "artifacts": result.artifacts,
                    "size_bytes": result.size_bytes,
                    "duration_ms": result.duration_ms,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if result.success:
            return 0
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
