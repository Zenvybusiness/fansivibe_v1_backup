"""Garment analysis port — seam between the application layer and the
provider-specific garment vision adapter (M11 wardrobe intelligence).

Mirrors ``appearance_analysis.py`` (BA-3): the application layer depends on
this abstraction only. Concrete adapters live in ``app/ai/`` and must not
depend on OpenAI SDK, Gemini SDK, Claude SDK, TensorFlow, PyTorch, or
OpenCV (plain-HTTP provider clients via httpx are permitted).
"""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.domain.value_objects import GarmentProfile


class GarmentAnalysisPort:
    """Port for garment analysis — measures garment attributes from pixels.

    Implementations must:
    - Accept a media reference dict and user ID
    - Accept the actual image bytes via ``image_bytes`` (callers that hold
      the bytes MUST pass them; adapters MUST analyze these bytes and MUST
      NOT derive attributes from media keys, filenames, or hashes)
    - Return a GarmentProfile with ONLY observed attributes; anything not
      clearly visible stays None (never invented)
    - Raise GarmentAnalysisError (same reason taxonomy as the appearance
      adapter) when no garment is visible, the subject is ambiguous, the
      provider is unreachable, confidence is below floor, or the provider
      output fails validation
    """

    @abstractmethod
    def analyze(
        self,
        *,
        media_ref: dict,
        user_id: UUID,
        image_bytes: bytes | None = None,
    ) -> GarmentProfile:
        """Measure garment attributes from the supplied image bytes."""
        ...

    @abstractmethod
    def validate_result(self, result: dict) -> bool:
        """Validate a garment result dict against the approved contract.

        Required keys: category, subcategory, color, pattern, material,
        style, fit, confidence, needs_review. Nullable attribute values
        stay nullable (never coerced to a guess); confidence is a float
        in [0, 1]; needs_review is a bool.
        """
        ...
