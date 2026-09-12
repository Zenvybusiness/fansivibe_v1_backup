"""API tests for the assistant card-feedback surface (#17, UC-23, STEP B-A).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; schema migrates to `head`, which includes the
0015 `suggestion_opened` / `assistant_navigation` seed rows).

Covers: opened → `suggestion_opened`; navigated →
`assistant_navigation`; arbitrary interactionType → 422; missing
interactionType → 422; success is exactly 204 with an empty body;
rows are owner-scoped to the authenticated user; no card existence
lookup (unknown card ids persist fine); retries append; no-auth → 401;
use-case mapping unit-tested independently with a fake repository.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.application.assistant import SubmitAssistantCardFeedback
from app.infrastructure.db.models import LearningSignals, Users
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}
PATH = "/v1/assistant/feedback"


def _make_user():
    Session = make_session()
    with Session() as session:
        user = session.execute(
            select(Users).where(Users.auth_provider == "dev", Users.auth_subject == "dev-user")
        ).scalar_one_or_none()
        if user is None:
            user = Users(auth_provider="dev", auth_subject="dev-user", display_name="Dev User")
            session.add(user)
            session.commit()
        return user.id


def _signal_count():
    Session = make_session()
    with Session() as session:
        return session.execute(
            select(func.count()).select_from(LearningSignals)
        ).scalar_one()


def _latest_signal():
    Session = make_session()
    with Session() as session:
        return session.execute(
            select(LearningSignals).order_by(LearningSignals.occurred_at.desc())
        ).scalars().first()


def test_opened_maps_to_suggestion_opened():
    """A. opened → suggestion_opened with the card title as label."""
    user_id = _make_user()
    resp = client.post(
        PATH,
        json={"cardTitle": "Textured Quiff", "interactionType": "opened"},
        headers=HEADERS,
    )
    assert resp.status_code == 204
    assert resp.content == b""
    assert _signal_count() == 1
    row = _latest_signal()
    assert row.user_id == user_id
    assert row.signal_type == "suggestion_opened"
    assert row.label == "Textured Quiff"


def test_navigated_maps_to_assistant_navigation():
    """B. navigated → assistant_navigation with the card id as label."""
    user_id = _make_user()
    resp = client.post(
        PATH,
        json={"cardId": "look_suggestion_04", "interactionType": "navigated"},
        headers=HEADERS,
    )
    assert resp.status_code == 204
    assert resp.content == b""
    assert _signal_count() == 1
    row = _latest_signal()
    assert row.user_id == user_id
    assert row.signal_type == "assistant_navigation"
    assert row.label == "look_suggestion_04"


def test_arbitrary_interaction_type_returns_422():
    """C. The client cannot name signal types — anything outside the frozen
    pair is rejected and nothing is stored."""
    user_id = _make_user()
    _ = user_id
    resp = client.post(
        PATH,
        json={"cardTitle": "Textured Quiff", "interactionType": "look_saved"},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _signal_count() == 0


def test_missing_interaction_type_returns_422():
    """D. interactionType is required; nothing is stored."""
    _make_user()
    resp = client.post(
        PATH,
        json={"cardTitle": "Textured Quiff"},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _signal_count() == 0


def test_success_returns_exactly_204_with_empty_body():
    """E. 204 + empty body on the contract shape."""
    _make_user()
    resp = client.post(
        PATH,
        json={
            "cardId": "look_suggestion_04",
            "cardTitle": "Textured Quiff",
            "interactionType": "opened",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 204
    assert resp.content == b""


def test_authenticated_request_uses_current_user():
    """F. The stored row belongs to the authenticated (dev-seam) user."""
    user_id = _make_user()
    resp = client.post(
        PATH,
        json={"interactionType": "opened"},
        headers=HEADERS,
    )
    assert resp.status_code == 204
    row = _latest_signal()
    assert row is not None
    assert row.user_id == user_id
    assert row.label == "opened"


def test_no_card_existence_lookup_is_required():
    """G. Cards are ephemeral: unknown ids/titles persist without lookup."""
    _make_user()
    resp = client.post(
        PATH,
        json={"cardId": "no-such-card", "cardTitle": "No Such Card", "interactionType": "navigated"},
        headers=HEADERS,
    )
    assert resp.status_code == 204
    assert _signal_count() == 1
    row = _latest_signal()
    assert row.signal_type == "assistant_navigation"
    assert row.label == "No Such Card"


def test_retry_appends_another_signal():
    """H. Deliberately NOT idempotency-keyed: the same request twice
    yields two append-only rows."""
    _make_user()
    body = {"cardTitle": "Textured Quiff", "interactionType": "opened"}
    first = client.post(PATH, json=body, headers=HEADERS)
    second = client.post(PATH, json=body, headers=HEADERS)
    assert first.status_code == 204
    assert second.status_code == 204
    assert _signal_count() == 2


def test_unauthorized_request_returns_401():
    """I. Auth uses the existing dev-seam behavior; nothing is stored."""
    resp = client.post(PATH, json={"interactionType": "opened"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"
    assert _signal_count() == 0


class _FakeSignals:
    """In-memory LearningSignalRepository stand-in (no DB)."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.commits = 0
        self.rollbacks = 0

    def insert_look_saved(self, *, user_id, signal_type="look_saved", label, context) -> None:
        self.rows.append(
            {"user_id": user_id, "signal_type": signal_type, "label": label, "context": context}
        )

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_use_case_mapping_independently():
    """J. UC-23 owns the mapping: pair → canonical types, label fallback
    (title → id → interaction), unknown → 422, single commit, no rollback."""
    from app.api.errors import ApiError

    signals = _FakeSignals()
    use_case = SubmitAssistantCardFeedback(signals=signals)
    user_id = uuid4()

    stored = use_case(
        user_id=user_id, card_id=None, card_title="Textured Quiff", interaction_type="opened"
    )
    assert stored == "suggestion_opened"
    stored = use_case(
        user_id=user_id, card_id="look_suggestion_04", card_title=None, interaction_type="navigated"
    )
    assert stored == "assistant_navigation"
    assert [row["signal_type"] for row in signals.rows] == [
        "suggestion_opened",
        "assistant_navigation",
    ]
    assert [row["label"] for row in signals.rows] == ["Textured Quiff", "look_suggestion_04"]
    assert signals.commits == 2
    assert signals.rollbacks == 0

    with pytest.raises(ApiError) as exc_info:
        use_case(user_id=user_id, card_id=None, card_title=None, interaction_type="dismissed")
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "VALIDATION_ERROR"
    assert len(signals.rows) == 2
