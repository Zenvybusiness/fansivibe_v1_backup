"""Dependency seam — resolves a Bearer token to a ``user_id``.

D-AUTH-1 (real authentication): JWT access tokens minted by
`POST /v1/auth/register` / `/v1/auth/login` verify here against
signature, expiry, and the R51 session store (`user_sessions`) via
`application.auth.resolve_session` — the frozen
``verify_access_token(token) -> Principal`` seam. Owner-scoping (OW-1)
is fully enforced in the repositories regardless of which path
produced the id.

Dev fallback: the historical single dev token maps to the seeded dev
user ONLY when `FANSIVIBE_ALLOW_DEV_TOKEN` is true (tests/dev). It
defaults to false, so the shared bootstrap identity can never
silently become production identity.
"""

from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError, authentication_error
from app.application.auth import resolve_session
from app.config.settings import get_settings
from app.domain.ports.repositories import TrendRepository
from app.infrastructure.db.models import UserState, Users
from app.infrastructure.db.repositories import AuthRepositorySQL
from app.infrastructure.db.session import get_db

if TYPE_CHECKING:
    from app.domain.ports.external import WeatherProvider

DEV_TOKEN = get_settings().dev_token
_DEV_PROVIDER = "dev"
_DEV_SUBJECT = "dev-user"
_DEV_DISPLAY_NAME = "Dev User"
_logger = logging.getLogger("fansivibe.api.deps")


def _seeded_dev_user(session: Session) -> UUID:
    user = session.execute(
        select(Users).where(
            Users.auth_provider == _DEV_PROVIDER,
            Users.auth_subject == _DEV_SUBJECT,
        )
    ).scalar_one_or_none()
    if user is None:
        user = Users(
            auth_provider=_DEV_PROVIDER,
            auth_subject=_DEV_SUBJECT,
            display_name=_DEV_DISPLAY_NAME,
        )
        session.add(user)
        session.flush()
        session.add(UserState(user_id=user.id))
        session.commit()
    return user.id


