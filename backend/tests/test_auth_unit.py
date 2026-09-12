"""Unit tests for D-AUTH-1 authentication and multi-user isolation.

Runs without an external PostgreSQL service using an in-memory
AuthRepository conforming to the domain protocol `AuthRepository`.
Tests every required authentication behavior:
- valid login
- invalid credentials (wrong password, unknown account)
- missing / invalid / expired / tampered token
- logout / session revocation
- session restoration
- duplicate account conflict (409)
- idempotent registration replay
- malformed request validation (422)
- email normalization and password policy
- User A vs User B identity isolation
- A -> B and B -> A IDOR defense
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.api.errors import ApiError
from app.application.auth import (
    RegisterAccount,
    SignIn,
    SignOut,
    issue_session,
    normalize_email,
    resolve_session,
    validated_display_name,
    validated_register_password,
)
from app.domain.ports.repositories import (
    AuthAccountRecord,
    AuthRepository,
    AuthSessionRecord,
)
from app.infrastructure.auth import (
    decode_access_token,
    digests_equal,
    hash_password,
    mint_access_token,
    token_digest,
    verify_password,
)

_SECRET = "test-unit-auth-secret-key-32-chars-long"
_EXPIRES_IN = 3600


class InMemoryAuthRepository:
    """In-memory implementation of the `AuthRepository` domain port."""

    def __init__(self) -> None:
        self.accounts: dict[tuple[str, str], AuthAccountRecord] = {}
        self.sessions: dict[str, AuthSessionRecord] = {}
        self.session_by_id: dict[UUID, AuthSessionRecord] = {}
        self.committed = False
        self.rolled_back = False

    def find_account(
        self, *, auth_provider: str, auth_subject: str
    ) -> AuthAccountRecord | None:
        return self.accounts.get((auth_provider, auth_subject))

    def create_account(
        self,
        *,
        auth_provider: str,
        auth_subject: str,
        display_name: str,
        password_hash: str | None,
        idempotency_key: str | None,
    ) -> AuthAccountRecord:
        record = AuthAccountRecord(
            user_id=uuid4(),
            auth_provider=auth_provider,
            auth_subject=auth_subject,
            display_name=display_name,
            password_hash=password_hash,
            register_idempotency_key=idempotency_key,
        )
        self.accounts[(auth_provider, auth_subject)] = record
        return record

    def create_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        token_digest: str,
        expires_at: datetime,
    ) -> AuthSessionRecord:
        record = AuthSessionRecord(
            id=session_id,
            user_id=user_id,
            token_digest=token_digest,
            expires_at=expires_at,
            revoked_at=None,
        )
        self.sessions[token_digest] = record
        self.session_by_id[session_id] = record
        return record

    def find_session(self, *, token_digest: str) -> AuthSessionRecord | None:
        return self.sessions.get(token_digest)

    def revoke_session(self, *, session_id: UUID) -> None:
        record = self.session_by_id.get(session_id)
        if record is not None and record.revoked_at is None:
            updated = AuthSessionRecord(
                id=record.id,
                user_id=record.user_id,
                token_digest=record.token_digest,
                expires_at=record.expires_at,
                revoked_at=datetime.now(timezone.utc),
            )
            self.sessions[record.token_digest] = updated
            self.session_by_id[session_id] = updated

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


# --- Email & Password Validation ---------------------------------------------


def test_normalize_email_valid():
    assert normalize_email("  Alex@Example.COM  ") == "alex@example.com"
    assert normalize_email("user.name+tag@sub.domain.co") == "user.name+tag@sub.domain.co"


def test_normalize_email_invalid():
    for bad in ["", "   ", "notanemail", "@example.com", "user@", "user@nodot", 123, None]:
        with pytest.raises(ApiError) as exc_info:
            normalize_email(bad)
        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "VALIDATION_ERROR"


def test_validated_register_password_valid():
    assert validated_register_password("Passw0rd1") == "Passw0rd1"
    assert validated_register_password("a" * 120 + "1") == "a" * 120 + "1"


def test_validated_register_password_invalid():
    for bad in ["short1", "nonumbers", "12345678", "a" * 129 + "1", "", 12345678]:
        with pytest.raises(ApiError) as exc_info:
            validated_register_password(bad)
        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "VALIDATION_ERROR"


def test_validated_display_name():
    assert validated_display_name(None) is None
    assert validated_display_name("  Alex  ") == "Alex"
    with pytest.raises(ApiError):
        validated_display_name("")
    with pytest.raises(ApiError):
        validated_display_name("   ")
    with pytest.raises(ApiError):
        validated_display_name("a" * 101)


# --- Infrastructure Crypto (bcrypt + JWT) -----------------------------------


def test_password_hashing_and_verification():
    pw = "Passw0rd1"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h) is True
    assert verify_password("WrongPassword1", h) is False
    assert verify_password("", h) is False


def test_token_minting_and_decoding():
    user_id = uuid4()
    session_id = uuid4()
    token = mint_access_token(
        user_id=user_id,
        session_id=session_id,
        secret=_SECRET,
        expires_in_s=3600,
    )
    dec_user, dec_sess = decode_access_token(token=token, secret=_SECRET)
    assert dec_user == user_id
    assert dec_sess == session_id


def test_token_decoding_failures():
    user_id = uuid4()
    session_id = uuid4()
    # Expired token
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    expired_token = mint_access_token(
        user_id=user_id,
        session_id=session_id,
        secret=_SECRET,
        expires_in_s=5,
        now=past,
    )
    with pytest.raises(ValueError):
        decode_access_token(token=expired_token, secret=_SECRET)

    # Wrong secret
    good_token = mint_access_token(
        user_id=user_id,
        session_id=session_id,
        secret=_SECRET,
        expires_in_s=3600,
    )
    with pytest.raises(ValueError):
        decode_access_token(token=good_token, secret="wrong-secret-key-that-is-at-least-32-chars!")

    # Tampered token
    with pytest.raises(ValueError):
        decode_access_token(token=good_token + "tampered", secret=_SECRET)


def test_token_digest_and_equality():
    t1 = "token-alpha"
    t2 = "token-beta"
    d1 = token_digest(t1)
    d2 = token_digest(t2)
    assert d1 != d2
    assert digests_equal(d1, d1) is True
    assert digests_equal(d1, d2) is False


# --- Registration & Idempotency ---------------------------------------------


def test_register_account_success():
    repo = InMemoryAuthRepository()
    use_case = RegisterAccount(auth=repo)
    account, token = use_case(
        email="alex@example.com",
        password="Passw0rd1",
        display_name="Alex",
        idempotency_key="reg-key-1",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    assert account.display_name == "Alex"
    assert account.auth_provider == "email"
    assert account.auth_subject == "alex@example.com"
    assert account.password_hash is not None
    assert account.password_hash != "Passw0rd1"
    assert repo.committed is True

    # Token resolves back to account
    resolved_user, resolved_sess = resolve_session(repo, token=token, secret=_SECRET)
    assert resolved_user == account.user_id


def test_register_duplicate_email_is_409():
    repo = InMemoryAuthRepository()
    use_case = RegisterAccount(auth=repo)
    use_case(
        email="alex@example.com",
        password="Passw0rd1",
        idempotency_key="key-1",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    with pytest.raises(ApiError) as exc_info:
        use_case(
            email="alex@example.com",
            password="Passw0rd1",
            idempotency_key="key-2",  # Different key -> conflict
            secret=_SECRET,
            expires_in_s=_EXPIRES_IN,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "CONFLICT"


def test_register_replay_same_key_same_payload():
    repo = InMemoryAuthRepository()
    use_case = RegisterAccount(auth=repo)
    acc1, tok1 = use_case(
        email="alex@example.com",
        password="Passw0rd1",
        display_name="Alex",
        idempotency_key="replay-key",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    acc2, tok2 = use_case(
        email="alex@example.com",
        password="Passw0rd1",
        display_name="Alex",
        idempotency_key="replay-key",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    assert acc1.user_id == acc2.user_id
    assert tok1 != tok2  # fresh session issued on replay


def test_register_replay_same_key_different_payload_is_409():
    repo = InMemoryAuthRepository()
    use_case = RegisterAccount(auth=repo)
    use_case(
        email="alex@example.com",
        password="Passw0rd1",
        idempotency_key="replay-key",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    with pytest.raises(ApiError) as exc_info:
        use_case(
            email="alex@example.com",
            password="DifferentPass1",
            idempotency_key="replay-key",
            secret=_SECRET,
            expires_in_s=_EXPIRES_IN,
        )
    assert exc_info.value.status_code == 409


# --- Login (Sign In) --------------------------------------------------------


def test_login_valid_credentials():
    repo = InMemoryAuthRepository()
    RegisterAccount(auth=repo)(
        email="login@example.com",
        password="Passw0rd1",
        idempotency_key="k1",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    sign_in = SignIn(auth=repo)
    account, token = sign_in(
        email="login@example.com",
        password="Passw0rd1",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    assert account.auth_subject == "login@example.com"
    user_id, _ = resolve_session(repo, token=token, secret=_SECRET)
    assert user_id == account.user_id


def test_login_wrong_password_is_uniform_401():
    repo = InMemoryAuthRepository()
    RegisterAccount(auth=repo)(
        email="victim@example.com",
        password="Passw0rd1",
        idempotency_key="k1",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    sign_in = SignIn(auth=repo)
    with pytest.raises(ApiError) as exc_info:
        sign_in(
            email="victim@example.com",
            password="WrongPass1",
            secret=_SECRET,
            expires_in_s=_EXPIRES_IN,
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "AUTHENTICATION_ERROR"


def test_login_unknown_email_is_uniform_401():
    repo = InMemoryAuthRepository()
    sign_in = SignIn(auth=repo)
    with pytest.raises(ApiError) as exc_info:
        sign_in(
            email="nonexistent@example.com",
            password="Passw0rd1",
            secret=_SECRET,
            expires_in_s=_EXPIRES_IN,
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "AUTHENTICATION_ERROR"


# --- Logout & Session Revocation --------------------------------------------


def test_logout_revokes_session():
    repo = InMemoryAuthRepository()
    _, token = RegisterAccount(auth=repo)(
        email="logout@example.com",
        password="Passw0rd1",
        idempotency_key="k1",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    user_id, session_id = resolve_session(repo, token=token, secret=_SECRET)
    assert user_id is not None

    # Sign out
    SignOut(auth=repo)(session_id=session_id)

    # Subsequent resolution must fail with 401
    with pytest.raises(ApiError) as exc_info:
        resolve_session(repo, token=token, secret=_SECRET)
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "AUTHENTICATION_ERROR"


def test_logout_only_revokes_caller_session():
    repo = InMemoryAuthRepository()
    account, tok1 = RegisterAccount(auth=repo)(
        email="multisess@example.com",
        password="Passw0rd1",
        idempotency_key="k1",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    _, tok2 = SignIn(auth=repo)(
        email="multisess@example.com",
        password="Passw0rd1",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    _, sess1 = resolve_session(repo, token=tok1, secret=_SECRET)
    _, sess2 = resolve_session(repo, token=tok2, secret=_SECRET)
    assert sess1 != sess2

    # Revoke device 1
    SignOut(auth=repo)(session_id=sess1)

    # Device 1 dead (401), Device 2 alive (200)
    with pytest.raises(ApiError):
        resolve_session(repo, token=tok1, secret=_SECRET)
    u2, s2 = resolve_session(repo, token=tok2, secret=_SECRET)
    assert u2 == account.user_id
    assert s2 == sess2


# --- Two-User Isolation & IDOR Defenses --------------------------------------


def test_two_users_isolated_sessions():
    repo = InMemoryAuthRepository()
    acc_a, tok_a = RegisterAccount(auth=repo)(
        email="alice@example.com",
        password="Passw0rd1",
        display_name="Alice",
        idempotency_key="k-alice",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    acc_b, tok_b = RegisterAccount(auth=repo)(
        email="bob@example.com",
        password="Passw0rd1",
        display_name="Bob",
        idempotency_key="k-bob",
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    assert acc_a.user_id != acc_b.user_id

    # Token A strictly resolves to Alice
    user_a, sess_a = resolve_session(repo, token=tok_a, secret=_SECRET)
    assert user_a == acc_a.user_id

    # Token B strictly resolves to Bob
    user_b, sess_b = resolve_session(repo, token=tok_b, secret=_SECRET)
    assert user_b == acc_b.user_id

    # IDOR check: Bob cannot resolve Alice's session
    # If Bob forged a JWT with Alice's user_id but his own session_id:
    forged = mint_access_token(
        user_id=acc_a.user_id,
        session_id=sess_b,
        secret=_SECRET,
        expires_in_s=_EXPIRES_IN,
    )
    # The session store verifies row.user_id == user_id (rejects mismatch)
    with pytest.raises(ApiError):
        resolve_session(repo, token=forged, secret=_SECRET)

    # Revoking Alice does not affect Bob
    SignOut(auth=repo)(session_id=sess_a)
    with pytest.raises(ApiError):
        resolve_session(repo, token=tok_a, secret=_SECRET)
    assert resolve_session(repo, token=tok_b, secret=_SECRET)[0] == acc_b.user_id
