from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


def _resolve_artifact(root: Path, candidate: str) -> Path:
    artifact = Path((candidate or "").strip())
    if artifact.is_absolute():
        return artifact
    return (root / artifact).resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signature_payload(payload: dict) -> str:
    canonical = deepcopy(payload)
    canonical.pop("signature_hmac_sha256", None)
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _compute_signature(payload: dict, signing_key: str) -> str:
    body = _signature_payload(payload).encode("utf-8")
    return hmac.new(signing_key.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True).strip()
    except Exception:
        return "workspace-without-git"


def main() -> int:
    parser = argparse.ArgumentParser(description="Endurece release manifest com hash de artefatos e assinatura HMAC.")
    parser.add_argument("--manifest", required=True, help="Manifest base existente.")
    parser.add_argument("--output", default="", help="Arquivo de saída. Default: sobrescreve o manifest informado.")
    parser.add_argument(
        "--signing-key-env",
        default="RELEASE_EVIDENCE_SIGNING_KEY",
        help="Variável de ambiente com chave HMAC para assinatura (opcional).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    manifest_path = Path(args.manifest).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if (args.output or "").strip() else manifest_path

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        raise SystemExit("Manifest inválido: campo checks deve ser objeto.")

    payload["commit_sha"] = _git_head(root)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    artifact_hashes: dict[str, str] = {}
    for check in checks.values():
        if not isinstance(check, dict):
            continue
        artifacts = check.get("artifacts", [])
        if not isinstance(artifacts, list):
            continue
        for raw in artifacts:
            candidate = str(raw or "").strip()
            if not candidate:
                continue
            artifact_path = _resolve_artifact(root, candidate)
            if not artifact_path.exists() or artifact_path.is_dir():
                raise SystemExit(f"Artefato inexistente/inválido: {candidate}")
            artifact_hashes[candidate] = _sha256_file(artifact_path)
    payload["artifacts_sha256"] = artifact_hashes

    signing_key = (os.getenv(args.signing_key_env, "") or "").strip()
    if signing_key:
        payload["signature_hmac_sha256"] = _compute_signature(payload, signing_key)
    else:
        payload.pop("signature_hmac_sha256", None)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success": True, "manifest": str(output_path), "artifacts_hashed": len(artifact_hashes)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
