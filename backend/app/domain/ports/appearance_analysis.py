"""Appearance analysis port — the seam between the application layer and
provider-specific model adapters.

The application/domain layer depends on this abstraction only (BA-3). Concrete
adapters live in `app/ai/` and must not depend on OpenAI SDK, Gemini SDK,
Claude SDK, TensorFlow, PyTorch, or OpenCV.

See `DevelopmentAppearanceAnalysisAdapter` for the deterministic development
implementation. Production model adapters must implement this port without
depending on external model providers.
"""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.domain.value_objects import AppearanceProfile


class AppearanceAnalysisPort:
    """Port for appearance analysis — separates the domain layer from
    provider-specific model implementations.

    Implementations must:
    - Accept a media reference dict and user ID
    - Accept the actual image bytes via the optional ``image_bytes`` parameter
      whenever the caller holds them (STEP 10 boundary fix — see ``analyze``)
    - Return an AppearanceProfile with only the attributes approved in the
      data contract (faceShape, skinTone, bodyType, styleType, sourceRunId)
    - NOT depend on OpenAI SDK, Gemini SDK, Claude SDK, TensorFlow, PyTorch,
      or OpenCV (plain-HTTP provider clients, e.g. via httpx, are permitted)
    - Produce deterministic, rules-based output suitable for development and
      testing
    - Clearly document when the implementation is DEVELOPMENT IMPLEMENTATION —
      NOT PRODUCTION AI
    """

    @abstractmethod
    def analyze(
        self,
        *,
        media_ref: dict,
        user_id: UUID,
        image_bytes: bytes | None = None,
    ) -> AppearanceProfile:
        """Analyze appearance from a media reference.

        Args:
            media_ref: The MediaRef dict from analysis_runs.input_media, expected
                to contain at minimum a "key" field with the owner-scoped object
                storage path.
            user_id: The authenticated user ID, used for owner-scoped processing.
            image_bytes: The actual received image bytes for this scan, when the
                caller holds them in the request lifecycle.

                STEP 10 boundary fix (explicit, backwards compatible): the
                persisted ``media_ref`` is metadata only and no object storage
                exists, so an adapter physically cannot obtain image bytes from
                ``media_ref`` alone. Callers that hold the bytes (e.g.
                ``CreateHairstyleImageRun``) MUST pass them here; production
                adapters MUST analyze these bytes and MUST NOT fall back to
                deterministic derivation from the media key. Adapters that do
                not need bytes (e.g. the development adapter) ignore this
                parameter, so existing callers are unaffected.

        Returns:
            AppearanceProfile with faceShape, skinTone, bodyType, styleType, and
            sourceRunId populated from the analysis. The profile follows the
            approved data contract taxonomy:

            - **OBSERVED**: faceShape, skinTone, bodyType — deterministic derivation
              from the media reference (development implementation uses hash-based
              generation)
            - **INFERRED**: sourceRunId — the producing run UUID, preserved as
              provenance
            - **DERIVED** (computed by caller): confidence, needs_more_data

        Note: This method must NOT depend on any external model provider (OpenAI,
        Gemini, Claude, TensorFlow, PyTorch, OpenCV). Use only deterministic,
        rules-based, or hash-based approaches.
        """
        ...

    @abstractmethod
    def validate_result(self, result: dict) -> bool:
        """Validate an analysis result dict against the approved data contract.

        Checks:
        - Required fields present: faceShape, skinTone, bodyType, styleType,
          sourceRunId, confidence, needs_more_data
        - Observed attribute values are from the allowed vocabulary:
            faceShape: oval, round, square, heart, diamond, rectangular
            skinTone: warm/cool + level codes
            bodyType: slim, average, curvy, plus
            styleType: 6 StyleVibe codes from onboarding
        - confidence is a float in [0, 1]
        - needs_more_data is a bool
        - sourceRunId is a non-empty string (UUID format)

        Returns:
            True if the result passes all contract validation, False otherwise.

        Note: This method must NOT leak provider-specific internals. It only
        validates the shape and allowed values of the approved attributes.
        """
        ...