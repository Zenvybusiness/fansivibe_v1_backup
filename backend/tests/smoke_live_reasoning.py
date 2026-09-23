"""Live end-to-end smoke test through the FastAPI application boundary for Phase 3AJ.

Runs against local Ollama with model qwen2.5vl:3b:
  1. one supported explanation: 'what is denim'
  2. one comparison: 'cotton vs linen'
  3. one styling/matching query: 'white sneakers'
  4. one insufficient-evidence query: 'kimono sizing'
  5. one unsupported/current-information query: 'current price of white sneakers'
"""

import json
import time
from starlette.testclient import TestClient
from app.ai.ollama_reasoner import OllamaFashionReasoner, ReasoningConfig
from app.api.deps import get_fashion_reasoner
from app.main import app

def run_smoke():
    config = ReasoningConfig(model="qwen2.5vl:3b", timeout_s=120.0, temperature=0.0)
    real_reasoner = OllamaFashionReasoner(config)
    app.dependency_overrides[get_fashion_reasoner] = lambda: real_reasoner

    client = TestClient(app)
    queries = [
        {"name": "supported_explanation", "payload": {"query": "what is denim", "intent": "explain"}},
        {"name": "comparison", "payload": {"query": "cotton vs linen"}},
        {"name": "styling_matching", "payload": {"query": "white sneakers", "intent": "match"}},
        {"name": "insufficient_evidence", "payload": {"query": "kimono sizing", "intent": "explain"}},
        {"name": "unsupported_info", "payload": {"query": "current price of white sneakers", "intent": "match"}},
    ]

    results = []
    print("=" * 60)
    print("STARTING PHASE 3AJ LIVE SMOKE TEST VIA FASTAPI BOUNDARY")
    print(f"Model: {config.model}, Base URL: {config.base_url}")
    print("=" * 60)

    for item in queries:
        name = item["name"]
        payload = item["payload"]
        print(f"\n---> Running: {name} (query: '{payload['query']}')")
        started = time.perf_counter()
        try:
            resp = client.post("/v1/reasoning", json=payload)
            elapsed = time.perf_counter() - started
            status = resp.status_code
            data = resp.json()
            print(f"Status: {status} in {elapsed:.2f}s")
            if status == 200:
                print(f"Answer: {data.get('answer')[:80]}...")
                print(f"Conclusions: {len(data.get('conclusions', []))}")
                for idx, c in enumerate(data.get('conclusions', [])):
                    print(f"  [{idx}] statement: {c.get('statement')}")
                    print(f"      evidence_ids: {c.get('evidence_ids')}")
                    print(f"      ffo_refs: {c.get('ffo_refs')}")
                    print(f"      standing: {c.get('standing')}")
                print(f"Confidence: {data.get('confidence')}")
                print(f"Unsupported: {data.get('unsupported')}")
                print(f"Missing evidence: {data.get('missing_evidence')}")
                print(f"Versions: {data.get('versions')}")
            else:
                print(f"Error payload: {data}")
            results.append({"name": name, "status": status, "elapsed": elapsed, "data": data})
        except Exception as exc:
            elapsed = time.perf_counter() - started
            print(f"EXCEPTION: {type(exc).__name__}: {exc} in {elapsed:.2f}s")
            results.append({"name": name, "status": "exception", "error": str(exc), "elapsed": elapsed})

    print("\n" + "=" * 60)
    print("SMOKE TEST SUMMARY:")
    for r in results:
        print(f"  {r['name']}: status={r['status']} elapsed={r['elapsed']:.2f}s")
    print("=" * 60)

    # Save output for deliverable
    with open("live_smoke_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_smoke()
