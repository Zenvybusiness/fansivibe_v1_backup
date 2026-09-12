"""Application use cases — event calendar CRUD (M8-B, UC-18/UC-19/UC-20).

Create (`CreateEvent`, endpoint #26) is TRX-7 tier-1: exactly one
`user_events` INSERT committed first, then the R36 occasion-preference
feed follows as a sequential second unit (DEC-015 overrules the
DAILY §5.4 "same transaction" phrase). If the preference write fails,
the event 201 stands — a 500-after-commit would induce F-8 duplicates,
the worse outcome. No learning signal is ever written here (no backend
`occasion_preferred` code exists).

Update (`UpdateEvent`, endpoint #28) is one UPDATE unit with the same
sequential R36 rule, applied only when the event type changed (the old
preference is retained, never removed — add-only lifecycle). Delete
(`DeleteEvent`, endpoint #29) is one DELETE with no R36 and no signal;
preferences and history are untouched (BC-41). List (`ListEvents`,
endpoint #27) is the owner-scoped upcoming-window read.

Business rules live here, not in the routers (BA-7). Past-date checks
use the server-UTC calendar date; wall-clock `HH:mm` carries no
timezone and is never converted. Stored text is never trimmed or
normalized — the DB CHECKs are the final safety layer.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from typing import Optional
from uuid import UUID

from app.api.errors import ApiError, database_failure, not_found, validation
from app.domain.ports.repositories import (
    EventOutfitComponent,
    EventOutfitRecommendation,
    EventTypeRepository,
    UserEventRecord,
    UserEventRepository,
    UserStateRepository,
    WardrobeItemRepository,
)
from app.domain.services.analysis_rules import (
    generate_outfit_candidates,
    rank_outfit_candidates,
    score_outfit_candidate,
    select_best_outfit_candidate,
)

_TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

_SORT_KEYS = ("event_date",)
_ORDERS = ("asc", "desc")


def _utc_today() -> date:
    """Server-UTC calendar date (past-date datum for event writes)."""
    return datetime.now(timezone.utc).date()


def _field_error(field: str, error: str, allowed: Optional[list[str]] = None) -> ApiError:
    details: dict = {"field_errors": [{"field": field, "error": error}]}
    if allowed is not None:
        details["field_errors"][0]["allowed"] = allowed
    return ApiError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Some of the provided values are not valid. Please check your input.",
        details=details,
    )


def _validate_title(title: object) -> str:
    if not isinstance(title, str) or not (1 <= len(title) <= 200):
        raise _field_error("title", "must be between 1 and 200 characters")
    return title


def _validate_event_type(*, event_types: EventTypeRepository, event_type: object) -> str:
    active = event_types.list_active()
    allowed = sorted(record.code for record in active)
    if not isinstance(event_type, str) or event_types.get_by_code(code=event_type) is None:
        raise _field_error("eventType", "unknown event type", allowed)
    return event_type


def _validate_event_date(event_date: object) -> date:
    if not isinstance(event_date, date):
        raise _field_error("eventDate", "must be an ISO date (YYYY-MM-DD)")
    if event_date < _utc_today():
        raise _field_error("eventDate", "must not be in the past")
    return event_date


def _validate_time(event_time: object) -> Optional[time]:
    if event_time is None:
        return None
    if not isinstance(event_time, str) or not _TIME_RE.match(event_time):
        raise _field_error("time", "must be strict HH:mm (e.g. 19:00)")
    hour, minute = event_time.split(":")
    return time(int(hour), int(minute))


def _validate_optional_text(field: str, value: object, *, limit: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not (1 <= len(value) <= limit):
        raise _field_error(field, f"must be between 1 and {limit} characters")
    return value


def _append_preferred_occasion(
    *, user_state: UserStateRepository, user_id: UUID, code: str
) -> None:
    """Best-effort R36 feed: append `code` to preferredOccasions if absent.

    Sequential second unit (DEC-015): the caller's event write is
    already committed before this runs. Existing values are preserved;
    a present code is a no-op. NEVER raises — any failure leaves the
    committed event standing (F-8 duplicate avoidance).
    """
    try:
        profile = user_state.get_profile(user_id=user_id)
        raw = profile.preferences.get("preferred_occasions") if profile is not None else None
        current = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
        if code in current:
            return
        user_state.update_preferences(
            user_id=user_id,
            preferences={"preferred_occasions": [*current, code]},
        )
    except Exception:
        return


class CreateEvent:
    """Create one owned event (endpoint #26 `POST /v1/events`, UC-18).

    Exactly one INSERT unit, committed first; R36 follows sequentially.
    Retries create separate rows (no key, F-8). No learning signal.
    """

    def __init__(
        self,
        *,
        events: UserEventRepository,
        event_types: EventTypeRepository,
        user_state: UserStateRepository,
    ) -> None:
        self._events = events
        self._event_types = event_types
        self._user_state = user_state

    def __call__(
        self,
        *,
        user_id: UUID,
        title: object,
        event_type: object,
        event_date: object,
        event_time: object = None,
        location: object = None,
        notes: object = None,
    ) -> UserEventRecord:
        title = _validate_title(title)
        event_type = _validate_event_type(event_types=self._event_types, event_type=event_type)
        event_date = _validate_event_date(event_date)
        parsed_time = _validate_time(event_time)
        location = _validate_optional_text("location", location, limit=200)
        notes = _validate_optional_text("notes", notes, limit=2000)
        try:
            record = self._events.create(
                user_id=user_id,
                title=title,
                event_type=event_type,
                event_date=event_date,
                event_time=parsed_time,
                location=location,
                notes=notes,
            )
            self._events.commit()
        except Exception:
            try:
                self._events.rollback()
            except Exception:
                pass
            raise database_failure()
        _append_preferred_occasion(
            user_state=self._user_state, user_id=user_id, code=event_type
        )
        return record


class ListEvents:
    """List the owner's events (endpoint #27 `GET /v1/events`).

    Upcoming window by default: absent `from` resolves to server-UTC
    today, `sort` accepts only `event_date`, default order is `asc`
    (soonest-first). Owner scoping is enforced by the repository (OW-1).
    """

    def __init__(self, *, events: UserEventRepository) -> None:
        self._events = events

    def __call__(
        self,
        *,
        user_id: UUID,
        from_date: Optional[date] = None,
        sort: str = "event_date",
        order: str = "asc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[UserEventRecord], int]:
        if sort not in _SORT_KEYS:
            raise _field_error("sort", "unknown sort key", list(_SORT_KEYS))
        if order not in _ORDERS:
            raise _field_error("order", "must be asc or desc", list(_ORDERS))
        if page < 1:
            raise _field_error("page", "must be at least 1")
        if not 1 <= page_size <= 100:
            raise _field_error("page_size", "must be between 1 and 100")
        return self._events.list_for_user(
            user_id=user_id,
            from_date=from_date if from_date is not None else _utc_today(),
            order=order,
            page=page,
            page_size=page_size,
        )


class UpdateEvent:
    """Full-replace one owned event (endpoint #28, UC-19).

    One UPDATE unit, committed first; R36 appends the NEW type code only
    when the type changed (old preference retained). A failed feed never
    rolls back the committed update. No learning signal.
    """

    def __init__(
        self,
        *,
        events: UserEventRepository,
        event_types: EventTypeRepository,
        user_state: UserStateRepository,
    ) -> None:
        self._events = events
        self._event_types = event_types
        self._user_state = user_state

    def __call__(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        title: object,
        event_type: object,
        event_date: object,
        event_time: object = None,
        location: object = None,
        notes: object = None,
    ) -> UserEventRecord:
        existing = self._events.get_for_user(user_id=user_id, event_id=event_id)
        if existing is None:
            raise not_found()
        title = _validate_title(title)
        event_type = _validate_event_type(event_types=self._event_types, event_type=event_type)
        event_date = _validate_event_date(event_date)
        parsed_time = _validate_time(event_time)
        location = _validate_optional_text("location", location, limit=200)
        notes = _validate_optional_text("notes", notes, limit=2000)
        try:
            updated = self._events.update(
                user_id=user_id,
                event_id=event_id,
                title=title,
                event_type=event_type,
                event_date=event_date,
                event_time=parsed_time,
                location=location,
                notes=notes,
            )
            self._events.commit()
        except Exception:
            try:
                self._events.rollback()
            except Exception:
                pass
            raise database_failure()
        if updated is None:  # pragma: no cover — defensive; row existed above.
            raise not_found()
        if event_type != existing.event_type:
            _append_preferred_occasion(
                user_state=self._user_state, user_id=user_id, code=event_type
            )
        return updated


class DeleteEvent:
    """Delete one owned event (endpoint #29 `DELETE`, UC-20).

    Physical row delete, single commit. Preferences and history are
    untouched (BC-41); no learning signal is written.
    """

    def __init__(self, *, events: UserEventRepository) -> None:
        self._events = events

    def __call__(self, *, user_id: UUID, event_id: UUID) -> None:
        if self._events.get_for_user(user_id=user_id, event_id=event_id) is None:
            raise not_found()
        self._events.delete(user_id=user_id, event_id=event_id)
        self._events.commit()


# Canonical ensemble slot order for component rendering (tops first).
_OUTFIT_SLOT_ORDER = ("tops", "bottoms", "outerwear", "footwear", "accessories")

_SLOT_ATTRS = {
    "tops": "top_ids",
    "bottoms": "bottom_ids",
    "outerwear": "outerwear_ids",
    "footwear": "footwear_ids",
    "accessories": "accessory_ids",
}


class GenerateEventOutfit:
    """Derive one outfit for an owned event (endpoint #30, UC-21, M8-C).

    READ/DERIVE only: no INSERT/UPDATE/DELETE anywhere (no save, no
    signal, no wear row, no preference write, no event/wardrobe
    mutation — and no commit call at all). Reuses the canonical
    generate → score → rank → select pipeline unmodified (no second
    engine, no second scoring); the event TYPE CODE seeds the scoring
    occasions as highest priority, composed with the persisted
    preferred occasions deduped (DEC-018/M9 precedent). Past events
    generate freely (no date gate — DEC-015).

    Returns the honest `EventOutfitRecommendation` subset, or `None`
    when the owner has no legal candidate (empty/sparse wardrobe) —
    the router maps `None` to 204 (sibling #41 precedent: empty derived
    results are not errors; a 404 would lie about the event and a 503
    would lie about availability — the rules engine has no external
    dependency, so 503 is never emitted here).
    """

    def __init__(
        self,
        *,
        events: UserEventRepository,
        event_types: EventTypeRepository,
        wardrobe_items: WardrobeItemRepository,
        user_state: UserStateRepository,
    ) -> None:
        self._events = events
        self._event_types = event_types
        self._wardrobe_items = wardrobe_items
        self._user_state = user_state

    def __call__(self, *, user_id: UUID, event_id: UUID) -> Optional[EventOutfitRecommendation]:
        event = self._events.get_for_user(user_id=user_id, event_id=event_id)
        if event is None:
            raise not_found()
        code = event.event_type

        wardrobe = self._load_owner_wardrobe(user_id=user_id)
        if not wardrobe:
            return None

        occasions = [code]
        occasions.extend(
            item
            for item in self._preferred_occasions(user_id=user_id)
            if isinstance(item, str) and item != code
        )
        adapted = [
            SimpleNamespace(
                id=str(record.id),
                category=record.category,
                color=record.color,
                material=record.material,
                is_favorite=record.is_favorite,
            )
            for record in wardrobe
        ]
        items_by_id = {item.id: item for item in adapted}
        ranked = rank_outfit_candidates(
            [
                score_outfit_candidate(candidate, items_by_id, frozenset(), occasions)
                for candidate in generate_outfit_candidates(adapted)
            ]
        )
        winner = select_best_outfit_candidate(ranked)
        if winner is None:
            return None
        by_record = {str(record.id): record for record in wardrobe}
        return self._to_recommendation(
            code=code, winner=winner, by_record=by_record
        )

    def _load_owner_wardrobe(self, *, user_id: UUID) -> list:
        """All of the owner's wardrobe items (owner-scoped pages of 100)."""
        items: list = []
        page = 1
        while True:
            batch, total = self._wardrobe_items.get_for_user(
                user_id=user_id, page=page, page_size=100
            )
            items.extend(batch)
            if len(items) >= total or not batch:
                return items
            page += 1

    def _preferred_occasions(self, *, user_id: UUID) -> list:
        """Persisted occasion codes for scoring context (read-only)."""
        try:
            profile = self._user_state.get_profile(user_id=user_id)
        except Exception:
            return []
        if profile is None:
            return []
        raw = profile.preferences.get("preferred_occasions")
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, str)]

    def _to_recommendation(self, *, code: str, winner, by_record: dict) -> EventOutfitRecommendation:
        type_row = self._event_types.get_by_code(code=code)
        label = type_row.label if type_row is not None else code
        # Winner score is the 0–100 budget composition (70+15+15); the
        # ensemble wire scale is 0..1 (REC_API §4.4, mock 0.91, DEC-015).
        # Linear rescale — order-preserving, bounds-preserving, the only
        # mapping both frozen scales admit. Engine already rounds to 2dp.
        match_score = round(winner.score / 100, 4)
        components: list[EventOutfitComponent] = []
        covered: list[str] = []
        for category in _OUTFIT_SLOT_ORDER:
            for item_id in getattr(winner, _SLOT_ATTRS[category], ()):
                record = by_record.get(item_id)
                if record is None:  # pragma: no cover — defensive; IDs are owned.
                    continue
                components.append(
                    EventOutfitComponent(
                        id=str(record.id),
                        name=record.name,
                        category=category,
                        color=record.color,
                        material=record.material,
                        reason=f"Chosen {category} piece for your {label} outfit",
                    )
                )
            if getattr(winner, _SLOT_ATTRS[category], ()):
                covered.append(category)
        count = len(covered)
        reasons = [
            f"Picked for a {label} occasion",
            f"Covers {count} categor{'y' if count == 1 else 'ies'}: "
            + ", ".join(covered),
        ]
        for component in components:
            record = by_record.get(component.id)
            if record is not None and record.is_favorite:
                reasons.append(f"Includes your favorite {record.name}")
        return EventOutfitRecommendation(
            title=f"{label} Outfit",
            match_score=match_score,
            components=components,
            reasons=reasons,
            selected_occasion=code,
        )
