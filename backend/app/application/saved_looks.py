"""Application use case — save a recommendation (UC-15) and list saved looks.

Save (`SaveRecommendation`) is TRX-3 true transaction: the `saved_looks`
insert, the `look_saved` learning signal, and the M10-A styled-day upsert
commit together (all-or-nothing).
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
from typing import Any, Optional, Sequence
from uuid import UUID

from app.api.errors import ApiError, conflict, not_found
from app.api.schemas.saved_looks import HydratedGarmentItem
from app.application.learning import mark_styled_today
from app.domain.ports.external import KnowledgeSource
from app.domain.ports.repositories import (
    ActivityDayRepository,
    LearningSignalRepository,
    SavedLookRecord,
    SavedLookRepository,
    WardrobeItemRecord,
    WardrobeItemRepository,
)
from app.domain.ports.storage import ObjectStoragePort


_SOURCE_CONTEXTS = {"hairstyle", "grooming", "outfit", "daily"}

# Snapshot `selectedItemIds` ownership validation (BC-56) applies to the
# outfit family saves: "outfit" and the M9 "daily" TodayLook save (DEC-018
# §1 — otherwise daily item IDs would skip validation). Hairstyle /
# grooming snapshots pass through untouched, exactly as before.
_VALIDATED_CONTEXTS = ("outfit", "daily")


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
        activity_days: Optional[ActivityDayRepository] = None,
    ) -> None:
        self._saved_looks = saved_looks
        self._signals = signals
        self._knowledge = knowledge
        self._wardrobe_items = wardrobe_items
        self._activity_days = activity_days

    def _validated_outfit_snapshot(
        self, *, user_id: UUID, snapshot: dict
    ) -> dict:
        """Validate and normalize `snapshot.selectedItemIds` for an outfit-family save.

        `source_context` is authoritative: this runs only for "outfit" and
        M9 "daily" saves, and outfit-family identity is never inferred from
        the snapshot itself. Hairstyle / grooming snapshots pass through
        untouched. Returns the snapshot to persist — identical except
        `selectedItemIds`, when supplied, becomes the deterministic sorted
        list of unique canonical UUID strings.
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

        if source_context in _VALIDATED_CONTEXTS:
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
            if self._activity_days is not None:
                # M10-A: today's styled-day upsert rides this same commit
                # (TRX-3 now covers save + signal + activity day). The
                # idempotent-replay path above returns before any insert,
                # so replays never touch activity history.
                mark_styled_today(activity_days=self._activity_days, user_id=user_id)
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


class GetSavedLook:
    """Retrieve one owned saved look (endpoint `GET /v1/looks/saved/{saved_look_id}`).

    Owner-scoped lookup (OW-1, 404-not-403). Foreign or missing ID raises 404.
    """

    def __init__(self, *, saved_looks: SavedLookRepository) -> None:
        self._saved_looks = saved_looks

    def __call__(
        self,
        *,
        user_id: UUID,
        saved_look_id: UUID,
    ) -> SavedLookRecord:
        record = self._saved_looks.get_for_user(
            user_id=user_id, saved_look_id=saved_look_id
        )
        if record is None:
            raise not_found()
        return record


