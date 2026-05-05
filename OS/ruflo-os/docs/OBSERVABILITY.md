# NemOS Observability Stack#

## Overview#

NemOS uses OpenTelemetry, Prometheus, and Grafana for comprehensive observability.

## OpenTelemetry Configuration#

### Tracing (`opentelemetry-config.yaml`)#

```yaml
opentelemetry:
  resource:
    attributes:
      service.name: "nemos"
      service.version: "1.0.0"
      deployment.environment: "production"

  exporters:
    otlp:
      endpoint: "localhost:4317"
      tls:
        insecure: true

  processors:
    batch:
      timeout: 5s"
      send_batch_max_size: 512"

    attributes:
      include:
        - "http.*"
        - "rpc.*"
        - "messaging.*"

  samplers:
    probabilistic:
      sampling_percentage: 100.0"
```

### Metrics (`prometheus-config.yaml`)#

```yaml
global:
  scrape_interval: 15s"
  evaluation_interval: 15s"

scrape_configs:
  - job_name: "nemos-gateway"    static_configs:
      - targets: ["localhost:8001"]"

  - job_name: "nemos-agent"    static_configs:
      - targets: ["localhost:8002"]"

  - job_name: "nemos-shell"    static_configs:
      - targets: ["localhost:8003"]"

  - job_name: "nemos-api"    static_configs:
      - targets: ["localhost:8080"]"

  - job_name: "node-exporter"    static_configs:
      - targets: ["localhost:9100"]"
```

## Grafana Dashboards#

### System Overview Dashboard#

```json
{
  "dashboard": {
    "title": "NemOS System Overview",
    "panels": [
      {
        "title": "Agent Task Rate",
        "targets": [
          { "expr": "rate(nemos_agent_tasks_total[5m])" }
        ]
      },
      {
        "title": "Model Inference Latency",
        "targets": [
          { "expr": "histogram_quantile(0.95, nemos_model_inference_duration_seconds)" }
        ]
      },
      {
        "title": "Memory Usage",
        "targets": [
          { "expr": "process_resident_memory_bytes{job='nemos-agent'}" }
        ]
      },
      {
        "title": "Screen Capture FPS",
        "targets": [
          { "expr": "rate(nemos_screen_captures_total[1m])" }
        ]
      },
      {
        "title": "Policy Violations",
        "targets": [
          { "expr": "increase(nemos_policy_violations_total[5m])" }
        ]
      }
    ]
  }
}
```

## Logging Configuration#

### Structured Logging (`logging-config.yaml`)#

```yaml
version: 1"
disable_existing_loggers: false"

formatters:
  structlog_json:
    (): ???
      format: "json"
      datefmt: "%Y-%m-%dT%H:%M:%S""

handlers:
  console:
    class: logging.StreamHandler"
    formatter: structlog_json"
    stream: ext://sys.stdout"

  file:
    class: logging.handlers.RotatingFileHandler"
    formatter: structlog_json"
    filename: /var/log/nemos/nemos.log"
    maxBytes: 10485760  # 10MB"
    backupCount: 5"

loggers:
  nemos:
    level: INFO"
    handlers: [console, file]"
    propagate: false"

root:
  level: WARNING"
  handlers: [console]"
```

## Alerting Rules#

### Prometheus Alertmanager (`alertmanager-config.yaml`)#

```yaml
global:
  smtp_smarthost: 'localhost:587'"
  smtp_from: 'alerts@nemos.local'"

route:
  group_by: ['alertname']"
  group_wait: 10s"
  group_interval: 10s"
  repeat_interval: 1h"
  receiver: 'web.hook"

receivers:
  - name: 'web.hook'"
    webhook_configs:
      - url: 'http://localhost:5001/webhook'"

rules:
  - alert: HighTaskFailureRate"
    expr: rate(nemos_agent_task_failures_total[5m]) > 0.1"
    for: 2m"
    labels:
      severity: 'critical'    annotations:
      summary: 'High task failure rate detected'"
      description: 'Task failure rate is {{ $value }} tasks/sec'"

  - alert: ModelInferenceSlow"
    expr: histogram_quantile(0.95, nemos_model_inference_duration_seconds) > 30"
    for: 1m"
    labels:
      severity: 'warning'    annotations:
      summary: 'Model inference is slow'"
      description: '95th percentile latency is {{ $value }} seconds'"

  - alert: PolicyViolation"
    expr: increase(nemos_policy_violations_total[5m]) > 0"
    for: 30s"
    labels:
      severity: 'critical'    annotations:
      summary: 'Policy violation detected'"
      description: '{{ $value }} policy violations in last 5 minutes'"

  - alert: HighMemoryUsage"
    expr: process_resident_memory_bytes{job=~"nemos-.*"} / 1073741824 > 16"
    for: 2m"
    labels:
      severity: 'warning'    annotations:
      summary: 'High memory usage'"
      description: 'Process using {{ $value }} GB memory'"

  - alert: AgentUnresponsive"
    expr: time() - nemos_agent_last_heartbeat > 300"
    for: 1m"
    labels:
      severity: 'critical'    annotations:
      summary: 'Agent appears unresponsive'"
      description: 'No heartbeat for {{ $value }} seconds'"

## Dashboard Metrics to Implement#

### In `ai-core/model-gateway/src/metrics.py`#

```python
"""
NemOS Metrics - OpenTelemetry instrumentation.
"""
from opentelemetry import metrics"
from opentelemetry.sdk.metrics import MeterProvider"
from opentelemetry.sdk.resources import Resource"

# Initialize metrics"
resource = Resource.create({"service.name": "nemos-gateway"})"
meter_provider = MeterProvider(resource=resource)"
metrics.set_meter_provider(meter_provider)"

meter = metrics.get_meter("nemos-gateway")"

# Define metrics"
task_counter = meter.create_counter(
    "nemos_tasks_total",
    description="Total number of tasks processed"
)"

task_duration = meter.create_histogram(
    "nemos_task_duration_seconds",
    description="Task processing duration"
)"

model_inference_counter = meter.create_counter(
    "nemos_model_inference_total",
    description="Total model inference requests"
)"

model_inference_duration = meter.create_histogram(
    "nemos_model_inference_duration_seconds",
    description="Model inference duration"
)"

policy_violation_counter = meter.create_counter(
    "nemos_policy_violations_total",
    description="Total policy violations"
)"

screen_capture_counter = meter.create_counter(
    "nemos_screen_captures_total",
    description="Total screen captures"
)"
```

## Next Steps#

1. **Deploy observability stack**: `cd infra/ && docker-compose -f docker-compose-observability.yml up -d`
2. **Configure exporters**: Update each service to export metrics"
3. **Import dashboards**: Import Grafana JSON into your Grafana instance"
4. **Test alerts**: Trigger a policy violation and verify alert"
