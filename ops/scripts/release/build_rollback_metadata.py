from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


_EXPLICIT_INSTANCE_PATTERNS = (
    re.compile(r"^x-release-instance-id:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^x-release-id:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^x-app-instance:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
)

_VOLATILE_HEADER_NAMES = {
    "date",
    "set-cookie",
    "content-length",
    "x-request-id",
    "x-runtime",
    "cf-ray",
    "cf-cache-status",
}


def _extract_runtime_id(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    for pattern in _EXPLICIT_INSTANCE_PATTERNS:
        match = pattern.search(text)
        if match:
            value = (match.group(1) or "").strip()
            if value:
                return value

    normalized_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        header_name, header_value = line.split(":", 1)
        key = header_name.strip().lower()
        if key in _VOLATILE_HEADER_NAMES:
            continue
        value = header_value.strip()
        if not value:
            continue
        normalized_lines.append(f"{key}:{value}")

    if not normalized_lines:
        return None

    normalized = "\n".join(sorted(normalized_lines))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"runtime:{digest}"


def _load_smoke(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera metadados auditaveis do rollback drill por identificador de runtime/instancia."
    )
    parser.add_argument("--header-before", required=True)
    parser.add_argument("--header-rollback", required=True)
    parser.add_argument("--header-forward", required=True)
    parser.add_argument("--smoke-before", required=True)
    parser.add_argument("--smoke-rollback", required=True)
    parser.add_argument("--smoke-forward", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    before_id = _extract_runtime_id(Path(args.header_before))
    rollback_id = _extract_runtime_id(Path(args.header_rollback))
    forward_id = _extract_runtime_id(Path(args.header_forward))

    smoke_before = _load_smoke(Path(args.smoke_before)) or {}
    smoke_rollback = _load_smoke(Path(args.smoke_rollback)) or {}
    smoke_forward = _load_smoke(Path(args.smoke_forward)) or {}

    smoke_ok = all(not bool(payload.get("failed")) for payload in (smoke_before, smoke_rollback, smoke_forward))
    runtime_ids = [item for item in (before_id, rollback_id, forward_id) if item]
    ids_ok = len(runtime_ids) == 3 and len(set(runtime_ids)) >= 2

    payload = {
        "success": bool(smoke_ok and ids_ok),
        "before_runtime_id": before_id or "",
        "rollback_runtime_id": rollback_id or "",
        "forward_runtime_id": forward_id or "",
        "smoke_before_ok": not bool(smoke_before.get("failed")),
        "smoke_rollback_ok": not bool(smoke_rollback.get("failed")),
        "smoke_forward_ok": not bool(smoke_forward.get("failed")),
    }

    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
