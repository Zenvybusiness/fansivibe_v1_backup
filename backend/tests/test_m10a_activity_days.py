"""M10-A foundation tests (STEP 19.14, DEC-019/DEC-020/DEC-021).

DB-backed where persistence matters (runs when PostgreSQL is reachable,
skips otherwise — see `tests/conftest.py`; schema migrates to `head`,
which includes the 0016 `activity_days` table). The C11 streak matrix
(F–M) is DB-free pure-function coverage of `derive_current_streak`.

Covers the task A–R matrix:
A. upsert creates one activity row
B. repeated same user/day write stays one row
C. upsert keeps styled=true (and never writes summary content)
D. different users remain isolated
E. different UTC days create separate rows
F. streak = 0 with no activity
G. streak = 1 for today only
H. streak = 1 for yesterday only
I. consecutive today+yesterday = 2
J. gap breaks streak
K. today unstyled but yesterday styled anchors to yesterday
L. future activity rows are ignored by streak derivation
M. first historical styled day gives streak 1
N. saved-look signal + activity_day are atomic (same commit)
O. assistant feedback signal + activity_day are atomic (API)
P. analysis signal(s) + activity_day are atomic (one day row)
Q. saved-look idempotent replay creates no duplicate activity rows
R. assistant feedback append-only behavior is unchanged (2 signals,
   still 1 day row)

Plus S: user deletion cascades to activity rows (TRX-8, PR-10).

Does NOT implement or touch `GET /v1/learning/summary` (M10-B).
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.application.learning import (
    DeriveCurrentStreak,
    derive_current_streak,
    mark_styled_today,
    utc_today,
)
from app.infrastructure.db.models import ActivityDays, LearningSignals, Users
from app.infrastructure.db.repositories import (
    ActivityDayRepositorySQL,
    LearningSignalRepositorySQL,
)
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}
FEEDBACK_PATH = "/v1/assistant/feedback"


def _today() -> date:
    return utc_today()


def _seed_user(session, subject: str):
    user = Users(
        auth_provider="m10a", auth_subject=subject, display_name="M10-A User"
    )
    session.add(user)
    session.commit()
    return user.id


def _activity_rows(session, user_id=None) -> list:
    stmt = select(ActivityDays)
    if user_id is not None:
        stmt = stmt.where(ActivityDays.user_id == user_id)
    return session.execute(stmt.order_by(ActivityDays.day.asc())).scalars().all()


def _activity_count(session, user_id=None) -> int:
    stmt = select(func.count()).select_from(ActivityDays)
    if user_id is not None:
        stmt = stmt.where(ActivityDays.user_id == user_id)
    return session.execute(stmt).scalar_one()


# ---------------------------------------------------------------------------
# A–E: repository upsert semantics (DB)
# ---------------------------------------------------------------------------


def test_A_upsert_creates_one_activity_row(db):
    """A. First upsert for a user/day creates exactly one styled row."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "a-user")
        repo = ActivityDayRepositorySQL(session)
        repo.upsert_styled_day(user_id=user_id, day=_today())
        session.commit()
        rows = _activity_rows(session, user_id)
        assert len(rows) == 1
        assert rows[0].user_id == user_id
        assert rows[0].day == _today()
        assert rows[0].styled is True
        assert rows[0].summary is None


def test_B_repeated_same_day_write_stays_one_row(db):
    """B. Repeating the upsert for the same user/day never duplicates."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "b-user")
        repo = ActivityDayRepositorySQL(session)
        repo.upsert_styled_day(user_id=user_id, day=_today())
        repo.upsert_styled_day(user_id=user_id, day=_today())
        repo.upsert_styled_day(user_id=user_id, day=_today())
        session.commit()
        assert _activity_count(session, user_id) == 1


def test_C_upsert_keeps_styled_true_and_summary_null(db):
    """C. The conflict path forces styled=true and never writes summary."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "c-user")
        session.add(
            ActivityDays(user_id=user_id, day=_today(), styled=False)
        )
        session.commit()
        repo = ActivityDayRepositorySQL(session)
        repo.upsert_styled_day(user_id=user_id, day=_today())
        session.commit()
        rows = _activity_rows(session, user_id)
        assert len(rows) == 1
        assert rows[0].styled is True
        assert rows[0].summary is None


def test_D_different_users_remain_isolated(db):
    """D. One user's day row is invisible to another user's streak read."""
    Session = make_session()
    with Session() as session:
        user_a = _seed_user(session, "d-user-a")
        user_b = _seed_user(session, "d-user-b")
        repo = ActivityDayRepositorySQL(session)
        repo.upsert_styled_day(user_id=user_a, day=_today())
        session.commit()
        assert [d for d in repo.list_styled_days(user_id=user_a)] == [_today()]
        assert repo.list_styled_days(user_id=user_b) == []
        assert _activity_count(session, user_b) == 0


