from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import execute_seed_bootstrap, get_db


def main() -> int:
    app = create_app()

    try:
        with app.app_context():
            db = get_db()
            execute_seed_bootstrap(db)
    except Exception as exc:
        print(f"Falha ao executar bootstrap de dados minimos: {exc}")
        return 1

    print(
        "Bootstrap de dados minimos concluido. "
        "Bases, defaults operacionais e seeds idempotentes aplicados."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
