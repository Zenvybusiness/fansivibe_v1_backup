"""Focused tests for the production Ollama vision appearance adapter.

All provider I/O is faked through the injectable ``chat_fn`` transport
boundary — no network, no paid/external calls. Proves actual-bytes
analysis, canonical output, confidence semantics, honest failures,
privacy (no bytes in logs/errors), non-use of the development adapter,
port injection, and ``CreateHairstyleImageRun`` integration.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import httpx
import pytest

from app.ai.vision_appearance_adapter import (
    ADAPTER_ID,
    LOW_CONFIDENCE_FLOOR,
    AppearanceAnalysisError,
    OllamaVisionAppearanceAdapter,
)
from app.domain.ports.appearance_analysis import AppearanceAnalysisPort
from app.domain.ports.repositories import AnalysisRunRecord

USER = uuid4()
MARKER = b"vision-marker-bytes-9f3c-unique"


def _chat_ok(face_shape="oval", confidence=0.9):
    def _chat(*, host, model, timeout_s, image_b64, prompt):
        _chat.captured = {
            "host": host,
            "model": model,
            "timeout_s": timeout_s,
            "image_b64": image_b64,
            "prompt": prompt,
        }
        return {"face_shape": face_shape, "confidence": confidence}

    _chat.captured = {}
    return _chat


def _adapter(chat_fn=None, **kwargs):
    return OllamaVisionAppearanceAdapter(
        host="http://vision-test:11434",
        model="test-vision",
        timeout_s=5.0,
        chat_fn=chat_fn or _chat_ok(),
        **kwargs,
    )


def _media_ref() -> dict:
    return {"key": f"users/{USER}/scans/{uuid4()}/input.jpg"}


# ---------------------------------------------------------------------------
# 1. Actual image bytes reach the analyzer
# ---------------------------------------------------------------------------


def test_actual_image_bytes_supplied_to_provider():
    chat = _chat_ok()
    adapter = _adapter(chat_fn=chat)
    profile = adapter.analyze(
        media_ref=_media_ref(), user_id=USER, image_bytes=MARKER
    )
    assert base64.b64decode(chat.captured["image_b64"]) == MARKER
    assert profile.faceShape == "oval"


def test_missing_bytes_refused_without_measuring():
    adapter = _adapter()
    with pytest.raises(ValueError):
        adapter.analyze(media_ref=_media_ref(), user_id=USER)


# ---------------------------------------------------------------------------
# 2/3/5. Canonical output, confidence bounds, label normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label", ["oval", "round", "square", "heart", "diamond", "rectangular"]
)
def test_valid_response_produces_canonical_face_shape(label):
    adapter = _adapter(chat_fn=_chat_ok(face_shape=label, confidence=0.9))
    profile = adapter.analyze(
        media_ref=_media_ref(), user_id=USER, image_bytes=MARKER
    )
    assert profile.faceShape == label


@pytest.mark.parametrize("label", ["Rectangle", "  OVAL  ", "Heart"])
def test_label_normalization_is_deterministic(label):
    adapter = _adapter(chat_fn=_chat_ok(face_shape=label, confidence=0.9))
    profile = adapter.analyze(
        media_ref=_media_ref(), user_id=USER, image_bytes=MARKER
    )
    assert profile.faceShape in (
        "rectangular",
        "oval",
        "heart",
    )


def test_unknown_label_rejected_not_guessed():
    adapter = _adapter(chat_fn=_chat_ok(face_shape="triangle", confidence=0.9))
    with pytest.raises(AppearanceAnalysisError) as excinfo:
        adapter.analyze(media_ref=_media_ref(), user_id=USER, image_bytes=MARKER)
    assert excinfo.value.reason == "invalid_analyzer_response"


@pytest.mark.parametrize("confidence", [1.5, -0.1, "high", True, None])
def test_out_of_range_confidence_rejected(confidence):
    adapter = _adapter(chat_fn=_chat_ok(face_shape="oval", confidence=confidence))
    with pytest.raises(AppearanceAnalysisError) as excinfo:
        adapter.analyze(media_ref=_media_ref(), user_id=USER, image_bytes=MARKER)
    assert excinfo.value.reason == "invalid_analyzer_response"


def test_low_confidence_fails_rather_than_guessing():
    adapter = _adapter(
        chat_fn=_chat_ok(face_shape="oval", confidence=LOW_CONFIDENCE_FLOOR - 0.01)
    )
    with pytest.raises(AppearanceAnalysisError) as excinfo:
        adapter.analyze(media_ref=_media_ref(), user_id=USER, image_bytes=MARKER)
    assert excinfo.value.reason == "low_confidence"


def test_floor_confidence_accepted():
    adapter = _adapter(
        chat_fn=_chat_ok(face_shape="oval", confidence=LOW_CONFIDENCE_FLOOR)
    )
    profile = adapter.analyze(
        media_ref=_media_ref(), user_id=USER, image_bytes=MARKER
    )
    assert profile.faceShape == "oval"


def test_unmeasured_fields_stay_empty():
    adapter = _adapter(chat_fn=_chat_ok(face_shape="oval", confidence=0.9))
    profile = adapter.analyze(
        media_ref=_media_ref(), user_id=USER, image_bytes=MARKER
    )
    assert profile.skinTone == ""
    assert profile.bodyType == ""
    assert profile.styleType == ""


# ---------------------------------------------------------------------------
# 6/7/8/9/10. Failure mapping
# ---------------------------------------------------------------------------


def test_no_face_becomes_no_face_detected():
    adapter = _adapter(chat_fn=_chat_ok(face_shape="no_face", confidence=0))
    with pytest.raises(AppearanceAnalysisError) as excinfo:
        adapter.analyze(media_ref=_media_ref(), user_id=USER, image_bytes=MARKER)
    assert excinfo.value.reason == "no_face_detected"


def test_ambiguous_subject_rejected():
    adapter = _adapter(chat_fn=_chat_ok(face_shape="ambiguous", confidence=0))
    with pytest.raises(AppearanceAnalysisError) as excinfo:
        adapter.analyze(media_ref=_media_ref(), user_id=USER, image_bytes=MARKER)
    assert excinfo.value.reason == "ambiguous_subject"


def test_timeout_maps_correctly():
    def _timeout(*, host, model, timeout_s, image_b64, prompt):
        raise httpx.TimeoutException("timed out")

    adapter = _adapter(chat_fn=_timeout)
    with pytest.raises(AppearanceAnalysisError) as excinfo:
        adapter.analyze(media_ref=_media_ref(), user_id=USER, image_bytes=MARKER)
    assert excinfo.value.reason == "analyzer_timeout"


def test_unavailable_maps_correctly():
    def _down(*, host, model, timeout_s, image_b64, prompt):
        raise httpx.ConnectError("refused")

    adapter = _adapter(chat_fn=_down)
    with pytest.raises(AppearanceAnalysisError) as excinfo:
        adapter.analyze(media_ref=_media_ref(), user_id=USER, image_bytes=MARKER)
    assert excinfo.value.reason == "analyzer_unavailable"


def test_disabled_vision_maps_to_unavailable(monkeypatch):
    monkeypatch.setenv("FANSIVIBE_DISABLE_VISION", "1")
    adapter = _adapter(chat_fn=_chat_ok())
    with pytest.raises(AppearanceAnalysisError) as excinfo:
        adapter.analyze(media_ref=_media_ref(), user_id=USER, image_bytes=MARKER)
    assert excinfo.value.reason == "analyzer_unavailable"


@pytest.mark.parametrize(
    "bad_response",
    [
        "not-a-dict",
        {"confidence": 0.9},
        {"face_shape": "oval"},
        {"face_shape": 42, "confidence": 0.9},
        {"face_shape": "oval", "confidence": "high"},
    ],
)
def test_invalid_provider_response_rejected(bad_response):
    adapter = _adapter(chat_fn=lambda **kwargs: bad_response)
    with pytest.raises(AppearanceAnalysisError) as excinfo:
        adapter.analyze(media_ref=_media_ref(), user_id=USER, image_bytes=MARKER)
    assert excinfo.value.reason == "invalid_analyzer_response"


# ---------------------------------------------------------------------------
# 11. Privacy: no bytes in logs or errors
# ---------------------------------------------------------------------------


def test_no_image_bytes_in_logs_or_errors(caplog):
    adapter = _adapter(chat_fn=_chat_ok(face_shape="triangle", confidence=0.9))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AppearanceAnalysisError) as excinfo:
            adapter.analyze(
                media_ref=_media_ref(), user_id=USER, image_bytes=MARKER
            )
    marker_b64 = base64.b64encode(MARKER).decode("ascii")
    assert MARKER.decode("ascii") not in caplog.text
    assert marker_b64 not in caplog.text
    assert MARKER.decode("ascii") not in str(excinfo.value)
    assert excinfo.value.reason == "invalid_analyzer_response"


# ---------------------------------------------------------------------------
# 12/13. Identity and port injection
# ---------------------------------------------------------------------------


def test_production_identity_distinct_from_development():
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter

    adapter = _adapter()
    assert isinstance(adapter, AppearanceAnalysisPort)
    assert not isinstance(adapter, DevelopmentAppearanceAnalysisAdapter)
    assert adapter.adapter_id == "ollama-vision-v1"
    assert ADAPTER_ID == "ollama-vision-v1"
    for banned in ("development", "hash", "mock", "fallback"):
        assert banned not in adapter.adapter_id


def test_validate_result_contract():
    adapter = _adapter()
    assert adapter.validate_result(
        {
            "faceShape": "oval",
            "skinTone": "",
            "bodyType": "",
            "styleType": "",
            "sourceRunId": "run-1",
            "confidence": 0.8,
            "needs_more_data": True,
        }
    ) is True
    assert adapter.validate_result({"faceShape": "triangle"}) is False


# ---------------------------------------------------------------------------
# 4/14. CreateHairstyleImageRun integration with the production adapter
# ---------------------------------------------------------------------------


@dataclass
class FakeRuns:
    rows: dict[UUID, dict] = field(default_factory=dict)
    next_id: UUID = field(default_factory=uuid4)

    def create(self, *, user_id, run_type, engine_version="rules-v1", input_media=None) -> UUID:
        run_id = self.next_id
        self.next_id = uuid4()
        self.rows[run_id] = {
            "id": run_id,
            "user_id": user_id,
            "run_type": run_type,
            "status": "pending",
            "engine_version": engine_version,
            "created_at": datetime.now(timezone.utc),
            "completed_at": None,
            "input_media": input_media,
            "result": None,
            "error": None,
        }
        return run_id

    def get_for_user(self, *, user_id, run_id) -> Optional[AnalysisRunRecord]:
        row = self.rows.get(run_id)
        if row is None or row["user_id"] != user_id:
            return None
        return AnalysisRunRecord(**{k: v for k, v in row.items() if k != "user_id"})

    def complete(self, *, run_id, user_id, status, result) -> bool:
        row = self.rows.get(run_id)
        if row is None or row["user_id"] != user_id or row["status"] != "pending":
            return False
        row["status"] = status
        row["result"] = result
        row["completed_at"] = datetime.now(timezone.utc)
        return True

    def fail(self, *, run_id, user_id, error) -> bool:
        row = self.rows.get(run_id)
        if row is None or row["user_id"] != user_id or row["status"] != "pending":
            return False
        row["status"] = "failed"
        row["error"] = error
        row["completed_at"] = datetime.now(timezone.utc)
        return True


class FakeUserState:
    def __init__(self) -> None:
        self._profile = None

    def get_style_profile(self, *, user_id: UUID):
        return self._profile

    def update_style_profile(
        self, *, user_id, face_shape, skin_tone, body_type, style_type, source_run_id
    ) -> None:
        self._profile = {
            "face_shape": face_shape,
            "skin_tone": skin_tone,
            "body_type": body_type,
            "style_type": style_type,
            "source_run_id": source_run_id,
        }


class FakeLearningSignal:
    def __init__(self) -> None:
        self.calls: list = []

    def insert_look_saved(self, *, user_id, label, context):
        self.calls.append({"user_id": user_id, "label": label, "context": context})


def _knowledge():
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    return CatalogKnowledgeSource()


def _image(payload: bytes):
    class MockImage:
        pass

    img = MockImage()
    img.content_type = "image/jpeg"
    img.size = len(payload)
    img.file = io.BytesIO(payload)
    return img


def test_production_adapter_end_to_end_through_use_case():
    """No domain-contract change: the use case consumes the production
    adapter via AppearanceAnalysisPort (bytes passthrough + reason mapping)."""
    from app.application.analysis import CreateHairstyleImageRun

    chat = _chat_ok(face_shape="oval", confidence=0.9)
    runs = FakeRuns()
    user_state = FakeUserState()
    learning_signal = FakeLearningSignal()
    use_case = CreateHairstyleImageRun(
        runs=runs,
        knowledge=_knowledge(),
        appearance_port=_adapter(chat_fn=chat),
        user_state=user_state,
        learning_signal=learning_signal,
    )
    run_id = use_case(user_id=USER, image=_image(MARKER))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.run_type == "hairstyle"
    assert record.status == "completed"
    assert record.result["appearance"]["faceShape"] == "oval"
    assert record.result["appearance"]["sourceRunId"] == str(run_id)
    # Sparse measured profile → engine honesty flag preserved.
    assert record.result["needs_more_data"] is True
    # Provenance distinguishes the production adapter.
    assert record.input_media["analyzer"] == "ollama-vision-v1"
    assert record.input_media["contentHash"] != "development-hash"
    profile = user_state.get_style_profile(user_id=USER)
    assert profile is not None and profile["face_shape"] == "oval"
    assert any(c["label"] == "analysis_updated" for c in learning_signal.calls)


def test_adapter_no_face_fails_run_with_reason():
    from app.application.analysis import CreateHairstyleImageRun

    runs = FakeRuns()
    use_case = CreateHairstyleImageRun(
        runs=runs,
        knowledge=_knowledge(),
        appearance_port=_adapter(chat_fn=_chat_ok(face_shape="no_face", confidence=0)),
        user_state=FakeUserState(),
        learning_signal=None,
    )
    run_id = use_case(user_id=USER, image=_image(MARKER))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "failed"
    assert record.result is None
    assert record.error["code"] == "PROCESSING_FAILURE"
    assert record.error["details"]["reason"] == "no_face_detected"
    assert MARKER.decode("ascii") not in str(record.error)
