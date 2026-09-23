"""Fansivibe backend AI service.

Runs the "own AI" assistant engine. The Flutter app never talks to an AI
provider directly — it calls this service, which returns typed structured
replies. See `backend/README.md`.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import uuid
from typing import Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import engine
from app.ai.lifecycle import OllamaLifecycleManager
from app.api import errors
from app.api.deps import get_current_user_id, get_lifecycle_manager
from app.api.errors import ApiError
from app.api.routers import (
    analysis,
    assistant,
    auth,
    events,
    feedback,
    knowledge,
    learning,
    looks,
    outfits,
    reasoning,
    users,
    wardrobe,
)
from app.config.settings import get_settings
from app.domain.ports.repositories import UserProfileRecord
from app.infrastructure.db.repositories import UserStateRepositorySQL
from app.infrastructure.db.session import get_db
from app.models.schemas import AssistantReply, AssistantRequest

logger = logging.getLogger("fansivibe.main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: background model warmup & probe on startup."""
    current_settings = get_settings()
    if not current_settings.disable_reasoning:
        try:
            lifecycle = OllamaLifecycleManager()
            status = lifecycle.check_availability(timeout_s=2.0)
            if status.available and status.model_present:
                logger.info(
                    "Ollama model '%s' available. Starting background warmup...",
                    status.model_name,
                )
                asyncio.create_task(asyncio.to_thread(lifecycle.warmup, 25.0))
            else:
                logger.warning(
                    "Ollama probe on startup: %s",
                    status.error or f"Model '{status.model_name}' missing",
                )
        except Exception as exc:
            logger.warning("Ollama startup probe failed: %s", exc)
    yield


app = FastAPI(
    title="Fansivibe AI",
    version="0.1.0",
    docs_url="/docs" if settings.is_docs_enabled else None,
    redoc_url="/redoc" if settings.is_docs_enabled else None,
    openapi_url="/openapi.json" if settings.is_docs_enabled else None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_and_correlation_headers(request: Request, call_next):
    """Add correlation ID, security headers, and record operational telemetry."""
    import time
    from app.telemetry.metrics import get_metrics_collector

    req_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = req_id
    t0 = time.monotonic()

    response = await call_next(request)
    duration_s = time.monotonic() - t0

    response.headers["X-Request-Id"] = req_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'"
    )

    current_settings = get_settings()
    if current_settings.is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # Operational metrics (Objective 4)
    get_metrics_collector().record_http_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_s=duration_s,
    )

    return response


_CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_CORS_ALLOW_HEADERS = [
    "Authorization",
    "Content-Type",
    "Idempotency-Key",
    "X-Request-Id",
    "Accept",
    "Origin",
]

_cors_allow_origins = list(settings.cors_origins)
_cors_allow_origin_regex = settings.effective_cors_origin_regex
if _cors_allow_origins or _cors_allow_origin_regex:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allow_origins,
        allow_origin_regex=_cors_allow_origin_regex,
        # Bearer-token auth needs no cookies; credentials stay False unless
        # explicitly enabled with non-wildcard origins (see settings).
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=_CORS_ALLOW_METHODS,
        allow_headers=_CORS_ALLOW_HEADERS,
    )

errors.register_error_handlers(app)
app.include_router(auth.router)
app.include_router(analysis.router)
app.include_router(assistant.router)
app.include_router(events.router)
app.include_router(feedback.router)
app.include_router(knowledge.router)
app.include_router(learning.router)
app.include_router(looks.router)
app.include_router(outfits.router)
app.include_router(reasoning.router)
app.include_router(users.router)
app.include_router(wardrobe.router)


@app.get("/health")
def health() -> dict:
    """Liveness probe: verifies process responsiveness."""
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    """Prometheus-compatible operational metrics endpoint (Objective 4)."""
    from fastapi.responses import Response
    from app.telemetry.metrics import get_metrics_collector

    content = get_metrics_collector().format_prometheus()
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


_corpus_ready_cached: bool | None = None


