"""Staging reverse proxy & TLS boundary service (Phase 3AM).

Emulates the Nginx reverse proxy boundary in local/staging topologies:
- Listens on port 8080 (or configurable PROXY_PORT)
- Upstream target: FastAPI backend (default: http://127.0.0.1:8000)
- Enforces Layer 4 Cascading Timeout (90s gateway deadline)
- Enforces request body size limits (2MB max)
- Manages correlation IDs (preserves client X-Request-Id or generates UUID4)
- Injects standard proxy headers: X-Forwarded-For, X-Forwarded-Proto, X-Proxy-By
- Zero secrets or payload logging
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fansivibe.staging_proxy")

UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "http://127.0.0.1:8000").rstrip("/")
GATEWAY_TIMEOUT_S = float(os.environ.get("PROXY_TIMEOUT_S", "90.0"))
MAX_BODY_BYTES = 2 * 1024 * 1024  # 2MB

# Async HTTP client with connection pooling and 90s timeout
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(GATEWAY_TIMEOUT_S, connect=5.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
)

from starlette.routing import Route

async def reverse_proxy_handler(request: Request) -> Response:
    # 1. Correlation ID management
    client_req_id = request.headers.get("x-request-id")
    req_id = client_req_id or str(uuid.uuid4())

    # 2. Enforce request size bound
    content_len_hdr = request.headers.get("content-length")
    if content_len_hdr and int(content_len_hdr) > MAX_BODY_BYTES:
        return Response(
            content='{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request entity exceeds 2MB limit."}}',
            status_code=413,
            media_type="application/json",
            headers={"X-Request-Id": req_id, "X-Proxy-By": "Fansivibe-Staging-Proxy"},
        )

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return Response(
            content='{"error":{"code":"PAYLOAD_TOO_LARGE","message":"Request entity exceeds 2MB limit."}}',
            status_code=413,
            media_type="application/json",
            headers={"X-Request-Id": req_id, "X-Proxy-By": "Fansivibe-Staging-Proxy"},
        )

    # 3. Construct upstream target URL
    target_path = request.url.path
    if request.url.query:
        target_path = f"{target_path}?{request.url.query}"
    target_url = f"{UPSTREAM_URL}{target_path}"

    # 4. Prepare forward headers
    forward_headers = dict(request.headers)
    forward_headers["x-request-id"] = req_id
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
        resp_headers["x-proxy-by"] = "Fansivibe-Staging-Proxy"

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
            headers={"X-Request-Id": req_id, "X-Proxy-By": "Fansivibe-Staging-Proxy"},
        )
    except httpx.ConnectError as exc:
        logger.warning("Gateway connect error reaching upstream %s [req_id=%s]: %s", target_url, req_id, exc)
        return Response(
            content='{"error":{"code":"BAD_GATEWAY","message":"Reverse proxy unable to connect to backend service."}}',
            status_code=502,
            media_type="application/json",
            headers={"X-Request-Id": req_id, "X-Proxy-By": "Fansivibe-Staging-Proxy"},
        )
    except Exception as exc:
        logger.error("Unexpected proxy error [req_id=%s]: %s", req_id, exc)
        return Response(
            content='{"error":{"code":"BAD_GATEWAY","message":"Reverse proxy failure."}}',
            status_code=502,
            media_type="application/json",
            headers={"X-Request-Id": req_id, "X-Proxy-By": "Fansivibe-Staging-Proxy"},
        )


proxy_app = Starlette(
    routes=[
        Route("/", reverse_proxy_handler, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
        Route("/{path:path}", reverse_proxy_handler, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
    ]
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("deploy.staging_proxy:proxy_app", host="127.0.0.1", port=8080, log_level="info")
