# Fansivibe Database Schema Audit (read-only)

**Date**: 2026-09-23
**Method**: repository config + all 21 migration files + SQLAlchemy models
+ live runtime `information_schema`/`pg_catalog` reads (SELECT-only;
no writes, no DDL, no data reads; credentials never printed).
**Verdict**: PASS WITH FINDINGS (no critical issues; M14 tables absent as required).

---

## 1. Database technology

- Primary database: **PostgreSQL** (JSONB, UUID `gen_random_uuid()`,
  `timestamptz`, plpgsql functions — all PG-specific).
- Production config: `docker-compose.production.yml` → Postgres 16
  cluster (port 5432); local dev runtime observed at `localhost:5432`
  (dev defaults only; values redacted).
- Test config: isolated database via `FANSIVIBE_TEST_DATABASE_URL`;
  without it DB-backed tests skip (never touch the authoritative DB).
- ORM: **SQLAlchemy 2.x** (`DeclarativeBase`, `mapped_column`,
  `sessionmaker`, `pool_pre_ping`, pool size/timeout/recycle settings).
- Migration framework: **Alembic** (`backend/alembic.ini`,
  `backend/alembic/env.py`, versions in `backend/alembic/versions/`).

## 2. Migration framework

Alembic, linear chain, single head. Numbering gap `0007` is
intentional (omitted revision number, not a missing file).

## 3. Current migration HEAD

**`0022`** (`0022_garment_run_type.py`). Verified three ways:
chain walk (base→…→0022), runtime `alembic_version = 0022`, full
`upgrade head` rehearsal history. Downgrades exist in 21/21 files.

| Rev | File | Change |
|---|---|---|
| 0001 | `0001_initial_schema.py` | 8 tables: users, user_state, looks, run_types, signal_types, analysis_runs, saved_looks, learning_signals; seeds (4 hairstyle looks, run/signal types); `complete_analysis_run()` fn |
| 0002 | `0002_analysis_runs_error.py` | `analysis_runs.error` JSONB + `fail_analysis_run()` fn |
| 0003 | `0003_grooming_knowledge.py` | Seed-only: grooming run type + grooming looks (v1.1) |
| 0004 | `0004_learning_signals_index.py` | Index `(user_id, signal_type, occurred_at)` |
| 0005 | `0005_wardrobe_reference_tables.py` | wardrobe_categories, colors, materials + vocab seeds |
| 0006 | `0006_wardrobe_items.py` | wardrobe_items + `(user_id)` index |
| 0008 | `0008_outfit_selected_signal_type.py` | Seed: `outfit_selected` signal type |
| 0009 | `0009_saved_looks_source_context.py` | `saved_looks.source_context` nullable + allow-list CHECK |
| 0010 | `0010_analysis_runs_knowledge_version.py` | `analysis_runs.knowledge_version` nullable |
| 0011 | `0011_looks_content_version_1_1.py` | Data-only: 4 hairstyle rows 1.0→1.1 |
| 0012 | `0012_wardrobe_wear_events.py` | wardrobe_wear_events + 2 indexes (item FK intentionally omitted) |
| 0013 | `0013_wardrobe_wear_idempotency_item.py` | Unique rescoped to `(user_id, key, wardrobe_item_id)` |
| 0014 | `0014_wardrobe_wear_groups.py` | wardrobe_wear_groups ledger |
| 0015 | `0015_assistant_card_signal_types.py` | Seed: 2 assistant signal types |
| 0016 | `0016_activity_days.py` | activity_days + owner-day unique |
| 0017 | `0017_events.py` | event_types (+8 seeds) + user_events + date index |
| 0018 | `0018_saved_looks_daily_context.py` | CHECK widened with `'daily'` (additive, no backfill) |
| 0019 | `0019_feedback_events.py` | feedback_events + FKs + unique + index |
| 0020 | `0020_auth_sessions.py` | `users.password_hash`, `users.register_idempotency_key`, user_sessions |
| 0021 | `0021_outfit_run_type.py` | Seed: `outfit` run type |
| 0022 | `0022_garment_run_type.py` | Seed: `garment` run type |

Migrations are sequential and consistent (single linear chain, no
branches, no conflicting heads).

## 4. Complete table inventory (runtime-verified, 20 tables)

Conventions everywhere: UUID PKs via `gen_random_uuid()`, `timestamptz`
`now()` defaults, `user_id → users.id ON DELETE CASCADE` for owned
rows, vocab FKs `RESTRICT`, history links `SET NULL`.

