"""C-02-F fit implementation tests (STEP 2.9, owner-locked Option B).

Migration/model (1-5, static + PG round-trip), persistence (6-10, use-case
doubles), normalization (11-19), scoring (20-30), regression (31-39).
DB-backed tests opt into the `db` fixture and skip cleanly without
PostgreSQL; everything else runs everywhere. No Fit data is fabricated:
missing/unknown/`tailored` evidence is always neutral.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.application.wardrobe import AddWardrobeItem, UpdateWardrobeItem
from app.domain.ports.repositories import WardrobeItemRecord
from app.domain.services.analysis_rules import (
    _FIT_CONFIDENCE_GATE,
    _FIT_MAP_VERSION,
    _FIT_MATCH_BONUS,
    _FIT_REQUEST_MAP,
    _candidate_members,
    _fit_points,
    _usable_fit_evidence,
    candidate_favorite_points,
    candidate_preference_points,
    compose_candidate_score,
    generate_outfit_candidates,
    rank_outfit_candidates,
    score_outfit_candidate,
    select_best_outfit_candidate,
)
from app.domain.value_objects import OutfitCandidate
from app.infrastructure.db.models import WardrobeItems

USER = uuid4()


def _item(uid, category, color="black", material="cotton", fit=None, conf=None):
    return SimpleNamespace(
        id=uid, category=category, color=color, material=material,
        is_favorite=False, fit=fit, fit_confidence=conf,
    )


def _cand_fit(top=(), bottom=(), outer=(), shoe=(), acc=()):
    return OutfitCandidate(
        top_ids=tuple(top), bottom_ids=tuple(bottom),
        outerwear_ids=tuple(outer), footwear_ids=tuple(shoe),
        accessory_ids=tuple(acc),
    )


def _members(*specs):
    """specs: (uid, cat, fit, conf) with black/cotton defaults, or full
    (uid, cat, color, material, fit, conf)."""
    items = {}
    by_cat = {}
    for spec in specs:
        if len(spec) == 6:
            uid, cat, color, material, fit, conf = spec
        else:
            uid, cat, fit, conf = spec
            color, material = "black", "cotton"
        items[uid] = _item(uid, cat, color=color, material=material, fit=fit, conf=conf)
        by_cat.setdefault(cat, []).append(uid)
    cand = _cand_fit(
        top=by_cat.get("tops", ()), bottom=by_cat.get("bottoms", ()),
        outer=by_cat.get("outerwear", ()), shoe=by_cat.get("footwear", ()),
        acc=by_cat.get("accessories", ()),
    )
    return cand, items


def _fit_term(cand, items, request):
    return _fit_points(_candidate_members(cand, items), request)


# --- migration / model (1-5) -------------------------------------------------

def test_0023_revision_chain_and_static_contract():
    """1-2. 0023 exists, child of 0022 (single linear head extension)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(config)
    # C-07 extended the head: 0024 (item_added seed) on top of 0023.
    assert tuple(script.get_heads()) == ("0024",)
    rev = script.get_revision("0024")
    assert rev is not None
    assert rev.down_revision == "0023"
    rev23 = script.get_revision("0023")
    assert rev23 is not None
    assert rev23.down_revision == "0022"


def test_fit_columns_nullable_on_model():
    """4-5. fit / fit_confidence are nullable model columns (missing = NULL)."""
    cols = WardrobeItems.__table__.columns
    assert cols["fit"].nullable is True
    assert cols["fit_confidence"].nullable is True


