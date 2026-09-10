"""Production appearance analysis adapter — Ollama-hosted vision model.

Server-side analyzer behind ``AppearanceAnalysisPort``. Sends the ACTUAL
received image bytes to a vision-capable model served by Ollama (same
self-hosted pattern as ``app.ai.llm_backend``) and maps the model's
observation to the canonical Fansivibe appearance contract.

This adapter is the opposite of ``DevelopmentAppearanceAnalysisAdapter``:
every attribute it returns was observed from the supplied pixels. Nothing
is derived from filenames, UUIDs, media keys, timestamps, or hashes.

Honesty rules enforced here:
- No usable face → ``AppearanceAnalysisError`` (``no_face_detected`` /
  ``ambiguous_subject``); never a default shape. "oval" is a measurement,
  never a fallback.
- Confidence below ``LOW_CONFIDENCE_FLOOR`` → ``low_confidence`` failure
  (contract outcome B). Above the floor, the profile is returned and the
  decision engine derives ``needs_more_data`` from profile completeness
  (a faceShape-only measurement is sparse by construction → outcome A).
- ``skinTone`` / ``bodyType`` / ``styleType`` stay empty: the prompt asks
  the model for face shape only, so no unsupported appearance claims are
  made.
- Image bytes are processed ephemerally: base64-encoded for the provider
  call, never logged, never persisted, never echoed in errors.

Configuration (environment, never hard-coded; ``FANSIVIBE_DISABLE_VISION=1``
forces ``analyzer_unavailable`` without network I/O):
- ``FANSIVIBE_VISION_HOST`` (default ``http://localhost:11434``)
- ``FANSIVIBE_VISION_MODEL`` (default ``llama3.2-vision`` — deployment MUST
  set a vision-capable model)
- ``FANSIVIBE_VISION_TIMEOUT_S`` (default ``20.0``)

Adapter identity: ``ADAPTER_ID = "ollama-vision-v1"`` — recorded in the
run's MediaRef ``analyzer`` field by the use case. Never "development-hash",
"mock", or "fallback".
"""

from __future__ import annotations

import base64
import os
from typing import Callable, Optional
from uuid import UUID

import httpx

from app.domain.ports.appearance_analysis import AppearanceAnalysisPort
from app.domain.value_objects import AppearanceProfile

ADAPTER_ID = "ollama-vision-v1"

_CANONICAL_FACE_SHAPES = frozenset(
    {"oval", "round", "square", "heart", "diamond", "rectangular"}
)

# Explicit, documented alias: the decision engine's hairstyle boost tables
# historically spell this value "rectangle"; the canonical port vocabulary
# is "rectangular". No other provider label is guessed.
_FACE_SHAPE_ALIASES = {"rectangle": "rectangular"}

# Special model verdicts (not face shapes).
_NO_FACE_TOKEN = "no_face"
_AMBIGUOUS_TOKEN = "ambiguous"

# Below this analyzer confidence the measurement is refused (outcome B).
LOW_CONFIDENCE_FLOOR = 0.35


class AppearanceAnalysisError(Exception):
    """Typed analyzer failure carrying a contract failure reason.

    ``reason`` is one of: ``no_face_detected``, ``ambiguous_subject``,
    ``analyzer_unavailable``, ``analyzer_timeout``, ``low_confidence``,
    ``invalid_analyzer_response``. The application layer maps it to a
    ``PROCESSING_FAILURE`` run error with ``details.reason``.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"appearance analysis failed: {reason}")
        self.reason = reason


def _prompt() -> str:
    return (
        "Look at the face in this photo. Reply with STRICT JSON only, no other text:\n"
        '{"face_shape": "<label>", "confidence": <number 0-1>}\n'
        "Rules:\n"
        '- <label> is exactly one of: oval, round, square, heart, diamond, rectangular.\n'
        "- confidence is how certain you are about the face shape, 0 to 1.\n"
        '- If no human face is clearly visible, reply {"face_shape": "no_face", "confidence": 0}.\n'
        "- If multiple faces are visible and you cannot safely pick the subject, "
        'reply {"face_shape": "ambiguous", "confidence": 0}.'
    )


def _normalize_face_shape(raw: object) -> str:
    """Map a provider label to the canonical vocabulary or raise."""
    if not isinstance(raw, str):
        raise AppearanceAnalysisError("invalid_analyzer_response")
    label = raw.strip().lower()
    if label == _NO_FACE_TOKEN:
        raise AppearanceAnalysisError("no_face_detected")
    if label == _AMBIGUOUS_TOKEN:
        raise AppearanceAnalysisError("ambiguous_subject")
    label = _FACE_SHAPE_ALIASES.get(label, label)
    if label not in _CANONICAL_FACE_SHAPES:
        raise AppearanceAnalysisError("invalid_analyzer_response")
    return label


def _parse_confidence(raw: object) -> float:
    """Validate provider confidence is a real number in [0, 1]."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise AppearanceAnalysisError("invalid_analyzer_response")
    value = float(raw)
    if not 0.0 <= value <= 1.0:
        raise AppearanceAnalysisError("invalid_analyzer_response")
    return value


