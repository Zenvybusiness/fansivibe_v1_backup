"""Application use case — submit a recommendation reaction (UC-32, M11).

`SubmitRecommendationFeedback` (endpoint #35 `POST /v1/feedback`)
appends exactly one `feedback_events` row (tier 1) and nothing else:
no learning-signal write (M10 is the sole writer, PR-7), no
activity-day upsert (raw reactions never mark a day styled), no wear /
wardrobe / save / event mutation, no preference write — and no commit
beyond the single row insert.

Target rules (BC-38/39, OW-1): at most one target per reaction (else
422); a catalog `targetLookId` must exist (else 404); an owned
`targetSavedLookId` must parse as UUID (else 422) and resolve to an
owned saved look (else 404-not-403 — foreign and missing are
indistinguishable, and nothing is stored either way).

Idempotency (C-12/API-33, M7 precedent): the contract's
`Idempotency-Key` is required (the router rejects a missing key). A
repeated key with the same canonical payload returns the original row
without re-inserting; a repeated key with a different payload is a
409 conflict. The key is stored verbatim (M7 precedent).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.api.errors import ApiError, conflict, database_failure, not_found
from app.domain.ports.repositories import (
    FeedbackEventRecord,
    FeedbackRepository,
    LookRepository,
    SavedLookRepository,
)

# Structural bounds (M9/M13 precedent: BC-13 family ceiling; the rating
# vocabulary itself is deliberately unfrozen — BC-38/39, PR-12).
_RATING_MAX_LENGTH = 200


def _field_error(
    field: str, error: str, allowed: Optional[list] = None
) -> ApiError:
    details: dict = {"field": field, "error": error}
    if allowed is not None:
        details["allowed"] = allowed
    return ApiError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Some of the provided values are not valid. Please check your input.",
        details={"field_errors": [details]},
    )


class SubmitRecommendationFeedback:
    def __init__(
        self,
        *,
        feedback: FeedbackRepository,
        saved_looks: SavedLookRepository,
        looks: LookRepository,
    ) -> None:
        self._feedback = feedback
        self._saved_looks = saved_looks
        self._looks = looks

    def __call__(
        self,
        *,
        user_id: UUID,
        rating: object,
        reason: object = None,
        target_look_id: object = None,
        target_saved_look_id: object = None,
        idempotency_key: str,
    ) -> FeedbackEventRecord:
        """Appends one reaction row (or returns the idempotent original)."""
        clean_rating = self._validated_rating(rating)
        clean_reason = self._validated_reason(reason)
        clean_look_id, clean_saved_id = self._validated_targets(
            user_id=user_id,
            target_look_id=target_look_id,
            target_saved_look_id=target_saved_look_id,
        )

        existing = self._feedback.get_by_idempotency(
            user_id=user_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            same_payload = (
                existing.rating == clean_rating
                and existing.reason == clean_reason
                and existing.target_look_id == clean_look_id
                and existing.target_saved_look_id == clean_saved_id
            )
            if not same_payload:
                raise conflict("duplicate")
            return existing

        try:
            saved = self._feedback.insert(
                user_id=user_id,
                target_look_id=clean_look_id,
                target_saved_look_id=clean_saved_id,
                rating=clean_rating,
                reason=clean_reason,
                idempotency_key=idempotency_key,
            )
            self._feedback.commit()
        except Exception:
            self._feedback.rollback()
            raise database_failure()
        return saved

    def _validated_rating(self, rating: object) -> str:
        if not isinstance(rating, str) or not rating.strip():
            raise _field_error("rating", "must be a non-empty string")
        if len(rating) > _RATING_MAX_LENGTH:
            raise _field_error(
                "rating",
                f"must be between 1 and {_RATING_MAX_LENGTH} characters",
            )
        return rating.strip()

    def _validated_reason(self, reason: object) -> Optional[str]:
        if reason is None:
            return None
        if not isinstance(reason, str) or not reason.strip():
            raise _field_error("reason", "must be a non-empty string")
        return reason.strip()

    def _validated_targets(
        self,
        *,
        user_id: UUID,
        target_look_id: object,
        target_saved_look_id: object,
    ) -> tuple[Optional[str], Optional[UUID]]:
        if target_look_id is not None and target_saved_look_id is not None:
            raise _field_error(
                "targetSavedLookId",
                "at most one target per reaction",
            )
        clean_look_id: Optional[str] = None
        if target_look_id is not None:
            if (
                not isinstance(target_look_id, str)
                or not target_look_id.strip()
            ):
                raise _field_error(
                    "targetLookId", "must be a non-empty string"
                )
            clean_look_id = target_look_id.strip()
            if self._looks.get_by_code(code=clean_look_id) is None:
                # Catalog existence only (KN catalog is system-owned):
                # unknown codes are not-found, never validation noise.
                raise not_found()
        clean_saved_id: Optional[UUID] = None
        if target_saved_look_id is not None:
            if (
                not isinstance(target_saved_look_id, str)
                or not target_saved_look_id.strip()
            ):
                raise _field_error(
                    "targetSavedLookId", "must be a non-empty string"
                )
            try:
                clean_saved_id = UUID(target_saved_look_id.strip())
            except (ValueError, TypeError):
                raise _field_error(
                    "targetSavedLookId",
                    f"not a valid UUID: {target_saved_look_id}",
                )
            if (
                self._saved_looks.get_for_user(
                    user_id=user_id, saved_look_id=clean_saved_id
                )
                is None
            ):
                # Owner-scoped lookup: nonexistent and foreign IDs are
                # indistinguishable by design (OW-1, 404-not-403). The
                # reaction is rejected outright — nothing is stored.
                raise not_found()
        return clean_look_id, clean_saved_id