def test_E_different_utc_days_create_separate_rows(db):
    """E. Distinct calendar days are distinct rows (per-day identity)."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "e-user")
        repo = ActivityDayRepositorySQL(session)
        repo.upsert_styled_day(user_id=user_id, day=_today() - timedelta(days=1))
        repo.upsert_styled_day(user_id=user_id, day=_today())
        session.commit()
        assert repo.list_styled_days(user_id=user_id) == [
            _today() - timedelta(days=1),
            _today(),
        ]


# ---------------------------------------------------------------------------
# F–M: C11 streak matrix (DB-free pure derivation, DEC-020 §D)
# ---------------------------------------------------------------------------


def test_F_streak_zero_with_no_activity():
    """F. No styled days → 0 (also through the repo-backed use case)."""
    assert derive_current_streak(styled_days=[], today=date(2026, 9, 12)) == 0
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "f-user")
        use_case = DeriveCurrentStreak(
            activity_days=ActivityDayRepositorySQL(session)
        )
        assert use_case(user_id=user_id) == 0


def test_G_streak_one_for_today_only():
    """G. Only today styled → 1 (today counts, DEC-020 §D3)."""
    today = date(2026, 9, 12)
    assert derive_current_streak(styled_days=[today], today=today) == 1


def test_H_streak_one_for_yesterday_only():
    """H. Only yesterday styled → 1 (anchor falls back to yesterday)."""
    today = date(2026, 9, 12)
    assert (
        derive_current_streak(
            styled_days=[today - timedelta(days=1)], today=today
        )
        == 1
    )


def test_I_consecutive_today_plus_yesterday_is_two():
    """I. Unbroken run ending today counts every consecutive day."""
    today = date(2026, 9, 12)
    assert (
        derive_current_streak(
            styled_days=[today - timedelta(days=1), today], today=today
        )
        == 2
    )


def test_J_gap_breaks_streak():
    """J. A missing day ends the run — only the trailing run counts."""
    today = date(2026, 9, 12)
    monday, tuesday, friday = (
        date(2026, 9, 7),
        date(2026, 9, 8),
        date(2026, 9, 11),
    )
    assert today == date(2026, 9, 12)
    assert (
        derive_current_streak(
            styled_days=[monday, tuesday, friday], today=friday
        )
        == 1
    )
    assert (
        derive_current_streak(styled_days=[monday, tuesday], today=today) == 0
    )


def test_K_unstyled_today_anchors_to_yesterday():
    """K. Today unstyled, yesterday styled → streak anchors to yesterday."""
    today = date(2026, 9, 12)
    yesterday = today - timedelta(days=1)
    assert (
        derive_current_streak(
            styled_days=[yesterday - timedelta(days=1), yesterday], today=today
        )
        == 2
    )


def test_L_future_activity_rows_are_ignored():
    """L. Days after today never contribute (pure + repo-backed paths)."""
    today = date(2026, 9, 12)
    assert (
        derive_current_streak(
            styled_days=[today + timedelta(days=1)], today=today
        )
        == 0
    )
    assert (
        derive_current_streak(
            styled_days=[today, today + timedelta(days=3)], today=today
        )
        == 1
    )
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "l-user")
        repo = ActivityDayRepositorySQL(session)
        repo.upsert_styled_day(
            user_id=user_id, day=utc_today() + timedelta(days=1)
        )
        session.commit()
        use_case = DeriveCurrentStreak(activity_days=repo)
        assert use_case(user_id=user_id) == 0


def test_M_first_historical_styled_day_gives_one():
    """M. A run of length one counts 1 — history start is included, and the
    repo→use-case path derives it from a single persisted row."""
    today = date(2026, 9, 12)
    assert derive_current_streak(styled_days=[today], today=today) == 1
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "m-user")
        repo = ActivityDayRepositorySQL(session)
        repo.upsert_styled_day(user_id=user_id, day=utc_today())
        session.commit()
        assert DeriveCurrentStreak(activity_days=repo)(user_id=user_id) == 1


# ---------------------------------------------------------------------------
# N: saved-look signal + activity_day atomicity (real SQL repos, one session)
# ---------------------------------------------------------------------------


class _FakeKnowledge:
    def lookup_hairstyle_look(self, code):
        return object()

    def lookup_grooming_look(self, code):
        return object()


class _FakeWardrobeItems:
    def get_by_id(self, *, user_id, item_id):
        return None


def _save_use_case(session):
    from app.application.saved_looks import SaveRecommendation
    from app.infrastructure.db.repositories import SavedLookRepositorySQL

    return SaveRecommendation(
        saved_looks=SavedLookRepositorySQL(session),
        signals=LearningSignalRepositorySQL(session),
        knowledge=_FakeKnowledge(),
        wardrobe_items=_FakeWardrobeItems(),
        activity_days=ActivityDayRepositorySQL(session),
    )


def test_N_saved_look_signal_and_activity_day_are_atomic(db):
    """N. Save commits look + look_saved signal + today's activity row
    together; rolling back the shared session removes signal and day."""
    from app.infrastructure.db.models import SavedLooks

    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "n-user")
        use_case = _save_use_case(session)
        saved, created = use_case(
            user_id=user_id,
            look_id=None,
            title="Evening Linen",
            snapshot={"kind": "hairstyle"},
            source_context="hairstyle",
            idempotency_key="m10a-n-1",
        )
        assert created is True
        assert session.execute(
            select(func.count()).select_from(SavedLooks)
        ).scalar_one() == 1
        assert session.execute(
            select(func.count()).select_from(LearningSignals)
        ).scalar_one() == 1
        rows = _activity_rows(session, user_id)
        assert len(rows) == 1
        assert rows[0].day == utc_today()
        assert rows[0].styled is True

    with Session() as session:
        user_id = _seed_user(session, "n-rollback-user")
        signals = LearningSignalRepositorySQL(session)
        activity = ActivityDayRepositorySQL(session)
        signals.insert_look_saved(
            user_id=user_id,
            signal_type="look_saved",
            label="rolled back",
            context={"source_context": "hairstyle", "look_id": None},
        )
        mark_styled_today(activity_days=activity, user_id=user_id)
        session.rollback()
        assert session.execute(
            select(func.count())
            .select_from(LearningSignals)
            .where(LearningSignals.user_id == user_id)
        ).scalar_one() == 0
        assert _activity_count(session, user_id) == 0


# ---------------------------------------------------------------------------
# O + R: assistant feedback API wiring (real router → real use case)
# ---------------------------------------------------------------------------


def _dev_user_id():
    Session = make_session()
    with Session() as session:
        user = session.execute(
            select(Users).where(
                Users.auth_provider == "dev", Users.auth_subject == "dev-user"
            )
        ).scalar_one_or_none()
        if user is None:
            user = Users(
                auth_provider="dev",
                auth_subject="dev-user",
                display_name="Dev User",
            )
            session.add(user)
            session.commit()
        return user.id


def _signal_count() -> int:
    Session = make_session()
    with Session() as session:
        return session.execute(
            select(func.count()).select_from(LearningSignals)
        ).scalar_one()


def _activity_count_all() -> int:
    Session = make_session()
    with Session() as session:
        return session.execute(
            select(func.count()).select_from(ActivityDays)
        ).scalar_one()


def test_O_assistant_feedback_signal_and_activity_day_are_atomic():
    """O. POST /v1/assistant/feedback → 204 + exactly one signal row and
    today's activity row (same commit, existing response unchanged)."""
    user_id = _dev_user_id()
    resp = client.post(
        FEEDBACK_PATH,
        json={"cardTitle": "Textured Quiff", "interactionType": "opened"},
        headers=HEADERS,
    )
    assert resp.status_code == 204
    assert resp.content == b""
    assert _signal_count() == 1
    Session = make_session()
    with Session() as session:
        rows = _activity_rows(session, user_id)
        assert len(rows) == 1
        assert rows[0].day == utc_today()
        assert rows[0].styled is True
        assert rows[0].summary is None