def get_current_user_id(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UUID:
    """Bearer-token → authenticated ``user_id`` (D-AUTH-1)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise authentication_error()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise authentication_error()
    settings = get_settings()
    try:
        user_id, _ = resolve_session(
            AuthRepositorySQL(db), token=token, secret=settings.auth_secret
        )
        return user_id
    except ApiError:
        pass
    if settings.allow_dev_token and token == settings.dev_token:
        try:
            return _seeded_dev_user(db)
        except Exception:
            raise ApiError(
                status_code=500,
                code="DATABASE_FAILURE",
                message="Something went wrong while saving your data. Please try again.",
            )
    raise authentication_error()


def get_trend_repository(db: Session = Depends(get_db)) -> TrendRepository:
    """Read-only D6 trend repository (D7 endpoint dependency seam).

    A dependency provider (like the reasoner/lifecycle ones) so tests can
    override it with a stub and exercise the API without a database.
    """
    from app.infrastructure.db.repositories import TrendRepositorySQL

    return TrendRepositorySQL(db)


def get_gpu_scheduler():
    """Dependency provider for GPUResourceScheduler (Sub-Batch 3.1).

    Returns the process-local thread-safe singleton GPU scheduler.
    Tests override this via app.dependency_overrides[get_gpu_scheduler].
    """
    from app.ai.manager.scheduler import get_gpu_scheduler as _get_gpu_scheduler

    return _get_gpu_scheduler()


def get_fashion_reasoner(
    scheduler: Any = Depends(get_gpu_scheduler),
):
    """Dependency provider for the fashion reasoning service (Phase 3AJ / Phase 2 Batch 3.2).

    Instantiates the OllamaFashionReasoner adapter configured from Settings
    and the shared GPUResourceScheduler singleton, allowing tests and mocks
    to override via FastAPI's `app.dependency_overrides`.
    """
    from app.ai.ollama_reasoner import OllamaFashionReasoner, ReasoningConfig
    from app.config.settings import get_settings
    from fastapi.params import Depends as DependsType

    settings = get_settings()
    config = ReasoningConfig.from_env(
        base_url=settings.reasoning_host,
        model=settings.reasoning_model,
        timeout_s=settings.reasoning_timeout_s,
        temperature=settings.reasoning_temperature,
        max_retries=settings.reasoning_max_retries,
        keep_alive=settings.reasoning_keep_alive,
    )
    sched = get_gpu_scheduler() if isinstance(scheduler, DependsType) else scheduler
    return OllamaFashionReasoner(config=config, scheduler=sched)


def get_lifecycle_manager():
    """Dependency provider for the Ollama lifecycle manager (Phase 3AL)."""
    from app.ai.lifecycle import OllamaLifecycleManager

    return OllamaLifecycleManager()


def get_optional_user_id(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UUID | None:
    """Optional Bearer-token auth: returns user_id if authenticated, or None for guest requests.

    If an Authorization header is provided, it must be valid; malformed/expired
    tokens fail closed with 401 instead of masquerading as guests.
    """
    if not authorization:
        return None
    return get_current_user_id(authorization=authorization, db=db)


def get_candidate_repository(db: Session = Depends(get_db)):
    """Discovery candidate repository dependency seam."""
    from app.infrastructure.db.repositories import DiscoveryRepositorySQL

    return DiscoveryRepositorySQL(db)


def get_user_state_repository(db: Session = Depends(get_db)):
    """User state repository dependency seam."""
    from app.infrastructure.db.repositories import UserStateRepositorySQL

    return UserStateRepositorySQL(db)


def get_wardrobe_repository(db: Session = Depends(get_db)):
    """Wardrobe item repository dependency seam."""
    from app.infrastructure.db.repositories import WardrobeItemRepositorySQL

    return WardrobeItemRepositorySQL(db)


def get_discovery_event_repository(db: Session = Depends(get_db)):
    """Discovery event repository dependency seam (DISCOVERY-10A)."""
    from app.infrastructure.db.repositories import DiscoveryEventRepositorySQL

    return DiscoveryEventRepositorySQL(db)


def require_operator_auth(
    request: Request,
    x_operator_key: str | None = Header(default=None, alias="X-Operator-Key"),
) -> None:
    """Require configured operator API key for maintenance endpoints.

    User JWTs and dev user tokens are never accepted here. Fails closed
    if FANSIVIBE_OPERATOR_API_KEY is unconfigured.
    """
    from app.telemetry.metrics import get_metrics_collector

    endpoint = request.url.path if request is not None else "operator"
    if not x_operator_key or not x_operator_key.strip():
        get_metrics_collector().record_tryon_auth_failure(endpoint=endpoint, status_code=401)
        _logger.warning(
            "Operator auth missing header [event=tryon_auth_failure, endpoint=%s, status=401]",
            endpoint,
        )
        raise authentication_error()
    configured = get_settings().operator_api_key
    if not configured:
        get_metrics_collector().record_tryon_auth_failure(endpoint=endpoint, status_code=503)
        _logger.error(
            "Operator auth unconfigured [event=tryon_auth_failure, endpoint=%s, status=503]",
            endpoint,
        )
        raise ApiError(
            status_code=503,
            code="OPERATOR_AUTH_NOT_CONFIGURED",
            message="Operator maintenance authentication is not configured.",
        )
    if not hmac.compare_digest(
        x_operator_key.strip().encode("utf-8"),
        configured.encode("utf-8"),
    ):
        get_metrics_collector().record_tryon_auth_failure(endpoint=endpoint, status_code=403)
        _logger.warning(
            "Operator auth rejected invalid key [event=tryon_auth_failure, endpoint=%s, status=403]",
            endpoint,
        )
        raise ApiError(
            status_code=403,
            code="FORBIDDEN",
            message="Operator authorization required.",
        )


def get_tryon_repository(request: Request):
    """Try-on job repository dependency seam (Phase 5C / 5E.1).

    Resolves to TryOnJobRepositorySQL when database is available, or
    falls back cleanly to in-memory repository when database is absent/disabled.
    Guarantees SQLAlchemy session closure via yield + finally.
    """
    override = request.app.dependency_overrides.get(get_tryon_repository)
    if override:
        res = override()
        if hasattr(res, "__next__"):
            try:
                yield next(res)
            finally:
                try:
                    res.close()
                except Exception:
                    pass
        else:
            yield res
        return

    db_override = request.app.dependency_overrides.get(get_db)
    if db_override:
        gen = None
        try:
            res = db_override()
            if hasattr(res, "__next__"):
                gen = res
                db = next(res)
            else:
                db = res
            from app.infrastructure.db.repositories import TryOnJobRepositorySQL

            repo = TryOnJobRepositorySQL(db)
        except (AssertionError, Exception):
            if gen is not None:
                try:
                    gen.close()
                except Exception:
                    pass
            from app.application.tryon import _IN_MEMORY_REPO

            yield _IN_MEMORY_REPO
            return
        try:
            yield repo
        finally:
            if gen is not None:
                try:
                    gen.close()
                except Exception:
                    pass
        return

    db = None
    try:
        from app.infrastructure.db.repositories import TryOnJobRepositorySQL
        from app.infrastructure.db.session import SessionLocal

        db = SessionLocal()
    except Exception:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        from app.application.tryon import _IN_MEMORY_REPO

        yield _IN_MEMORY_REPO
        return

    try:
        yield TryOnJobRepositorySQL(db)
    finally:
        db.close()


def get_tryon_wardrobe_repository(request: Request):
    """Wardrobe repository resolver for try-on (handles _no_db test mode cleanly).

    Guarantees SQLAlchemy session closure via yield + finally.
    """
    override = request.app.dependency_overrides.get(get_wardrobe_repository)
    if override:
        res = override()
        if hasattr(res, "__next__"):
            try:
                yield next(res)
            finally:
                try:
                    res.close()
                except Exception:
                    pass
        else:
            yield res
        return

    db_override = request.app.dependency_overrides.get(get_db)
    if db_override:
        gen = None
        try:
            res = db_override()
            if hasattr(res, "__next__"):
                gen = res
                db = next(res)
            else:
                db = res
            from app.infrastructure.db.repositories import WardrobeItemRepositorySQL

            repo = WardrobeItemRepositorySQL(db)
        except (AssertionError, Exception):
            if gen is not None:
                try:
                    gen.close()
                except Exception:
                    pass
            yield None
            return
        try:
            yield repo
        finally:
            if gen is not None:
                try:
                    gen.close()
                except Exception:
                    pass
        return

    db = None
    try:
        from app.infrastructure.db.repositories import WardrobeItemRepositorySQL
        from app.infrastructure.db.session import SessionLocal

        db = SessionLocal()
    except Exception:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        yield None
        return

    try:
        yield WardrobeItemRepositorySQL(db)
    finally:
        db.close()




def get_storage_adapter():
    """Dependency provider for object storage port (Stage 2 P0-4 / M16).

    Instantiates the configured storage adapter based on Settings.
    Tests override this via app.dependency_overrides[get_storage_adapter].
    """
    from app.config.settings import get_settings
    from app.infrastructure.external.storage import get_default_storage_adapter

    return get_default_storage_adapter(get_settings())


def get_weather_provider() -> Optional[WeatherProvider]:
    """Dependency provider for weather provider port (Stage 2 P1-3).

    Instantiates the configured weather provider based on Settings.
    Returns None if weather is disabled ('off').
    Tests override this via app.dependency_overrides[get_weather_provider].
    """
    from app.config.settings import get_settings
    from app.infrastructure.external.weather import get_default_weather_provider

    return get_default_weather_provider(get_settings())
