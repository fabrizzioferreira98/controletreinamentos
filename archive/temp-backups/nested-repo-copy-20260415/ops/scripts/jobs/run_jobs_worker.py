from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


import os
import time

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.jobs import process_background_jobs


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return max(minimum, default)
    try:
        return max(minimum, int(raw))
    except ValueError:
        return max(minimum, default)


def main() -> int:
    app = create_app()
    max_jobs = _env_int("JOB_WORKER_MAX_JOBS", 25, minimum=1)
    drain_mode = (os.getenv("JOB_WORKER_DRAIN", "0") or "").strip().lower() in {"1", "true", "yes", "on"}
    max_cycles = _env_int("JOB_WORKER_MAX_CYCLES", 20, minimum=1)
    idle_sleep_seconds = _env_int("JOB_WORKER_IDLE_SLEEP_SECONDS", 2, minimum=1)

    aggregated = {"processed": 0, "succeeded": 0, "failed": 0, "dead_letter": 0}
    cycles = 0
    while True:
        cycles += 1
        summary = process_background_jobs(app, max_jobs=max_jobs, worker_id=f"cli:{os.getpid()}:c{cycles}")
        for key in aggregated:
            aggregated[key] += int(summary.get(key, 0) or 0)
        print(
            "Ciclo {cycle}: processados={processed} sucesso={succeeded} falha={failed} dead-letter={dead_letter}".format(
                cycle=cycles,
                **summary,
            )
        )
        if not drain_mode:
            break
        if summary["processed"] == 0:
            break
        if cycles >= max_cycles:
            print(f"Limite de ciclos atingido ({max_cycles}). Encerrando worker em modo drain.")
            break
        time.sleep(idle_sleep_seconds)

    print(
        "Resumo final: processados={processed} | sucesso={succeeded} | falha={failed} | dead-letter={dead_letter}".format(
            **aggregated
        )
    )
    if aggregated["dead_letter"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
