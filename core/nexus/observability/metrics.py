"""Prometheus metrics for Nexus."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry, generate_latest
from prometheus_client.multiprocess import MultiProcessCollector
import os

# Check if running in multiprocess mode
if "prometheus_multiproc_dir" in os.environ:
    registry = CollectorRegistry()
    MultiProcessCollector(registry)
else:
    registry = CollectorRegistry(auto_describe=True)

# --- Application Info ---

app_info = Info(
    "nexus_app",
    "Nexus application information",
    registry=registry,
)

# --- HTTP Metrics ---

http_requests_total = Counter(
    "nexus_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "nexus_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry,
)

http_requests_in_progress = Gauge(
    "nexus_http_requests_in_progress",
    "HTTP requests currently in progress",
    ["method", "endpoint"],
    registry=registry,
)

# --- Database Metrics ---

db_connections_total = Gauge(
    "nexus_db_connections_total",
    "Total database connections",
    ["state"],  # active, idle
    registry=registry,
)

db_query_duration_seconds = Histogram(
    "nexus_db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],  # select, insert, update, delete
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry,
)

db_query_errors_total = Counter(
    "nexus_db_query_errors_total",
    "Total database query errors",
    ["operation", "error_type"],
    registry=registry,
)

# --- Cache Metrics ---

cache_hits_total = Counter(
    "nexus_cache_hits_total",
    "Total cache hits",
    ["cache_name"],
    registry=registry,
)

cache_misses_total = Counter(
    "nexus_cache_misses_total",
    "Total cache misses",
    ["cache_name"],
    registry=registry,
)

cache_operations_total = Counter(
    "nexus_cache_operations_total",
    "Total cache operations",
    ["cache_name", "operation"],  # get, set, delete
    registry=registry,
)

# --- Agent Metrics ---

agents_total = Gauge(
    "nexus_agents_total",
    "Total registered agents",
    ["status"],  # active, inactive
    registry=registry,
)

agent_messages_total = Counter(
    "nexus_agent_messages_total",
    "Total messages processed by agents",
    ["direction"],  # inbound, outbound
    registry=registry,
)

agent_api_calls_total = Counter(
    "nexus_agent_api_calls_total",
    "Total API calls made by agents",
    ["agent_id", "endpoint"],
    registry=registry,
)

# --- WebSocket Metrics ---

websocket_connections_total = Gauge(
    "nexus_websocket_connections_total",
    "Total active WebSocket connections",
    registry=registry,
)

websocket_messages_total = Counter(
    "nexus_websocket_messages_total",
    "Total WebSocket messages",
    ["direction", "message_type"],  # inbound/outbound, text/binary
    registry=registry,
)

# --- Job Queue Metrics ---

jobs_total = Counter(
    "nexus_jobs_total",
    "Total background jobs",
    ["queue", "status"],  # completed, failed, retried
    registry=registry,
)

jobs_in_progress = Gauge(
    "nexus_jobs_in_progress",
    "Background jobs currently in progress",
    ["queue"],
    registry=registry,
)

job_duration_seconds = Histogram(
    "nexus_job_duration_seconds",
    "Background job duration in seconds",
    ["queue", "task_name"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
    registry=registry,
)

job_queue_length = Gauge(
    "nexus_job_queue_length",
    "Number of jobs waiting in queue",
    ["queue"],
    registry=registry,
)

# --- Device/IoT Metrics ---

devices_total = Gauge(
    "nexus_devices_total",
    "Total registered devices",
    ["device_type", "status"],  # online, offline
    registry=registry,
)

device_telemetry_total = Counter(
    "nexus_device_telemetry_total",
    "Total telemetry messages received",
    ["device_type"],
    registry=registry,
)

device_commands_total = Counter(
    "nexus_device_commands_total",
    "Total commands sent to devices",
    ["command_type", "status"],  # completed, failed
    registry=registry,
)

# --- Marketplace Metrics ---

marketplace_transactions_total = Counter(
    "nexus_marketplace_transactions_total",
    "Total marketplace transactions",
    ["transaction_type", "status"],
    registry=registry,
)

marketplace_revenue_cents = Counter(
    "nexus_marketplace_revenue_cents",
    "Total marketplace revenue in cents",
    ["fee_type"],  # platform_fee, seller_revenue
    registry=registry,
)

# --- Storage Metrics ---

storage_files_total = Gauge(
    "nexus_storage_files_total",
    "Total files in storage",
    ["bucket"],
    registry=registry,
)

storage_bytes_total = Gauge(
    "nexus_storage_bytes_total",
    "Total storage bytes used",
    ["bucket"],
    registry=registry,
)

storage_operations_total = Counter(
    "nexus_storage_operations_total",
    "Total storage operations",
    ["operation"],  # upload, download, delete
    registry=registry,
)

# --- Search Metrics ---

search_queries_total = Counter(
    "nexus_search_queries_total",
    "Total search queries",
    ["search_type"],  # text, semantic, hybrid
    registry=registry,
)

search_duration_seconds = Histogram(
    "nexus_search_duration_seconds",
    "Search query duration in seconds",
    ["search_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    registry=registry,
)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest(registry)


def set_app_info(version: str, environment: str = "production"):
    """Set application info metric."""
    app_info.info({
        "version": version,
        "environment": environment,
    })
