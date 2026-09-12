"""Application use case — save a recommendation (UC-15) and list saved looks.

Save (`SaveRecommendation`) is TRX-3 true transaction: the `saved_looks`
insert and the `look_saved` learning signal commit together (all-or-nothing).
Idempotent replay via the contract's `Idempotency-Key` (C-12/API-33): a
repeated key with the same payload returns the original save; a repeated key
with a different payload is a conflict. The save never mutates the producing
run.

List (`ListSavedLooks`) is the owner-scoped read surface for endpoint #24
(`GET /v1/looks/saved`): paginated, `createdAt`-desc, no fabrication.

Delete (`DeleteSavedLook`) is the owner-scoped removal surface for endpoint
#25 (`DELETE /v1/looks/saved/{saved_look_id}`, DEC-013): physical row delete,
single commit, no signal write — history (`learning_signals`) is preserved.
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
    WardrobeItemRepository,
)

_SOURCE_CONTEXTS = {"hairstyle", "grooming", "outfit"}


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


def _invalid_selected_item_ids(details: str) -> ApiError:
    """422 for a malformed outfit `selectedItemIds` field (not a list, or a
    member that is not a UUID string). Unknown or foreign item IDs are a 404
    via `not_found()` instead — the item does not exist for this owner."""
    return ApiError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Some of the provided values are not valid. Please check your input.",
        details={
            "field_errors": [
                {
                    "field": "snapshot.selectedItemIds",
                    "error": details,
                }
            ]
        },
    )


class SaveRecommendation:
    def __init__(
        self,
        *,
        saved_looks: SavedLookRepository,
        signals: LearningSignalRepository,
        knowledge: KnowledgeSource,
        wardrobe_items: WardrobeItemRepository,
    ) -> None:
        self._saved_looks = saved_looks
        self._signals = signals
        self._knowledge = knowledge
        self._wardrobe_items = wardrobe_items

    def _validated_outfit_snapshot(
        self, *, user_id: UUID, snapshot: dict
    ) -> dict:
        """Validate and normalize `snapshot.selectedItemIds` for an outfit save.

        `source_context` is authoritative: this runs only for outfit saves, and
        outfit identity is never inferred from the snapshot itself. Hairstyle /
        grooming snapshots pass through untouched. Returns the snapshot to
        persist — identical except `selectedItemIds`, when supplied, becomes
        the deterministic sorted list of unique canonical UUID strings.
        """
        if not isinstance(snapshot, dict):
            raise _invalid_selected_item_ids("snapshot must be an object")
        if "selectedItemIds" not in snapshot:
            return snapshot
        raw_ids = snapshot["selectedItemIds"]
        if not isinstance(raw_ids, list):
            raise _invalid_selected_item_ids("must be a list of wardrobe item IDs")
        parsed: list[UUID] = []
        for raw in raw_ids:
            if not isinstance(raw, str):
                raise _invalid_selected_item_ids("every item ID must be a UUID string")
            try:
                parsed.append(UUID(raw))
            except (ValueError, TypeError):
                raise _invalid_selected_item_ids(f"not a valid UUID: {raw}")
        for item_id in parsed:
            if self._wardrobe_items.get_by_id(user_id=user_id, item_id=item_id) is None:
                # Owner-scoped lookup: nonexistent and foreign IDs are
                # indistinguishable by design (OW-1, 404-not-403). The save is
                # rejected outright — foreign IDs are never silently dropped.
                raise not_found()
        canonical = sorted({str(item_id) for item_id in parsed})
        return {**snapshot, "selectedItemIds": canonical}

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

        if source_context == "outfit":
            # Normalized BEFORE the idempotency check so a byte-identical
            # replay compares against the canonical persisted form and
            # returns the original row (C-12/API-33), instead of conflicting
            # with its own normalization.
            snapshot = self._validated_outfit_snapshot(
                user_id=user_id, snapshot=snapshot
            )

        existing = self._saved_looks.get_by_idempotency(
            user_id=user_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            same_payload = (
                existing.look_id == look_id
                and existing.title == title
                and existing.source_context == source_context
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
                source_context=source_context,
                snapshot=snapshot,
                idempotency_key=idempotency_key,
                source_run_id=source_run_id,
            )
            self._signals.insert_look_saved(
                user_id=user_id,
                signal_type="look_saved",
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


class ListSavedLooks:
    """List the owner's saved looks (endpoint #24 `GET /v1/looks/saved`).

    Owner scoping is enforced by the repository (OW-1); rows are ordered
    `createdAt` desc per PAGINATION_FILTERING §9.3. Missing rows are simply an
    empty page — never fabricated.
    """

    def __init__(self, *, saved_looks: SavedLookRepository) -> None:
        self._saved_looks = saved_looks

    def __call__(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[SavedLookRecord], int]:
        """Returns (saved_look records, total count) for the owner."""
        return self._saved_looks.list_for_user(
            user_id=user_id, page=page, page_size=page_size
        )


class DeleteSavedLook:
    """Delete one owned saved look (endpoint #25, DEC-013).

    Owner-scoped delete: a missing or foreign id is the same not-found
    condition (OW-1, 404-not-403). Successful delete physically removes
    exactly that row (snapshot included) with a single commit. No
    learning signal is written and existing signals are untouched.
    """

    def __init__(self, *, saved_looks: SavedLookRepository) -> None:
        self._saved_looks = saved_looks

    def __call__(
        self,
        *,
        user_id: UUID,
        saved_look_id: UUID,
    ) -> None:
        record = self._saved_looks.get_for_user(
            user_id=user_id, saved_look_id=saved_look_id
        )
        if record is None:
            raise not_found()
        self._saved_looks.delete(user_id=user_id, saved_look_id=saved_look_id)
        self._saved_looks.commit()
