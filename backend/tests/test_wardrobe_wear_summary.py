"""Read-only wear-intelligence tests (STEP 15.6).

`GetWearSummary` computes grounded statistics from flat
`wardrobe_wear_events` ONLY — favorites, saved looks, recommendations, and
created/updated timestamps are never evidence. Writes go through the real
`POST /v1/wardrobe/wears` contract (canonicalization, UTC, ledger), reads
through `WearEventRepositorySQL.get_wear_summary` + `GetWearSummary`.

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.application.wardrobe import GetWearSummary
from app.infrastructure.db.models import (
    Colors,
    Materials,
    Users,
    UserState,
    WardrobeCategories,
    WardrobeItems,
)
from app.infrastructure.db.repositories import WearEventRepositorySQL

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}

_T1 = "2024-01-10T12:00:00Z"
_T2 = "2024-01-20T12:00:00Z"
_T3 = "2024-01-25T12:00:00Z"


def _utc(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


@pytest.fixture
def dev_user_id(db):
    """Get or create the dev user ID (mirrors test_wardrobe_wears_api.py)."""
    Session = db
    with Session() as session:
        user = session.execute(
            select(Users).where(
                Users.auth_provider == "dev", Users.auth_subject == "dev-user"
            )
        ).scalar_one_or_none()
        if user is None:
            user = Users(
                auth_provider="dev", auth_subject="dev-user", display_name="Dev User"
            )
            session.add(user)
            session.flush()
            session.add(UserState(user_id=user.id))
            session.commit()
        return user.id


def _seed_vocab(db):
    Session = db
    with Session() as session:
        for code, label in (
            ("tops", "Tops"),
            ("bottoms", "Bottoms"),
            ("outerwear", "Outerwear"),
            ("footwear", "Footwear"),
            ("accessories", "Accessories"),
        ):
            if session.get(WardrobeCategories, code) is None:
                session.add(
                    WardrobeCategories(code=code, label=label, sort_order=1, active=True)
                )
        for code, label in (("charcoal", "Charcoal"), ("white", "White")):
            if session.get(Colors, code) is None:
                session.add(Colors(code=code, label=label, sort_order=1, active=True))
        for code, label in (("wool", "Wool"), ("cotton", "Cotton")):
            if session.get(Materials, code) is None:
                session.add(
                    Materials(code=code, label=label, sort_order=1, active=True)
                )
        session.commit()


def _seed_item(db, user_id, **kwargs):
    defaults = dict(
        name="Merino Crew Neck",
        category="tops",
        color="charcoal",
        material="wool",
        isFavorite=False,
    )
    defaults.update(kwargs)
    Session = db
    with Session() as session:
        item = WardrobeItems(
            user_id=user_id,
            name=defaults["name"],
            category_id=defaults["category"],
            color_id=defaults["color"],
            material_id=defaults.get("material"),
            is_favorite=defaults["isFavorite"],
            image_ref=None,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item


def _make_other_user(db):
    """A second owner (unique subject per call; the dev seam stays dev)."""
    Session = db
    with Session() as session:
        other = Users(
            auth_provider="dev",
            auth_subject=f"other-user-{uuid4().hex}",
            display_name="Other",
        )
        session.add(other)
        session.flush()
        session.add(UserState(user_id=other.id))
        session.commit()
        session.refresh(other)
        return other.id


def _post(item_ids, key, worn_at=None):
    body = {"itemIds": item_ids}
    if worn_at is not None:
        body["wornAt"] = worn_at
    return client.post(
        "/v1/wardrobe/wears", json=body, headers={**HEADERS, "Idempotency-Key": key}
    )


def _summary(db, user_id, now=None):
    Session = db
    with Session() as session:
        return GetWearSummary(wears=WearEventRepositorySQL(session))(
            user_id=user_id, now=now
        )


def _assert_invariants(summary):
    assert summary.total_wears == sum(summary.wear_counts.values())
    assert summary.total_wears == sum(summary.wears_by_category.values())


# --- owner isolation --------------------------------------------------------


def test_owner_isolation(db, dev_user_id):
    """Another owner's events never leak into this owner's summary."""
    from app.application.wardrobe import LogWearEvents
    from app.infrastructure.db.repositories import (
        WardrobeItemRepositorySQL,
        WearGroupRepositorySQL,
    )

    _seed_vocab(db)
    mine = _seed_item(db, dev_user_id, name="Mine")
    other_id = _make_other_user(db)
    theirs = _seed_item(db, other_id, name="Theirs", category="bottoms")
    Session = db
    with Session() as session:
        LogWearEvents(
            wardrobe=WardrobeItemRepositorySQL(session),
            wears=WearEventRepositorySQL(session),
            groups=WearGroupRepositorySQL(session),
        )(
            user_id=other_id,
            item_ids=[theirs.id],
            worn_at=_utc(2024, 1, 15),
            idempotency_key="summary-isolation-1",
        )
    own = _summary(db, dev_user_id)
    assert own.total_wears == 0
    assert own.wear_counts == {str(mine.id): 0}
    assert own.unworn_item_ids == [str(mine.id)]
    assert own.recently_worn_item_ids == []
    stranger = _summary(db, other_id)
    assert stranger.total_wears == 1
    assert stranger.wear_counts == {str(theirs.id): 1}
    _assert_invariants(own)
    _assert_invariants(stranger)


# --- counts / last-worn -----------------------------------------------------


def test_total_and_per_item_counts(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    assert _post([str(item_a.id)], "summary-count-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "summary-count-2", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "summary-count-3", worn_at=_T1).status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.total_wears == 3
    assert summary.wear_counts == {str(item_a.id): 2, str(item_b.id): 1}
    _assert_invariants(summary)


def test_last_worn_is_the_maximum_instant(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    assert _post([str(item.id)], "summary-last-1", worn_at=_T2).status_code == 201
    assert _post([str(item.id)], "summary-last-2", worn_at=_T1).status_code == 201
    assert _post([str(item.id)], "summary-last-3", worn_at=_T3).status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.last_worn == {str(item.id): _utc(2024, 1, 25, 12)}
    assert summary.wear_counts == {str(item.id): 3}


def test_multiple_same_day_events_count_separately(db, dev_user_id):
    """Three logs sharing one `wornAt` are three wears, not one."""
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    for index in range(3):
        resp = _post([str(item.id)], f"summary-sameday-{index}", worn_at=_T1)
        assert resp.status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.total_wears == 3
    assert summary.wear_counts == {str(item.id): 3}
    assert summary.last_worn == {str(item.id): _utc(2024, 1, 10, 12)}
    _assert_invariants(summary)


def test_multi_item_wear_group_counts_once_per_item(db, dev_user_id):
    """One two-item action is one wear for EACH item row."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    resp = _post([str(item_a.id), str(item_b.id)], "summary-group-1", worn_at=_T1)
    assert resp.status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.total_wears == 2
    assert summary.wear_counts == {str(item_a.id): 1, str(item_b.id): 1}
    assert summary.wears_by_category == {"bottoms": 1, "tops": 1}
    _assert_invariants(summary)


