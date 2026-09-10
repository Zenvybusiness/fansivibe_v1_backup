"""Unit tests for the save use case (`SaveRecommendation`, UC-15).

No database — fake repositories. Covers the contract's save semantics
(FANSIVIBE_API_CONTRACT_V1.md §4, C-12/API-33): TRX-3 all-or-nothing
(saved look + `look_saved` signal), idempotency-key replay returns the
original save, a conflicting replay is a 409, ownership is enforced, and
unknown look ids/source contexts are typed errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.api.errors import ApiError
from app.application.saved_looks import ListSavedLooks, SaveRecommendation
from app.domain.ports.repositories import SavedLookRecord
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

USER = uuid4()
OTHER_USER = uuid4()


@dataclass
class FakeKnowledge:
    def __init__(self, has_look: bool = True) -> None:
        self._has_look = has_look
        self.lookups = 0

    def lookup_hairstyle_look(self, code: str):
        self.lookups += 1
        if not self._has_look:
            return None
        return object()

    def lookup_grooming_look(self, code: str):
        self.lookups += 1
        if not self._has_look:
            return None
        return object()


@dataclass
class FakeSavedLooks:
    """In-memory SavedLookRepository faithful to the protocol shape."""

    rows: list = field(default_factory=list)
    commits: int = 0
    rollbacks: int = 0
    insert_error: Optional[Exception] = None

    def insert(
        self,
        *,
        user_id: UUID,
        look_id: Optional[str],
        title: str,
        source_context: str,
        snapshot: dict,
        idempotency_key: str,
        source_run_id: Optional[UUID],
    ) -> SavedLookRecord:
        if self.insert_error is not None:
            raise self.insert_error
        record = SavedLookRecord(
            id=uuid4(),
            look_id=look_id,
            title=title,
            source_context=source_context,
            snapshot=snapshot,
            source_run_id=source_run_id,
            created_at=datetime.now(timezone.utc),
        )
        self.rows.append(
            {
                "user_id": user_id,
                "idempotency_key": idempotency_key,
                "record": record,
            }
        )
        return record

    def get_for_user(
        self, *, user_id: UUID, saved_look_id: UUID
    ) -> Optional[SavedLookRecord]:
        for row in self.rows:
            if row["user_id"] == user_id and row["record"].id == saved_look_id:
                return row["record"]
        return None

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[SavedLookRecord]:
        for row in self.rows:
            if (
                row["user_id"] == user_id
                and row["idempotency_key"] == idempotency_key
            ):
                return row["record"]
        return None

    def list_for_user(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[SavedLookRecord], int]:
        owned = [
            row["record"] for row in self.rows if row["user_id"] == user_id
        ]
        owned.sort(key=lambda r: r.created_at, reverse=True)
        start = (page - 1) * page_size
        return owned[start : start + page_size], len(owned)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@dataclass
class FakeSignals:
    signals: list = field(default_factory=list)
    commits: int = 0
    rollbacks: int = 0

    def insert_look_saved(
        self, *, user_id: UUID, signal_type: str = "look_saved", label: str, context: Optional[dict]
    ) -> None:
        self.signals.append({"user_id": user_id, "signal_type": signal_type, "label": label, "context": context})

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@dataclass
class FakeWardrobeItems:
    """In-memory WardrobeItemRepository double (owner-scoped, OW-1)."""

    rows: list = field(default_factory=list)  # (user_id, item_id)

    def add(self, user_id: UUID, item_id: UUID) -> None:
        self.rows.append((user_id, item_id))

    def get_by_id(self, *, user_id: UUID, item_id: UUID):
        for owner, owned_id in self.rows:
            if owner == user_id and owned_id == item_id:
                return object()
        return None


SNAPSHOT = {
    "appearance": {
        "faceShape": "Oval",
        "sourceRunId": "00000000-0000-0000-0000-000000000001",
    },
    "recommendations": {
        "top": {
            "id": "textured_quiff",
            "name": "Textured Quiff",
            "matchScore": 0.94,
            "description": "A modern take on the classic quiff.",
            "reasons": ["Oval face shapes benefit from volume on top"],
            "stylingTips": "Apply mousse.",
            "maintenance": "Medium",
            "bestFor": "Oval",
        },
        "alternatives": [],
    },
}


def _make(*, has_look: bool = True) -> tuple[SaveRecommendation, FakeSavedLooks, FakeSignals]:
    saved_looks = FakeSavedLooks()
    signals = FakeSignals()
    use_case = SaveRecommendation(
        saved_looks=saved_looks,
        signals=signals,
        knowledge=FakeKnowledge(has_look=has_look),
        wardrobe_items=FakeWardrobeItems(),
    )
    return use_case, saved_looks, signals


def _snapshot_without_source_run_id() -> dict:
    import copy

    snapshot = copy.deepcopy(SNAPSHOT)
    del snapshot["appearance"]["sourceRunId"]
    return snapshot


def test_save_inserts_look_and_signal_and_commits():
    use_case, saved_looks, signals = _make()
    saved, created = use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="key-1",
    )

    assert created is True
    assert saved.look_id == "textured_quiff"
    assert saved.title == "Textured Quiff"
    assert saved.source_context == "hairstyle"
    assert str(saved.source_run_id) == "00000000-0000-0000-0000-000000000001"
    assert saved_looks.commits == 1
    assert saved_looks.rollbacks == 0
    assert signals.signals == [
        {
            "user_id": USER,
            "signal_type": "look_saved",
            "label": "Textured Quiff",
            "context": {"source_context": "hairstyle", "look_id": "textured_quiff"},
        }
    ]


def test_idempotent_replay_returns_original_without_new_rows():
    use_case, saved_looks, signals = _make()
    use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="key-replay",
    )
    original = saved_looks.rows[0]["record"]

    replayed, created = use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="key-replay",
    )

    assert created is False
    assert replayed is original
    assert len(saved_looks.rows) == 1
    assert len(signals.signals) == 1
    assert saved_looks.commits == 1


def test_conflicting_replay_raises_conflict():
    use_case, saved_looks, signals = _make()
    use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="key-conflict",
    )

    with pytest.raises(ApiError) as excinfo:
        use_case(
            user_id=USER,
            look_id="textured_quiff",
            title="Different Title",
            snapshot=SNAPSHOT,
            source_context="hairstyle",
            idempotency_key="key-conflict",
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "CONFLICT"
    assert len(saved_looks.rows) == 1
    assert saved_looks.commits == 1


def test_idempotency_is_owner_scoped():
    use_case, saved_looks, _ = _make()
    use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="key-shared",
    )

    other, created = use_case(
        user_id=OTHER_USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="key-shared",
    )

    assert created is True
    assert other is not saved_looks.rows[0]["record"]
    assert len(saved_looks.rows) == 2


def test_unknown_look_id_raises_not_found():
    use_case, saved_looks, signals = _make(has_look=False)
    with pytest.raises(ApiError) as excinfo:
        use_case(
            user_id=USER,
            look_id="no_such_look",
            title="No Such Look",
            snapshot=SNAPSHOT,
            source_context="hairstyle",
            idempotency_key="key-x",
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "NOT_FOUND"
    assert len(saved_looks.rows) == 0
    assert len(signals.signals) == 0


def test_unknown_source_context_raises_validation():
    use_case, saved_looks, signals = _make()
    with pytest.raises(ApiError) as excinfo:
        use_case(
            user_id=USER,
            look_id="textured_quiff",
            title="Textured Quiff",
            snapshot=SNAPSHOT,
            source_context="wardrobe",
            idempotency_key="key-y",
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "VALIDATION_ERROR"
    assert excinfo.value.details["field_errors"][0]["field"] == "sourceContext"
    assert len(saved_looks.rows) == 0
    assert len(signals.signals) == 0


def test_look_id_may_be_none_without_catalog_lookup():
    use_case, saved_looks, _ = _make()
    saved = use_case(
        user_id=USER,
        look_id=None,
        title="Custom Look",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="key-none",
    )

    assert saved[0].look_id is None
    assert saved[1] is True


def test_insert_failure_rolls_back_and_raises_database_failure():
    use_case, saved_looks, signals = _make()
    saved_looks.insert_error = RuntimeError("boom")
    with pytest.raises(ApiError) as excinfo:
        use_case(
            user_id=USER,
            look_id="textured_quiff",
            title="Textured Quiff",
            snapshot=SNAPSHOT,
            source_context="hairstyle",
            idempotency_key="key-db",
        )

    assert excinfo.value.status_code == 500
    assert excinfo.value.code == "DATABASE_FAILURE"
    assert saved_looks.rollbacks == 1
    assert len(signals.signals) == 0


def test_knowledge_catalog_lookup_is_used_for_save():
    use_case, *_ = _make()
    knowledge = CatalogKnowledgeSource()
    use_case = SaveRecommendation(
        saved_looks=FakeSavedLooks(),
        signals=FakeSignals(),
        knowledge=knowledge,
        wardrobe_items=FakeWardrobeItems(),
    )
    saved = use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="key-catalog",
    )
    assert saved[0].look_id == "textured_quiff"


# --- ListSavedLooks (endpoint #24) -------------------------------------------


def _seed_looks(rows: list, user_id: UUID, count: int = 3) -> None:
    for i in range(count):
        record = SavedLookRecord(
            id=uuid4(),
            look_id=f"look-{i}",
            title=f"Look {i}",
            source_context="hairstyle",
            snapshot=SNAPSHOT,
            source_run_id=None,
            created_at=datetime.now(timezone.utc),
        )
        rows.append({"user_id": user_id, "idempotency_key": f"list-key-{i}", "record": record})


def test_list_returns_owned_rows_and_total():
    saved_looks = FakeSavedLooks()
    _seed_looks(saved_looks.rows, USER, count=3)
    _seed_looks(saved_looks.rows, OTHER_USER, count=2)

    use_case = ListSavedLooks(saved_looks=saved_looks)
    items, total = use_case(user_id=USER, page=1, page_size=20)

    assert total == 3
    assert [item.title for item in items] == ["Look 2", "Look 1", "Look 0"]


def test_list_respects_pagination():
    saved_looks = FakeSavedLooks()
    _seed_looks(saved_looks.rows, USER, count=5)

    use_case = ListSavedLooks(saved_looks=saved_looks)
    items, total = use_case(user_id=USER, page=2, page_size=2)

    assert total == 5
    assert len(items) == 2


def test_list_is_empty_for_owner_without_saves():
    saved_looks = FakeSavedLooks()

    use_case = ListSavedLooks(saved_looks=saved_looks)
    items, total = use_case(user_id=USER, page=1, page_size=20)

    assert items == []
    assert total == 0

# ============================================================================
# STEP 11.16 — outfit save contract: backend-owned source_context discriminator
# + validated/normalized snapshot.selectedItemIds for outfit saves.
# DB-free (fake repos). source_context is authoritative; look_id NULL, titles,
# and snapshot shape are never used as domain discriminators.
# ============================================================================

OUTFIT_SNAPSHOT = {
    "appearance": {
        "faceShape": "Oval",
    },
    "outfit": {"occasion": "date"},
}


def _make_with_wardrobe(*, owner_items=(), other_items=()):
    """SaveRecommendation with a wardrobe double: `owner_items` belong to
    USER, `other_items` belong to OTHER_USER."""
    saved_looks = FakeSavedLooks()
    signals = FakeSignals()
    wardrobe = FakeWardrobeItems()
    for item_id in owner_items:
        wardrobe.add(USER, item_id)
    for item_id in other_items:
        wardrobe.add(OTHER_USER, item_id)
    use_case = SaveRecommendation(
        saved_looks=saved_looks,
        signals=signals,
        knowledge=FakeKnowledge(has_look=False),
        wardrobe_items=wardrobe,
    )
    return use_case, saved_looks, signals


def _outfit_snapshot(item_ids=None):
    import copy

    snapshot = copy.deepcopy(OUTFIT_SNAPSHOT)
    if item_ids is not None:
        snapshot["selectedItemIds"] = item_ids
    return snapshot


# --- A: save context persistence --------------------------------------------


def test_11_16_hairstyle_context_persisted():
    use_case, saved_looks, _ = _make()
    saved, created = use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="ctx-hair",
    )
    assert created is True
    assert saved.source_context == "hairstyle"
    assert saved_looks.rows[0]["record"].source_context == "hairstyle"


def test_11_16_grooming_context_persisted_without_selected_item_ids():
    use_case, saved_looks, _ = _make()
    saved, created = use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Goatee",
        snapshot=dict(SNAPSHOT),
        source_context="grooming",
        idempotency_key="ctx-groom",
    )
    assert created is True
    assert saved.source_context == "grooming"
    assert "selectedItemIds" not in saved.snapshot


def test_11_16_outfit_context_persisted_with_null_look_id():
    use_case, saved_looks, _ = _make()
    saved, created = use_case(
        user_id=USER,
        look_id=None,
        title="Date Night Outfit",
        snapshot=_outfit_snapshot(),
        source_context="outfit",
        idempotency_key="ctx-outfit",
    )
    assert created is True
    assert saved.source_context == "outfit"
    assert saved.look_id is None


# --- C: valid owner item IDs accepted + normalized ---------------------------


def test_11_16_outfit_valid_item_ids_normalized_to_canonical_sorted():
    item_b = uuid4()
    item_a = uuid4()
    use_case, saved_looks, _ = _make_with_wardrobe(owner_items=(item_a, item_b))
    saved, created = use_case(
        user_id=USER,
        look_id=None,
        title="Outfit",
        snapshot=_outfit_snapshot([str(item_b), str(item_a).upper()]),
        source_context="outfit",
        idempotency_key="ctx-norm",
    )
    assert created is True
    assert saved.snapshot["selectedItemIds"] == sorted([str(item_a), str(item_b)])
    # Unrelated snapshot fields are untouched.
    assert saved.snapshot["outfit"] == {"occasion": "date"}
    assert saved.snapshot["appearance"] == {"faceShape": "Oval"}


# --- D: duplicates ------------------------------------------------------------


def test_11_16_outfit_duplicate_ids_become_one_canonical_id():
    item = uuid4()
    use_case, _, _ = _make_with_wardrobe(owner_items=(item,))
    saved, _ = use_case(
        user_id=USER,
        look_id=None,
        title="Outfit",
        snapshot=_outfit_snapshot([str(item), str(item).upper(), str(item)]),
        source_context="outfit",
        idempotency_key="ctx-dupe",
    )
    assert saved.snapshot["selectedItemIds"] == [str(item)]


# --- E/F/K: foreign + unknown IDs rejected, atomically ------------------------


def test_11_16_outfit_foreign_item_id_rejected_without_rows_or_signal():
    mine = uuid4()
    theirs = uuid4()
    use_case, saved_looks, signals = _make_with_wardrobe(
        owner_items=(mine,), other_items=(theirs,)
    )
    with pytest.raises(ApiError) as excinfo:
        use_case(
            user_id=USER,
            look_id=None,
            title="Outfit",
            snapshot=_outfit_snapshot([str(mine), str(theirs)]),
            source_context="outfit",
            idempotency_key="ctx-foreign",
        )
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "NOT_FOUND"
    assert len(saved_looks.rows) == 0
    assert len(signals.signals) == 0
    assert saved_looks.commits == 0


def test_11_16_outfit_unknown_item_id_rejected_without_rows_or_signal():
    use_case, saved_looks, signals = _make_with_wardrobe()
    with pytest.raises(ApiError) as excinfo:
        use_case(
            user_id=USER,
            look_id=None,
            title="Outfit",
            snapshot=_outfit_snapshot([str(uuid4())]),
            source_context="outfit",
            idempotency_key="ctx-unknown",
        )
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "NOT_FOUND"
    assert len(saved_looks.rows) == 0
    assert len(signals.signals) == 0


# --- G: malformed selectedItemIds rejected ------------------------------------


@pytest.mark.parametrize(
    "bad_ids",
    [
        "not-a-list",
        {"id": "x"},
        ["not-a-uuid"],
        [123],
        [None],
    ],
)
def test_11_16_outfit_malformed_selected_item_ids_rejected(bad_ids):
    use_case, saved_looks, signals = _make_with_wardrobe()
    snapshot = _outfit_snapshot()
    snapshot["selectedItemIds"] = bad_ids
    with pytest.raises(ApiError) as excinfo:
        use_case(
            user_id=USER,
            look_id=None,
            title="Outfit",
            snapshot=snapshot,
            source_context="outfit",
            idempotency_key=f"ctx-bad-{len(saved_looks.rows)}",
        )
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "VALIDATION_ERROR"
    assert len(saved_looks.rows) == 0
    assert len(signals.signals) == 0


# --- H: hairstyle/grooming compatibility --------------------------------------


def test_11_16_hairstyle_snapshot_without_selected_item_ids_untouched():
    use_case, _, _ = _make()
    saved, _ = use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=dict(SNAPSHOT),
        source_context="hairstyle",
        idempotency_key="ctx-compat",
    )
    assert saved.snapshot == SNAPSHOT


# --- J: idempotency with source_context ---------------------------------------


def test_11_16_same_key_changed_context_returns_conflict():
    use_case, saved_looks, signals = _make()
    use_case(
        user_id=USER,
        look_id="textured_quiff",
        title="Textured Quiff",
        snapshot=SNAPSHOT,
        source_context="hairstyle",
        idempotency_key="ctx-change",
    )
    with pytest.raises(ApiError) as excinfo:
        use_case(
            user_id=USER,
            look_id="textured_quiff",
            title="Textured Quiff",
            snapshot=SNAPSHOT,
            source_context="grooming",
            idempotency_key="ctx-change",
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "CONFLICT"
    assert len(saved_looks.rows) == 1
    assert len(signals.signals) == 1


# --- L: outfit save still emits exactly one intact look_saved signal ---------


def test_11_16_outfit_save_emits_single_intact_look_saved_signal():
    item = uuid4()
    use_case, saved_looks, signals = _make_with_wardrobe(owner_items=(item,))
    use_case(
        user_id=USER,
        look_id=None,
        title="Date Night Outfit",
        snapshot=_outfit_snapshot([str(item)]),
        source_context="outfit",
        idempotency_key="ctx-signal",
    )
    assert saved_looks.commits == 1
    assert signals.signals == [
        {
            "user_id": USER,
            "signal_type": "look_saved",
            "label": "Date Night Outfit",
            "context": {"source_context": "outfit", "look_id": None},
        }
    ]


def test_11_16_outfit_byte_identical_replay_returns_original():
    """J (outfit). Replay of the exact bytes returns the original row even
    though the persisted snapshot is the canonical normalized form."""
    item = uuid4()
    use_case, saved_looks, signals = _make_with_wardrobe(owner_items=(item,))
    payload = _outfit_snapshot([str(item).upper(), str(item)])
    first, created = use_case(
        user_id=USER,
        look_id=None,
        title="Outfit",
        snapshot=payload,
        source_context="outfit",
        idempotency_key="ctx-replay",
    )
    assert created is True
    replayed, created = use_case(
        user_id=USER,
        look_id=None,
        title="Outfit",
        snapshot=payload,
        source_context="outfit",
        idempotency_key="ctx-replay",
    )
    assert created is False
    assert replayed is first
    assert len(saved_looks.rows) == 1
    assert len(signals.signals) == 1
