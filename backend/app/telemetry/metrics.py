"""Production-grade operational telemetry & Prometheus metrics exporter (Phase 3AM).

Zero external dependencies (stdlib thread-safe collectors).
Meets Phase 3AM Objective 4:
- Request count & latency
- HTTP status breakdowns (explicit 429, 502, 503, 504 tracking)
- Reasoning latency & active concurrency gauge
- Readiness status & Ollama availability gauges
- Standard Prometheus text format exposition

Privacy Guarantees:
- Zero raw prompts
- Zero raw model outputs
- Zero user images or biometric data
- Zero auth tokens, secrets, or PII
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


class MetricsCollector:
    """Thread-safe in-process metrics accumulator for Prometheus exposition."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Key: (method, path, status_str) -> int
        self._http_requests: dict[tuple[str, str, str], int] = defaultdict(int)
        # Key: (method, path) -> [count, sum_seconds]
        self._http_duration: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        # Key: status_code_int -> int
        self._status_counts: dict[int, int] = defaultdict(int)

        # Reasoning metrics
        self._reasoning_count: int = 0
        self._reasoning_duration_sum: float = 0.0
        self._reasoning_by_status: dict[str, int] = defaultdict(int)

        # Gauges
        self._active_concurrency: int = 0
        self._readiness_status: float = 0.0
        self._ollama_available: float = 0.0

    def record_http_request(
        self, method: str, path: str, status_code: int, duration_s: float
    ) -> None:
        """Record an inbound HTTP request."""
        # Sanitize path to prevent cardinality explosion (only keep base routes)
        route = self._normalize_path(path)
        status_str = str(status_code)
        with self._lock:
            self._http_requests[(method.upper(), route, status_str)] += 1
            dur = self._http_duration[(method.upper(), route)]
            dur[0] += 1
            dur[1] += duration_s
            self._status_counts[status_code] += 1

    def record_reasoning_query(self, status: str, duration_s: float) -> None:
        """Record a completed reasoning query."""
        with self._lock:
            self._reasoning_count += 1
            self._reasoning_duration_sum += duration_s
            self._reasoning_by_status[status] += 1

    def set_active_concurrency(self, active: int) -> None:
        """Update active reasoning concurrency gauge."""
        with self._lock:
            self._active_concurrency = max(0, active)

    def set_readiness_status(self, is_ready: bool) -> None:
        """Update system readiness gauge (1.0 = ready, 0.0 = not ready)."""
        with self._lock:
            self._readiness_status = 1.0 if is_ready else 0.0

    def set_ollama_availability(self, is_available: bool) -> None:
        """Update Ollama availability gauge (1.0 = available, 0.0 = unavailable)."""
        with self._lock:
            self._ollama_available = 1.0 if is_available else 0.0

    def get_status_count(self, status_code: int) -> int:
        """Return the count of requests for a specific HTTP status code."""
        with self._lock:
            return self._status_counts.get(status_code, 0)

    def get_summary(self) -> dict[str, Any]:
        """Return summary dict for verification and testing."""
        with self._lock:
            return {
                "http_requests_total": sum(self._http_requests.values()),
                "status_counts": dict(self._status_counts),
                "reasoning_queries_total": self._reasoning_count,
                "reasoning_duration_sum": round(self._reasoning_duration_sum, 4),
                "active_concurrency": self._active_concurrency,
                "readiness_status": self._readiness_status,
                "ollama_available": self._ollama_available,
            }

    def format_prometheus(self) -> str:
        """Format metrics in standard Prometheus text exposition format (version 0.0.4)."""
        lines: list[str] = []

        with self._lock:
            # 1. HTTP Requests Total
            lines.append("# HELP fansivibe_http_requests_total Total number of HTTP requests processed.")
            lines.append("# TYPE fansivibe_http_requests_total counter")
            for (method, route, status_str), count in sorted(self._http_requests.items()):
                lines.append(
                    f'fansivibe_http_requests_total{{method="{method}",path="{route}",status="{status_str}"}} {count}'
                )

            # 2. HTTP Request Duration
            lines.append("# HELP fansivibe_http_request_duration_seconds Latency of HTTP requests in seconds.")
            lines.append("# TYPE fansivibe_http_request_duration_seconds summary")
            for (method, route), (cnt, total_dur) in sorted(self._http_duration.items()):
                lines.append(f'fansivibe_http_request_duration_seconds_count{{method="{method}",path="{route}"}} {int(cnt)}')
                lines.append(f'fansivibe_http_request_duration_seconds_sum{{method="{method}",path="{route}"}} {total_dur:.6f}')

            # 3. HTTP Status Counts
            lines.append("# HELP fansivibe_http_status_total Total HTTP responses partitioned by status code.")
            lines.append("# TYPE fansivibe_http_status_total counter")
            for code in sorted(self._status_counts.keys()):
                lines.append(f'fansivibe_http_status_total{{code="{code}"}} {self._status_counts[code]}')

            # Ensure explicit key status lines are always reported (429, 502, 503, 504)
            for key_code in (429, 502, 503, 504):
                if key_code not in self._status_counts:
                    lines.append(f'fansivibe_http_status_total{{code="{key_code}"}} 0')

            # 4. Reasoning Duration & Total
            lines.append("# HELP fansivibe_reasoning_duration_seconds Fashion reasoning execution duration in seconds.")
            lines.append("# TYPE fansivibe_reasoning_duration_seconds summary")
            lines.append(f"fansivibe_reasoning_duration_seconds_count {self._reasoning_count}")
            lines.append(f"fansivibe_reasoning_duration_seconds_sum {self._reasoning_duration_sum:.6f}")

            lines.append("# HELP fansivibe_reasoning_queries_total Total fashion reasoning queries handled.")
            lines.append("# TYPE fansivibe_reasoning_queries_total counter")
            for status, count in sorted(self._reasoning_by_status.items()):
                lines.append(f'fansivibe_reasoning_queries_total{{status="{status}"}} {count}')
            if not self._reasoning_by_status:
                lines.append('fansivibe_reasoning_queries_total{status="total"} 0')

            # 5. Active Reasoning Concurrency Gauge
            lines.append("# HELP fansivibe_reasoning_concurrency_active Number of reasoning requests currently executing.")
            lines.append("# TYPE fansivibe_reasoning_concurrency_active gauge")
            lines.append(f"fansivibe_reasoning_concurrency_active {self._active_concurrency}")

            # 6. Readiness Status Gauge
            lines.append("# HELP fansivibe_readiness_status System readiness probe status (1=ready, 0=not ready).")
            lines.append("# TYPE fansivibe_readiness_status gauge")
            lines.append(f"fansivibe_readiness_status {self._readiness_status}")

            # 7. Ollama Availability Gauge
            lines.append("# HELP fansivibe_ollama_available Ollama service reachability (1=available, 0=unavailable).")
            lines.append("# TYPE fansivibe_ollama_available gauge")
            lines.append(f"fansivibe_ollama_available {self._ollama_available}")

        return "\n".join(lines) + "\n"

    def _normalize_path(self, path: str) -> str:
        """Map paths to low-cardinality endpoint names."""
        clean = path.split("?")[0].rstrip("/")
        if not clean:
            return "/"
        # Group dynamic UUIDs or IDs
        parts = clean.split("/")
        norm_parts = []
        for p in parts:
            if len(p) >= 32 and (p.count("-") == 4 or p.isalnum()):
                norm_parts.append("{id}")
            else:
                norm_parts.append(p)
        return "/".join(norm_parts)


# Global singleton collector
_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Return the global telemetry metrics collector instance."""
    return _collector
