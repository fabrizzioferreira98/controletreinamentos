from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _request(url: str, *, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        return exc.code, body, dict(exc.headers or {})


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test pós-deploy")
    parser.add_argument("--base-url", required=True, help="URL base do ambiente, ex.: https://app.exemplo.com")
    parser.add_argument("--metrics-token", default="", help="Token opcional para /api/internal/metrics (evite CLI).")
    parser.add_argument(
        "--metrics-token-file",
        default="",
        help="Arquivo com METRICS_TOKEN (recomendado para evitar histórico de shell).",
    )
    parser.add_argument(
        "--metrics-token-env",
        default="METRICS_TOKEN",
        help="Variável de ambiente com token de métricas (padrão: METRICS_TOKEN).",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    checks = [
        ("login_page", f"{base_url}/login", {200}),
        ("dashboard_redirect", f"{base_url}/dashboard", {302, 303, 200}),
        ("notificacoes_redirect", f"{base_url}/notificacoes-email", {302, 303, 200}),
    ]

    results: list[dict] = []
    failed = False

    for name, url, expected in checks:
        status, _body, _headers = _request(url)
        ok = status in expected
        results.append({"check": name, "url": url, "status": status, "expected": sorted(expected), "ok": ok})
        if not ok:
            failed = True

    metrics_token = ""
    if args.metrics_token:
        metrics_token = args.metrics_token.strip()
        print(
            "WARN: --metrics-token via CLI expõe risco de histórico. Prefira --metrics-token-file ou variável de ambiente.",
            file=sys.stderr,
        )
    elif args.metrics_token_file:
        try:
            metrics_token = (open(args.metrics_token_file, "r", encoding="utf-8").read() or "").strip()
        except OSError as exc:
            print(json.dumps({"failed": True, "error": "metrics_token_file_error", "detail": str(exc)}, ensure_ascii=False, indent=2))
            return 1
    else:
        metrics_env = (args.metrics_token_env or "").strip() or "METRICS_TOKEN"
        metrics_token = (os.getenv(metrics_env, "") or "").strip()

    metric_headers = {}
    if metrics_token:
        metric_headers["X-Metrics-Token"] = metrics_token
    metric_status, metric_body, _ = _request(f"{base_url}/api/internal/metrics", headers=metric_headers)
    metric_ok = metric_status in {200, 403, 503}
    results.append(
        {
            "check": "internal_metrics",
            "url": f"{base_url}/api/internal/metrics",
            "status": metric_status,
            "expected": [200, 403, 503],
            "ok": metric_ok,
            "note": "200 com token válido; 403 com token inválido; 503 quando METRICS_TOKEN não está configurado",
        }
    )
    if not metric_ok:
        failed = True

    print(json.dumps({"failed": failed, "results": results}, ensure_ascii=False, indent=2))
    if metric_status == 200 and metric_body:
        print("\nmetrics_sample:")
        print(metric_body[:500])

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