def test_R_assistant_feedback_append_only_behavior_unchanged():
    """R. Retries still append signal rows (no key) while the day row
    stays exactly one — existing B-A behavior preserved (cf. test H in
    test_assistant_feedback_api.py)."""
    _dev_user_id()
    body = {"cardTitle": "Textured Quiff", "interactionType": "opened"}
    first = client.post(FEEDBACK_PATH, json=body, headers=HEADERS)
    second = client.post(FEEDBACK_PATH, json=body, headers=HEADERS)
    assert first.status_code == 204
    assert second.status_code == 204
    assert _signal_count() == 2
    assert _activity_count_all() == 1


# ---------------------------------------------------------------------------
# P: analysis signal(s) + activity_day atomicity
# ---------------------------------------------------------------------------


class _FakeRuns:
    def __init__(self) -> None:
        self._rows: dict = {}

    def create(self, *, user_id, run_type, engine_version, input_media, knowledge_version):
        from uuid import uuid4

        run_id = uuid4()
        self._rows[run_id] = {"user_id": user_id, "run_type": run_type, "status": "pending"}
        return run_id

    def complete(self, *, run_id, user_id, status, result):
        self._rows[run_id]["status"] = status
        self._rows[run_id]["result"] = result
        return True

    def fail(self, *, run_id, user_id, error):
        self._rows[run_id]["status"] = "failed"
        return True

    def get_for_user(self, *, user_id, run_id):
        row = self._rows.get(run_id)
        if row is None or row["user_id"] != user_id:
            return None
        return row


