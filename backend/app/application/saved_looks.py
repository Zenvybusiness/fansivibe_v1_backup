"""Application use case — save a recommendation (UC-15).

TRX-3 true transaction: the `saved_looks` insert and the `look_saved`
learning signal commit together (all-or-nothing). Idempotent replay via the
contract's `Idempotency-Key` (C-12/API-33): a repeated key with the same
payload returns the original save; a repeated key with a different payload is
a conflict. The save never mutates the producing run.
"""

from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from app.api.errors import ApiError, conflict, not_found
from app.domain.ports.external import KnowledgeSource
from app.domain.ports.repositories import (
    LearningSignalRepository,
    SavedLookRecord,
    SavedLookRepository,
)

_SOURCE_CONTEXTS = {"hairstyle", "grooming"}


def _source_run_id_from_snapshot(snapshot: dict) -> Optional[UUID]:
    """Provenance link: the producing run named inside the result snapshot."""
    appearance = snapshot.get("appearance") or {}
    value = appearance.get("sourceRunId")
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


class SaveRecommendation:
    def __init__(
        self,
        *,
        saved_looks: SavedLookRepository,
        signals: LearningSignalRepository,
        knowledge: KnowledgeSource,
    ) -> None:
        self._saved_looks = saved_looks
        self._signals = signals
        self._knowledge = knowledge

    def __call__(
        self,
        *,
        user_id: UUID,
        look_id: Optional[str],
        title: str,
        snapshot: dict,
        source_context: str,
        idempotency_key: str,
    ) -> tuple[SavedLookRecord, bool]:
        """Returns (saved_look, created). `created=False` on idempotent replay."""
        if source_context not in _SOURCE_CONTEXTS:
            raise ApiError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="Some of the provided values are not valid. Please check your input.",
                details={
                    "field_errors": [
                        {
                            "field": "sourceContext",
                            "error": "unknown value",
                            "allowed": sorted(_SOURCE_CONTEXTS),
                        }
                    ]
                },
            )

        if look_id is not None and self._knowledge.lookup_hairstyle_look(look_id) is None and self._knowledge.lookup_grooming_look(look_id) is None:
            raise not_found()

        existing = self._saved_looks.get_by_idempotency(
            user_id=user_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            same_payload = (
                existing.look_id == look_id
                and existing.title == title
                and json.dumps(existing.snapshot, sort_keys=True)
                == json.dumps(snapshot, sort_keys=True)
            )
            if not same_payload:
                raise conflict("duplicate")
            return existing, False

        source_run_id = _source_run_id_from_snapshot(snapshot)
        try:
            saved = self._saved_looks.insert(
                user_id=user_id,
                look_id=look_id,
                title=title,
                snapshot=snapshot,
                idempotency_key=idempotency_key,
                source_run_id=source_run_id,
            )
            self._signals.insert_look_saved(
                user_id=user_id,
                label=title,
                context={"source_context": source_context, "look_id": look_id},
            )
            self._saved_looks.commit()
        except Exception:
            self._saved_looks.rollback()
            raise ApiError(
                status_code=500,
                code="DATABASE_FAILURE",
                message="Something went wrong while saving your data. Please try again.",
            )
        return saved, True
