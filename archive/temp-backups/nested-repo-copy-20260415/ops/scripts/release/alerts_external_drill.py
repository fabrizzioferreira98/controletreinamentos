from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


def _build_payload(*, source: str, severity: str, message: str) -> dict:
    return {
        "event": "release_alert_drill",
        "source": source,
        "severity": severity,
        "message": message,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Drill de alerta externo para release.")
    parser.add_argument("--webhook-url", default="", help="Webhook HTTP de alerta (Slack/PagerDuty/etc).")
    parser.add_argument(
        "--webhook-url-file",
        default="",
        help="Arquivo contendo webhook URL (recomendado para evitar segredo no histórico do shell).",
    )
    parser.add_argument(
        "--webhook-url-env",
        default="ALERTS_TEST_WEBHOOK_URL",
        help="Variável de ambiente com webhook URL (padrão: ALERTS_TEST_WEBHOOK_URL).",
    )
    parser.add_argument("--source", default="release-gate")
    parser.add_argument("--severity", default="warning")
    parser.add_argument("--message", default="Teste controlado de alerta externo para validacao de release.")
    parser.add_argument("--acknowledged-by", default="", help="Responsável que confirmou o alerta.")
    parser.add_argument("--escalation-target", default="", help="Destino de escalonamento validado.")
    parser.add_argument("--require-ack", action="store_true", help="Falha se não houver ack/escalonamento informado.")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    webhook_env_name = (args.webhook_url_env or "").strip() or "ALERTS_TEST_WEBHOOK_URL"
    webhook_url = ""
    if args.webhook_url:
        webhook_url = args.webhook_url.strip()
    elif args.webhook_url_file:
        try:
            webhook_url = (open(args.webhook_url_file, "r", encoding="utf-8").read() or "").strip()
        except OSError as exc:
            print(
                json.dumps(
                    {
                        "success": False,
                        "message": "Não foi possível ler arquivo de webhook.",
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
    else:
        webhook_url = (os.getenv(webhook_env_name, "") or "").strip()
    if not webhook_url:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "Webhook de alerta não configurado. Use --webhook-url-file ou variável de ambiente.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    if args.webhook_url:
        print(
            f"WARN: webhook URL via CLI pode vazar no histórico. Prefira --webhook-url-file ou {webhook_env_name}.",
            file=sys.stderr,
        )

    payload = _build_payload(source=args.source, severity=args.severity, message=args.message)
    request = urllib.request.Request(
        webhook_url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=max(3, int(args.timeout))) as response:
            body = response.read()
            ok = 200 <= response.status < 300
            acknowledged_by = (args.acknowledged_by or "").strip()
            escalation_target = (args.escalation_target or "").strip()
            acknowledged = bool(acknowledged_by and escalation_target)
            if args.require_ack and not acknowledged:
                ok = False
            result = {
                "success": ok,
                "status": response.status,
                "response_body_sha256": hashlib.sha256(body).hexdigest() if body else "",
                "response_body_length": len(body or b""),
                "payload": payload,
                "acknowledged": acknowledged,
                "acknowledged_by": acknowledged_by,
                "escalation_target": escalation_target,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if ok else 1
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        print(
            json.dumps(
                {
                    "success": False,
                    "status": exc.code,
                    "error": "http_error",
                    "response_body_sha256": hashlib.sha256(body).hexdigest() if body else "",
                    "response_body_length": len(body or b""),
                    "payload": payload,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    except urllib.error.URLError as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "network_error",
                    "detail": str(exc.reason),
                    "payload": payload,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
