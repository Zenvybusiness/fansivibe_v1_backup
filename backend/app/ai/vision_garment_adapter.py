"""Production garment analysis adapter — Ollama-hosted vision model (M11).

Server-side analyzer behind ``GarmentAnalysisPort``. Sends the ACTUAL
received garment image bytes to the same self-hosted vision model as
``vision_appearance_adapter`` and maps the model's observation to the
canonical garment contract. Transport (``_default_chat``), confidence
parsing, and the failure taxonomy are reused from the appearance adapter —
only the prompt and normalization are garment-specific.

Honesty rules enforced here:
- No usable garment → ``GarmentAnalysisError`` (``no_garment_detected`` /
  ``ambiguous_subject``); never a default category. ``null`` is a
  measurement ("not clearly visible"), never a fallback for a guess.
- Confidence below ``LOW_CONFIDENCE_FLOOR`` → ``low_confidence`` failure.
- ``category`` outside the canonical wardrobe codes is coerced to None
  (the model describing instead of classifying is not a run failure);
  wrong JSON types are ``invalid_analyzer_response``.
- Image bytes are processed ephemerally: base64-encoded for the provider
  call, never logged, never persisted, never echoed in errors.

Configuration reuses the vision settings (never hard-coded):
- ``FANSIVIBE_VISION_HOST`` (default ``http://localhost:11434``)
- ``FANSIVIBE_VISION_MODEL`` (default ``llama3.2-vision`` — deployment MUST
  set a vision-capable model; qwen2.5vl:3b in this deployment)
- ``FANSIVIBE_VISION_TIMEOUT_S`` (default ``20.0``)
- ``FANSIVIBE_DISABLE_VISION=1`` forces ``analyzer_unavailable``.

Adapter identity: ``ADAPTER_ID = "ollama-garment-v1"`` — recorded in the
run's MediaRef ``analyzer`` field by the use case.
"""

from __future__ import annotations

import os
from typing import Callable, Optional
from uuid import UUID

import httpx

from app.ai.vision_appearance_adapter import (
    LOW_CONFIDENCE_FLOOR,
    _default_chat,
    _parse_confidence,
)
from app.domain.ports.garment_analysis import GarmentAnalysisPort
from app.domain.value_objects import GarmentProfile

ADAPTER_ID = "ollama-garment-v1"

# Canonical wardrobe category codes (wardrobe_categories seed). The prompt
# constrains the model to these; anything else observed is coerced to None.
_CANONICAL_CATEGORIES = frozenset(
    {"tops", "bottoms", "outerwear", "footwear", "accessories"}
)

# Special model verdicts (not categories).
_NO_GARMENT_TOKEN = "no_garment"
_AMBIGUOUS_TOKEN = "ambiguous"


class GarmentAnalysisError(Exception):
    """Typed analyzer failure carrying a contract failure reason.

    ``reason`` is one of: ``no_garment_detected``, ``ambiguous_subject``,
    ``analyzer_unavailable``, ``analyzer_timeout``, ``low_confidence``,
    ``invalid_analyzer_response``. The application layer maps it to a
    ``PROCESSING_FAILURE`` run error with ``details.reason``.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"garment analysis failed: {reason}")
        self.reason = reason


def _prompt() -> str:
    return (
        "Look at the clothing item in this photo. Reply with STRICT JSON only, no other text:\n"
        '{"category": "<code or null>", "subcategory": "<string or null>", '
        '"color": "<string or null>", "pattern": "<string or null>", '
        '"material": "<string or null>", "style": "<string or null>", '
        '"fit": "<string or null>", "confidence": <number 0-1>}\n'
        "Rules:\n"
        "- <code> is exactly one of: tops, bottoms, outerwear, footwear, accessories.\n"
        "- Reply null (JSON null, not the string) for any attribute you cannot clearly see.\n"
        "- confidence is how certain you are about the category, 0 to 1.\n"
        '- If no clothing item is clearly visible, reply {"category": "no_garment", '
        '"confidence": 0} (other keys may be null).\n'
        "- A face-first portrait is NOT a garment photo: unless an item of "
        "clothing is clearly shown as the photo's subject (not just a collar "
        'or shoulders behind a face), reply {"category": "no_garment", '
        '"confidence": 0}.\n'
        "- If several garments overlap and you cannot safely pick the subject, "
        'reply {"category": "ambiguous", "confidence": 0}.'
    )


def _normalize_category(raw: object) -> str | None:
    """Map a provider category to the canonical codes, None, or raise."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise GarmentAnalysisError("invalid_analyzer_response")
    label = raw.strip().lower()
    if not label or label == "null":
        return None
    if label == _NO_GARMENT_TOKEN:
        raise GarmentAnalysisError("no_garment_detected")
    if label == _AMBIGUOUS_TOKEN:
        raise GarmentAnalysisError("ambiguous_subject")
    # ponytail: describing instead of classifying (e.g. "shirt") is not a
    # run failure — it coerces to None and the user confirms the category.
    if label not in _CANONICAL_CATEGORIES:
        return None
    return label


