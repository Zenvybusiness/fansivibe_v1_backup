"""Phase 1 Step 10 — C-10 Analysis Idempotency Implementation Tests.

Verifies:
A. New analysis request with a new key creates exactly one AnalysisRun.
B. Same user + same key replay returns the same run_id.
C. Replay does NOT create another AnalysisRun.
D. Replay does NOT invoke the AI/vision adapter again.
E. Replay does NOT repeat style_profile side effects.
F. Replay does NOT emit duplicate learning signals.
G. Different keys create independent runs.
H. Different users with the same key create independent runs.
I. Missing/null key preserves existing non-idempotent behavior.
J. Existing legacy AnalysisRuns with NULL idempotency_key remain valid.
K. Unique database constraint exists.
L. Concurrent same-key requests cannot create two logical runs (race safety).
M. All five execution paths are covered:
   - garment
   - outfit
   - hairstyle image
   - hairstyle profile-only
   - grooming
N. Migration 0025 upgrade/downgrade static and revision chain contracts.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Text, create_engine, select
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.api.errors import ApiError
from app.application.analysis import (
    CreateGarmentRun,
    CreateGroomingRun,
    CreateHairstyleImageRun,
    CreateHairstyleRun,
    CreateOutfitRun,
)
from app.domain.ports.repositories import AnalysisRunRecord
from app.domain.ports.appearance_analysis import AppearanceAnalysisPort
from app.domain.value_objects import AppearanceProfile, GarmentProfile
from app.infrastructure.db.models import AnalysisRuns
from app.infrastructure.db.repositories import AnalysisRunRepositorySQL
from app.infrastructure.external.knowledge import CatalogKnowledgeSource


USER_1 = uuid4()
USER_2 = uuid4()


# ---------------------------------------------------------------------------
# Fake In-Memory Repositories for Deterministic Use Case Testing
# ---------------------------------------------------------------------------

@dataclass
class FakeRunsRepo:
    """In-memory AnalysisRunRepository with idempotency & race simulation."""

    rows: dict[UUID, dict] = field(default_factory=dict)
    next_id: Optional[UUID] = None
    fail_next_create_with_integrity: bool = False
    concurrent_winner_row: Optional[dict] = None

    def create(
        self,
        *,
        user_id: UUID,
        run_type: str,
        engine_version: str = "rules-v1",
        input_media: Optional[dict] = None,
        knowledge_version: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> UUID:
        if self.fail_next_create_with_integrity:
            self.fail_next_create_with_integrity = False
            if self.concurrent_winner_row:
                winner_id = self.concurrent_winner_row["id"]
                self.rows[winner_id] = dict(self.concurrent_winner_row)
            raise IntegrityError("duplicate key", params={}, orig=Exception("unique constraint"))

        # Check unique constraint simulation
        if idempotency_key is not None:
            for r in self.rows.values():
                if r["user_id"] == user_id and r.get("idempotency_key") == idempotency_key:
                    raise IntegrityError("duplicate key", params={}, orig=Exception("unique constraint"))

        run_id = self.next_id or uuid4()
        self.next_id = None
        self.rows[run_id] = {
            "id": run_id,
            "user_id": user_id,
            "run_type": run_type,
            "status": "pending",
            "engine_version": engine_version,
            "created_at": datetime.now(timezone.utc),
            "completed_at": None,
            "input_media": input_media,
            "result": None,
            "error": None,
            "knowledge_version": knowledge_version,
            "idempotency_key": idempotency_key,
        }
        return run_id

    def get_for_user(self, *, user_id: UUID, run_id: UUID) -> Optional[AnalysisRunRecord]:
        row = self.rows.get(run_id)
        if row is None or row["user_id"] != user_id:
            return None
        return AnalysisRunRecord(**{k: v for k, v in row.items() if k != "user_id"})

    def get_by_idempotency(self, *, user_id: UUID, idempotency_key: str) -> Optional[AnalysisRunRecord]:
        for row in self.rows.values():
            if row["user_id"] == user_id and row.get("idempotency_key") == idempotency_key:
                return AnalysisRunRecord(**{k: v for k, v in row.items() if k != "user_id"})
        return None

    def list_for_user(self, *, user_id: UUID, page: int, page_size: int):
        items = [r for r in self.rows.values() if r["user_id"] == user_id]
        return items, len(items)

    def complete(self, *, run_id: UUID, user_id: UUID, status: str, result: dict) -> bool:
        row = self.rows.get(run_id)
        if row is None or row["user_id"] != user_id:
            return False
        row["status"] = status
        row["result"] = result
        row["completed_at"] = datetime.now(timezone.utc)
        return True

    def fail(self, *, run_id: UUID, user_id: UUID, error: dict) -> bool:
        row = self.rows.get(run_id)
        if row is None or row["user_id"] != user_id:
            return False
        row["status"] = "failed"
        row["error"] = error
        row["completed_at"] = datetime.now(timezone.utc)
        return True


class FakeUserStateRepo:
    def __init__(self, profile: Optional[dict] = None) -> None:
        self.profile = profile
        self.update_count = 0
        self.last_update = None

    def get_style_profile(self, *, user_id: UUID) -> Optional[dict]:
        return self.profile

    def update_style_profile(
        self,
        *,
        user_id: UUID,
        face_shape: str,
        skin_tone: str,
        body_type: str,
        style_type: str,
        source_run_id: str,
    ) -> None:
        self.update_count += 1
        self.last_update = {
            "user_id": user_id,
            "face_shape": face_shape,
            "skin_tone": skin_tone,
            "body_type": body_type,
            "style_type": style_type,
            "source_run_id": source_run_id,
        }


class FakeLearningSignalRepo:
    def __init__(self) -> None:
        self.signals: list[dict] = []
        self.commits: int = 0

    def insert_look_saved(
        self,
        *,
        user_id: UUID,
        signal_type: str,
        label: str,
        context: Optional[dict] = None,
    ) -> None:
        self.signals.append(
            {
                "user_id": user_id,
                "signal_type": signal_type,
                "label": label,
                "context": context,
            }
        )

    def record_signal(
        self,
        *,
        user_id: UUID,
        signal_type: str,
        source_run_id: Optional[UUID],
        payload: dict,
    ) -> None:
        self.signals.append(
            {
                "user_id": user_id,
                "signal_type": signal_type,
                "source_run_id": source_run_id,
                "payload": payload,
            }
        )

    def commit(self) -> None:
        self.commits += 1



class FakeSavedLookRepo:
    def list_for_user(self, *, user_id: UUID, page: int, page_size: int):
        return [], 0


class SpyAppearancePort(AppearanceAnalysisPort):
    adapter_id = "spy-vision-adapter"

    def __init__(self) -> None:
        self.call_count = 0

    def analyze(
        self, *, media_ref: dict, user_id: UUID, image_bytes: Optional[bytes] = None
    ) -> AppearanceProfile:
        self.call_count += 1
        return AppearanceProfile(
            faceShape="Oval",
            skinTone="Warm Medium",
            bodyType="Athletic",
            styleType="Classic",
        )


class SpyGarmentPort:
    adapter_id = "spy-garment-adapter"

    def __init__(self) -> None:
        self.call_count = 0

    def analyze(
        self, *, media_ref: dict, user_id: UUID, image_bytes: Optional[bytes] = None
    ) -> GarmentProfile:
        self.call_count += 1
        return GarmentProfile(
            category="tops",
            subcategory="oxford shirt",
            color="light blue",
            pattern="solid",
            material="cotton",
            style=None,
            fit=None,
            confidence=0.84,
            needs_review=False,
        )


class MockImage:
    def __init__(self, content: bytes, content_type: str = "image/jpeg") -> None:
        self.content = content
        self.file = io.BytesIO(content)
        self.content_type = content_type
        self.size = len(content)

    def read(self) -> bytes:
        return self.content

    def seek(self, offset: int) -> None:
        self.file.seek(offset)


# ---------------------------------------------------------------------------
# Section 1: Migration 0025 & Model Schema Contract (N, K, J)
# ---------------------------------------------------------------------------

def test_0025_revision_chain_and_static_contract():
    """N. Migration 0025 is linear head off 0024 with clean downgrade."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(config)

    assert tuple(script.get_heads()) == ("0025",)
    rev25 = script.get_revision("0025")
    assert rev25 is not None
    assert rev25.down_revision == "0024"

    # Static inspection of 0025 file
    import importlib.util
    spec = importlib.util.spec_from_file_location("m0025", rev25.path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")
    assert mod.revision == "0025"
    assert mod.down_revision == "0024"


def test_analysis_runs_model_has_idempotency_column_and_constraint():
    """K, J. AnalysisRuns model defines nullable idempotency_key & unique constraint."""
    table = AnalysisRuns.__table__
    assert "idempotency_key" in table.c
    col = table.c["idempotency_key"]
    assert col.nullable is True
    assert isinstance(col.type, Text)

    # Check unique constraint on (user_id, idempotency_key)
    uq_names = [c.name for c in table.constraints if c.name == "uq_analysis_runs_idempotency"]
    assert "uq_analysis_runs_idempotency" in uq_names


# ---------------------------------------------------------------------------
# Section 2: Hairstyle Profile-Only Execution Path (A, B, C, F, G, H, I, J)
# ---------------------------------------------------------------------------

def test_hairstyle_profile_idempotency_flow():
    """A-C, G-J for Hairstyle profile-only path."""
    runs = FakeRunsRepo()
    user_state = FakeUserStateRepo({"face_shape": "Oval", "skin_tone": "Warm Medium"})
    knowledge = CatalogKnowledgeSource()
    use_case = CreateHairstyleRun(runs=runs, user_state=user_state, knowledge=knowledge)

    # A. New request with key creates 1 run
    run_1 = use_case(user_id=USER_1, idempotency_key="key-hs-1")
    assert run_1 is not None
    assert len(runs.rows) == 1
    record = runs.get_for_user(user_id=USER_1, run_id=run_1)
    assert record.idempotency_key == "key-hs-1"

    # B, C. Same user + same key returns same run_id without duplicate run
    run_1_replay = use_case(user_id=USER_1, idempotency_key="key-hs-1")
    assert run_1_replay == run_1
    assert len(runs.rows) == 1

    # G. Different key creates independent run
    run_2 = use_case(user_id=USER_1, idempotency_key="key-hs-2")
    assert run_2 != run_1
    assert len(runs.rows) == 2

    # H. Different user with same key creates independent run
    run_user2 = use_case(user_id=USER_2, idempotency_key="key-hs-1")
    assert run_user2 != run_1
    assert len(runs.rows) == 3

    # I. Missing / None key creates independent non-idempotent run
    run_none_1 = use_case(user_id=USER_1, idempotency_key=None)
    run_none_2 = use_case(user_id=USER_1, idempotency_key=None)
    assert run_none_1 != run_none_2
    assert len(runs.rows) == 5

    # J. Legacy row with NULL key remains valid
    legacy_id = uuid4()
    runs.rows[legacy_id] = {
        "id": legacy_id,
        "user_id": USER_1,
        "run_type": "hairstyle",
        "status": "completed",
        "engine_version": "rules-v1",
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
        "input_media": None,
        "result": None,
        "error": None,
        "knowledge_version": None,
        "idempotency_key": None,
    }
    legacy_rec = runs.get_for_user(user_id=USER_1, run_id=legacy_id)
    assert legacy_rec is not None
    assert legacy_rec.idempotency_key is None
    # Key lookup does not collide with NULL
    assert runs.get_by_idempotency(user_id=USER_1, idempotency_key="key-hs-1").id == run_1


# ---------------------------------------------------------------------------
# Section 3: Hairstyle Image Execution Path (D, E, F, M, Mismatch)
# ---------------------------------------------------------------------------

def test_hairstyle_image_idempotency_prevents_adapter_and_side_effects():
    """D, E, F for Hairstyle image path."""
    runs = FakeRunsRepo()
    user_state = FakeUserStateRepo(None)
    port = SpyAppearancePort()
    signals = FakeLearningSignalRepo()
    knowledge = CatalogKnowledgeSource()

    use_case = CreateHairstyleImageRun(
        runs=runs,
        knowledge=knowledge,
        appearance_port=port,
        user_state=user_state,
        learning_signal=signals,
    )

    image_a = MockImage(b"test-face-image-bytes-a")

    # Initial run
    run_id = use_case(user_id=USER_1, image=image_a, idempotency_key="key-hs-img")
    assert run_id is not None
    assert port.call_count == 1
    assert user_state.update_count == 1
    assert len(signals.signals) == 1
    assert len(runs.rows) == 1

    # Replay with same image and same key
    replay_id = use_case(user_id=USER_1, image=image_a, idempotency_key="key-hs-img")
    assert replay_id == run_id

    # D. Adapter was NOT called again
    assert port.call_count == 1
    # E. Style profile was NOT updated again
    assert user_state.update_count == 1
    # F. Learning signal was NOT emitted again
    assert len(signals.signals) == 1
    # C. No additional DB row
    assert len(runs.rows) == 1

    # Payload mismatch: different image under same key -> 409 CONFLICT
    image_b = MockImage(b"different-image-bytes-b")
    with pytest.raises(ApiError) as exc_info:
        use_case(user_id=USER_1, image=image_b, idempotency_key="key-hs-img")
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "CONFLICT"


# ---------------------------------------------------------------------------
# Section 4: Outfit Image Execution Path (M, D, E, F)
# ---------------------------------------------------------------------------

def test_outfit_image_idempotency_flow():
    """Outfit image analysis idempotency path."""
    runs = FakeRunsRepo()
    user_state = FakeUserStateRepo(None)
    port = SpyAppearancePort()
    signals = FakeLearningSignalRepo()
    knowledge = CatalogKnowledgeSource()

    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=knowledge,
        appearance_port=port,
        user_state=user_state,
        learning_signal=signals,
    )

    image = MockImage(b"outfit-scan-photo")
    run_id = use_case(user_id=USER_1, image=image, idempotency_key="key-outfit-1")
    assert run_id is not None
    assert port.call_count == 1
    assert user_state.update_count == 1
    assert len(signals.signals) == 2

    # Replay
    replay_id = use_case(user_id=USER_1, image=image, idempotency_key="key-outfit-1")
    assert replay_id == run_id
    assert port.call_count == 1
    assert user_state.update_count == 1
    # F. Replay does NOT emit duplicate learning signals (still exactly 2)
    assert len(signals.signals) == 2
    assert len(runs.rows) == 1

    # Different image -> 409 conflict
    diff_image = MockImage(b"different-outfit-scan-photo")
    with pytest.raises(ApiError) as exc_info:
        use_case(user_id=USER_1, image=diff_image, idempotency_key="key-outfit-1")
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Section 5: Grooming Execution Path (M)
# ---------------------------------------------------------------------------

