"""Fansivibe backend AI service.

Runs the "own AI" assistant engine. The Flutter app never talks to an AI
provider directly — it calls this service, which returns typed structured
replies. See `backend/README.md`.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import uuid
from typing import Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import engine
from app.ai.lifecycle import OllamaLifecycleManager
from app.api import errors
from app.api.deps import get_current_user_id, get_lifecycle_manager
from app.api.errors import ApiError, database_failure
from app.api.routers import (
    analysis,
    assistant,
    auth,
    discovery,
    events,
    feedback,
    knowledge,
    learning,
    looks,
    media,
    outfits,
    reasoning,
    trend_analysis,
    trending,
    tryon,
    users,
    wardrobe,
)
from app.application.outfits import GenerateOutfit
from app.config.settings import get_settings
from app.domain.ports.repositories import (
    SavedLookRepository,
    UserProfileRecord,
    WardrobeItemRepository,
)
from app.domain.services.analysis_rules import resolve_preferred_item_ids
from app.infrastructure.db.repositories import (
    SavedLookRepositorySQL,
    UserStateRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.infrastructure.db.session import get_db
from app.models.schemas import (
    AssistantReply,
    AssistantRequest,
    FaceData,
    UserContext,
    WardrobeItem,
)

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
app.include_router(discovery.router)
app.include_router(events.router)
app.include_router(feedback.router)
app.include_router(knowledge.router)
app.include_router(learning.router)
app.include_router(looks.router)
app.include_router(media.router)
app.include_router(outfits.router)
app.include_router(reasoning.router)
app.include_router(trend_analysis.router)
app.include_router(trending.router)
app.include_router(tryon.router)
app.include_router(users.router)
app.include_router(wardrobe.router)

# Mount static asset directory for development fixtures and media assets
_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


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


def _resolve_assistant_face(
    record: Optional[UserProfileRecord],
    client_face: Optional[FaceData],
) -> Optional[FaceData]:
    """Resolve authoritative face data.

    Server `style_profile` is authoritative for authenticated users.
    If server attributes are unmeasured/empty, preserve client transient attributes if present.
    Never persists, never writes, never throws.
    """
    style = (
        record.style_profile
        if record is not None and isinstance(record.style_profile, dict)
        else {}
    )
    server_face = style.get("face_shape")
    server_skin = style.get("skin_tone")
    server_body = style.get("body_type")
    server_style = style.get("style_type")

    face_shape = (
        str(server_face).strip()
        if server_face and str(server_face).strip()
        else (client_face.faceShape if client_face else None)
    )
    skin_tone = (
        str(server_skin).strip()
        if server_skin and str(server_skin).strip()
        else (client_face.skinTone if client_face else None)
    )
    body_type = (
        str(server_body).strip()
        if server_body and str(server_body).strip()
        else (client_face.bodyType if client_face else None)
    )
    style_type = (
        str(server_style).strip()
        if server_style and str(server_style).strip()
        else (client_face.styleType if client_face else None)
    )

    if not any((face_shape, skin_tone, body_type, style_type)):
        return None

    return FaceData(
        faceShape=face_shape or None,
        skinTone=skin_tone or None,
        bodyType=body_type or None,
        styleType=style_type or None,
    )


class _CachedSavedLooksWrapper:
    def __init__(self, rows: list, total: int) -> None:
        self._rows = rows
        self._total = total

    def list_for_user(self, *, user_id: UUID, page: int = 1, page_size: int = 100):
        return self._rows, self._total


def _load_authoritative_wardrobe(
    repo: WardrobeItemRepository, user_id: UUID, db: Session
) -> list[WardrobeItem]:
    """Load authoritative wardrobe from PostgreSQL for an authenticated user.

    Preserves garment IDs, names, categories, colors, materials, and favorite flags.
    Never merges unverified client snapshot items into authenticated wardrobe.
    Distinguishes an empty wardrobe (returns empty list) from a repository failure (raises database_failure).
    """
    if hasattr(repo, "_session") and not hasattr(getattr(repo, "_session"), "execute"):
        return []

    items: list[WardrobeItem] = []
    page = 1
    while True:
        try:
            batch, total = repo.get_for_user(
                user_id=user_id, page=page, page_size=100
            )
        except Exception as exc:
            logger.exception(
                "Authoritative wardrobe lookup failed for user %s: %s", user_id, exc
            )
            raise database_failure() from exc

        for record in batch or []:
            item_id = str(getattr(record, "id", ""))
            name = getattr(record, "name", "")
            category = getattr(record, "category", getattr(record, "category_id", ""))
            color = getattr(record, "color", getattr(record, "color_id", ""))
            material = getattr(record, "material", getattr(record, "material_id", None))
            is_fav = bool(getattr(record, "is_favorite", getattr(record, "isFavorite", False)))
            items.append(
                WardrobeItem(
                    id=item_id,
                    name=name,
                    category=category,
                    color=color,
                    material=material,
                    isFavorite=is_fav,
                )
            )
        if len(items) >= total or not batch:
            break
        page += 1

    return items


def _load_authoritative_saved_looks(
    repo: SavedLookRepository, user_id: UUID, db: Session
) -> tuple[list[str], list[str]]:
    """Load authoritative saved looks and resolve preferred item IDs in a single query.

    Returns (saved_looks_strings, preferred_item_ids).
    Missing saved-look data degrades safely to empty lists.
    """
    if hasattr(repo, "_session") and not hasattr(getattr(repo, "_session"), "execute"):
        return [], []

    saved_looks_list: list[str] = []
    preferred_item_ids: list[str] = []

    try:
        rows, total = repo.list_for_user(user_id=user_id, page=1, page_size=100)
    except Exception as exc:
        logger.warning(
            "Saved look listing failed for user %s (degrading safely): %s",
            user_id,
            exc,
        )
        return [], []

    for r in rows or []:
        look_id = getattr(r, "look_id", None)
        title = getattr(r, "title", None)
        if look_id and str(look_id) not in saved_looks_list:
            saved_looks_list.append(str(look_id))
        if title and str(title) not in saved_looks_list:
            saved_looks_list.append(str(title))

    try:
        pref_set = resolve_preferred_item_ids(
            saved_looks=_CachedSavedLooksWrapper(rows or [], total),
            user_id=user_id,
        )
        preferred_item_ids = sorted(list(pref_set))
    except Exception:
        preferred_item_ids = []

    return saved_looks_list, preferred_item_ids


@app.post("/v1/assistant/chat", response_model=AssistantReply)
def assistant_chat(
    request: AssistantRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> AssistantReply:
    """Chat with the assistant.

    Stage 1D Batch 4B.2: Authenticated Wardrobe & Profile Data Authority.
    - Authenticated users derive wardrobe, preferences, style profile, and saved looks
      strictly from PostgreSQL repositories (never from volatile client snapshots).
    - Unauthenticated guest requests strictly preserve client context without database
      lookups, invented UUIDs, or persistence (D10 Option A).
    """
    user_id: UUID | None = None
    try:
        user_id = get_current_user_id(authorization, db)
    except ApiError:
        user_id = None

    client_occasions = (
        list(request.user.preferredOccasions) if request.user else []
    )

    if user_id is None:
        # Guest request: zero DB access, preserve client context, zero persistence
        return engine.handle(request, preferred_occasions=client_occasions)

    # Authenticated user: load authoritative data from PostgreSQL
    user_state_repo = UserStateRepositorySQL(db)
    wardrobe_repo = WardrobeItemRepositorySQL(db)
    saved_looks_repo = SavedLookRepositorySQL(db)

    try:
        record = user_state_repo.get_profile(user_id=user_id)
    except Exception:
        record = None

    occasions = _resolve_assistant_occasions(record, client_occasions)
    face = _resolve_assistant_face(record, request.user.face if request.user else None)
    wardrobe = _load_authoritative_wardrobe(wardrobe_repo, user_id=user_id, db=db)
    saved_looks, preferred_item_ids = _load_authoritative_saved_looks(
        saved_looks_repo, user_id=user_id, db=db
    )

    auth_context = UserContext(
        wardrobe=wardrobe,
        face=face,
        savedLooks=saved_looks,
        preferredOccasions=occasions,
    )
    auth_request = AssistantRequest(
        messages=request.messages,
        user=auth_context,
    )

    generate_outfit = GenerateOutfit(
        wardrobe_items=wardrobe_repo,
        user_state=user_state_repo,
        saved_looks=saved_looks_repo,
    )

    return engine.handle(
        auth_request,
        user_id=user_id,
        preferred_occasions=occasions,
        preferred_item_ids=preferred_item_ids,
        generate_outfit=generate_outfit,
        wardrobe_items=wardrobe_repo,
        user_state=user_state_repo,
    )


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
