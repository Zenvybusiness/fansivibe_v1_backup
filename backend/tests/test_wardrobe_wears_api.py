"""API tests for the wear-event surface (STEP 15.4).

`POST /v1/wardrobe/wears` logs one row per wardrobe item sharing one
server-generated group; `GET /v1/wardrobe/wears` lists individual rows.
Idempotency mirrors UC-15 (TRX-3): canonical payload compared BEFORE the
write, replay returns the original group (`created=false`, still 201),
changed payload → 409.

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.infrastructure.db.models import (
    Colors,
    Materials,
    Users,
    UserState,
    WardrobeCategories,
    WardrobeItems,
    WardrobeWearEvents,
)

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}


@pytest.fixture
def dev_user_id(db):
    """Get or create the dev user ID (mirrors test_wardrobe_api.py)."""
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


def _wear_count(db):
    Session = db
    with Session() as session:
        return session.execute(
            select(text("count(*)")).select_from(text("wardrobe_wear_events"))
        ).scalar_one()


def _group_count(db):
    Session = db
    with Session() as session:
        return session.execute(
            select(text("count(*)")).select_from(text("wardrobe_wear_groups"))
        ).scalar_one()


def _groups_for_key(db, user_id, key):
    """Ledger rows for one (user, key): (id, item_ids) tuples."""
    Session = db
    with Session() as session:
        return session.execute(
            text(
                "SELECT id, item_ids FROM wardrobe_wear_groups "
                "WHERE user_id = :uid AND idempotency_key = :key"
            ),
            {"uid": str(user_id), "key": key},
        ).all()


def _group_ids_for_key(db, user_id, key):
    """Distinct wear_group_ids on event rows for one (user, key)."""
    Session = db
    with Session() as session:
        return session.execute(
            text(
                "SELECT DISTINCT wear_group_id FROM wardrobe_wear_events "
                "WHERE user_id = :uid AND idempotency_key = :key"
            ),
            {"uid": str(user_id), "key": key},
        ).scalars().all()


def _post(item_ids, key, worn_at=None, headers=HEADERS):
    body = {"itemIds": item_ids}
    if worn_at is not None:
        body["wornAt"] = worn_at
    return client.post(
        "/v1/wardrobe/wears", json=body, headers={**headers, "Idempotency-Key": key}
    )


# --- POST: happy paths ------------------------------------------------------


def test_post_single_item_wear_returns_201(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    resp = _post([str(item.id)], "wear-single-1")
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is True
    assert body["wornAt"] is not None
    assert body["wearGroupId"] is not None
    assert len(body["wears"]) == 1
    row = body["wears"][0]
    assert row["wardrobeItemId"] == str(item.id)
    assert row["wearGroupId"] == body["wearGroupId"]
    assert row["wornAt"] == body["wornAt"]
    assert row["id"] is not None
    assert row["createdAt"] is not None
    assert _wear_count(db) == 1


def test_post_multi_item_wear_shares_one_group(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    resp = _post([str(item_a.id), str(item_b.id)], "wear-multi-1")
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is True
    assert len(body["wears"]) == 2
    groups = {row["wearGroupId"] for row in body["wears"]}
    assert groups == {body["wearGroupId"]}
    assert sorted(row["wardrobeItemId"] for row in body["wears"]) == sorted(
        [str(item_a.id), str(item_b.id)]
    )
    assert _wear_count(db) == 2


def test_post_omitted_worn_at_populates_server_time(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    before = datetime.now(timezone.utc)
    resp = _post([str(item.id)], "wear-now-1")
    after = datetime.now(timezone.utc)
    assert resp.status_code == 201
    worn = datetime.fromisoformat(resp.json()["wornAt"])
    assert before - timedelta(seconds=5) <= worn <= after + timedelta(seconds=5)


def test_post_explicit_worn_at_preserved(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    resp = _post([str(item.id)], "wear-explicit-1", worn_at="2024-03-01T12:00:00Z")
    assert resp.status_code == 201
    body = resp.json()
    # The wire offset form follows the connection timezone; the instant is
    # what the API guarantees — compare instants, not strings.
    assert datetime.fromisoformat(body["wornAt"]) == datetime(
        2024, 3, 1, 12, 0, tzinfo=timezone.utc
    )
    assert body["wears"][0]["wornAt"] == body["wornAt"]


def test_post_duplicate_item_ids_canonicalized(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    ids = [str(item_b.id), str(item_a.id), str(item_a.id)]
    resp = _post(ids, "wear-dupe-1")
    assert resp.status_code == 201
    body = resp.json()
    assert [row["wardrobeItemId"] for row in body["wears"]] == sorted(
        [str(item_a.id), str(item_b.id)]
    )
    assert _wear_count(db) == 2


# --- POST: validation -------------------------------------------------------


def test_post_more_than_ten_unique_items_returns_422(db, dev_user_id):
    _seed_vocab(db)
    ids = [str(_seed_item(db, dev_user_id, name=f"Item {i}").id) for i in range(11)]
    resp = _post(ids, "wear-too-many-1")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _wear_count(db) == 0


def test_post_malformed_uuid_returns_422(db, dev_user_id):
    _seed_item(db, dev_user_id)
    resp = _post(["nope"], "wear-malformed-1")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _wear_count(db) == 0


def test_post_requires_idempotency_key(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    resp = client.post(
        "/v1/wardrobe/wears", json={"itemIds": [str(item.id)]}, headers=HEADERS
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _wear_count(db) == 0


def test_post_future_worn_at_returns_422(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    resp = _post([str(item.id)], "wear-future-1", worn_at=future)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _wear_count(db) == 0


def test_post_requires_auth(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    resp = client.post(
        "/v1/wardrobe/wears",
        json={"itemIds": [str(item.id)]},
        headers={"Idempotency-Key": "wear-noauth-1"},
    )
    assert resp.status_code == 401
    assert _wear_count(db) == 0


# --- POST: idempotency ------------------------------------------------------


def test_post_replay_returns_original_with_created_false(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    first = _post([str(item.id)], "wear-replay-1")
    assert first.status_code == 201
    replay = _post([str(item.id)], "wear-replay-1")
    assert replay.status_code == 201
    assert replay.json()["created"] is False
    assert replay.json()["wearGroupId"] == first.json()["wearGroupId"]
    assert replay.json()["wears"] == first.json()["wears"]
    assert _wear_count(db) == 1


def test_post_conflicting_replay_returns_409(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    first = _post([str(item_a.id)], "wear-conflict-1")
    assert first.status_code == 201
    resp = _post([str(item_b.id)], "wear-conflict-1")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"
    assert _wear_count(db) == 1


def test_post_same_key_different_user_is_independent(db, dev_user_id):
    """Idempotency scope is (user_id, key): no cross-user conflict."""
    from app.application.wardrobe import LogWearEvents
    from app.infrastructure.db.repositories import (
        WardrobeItemRepositorySQL,
        WearEventRepositorySQL,
        WearGroupRepositorySQL,
    )

    _seed_vocab(db)
    other_id = _make_other_user(db)
    item_dev = _seed_item(db, dev_user_id)
    item_other = _seed_item(db, other_id, name="Other Tee")
    Session = db
    with Session() as session:
        use_case = LogWearEvents(
            wardrobe=WardrobeItemRepositorySQL(session),
            wears=WearEventRepositorySQL(session),
            groups=WearGroupRepositorySQL(session),
        )
        records_dev, created_dev = use_case(
            user_id=dev_user_id,
            item_ids=[item_dev.id],
            worn_at=None,
            idempotency_key="wear-shared-key-1",
        )
        records_other, created_other = use_case(
            user_id=other_id,
            item_ids=[item_other.id],
            worn_at=None,
            idempotency_key="wear-shared-key-1",
        )
    assert created_dev is True
    assert created_other is True
    assert records_dev[0].wear_group_id != records_other[0].wear_group_id
    assert _wear_count(db) == 2


def test_post_order_insensitive_replay(db, dev_user_id):
    """[B, A] vs [A, B] under one key replays (canonical order)."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    first = _post([str(item_b.id), str(item_a.id)], "wear-order-1")
    assert first.status_code == 201
    replay = _post([str(item_a.id), str(item_b.id)], "wear-order-1")
    assert replay.status_code == 201
    assert replay.json()["created"] is False
    assert replay.json()["wearGroupId"] == first.json()["wearGroupId"]
    assert _wear_count(db) == 2