# --- most / least / unworn --------------------------------------------------


def test_most_worn_tie_orders_by_recency_then_id(db, dev_user_id):
    """Tied counts break by last-worn desc, then item id asc; count beats recency."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee A")
    item_b = _seed_item(db, dev_user_id, name="Tee B")
    item_c = _seed_item(db, dev_user_id, name="Fresh", category="bottoms")
    # A and B tie at 2 with the SAME last instant → id order decides.
    assert _post([str(item_a.id)], "summary-tie-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "summary-tie-2", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "summary-tie-3", worn_at=_T1).status_code == 201
    assert _post([str(item_b.id)], "summary-tie-4", worn_at=_T2).status_code == 201
    # C is the most recently worn but has fewer wears — never most-worn.
    assert _post([str(item_c.id)], "summary-tie-5", worn_at=_T3).status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.most_worn_item_ids == sorted([str(item_a.id), str(item_b.id)])
    _assert_invariants(summary)


def test_most_worn_prefers_more_recent_on_tie(db, dev_user_id):
    """Equal counts with different last instants → more recent first."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee A")
    item_b = _seed_item(db, dev_user_id, name="Tee B")
    assert _post([str(item_a.id)], "summary-recency-1", worn_at=_T1).status_code == 201
    assert _post([str(item_b.id)], "summary-recency-2", worn_at=_T2).status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.most_worn_item_ids == [str(item_b.id), str(item_a.id)]