def test_grooming_idempotency_flow():
    """Grooming profile-only analysis idempotency path."""
    runs = FakeRunsRepo()
    user_state = FakeUserStateRepo({"face_shape": "Oval"})
    knowledge = CatalogKnowledgeSource()
    saved_looks = FakeSavedLookRepo()

    use_case = CreateGroomingRun(
        runs=runs,
        user_state=user_state,
        knowledge=knowledge,
        saved_looks=saved_looks,
    )

    run_id = use_case(user_id=USER_1, idempotency_key="key-grooming-1")
    assert run_id is not None
    assert len(runs.rows) == 1

    # Replay
    replay_id = use_case(user_id=USER_1, idempotency_key="key-grooming-1")
    assert replay_id == run_id
    assert len(runs.rows) == 1

    # Run type mismatch -> 409 conflict
    # (If the key was previously used for a hairstyle run)
    hairstyles = FakeRunsRepo()
    hairstyles.create(
        user_id=USER_1,
        run_type="hairstyle",
        idempotency_key="key-shared-type-clash",
    )
    clash_use_case = CreateGroomingRun(
        runs=hairstyles,
        user_state=user_state,
        knowledge=knowledge,
        saved_looks=saved_looks,
    )
    with pytest.raises(ApiError) as exc_info:
        clash_use_case(user_id=USER_1, idempotency_key="key-shared-type-clash")
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Section 6: Garment Execution Path (M)
# ---------------------------------------------------------------------------

