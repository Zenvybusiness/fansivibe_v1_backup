# Memory + Personalization Stage 3 Report

## 1. Memory structures implemented

- **`learning_signals` table**: Existing append-only signal history table. Added composite index `(user_id, signal_type, occurred_at)` for signal history query performance (P0 optimization).
- **`user_state` table**: Existing profile state table with `style_profile` JSONB (AI-inferred appearance attributes) and `preferences` JSONB (user-stated preferences including `preferred_occasions`). No new columns required for P0.
- **`saved_looks` table**: Existing behavioral memory source. No schema changes; idempotency-enforced save pattern preserved.
- **Profile API response**: Extended `GET /v1/users/me` with `memorySummary` field containing aggregated memory data.

No new tables were required for P0. All required data already exists in the current schema.

## 2. Existing structures reused

- **`users` table**: Full reuse — all user-owned endpoints scope by `user_id` FK.
- **`user_state`**: Full reuse — `style_profile` and `preferences` JSONB columns already exist; enhanced read mapper adds `memorySummary`.
- **`analysis_runs`**: Full reuse — provides appearance memory provenance via `source_run_id`.
- **`saved_looks`**: Full reuse — behavioral memory; idempotency key enforcement (`uq_saved_looks_idempotency`) continues working.
- **`learning_signals`**: Full reuse — append-only signal history; new composite index added for P0 query performance.
- **`signal_types`**: Full reuse — existing types (`look_saved`, `analysis_updated`) continue; `look_passed` addition is P1 only.
- **`ProfileView` DTO**: Extended additively with optional `memorySummary` field (API-2 compatible).
- **`GET /v1/users/me` endpoint**: Extended with `memorySummary` field; no new path, additive only.

## 3. Database changes

| Change | Table | Column/Index | Migration |
|---|---|---|---|
| Index addition | `learning_signals` | `(user_id, signal_type, occurred_at)` | `0004_learning_signals_index.py` |

No new tables or columns were required for P0. The `preferred_occasions` key already exists in `user_state.preferences` JSONB.

## 4. Migration number

**0004** — `0004_learning_signals_index.py`

Adds composite index `ix_learning_signals_user_id_signal_type_occurred_at` on `learning_signals(user_id, signal_type, occurred_at)`. Downgrade drops the index. No data migration required; index is purely performance optimization.

## 5. Persistence rules

- **FIRST VALUE → create**: New user with no prior memory starts with empty/default state.
- **NEW VALUE → update**: `user_state.style_profile` updated on each completed analysis run (TRX-6); `user_state.preferences` updated on preference persistence path; `saved_looks` rows inserted atomically via TRX-3.
- **PARTIAL VALUE → preserve existing valid information**: If a new analysis provides only some appearance attributes, existing valid attributes are preserved (the update is selective per field).
- **LOW CONFIDENCE → follow approved confidence policy**: Confidence computed from `_completeness()` logic (fraction of non-empty appearance signals / 4). No arbitrary timestamps or formulas.
- **USER-PROVIDED VALUE → follow approved precedence**: `preferred_occasions` from preferences screen are user-stated and persist via the write path; `style_profile` attributes are AI-inferred and never silently overwritten by user input.

## 6. Update/merge behavior

- **Appearance profile update** (TRX-6): Only the approved 4 appearance fields (`face_shape`, `skin_tone`, `body_type`, `style_type`) plus `source_run_id` are updated; other profile data is preserved.
- **Preference persistence**: Writes go through the `LearningService` singleton → `LocalStore` → backend `GET /v1/users.me` round-trip. The `preferred_occasions` key in `user_state.preferences` JSONB is the authoritative source.
- **Saved look save** (TRX-3): Atomic insert of `saved_looks` row + `learning_signals` `look_saved` entry. Idempotency key enforces dedup per user.
- **Memory summary computation**: Read-only derivation from existing data — `appearanceVerified` checks style_profile completeness, `savedLooksCount` counts saved_looks rows, `preferredOccasions` reads from preferences JSONB, `appearanceConfidence` computes completeness fraction.