- **users** — PK id; auth_provider, auth_subject, display_name (NN);
  password_hash, register_idempotency_key (nullable); created/updated.
  UQ(auth_provider, auth_subject); CK display_name 1–100.
- **user_sessions** — PK id; user_id NN→users CASCADE; token_digest NN
  UQ (SHA-256, token never stored); created_at, expires_at NN;
  revoked_at nullable. Index (user_id, expires_at).
- **user_state** — PK user_id→users CASCADE; style_profile,
  preferences, flags JSONB NN (`'{}'`); version int NN (CK ≥ 0).
- **looks** — PK code (text); title NN (CK 1–200); image_ref nullable;
  content_version NN; published/deprecated nullable; payload JSONB NN.
- **run_types / signal_types** — PK code; label NN (CK 1–100);
  sort_order NN (CK ≥ 0); active NN; created/updated.
- **analysis_runs** — PK id; user_id NN→users CASCADE; run_type
  NN→run_types RESTRICT; status NN (CK pending/completed/failed);
  engine_version NN; knowledge_version, input_media, result, error
  nullable; created_at NN; completed_at nullable.
  Indexes (user_id, created_at), (user_id, run_type, created_at).
- **saved_looks** — PK id; user_id NN→users CASCADE; look_id
  nullable→looks SET NULL; title NN (CK 1–200); source_context nullable
  (CK ∈ hairstyle/grooming/outfit/daily, NULL passes for legacy);
  snapshot JSONB NN; idempotency_key NN; source_run_id
  nullable→analysis_runs SET NULL. UQ(user_id, idempotency_key);
  index (user_id, created_at).
- **learning_signals** — PK id; user_id NN→users CASCADE; signal_type
  NN→signal_types RESTRICT; label NN (CK 1–200); context nullable;
  occurred_at NN. Indexes (user_id, occurred_at),
  (user_id, signal_type, occurred_at).
- **wardrobe_categories / colors / materials** — PK code; label NN;
  sort_order NN; active NN; created/updated. No CHECKs in DB.
- **wardrobe_items** — PK id; user_id NN→users CASCADE; name NN;
  category_id NN→wardrobe_categories RESTRICT; color_id
  NN→colors RESTRICT; material_id nullable→materials RESTRICT;
  is_favorite NN (false); image_ref nullable. Index (user_id).
- **wardrobe_wear_events** — PK id; user_id NN→users CASCADE;
  wardrobe_item_id NN (**no FK by design**); worn_at NN;
  wear_group_id NN (**no FK**); idempotency_key NN.
  UQ(user_id, key, wardrobe_item_id); indexes (user_id, worn_at),
  (user_id, wardrobe_item_id, worn_at).
- **wardrobe_wear_groups** — PK id (= wear_group_id); user_id
  NN→users CASCADE; idempotency_key NN; item_ids JSONB NN;
  worn_at NN. UQ(user_id, idempotency_key).
- **activity_days** — PK id; user_id NN→users CASCADE; day DATE NN;
  styled NN (true); summary nullable; occurred_at NN.
  UQ(user_id, day) doubles as the streak-scan index.
- **event_types** — PK code; label NN; sort_order NN; active NN;
  created/updated. 8 frozen seeds.
- **user_events** — PK id; user_id NN→users CASCADE; title NN
  (CK 1–200); event_type_id NN→event_types RESTRICT; event_date DATE
  NN; event_time TIME nullable (wall-clock, tz-naive by design);
  location (CK 1–200 if non-null), notes (CK 1–2000 if non-null).
  Index (user_id, event_date). Duplicates allowed (no UQ beyond PK).
- **feedback_events** — PK id; user_id NN→users CASCADE;
  target_look_id nullable→looks SET NULL; target_saved_look_id
  nullable→saved_looks SET NULL; rating NN (**no CHECK by design**,
  vocab pending); reason nullable; idempotency_key NN; occurred_at NN.
  UQ(user_id, idempotency_key); index (user_id, occurred_at).
- Functions: `complete_analysis_run`, `fail_analysis_run`
  (write-once guarded mutations, user-scoped).

## 5. Relationships

users (1) → (N) user_state [1:1 by PK], user_sessions, analysis_runs,
saved_looks, learning_signals, wardrobe_items, wardrobe_wear_events,
wardrobe_wear_groups, activity_days, user_events, feedback_events —
all `ON DELETE CASCADE` (account erasure removes everything, TRX-8).
looks ← saved_looks / feedback_events (`SET NULL`, history survives).
analysis_runs ← saved_looks (`SET NULL`). run_types/signal_types/
event_types/wardrobe_categories/colors/materials ← referencing rows
(`RESTRICT`, vocab cannot be deleted under use). Wear history links
(item_id, group_id) are UUIDs **without FKs** (history survives
deletion; stale ids ignored at read).

