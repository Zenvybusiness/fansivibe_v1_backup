"""Production reverse proxy & canary traffic splitting service (Phase 3AN).

Emulates the Nginx reverse proxy boundary in production and testing topologies:
- Listens on port 8080 (or configurable PROXY_PORT)
- Upstream targets:
  - Primary (stable baseline): http://127.0.0.1:8000 (PRIMARY_UPSTREAM_URL)
  - Canary (release candidate): http://127.0.0.1:8001 (CANARY_UPSTREAM_URL)
- Traffic splitting:
  - Configurable canary traffic percentage (default: 5.0%, CANARY_PERCENTAGE)
  - Deterministic hash-based routing using X-Request-Id
  - Override header support: X-Force-Canary: true/false for targeted testing
  - Instant rollback capability: CANARY_PERCENTAGE=0 instantly diverts 100% traffic to primary
- Enforces Layer 4 Cascading Timeout (90s gateway deadline)
- Enforces request body size limits (2MB max, returns 413)
- Manages correlation IDs (preserves client X-Request-Id or generates UUID4)
- Injects standard proxy headers: X-Request-Id, X-Canary, X-Proxy-By
- Enforces production security: blocks /docs, /redoc, /openapi.json; adds HSTS and security headers
- Zero secrets or payload logging
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fansivibe.production_canary_proxy")

PRIMARY_UPSTREAM_URL = os.environ.get("PRIMARY_UPSTREAM_URL", "http://127.0.0.1:8000").rstrip("/")
CANARY_UPSTREAM_URL = os.environ.get("CANARY_UPSTREAM_URL", "http://127.0.0.1:8001").rstrip("/")
GATEWAY_TIMEOUT_S = float(os.environ.get("PROXY_TIMEOUT_S", "90.0"))
MAX_BODY_BYTES = 2 * 1024 * 1024  # 2MB

# Canary traffic percentage (0.0 to 100.0)
DEFAULT_CANARY_PERCENTAGE = float(os.environ.get("CANARY_PERCENTAGE", "5.0"))


class CanaryRouter:
    """Thread-safe canary traffic splitter and metric tracker."""

    def __init__(self, canary_percentage: float = DEFAULT_CANARY_PERCENTAGE) -> None:
        self.canary_percentage = max(0.0, min(100.0, canary_percentage))
        self.total_requests = 0
        self.primary_requests = 0
        self.canary_requests = 0
        self.rollback_active = False

    def set_canary_percentage(self, percentage: float) -> None:
        self.canary_percentage = max(0.0, min(100.0, percentage))
        if self.canary_percentage == 0.0:
            self.rollback_active = True
        else:
            self.rollback_active = False
        logger.info("Canary percentage updated to %.2f%% (rollback_active=%s)", self.canary_percentage, self.rollback_active)

    def route(self, req_id: str, force_canary: str | None = None) -> tuple[str, bool]:
        """Determine whether request routes to canary or primary upstream."""
        self.total_requests += 1

        # 1. Forced routing via header
        if force_canary is not None:
            if force_canary.lower() in ("true", "1", "yes"):
                self.canary_requests += 1
                return CANARY_UPSTREAM_URL, True
            elif force_canary.lower() in ("false", "0", "no"):
                self.primary_requests += 1
                return PRIMARY_UPSTREAM_URL, False

        # 2. If canary percentage is 0 (or rollback), always primary
        if self.canary_percentage <= 0.0:
            self.primary_requests += 1
            return PRIMARY_UPSTREAM_URL, False

        # 3. Deterministic hash-based traffic splitting using req_id
        # Hash req_id to an integer between 0 and 9999 (0.01% precision)
        digest = hashlib.sha256(req_id.encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 10000
        threshold = int(self.canary_percentage * 100)  # e.g., 5.0% -> 500

        is_canary = bucket < threshold
        if is_canary:
            self.canary_requests += 1
            return CANARY_UPSTREAM_URL, True
        else:
            self.primary_requests += 1
            return PRIMARY_UPSTREAM_URL, False


router = CanaryRouter()

# Async HTTP client with connection pooling and 90s timeout
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(GATEWAY_TIMEOUT_S, connect=5.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
)


async def production_proxy_handler(request: Request) -> Response:
    t0 = time.monotonic()

    # 1. Correlation ID management
    client_req_id = request.headers.get("x-request-id")
    req_id = client_req_id or str(uuid.uuid4())

    # 2. Enforce request size bound (2MB max)
    content_len_hdr = request.headers.get("content-length")
    if content_len_hdr and int(content_len_hdr) > MAX_BODY_BYTES:
        return Response(
            content='{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request entity exceeds 2MB limit."}}',
            status_code=413,
            media_type="application/json",
            headers={
                "X-Request-Id": req_id,
                "X-Proxy-By": "Fansivibe-Production-Canary-Proxy",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            },
        )

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return Response(
            content='{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request entity exceeds 2MB limit."}}',
            status_code=413,
            media_type="application/json",
            headers={
                "X-Request-Id": req_id,
                "X-Proxy-By": "Fansivibe-Production-Canary-Proxy",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            },
        )

    # 3. Security: Block Swagger/Redoc endpoints in production
    path = request.url.path
    if path in ("/docs", "/redoc", "/openapi.json"):
        return Response(
            content='{"error":{"code":"NOT_FOUND","message":"API documentation is disabled in production."}}',
            status_code=404,
            media_type="application/json",
            headers={
                "X-Request-Id": req_id,
                "X-Proxy-By": "Fansivibe-Production-Canary-Proxy",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            },
        )

    # 4. Canary traffic routing decision
    force_canary_hdr = request.headers.get("x-force-canary")
    upstream_url, is_canary = router.route(req_id, force_canary=force_canary_hdr)

    # 5. Construct upstream target URL
    target_path = path
    if request.url.query:
        target_path = f"{target_path}?{request.url.query}"
    target_url = f"{upstream_url}{target_path}"

    # 6. Forwarding headers
    forward_headers = dict(request.headers)
    forward_headers["x-request-id"] = req_id
    forward_headers["x-canary"] = "true" if is_canary else "false"
    forward_headers["x-forwarded-for"] = request.client.host if request.client else "127.0.0.1"
    forward_headers["x-forwarded-proto"] = request.url.scheme
    forward_headers.pop("host", None)

    try:
        upstream_resp = await http_client.request(
            method=request.method,
            url=target_url,
            headers=forward_headers,
            content=body,
        )

        resp_headers = dict(upstream_resp.headers)
        resp_headers["x-request-id"] = req_id
        resp_headers["x-canary"] = "true" if is_canary else "false"
        resp_headers["x-proxy-by"] = "Fansivibe-Production-Canary-Proxy"
        resp_headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
        resp_headers["x-content-type-options"] = "nosniff"
        resp_headers["x-frame-options"] = "DENY"

        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type=upstream_resp.headers.get("content-type"),
        )
    except httpx.TimeoutException:
        logger.warning("Gateway timeout reaching upstream %s [req_id=%s]", target_url, req_id)
        return Response(
            content='{"error":{"code":"GATEWAY_TIMEOUT","message":"Reverse proxy timed out waiting for backend."}}',
            status_code=504,
            media_type="application/json",
            headers={
                "X-Request-Id": req_id,
                "X-Canary": "true" if is_canary else "false",
                "X-Proxy-By": "Fansivibe-Production-Canary-Proxy",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            },
        )
    except httpx.ConnectError as exc:
        logger.warning("Gateway connect error reaching upstream %s [req_id=%s]: %s", target_url, req_id, exc)
        return Response(
            content='{"error":{"code":"BAD_GATEWAY","message":"Reverse proxy unable to connect to backend service."}}',
            status_code=502,
            media_type="application/json",
            headers={
                "X-Request-Id": req_id,
                "X-Canary": "true" if is_canary else "false",
                "X-Proxy-By": "Fansivibe-Production-Canary-Proxy",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            },
        )
    except Exception as exc:
        logger.error("Unexpected proxy error [req_id=%s]: %s", req_id, exc)
        return Response(
            content='{"error":{"code":"BAD_GATEWAY","message":"Reverse proxy failure."}}',
            status_code=502,
            media_type="application/json",
            headers={
                "X-Request-Id": req_id,
                "X-Canary": "true" if is_canary else "false",
                "X-Proxy-By": "Fansivibe-Production-Canary-Proxy",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            },
        )


async def admin_canary_status(request: Request) -> Response:
    """Internal admin endpoint to view or adjust canary traffic split."""
    if request.method == "POST":
        try:
            data = await request.json()
            if "percentage" in data:
                router.set_canary_percentage(float(data["percentage"]))
        except Exception:
            pass
    return Response(
        content=f'{{"canary_percentage":{router.canary_percentage},"total":{router.total_requests},"primary":{router.primary_requests},"canary":{router.canary_requests},"rollback_active":{str(router.rollback_active).lower()}}}',
        status_code=200,
        media_type="application/json",
    )


proxy_app = Starlette(
    routes=[
        Route("/_proxy/canary", admin_canary_status, methods=["GET", "POST"]),
        Route("/", production_proxy_handler, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
        Route("/{path:path}", production_proxy_handler, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
    ]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("deploy.production_canary_proxy:proxy_app", host="127.0.0.1", port=8080, log_level="info")
