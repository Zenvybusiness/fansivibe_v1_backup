# STEP 7 — PostgreSQL Foundation Implementation (Hairstyle Vertical Slice)

**Deliverable:** the PostgreSQL schema/migrations required by the approved
hairstyle vertical slice, implemented from the finalized STEP 4 design.
**Status:** IMPLEMENTED & VERIFIED (offline). Live migration is blocked only by
the environment (no PostgreSQL reachable) — see §9.

---

## 1. Purpose and scope

Implement **only** the database foundation the approved
`STEP_7_HAIRSTYLE_IMPLEMENTATION_PLAN.md` vertical slice needs, using the
finalized STEP 4 PostgreSQL design (`POSTGRESQL_SCHEMA_V1_REVIEW.md` verdict:
all 23 logical tables approved; the slice implements the minimal subset).

Implemented:
- the required database schema/migrations (Alembic)
- approved table names, types, constraints, foreign keys, indexes
- preservation of historical AI analysis (append-only runs, TRX-5)
- preservation of user ownership (`user_id` FK composition, OW-1)
- the approved media strategy (`MediaRef`-only, no blobs)
- the approved JSONB boundaries (non-query-axis payloads only)

Explicitly **not** implemented (per the task and plan §12):
- unrelated tables (`wardrobe_items`, `user_events`, `subscriptions`,
  `feedback_events`, `recommendation_history`, `style_score_records`,
  `activity_days`, `today_look_records`, and the remaining reference tables)
- recommendation/decision logic (Stage 2+)
- any Flutter change
- any other backend feature

## 2. Source of truth (grounding)

| Document | Role |
| --- | --- |
| `docs/database/POSTGRESQL_SCHEMA_V1_REVIEW.md` | Final design review — approved tables, relationships, constraints, indexes, JSONB, media. |
| `docs/database/TABLE_DEFINITIONS.md` | Exact column-level contract (types, nullability, defaults, constraints, timestamps). |
| `docs/database/RELATIONSHIP_CONSTRAINTS.md` | FK rules (CASCADE / RESTRICT / SET NULL). |
| `docs/database/INDEX_STRATEGY.md` | The 14 approved btree indexes (+ implicit PK/`code` indexes). |
| `docs/database/HISTORY_AND_VERSIONING.md` | Never-overwrite invariant, append-only grant model (PR-5). |
| `docs/database/JSONB_STRATEGY.md` | JSONB usage boundaries (no GIN, no query axis). |
| `docs/database/MEDIA_STORAGE_DESIGN.md` | `MediaRef`-only; bytes never in PostgreSQL (PR-8). |
| `docs/database/TRANSACTION_BOUNDARIES.md` | TRX-3 save+signal, TRX-5 write-once completion, TRX-6 projection. |

## 3. What was created

### 3.1 Migration

`backend/alembic/versions/0001_initial_schema.py` (revision `0001`, the single
foundation migration):

1. Creates the **8 slice tables** (exact STEP-4 shapes).
2. **Seeds** the slice knowledge: 4 `looks` rows
   (`textured_quiff`, `classic_pompadour`, `side_part`, `brushed_up_undercut`
   — mirroring `hairstyle_mock_data.dart` and the backend catalog),
   `run_types('hairstyle')`, `signal_types('look_saved')` +
   `signal_types('analysis_updated')` (the two types the slice writes;
   remaining 6 signal types seed at their feature milestones).
3. Creates the server-side **TRX-5 write-once guard**
   `complete_analysis_run(p_run_id, p_user_id, p_status, p_result)` — the only
   permitted mutation of the append-only `analysis_runs` (UPDATE guarded by
   `status = 'pending'`, returns `true` only when exactly one row transitioned).

Supporting files (created in Stage 0, already present and verified this step):
- `backend/app/infrastructure/db/session.py` — engine/session factory, `Base`,
  `DATABASE_URL` env read (default
  `postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe`),
  FastAPI `get_db` dependency.
- `backend/app/infrastructure/db/models.py` — SQLAlchemy 2.0 ORM models for
  the same 8 tables (kept in sync with the migration).
- `backend/alembic/env.py` — Alembic env wired to the app `Base.metadata` +
  `DATABASE_URL`.
- `backend/docker-compose.yml` — `postgres:16` service (name `fansivibe`,
  user/pass `fansivibe`/`fansivibe_dev`, port 5432).
- `backend/requirements.txt` — `sqlalchemy>=2.0`, `psycopg[binary]`, `alembic`.

### 3.2 Tables (all 8, exact approved shapes)

| Table | PK | Type | Purpose (slice role) |
| --- | --- | --- | --- |
| `users` | `id uuid` | current state (P0) | account identity; root of ownership |
| `user_state` | `user_id uuid` (1:1 FK) | current state (P0) | `style_profile`/`preferences`/`flags` JSONB projection |
| `looks` | `code text` | knowledge (K9.1) | canonical hairstyle look catalog |
| `run_types` | `code text` | reference | `hairstyle` (slice) |
| `signal_types` | `code text` | reference | `look_saved`, `analysis_updated` (slice) |
| `analysis_runs` | `id uuid` | append-only history (P2) | immutable AI analysis runs |
| `saved_looks` | `id uuid` | current state (P0) | immutable saved-look snapshots |
| `learning_signals` | `id uuid` | append-only history (P0) | typed interaction history (`look_saved`) |