## 6. Owner-isolation assessment

- User-owned (11): user_state, user_sessions, analysis_runs,
  saved_looks, learning_signals, wardrobe_items, wardrobe_wear_events,
  wardrobe_wear_groups, activity_days, user_events, feedback_events —
  all carry non-nullable `user_id → users.id CASCADE`.
- System-owned by design (8): users (identity root), looks,
  run_types, signal_types, wardrobe_categories, colors, materials,
  event_types — no `user_id`, contain no user data.
- Owner-scoped uniqueness where required: UQ(user_id,key) on
  saved_looks/feedback_events/wear_groups; UQ(user_id,key,item) on
  wear events; UQ(user_id,day) on activity_days; UQ(provider,subject)
  on users. All correctly scoped.
- Orphan analysis: CASCADE deletes leave no orphans on owned rows;
  `SET NULL` links null cleanly; the only unenforced links are
  wear_events.wardrobe_item_id and wear_events.wear_group_id (no FK
  by documented design — stale ids possible, ignored at read time;
  see MEDIUM finding F2).

## 7. Model/migration/schema consistency

Runtime schema matches migrations exactly (column-for-column verified).
Findings vs SQLAlchemy models (`app/infrastructure/db/models.py`):

- F1 [LOW] Model-only CHECKs without DB backing: models declare
  `ck_wardrobe_categories/colors/materials/event_types_label_len`,
  but migrations never created them and runtime lacks them. Harmless
  at runtime (model CHECKs only affect `create_all` DDL), but model
  metadata diverges from the physical schema.
- F2 [MEDIUM] `wear_events.wear_group_id` has no FK to
  `wardrobe_wear_groups.id` (STEP 15.2 predates the 0014 ledger).
  Group↔event integrity is app-enforced; the DB cannot reject
  dangling group ids or childless groups.
- F3 [MEDIUM] `users.register_idempotency_key` has no UNIQUE
  constraint; replay safety is app-enforced
  (`application/auth.py` read-then-compare). A concurrent
  double-register race could create duplicate accounts; a
  `UQ(provider, subject, register_idempotency_key)` (partial, NOT
  NULL) would close it.
- F4 [INFORMATIONAL] Models omit two physical indexes from
  `__table_args__` (0004 second learning_signals index,
  `ix_wardrobe_items_user_id`). Normal — indexes need not be
  declared in models; no runtime effect.
- F5 [INFORMATIONAL] `feedback_events.rating` deliberately has no
  CHECK (vocabulary pending, documented in 0019). Revisit when the
  feedback design freezes.
- F6 [INFORMATIONAL] `saved_looks.source_context` NULL legacy rows
  pass the CHECK by design (documented honest-unknown semantics).

## 8. M14 Trending table status

| Table | Status |
|---|---|
| trend_sources | NOT CREATED |
| trend_signals | NOT CREATED |
| trend_entities | NOT CREATED |
| trend_snapshots | NOT CREATED |
| trend_products | NOT CREATED |
| trend_product_sources | NOT CREATED |

Zero `trend_*` objects in migrations, models, or runtime. No other
Trending-related tables exist. M14 runs stateless (test adapter only).

## 9. Missing/planned tables

Only the deferred M14 set above (spec in
`docs/architecture/TRENDING_PROVIDER_VALIDATION.md` §14; migration
0023 intentionally not created). No other planned tables found.

## 10. Whether a migration is currently required

**No.** HEAD 0022 covers all models in active use; the F1–F6 findings
need decisions, not emergency DDL; M14 must stay migration-free until
a real provider credential lands.

## 11. Recommended next database milestone

1. Decide F2/F3 (add FK + partial unique, or formally accept
   app-enforcement with a regression test pinning the behavior).
2. Align F1 (drop model-only CHECKs or migrate them in).
3. When the first provider connects: migration 0023 (trend_sources,
   trend_entities, trend_snapshots, trend_items, trend_products) with
   24h-refresh retention, `(snapshot_date, region)` + `(snapshot,
   rank)` uniqueness, and hot-linked-URL-only storage.

---

```
DATABASE AUDIT STATUS: PASS WITH FINDINGS
CODE CHANGES: 0
MIGRATIONS CREATED: 0
DATABASE MODIFIED: NO
M14 TABLES CREATED: 0
```
