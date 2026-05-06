from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401, ANN001
        return None


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _request(url: str, *, headers: dict[str, str] | None = None, follow_redirects: bool = False) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    opener = urllib.request.build_opener() if follow_redirects else urllib.request.build_opener(_NoRedirectHandler)
    started = time.perf_counter()
    try:
        with opener.open(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            status = int(resp.status)
            response_headers = dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        status = int(exc.code)
        response_headers = dict(exc.headers or {})
    except urllib.error.URLError as exc:
        return {
            "url": url,
            "status": 0,
            "ok": False,
            "error": "url_error",
            "detail": str(exc.reason),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "headers": {},
            "release_headers": {},
            "body_sample": "",
        }

    header_lookup = {key.lower(): value for key, value in response_headers.items()}

    def header(name: str) -> str:
        return str(header_lookup.get(name.lower()) or "")

    release_headers = {
        "X-Release-ID": header("X-Release-ID"),
        "X-Release-Instance-ID": header("X-Release-Instance-ID"),
        "X-Request-ID": header("X-Request-ID"),
        "X-Correlation-ID": header("X-Correlation-ID"),
    }
    return {
        "url": url,
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "headers": {
            key: header(key)
            for key in (
                "Content-Type",
                "Location",
                "Cache-Control",
                "X-Release-ID",
                "X-Release-Instance-ID",
                "X-Request-ID",
                "X-Correlation-ID",
            )
            if header(key)
        },
        "release_headers": release_headers,
        "_body": body,
        "body_sample": body[:500],
    }


def _json_body(response: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(str(response.get("_body") or response.get("body_sample") or "{}"))
    except json.JSONDecodeError:
        return {}


def _load_metrics_token(args: argparse.Namespace) -> str:
    if args.metrics_token:
        print(
            "WARN: --metrics-token via CLI exposes shell history risk. Prefer --metrics-token-file or environment.",
            file=sys.stderr,
        )
        return str(args.metrics_token).strip()
    if args.metrics_token_file:
        return (Path(args.metrics_token_file).read_text(encoding="utf-8") or "").strip()
    metrics_env = (args.metrics_token_env or "").strip() or "METRICS_TOKEN"
    return (os.getenv(metrics_env, "") or "").strip()


def _release_headers_ok(
    response: dict[str, Any],
    *,
    expected_release_id: str,
    expected_release_instance_id: str,
) -> tuple[bool, dict[str, str]]:
    headers = response.get("release_headers") if isinstance(response.get("release_headers"), dict) else {}
    release_id = str(headers.get("X-Release-ID") or "").strip()
    instance_id = str(headers.get("X-Release-Instance-ID") or "").strip()
    ok = bool(release_id and instance_id)
    if expected_release_id:
        ok = ok and release_id == expected_release_id
    if expected_release_instance_id:
        ok = ok and instance_id == expected_release_instance_id
    return ok, {
        "release_id": release_id,
        "release_instance_id": instance_id,
        "request_id": str(headers.get("X-Request-ID") or "").strip(),
        "correlation_id": str(headers.get("X-Correlation-ID") or "").strip(),
    }


def _check_http(
    *,
    name: str,
    url: str,
    expected: set[int],
    expected_release_id: str,
    expected_release_instance_id: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = _request(url, headers=headers)
    response["check"] = name
    response["expected"] = sorted(expected)
    response["ok"] = int(response.get("status", 0) or 0) in expected
    header_ok, ids = _release_headers_ok(
        response,
        expected_release_id=expected_release_id,
        expected_release_instance_id=expected_release_instance_id,
    )
    response["runtime_identity"] = ids
    response["runtime_identity_ok"] = header_ok
    return response


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post-deploy smoke test with material JSON evidence.")
    parser.add_argument("--base-url", required=True, help="Environment base URL, e.g. https://app.example.com")
    parser.add_argument(
        "--metrics-url",
        default="",
        help="Optional metrics URL. Defaults to <base-url>/api/internal/metrics.",
    )
    parser.add_argument("--metrics-token", default="", help="Optional token for /api/internal/metrics.")
    parser.add_argument(
        "--metrics-token-file",
        default="",
        help="File containing METRICS_TOKEN. Prefer this over CLI token.",
    )
    parser.add_argument(
        "--metrics-token-env",
        default="METRICS_TOKEN",
        help="Environment variable containing the metrics token.",
    )
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    parser.add_argument("--environment", default=os.getenv("APP_ENV", ""))
    parser.add_argument("--release-id", default=os.getenv("APP_RELEASE_ID", ""))
    parser.add_argument("--release-instance-id", default=os.getenv("APP_RELEASE_INSTANCE_ID", ""))
    parser.add_argument("--package-release-id", default="", help="Release package identity for manifest validation.")
    parser.add_argument("--commit-sha", default="", help="Commit identity for manifest validation.")
    parser.add_argument("--evidence-manifest", default="", help="Release evidence manifest path.")
    parser.add_argument("--expected-runtime-release-id", default="", help="Expected X-Release-ID header value.")
    parser.add_argument(
        "--expected-runtime-release-instance-id",
        default="",
        help="Expected X-Release-Instance-ID header value.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    base_url = args.base_url.rstrip("/")
    metrics_url = (args.metrics_url or f"{base_url}/api/internal/metrics").strip()
    metrics_token = _load_metrics_token(args)
    package_release_id = (args.package_release_id or args.release_id or "").strip()
    runtime_release_id = (args.expected_runtime_release_id or args.release_id or "").strip()
    runtime_release_instance_id = (
        args.expected_runtime_release_instance_id or args.release_instance_id or runtime_release_id
    ).strip()

    results: list[dict[str, Any]] = []
    results.append(
        _check_http(
            name="healthz",
            url=f"{base_url}/healthz",
            expected={200},
            expected_release_id=runtime_release_id,
            expected_release_instance_id=runtime_release_instance_id,
        )
    )
    health_body = _json_body(results[-1])
    results[-1]["contract"] = "status=ok and checks.database=ok"
    results[-1]["body_json"] = health_body
    results[-1]["ok"] = bool(
        results[-1]["ok"]
        and health_body.get("status") == "ok"
        and (health_body.get("checks") or {}).get("database") == "ok"
    )
    results[-1].pop("_body", None)

    for name, path, expected in (
        ("login_page", "/login", {200, 302, 303}),
        ("dashboard_redirect", "/dashboard", {302, 303}),
        ("notificacoes_redirect", "/notificacoes-email", {302, 303}),
    ):
        item = _check_http(
            name=name,
            url=f"{base_url}{path}",
            expected=expected,
            expected_release_id=runtime_release_id,
            expected_release_instance_id=runtime_release_instance_id,
        )
        item["contract"] = "route is alive and responds with the expected unauthenticated page or redirect"
        item.pop("_body", None)
        results.append(item)

    metrics_headers = {"X-Metrics-Token": metrics_token} if metrics_token else {}
    metric_item = _check_http(
        name="internal_metrics",
        url=metrics_url,
        expected={200},
        headers=metrics_headers,
        expected_release_id=runtime_release_id,
        expected_release_instance_id=runtime_release_instance_id,
    )
    metric_item["contract"] = "valid X-Metrics-Token returns Prometheus metrics"
    metric_body = str(metric_item.pop("_body", "") or "")
    metric_item["metrics_sample"] = metric_body[:500]
    metric_item["metrics_contract_markers"] = {
        "prometheus_content": "HELP" in metric_body or "TYPE" in metric_body,
        "runtime_resource_metric_present": "runtime_resource_metrics_available" in metric_body,
    }
    metric_item["ok"] = bool(
        metric_item["ok"]
        and metric_item["metrics_contract_markers"]["prometheus_content"]
        and metric_item["metrics_contract_markers"]["runtime_resource_metric_present"]
    )
    metric_item.pop("body_sample", None)
    results.append(metric_item)

    runtime_ids = [
        item.get("runtime_identity")
        for item in results
        if isinstance(item, dict) and isinstance(item.get("runtime_identity"), dict)
    ]
    runtime_identity_ok = bool(runtime_ids) and all(
        bool((item or {}).get("release_id") and (item or {}).get("release_instance_id")) for item in runtime_ids
    )
    if runtime_release_id:
        runtime_identity_ok = runtime_identity_ok and all(
            (item or {}).get("release_id") == runtime_release_id for item in runtime_ids
        )
    if runtime_release_instance_id:
        runtime_identity_ok = runtime_identity_ok and all(
            (item or {}).get("release_instance_id") == runtime_release_instance_id for item in runtime_ids
        )

    runtime_result = {
        "check": "runtime_headers",
        "url": base_url,
        "status": 200 if runtime_identity_ok else 0,
        "expected": ["X-Release-ID", "X-Release-Instance-ID"],
        "ok": runtime_identity_ok,
        "runtime_ids": runtime_ids,
        "contract": "runtime emits release headers on real HTTP responses",
    }
    results.append(runtime_result)

    payload = {
        "failed": any(not bool(item.get("ok")) for item in results),
        "generated_at": _now_utc(),
        "environment": args.environment,
        "base_url": base_url,
        "metrics_url": metrics_url,
        "release_id": package_release_id,
        "commit_sha": args.commit_sha,
        "evidence_manifest": args.evidence_manifest,
        "runtime_release_id": runtime_release_id,
        "runtime_release_instance_id": runtime_release_instance_id,
        "results": results,
        "runtime": {
            "alive": bool(results[0].get("ok")),
            "headers_present": runtime_identity_ok,
            "release_id": runtime_release_id,
            "release_instance_id": runtime_release_instance_id,
        },
    }

    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)

    return 1 if payload["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
