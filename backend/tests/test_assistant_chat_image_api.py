"""Assistant image-chat tests (DB-free).

Covers `POST /v1/assistant/chat-with-image` (approved backend gap fix):
genuine vision measurement (actual bytes reach the stubbed garment port),
typed `AssistantReply` contract, honest wardrobe matching against the
caller-supplied snapshot only, unauthenticated guest access, validation
before AI work, and honest analyzer failures. Zero database rows (the
`get_db` dependency raises if touched).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.api.routers.assistant as assistant_router
from app.ai.vision_garment_adapter import GarmentAnalysisError
from app.domain.value_objects import GarmentProfile

PATH = "/v1/assistant/chat-with-image"
JPEG = ("outfit.jpg", b"outfit-photo-bytes", "image/jpeg")


class StubGarmentPort:
    """Recording garment port. `mode`: ok | no-garment | crash | null-category."""

    instances: list = []
    mode: str = "ok"

    adapter_id = "ollama-garment-v1"

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list = []
        StubGarmentPort.instances.append(self)

    def analyze(self, *, media_ref, user_id, image_bytes=None):
        self.calls.append(
            {"media_ref": media_ref, "user_id": user_id, "image_bytes": image_bytes}
        )
        if StubGarmentPort.mode == "no-garment":
            raise GarmentAnalysisError("no_garment_detected")
        if StubGarmentPort.mode == "crash":
            raise RuntimeError("boom")
        category = None if StubGarmentPort.mode == "null-category" else "tops"
        return GarmentProfile(
            category=category,
            subcategory="oxford shirt" if category else None,
            color="light blue",
            pattern="solid",
            material="cotton",
            style="casual",
            fit="regular",
            confidence=0.82,
            needs_review=False,
            sourceRunId="",
        )


def _no_db():
    raise AssertionError("chat-with-image must never touch the database")


def _client(monkeypatch) -> TestClient:
    from app.main import app
    from app.infrastructure.db.session import get_db

    StubGarmentPort.instances = []
    StubGarmentPort.mode = "ok"
    monkeypatch.setattr(
        assistant_router, "OllamaVisionGarmentAdapter", StubGarmentPort
    )
    monkeypatch.setitem(app.dependency_overrides, get_db, _no_db)
    return TestClient(app)


def _post(client: TestClient, files=None, data=None):
    return client.post(
        PATH,
        files=files if files is not None else {"image": JPEG},
        data=data or {},
    )


def _user(*items: dict) -> str:
    return json.dumps(
        {
            "wardrobe": [
                {
                    "id": i["id"],
                    "name": i["name"],
                    "category": i["category"],
                    "color": i.get("color", ""),
                    "isFavorite": i.get("isFavorite", False),
                }
                for i in items
            ],
            "preferredOccasions": [],
        }
    )


# --- genuine measurement -----------------------------------------------------

def test_image_bytes_reach_vision_port_without_bearer(monkeypatch):
    resp = _post(_client(monkeypatch))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["intent"] == "outfit_image"
    assert StubGarmentPort.instances, "vision port was never constructed"
    calls = StubGarmentPort.instances[-1].calls
    assert len(calls) == 1
    assert calls[0]["image_bytes"] == b"outfit-photo-bytes"


def test_observation_card_uses_measured_attributes(monkeypatch):
    body = _post(_client(monkeypatch)).json()
    observed = next(c for c in body["cards"] if c["kind"] == "outfit")
    assert "oxford shirt" in observed["title"]
    joined = " ".join(observed["items"])
    assert "light blue" in joined and "cotton" in joined
    # Honesty disclaimer names what vision cannot know — without claiming it.
    assert "can't tell" in body["text"]
    assert "% match" not in body["text"]


def test_question_without_image_context_still_answered(monkeypatch):
    resp = _post(
        _client(monkeypatch),
        data={"message": "Does this suit my style?"},
    )
    assert resp.status_code == 200
    assert "light blue" in resp.json()["text"] or "oxford" in resp.json()["text"]


# --- honest wardrobe matching -------------------------------------------------

def test_match_uses_only_caller_wardrobe(monkeypatch):
    resp = _post(
        _client(monkeypatch),
        data={
            "message": "Which top matches?",
            "user": _user(
                {"id": "a", "name": "Blue Oxford", "category": "tops", "color": "light blue"},
                {"id": "b", "name": "Black Boots", "category": "footwear", "color": "black"},
            ),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    match_cards = [c for c in body["cards"] if c["kind"] == "wardrobe"]
    assert len(match_cards) == 1
    assert match_cards[0]["title"] == "Blue Oxford"
    assert "Black Boots" not in body["text"]


def test_empty_wardrobe_is_honest(monkeypatch):
    body = _post(_client(monkeypatch), data={"user": "{}"}).json()
    assert body["intent"] == "outfit_image"
    assert [c for c in body["cards"] if c["kind"] == "wardrobe"] == []
    assert "empty" in body["text"].lower()


def test_no_match_says_so(monkeypatch):
    resp = _post(
        _client(monkeypatch),
        data={
            "user": _user(
                {"id": "b", "name": "Black Boots", "category": "footwear", "color": "black"},
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [c for c in body["cards"] if c["kind"] == "wardrobe"] == []
    assert "nothing" in body["text"].lower() or "no" in body["text"].lower()


# --- validation before AI work -------------------------------------------------

def test_invalid_image_type_rejected(monkeypatch):
    client = _client(monkeypatch)
    resp = _post(client, files={"image": ("outfit.gif", b"bytes", "image/gif")})
    assert resp.status_code == 422
    assert StubGarmentPort.instances[-1].calls == [] if StubGarmentPort.instances else True


def test_malformed_user_rejected(monkeypatch):
    resp = _post(_client(monkeypatch), data={"user": "not-json"})
    assert resp.status_code == 422


def test_malformed_history_rejected(monkeypatch):
    resp = _post(_client(monkeypatch), data={"history": "[oops"})
    assert resp.status_code == 422


def test_history_round_trips_for_follow_ups(monkeypatch):
    history = json.dumps(
        [
            {"role": "user", "content": "What is this?"},
            {"role": "assistant", "content": "I can see oxford shirt in light blue."},
        ]
    )
    resp = _post(
        _client(monkeypatch),
        data={"message": "What shoes work?", "history": history},
    )
    assert resp.status_code == 200
    assert resp.json()["intent"] == "outfit_image"


# --- honest failures, never fake ------------------------------------------------

def test_no_garment_is_422_never_fake(monkeypatch):
    client = _client(monkeypatch)
    StubGarmentPort.mode = "no-garment"
    resp = _post(client)
    assert resp.status_code == 422
    assert "no_garment_detected" in resp.text


def test_adapter_crash_is_503_never_fake(monkeypatch):
    client = _client(monkeypatch)
    StubGarmentPort.mode = "crash"
    resp = _post(client)
    assert resp.status_code == 503