def test_least_worn_includes_unworn(db, dev_user_id):
    """Global minimum wins: a never-worn item is the least worn."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Workhorse")
    item_b = _seed_item(db, dev_user_id, name="Occasional")
    item_c = _seed_item(db, dev_user_id, name="Pristine")
    assert _post([str(item_a.id)], "summary-least-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "summary-least-2", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "summary-least-3", worn_at=_T1).status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.unworn_item_ids == [str(item_c.id)]
    assert summary.least_worn_item_ids == [str(item_c.id)]
    _assert_invariants(summary)


def test_least_worn_tie_orders_by_earliest_then_id(db, dev_user_id):
    """All-worn minimum group orders by last-worn asc, then item id asc."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Workhorse")
    item_b = _seed_item(db, dev_user_id, name="Early")
    item_c = _seed_item(db, dev_user_id, name="Late")
    assert _post([str(item_a.id)], "summary-leasttie-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "summary-leasttie-2", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "summary-leasttie-3", worn_at=_T1).status_code == 201
    assert _post([str(item_c.id)], "summary-leasttie-4", worn_at=_T3).status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.unworn_item_ids == []
    assert summary.least_worn_item_ids == [str(item_b.id), str(item_c.id)]
    _assert_invariants(summary)


# --- recent window ----------------------------------------------------------


def test_recent_wear_boundary_is_inclusive(db, dev_user_id):
    """`now - 30d` is recent; one second earlier is not. Ordered newest-first."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee A")
    item_b = _seed_item(db, dev_user_id, name="Tee B", category="bottoms")
    item_c = _seed_item(db, dev_user_id, name="Tee C")
    assert _post([str(item_a.id)], "summary-recent-1", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "summary-recent-2", worn_at=_T1).status_code == 201
    assert _post([str(item_c.id)], "summary-recent-3", worn_at=_T3).status_code == 201
    # T2 + 30 days exactly: A is exactly on the boundary (inclusive).
    boundary = _utc(2024, 2, 19, 12)
    summary = _summary(db, dev_user_id, now=boundary)
    assert summary.recently_worn_item_ids == [str(item_c.id), str(item_a.id)]
    # One second later: A drops out, only C (T3) remains.
    summary = _summary(db, dev_user_id, now=_utc(2024, 2, 19, 12, 0, 1))
    assert summary.recently_worn_item_ids == [str(item_c.id)]


# --- categories -------------------------------------------------------------


def test_category_frequency(db, dev_user_id):
    """Per-category frequencies over current items; keys code-sorted, zeros kept."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee A")
    item_b = _seed_item(db, dev_user_id, name="Tee B")
    item_c = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    _seed_item(db, dev_user_id, name="Boots", category="footwear")
    assert _post([str(item_a.id)], "summary-cat-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "summary-cat-2", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "summary-cat-3", worn_at=_T1).status_code == 201
    assert _post([str(item_c.id)], "summary-cat-4", worn_at=_T1).status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.wears_by_category == {"bottoms": 1, "footwear": 0, "tops": 3}
    assert list(summary.wears_by_category) == ["bottoms", "footwear", "tops"]
    _assert_invariants(summary)


# --- stale / empty / non-evidence -------------------------------------------


def test_deleted_item_history_is_ignored(db, dev_user_id):
    """Deleting an item removes its history from every summary field."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Doomed")
    item_b = _seed_item(db, dev_user_id, name="Survivor", category="bottoms")
    assert _post([str(item_a.id)], "summary-stale-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "summary-stale-2", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "summary-stale-3", worn_at=_T1).status_code == 201
    assert _summary(db, dev_user_id).total_wears == 3
    deleted = client.delete(f"/v1/wardrobe/items/{item_a.id}", headers=HEADERS)
    assert deleted.status_code == 204
    summary = _summary(db, dev_user_id)
    assert summary.total_wears == 1
    assert summary.wear_counts == {str(item_b.id): 1}
    assert str(item_a.id) not in summary.last_worn
    assert summary.most_worn_item_ids == [str(item_b.id)]
    assert summary.wears_by_category == {"bottoms": 1}
    _assert_invariants(summary)


def test_empty_wear_history(db, dev_user_id):
    """Items but no events: zeros, Nones, empty most/recent, all unworn."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    summary = _summary(db, dev_user_id)
    assert summary.total_wears == 0
    assert summary.wear_counts == {str(item_a.id): 0, str(item_b.id): 0}
    assert summary.last_worn == {str(item_a.id): None, str(item_b.id): None}
    assert summary.most_worn_item_ids == []
    assert summary.least_worn_item_ids == sorted([str(item_a.id), str(item_b.id)])
    assert summary.unworn_item_ids == sorted([str(item_a.id), str(item_b.id)])
    assert summary.recently_worn_item_ids == []
    assert summary.wears_by_category == {"bottoms": 0, "tops": 0}
    _assert_invariants(summary)


def test_favorites_and_saved_looks_create_no_wear_evidence(db, dev_user_id):
    """A favorited, outfit-saved item with no wear rows is still unworn."""
    _seed_vocab(db)
    fav = _seed_item(db, dev_user_id, name="Beloved", isFavorite=True)
    plain = _seed_item(db, dev_user_id, name="Plain", category="bottoms")
    save = client.post(
        "/v1/looks/saved",
        json={
            "lookId": None,
            "title": "Weekend Outfit",
            "sourceContext": "outfit",
            "snapshot": {"selectedItemIds": [str(fav.id), str(plain.id)]},
        },
        headers={**HEADERS, "Idempotency-Key": "summary-noevidence-1"},
    )
    assert save.status_code == 201
    summary = _summary(db, dev_user_id)
    assert summary.total_wears == 0
    assert summary.wear_counts == {str(fav.id): 0, str(plain.id): 0}
    assert summary.unworn_item_ids == sorted([str(fav.id), str(plain.id)])
    assert summary.most_worn_item_ids == []
    assert summary.recently_worn_item_ids == []
    _assert_invariants(summary)


def test_deterministic_ordering_across_calls(db, dev_user_id):
    """Repeated summaries are identical; map keys and rankings stay ordered."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee A")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    item_c = _seed_item(db, dev_user_id, name="Tee C")
    assert _post([str(item_a.id)], "summary-determin-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "summary-determin-2", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "summary-determin-3", worn_at=_T2).status_code == 201
    assert _post([str(item_c.id)], "summary-determin-4", worn_at=_T3).status_code == 201
    # Pin `now` just after the fixtures: all three are recent, with the
    # two T2 items tie-broken by id (server-now would age everything out).
    now = _utc(2024, 1, 26)
    first = _summary(db, dev_user_id, now=now)
    second = _summary(db, dev_user_id, now=now)
    assert first == second
    assert list(first.wear_counts) == sorted(first.wear_counts)
    assert list(first.last_worn) == sorted(first.last_worn)
    assert list(first.wears_by_category) == sorted(first.wears_by_category)
    assert first.most_worn_item_ids == [str(item_a.id)]
    assert first.recently_worn_item_ids == [str(item_c.id)] + sorted(
        [str(item_a.id), str(item_b.id)]
    )
    _assert_invariants(first)
