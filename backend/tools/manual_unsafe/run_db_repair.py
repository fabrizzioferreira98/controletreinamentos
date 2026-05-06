from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops.scripts.database.run_db_consistency import REPAIR_ACK_TOKEN, main


def _forward_args(argv: list[str]) -> list[str]:
    forwarded = ["--repair", "--repair-ack", REPAIR_ACK_TOKEN]
    skip_next = False
    for idx, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg in {"--repair", "--repair-ack"}:
            if arg == "--repair-ack" and idx + 1 < len(argv):
                skip_next = True
            continue
        forwarded.append(arg)
    return forwarded


if __name__ == "__main__":
    raise SystemExit(main(_forward_args(sys.argv[1:])))