### 3.3 Constraints (all approved)

| Table | CHECK / UNIQUE |
| --- | --- |
| `users` | `ck_users_display_name_len` CHECK (1–100); `uq_users_auth_pair` UNIQUE (auth_provider, auth_subject) |
| `user_state` | `ck_user_state_version` CHECK (>= 0) |
| `looks` | `ck_looks_title_len` CHECK (1–200) |
| `run_types` | `ck_run_types_label_len` (1–100); `ck_run_types_sort_order` (>= 0) |
| `signal_types` | `ck_signal_types_label_len` (1–100); `ck_signal_types_sort_order` (>= 0) |
| `analysis_runs` | `ck_analysis_runs_status` CHECK (`pending`/`completed`/`failed`) |
| `saved_looks` | `ck_saved_looks_title_len` (1–200); `uq_saved_looks_idempotency` UNIQUE (user_id, idempotency_key) — slice-level extension for the contract's required Idempotency-Key replay (C-12/API-33), documented in a column COMMENT |
| `learning_signals` | `ck_learning_signals_label_len` CHECK (1–200) |

### 3.4 Foreign keys (all approved)

| Child | Column | → Parent | Rule |
| --- | --- | --- | --- |
| `user_state` | `user_id` | `users(id)` | CASCADE (1:1 composition) |
| `analysis_runs` | `user_id` | `users(id)` | CASCADE (ownership) |
| `analysis_runs` | `run_type` | `run_types(code)` | RESTRICT (knowledge) |
| `saved_looks` | `user_id` | `users(id)` | CASCADE (ownership) |
| `saved_looks` | `look_id` | `looks(code)` | SET NULL (deprecation-safe, R30) |
| `saved_looks` | `source_run_id` | `analysis_runs(id)` | SET NULL (provenance cross-link) |
| `learning_signals` | `user_id` | `users(id)` | CASCADE (ownership) |
| `learning_signals` | `signal_type` | `signal_types(code)` | RESTRICT (knowledge) |

`learning_signals` intentionally has **no FK to the triggering entity**
(`saved_looks`) — deleting current state never deletes history (§10 rule 3).

### 3.5 Indexes (approved; 4 btree added in this step)

Per `INDEX_STRATEGY.md` §3/§4, the slice's tables require:

| Index | Columns | Type | Accelerates (access pattern) | Unique |
| --- | --- | --- | --- | --- |
| `uq_users_auth_pair` | `users (auth_provider, auth_subject)` | btree | A1 auth lookup | Yes |
| `ix_analysis_runs_user_id_created_at` | `analysis_runs (user_id, created_at)` | btree | A10 scans by user/date | No |
| `ix_analysis_runs_user_id_run_type_created_at` | `analysis_runs (user_id, run_type, created_at)` | btree | A10 latest run of a type (provenance) | No |
| `ix_saved_looks_user_id_created_at` | `saved_looks (user_id, created_at)` | btree | A5 saved-looks list, newest first | No |
| `ix_learning_signals_user_id_occurred_at` | `learning_signals (user_id, occurred_at)` | btree | A6 learning feed + aggregation | No |

**This step's change:** the four non-unique btree indexes were added to
`0001_initial_schema.py` (`op.create_index` in `upgrade`, `op.drop_index` in
`downgrade`) and mirrored as `Index` declarations in
`app/infrastructure/db/models.py` so the ORM metadata and the migration stay in
sync (no autogenerate drift). They were missing from the prior committed
foundation and are now present.

Not created (approved deferrals, `INDEX_STRATEGY` §6): GIN on any JSONB,
low-selectivity single-column indexes (`status`, `run_type`, `signal_type`),
and indexes on tables outside the slice.

### 3.6 JSONB boundaries (approved)

JSONB is used only for the approved non-query-axis payloads:

| Column | Content |
| --- | --- |
| `user_state.style_profile` / `preferences` / `flags` | current-state unit payloads |
| `looks.payload` | catalog content (hairstyle fields, `scoreSeed`) |
| `analysis_runs.input_media` / `result` | `MediaRef` ref + immutable AI snapshot |
| `saved_looks.snapshot` | immutable saved-look payload (R31) |
| `learning_signals.context` | small optional event context |

No GIN, no JSON-path filter as a primary access; all query axes are relational
btree columns.

### 3.7 Media strategy (approved)

PostgreSQL stores **only `MediaRef` JSONB references** (`looks.image_ref`,
`analysis_runs.input_media`). Bytes live in object storage (M16 sealed until
MS10.3). No blobs, no media table, no FK into object storage.

### 3.8 History preservation & ownership (approved)

- `analysis_runs` is **append-only**; the only mutation is the TRX-5 guarded
  `complete_analysis_run` (write-once, status transition
  `pending → completed|failed`, never overwritten in place, PR-6).
