from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_metrics_token(args: argparse.Namespace) -> str:
    if args.metrics_token_file:
        return (Path(args.metrics_token_file).read_text(encoding="utf-8") or "").strip()
    env_name = (args.metrics_token_env or "").strip() or "METRICS_TOKEN"
    return (os.getenv(env_name, "") or "").strip()


def _response_header(headers: dict[str, str], name: str) -> str:
    lookup = {str(key).lower(): str(value) for key, value in headers.items()}
    return lookup.get(name.lower(), "")


def _request(url: str, *, token: str = "") -> dict[str, Any]:
    headers = {"X-Metrics-Token": token} if token else {}
    req = urllib.request.Request(url, headers=headers)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status = int(response.status)
            body = response.read().decode("utf-8", errors="ignore")
            response_headers = dict(response.headers)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        response_headers = dict(exc.headers or {})
    except urllib.error.URLError as exc:
        return {
            "status": 0,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "headers": {},
            "body_sample": "",
            "body_json": {},
            "error": "url_error",
            "detail": str(exc.reason),
        }

    body_json: dict[str, Any] = {}
    content_type = _response_header(response_headers, "Content-Type")
    if "json" in content_type.lower():
        try:
            body_json = json.loads(body)
        except json.JSONDecodeError:
            body_json = {}

    return {
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "headers": {
            key: _response_header(response_headers, key)
            for key in (
                "Content-Type",
                "X-Release-ID",
                "X-Release-Instance-ID",
                "X-Request-ID",
                "X-Correlation-ID",
            )
            if _response_header(response_headers, key)
        },
        "body_sample": body[:500],
        "body_json": body_json,
        "_body": body,
    }


def _scenario(
    *,
    name: str,
    endpoint: str,
    token: str,
    token_supplied: bool,
    expected_statuses: set[int],
    expect_prometheus: bool,
) -> dict[str, Any]:
    response = _request(endpoint, token=token)
    body = str(response.pop("_body", "") or "")
    status = int(response.get("status", 0) or 0)
    prometheus_content = "# HELP " in body or "# TYPE " in body
    runtime_metric_present = "runtime_resource_metrics_available" in body
    exposed_metrics_while_forbidden = status in {401, 403, 503} and prometheus_content
    ok = status in expected_statuses
    if expect_prometheus:
        ok = ok and prometheus_content and runtime_metric_present
    else:
        ok = ok and not exposed_metrics_while_forbidden

    response.update(
        {
            "scenario": name,
            "token_supplied": token_supplied,
            "expected_statuses": sorted(expected_statuses),
            "ok": bool(ok),
            "contract": (
                "valid token returns Prometheus metrics"
                if expect_prometheus
                else "missing/invalid token fails closed and does not expose metrics"
            ),
            "markers": {
                "prometheus_content": prometheus_content,
                "runtime_resource_metric_present": runtime_metric_present,
                "exposed_metrics_while_forbidden": exposed_metrics_while_forbidden,
            },
        }
    )
    return response


def _runtime_headers_present(scenarios: list[dict[str, Any]], *, expected_runtime_release_id: str) -> bool:
    if not scenarios:
        return False
    for scenario in scenarios:
        headers = scenario.get("headers") if isinstance(scenario.get("headers"), dict) else {}
        release_id = str(headers.get("X-Release-ID") or "").strip()
        instance_id = str(headers.get("X-Release-Instance-ID") or "").strip()
        if not release_id or not instance_id:
            return False
        if expected_runtime_release_id and release_id != expected_runtime_release_id:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate hardened metrics endpoint access behavior.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metrics-token-file", default="")
    parser.add_argument("--metrics-token-env", default="METRICS_TOKEN")
    parser.add_argument("--environment", default=os.getenv("APP_ENV", ""))
    parser.add_argument("--release-id", required=True, help="Release package identity.")
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--evidence-manifest", default="")
    parser.add_argument("--expected-runtime-release-id", default=os.getenv("APP_RELEASE_ID", ""))
    parser.add_argument("--expected-runtime-release-instance-id", default=os.getenv("APP_RELEASE_INSTANCE_ID", ""))
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    endpoint = f"{base_url}/api/internal/metrics"
    metrics_token = _load_metrics_token(args)
    invalid_token = "invalid-metrics-token-for-hardening-check"

    scenarios = [
        _scenario(
            name="without_token",
            endpoint=endpoint,
            token="",
            token_supplied=False,
            expected_statuses={403, 503},
            expect_prometheus=False,
        ),
        _scenario(
            name="invalid_token",
            endpoint=endpoint,
            token=invalid_token,
            token_supplied=True,
            expected_statuses={403, 503},
            expect_prometheus=False,
        ),
        _scenario(
            name="valid_token",
            endpoint=endpoint,
            token=metrics_token,
            token_supplied=True,
            expected_statuses={200},
            expect_prometheus=True,
        ),
    ]

    statuses = {str(item["scenario"]): str(item.get("status", "")) for item in scenarios}
    runtime_headers_ok = _runtime_headers_present(
        scenarios,
        expected_runtime_release_id=(args.expected_runtime_release_id or "").strip(),
    )
    if (args.expected_runtime_release_instance_id or "").strip():
        runtime_headers_ok = runtime_headers_ok and all(
            str((item.get("headers") or {}).get("X-Release-Instance-ID") or "").strip()
            == args.expected_runtime_release_instance_id
            for item in scenarios
        )
    token_configured = bool(metrics_token)
    access_ok = all(bool(item.get("ok")) for item in scenarios)
    success = bool(token_configured and access_ok and runtime_headers_ok)

    payload = {
        "success": success,
        "generated_at": _now_utc(),
        "environment": args.environment,
        "release_id": args.release_id,
        "commit_sha": args.commit_sha,
        "evidence_manifest": args.evidence_manifest,
        "endpoint": endpoint,
        "runtime_release_id": args.expected_runtime_release_id,
        "runtime_release_instance_id": args.expected_runtime_release_instance_id,
        "metrics_token_configured": token_configured,
        "without_token_status": statuses.get("without_token", ""),
        "invalid_token_status": statuses.get("invalid_token", ""),
        "valid_token_status": statuses.get("valid_token", ""),
        "hardening": {
            "without_token_fail_closed": statuses.get("without_token") in {"403", "503"},
            "invalid_token_fail_closed": statuses.get("invalid_token") in {"403", "503"},
            "valid_token_returns_metrics": statuses.get("valid_token") == "200"
            and bool((scenarios[2].get("markers") or {}).get("prometheus_content")),
            "forbidden_paths_do_not_expose_metrics": all(
                not bool((item.get("markers") or {}).get("exposed_metrics_while_forbidden"))
                for item in scenarios[:2]
            ),
            "runtime_headers_present": runtime_headers_ok,
        },
        "scenarios": scenarios,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
