"""OpenTelemetry Distributed Tracing (DOC-019 Section 2.2-2.3)

Trace flow: Request -> Amygdala -> Router -> Cache Cascade -> Engine -> Bridge -> Response
Each step is a span with attributes for debugging.
"""

import os
import logging
from contextlib import contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger("cortexdb.observability.tracing")

# OTel imports - gracefully degrade if not installed
_tracer = None
_otel_available = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    _otel_available = True
except ImportError:
    pass


def setup_tracing(service_name: str = "cortexdb",
                  otlp_endpoint: Optional[str] = None,
                  console_export: bool = False) -> bool:
    """Initialize OpenTelemetry tracing. Returns True if successful."""
    global _tracer

    if not _otel_available:
        logger.info("OpenTelemetry not installed - tracing disabled (pip install opentelemetry-sdk)")
        return False

    endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.SERVICE_VERSION: "2.0.0",
        "deployment.environment": os.getenv("CORTEX_MODE", "development"),
    })

    provider = TracerProvider(resource=resource)

    # OTLP exporter (Grafana Tempo / Jaeger)
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"OTel OTLP exporter -> {endpoint}")
        except ImportError:
            logger.warning("opentelemetry-exporter-otlp not installed")

    # Console exporter (dev mode)
    if console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("cortexdb", "2.0.0")
    logger.info("OpenTelemetry tracing initialized")
    return True


def get_tracer():
    """Get the CortexDB tracer (or a no-op tracer if OTel not available)."""
    global _tracer
    if _tracer:
        return _tracer
    if _otel_available:
        return trace.get_tracer("cortexdb", "2.0.0")
    return _NoOpTracer()


@contextmanager
def trace_span(name: str, attributes: Dict[str, Any] = None):
    """Context manager for creating traced spans. No-ops if OTel unavailable."""
    tracer = get_tracer()
    if isinstance(tracer, _NoOpTracer):
        yield _NoOpSpan()
        return

    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        yield span


class _NoOpSpan:
    """No-op span when OTel is not available."""
    def set_attribute(self, key, value): pass
    def set_status(self, status): pass
    def record_exception(self, exc): pass
    def add_event(self, name, attributes=None): pass


class _NoOpTracer:
    """No-op tracer when OTel is not available."""
    def start_as_current_span(self, name, **kwargs):
        return _NoOpContextManager()
    def start_span(self, name, **kwargs):
        return _NoOpSpan()


class _NoOpContextManager:
    def __enter__(self): return _NoOpSpan()
    def __exit__(self, *args): pass
