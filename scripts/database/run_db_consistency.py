"""COMPAT: wrapper historico para consistencia de banco.

Comando oficial: backend/tools/maintenance/run_db_consistency.py.
Manter fino: este arquivo existe apenas para consumidores antigos.
"""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.tools.maintenance.run_db_consistency import main


COMPAT_NOTICE = (
    "Compatibilidade: scripts/database/run_db_consistency.py e alias historico; "
    "use backend/tools/maintenance/run_db_consistency.py."
)


if __name__ == "__main__":
    print(COMPAT_NOTICE, file=sys.stderr)
    raise SystemExit(main())