def _default_chat(
    *, host: str, model: str, timeout_s: float, image_b64: str, prompt: str
) -> dict:
    """POST the image to Ollama chat and return the decoded JSON body."""
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_b64],
                        }
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise AppearanceAnalysisError("analyzer_timeout") from exc
    except httpx.ConnectError as exc:
        raise AppearanceAnalysisError("analyzer_unavailable") from exc
    except httpx.HTTPError as exc:
        raise AppearanceAnalysisError("analyzer_unavailable") from exc
    if not isinstance(payload, dict):
        raise AppearanceAnalysisError("invalid_analyzer_response")
    message = payload.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise AppearanceAnalysisError("invalid_analyzer_response")
    import json as _json

    try:
        decoded = _json.loads(content)
    except ValueError as exc:
        raise AppearanceAnalysisError("invalid_analyzer_response") from exc
    if not isinstance(decoded, dict):
        raise AppearanceAnalysisError("invalid_analyzer_response")
    return decoded


class OllamaVisionAppearanceAdapter(AppearanceAnalysisPort):
    """Production adapter: measures face shape from actual image pixels."""

    adapter_id = ADAPTER_ID

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
        chat_fn: Optional[Callable[..., dict]] = None,
    ) -> None:
        from app.config.settings import get_settings

        settings = get_settings()
        self._host = host or settings.vision_host
        self._model = model or settings.vision_model
        self._timeout_s = timeout_s or settings.vision_timeout_s
        # Injectable transport boundary: tests supply a fake, production
        # uses Ollama over httpx. Signature:
        #   chat_fn(*, host, model, timeout_s, image_b64, prompt) -> dict
        self._chat_fn = chat_fn or _default_chat

    def analyze(
        self,
        *,
        media_ref: dict,
        user_id: UUID,
        image_bytes: bytes | None = None,
    ) -> AppearanceProfile:
        """Measure appearance from the supplied image bytes."""
        if image_bytes is None:
            # Programming error: without bytes there is nothing to measure,
            # and this adapter refuses to derive from the media key.
            raise ValueError("OllamaVisionAppearanceAdapter requires image_bytes")
        if os.environ.get("FANSIVIBE_DISABLE_VISION") == "1":
            raise AppearanceAnalysisError("analyzer_unavailable")
        image_b64 = base64.b64encode(bytes(image_bytes)).decode("ascii")
        try:
            decoded = self._chat_fn(
                host=self._host,
                model=self._model,
                timeout_s=self._timeout_s,
                image_b64=image_b64,
                prompt=_prompt(),
            )
        except AppearanceAnalysisError:
            raise
        except httpx.TimeoutException as exc:
            raise AppearanceAnalysisError("analyzer_timeout") from exc
        except httpx.HTTPError as exc:
            raise AppearanceAnalysisError("analyzer_unavailable") from exc
        except Exception as exc:
            raise AppearanceAnalysisError("analyzer_unavailable") from exc
        if not isinstance(decoded, dict):
            raise AppearanceAnalysisError("invalid_analyzer_response")
        face_shape = _normalize_face_shape(decoded.get("face_shape"))
        confidence = _parse_confidence(decoded.get("confidence"))
        if confidence < LOW_CONFIDENCE_FLOOR:
            raise AppearanceAnalysisError("low_confidence")
        return AppearanceProfile(
            faceShape=face_shape,
            skinTone="",
            bodyType="",
            styleType="",
            sourceRunId="",
        )

    def validate_result(self, result: dict) -> bool:
        """Contract validation for adapter result dicts."""
        required = {
            "faceShape",
            "skinTone",
            "bodyType",
            "styleType",
            "sourceRunId",
            "confidence",
            "needs_more_data",
        }
        if not isinstance(result, dict) or not all(k in result for k in required):
            return False
        if result["faceShape"] not in _CANONICAL_FACE_SHAPES:
            return False
        try:
            conf = result["confidence"]
            if isinstance(conf, bool) or not isinstance(conf, (int, float)):
                return False
            if not 0.0 <= float(conf) <= 1.0:
                return False
        except (TypeError, ValueError):
            return False
        if not isinstance(result["needs_more_data"], bool):
            return False
        if not isinstance(result["sourceRunId"], str):
            return False
        return True


__all__ = [
    "ADAPTER_ID",
    "LOW_CONFIDENCE_FLOOR",
    "AppearanceAnalysisError",
    "OllamaVisionAppearanceAdapter",
]
