"""Prometheus metrics for the model gateway."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUEST_COUNT = Counter(
    "ruflo_model_gateway_requests_total",
    "Total inference requests",
    ["provider", "model", "status"],
)

REQUEST_LATENCY = Histogram(
    "ruflo_model_gateway_request_duration_seconds",
    "Inference request duration in seconds",
    ["provider", "model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

TOKENS_USED = Counter(
    "ruflo_model_gateway_tokens_total",
    "Total tokens consumed",
    ["provider", "model", "direction"],
)

# Provider health
PROVIDER_STATUS = Gauge(
    "ruflo_model_gateway_provider_status",
    "Provider availability (1=up, 0=down)",
    ["provider"],
)

# Registry
REGISTERED_MODELS = Gauge(
    "ruflo_model_gateway_registered_models",
    "Number of models in the registry",
    ["provider"],
)

# Active requests
ACTIVE_REQUESTS = Gauge(
    "ruflo_model_gateway_active_requests",
    "Currently processing requests",
    ["provider"],
)
