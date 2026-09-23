"""Live Staging Smoke Test Suite (Phase 3AM Objective 12).

Executes end-to-end through the deployed staging reverse proxy boundary:
Flutter / Client -> Reverse Proxy (port 8080) -> FastAPI (port 8000) -> PostgreSQL (16) -> Ollama -> qwen2.5vl:3b
"""

from __future__ import annotations

import json
import time
import uuid
import httpx

PROXY_BASE_URL = "http://127.0.0.1:8080"

QUERIES = [
    "what is denim",
    "cotton vs linen",
    "white sneakers",
    "kimono sizing",
    "current price of white sneakers",
]

def run_smoke():
    print("=" * 80)
    print("PHASE 3AM: LIVE STAGING SMOKE TEST EXECUTION")
    print(f"Target: Reverse Proxy Boundary at {PROXY_BASE_URL}")
    print("=" * 80)

    client = httpx.Client(base_url=PROXY_BASE_URL, timeout=90.0)

    # 1. Probes
    print("\n--- 1. HEALTH & READINESS PROBES ---")
    t0 = time.monotonic()
    resp_health = client.get("/health")
    lat_health = time.monotonic() - t0
    print(f"GET /health -> HTTP {resp_health.status_code} ({lat_health:.3f}s): {resp_health.json()}")

    t0 = time.monotonic()
    resp_ready = client.get("/ready")
    lat_ready = time.monotonic() - t0
    print(f"GET /ready -> HTTP {resp_ready.status_code} ({lat_ready:.3f}s): {resp_ready.json()}")

    t0 = time.monotonic()
    resp_ready_det = client.get("/ready?detailed=true")
    lat_ready_det = time.monotonic() - t0
    print(f"GET /ready?detailed=true -> HTTP {resp_ready_det.status_code} ({lat_ready_det:.3f}s): {resp_ready_det.json()}")

    # 2. Reasoning Queries
    print("\n--- 2. LIVE REASONING QUERIES ---")
    results = []
    for query in QUERIES:
        client_req_id = f"smoke-3am-{uuid.uuid4().hex[:8]}"
        payload = {
            "query": query,
            "max_conclusions": 3,
        }
        headers = {
            "X-Request-Id": client_req_id,
            "Content-Type": "application/json",
        }

        print(f"\nExecuting: '{query}' [Client Req ID: {client_req_id}] ...")
        t0 = time.monotonic()
        try:
            resp = client.post("/v1/reasoning", json=payload, headers=headers)
            elapsed = time.monotonic() - t0
            status_code = resp.status_code
            server_req_id = resp.headers.get("X-Request-Id", "MISSING")
            proxy_by = resp.headers.get("X-Proxy-By", "MISSING")

            raw_text = resp.text
            # Leakage checks
            raw_leakage = False
            leak_reasons = []
            if "<think>" in raw_text or "</think>" in raw_text:
                raw_leakage = True
                leak_reasons.append("Raw model thinking tags detected")
            if "```json" in raw_text and status_code == 200:
                raw_leakage = True
                leak_reasons.append("Raw markdown block in output")
            if "password" in raw_text.lower() or "secret" in raw_text.lower():
                raw_leakage = True
                leak_reasons.append("Secret keywords in body")

            try:
                data = resp.json()
            except Exception:
                data = {"raw": raw_text[:200]}

            error_class = None
            conclusions_count = 0
            if status_code == 200:
                error_class = "NONE (SUCCESS)"
                conclusions_count = len(data.get("conclusions", []))
            elif status_code == 502:
                error_class = data.get("error", {}).get("code", "AI_FAILURE")
            else:
                error_class = f"HTTP_{status_code}"

            record = {
                "query": query,
                "status_code": status_code,
                "latency_s": round(elapsed, 3),
                "request_id": server_req_id,
                "request_id_preserved": (server_req_id == client_req_id),
                "proxy_header": proxy_by,
                "error_classification": error_class,
                "conclusions_count": conclusions_count,
                "raw_leakage": raw_leakage,
                "leak_reasons": leak_reasons,
                "detail_snippet": data.get("error", {}).get("message") if status_code != 200 else data.get("primary_answer", "")[:120],
            }
            results.append(record)

            print(f"Status: HTTP {status_code} | Latency: {elapsed:.2f}s | Req-ID Preserved: {server_req_id == client_req_id}")
            print(f"Error Classification: {error_class}")
            print(f"Raw Output Leakage: {raw_leakage} (Reasons: {leak_reasons or 'None'})")
            if status_code == 200:
                print(f"Admitted Conclusions: {conclusions_count}")
                print(f"Primary Answer: {data.get('primary_answer', '')[:100]}...")
            else:
                print(f"Error Detail: {data.get('error', {}).get('message', '')}")

        except Exception as e:
            elapsed = time.monotonic() - t0
            print(f"EXCEPTION: {e}")
            results.append({
                "query": query,
                "status_code": "EXCEPTION",
                "latency_s": round(elapsed, 3),
                "request_id": client_req_id,
                "error_classification": str(e),
                "raw_leakage": False,
            })

    # 3. Observability telemetry verification
    print("\n--- 3. POST-SMOKE PROMETHEUS METRICS ---")
    resp_metrics = client.get("/metrics")
    print(f"GET /metrics -> HTTP {resp_metrics.status_code}")
    metrics_text = resp_metrics.text
    for line in metrics_text.splitlines():
        if line.startswith("fansivibe_http_status_total") or line.startswith("fansivibe_http_requests_total") or line.startswith("fansivibe_reasoning_duration_seconds_count"):
            print("  ", line)

    print("\n" + "=" * 80)
    print("LIVE SMOKE SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Query':<32} | {'HTTP':<5} | {'Latency':<8} | {'ReqID Match':<11} | {'Classification':<15} | {'Leakage':<7}")
    print("-" * 88)
    for r in results:
        match_str = "YES" if r.get("request_id_preserved") else "NO"
        leak_str = "CLEAN" if not r.get("raw_leakage") else "LEAK!"
        print(f"{r['query']:<32} | {r['status_code']:<5} | {r['latency_s']:<7}s | {match_str:<11} | {r['error_classification']:<15} | {leak_str:<7}")

    with open("staging_smoke_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to backend/staging_smoke_results.json")

if __name__ == "__main__":
    run_smoke()