- `learning_signals` is append-only (INSERT/SELECT at the role level, PR-5);
  `saved_looks` rows are immutable once written (R31).
- Every user-owned table is keyed/scoped by `user_id` (OW-1, 404-not-403 at the
  API); all `user_id` FKs are `ON DELETE CASCADE` (full-erasure path, PR-4).

## 4. Dependencies added (per plan D3)

`sqlalchemy>=2.0`, `psycopg[binary]`, `alembic` in `backend/requirements.txt`;
`postgres:16` dev service in `backend/docker-compose.yml`. No other dependency.

## 5. Migration structure

- `backend/alembic.ini` — script location `%(here)s/alembic`.
- `backend/alembic/env.py` — imports `DATABASE_URL` + `Base` +
  `app.infrastructure.db.models`; offline and online modes configured.
- `backend/alembic/versions/0001_initial_schema.py` — revision `0001`,
  `down_revision = None` (the single foundation migration).

## 6. What was verified

Environment limitation: **no PostgreSQL is reachable in this environment**
(no docker daemon access, no local `postgres`/`psql` binaries, no sudo). Live
migration and the DB-backed tests therefore cannot run here. Verification was
performed as follows (honest, nothing claimed beyond what ran):

1. **Migrations (offline):** `alembic upgrade --sql head` generated clean,
   complete, transaction-wrapped DDL (`/tmp/opencode/fansivibe_migration.sql`,
   166 lines) — 8 `CREATE TABLE`, 5 `CREATE INDEX` (incl. the 4 added btree),
   8 `CHECK`, 2 `UNIQUE`, 8 `FOREIGN KEY` (CASCADE/RESTRICT/SET NULL), 4 `looks`
   + 1 `run_type` + 2 `signal_type` seed `INSERT`s, and the
   `complete_analysis_run` function. Exit 0.
2. **Schema:** every column/type/nullability/default in the emitted DDL was
   cross-checked against `TABLE_DEFINITIONS.md` for the 8 tables (match).
3. **Constraints:** the `CHECK`/`UNIQUE` set matches §3.3 (match).
4. **Indexes:** the emitted `CREATE INDEX` set matches §3.5; ORM metadata
   (`Base.metadata`) renders the identical 4 btree indexes via a mock engine —
   migration ↔ models are in sync (no drift).
5. **Backend tests:** `pytest -q` → **32 passed, 17 skipped** (the 17 DB-backed
   tests skip cleanly via the `conftest.py` reachability check, as designed).
   No regressions vs the prior 32/17 baseline.
6. **Static analysis:** `pyflakes` clean on the two changed files.

### To run the live migration (requires PostgreSQL)

```bash
cd backend
docker compose up -d postgres        # or export DATABASE_URL=...
.venv/bin/alembic upgrade head
.venv/bin/python -m pytest -q        # then the 17 DB-backed tests run
```

## 7. Files changed / created in this step

**Changed:**
- `backend/alembic/versions/0001_initial_schema.py` — added the 4 approved
  btree indexes (upgrade + downgrade).
- `backend/app/infrastructure/db/models.py` — added the matching 4 `Index`
  declarations (metadata sync).

**Created (this step):**
- `docs/implementation/STEP_7_DATABASE_IMPLEMENTATION.md` — this document.

**Unchanged:** all of Flutter; the assistant surface; the API/application/
domain layers; unrelated backend features.

(Note: `backend/docker-compose.yml`, `requirements.txt`, `alembic.ini`,
`alembic/env.py`, `session.py`, and the remaining ORM/migration content existed
from Stage 0 and were verified, not re-created, in this step.)

## 8. Report

**Inspection performed:** STEP 4 design docs (POSTGRESQL_SCHEMA_V1_REVIEW,
TABLE_DEFINITIONS, INDEX_STRATEGY, RELATIONSHIP_CONSTRAINTS,
HISTORY_AND_VERSIONING, JSONB_STRATEGY, MEDIA_STORAGE_DESIGN,
TRANSACTION_BOUNDARIES), the STEP 7 plan (§8.2/§11), and the live backend
migration/models/session/conftest/docker-compose.

**Validation run:** `alembic upgrade --sql head` (clean offline DDL);
metadata-vs-migration index comparison; `pytest -q` (32 passed, 17 skipped);
`pyflakes` (clean). See §6.

**Remaining / caveats:**
- Live `alembic upgrade head` and the 17 DB-backed tests require a reachable
  PostgreSQL (`docker compose up postgres` or `DATABASE_URL`); both skip/block
  cleanly in this environment and are documented — not faked.
- Seeded vocabulary is slice-scoped by design (plan §12): `run_types` seeds only
  `hairstyle`; `signal_types` seeds the 2 the slice writes. The remaining
  `run_types` (outfit/face/grooming) and 6 signal types seed at their feature
  milestones (POSTGRESQL_SCHEMA_V1_REVIEW F5/F6).
- `learning_signals.occurred_at` carries `server_default now()` — a small,
  documented additive (the slice's save-event time equals the insert time);
  the approved table shows the column as NOT NULL without a default.
