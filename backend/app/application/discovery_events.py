"""Discovery interaction events application use cases (TASK DISCOVERY-10A).

Provides validated, identity-isolated ingestion of discovery interaction events:
- Product impressions (with dwell and visibility thresholds)
- Product clicks, saves, unsaves
- Complete Look candidate selections

Invariants:
- Identity Isolation: authenticated user (via verified JWT claims) OR guest session (UUIDv4).
  Requests cannot contain both, and cannot contain neither.
- Client cannot provide or override userId.
- Event allow-list: product_impression, product_click, product_save, product_unsave, look_select.
  look_save and product_dismiss are deferred and rejected.
- Deterministic look ID format (^look_[a-f0-9]{16}$) required for complete_look targets.
- Unknown product targets fail closed with 404 NOT_FOUND.
- Timestamp bounds: occurredAt must be within [now - 24h, now + 5m].
- Bounded metadata with strict privacy-protecting allow-list.
- Idempotent deduplication and conflict detection (409 on duplicate ID with conflicting payload).
- Single-transaction atomic batch writes (1 to 50 events).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence
from uuid import UUID

from app.api.errors import ApiError, validation
from app.api.schemas.discovery import (
    DiscoveryEventAckSchema,
    DiscoveryEventIngestItemSchema,
    DiscoveryEventsBatchRequest,
    DiscoveryEventsIngestResponse,
)
from app.domain.ports.repositories import DiscoveryEventRepository

_LOOK_ID_REGEX = re.compile(r"^look_[a-f0-9]{16}$")
_ALLOWED_EVENT_TYPES = {
    "product_impression",
    "product_click",
    "product_save",
    "product_unsave",
    "look_select",
    "offer_click",
}
_DEFERRED_EVENT_TYPES = {"look_save", "product_dismiss"}
_ALLOWED_SURFACES = {
    "for_you_hero",
    "for_you_grid",
    "because_you_like",
    "complete_looks",
    "product_offers",
    "product_offer_sheet",
}
_ALLOWED_CATEGORIES = {"tops", "bottoms", "outerwear", "footwear", "accessories"}


def compute_payload_hash(
    *,
    event_type: str,
    target_type: str,
    target_id: str,
    surface: str,
    position: Optional[int],
    metadata: dict[str, Any],
) -> str:
    """Compute deterministic SHA-256 hash of canonical event payload attributes."""
    canonical_dict = {
        "event_type": event_type,
        "target_type": target_type,
        "target_id": target_id,
        "surface": surface,
        "position": position,
        "metadata": metadata,
    }
    canonical_repr = json.dumps(
        canonical_dict, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


class IngestDiscoveryEvents:
    """Application use case for validating and persisting discovery interaction events."""

    def __init__(self, repository: DiscoveryEventRepository) -> None:
        self._repository = repository

    def __call__(
        self,
        *,
        request: DiscoveryEventsBatchRequest,
        user_id: Optional[UUID],
    ) -> DiscoveryEventsIngestResponse:
        # 1. Identity isolation & mutual exclusivity
        guest_session_id = request.guestSessionId

        if user_id is not None and guest_session_id is not None:
            raise validation(
                [
                    {
                        "field": "guestSessionId",
                        "error": "Authenticated requests cannot provide guestSessionId.",
                    }
                ]
            )

        if user_id is None and guest_session_id is None:
            raise validation(
                [
                    {
                        "field": "guestSessionId",
                        "error": "Guest requests must provide a valid guestSessionId.",
                    }
                ]
            )

        events: list[DiscoveryEventIngestItemSchema] = request.events
        if not events:
            raise validation(
                [
                    {
                        "field": "events",
                        "error": "Batch must contain between 1 and 50 events.",
                    }
                ]
            )

        # 2. Comprehensive validation across all events
        now = datetime.now(timezone.utc)
        min_occurred_at = now - timedelta(hours=24)
        max_occurred_at = now + timedelta(minutes=5)

        field_errors: list[dict[str, Any]] = []
        product_target_ids: set[UUID] = set()

        for idx, ev in enumerate(events):
            prefix = f"events.{idx}"

            # Event type check
            if ev.eventType in _DEFERRED_EVENT_TYPES:
                field_errors.append(
                    {
                        "field": f"{prefix}.eventType",
                        "error": f"Event type '{ev.eventType}' is deferred and not accepted.",
                    }
                )
            elif ev.eventType not in _ALLOWED_EVENT_TYPES:
                field_errors.append(
                    {
                        "field": f"{prefix}.eventType",
                        "error": f"Event type '{ev.eventType}' is not supported.",
                    }
                )

            # Target type & target ID check
            if ev.targetType == "product":
                if ev.eventType not in {
                    "product_impression",
                    "product_click",
                    "product_save",
                    "product_unsave",
                    "offer_click",
                }:
                    field_errors.append(
                        {
                            "field": f"{prefix}.eventType",
                            "error": f"Event type '{ev.eventType}' is not valid for product target.",
                        }
                    )
                try:
                    p_uuid = UUID(ev.targetId)
                    product_target_ids.add(p_uuid)
                except (ValueError, TypeError):
                    field_errors.append(
                        {
                            "field": f"{prefix}.targetId",
                            "error": "Product targetId must be a valid UUID.",
                        }
                    )
            elif ev.targetType == "complete_look":
                if ev.eventType != "look_select":
                    field_errors.append(
                        {
                            "field": f"{prefix}.eventType",
                            "error": f"Event type '{ev.eventType}' is not valid for complete_look target.",
                        }
                    )
                if not _LOOK_ID_REGEX.match(ev.targetId):
                    field_errors.append(
                        {
                            "field": f"{prefix}.targetId",
                            "error": "Complete look targetId must match format 'look_{16-char-hex}'.",
                        }
                    )
            else:
                field_errors.append(
                    {
                        "field": f"{prefix}.targetType",
                        "error": f"Target type '{ev.targetType}' is not supported.",
                    }
                )

            # Surface check
            if ev.surface not in _ALLOWED_SURFACES:
                field_errors.append(
                    {
                        "field": f"{prefix}.surface",
                        "error": f"Surface '{ev.surface}' is not supported.",
                    }
                )

            # Position check
            if ev.position is not None and not (0 <= ev.position <= 1000):
                field_errors.append(
                    {
                        "field": f"{prefix}.position",
                        "error": "Position must be between 0 and 1000.",
                    }
                )

            # Timestamp bounds check
            occurred_at = (
                ev.occurredAt
                if ev.occurredAt.tzinfo is not None
                else ev.occurredAt.replace(tzinfo=timezone.utc)
            )
            if occurred_at < min_occurred_at or occurred_at > max_occurred_at:
                field_errors.append(
                    {
                        "field": f"{prefix}.occurredAt",
                        "error": "Timestamp occurredAt is outside acceptable window [now - 24h, now + 5m].",
                    }
                )

            # Metadata bounds & allow-list
            meta = ev.metadata or {}
            if len(meta.keys()) > 8:
                field_errors.append(
                    {
                        "field": f"{prefix}.metadata",
                        "error": "Metadata exceeds maximum 8 keys limit.",
                    }
                )
            try:
                meta_json = json.dumps(meta)
                if len(meta_json) > 1024:
                    field_errors.append(
                        {
                            "field": f"{prefix}.metadata",
                            "error": "Metadata exceeds maximum 1024 bytes limit.",
                        }
                    )
            except (TypeError, ValueError):
                field_errors.append(
                    {
                        "field": f"{prefix}.metadata",
                        "error": "Metadata is not valid JSON.",
                    }
                )

            # Metadata key allow-lists per event type
            if ev.eventType == "product_impression":
                allowed_keys = {"dwellTimeMs", "viewportRatio"}
                for k in meta.keys():
                    if k not in allowed_keys:
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.{k}",
                                "error": f"Disallowed metadata key '{k}' for product_impression.",
                            }
                        )
                if "dwellTimeMs" in meta:
                    v = meta["dwellTimeMs"]
                    if not isinstance(v, int) or isinstance(v, bool) or not (1000 <= v <= 60000):
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.dwellTimeMs",
                                "error": "dwellTimeMs must be an integer between 1000 and 60000.",
                            }
                        )
                if "viewportRatio" in meta:
                    v = meta["viewportRatio"]
                    if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.5 <= v <= 1.0):
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.viewportRatio",
                                "error": "viewportRatio must be a float between 0.5 and 1.0.",
                            }
                        )
            elif ev.eventType in {"product_click", "product_save", "product_unsave"}:
                allowed_keys = {"activeCategoryFilter"}
                for k in meta.keys():
                    if k not in allowed_keys:
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.{k}",
                                "error": f"Disallowed metadata key '{k}' for {ev.eventType}.",
                            }
                        )
                if "activeCategoryFilter" in meta:
                    v = meta["activeCategoryFilter"]
                    if v is not None and v not in _ALLOWED_CATEGORIES:
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.activeCategoryFilter",
                                "error": "activeCategoryFilter must be null or an allowed category.",
                            }
                        )
            elif ev.eventType == "offer_click":
                allowed_keys = {
                    "offerId",
                    "retailer",
                    "retailerSlug",
                    "activeCategoryFilter",
                }
                for k in meta.keys():
                    if k not in allowed_keys:
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.{k}",
                                "error": f"Disallowed metadata key '{k}' for offer_click.",
                            }
                        )
                if "offerId" in meta:
                    v = meta["offerId"]
                    try:
                        UUID(str(v))
                    except (ValueError, TypeError):
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.offerId",
                                "error": "offerId must be a valid UUID string.",
                            }
                        )
                if "retailer" in meta:
                    v = meta["retailer"]
                    if not isinstance(v, str) or not (1 <= len(v) <= 100):
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.retailer",
                                "error": "retailer must be a non-empty string up to 100 characters.",
                            }
                        )
                if "retailerSlug" in meta:
                    v = meta["retailerSlug"]
                    if not isinstance(v, str) or not (1 <= len(v) <= 100):
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.retailerSlug",
                                "error": "retailerSlug must be a non-empty string up to 100 characters.",
                            }
                        )
                if "activeCategoryFilter" in meta:
                    v = meta["activeCategoryFilter"]
                    if v is not None and v not in _ALLOWED_CATEGORIES:
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.activeCategoryFilter",
                                "error": "activeCategoryFilter must be null or an allowed category.",
                            }
                        )
            elif ev.eventType == "look_select":
                allowed_keys = {"selectedSlotCount", "totalCatalogPrice"}
                for k in meta.keys():
                    if k not in allowed_keys:
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.{k}",
                                "error": f"Disallowed metadata key '{k}' for look_select.",
                            }
                        )
                if "selectedSlotCount" in meta:
                    v = meta["selectedSlotCount"]
                    if not isinstance(v, int) or isinstance(v, bool) or not (2 <= v <= 5):
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.selectedSlotCount",
                                "error": "selectedSlotCount must be an integer between 2 and 5.",
                            }
                        )
                if "totalCatalogPrice" in meta:
                    v = meta["totalCatalogPrice"]
                    if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0.0:
                        field_errors.append(
                            {
                                "field": f"{prefix}.metadata.totalCatalogPrice",
                                "error": "totalCatalogPrice must be non-negative.",
                            }
                        )

        if field_errors:
            raise validation(field_errors)

        # 3. Product existence validation (fail closed with 404 for unknown products)
        if product_target_ids:
            existing_product_ids = self._repository.get_existing_product_ids(
                product_target_ids
            )
            missing_ids = product_target_ids - existing_product_ids
            if missing_ids:
                missing_id = sorted(list(missing_ids))[0]
                raise ApiError(
                    status_code=404,
                    code="NOT_FOUND",
                    message="The requested item was not found.",
                    details={"targetId": str(missing_id), "kind": "unknown_product"},
                )

        # 4. Prepare repository payloads with deterministic payload hash
        repo_payloads: list[dict[str, Any]] = []
        for ev in events:
            phash = compute_payload_hash(
                event_type=ev.eventType,
                target_type=ev.targetType,
                target_id=ev.targetId,
                surface=ev.surface,
                position=ev.position,
                metadata=ev.metadata or {},
            )
            occurred_at = (
                ev.occurredAt
                if ev.occurredAt.tzinfo is not None
                else ev.occurredAt.replace(tzinfo=timezone.utc)
            )
            repo_payloads.append(
                {
                    "client_event_id": ev.eventId,
                    "event_type": ev.eventType,
                    "target_type": ev.targetType,
                    "target_id": ev.targetId,
                    "product_id": (
                        UUID(ev.targetId) if ev.targetType == "product" else None
                    ),
                    "surface": ev.surface,
                    "position": ev.position,
                    "payload_hash": phash,
                    "metadata": ev.metadata or {},
                    "client_occurred_at": occurred_at,
                }
            )

        # 5. Persist batch atomically
        ack_tuples = self._repository.persist_events_batch(
            events=repo_payloads,
            user_id=user_id,
            guest_session_id=guest_session_id,
        )

        ack_schemas = [
            DiscoveryEventAckSchema(
                eventId=cid,
                status=st,
                replayed=rep,
            )
            for cid, st, rep in ack_tuples
        ]

        accepted_count = sum(
            1 for _, st, rep in ack_tuples if st == "accepted" and not rep
        )

        return DiscoveryEventsIngestResponse(
            acceptedCount=accepted_count,
            events=ack_schemas,
        )
