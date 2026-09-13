"""Fansivibe backend AI service.

Runs the "own AI" assistant engine. The Flutter app never talks to an AI
provider directly — it calls this service, which returns typed structured
replies. See `backend/README.md`.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import engine
from app.api import errors
from app.api.deps import get_current_user_id
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
    users,
    wardrobe,
)
from app.config.settings import get_settings
from app.domain.ports.repositories import UserProfileRecord
from app.infrastructure.db.repositories import UserStateRepositorySQL
from app.infrastructure.db.session import get_db
from app.models.schemas import AssistantReply, AssistantRequest

settings = get_settings()

app = FastAPI(
    title="Fansivibe AI",
    version="0.1.0",
    docs_url="/docs" if settings.is_docs_enabled else None,
    redoc_url="/redoc" if settings.is_docs_enabled else None,
    openapi_url="/openapi.json" if settings.is_docs_enabled else None,
)

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
app.include_router(users.router)
app.include_router(wardrobe.router)


@app.get("/health")
def health() -> dict:
    """Liveness probe: verifies process responsiveness."""
    return {"status": "ok"}


@app.get("/ready")
@app.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    """Readiness probe: validates database connectivity before routing traffic."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "disconnected"},
        )


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
