#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _iter_log_records(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield line_number, payload


def _collect_matches(log_files: list[Path], request_codes: set[str]) -> dict:
    grouped: dict[str, list[dict]] = {code: [] for code in sorted(request_codes)}
    for log_file in log_files:
        if not log_file.exists():
            continue
        for line_number, payload in _iter_log_records(log_file):
            request_id = str(payload.get("request_id") or "").strip()
            if request_id not in request_codes:
                continue
            grouped[request_id].append(
                {
                    "file": str(log_file),
                    "line": line_number,
                    "timestamp": payload.get("timestamp"),
                    "level": payload.get("level"),
                    "logger": payload.get("logger"),
                    "module": payload.get("module"),
                    "function": payload.get("function"),
                    "message": payload.get("message"),
                    "exception": payload.get("exception"),
                }
            )
    return grouped


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rastreia códigos de erro/request_id em logs JSON estruturados da aplicação."
        )
    )
    parser.add_argument(
        "--codes",
        nargs="+",
        required=True,
        help="Lista de códigos/request_id exibidos ao usuário (hex).",
    )
    parser.add_argument(
        "--log-file",
        action="append",
        required=True,
        help="Arquivo de log JSONL (pode repetir --log-file múltiplas vezes).",
    )
    args = parser.parse_args()

    request_codes = {code.strip() for code in args.codes if code and code.strip()}
    log_files = [Path(item).expanduser().resolve() for item in args.log_file]
    grouped = _collect_matches(log_files, request_codes)

    found = {code: entries for code, entries in grouped.items() if entries}
    not_found = sorted([code for code, entries in grouped.items() if not entries])
    output = {
        "success": True,
        "searched_codes": sorted(request_codes),
        "log_files": [str(path) for path in log_files],
        "found_codes": sorted(found.keys()),
        "not_found_codes": not_found,
        "matches": found,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

