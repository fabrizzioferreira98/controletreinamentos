from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.db import execute_schema_bootstrap, get_db, schema_consistency_report


def main() -> int:
    app = create_app()

    try:
        with app.app_context():
            db = get_db()
            execute_schema_bootstrap(db)
            report = schema_consistency_report(db)
    except Exception as exc:
        print(f"Falha ao executar bootstrap estrutural do banco: {exc}")
        return 1

    if not report["is_consistent"]:
        print("Bootstrap estrutural concluido com pendencias.")
        print(f"Tabelas faltantes: {report['missing_tables'] or 'nenhuma'}")
        print(f"Colunas faltantes: {report['missing_columns'] or 'nenhuma'}")
        return 2

    print("Bootstrap estrutural concluido com schema consistente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