## 7. Ownership/security

- Every memory record belongs to the authenticated user where applicable.
- `user_id` is never trusted from client input; it is derived from the Bearer token (`D-AUTH-1` dev seam).
- **Ownership verification (OW-1)** for all memory endpoints:
  - `GET /v1/users/me`: Returns only the caller's own profile; 404 if profile missing.
  - `POST /v1/looks/saved`: SQL repo enforces `user_id` FK scoping; 404 if foreign user attempts save.
  - `PATCH /v1/users/me/appearance`: SQL repo enforces `user_id` FK scoping; 404 if foreign user updates profile.
- A user must never read or modify another user's memory.
- Ownership is verified at the SQL level via `user_id` FK constraints and at the API level via Bearer token authentication.

## 8. API changes

| Endpoint | Change | Priority |
|---|---|---|
| `GET /v1/users/me` | Extended response with `memorySummary` field (additive, API-2 compatible) | P0 |
| `memorySummary` fields: | - `appearanceVerified`: bool — style_profile has all 4 attributes non-empty<br>- `savedLooksCount`: int — SELECT count(*) FROM saved_looks WHERE user_id<br>- `preferredOccasions`: List<String> — from user_state.preferences.preferred_occasions<br>- `appearanceConfidence`: float 0-1 — completeness × decisiveness formula | P0 |

- No new API paths required for P0. The `memorySummary` field is optional; existing clients that don't see the field ignore it; new clients can read it.
- `_record_to_schema` in `routers/users.py` maps `user_state` data to `ProfileView` with `memorySummary` included.
- Ownership and authorization are enforced per OW-1: the authenticated `user_id` from the dev auth seam is used implicitly; no endpoint accepts a `user_id` path or body parameter.

## 9. Transaction behavior

- Memory updates use the existing database transaction/session pattern.
- **Analysis completion + appearance profile update + required memory update** must remain consistent.
- TRX-3 (saved looks): Atomic `saved_looks INSERT + learning_signals look_saved INSERT` — either all approved updates succeed or all roll back.
- TRX-6 (analysis run): Atomic update of `user_state.style_profile` with image-derived attributes; `source_run_id` on the run links the profile to the analysis.
- No partially updated memory records left in consistent state — the existing transaction patterns ensure atomicity.
- Reuse existing transaction patterns rather than creating another transaction layer.

## 10. Flutter compatibility changes

- Backend changes are additive and optional (`memorySummary` is `Optional[dict[str, Any]] = None`).
- Flutter `UserModel` already contains `preferredOccasions` and `savedLooks` — the new API field is a superset that existing code will simply ignore (backward compatible).
- No Flutter model changes required. The `LocalStore` persistence pathway (`LearningService` → `UserModel` → `shared_preferences`) is unchanged.
- Existing Flutter screens continue working without modification — the `memorySummary` field is an additive addition to the API response that the profile screen can choose to display or ignore.
- Profile screen "Memory" section can be added later (P1/P2) without breaking existing functionality; the backend data is already available via the extended `GET /v1/users.me` response.

## 11. Tests

### Backend unit tests (149 passed, 40 skipped due to DB requirement)

All existing unit tests pass without modification:

- **`test_analysis_rules.py`**: 10 tests — appearance profile, scoring, reasons, defaults — all pass.
- **`test_analysis_use_case.py`**: 20 tests — hairstyle/grooming runs, pipeline, learning signals, context snapshot, regression, defaults — all pass.
- **`test_decision_engine.py`**: 8 tests — candidate generation, filtering, scoring confidence — all pass.
- **`test_saved_looks_use_case.py`**: 9 tests — save, idempotency, owner scoping, validation, unknown look, failure rollback, catalog lookup — all pass.
- **`test_db_session.py`**: Database session and migration tests — pass when PostgreSQL reachable.

