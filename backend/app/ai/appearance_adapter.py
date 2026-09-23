"""Development appearance analysis adapter — DETERMINISTIC, NOT PRODUCTION AI.

This adapter implements the `AppearanceAnalysisPort` using deterministic,
hash-based generation. It is explicitly a development/test infrastructure
component and does NOT represent production AI model inference.

Production model adapters must implement `AppearanceAnalysisPort` without
depending on OpenAI SDK, Gemini SDK, Claude SDK, TensorFlow, PyTorch, or
OpenCV. Such adapters would replace this development implementation when a
real approved model/partner becomes available.

The hash-based generation below is intentionally simple and transparent:
given the same media_ref key, it always produces the same appearance profile.
It is NOT intended to provide accurate appearance analysis — it is for
development, testing, and prototype validation only.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Optional

from uuid import UUID, uuid4

from app.domain.ports.appearance_analysis import AppearanceAnalysisPort
from app.domain.value_objects import AppearanceProfile


# ---------------------------------------------------------------------------
# Vocabulary vocabularies (approved by data contract)
# ---------------------------------------------------------------------------

_FACE_SHAPE_VOCAB = ["oval", "round", "square", "heart", "diamond", "rectangular"]

_SKIN_TONE_VOCAB = [
    "W00", "W01", "W02", "W03", "W04", "W05",  # warm levels
    "C00", "C01", "C02", "C03", "C04", "C05",  # cool levels
]

_BODY_TYPE_VOCAB = ["slim", "average", "curvy", "plus"]

_STYLE_VIBE_VOCAB = [
    "casual",
    "smart_casual",
    "formal",
    "bohemian",
    "streetwear",
    "preppy",
]


def _deterministic_hash(key: str) -> str:
    """Deterministic SHA-256 hash of a media reference key.

    Same input always produces same output. Used to seed appearance attribute
    generation without depending on any external model provider.

    Note: This is a DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI. The hash
    does not correspond to any real image features; it is purely deterministic
    infrastructure for development and testing.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _hash_to_face_shape(hash_hex: str) -> str:
    """Map hash to a face shape vocab code.

    DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI.
    """
    idx = int(hash_hex[:8], 16) % len(_FACE_SHAPE_VOCAB)
    return _FACE_SHAPE_VOCAB[idx]


def _hash_to_skin_tone(hash_hex: str) -> str:
    """Map hash to a skin tone vocab code.

    DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI.
    """
    idx = int(hash_hex[:8], 16) % len(_SKIN_TONE_VOCAB)
    return _SKIN_TONE_VOCAB[idx]


def _hash_to_body_type(hash_hex: str) -> str:
    """Map hash to a body type vocab code.

    DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI.
    """
    idx = int(hash_hex[:8], 16) % len(_BODY_TYPE_VOCAB)
    return _BODY_TYPE_VOCAB[idx]


def _hash_to_style_vibe(hash_hex: str) -> str:
    """Map hash to a style vibe code.

    DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI.
    """
    idx = int(hash_hex[:8], 16) % len(_STYLE_VIBE_VOCAB)
    return _STYLE_VIBE_VOCAB[idx]


def _hash_to_confidence(hash_hex: str) -> float:
    """Derive a confidence value from hash.

    DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI.
    Confidence = (sum of first 4 hex bytes as int / 0xFFFFFFFF) rounded to 2 dp.
    This yields a float in [0, 1] that is deterministic per input.
    """
    val = int(hash_hex[:8], 16)
    return round(val / 0xFFFFFFFF, 2)


def _hash_to_needs_more_data(confidence: float) -> bool:
    """Derive needs_more_data from confidence.

    DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI.
    Lower confidence signals sparser grounding, triggering needs_more_data.
    """
    return confidence < 0.5