def _check_corpus() -> bool:
    global _corpus_ready_cached
    if _corpus_ready_cached is not None:
        return _corpus_ready_cached
    try:
        from app.data.ffo import FFO_VERSION, corpus
        from app.domain.services.ffo_reasoning import corpus_digest

        docs = corpus.load_documents()
        index = corpus.build_index(docs)
        versions_map = corpus.corpus_versions(index)
        digest = corpus_digest(versions_map, FFO_VERSION)
        _corpus_ready_cached = bool(digest)
    except Exception:
        _corpus_ready_cached = False
    return _corpus_ready_cached


@app.get("/ready")
@app.get("/health/ready")
def ready(
    detailed: bool = False,
    db: Session = Depends(get_db),
    lifecycle: OllamaLifecycleManager = Depends(get_lifecycle_manager),
) -> dict:
    """Readiness probe: validates dependencies before routing traffic.

    When `detailed=False` (default): returns truthful DB readiness
    `{"status": "ready", "database": "connected"}` or 503 `{"status": "not_ready", "database": "disconnected"}`.

    When `detailed=True`: reports structured checks across Database, FFO Corpus,
    and Ollama Reasoning subsystem.
    """
    from app.telemetry.metrics import get_metrics_collector
    collector = get_metrics_collector()

    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    if not detailed:
        collector.set_readiness_status(db_ok)
        if db_ok:
            return {"status": "ready", "database": "connected"}
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "disconnected"},
        )

    current_settings = get_settings()
    corpus_ok = _check_corpus()

    if current_settings.disable_reasoning:
        ai_ok = True
        reasoning_status = "disabled"
    else:
        ai_status = lifecycle.check_availability(timeout_s=1.5)
        ai_ok = ai_status.available and ai_status.model_present
        reasoning_status = (
            "ok"
            if ai_ok
            else ("unavailable" if not ai_status.available else "model_missing")
        )

    all_ready = db_ok and corpus_ok
    status_str = (
        "ready"
        if (all_ready and ai_ok)
        else ("ready_degraded" if all_ready else "not_ready")
    )
    status_code = 200 if all_ready else 503

    collector.set_readiness_status(status_code == 200)
    collector.set_ollama_availability(ai_ok if not current_settings.disable_reasoning else True)

    payload = {
        "status": status_str,
        "database": "connected" if db_ok else "disconnected",
        "checks": {
            "database": "ok" if db_ok else "disconnected",
            "ffo_corpus": "ok" if corpus_ok else "error",
            "reasoning": reasoning_status,
            "reasoning_model": lifecycle.model,
        },
    }
    return JSONResponse(status_code=status_code, content=payload)


@app.post("/v1/assistant/chat", response_model=AssistantReply)
def assistant_chat(
    request: AssistantRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> AssistantReply:
    """Chat with the assistant (STEP 11.10: server-authoritative occasions).

    Authentication stays optional so existing unauthenticated clients keep
    working: without a valid Bearer token the request falls back to the
    client-provided occasions. With a token, the persisted
    ``preferred_occasions`` win when valid and non-empty; every other case —
    missing row, missing/malformed/empty server value, repository failure —
    falls back to ``request.user.preferredOccasions`` without throwing.
    Resolution is read-only (no database write).
    """
    user_id: UUID | None = None
    try:
        user_id = get_current_user_id(authorization, db)
    except ApiError:
        user_id = None

    client_occasions = (
        list(request.user.preferredOccasions) if request.user else []
    )
    occasions = client_occasions
    if user_id is not None:
        try:
            record = UserStateRepositorySQL(db).get_profile(user_id=user_id)
        except Exception:
            record = None
        occasions = _resolve_assistant_occasions(record, client_occasions)
    return engine.handle(request, preferred_occasions=occasions)


def _resolve_assistant_occasions(
    record: Optional[UserProfileRecord], client_occasions: list[str]
) -> list[str]:
    """Precedence: valid non-empty server `preferred_occasions`, else client.

    Never merges, never normalizes, never throws, never writes.
    """
    preferences = record.preferences if record is not None else None
    if isinstance(preferences, dict):
        raw = preferences.get("preferred_occasions")
        if (
            isinstance(raw, list)
            and len(raw) > 0
            and all(isinstance(item, str) for item in raw)
        ):
            return list(raw)
    return list(client_occasions)