def test_post_duplicate_vs_canonical_replay(db, dev_user_id):
    """[A, A, B] vs [A, B] under one key replays (dedupe before compare)."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    first = _post(
        [str(item_a.id), str(item_a.id), str(item_b.id)], "wear-dupeeq-1"
    )
    assert first.status_code == 201
    replay = _post([str(item_a.id), str(item_b.id)], "wear-dupeeq-1")
    assert replay.status_code == 201
    assert replay.json()["created"] is False
    assert _wear_count(db) == 2


def test_post_equivalent_worn_at_format_replays(db, dev_user_id):
    """`Z` vs `+00:00` for one instant replays (instant, not string, compare)."""
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    first = _post([str(item.id)], "wear-tzfmt-1", worn_at="2024-05-01T10:00:00Z")
    assert first.status_code == 201
    replay = _post(
        [str(item.id)], "wear-tzfmt-1", worn_at="2024-05-01T10:00:00+00:00"
    )
    assert replay.status_code == 201
    assert replay.json()["created"] is False
    assert _wear_count(db) == 1


# --- POST: ownership / history ----------------------------------------------


def test_post_cross_user_item_returns_404(db, dev_user_id):
    """Another owner's item → 404 (OW-1, 404-not-403), nothing stored."""
    _seed_vocab(db)
    other_id = _make_other_user(db)
    foreign = _seed_item(db, other_id, name="Foreign Tee")
    resp = _post([str(foreign.id)], "wear-foreign-1")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
    assert _wear_count(db) == 0