class _MockImage:
    content_type = "image/jpeg"
    size = 1_000_000

    def __init__(self, payload: bytes = b"m10a-outfit-bytes") -> None:
        import io

        self.file = io.BytesIO(payload)


def test_P_outfit_run_signals_share_one_activity_day(db):
    """P (multi-signal). CreateOutfitRun writes analysis_updated +
    outfit_selected in one commit with exactly one activity row."""
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter
    from app.application.analysis import CreateOutfitRun
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "p-outfit-user")
        use_case = CreateOutfitRun(
            runs=_FakeRuns(),
            knowledge=CatalogKnowledgeSource(),
            appearance_port=DevelopmentAppearanceAnalysisAdapter(),
            user_state=None,
            learning_signal=LearningSignalRepositorySQL(session),
            activity_days=ActivityDayRepositorySQL(session),
        )
        run_id = use_case(user_id=user_id, image=_MockImage())
        assert run_id is not None
        assert session.execute(
            select(func.count()).select_from(LearningSignals)
        ).scalar_one() == 2
        rows = _activity_rows(session, user_id)
        assert len(rows) == 1
        assert rows[0].day == utc_today()
        assert rows[0].styled is True


class _FakeActivityDays:
    """Recording ActivityDayRepository double (no DB)."""

    def __init__(self) -> None:
        self.upserts: list = []

    def upsert_styled_day(self, *, user_id, day) -> None:
        self.upserts.append({"user_id": user_id, "day": day})

    def list_styled_days(self, *, user_id):
        return [u["day"] for u in self.upserts if u["user_id"] == user_id]


class _FakeLearningSignal:
    def __init__(self) -> None:
        self.calls: list = []
        self.commits = 0

    def insert_look_saved(self, *, user_id, signal_type="look_saved", label, context):
        self.calls.append(
            {"user_id": user_id, "signal_type": signal_type, "label": label, "context": context}
        )

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_P_hairstyle_run_marks_day_exactly_once():
    """P (single-signal). CreateHairstyleImageRun marks the UTC day exactly
    once alongside its single analysis_updated signal (no extra commit)."""
    from app.application.analysis import CreateHairstyleImageRun
    from app.domain.value_objects import AppearanceProfile
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    user_id = uuid4()

    class StubPort:
        def analyze(self, *, media_ref, user_id, image_bytes=None):
            return AppearanceProfile(
                faceShape="oval",
                skinTone="C01",
                bodyType="average",
                styleType="casual",
                sourceRunId="",
            )

        def validate_result(self, result) -> bool:
            return True

    signals = _FakeLearningSignal()
    activity = _FakeActivityDays()
    use_case = CreateHairstyleImageRun(
        runs=_FakeRuns(),
        knowledge=CatalogKnowledgeSource(),
        appearance_port=StubPort(),
        user_state=None,
        learning_signal=signals,
        activity_days=activity,
    )
    run_id = use_case(user_id=user_id, image=_MockImage(b"m10a-hair-bytes"))
    assert run_id is not None
    assert [c["signal_type"] for c in signals.calls] == ["analysis_updated"]
    assert signals.commits == 1
    assert activity.upserts == [{"user_id": user_id, "day": utc_today()}]


# ---------------------------------------------------------------------------
# Q: saved-look idempotent replay creates no duplicate activity rows
# ---------------------------------------------------------------------------


def test_Q_saved_look_replay_creates_no_duplicate_activity(db):
    """Q. Same key + same payload replays the original save with no new
    signal and no new activity row (existing C-12/API-33 behavior kept)."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "q-user")
        use_case = _save_use_case(session)
        kwargs = dict(
            user_id=user_id,
            look_id=None,
            title="Evening Linen",
            snapshot={"kind": "hairstyle"},
            source_context="hairstyle",
            idempotency_key="m10a-q-1",
        )
        first, created_first = use_case(**kwargs)
        assert created_first is True
        second, created_second = use_case(**kwargs)
        assert created_second is False
        assert second.id == first.id
        assert session.execute(
            select(func.count()).select_from(LearningSignals)
        ).scalar_one() == 1
        assert _activity_count(session, user_id) == 1


# ---------------------------------------------------------------------------
# S: account deletion cascades (TRX-8, PR-10)
# ---------------------------------------------------------------------------


def test_S_user_deletion_cascades_to_activity_rows(db):
    """S. Deleting the user row removes its activity history — no orphans."""
    from sqlalchemy import delete

    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "s-user")
        repo = ActivityDayRepositorySQL(session)
        repo.upsert_styled_day(user_id=user_id, day=utc_today())
        session.commit()
        assert _activity_count(session, user_id) == 1
        session.execute(delete(Users).where(Users.id == user_id))
        session.commit()
        assert _activity_count(session, user_id) == 0