class DevelopmentAppearanceAnalysisAdapter(AppearanceAnalysisPort):
    """DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI.

    Deterministic hash-based appearance analysis adapter that implements the
    `AppearanceAnalysisPort` contract. Given the same media reference key, it
    always produces the same AppearanceProfile. Use only for development and
    testing until a production model adapter is available.

    This adapter does NOT:
    - Depend on OpenAI SDK, Gemini SDK, Claude SDK, TensorFlow, PyTorch, or OpenCV
    - Provide real image analysis or face/appearance detection
    - Claim production-quality results

    It DOES:
    - Implement the AppearanceAnalysisPort abstraction
    - Produce deterministic output suitable for development/testing
    - Follow the approved data contract attribute taxonomy
    - Clearly flag itself as development-only infrastructure
    """

    def _generate_appearance_profile(self, media_ref: dict, user_id: UUID) -> AppearanceProfile:
        """Generate an AppearanceProfile from a media reference using deterministic hashing.

        The generation is entirely hash-based — given the same media_ref key,
        it always produces the same profile. This is NOT real AI analysis; it is
        deterministic infrastructure for development and testing.

        Args:
            media_ref: The MediaRef dict from analysis_runs.input_media. Must
                contain a "key" field with the owner-scoped object storage path.
            user_id: The authenticated user ID.

        Returns:
            AppearanceProfile with faceShape, skinTone, bodyType, styleType, and
            sourceRunId. All observed attributes are derived deterministically
            from the media reference key via SHA-256 hashing.
        """
        key = media_ref.get("key", "")
        if not key:
            # Fallback: generate a provisional profile with a new run ID
            run_id = str(uuid4())
            return AppearanceProfile(
                faceShape="",
                skinTone="",
                bodyType="",
                styleType="",
                sourceRunId=run_id,
            )

        hash_hex = _deterministic_hash(key)

        face_shape = _hash_to_face_shape(hash_hex)
        skin_tone = _hash_to_skin_tone(hash_hex)
        body_type = _hash_to_body_type(hash_hex)
        style_type = _hash_to_style_vibe(hash_hex)

        # Derive sourceRunId from the media key's embedded run ID if possible,
        # otherwise generate a deterministic UUID
        source_run_id = self._extract_source_run_id(key) or str(uuid4())

        return AppearanceProfile(
            faceShape=face_shape,
            skinTone=skin_tone,
            bodyType=body_type,
            styleType=style_type,
            sourceRunId=source_run_id,
        )

    def _extract_source_run_id(self, key: str) -> Optional[str]:
        """Attempt to extract a run ID from the owner-scoped media key.

        Media key format: users/{user_id}/scans/{run_id}/input.{ext}

        Returns the run_id string if found, None otherwise.
        """
        try:
            parts = key.split("/")
            # Expected: ['users', '{user_id}', 'scans', '{run_id}', 'input.{ext}']
            if len(parts) >= 5 and parts[0] == "users" and parts[2] == "scans":
                # The run ID might be the 4th component; validate it looks like a UUID
                potential_id = parts[3]
                # Basic UUID format check (8-4-4-4-12 hex groups)
                import re
                uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
                if re.match(uuid_pattern, potential_id, re.IGNORECASE):
                    return potential_id
        except Exception:
            pass
        return None

    def analyze(
        self,
        *,
        media_ref: dict,
        user_id: UUID,
        image_bytes: bytes | None = None,
    ) -> AppearanceProfile:
        """See `AppearanceAnalysisPort.analyze`."""

        return self._generate_appearance_profile(media_ref, user_id)


    def validate_result(self, result: dict) -> bool:
        """See `AppearanceAnalysisPort.validate_result`.

        Validates that the result dict conforms to the approved appearance data
        contract: required fields present, allowed enum values for observed
        attributes, confidence in [0,1], needs_more_data is bool, sourceRunId
        is a non-empty string.

        Note: This is a contract validation only — it does NOT verify that the
        values represent real image analysis. It only checks schema compliance.
        """
        # Required fields
        required = {"faceShape", "skinTone", "bodyType", "styleType", "sourceRunId", "confidence", "needs_more_data"}
        if not all(k in result for k in required):
            return False

        # Observed attribute values must be from the approved vocabularies
        face_shape_ok = result["faceShape"] in _FACE_SHAPE_VOCAB
        skin_tone_ok = result["skinTone"] in _SKIN_TONE_VOCAB
        body_type_ok = result["bodyType"] in _BODY_TYPE_VOCAB
        style_type_ok = result["styleType"] in _STYLE_VIBE_VOCAB

        if not (face_shape_ok and skin_tone_ok and body_type_ok and style_type_ok):
            return False

        # Confidence must be in [0, 1]
        try:
            conf = float(result["confidence"])
            if not (0.0 <= conf <= 1.0):
                return False
        except (TypeError, ValueError):
            return False

        # needs_more_data must be bool
        if not isinstance(result["needs_more_data"], bool):
            return False

        # sourceRunId must be a non-empty string
        if not isinstance(result["sourceRunId"], str) or not result["sourceRunId"].strip():
            return False

        return True

    def __repr__(self) -> str:
        return ("<DevelopmentAppearanceAnalysisAdapter>"
                " deterministic hash-based; NOT production AI</__repr__>")