"""C-07 item_added implementation tests (Option A, owner-locked).

One history row per successful server-side wardrobe create, post-commit
(TRX-7 style), via the existing signal writer. No recommendation effect.
DB-free except the PG-gated seed/downgrade proofs (skip without PG).
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.application.wardrobe import AddWardrobeItem, UpdateWardrobeItem
from app.domain.ports.repositories import WardrobeItemRecord

USER = uuid4()


def _record():
    return WardrobeItemRecord(
        id=uuid4(), user_id=USER, name="Shirt", category="tops",
        color="black", material=None, is_favorite=False, image_ref=None,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


class _FakeWardrobe:
    def __init__(self, *, fail_create=False) -> None:
        self.fail_create = fail_create
        self.commits = 0
        self.rollbacks = 0
        self.row = _record()

    def create(self, **kwargs):
        if self.fail_create:
            raise IntegrityError("INSERT", {}, Exception("boom"))
        return self.row

    def update(self, **kwargs):
        return self.row

    def get_by_id(self, *, user_id, item_id):
        return self.row

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeSignals:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.commits = 0
        self.rollbacks = 0

    def insert_look_saved(self, *, user_id, signal_type="look_saved", label, context):
        self.rows.append(
            {"user_id": user_id, "signal_type": signal_type, "label": label, "context": context}
        )

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _add(wardrobe, signals, **over):
    args = dict(
        user_id=USER, name="Shirt", category="tops", color="black",
        material=None, isFavorite=False,
    )
    args.update(over)
    return AddWardrobeItem(wardrobe=wardrobe, signals=signals)(**args)


# A. Successful server create produces exactly one item_added row.
def test_successful_create_emits_single_item_added():
    wardrobe, signals = _FakeWardrobe(), _FakeSignals()
    record = _add(wardrobe, signals)
    assert record is wardrobe.row
    assert wardrobe.commits == 1
    assert len(signals.rows) == 1
    row = signals.rows[0]
    assert row["signal_type"] == "item_added"
    assert row["label"] == "Shirt"
    assert row["context"] == {"wardrobe_item_id": str(wardrobe.row.id)}
    assert row["user_id"] == USER
    assert signals.commits == 1


# B/C. Failed create (DB error, validation) produces no signal.
def test_failed_create_emits_no_signal():
    wardrobe, signals = _FakeWardrobe(fail_create=True), _FakeSignals()
    with pytest.raises(IntegrityError):
        _add(wardrobe, signals)
    assert signals.rows == []
    assert signals.commits == 0


def test_validation_failure_emits_no_signal():
    from app.api.errors import ApiError

    wardrobe, signals = _FakeWardrobe(), _FakeSignals()
    with pytest.raises(ApiError):
        _add(wardrobe, signals, name="")
    assert signals.rows == []
    assert wardrobe.commits == 0


# C (local/guest): the server use case is never constructed for local
# objects (Flutter-side `local-*` path); signals=None preserves exact
# pre-C-07 behavior with no ledger touch.
def test_no_signals_repo_means_no_ledger_touch():
    wardrobe = _FakeWardrobe()
    record = AddWardrobeItem(wardrobe=wardrobe)(  # signals defaults None
        user_id=USER, name="Shirt", category="tops", color="black",
        material=None, isFavorite=False,
    )
    assert record is wardrobe.row
    assert wardrobe.commits == 1


# D. Edits never emit item_added (UpdateWardrobeItem takes no signals).
def test_update_path_has_no_signal_surface():
    params = inspect.signature(UpdateWardrobeItem.__init__).parameters
    assert set(params) == {"self", "wardrobe"}


# E. Retry/duplicate behavior follows the existing append-only writer:
# one call → exactly one row; each successful create is its own event.
def test_each_successful_create_is_its_own_event():
    wardrobe, signals = _FakeWardrobe(), _FakeSignals()
    _add(wardrobe, signals)
    assert len(signals.rows) == 1
    _add(wardrobe, signals, name="Second")
    assert len(signals.rows) == 2
    assert [r["signal_type"] for r in signals.rows] == ["item_added", "item_added"]
    assert [r["label"] for r in signals.rows] == ["Shirt", "Second"]


# H. Existing signal contract untouched (default type still look_saved).
def test_existing_signal_writer_contract_unchanged():
    from app.domain.ports.repositories import LearningSignalRepository

    params = inspect.signature(LearningSignalRepository.insert_look_saved).parameters
    assert params["signal_type"].default == "look_saved"


# I. No scoring surface gained a signal/item_added input.
def test_scoring_signatures_have_no_item_added_input():
    from app.domain.services import analysis_rules

    for fn in (
        analysis_rules.score_outfit_candidate,
        analysis_rules.preference_contribution,
        analysis_rules.candidate_preference_points,
        analysis_rules.compose_candidate_score,
    ):
        assert "item_added" not in inspect.signature(fn).parameters
        assert "signal" not in inspect.signature(fn).parameters


# F/G (PG). Seed present at head; downgrade removes only its own seed.
def test_0024_revision_chain_and_static_contract():
    """0024 exists, child of 0023 (single linear head extension)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(config)
    assert tuple(script.get_heads()) == ("0025",)
    rev25 = script.get_revision("0025")
    assert rev25 is not None
    assert rev25.down_revision == "0024"
    rev = script.get_revision("0024")
    assert rev is not None
    assert rev.down_revision == "0023"


def test_item_added_seed_and_downgrade_round_trip(db):
    """PG: head seeds item_added; downgrade to 0023 removes only it."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.attributes["configure_logger"] = False

    def codes(session):
        return sorted(
            r[0]
            for r in session.execute(text("SELECT code FROM signal_types")).all()
        )

    Session = db
    with Session() as session:
        assert "item_added" in codes(session)
    command.downgrade(config, "0023")
    with Session() as session:
        remaining = codes(session)
        assert "item_added" not in remaining
        assert remaining == [
            "analysis_updated",
            "assistant_navigation",
            "look_saved",
            "outfit_selected",
            "suggestion_opened",
        ]
    command.upgrade(config, "head")
    with Session() as session:
        assert "item_added" in codes(session)
