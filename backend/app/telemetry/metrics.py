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

        self._llm_enrichments: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
        self._llm_duration_count: int = 0
        self._llm_duration_sum: float = 0.0

        # Gauges
        self._active_concurrency: int = 0
        self._readiness_status: float = 0.0
        self._ollama_available: float = 0.0

        # Virtual Try-On operational telemetry (Phase 7D)
        self._tryon_jobs_created: dict[tuple[str, str], int] = defaultdict(int)
        self._tryon_jobs_terminal: dict[tuple[str, str, str], int] = defaultdict(int)
        self._tryon_processing_count: int = 0
        self._tryon_processing_duration_sum: float = 0.0
        self._tryon_long_running_jobs: int = 0
        self._tryon_retries: dict[str, int] = defaultdict(int)
        self._tryon_credits_charged: dict[str, int] = defaultdict(int)
        self._tryon_storage_errors: dict[str, int] = defaultdict(int)
        self._tryon_quota_rejections: dict[str, int] = defaultdict(int)
        self._tryon_provider_outcomes: dict[tuple[str, str], int] = defaultdict(int)
        self._tryon_auth_failures: dict[tuple[str, str], int] = defaultdict(int)
        self._tryon_active_jobs: int = 0
        self._tryon_provider_credit_balance: dict[str, float] = {}
        self._tryon_stale_jobs_recovered: int = 0
        self._tryon_interrupted_jobs_recovered: int = 0
        self._tryon_retention_cleanup_runs: dict[str, int] = defaultdict(int)
        self._tryon_retention_last_success_ts: float = 0.0

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

    def record_llm_enrichment(
        self,
        *,
        provider: str,
        model: str,
        status: str,
        reason: str,
        error_type: str = "none",
        duration_s: float | None = None,
    ) -> None:
        """Record one self-hosted LLM enrichment outcome without content data."""
        with self._lock:
            self._llm_enrichments[(provider or "unknown", model or "unknown", status, reason, error_type or "none")] += 1
            if duration_s is not None and duration_s >= 0:
                self._llm_duration_count += 1
                self._llm_duration_sum += duration_s

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

    def record_tryon_job_created(self, *, provider: str, replayed: bool) -> None:
        """Record a Try-On job creation or idempotent replay."""
        kind = "replay" if replayed else "created"
        with self._lock:
            self._tryon_jobs_created[(provider or "unknown", kind)] += 1

    def record_tryon_job_terminal(
        self,
        *,
        provider: str,
        status: str,
        error_code: str | None = None,
        duration_s: float | None = None,
        credits_charged: int = 0,
    ) -> None:
        """Record a terminal Try-On job outcome, duration, and credits consumed."""
        code = error_code or "none"
        with self._lock:
            self._tryon_jobs_terminal[(provider or "unknown", status, code)] += 1
            if duration_s is not None and duration_s >= 0:
                self._tryon_processing_count += 1
                self._tryon_processing_duration_sum += duration_s
                if duration_s >= 60.0:
                    self._tryon_long_running_jobs += 1
            if credits_charged > 0:
                self._tryon_credits_charged[provider or "unknown"] += int(credits_charged)

    def record_tryon_retry(self, *, provider: str) -> None:
        """Record a Try-On job retry."""
        with self._lock:
            self._tryon_retries[provider or "unknown"] += 1

    def record_tryon_storage_error(self, *, operation: str) -> None:
        """Record an R2/storage error during Try-On media handling."""
        with self._lock:
            self._tryon_storage_errors[operation or "unknown"] += 1

    def record_tryon_quota_rejection(self, reason: str) -> None:
        """Record a Try-On quota, concurrency, or rate-limit rejection."""
        with self._lock:
            self._tryon_quota_rejections[reason or "unknown"] += 1

    def record_tryon_provider_outcome(self, *, provider: str, outcome: str) -> None:
        """Record a Try-On provider call outcome."""
        with self._lock:
            self._tryon_provider_outcomes[(provider or "unknown", outcome or "unknown")] += 1

    def record_tryon_auth_failure(self, *, endpoint: str, status_code: int) -> None:
        """Record an authentication or authorization failure on Try-On endpoints."""
        with self._lock:
            self._tryon_auth_failures[(endpoint or "unknown", str(status_code))] += 1

    def set_tryon_active_jobs(self, active: int) -> None:
        """Update active in-process Try-On worker concurrency gauge."""
        with self._lock:
            self._tryon_active_jobs = max(0, active)

    def set_tryon_provider_credit_balance(self, *, provider: str, balance: float) -> None:
        """Update last-observed provider credit balance gauge."""
        with self._lock:
            self._tryon_provider_credit_balance[provider or "unknown"] = float(balance)

    def record_tryon_stale_jobs_recovered(self, count: int = 1) -> None:
        """Record stale Try-On jobs recovered by maintenance."""
        if count <= 0:
            return
        with self._lock:
            self._tryon_stale_jobs_recovered += int(count)

    def record_tryon_interrupted_jobs_recovered(self, count: int = 1) -> None:
        """Record interrupted Try-On jobs recovered on startup."""
        if count <= 0:
            return
        with self._lock:
            self._tryon_interrupted_jobs_recovered += int(count)

    def record_tryon_retention_cleanup(self, *, outcome: str) -> None:
        """Record a Try-On retention cleanup execution outcome."""
        with self._lock:
            self._tryon_retention_cleanup_runs[outcome or "unknown"] += 1
            if outcome == "success":
                self._tryon_retention_last_success_ts = time.time()

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
                "llm_enrichments": {
                    f"{prov}:{model}:{status}:{reason}:{error_type}": cnt
                    for (prov, model, status, reason, error_type), cnt in self._llm_enrichments.items()
                },
                "llm_enrichment_duration_count": self._llm_duration_count,
                "llm_enrichment_duration_sum": round(self._llm_duration_sum, 4),
                "active_concurrency": self._active_concurrency,
                "readiness_status": self._readiness_status,
                "ollama_available": self._ollama_available,
                "tryon_jobs_created_total": sum(self._tryon_jobs_created.values()),
                "tryon_jobs_replayed_total": sum(
                    cnt for (_, kind), cnt in self._tryon_jobs_created.items() if kind == "replay"
                ),
                "tryon_jobs_terminal": {
                    f"{prov}:{st}:{code}": cnt
                    for (prov, st, code), cnt in self._tryon_jobs_terminal.items()
                },
                "tryon_processing_count": self._tryon_processing_count,
                "tryon_processing_duration_sum": round(self._tryon_processing_duration_sum, 4),
                "tryon_long_running_jobs_total": self._tryon_long_running_jobs,
                "tryon_retries_total": sum(self._tryon_retries.values()),
                "tryon_credits_charged_total": sum(self._tryon_credits_charged.values()),
                "tryon_storage_errors": dict(self._tryon_storage_errors),
                "tryon_quota_rejections": dict(self._tryon_quota_rejections),
                "tryon_provider_outcomes": {
                    f"{prov}:{out}": cnt
                    for (prov, out), cnt in self._tryon_provider_outcomes.items()
                },
                "tryon_auth_failures": {
                    f"{ep}:{code}": cnt
                    for (ep, code), cnt in self._tryon_auth_failures.items()
                },
                "tryon_active_jobs": self._tryon_active_jobs,
                "tryon_provider_credit_balance": dict(self._tryon_provider_credit_balance),
                "tryon_stale_jobs_recovered_total": self._tryon_stale_jobs_recovered,
                "tryon_interrupted_jobs_recovered_total": self._tryon_interrupted_jobs_recovered,
                "tryon_retention_cleanup_runs": dict(self._tryon_retention_cleanup_runs),
                "tryon_retention_last_success_timestamp_seconds": self._tryon_retention_last_success_ts,
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

            lines.append("# HELP fansivibe_llm_enrichments_total Self-hosted LLM enrichment outcomes by provenance.")
            lines.append("# TYPE fansivibe_llm_enrichments_total counter")
            for (prov, model, status, reason, error_type), cnt in sorted(self._llm_enrichments.items()):
                lines.append(
                    f'fansivibe_llm_enrichments_total{{provider="{prov}",model="{model}",status="{status}",reason="{reason}",error_type="{error_type}"}} {cnt}'
                )

            lines.append("# HELP fansivibe_llm_enrichment_duration_seconds LLM enrichment latency in seconds.")
            lines.append("# TYPE fansivibe_llm_enrichment_duration_seconds summary")
            lines.append(f"fansivibe_llm_enrichment_duration_seconds_count {self._llm_duration_count}")
            lines.append(f"fansivibe_llm_enrichment_duration_seconds_sum {self._llm_duration_sum:.6f}")

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

            # 8. Virtual Try-On Metrics (Phase 7D)
            lines.append("# HELP fansivibe_tryon_jobs_created_total Total Virtual Try-On jobs created or replayed.")
            lines.append("# TYPE fansivibe_tryon_jobs_created_total counter")
            for (prov, kind), cnt in sorted(self._tryon_jobs_created.items()):
                lines.append(
                    f'fansivibe_tryon_jobs_created_total{{provider="{prov}",kind="{kind}"}} {cnt}'
                )

            lines.append("# HELP fansivibe_tryon_jobs_terminal_total Terminal Virtual Try-On jobs by provider, status, and error code.")
            lines.append("# TYPE fansivibe_tryon_jobs_terminal_total counter")
            for (prov, st, code), cnt in sorted(self._tryon_jobs_terminal.items()):
                lines.append(
                    f'fansivibe_tryon_jobs_terminal_total{{provider="{prov}",status="{st}",error_code="{code}"}} {cnt}'
                )

            lines.append("# HELP fansivibe_tryon_processing_duration_seconds Virtual Try-On job processing duration in seconds.")
            lines.append("# TYPE fansivibe_tryon_processing_duration_seconds summary")
            lines.append(f"fansivibe_tryon_processing_duration_seconds_count {self._tryon_processing_count}")
            lines.append(f"fansivibe_tryon_processing_duration_seconds_sum {self._tryon_processing_duration_sum:.6f}")

            lines.append("# HELP fansivibe_tryon_long_running_jobs_total Try-On jobs exceeding 60s processing duration.")
            lines.append("# TYPE fansivibe_tryon_long_running_jobs_total counter")
            lines.append(f"fansivibe_tryon_long_running_jobs_total {self._tryon_long_running_jobs}")

            lines.append("# HELP fansivibe_tryon_retries_total Total Virtual Try-On job retries.")
            lines.append("# TYPE fansivibe_tryon_retries_total counter")
            for prov, cnt in sorted(self._tryon_retries.items()):
                lines.append(f'fansivibe_tryon_retries_total{{provider="{prov}"}} {cnt}')

            lines.append("# HELP fansivibe_tryon_credits_charged_total Estimated/charged provider credits for Try-On.")
            lines.append("# TYPE fansivibe_tryon_credits_charged_total counter")
            for prov, cnt in sorted(self._tryon_credits_charged.items()):
                lines.append(f'fansivibe_tryon_credits_charged_total{{provider="{prov}"}} {cnt}')

            lines.append("# HELP fansivibe_tryon_storage_errors_total Storage errors during Try-On media operations.")
            lines.append("# TYPE fansivibe_tryon_storage_errors_total counter")
            for op, cnt in sorted(self._tryon_storage_errors.items()):
                lines.append(f'fansivibe_tryon_storage_errors_total{{operation="{op}"}} {cnt}')

            lines.append("# HELP fansivibe_tryon_quota_rejections_total Try-On submissions rejected due to quotas or rate limits.")
            lines.append("# TYPE fansivibe_tryon_quota_rejections_total counter")
            for reason, cnt in sorted(self._tryon_quota_rejections.items()):
                lines.append(f'fansivibe_tryon_quota_rejections_total{{reason="{reason}"}} {cnt}')

            lines.append("# HELP fansivibe_tryon_provider_outcomes_total Outcomes of Try-On provider invocations.")
            lines.append("# TYPE fansivibe_tryon_provider_outcomes_total counter")
            for (prov, out), cnt in sorted(self._tryon_provider_outcomes.items()):
                lines.append(
                    f'fansivibe_tryon_provider_outcomes_total{{provider="{prov}",outcome="{out}"}} {cnt}'
                )

            lines.append("# HELP fansivibe_tryon_auth_failures_total Authentication or authorization failures on Try-On endpoints.")
            lines.append("# TYPE fansivibe_tryon_auth_failures_total counter")
            for (ep, code), cnt in sorted(self._tryon_auth_failures.items()):
                lines.append(
                    f'fansivibe_tryon_auth_failures_total{{endpoint="{ep}",status_code="{code}"}} {cnt}'
                )

            lines.append("# HELP fansivibe_tryon_active_jobs Currently executing Try-On background jobs.")
            lines.append("# TYPE fansivibe_tryon_active_jobs gauge")
            lines.append(f"fansivibe_tryon_active_jobs {self._tryon_active_jobs}")

            lines.append("# HELP fansivibe_tryon_provider_credit_balance Last observed Try-On provider credit balance.")
            lines.append("# TYPE fansivibe_tryon_provider_credit_balance gauge")
            for prov, bal in sorted(self._tryon_provider_credit_balance.items()):
                lines.append(f'fansivibe_tryon_provider_credit_balance{{provider="{prov}"}} {bal}')

            lines.append("# HELP fansivibe_tryon_stale_jobs_recovered_total Stale Try-On jobs recovered by maintenance.")
            lines.append("# TYPE fansivibe_tryon_stale_jobs_recovered_total counter")
            lines.append(f"fansivibe_tryon_stale_jobs_recovered_total {self._tryon_stale_jobs_recovered}")

            lines.append("# HELP fansivibe_tryon_interrupted_jobs_recovered_total Interrupted Try-On jobs recovered on startup.")
            lines.append("# TYPE fansivibe_tryon_interrupted_jobs_recovered_total counter")
            lines.append(f"fansivibe_tryon_interrupted_jobs_recovered_total {self._tryon_interrupted_jobs_recovered}")

            lines.append("# HELP fansivibe_tryon_retention_cleanup_runs_total Try-On retention cleanup executions by outcome.")
            lines.append("# TYPE fansivibe_tryon_retention_cleanup_runs_total counter")
            for outcome, cnt in sorted(self._tryon_retention_cleanup_runs.items()):
                lines.append(f'fansivibe_tryon_retention_cleanup_runs_total{{outcome="{outcome}"}} {cnt}')

            lines.append("# HELP fansivibe_tryon_retention_last_success_timestamp_seconds Unix timestamp of last clean retention cleanup.")
            lines.append("# TYPE fansivibe_tryon_retention_last_success_timestamp_seconds gauge")
            lines.append(f"fansivibe_tryon_retention_last_success_timestamp_seconds {self._tryon_retention_last_success_ts:.3f}")

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
