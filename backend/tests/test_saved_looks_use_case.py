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
        self, *, user_id: UUID, label: str, context: Optional[dict]
    ) -> None:
        self.signals.append({"user_id": user_id, "label": label, "context": context})

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


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
    assert str(saved.source_run_id) == "00000000-0000-0000-0000-000000000001"
    assert saved_looks.commits == 1
    assert saved_looks.rollbacks == 0
    assert signals.signals == [
        {
            "user_id": USER,
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