def test_garment_idempotency_flow():
    """Garment analysis idempotency path."""
    runs = FakeRunsRepo()
    garment_port = SpyGarmentPort()
    use_case = CreateGarmentRun(runs=runs, garment_port=garment_port)

    image = MockImage(b"blue-denim-jacket-bytes")
    run_id = use_case(user_id=USER_1, image=image, idempotency_key="key-garment-1")
    assert run_id is not None
    assert len(runs.rows) == 1
    assert garment_port.call_count == 1

    # Replay
    replay_id = use_case(user_id=USER_1, image=image, idempotency_key="key-garment-1")
    assert replay_id == run_id
    assert len(runs.rows) == 1
    # D. Replay does NOT invoke adapter again
    assert garment_port.call_count == 1

    # Different image with same key -> 409 conflict
    diff_image = MockImage(b"red-tshirt-bytes")
    with pytest.raises(ApiError) as exc_info:
        use_case(user_id=USER_1, image=diff_image, idempotency_key="key-garment-1")
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Section 7: Concurrency & Race Handling (L)
# ---------------------------------------------------------------------------

def test_concurrent_same_key_race_resolves_to_single_run():
    """L. When two requests race, the DB IntegrityError loser safely re-reads the winner."""
    runs = FakeRunsRepo()
    user_state = FakeUserStateRepo({"face_shape": "Oval"})
    knowledge = CatalogKnowledgeSource()

    use_case = CreateHairstyleRun(runs=runs, user_state=user_state, knowledge=knowledge)

    # Prepare concurrent winner row
    winner_id = uuid4()
    runs.concurrent_winner_row = {
        "id": winner_id,
        "user_id": USER_1,
        "run_type": "hairstyle",
        "status": "pending",
        "engine_version": "rules-v1",
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
        "input_media": None,
        "result": None,
        "error": None,
        "knowledge_version": "1.1+1.0",
        "idempotency_key": "race-key-1",
    }
    # Tell the fake repo to raise IntegrityError on create
    runs.fail_next_create_with_integrity = True

    # Loser executes: initial get_by_idempotency returned None, but create() raises IntegrityError.
    # The use case catches IntegrityError and retrieves the winner.
    resolved_id = use_case(user_id=USER_1, idempotency_key="race-key-1")

    assert resolved_id == winner_id
    assert len(runs.rows) == 1


