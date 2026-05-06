from pathlib import Path
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops.scripts.database.run_db_consistency import main


def _guard_manual_repair(argv: list[str]) -> int | None:
    if "--repair" not in argv:
        return None
    payload = {
        "ok": False,
        "error": "repair_removed_from_canonical_maintenance_path",
        "message": (
            "run_db_consistency.py em maintenance valida apenas schema+dado. "
            "Use backend/tools/manual_unsafe/run_db_repair.py para repair manual/perigoso."
        ),
        "classification": "manual_unsafe_redirect",
        "redirect_command": "backend/tools/manual_unsafe/run_db_repair.py",
    }
    if "--json" in argv:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["message"])
    return 2


def _main(argv: list[str]) -> int:
    blocked = _guard_manual_repair(argv)
    if blocked is not None:
        return blocked
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