class HydrateSavedLookGarments:
    """Enriches saved looks with current active wardrobe items and presigned image URLs (P1-2).

    Read-only: never modifies the database or the durable snapshot.
    Enforces OW-1: queries only wardrobe items belonging to user_id.
    Handles archived/deleted garments gracefully with isArchived=True.
    Avoids N+1 queries by batching all garment lookups across all records.
    """

    def __init__(
        self,
        *,
        wardrobe_items: WardrobeItemRepository,
        storage: Optional[ObjectStoragePort] = None,
    ) -> None:
        self._wardrobe_items = wardrobe_items
        self._storage = storage

    async def __call__(
        self,
        *,
        user_id: UUID,
        records: Sequence[SavedLookRecord],
    ) -> dict[UUID, list[HydratedGarmentItem]]:
        result: dict[UUID, list[HydratedGarmentItem]] = {}
        if not records:
            return result

        # 1. Collect all distinct referenced garment UUIDs across all records
        all_garment_ids: set[UUID] = set()
        for record in records:
            if record.source_context in ("hairstyle", "grooming"):
                continue

            snapshot = record.snapshot if isinstance(record.snapshot, dict) else {}
            components = snapshot.get("components")
            if isinstance(components, list):
                for comp in components:
                    if isinstance(comp, dict) and comp.get("id"):
                        try:
                            all_garment_ids.add(UUID(str(comp["id"])))
                        except (ValueError, TypeError):
                            pass
            selected_ids = snapshot.get("selectedItemIds")
            if isinstance(selected_ids, list):
                for sid in selected_ids:
                    try:
                        all_garment_ids.add(UUID(str(sid)))
                    except (ValueError, TypeError):
                        pass

        # 2. Batch query active wardrobe items owned by user_id
        active_items: dict[str, WardrobeItemRecord] = {}
        if all_garment_ids:
            found_records = self._wardrobe_items.get_by_ids(
                user_id=user_id, item_ids=list(all_garment_ids)
            )
            for item in found_records:
                active_items[str(item.id)] = item

        # 3. Pre-generate presigned GET URLs for all active items that have valid keys
        presigned_urls: dict[str, tuple[str, dict[str, Any]]] = {}
        if self._storage is not None:
            user_prefix = f"users/{user_id}/"
            for gid, item in active_items.items():
                image_ref = item.image_ref
                if image_ref and isinstance(image_ref, dict):
                    key = (
                        image_ref.get("objectKey")
                        or image_ref.get("object_key")
                        or image_ref.get("canonical_key")
                        or image_ref.get("canonicalKey")
                        or image_ref.get("key")
                    )
                    # Verify key belongs to this user namespace (OW-1 defense)
                    if key and isinstance(key, str) and (key.startswith(user_prefix) or str(user_id) in key):
                        try:
                            url = await self._storage.generate_presigned_get_url(
                                key=key, expires_in_s=900
                            )
                            enriched_ref = {**image_ref, "downloadUrl": url, "url": url}
                            presigned_urls[gid] = (url, enriched_ref)
                        except Exception:
                            pass

        # 4. Construct HydratedGarmentItem list for each look
        for record in records:
            if record.source_context in ("hairstyle", "grooming"):
                result[record.id] = []
                continue

            snapshot = record.snapshot if isinstance(record.snapshot, dict) else {}
            components = snapshot.get("components")
            selected_ids = snapshot.get("selectedItemIds")

            look_items: list[HydratedGarmentItem] = []
            seen_ids: set[str] = set()

            if isinstance(components, list) and components:
                for comp in components:
                    if not isinstance(comp, dict):
                        continue
                    raw_id = comp.get("id")
                    if not raw_id:
                        continue
                    gid = str(raw_id)
                    seen_ids.add(gid)

                    if gid in active_items:
                        active = active_items[gid]
                        img_url, img_ref = presigned_urls.get(gid, (None, active.image_ref))
                        look_items.append(
                            HydratedGarmentItem(
                                id=gid,
                                name=active.name or comp.get("name") or "Garment",
                                category=active.category or comp.get("category") or "unknown",
                                color=active.color or comp.get("color") or "",
                                material=active.material or comp.get("material"),
                                isFavorite=active.is_favorite,
                                imageRef=img_ref,
                                imageUrl=img_url,
                                fit=active.fit,
                                fitConfidence=active.fit_confidence,
                                reason=comp.get("reason"),
                                isArchived=False,
                            )
                        )
                    else:
                        look_items.append(
                            HydratedGarmentItem(
                                id=gid,
                                name=comp.get("name") or "Archived Garment",
                                category=comp.get("category") or "unknown",
                                color=comp.get("color") or "",
                                material=comp.get("material"),
                                isFavorite=False,
                                imageRef=None,
                                imageUrl=None,
                                fit=None,
                                fitConfidence=None,
                                reason=comp.get("reason"),
                                isArchived=True,
                            )
                        )
            elif isinstance(selected_ids, list) and selected_ids:
                for raw_id in selected_ids:
                    gid = str(raw_id)
                    if gid in seen_ids:
                        continue
                    seen_ids.add(gid)

                    if gid in active_items:
                        active = active_items[gid]
                        img_url, img_ref = presigned_urls.get(gid, (None, active.image_ref))
                        look_items.append(
                            HydratedGarmentItem(
                                id=gid,
                                name=active.name or "Garment",
                                category=active.category or "unknown",
                                color=active.color or "",
                                material=active.material,
                                isFavorite=active.is_favorite,
                                imageRef=img_ref,
                                imageUrl=img_url,
                                fit=active.fit,
                                fitConfidence=active.fit_confidence,
                                reason=None,
                                isArchived=False,
                            )
                        )
                    else:
                        look_items.append(
                            HydratedGarmentItem(
                                id=gid,
                                name="Archived Garment",
                                category="unknown",
                                color="",
                                material=None,
                                isFavorite=False,
                                imageRef=None,
                                imageUrl=None,
                                fit=None,
                                fitConfidence=None,
                                reason=None,
                                isArchived=True,
                            )
                        )

            result[record.id] = look_items

        return result