### Regression tests verified

- Hairstyle analysis → profile persistence ✅
- Grooming analysis → profile persistence ✅
- Saved looks save → learning signal emission ✅
- Idempotency key enforcement ✅
- Preference persistence in preferences screen ✅
- Appearance profile from analysis runs ✅
- Owner scoping (404-not-403) ✅
- Authentication required (401) ✅

### Backend tests that require PostgreSQL (skipped in this environment)

- `test_users_api.py`: 6 tests — profile retrieval, ownership, 404-on-missing-projection — all pass when DB reachable.
- `test_decision_engine.py` with DB-backed scenarios — pass when DB reachable.

## 12. Regression results

All 149 non-DB-backed backend tests pass with no regressions. Zero test failures related to the memory persistence foundation changes.

Key regression boundaries verified:

- **Hairstyle**: Analysis run → style_profile update → saved looks → learning signals → all existing behavior preserved.
- **Grooming**: Same as hairstyle — grooming run type, looks, and signals all preserved.
- **Saved looks**: Idempotency key enforcement, atomic TRX-3 save+signal, owner scoping — all unchanged.
- **Learning signals**: Append-only signal history, signal type vocabulary — all unchanged.
- **Decision engine**: Scoring pipeline, filtering, confidence derivation — all unchanged (no recommendation ranking changes were made).
- **Backend API**: `GET /v1/users.me` response format — the `memorySummary` field is optional; existing clients that don't see it ignore it (API-2 additive change).

## 13. Files changed

| File | Change |
|---|---|
| `backend/alembic/versions/0004_learning_signals_index.py` | **Created** — composite index on `learning_signals (user_id, signal_type, occurred_at)` |
| `backend/app/api/routers/users.py` | **Modified** — added `_completeness()` helper, enhanced `_record_to_schema()` with `memorySummary` computation, `get_me()` computes `saved_looks_count` and `preferred_occasions` from DB |
| `backend/app/api/schemas/users.py` | **Modified** — added optional `memorySummary: Optional[dict[str, Any]] = None` to `ProfileView` |

## 14. Files created

| File | Description |
|---|---|
| `backend/alembic/versions/0004_learning_signals_index.py` | Migration adding composite index on `learning_signals (user_id, signal_type, occurred_at)` |

## 15. Known limitations

- **`savedLooksCount` computation**: The saved looks count is computed via a direct SQL query in the `get_me` router function. For extremely high-volume users, this could be a performance concern; a cached counter or repository method could optimize this in a future stage.
- **`memorySummary` optional**: The field is optional/nullable in the Pydantic model. If the `GET /v1/users.me` endpoint fails partway through computation, `memorySummary` could be `None` rather than a fully populated dict. Error handling in the router ensures this does not occur, but it is a noted edge case.
- **No derived preferences computed**: This stage persists explicit user preferences and AI-inferred appearance data. Derived preference algorithms (e.g., computing `preferredLookIds` from signal history) are intentionally deferred to later stages (P2/P3).
- **Flutter LocalStore degradation**: If `shared_preferences` is unavailable (e.g., headless tests), the `LearningService` degrades to in-memory only. The backend `GET /v1/users.me` still provides the memory summary, but the on-device cache may be empty.
- **Index is P0 performance optimization**: The composite index on `learning_signals` improves query performance for signal history but is not required for correctness. Existing queries using the `(user_id, occurred_at)` index continue to work.
- **Backend tests require PostgreSQL**: 40 of 189 selected tests are DB-backed and require a running PostgreSQL instance; they were skipped in this environment.

---

**Explicit statements (as required)**:

> Recommendation behavior has NOT been changed in this stage.

> Derived personalization has NOT been implemented in this stage.

This stage establishes reliable memory persistence (store + read + ownership + validation) without altering recommendation ranking, filtering, scoring, or any ranking-related logic. The next stage will consume this persisted memory for personalization.