"""OpenTelemetry wiring for the Ch25 local-with-docker-compose anchor.

Exports every span over OTLP/HTTP to the local `lgtm` collector
(`docker.io/grafana/otel-lgtm`). `ALWAYS_ON` sampling is deliberate: this
chapter's verify.sh asserts a SPECIFIC, fixed trace id landed in Tempo, so
sampling must never drop it.

`FastAPIInstrumentor` auto-instruments every request (HTTP server spans
carrying `http.route`/`http.method`-style attributes) and honors an
inbound W3C `traceparent` header via the default `tracecontext` propagator
— no extra config needed for a request to CONTINUE an existing trace id
rather than starting a new one.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "shipping-python")
_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4318")


def configure_tracing(app: FastAPI) -> None:
    resource = Resource.create({"service.name": _SERVICE_NAME})
    provider = TracerProvider(resource=resource, sampler=ALWAYS_ON)
    exporter = OTLPSpanExporter(endpoint=f"{_OTLP_ENDPOINT}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