def test_post_phantom_item_returns_404_and_history_survives_delete(
    db, dev_user_id
):
    """Unknown UUIDs cannot be newly logged; rows logged before an item's
    deletion stay readable (history, not a live join)."""
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    phantom = _post([str(uuid4())], "wear-phantom-1")
    assert phantom.status_code == 404
    assert _wear_count(db) == 0

    logged = _post([str(item.id)], "wear-history-1")
    assert logged.status_code == 201
    deleted = client.delete(f"/v1/wardrobe/items/{item.id}", headers=HEADERS)
    assert deleted.status_code == 204
    listed = client.get("/v1/wardrobe/wears", headers=HEADERS)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["wardrobeItemId"] == str(item.id)


def test_post_partial_failure_rolls_back_without_rows(db, dev_user_id, monkeypatch):
    """A mid-batch insert failure commits nothing (single transaction)."""
    from app.infrastructure.db.repositories import WearEventRepositorySQL

    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    original = WearEventRepositorySQL.log
    calls = []

    def flaky(self, **kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return original(self, **kwargs)

    monkeypatch.setattr(WearEventRepositorySQL, "log", flaky)
    resp = _post([str(item_a.id), str(item_b.id)], "wear-rollback-1")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "DATABASE_FAILURE"
    assert _wear_count(db) == 0
    # The ledger row rolls back with the event rows: one transaction.
    assert _group_count(db) == 0


# --- GET --------------------------------------------------------------------


def test_get_empty_history_returns_empty_envelope(db, dev_user_id):
    resp = client.get("/v1/wardrobe/wears", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_get_returns_individual_rows(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    _post([str(item_a.id), str(item_b.id)], "wear-get-1")
    resp = client.get("/v1/wardrobe/wears", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    for row in body["items"]:
        assert set(row) == {"id", "wardrobeItemId", "wornAt", "wearGroupId", "createdAt"}


def test_get_item_id_filter(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    _post([str(item_a.id), str(item_b.id)], "wear-filter-1")
    resp = client.get(
        "/v1/wardrobe/wears", params={"item_id": str(item_a.id)}, headers=HEADERS
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["wardrobeItemId"] == str(item_a.id)


def test_get_pagination(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    for day, key in (("01", "wear-page-1"), ("02", "wear-page-2"), ("03", "wear-page-3")):
        resp = _post([str(item.id)], key, worn_at=f"2024-06-{day}T12:00:00Z")
        assert resp.status_code == 201
    first = client.get(
        "/v1/wardrobe/wears", params={"page": 1, "page_size": 2}, headers=HEADERS
    ).json()
    second = client.get(
        "/v1/wardrobe/wears", params={"page": 2, "page_size": 2}, headers=HEADERS
    ).json()
    assert (first["page"], first["page_size"], first["total"]) == (1, 2, 3)
    assert len(first["items"]) == 2
    assert (second["page"], len(second["items"])) == (2, 1)


def test_get_orders_worn_at_desc(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    for day in ("01", "02", "03"):
        _post([str(item.id)], f"wear-order-{day}", worn_at=f"2024-07-{day}T12:00:00Z")
    resp = client.get("/v1/wardrobe/wears", headers=HEADERS)
    assert resp.status_code == 200
    worn = [datetime.fromisoformat(row["wornAt"]) for row in resp.json()["items"]]
    assert worn == [
        datetime(2024, 7, day, 12, 0, tzinfo=timezone.utc) for day in (3, 2, 1)
    ]


def test_get_id_asc_tiebreaker_for_shared_worn_at(db, dev_user_id):
    """Rows of one POST share `worn_at`; `id` ASC keeps pagination stable."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    logged = _post([str(item_a.id), str(item_b.id)], "wear-tie-1")
    assert logged.status_code == 201
    resp = client.get("/v1/wardrobe/wears", headers=HEADERS)
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()["items"]]
    assert ids == sorted(ids)


def test_get_is_user_isolated(db, dev_user_id):
    """Another owner's rows never appear in my history."""
    from app.application.wardrobe import LogWearEvents
    from app.infrastructure.db.repositories import (
        WardrobeItemRepositorySQL,
        WearEventRepositorySQL,
        WearGroupRepositorySQL,
    )

    _seed_vocab(db)
    other_id = _make_other_user(db)
    mine = _seed_item(db, dev_user_id)
    theirs = _seed_item(db, other_id, name="Other Tee")
    Session = db
    with Session() as session:
        use_case = LogWearEvents(
            wardrobe=WardrobeItemRepositorySQL(session),
            wears=WearEventRepositorySQL(session),
            groups=WearGroupRepositorySQL(session),
        )
        use_case(
            user_id=other_id,
            item_ids=[theirs.id],
            worn_at=None,
            idempotency_key="wear-isolation-1",
        )
    _post([str(mine.id)], "wear-isolation-2")
    resp = client.get("/v1/wardrobe/wears", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["wardrobeItemId"] == str(mine.id)


def test_get_malformed_item_id_returns_422(db, dev_user_id):
    resp = client.get(
        "/v1/wardrobe/wears", params={"item_id": "nope"}, headers=HEADERS
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_requires_auth(db, dev_user_id):
    resp = client.get("/v1/wardrobe/wears")
    assert resp.status_code == 401


# --- STEP 15.4B: durable action ledger ---------------------------------------
#
# One POST = one logical action = ONE ledger row. These tests prove the
# architecture (whole-request atomic idempotency, including under
# concurrency), not just serial implementation behavior.
# ---------------------------------------------------------------------------


def test_post_creates_one_ledger_group(db, dev_user_id):
    """A multi-item POST writes one group row holding the canonical payload;
    the group id IS the rows' wear_group_id."""
    from datetime import datetime, timezone

    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    resp = _post(
        [str(item_b.id), str(item_a.id)],
        "wear-ledger-1",
        worn_at="2024-08-01T12:00:00Z",
    )
    assert resp.status_code == 201
    body = resp.json()
    groups = _groups_for_key(db, dev_user_id, "wear-ledger-1")
    assert len(groups) == 1
    assert str(groups[0][0]) == body["wearGroupId"]
    assert groups[0][1] == sorted([str(item_a.id), str(item_b.id)])
    assert _group_ids_for_key(db, dev_user_id, "wear-ledger-1") == [
        groups[0][0]
    ]
    assert datetime.fromisoformat(body["wornAt"]) == datetime(
        2024, 8, 1, 12, 0, tzinfo=timezone.utc
    )


def _run_concurrent_wears(db, user_id, key, payloads):
    """Run use-case wear logs on two threads behind a barrier.

    Separate sessions per thread (the only thread-safe pattern); the
    barrier makes the ledger inserts overlap. Outcome assertions (not
    timing) make the test deterministic: every interleave resolves to the
    same observable state.
    """
    import threading

    from app.api.errors import ApiError
    from app.application.wardrobe import LogWearEvents
    from app.infrastructure.db.repositories import (
        WardrobeItemRepositorySQL,
        WearEventRepositorySQL,
        WearGroupRepositorySQL,
    )
    from tests.conftest import make_session

    barrier = threading.Barrier(2)
    outcomes = {}

    def worker(slot, item_ids):
        Session = make_session()
        with Session() as session:
            use_case = LogWearEvents(
                wardrobe=WardrobeItemRepositorySQL(session),
                wears=WearEventRepositorySQL(session),
                groups=WearGroupRepositorySQL(session),
            )
            try:
                barrier.wait(timeout=30)
                records, created = use_case(
                    user_id=user_id,
                    item_ids=item_ids,
                    worn_at=None,
                    idempotency_key=key,
                )
                outcomes[slot] = (
                    "created" if created else "replay",
                    sorted(str(r.wardrobe_item_id) for r in records),
                    str(records[0].wear_group_id) if records else None,
                )
            except ApiError as exc:
                session.rollback()
                outcomes[slot] = (f"api-{exc.code}",)
            except Exception:  # noqa: BLE001
                session.rollback()
                outcomes[slot] = ("unexpected-error",)

    threads = [
        threading.Thread(target=worker, args=(slot, ids))
        for slot, ids in enumerate(payloads)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)
    assert sorted(outcomes) == [0, 1]
    return outcomes


def test_post_concurrent_identical_requests_create_one_group(db, dev_user_id):
    """Same key + same items concurrently: exactly one group, N rows, one
    created=true + one created=false, no duplicates."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    ids = [item_a.id, item_b.id]
    outcomes = _run_concurrent_wears(
        db, dev_user_id, "wear-conc-same-1", [ids, ids]
    )
    kinds = sorted(outcomes[slot][0] for slot in outcomes)
    assert kinds == ["created", "replay"]
    assert _group_count(db) == 1
    assert _wear_count(db) == 2
    groups = _groups_for_key(db, dev_user_id, "wear-conc-same-1")
    assert len(groups) == 1
    assert _group_ids_for_key(db, dev_user_id, "wear-conc-same-1") == [
        groups[0][0]
    ]


def test_post_concurrent_disjoint_requests_do_not_fuse(db, dev_user_id):
    """Same key + DISJOINT items concurrently: exactly one group wins, the
    loser 409s, and the key never spans two groups (the 15.4A hole)."""
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    item_c = _seed_item(db, dev_user_id, name="Jacket", category="outerwear")
    item_d = _seed_item(db, dev_user_id, name="Sneakers", category="footwear")
    outcomes = _run_concurrent_wears(
        db,
        dev_user_id,
        "wear-conc-split-1",
        [[item_a.id, item_b.id], [item_c.id, item_d.id]],
    )
    kinds = sorted(outcomes[slot][0] for slot in outcomes)
    assert kinds == ["api-CONFLICT", "created"]
    # One group, one winner's rows, one shared group id — never fused.
    assert _group_count(db) == 1
    assert _wear_count(db) == 2
    groups = _groups_for_key(db, dev_user_id, "wear-conc-split-1")
    assert len(groups) == 1
    assert _group_ids_for_key(db, dev_user_id, "wear-conc-split-1") == [
        groups[0][0]
    ]
    winner_items = next(
        outcomes[slot][1] for slot in outcomes if outcomes[slot][0] == "created"
    )
    assert groups[0][1] == winner_items


def test_delete_user_cascades_groups_and_rows(db, dev_user_id):
    """Account erasure removes the ledger AND the event history (composition)."""
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id)
    resp = _post([str(item.id)], "wear-cascade-1")
    assert resp.status_code == 201
    assert _wear_count(db) == 1
    assert _group_count(db) == 1
    Session = db
    with Session() as session:
        session.execute(
            text("DELETE FROM users WHERE id = :uid"), {"uid": str(dev_user_id)}
        )
        session.commit()
    assert _wear_count(db) == 0
    assert _group_count(db) == 0
