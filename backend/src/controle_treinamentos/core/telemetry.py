"""OpenTelemetry instrumentation scaffolding.

To activate:
1. pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-flask
2. Set OTEL_EXPORTER_OTLP_ENDPOINT in env
3. Call configure_otel(app) in create_app()
"""
from __future__ import annotations

import os


def configure_otel(app) -> None:
    """Initialize OpenTelemetry tracing if OTEL_EXPORTER_OTLP_ENDPOINT is set."""
    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "") or "").strip()
    if not endpoint:
        app.logger.info(
            "OpenTelemetry tracing disabled.",
            extra={
                "event": "dependency_disabled",
                "component": "opentelemetry",
                "reason": "endpoint_not_configured",
            },
        )
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanExporter

        resource = Resource.create({
            "service.name": os.getenv("OTEL_SERVICE_NAME", "controle-treinamentos"),
        })
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanExporter(exporter))
        trace.set_tracer_provider(provider)
        FlaskInstrumentor().instrument_app(app)
        app.logger.info(
            "OpenTelemetry tracing configured.",
            extra={
                "event": "dependency_initialized",
                "component": "opentelemetry",
                "endpoint": endpoint,
            },
        )
    except ImportError:
        app.logger.warning(
            "OpenTelemetry packages not installed.",
            extra={
                "event": "dependency_unavailable",
                "component": "opentelemetry",
                "reason": "packages_not_installed",
            },
        )