def _normalize_text(raw: object) -> str | None:
    """Observed free-form attribute or None; wrong types fail the run."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise GarmentAnalysisError("invalid_analyzer_response")
    text = raw.strip()
    if not text or text.lower() == "null":
        return None
    return text


class OllamaVisionGarmentAdapter(GarmentAnalysisPort):
    """Production adapter: measures garment attributes from actual pixels."""

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
        self._disabled = bool(getattr(settings, "disable_vision", False))
        # Injectable transport boundary: tests supply a fake, production
        # uses Ollama over httpx (shared with the appearance adapter).
        self._chat_fn = chat_fn or _default_chat

    def analyze(
        self,
        *,
        media_ref: dict,
        user_id: UUID,
        image_bytes: bytes | None = None,
    ) -> GarmentProfile:
        """Measure garment attributes from the supplied image bytes."""
        import base64

        if image_bytes is None:
            raise ValueError("OllamaVisionGarmentAdapter requires image_bytes")
        if self._disabled or os.environ.get("FANSIVIBE_DISABLE_VISION") == "1":
            raise GarmentAnalysisError("analyzer_unavailable")
        image_b64 = base64.b64encode(bytes(image_bytes)).decode("ascii")
        try:
            decoded = self._chat_fn(
                host=self._host,
                model=self._model,
                timeout_s=self._timeout_s,
                image_b64=image_b64,
                prompt=_prompt(),
            )
        except GarmentAnalysisError:
            raise
        except httpx.TimeoutException as exc:
            raise GarmentAnalysisError("analyzer_timeout") from exc
        except httpx.HTTPError as exc:
            raise GarmentAnalysisError("analyzer_unavailable") from exc
        except Exception as exc:
            raise GarmentAnalysisError("analyzer_unavailable") from exc
        if not isinstance(decoded, dict):
            raise GarmentAnalysisError("invalid_analyzer_response")
        # Category verdict first (face-adapter precedent): no_garment /
        # ambiguous carry confidence 0 by contract and must surface their
        # specific reason, never low_confidence.
        category = _normalize_category(decoded.get("category"))
        try:
            confidence = _parse_confidence(decoded.get("confidence"))
        except Exception as exc:
            # _parse_confidence raises AppearanceAnalysisError; re-map to
            # the garment taxonomy so callers see one reason vocabulary.
            raise GarmentAnalysisError("invalid_analyzer_response") from exc
        if confidence < LOW_CONFIDENCE_FLOOR:
            raise GarmentAnalysisError("low_confidence")
        subcategory = _normalize_text(decoded.get("subcategory"))
        color = _normalize_text(decoded.get("color"))
        pattern = _normalize_text(decoded.get("pattern"))
        material = _normalize_text(decoded.get("material"))
        style = _normalize_text(decoded.get("style"))
        fit = _normalize_text(decoded.get("fit"))
        # ponytail: deterministic review flag — missing core facts or a
        # weak measurement always routes through user confirmation.
        needs_review = (
            category is None or color is None or material is None or confidence < 0.6
        )
        return GarmentProfile(
            category=category,
            subcategory=subcategory,
            color=color,
            pattern=pattern,
            material=material,
            style=style,
            fit=fit,
            confidence=confidence,
            needs_review=needs_review,
            sourceRunId="",
        )

    def validate_result(self, result: dict) -> bool:
        """Contract validation for garment result dicts."""
        required = {
            "category",
            "subcategory",
            "color",
            "pattern",
            "material",
            "style",
            "fit",
            "confidence",
            "needs_review",
        }
        if not isinstance(result, dict) or not all(k in result for k in required):
            return False
        category = result["category"]
        if category is not None and category not in _CANONICAL_CATEGORIES:
            return False
        for key in ("subcategory", "color", "pattern", "material", "style", "fit"):
            value = result[key]
            if value is not None and not isinstance(value, str):
                return False
        try:
            conf = result["confidence"]
            if isinstance(conf, bool) or not isinstance(conf, (int, float)):
                return False
            if not 0.0 <= float(conf) <= 1.0:
                return False
        except (TypeError, ValueError):
            return False
        if not isinstance(result["needs_review"], bool):
            return False
        return True


__all__ = [
    "ADAPTER_ID",
    "GarmentAnalysisError",
    "OllamaVisionGarmentAdapter",
]