# ---------------------------------------------------------------------------
# Section 8: AnalysisRunRepositorySQL with Database Integration
# ---------------------------------------------------------------------------

def test_sql_repository_idempotency_and_uniqueness(db):
    """Test SQL implementation of AnalysisRunRepository for idempotency and unique constraint."""
    from tests.conftest import make_session

    Session = make_session()
    with Session() as session:
        repo = AnalysisRunRepositorySQL(session)

        # 1. Create with idempotency key
        run_id_1 = repo.create(
            user_id=USER_1,
            run_type="hairstyle",
            idempotency_key="sql-key-1",
        )
        assert run_id_1 is not None

        # 2. Get by idempotency
        rec = repo.get_by_idempotency(user_id=USER_1, idempotency_key="sql-key-1")
        assert rec is not None
        assert rec.id == run_id_1
        assert rec.idempotency_key == "sql-key-1"

        # 3. Different user or different key returns None
        assert repo.get_by_idempotency(user_id=USER_2, idempotency_key="sql-key-1") is None
        assert repo.get_by_idempotency(user_id=USER_1, idempotency_key="sql-key-diff") is None

        # 4. Null key creates row with None key
        run_id_null = repo.create(
            user_id=USER_1,
            run_type="hairstyle",
            idempotency_key=None,
        )
        rec_null = repo.get_for_user(user_id=USER_1, run_id=run_id_null)
        assert rec_null is not None
        assert rec_null.idempotency_key is None