def test_existing_rows_valid_with_null_fit():
    """3. Legacy construction (no fit args) stays valid; NULL by default."""
    record = WardrobeItemRecord(
        id=uuid4(), user_id=USER, name="Shirt", category="tops",
        color="black", material=None, is_favorite=False, image_ref=None,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    assert record.fit is None
    assert record.fit_confidence is None


def test_0023_downgrade_upgrade_round_trip(db):
    """1-2 (PG). Downgrade removes both columns; upgrade restores them nullable."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.attributes["configure_logger"] = False

    def cols(session):
        return {
            r[0]: r[2]
            for r in session.execute(
                text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'wardrobe_items' "
                    "AND column_name IN ('fit', 'fit_confidence')"
                )
            ).all()
        }

    Session = db
    command.downgrade(config, "0022")
    with Session() as session:
        assert cols(session) == {}
    command.upgrade(config, "head")
    with Session() as session:
        assert cols(session) == {"fit": "YES", "fit_confidence": "YES"}


# --- persistence (6-10) ------------------------------------------------------

class _FakeWardrobe:
    def __init__(self) -> None:
        self.created: dict = {}
        self.updated: dict = {}
        self.row = WardrobeItemRecord(
            id=uuid4(), user_id=USER, name="Shirt", category="tops",
            color="black", material=None, is_favorite=False, image_ref=None,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )

    def create(self, **kwargs):
        self.created = kwargs
        return self.row

    def update(self, **kwargs):
        self.updated = kwargs
        return self.row

    def get_by_id(self, *, user_id, item_id):
        return self.row

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _add(repo, **over):
    args = dict(
        user_id=USER, name="Shirt", category="tops", color="black",
        material=None, isFavorite=False,
    )
    args.update(over)
    return AddWardrobeItem(wardrobe=repo)(**args)


def test_vision_fit_and_confidence_persisted_verbatim():
    """6-7. Observed fit + analyzer confidence pass through unconverted."""
    repo = _FakeWardrobe()
    _add(repo, fit="relaxed", fit_confidence=0.83)
    assert repo.created["fit"] == "relaxed"
    assert repo.created["fit_confidence"] == 0.83


def test_missing_fit_and_confidence_persist_as_null():
    """8-9. Absent evidence → NULL (never 0, never 'unknown')."""
    repo = _FakeWardrobe()
    _add(repo)
    assert repo.created["fit"] is None
    assert repo.created["fit_confidence"] is None


def test_unrelated_garment_attributes_unchanged():
    """10. category/color/material/imageRef pass through exactly as before."""
    repo = _FakeWardrobe()
    _add(
        repo, category="bottoms", color="navy", material="denim",
        image_ref={"key": "k"}, fit="slim", fit_confidence=0.9,
    )
    assert repo.created["category"] == "bottoms"
    assert repo.created["color"] == "navy"
    assert repo.created["material"] == "denim"
    assert repo.created["image_ref"] == {"key": "k"}


def test_update_fit_set_semantics():
    """Update path: fit_set gates writes; explicit null clears."""
    repo = _FakeWardrobe()
    item_id = uuid4()
    UpdateWardrobeItem(wardrobe=repo)(
        user_id=USER, item_id=item_id, name=None, category=None, color=None,
        material=None, isFavorite=None, fit="slim", fit_set=True,
        fit_confidence=0.7, fit_confidence_set=True,
    )
    assert repo.updated["fit"] == "slim"
    assert repo.updated["fit_set"] is True
    assert repo.updated["fit_confidence"] == 0.7
    assert repo.updated["fit_confidence_set"] is True

    repo2 = _FakeWardrobe()
    UpdateWardrobeItem(wardrobe=repo2)(
        user_id=USER, item_id=item_id, name="Renamed", category=None,
        color=None, material=None, isFavorite=None,
    )
    assert repo2.updated["fit_set"] is False
    assert repo2.updated["fit_confidence_set"] is False


# --- normalization (11-19) ---------------------------------------------------

def test_locked_request_map_content():
    assert _FIT_REQUEST_MAP == {
        "slim": frozenset({"slim", "fitted", "compression"}),
        "relaxed": frozenset({"relaxed", "loose", "oversized"}),
    }
    assert _FIT_MAP_VERSION == "c02-f/1"
    assert _FIT_MATCH_BONUS == 5.0
    assert _FIT_CONFIDENCE_GATE == 0.6


def test_slim_evidence_values_map():
    """11-13. slim/fitted/compression evidence usable at gate."""
    for value in ("slim", "fitted", "compression"):
        assert _usable_fit_evidence(value, 0.9) == "slim"
        cand, items = _members(("t", "tops", value, 0.9), ("b", "bottoms", "slim", 0.9))
        assert _fit_term(cand, items, "slim") == 5.0


def test_relaxed_evidence_values_map():
    """14-16. relaxed/loose/oversized evidence usable at gate."""
    for value in ("relaxed", "loose", "oversized"):
        assert _usable_fit_evidence(value, 0.9) == "relaxed"
        cand, items = _members(("t", "tops", value, 0.9), ("b", "bottoms", "relaxed", 0.9))
        assert _fit_term(cand, items, "relaxed") == 5.0


def test_tailored_unsupported_and_neutral():
    """17. tailored has no mapping: request and evidence both neutral."""
    assert _usable_fit_evidence("tailored", 0.95) is None
    cand, items = _members(("t", "tops", "tailored", 0.95), ("b", "bottoms", "tailored", 0.95))
    assert _fit_term(cand, items, "tailored") == 0.0
    assert _fit_term(cand, items, "slim") == 0.0


def test_unknown_and_missing_evidence_neutral():
    """18-19. Unknown strings, None, wrong types → neutral, never a veto."""
    for bad in (None, "", "skinny", "regular", 42, True):
        assert _usable_fit_evidence(bad, 0.9) is None
    cand, items = _members(("t", "tops", "skinny", 0.9), ("b", "bottoms", None, 0.9))
    assert _fit_term(cand, items, "slim") == 0.0
    # Unknown member skipped: one usable match + one missing → still +5.
    cand2, items2 = _members(("t", "tops", "slim", 0.9), ("b", "bottoms", None, None))
    assert _fit_term(cand2, items2, "slim") == 5.0
    # Unknown/absent request → 0.
    assert _fit_term(cand2, items2, None) == 0.0
    assert _fit_term(cand2, items2, "vibrant") == 0.0
    assert _fit_term(cand2, items2, "") == 0.0


# --- scoring (20-30) ---------------------------------------------------------

def _slim_pair(conf):
    return _members(("t", "tops", "slim", conf), ("b", "bottoms", "fitted", conf))


def test_confidence_below_gate_scores_zero():
    """20. conf < 0.60 → 0 even on perfect match."""
    cand, items = _slim_pair(0.59)
    assert _fit_term(cand, items, "slim") == 0.0
    out = score_outfit_candidate(cand, items, frozenset(), [], preferred_fit="slim")
    base = score_outfit_candidate(cand, items, frozenset(), [])
    assert out.score == base.score  # no fit contribution below gate


def test_confidence_exactly_gate_eligible():
    """21. conf == 0.60 → eligible (+5)."""
    cand, items = _slim_pair(0.60)
    assert _fit_term(cand, items, "slim") == 5.0


def test_confidence_above_gate_eligible():
    """22. conf > 0.60 → eligible (+5)."""
    cand, items = _slim_pair(0.95)
    assert _fit_term(cand, items, "slim") == 5.0


def test_confidence_never_multiplied():
    """23. Gate only: 0.6 and 1.0 evidence contribute identically."""
    low = _fit_term(*_slim_pair(0.60), "slim")
    high = _fit_term(*_slim_pair(1.0), "slim")
    assert low == high == 5.0  # a multiplier would give 3.0 vs 5.0
    # Out-of-range / bool confidences are invalid evidence, never scaled in.
    for bad in (-0.1, 1.5, True, float("nan")):
        assert _usable_fit_evidence("slim", bad) is None


def test_missing_confidence_scores_zero():
    """25. Fit present but confidence absent on every member → 0 (never assume)."""
    cand, items = _members(("t", "tops", "slim", None), ("b", "bottoms", "slim", None))
    assert _fit_term(cand, items, "slim") == 0.0


def test_fit_mismatch_never_filters():
    """28. Usable-evidence mismatch → 0 points, candidate still ranks."""
    cand, items = _members(("t", "tops", "slim", 0.9), ("b", "bottoms", "relaxed", 0.9))
    assert _fit_term(cand, items, "slim") == 0.0
    by_id = items
    ranked = rank_outfit_candidates(
        [score_outfit_candidate(cand, by_id, frozenset(), [], preferred_fit="slim")]
    )
    assert len(ranked) == 1
    assert select_best_outfit_candidate(ranked) is not None


def test_fit_contribution_capped_and_budget_holds():
    """29-30. Fit ≤ +5; compatibility ceiling exactly 70 with fit live."""
    cand, items = _members(
        ("t", "tops", "black", "cotton", "slim", 0.9),
        ("b", "bottoms", "white", "cotton", "slim", 0.9),
        ("o", "outerwear", "charcoal", "cotton", "slim", 0.9),
        ("f", "footwear", "grey", "cotton", "slim", 0.9),
        ("a", "accessories", "black", "cotton", "slim", 0.9),
    )
    out = score_outfit_candidate(
        cand, items, frozenset(), ["casual"],
        preferred_palette="monochrome", preferred_fit="slim",
    )
    # 35 coverage + 5 color + 5 material + 5 season + 0 formality (mixed
    # registers) + 5 occasion + 5 palette + 5 fit = 65.
    assert out.compatibility == 65.0
    assert out.score == 65.0
    plain = score_outfit_candidate(cand, items, frozenset(), ["casual"])
    assert out.score == plain.score + 10.0  # palette 5 + fit 5, nothing else moved


# --- regression (31-39) ------------------------------------------------------

def test_palette_still_plus_five():
    """31. Palette behavior preserved after fit integration."""
    cand, items = _members(("t", "tops", None, None), ("b", "bottoms", None, None))
    from app.domain.services.analysis_rules import _candidate_members, _palette_points
    assert _palette_points(_candidate_members(cand, items), "monochrome") == 5.0


def test_caps_and_tie_break_unchanged():
    """34-38. Coverage 35 cap, pref/fav 15 caps, final ≤ 100, tie-break."""
    ids = [f"aaaaaaaa-0000-4000-8000-{i:012d}" for i in range(4)]
    assert candidate_preference_points(frozenset(ids), ids) == 15.0
    assert candidate_favorite_points([True, True, True, True]) == 15.0
    assert compose_candidate_score(70.0, 15.0, 15.0) == 100.0
    low = OutfitCandidate(top_ids=("b",), bottom_ids=("b",), score=50.0)
    fuller = OutfitCandidate(top_ids=("a",), bottom_ids=("b", "c"), score=50.0)
    assert rank_outfit_candidates([low, fuller])[0] is fuller
