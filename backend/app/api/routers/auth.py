"""Auth API router — D-AUTH-1 real authentication (M1, endpoints #02–05).

`POST /v1/auth/register` (O-1/UC-1), `POST /v1/auth/login` (O-3/UC-3),
`POST /v1/auth/logout` (O-4/UC-4), `POST /v1/auth/social` (O-2/UC-2)
per `docs/api/AUTH_API.md` §5. Account deletion (O-6) is documented
but NOT mounted until the erasure pipeline lands (API-12); no refresh
endpoint exists (§3.1 — explicitly excluded, never invented).

- Register/login are public (credentials in, session out); logout is
  auth (the session in the Bearer header is revoked, 204).
- Register requires the contract's `Idempotency-Key` (C-12/API-33):
  same key + same payload replays to the same account, never a
  duplicate; a taken email under a fresh key is a 409.
- Social validates the frozen shape (provider allow-list, non-empty
  provider token) then answers the honest 502: no external identity
  provider is configured in this instantiation, so no session is ever
  minted from an unverified provider token.
- Error bodies are the frozen `{error:{code,message,details}}`
  taxonomy; login failures are a uniform 401 (enumeration control).
- Nothing here logs credentials, emails-as-secrets, or tokens (ER-4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.errors import (
    ApiError,
    authentication_error,
    external_failure,
    validation,
)
from app.api.routers.users import build_profile_view
from app.api.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    SocialSignInRequest,
)
from app.application.auth import RegisterAccount, SignIn, SignOut, resolve_session
from app.application.users import GetProfile
from app.config.settings import get_settings
from app.infrastructure.db.repositories import (
    AuthRepositorySQL,
    UserStateRepositorySQL,
)
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/auth", tags=["auth"])

_SOCIAL_PROVIDERS = ("google", "apple")


def _auth_response(
    db: Session,
    *,
    user_id,
    access_token: str,
) -> AuthResponse:
    settings = get_settings()
    record = GetProfile(user_state=UserStateRepositorySQL(db))(user_id=user_id)
    return AuthResponse(
        accessToken=access_token,
        tokenType="bearer",
        expiresIn=settings.auth_expires_in_s,
        profile=build_profile_view(db, record),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    responses={
        409: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
    },
)
def register_account(
    request: RegisterRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Create an account + first session (UC-1, 201 `AuthResponse`)."""
    if not idempotency_key:
        raise validation(
            [{"field": "Idempotency-Key", "error": "required header"}]
        )
    settings = get_settings()
    use_case = RegisterAccount(auth=AuthRepositorySQL(db))
    account, token = use_case(
        email=request.email,
        password=request.password,
        display_name=request.displayName,
        idempotency_key=idempotency_key,
        secret=settings.auth_secret,
        expires_in_s=settings.auth_expires_in_s,
    )
    return _auth_response(db, user_id=account.user_id, access_token=token)


@router.post(
    "/login",
    response_model=AuthResponse,
    responses={
        401: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
    },
)
def sign_in(
    request: LoginRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Verify credentials and issue one session (UC-3, 200 `AuthResponse`)."""
    settings = get_settings()
    use_case = SignIn(auth=AuthRepositorySQL(db))
    account, token = use_case(
        email=request.email,
        password=request.password,
        secret=settings.auth_secret,
        expires_in_s=settings.auth_expires_in_s,
    )
    return _auth_response(db, user_id=account.user_id, access_token=token)


@router.post(
    "/logout",
    status_code=204,
    responses={401: {"model": dict}},
)
def sign_out(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Revoke the caller's session (UC-4, 204).

    A missing/unresolvable token is a 401 (AUTH_API §5.4 — the client
    treats its local logout as complete regardless, which is the
    idempotency the contract means).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise authentication_error()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise authentication_error()
    settings = get_settings()
    auth = AuthRepositorySQL(db)
    _, session_id = resolve_session(
        auth, token=token, secret=settings.auth_secret
    )
    SignOut(auth=auth)(session_id=session_id)
    return Response(status_code=204)


@router.post(
    "/social",
    responses={
        422: {"model": dict},
        502: {"model": dict},
    },
)
def social_sign_in(
    request: SocialSignInRequest,
    db: Session = Depends(get_db),
):
    """Exchange a provider token (O-2/UC-2) — honestly unavailable.

    The frozen shape is validated (provider allow-list 422 with allowed
    values; non-empty provider token 422); verification itself needs an
    external identity provider that is not configured in this
    instantiation, so the exchange answers 502
    `EXTERNAL_SERVICE_FAILURE` (AUTH_API §5.2) and mints nothing.
    Accepting an unverified provider token would be a production auth
    bypass — never done.
    """
    if request.provider not in _SOCIAL_PROVIDERS:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Some of the provided values are not valid. Please check your input.",
            details={
                "field_errors": [
                    {
                        "field": "provider",
                        "error": "unsupported provider",
                        "allowed": list(_SOCIAL_PROVIDERS),
                    }
                ]
            },
        )
    if not isinstance(request.providerToken, str) or not request.providerToken.strip():
        raise validation([{"field": "providerToken", "error": "required"}])
    raise external_failure()
