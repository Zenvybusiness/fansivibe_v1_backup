# Memory + Personalization Data Contract

## Overview

This document defines the minimum data contracts required to make Fansivibe progressively remember and personalize the user. It reuses existing infrastructure wherever possible and only proposes new columns/tables when the current model cannot represent the required memory.

The current system is classified as **LEVEL 1 — UNDERSTOOD** (verified appearance information only). The target progression is to **LEVEL 4 — PERSONALIZED** where recommendations use multiple reliable user signals (appearance + preferences + behavior).

---

## 1. Existing Tables — Reuse Assessment

### 1.1 `users`
- **Purpose**: User identity and authentication scoping
- **Ownership**: `id` is the aggregate root; all user-owned tables scope by `user_id` (OW-1)
- **Columns**: `id` (PK, UUID), `auth_provider`, `auth_subject`, `display_name`, `created_at`, `updated_at`
- **Reuse**: Full — all user-owned endpoints use `user_id` FK scoping
- **Constraints**: `UniqueConstraint(auth_provider, auth_subject)` (OW-1)

### 1.2 `user_state`
- **Purpose**: Current user profile state (mutable, versioned)
- **Columns** (existing, reused):
  - `style_profile` JSONB — `faceShape`, `skinTone`, `bodyType`, `styleType` from analysis runs
  - `preferences` JSONB — `preferred_occasions` (camelCase `preferredOccasions` on wire)
  - `flags` JSONB — feature flags, optimization switches
  - `version` int — optimistic lock version (CK: `version >= 0`)
  - `user_id` PK FK → `users.id` ON DELETE CASCADE
  - `updated_at` timestamp
- **Reuse**: Full — all profile state lives here
- **Notes**: 
  - `style_profile` is AI-inferred from analysis runs; new analysis creates new entry (append-only per PR-5)
  - `preferred_occasions` is user-stated; persists in JSONB but Flutter LocalStore persistence is G-P0-2 gap
  - `version` enables optimistic concurrency for concurrent updates

### 1.3 `analysis_runs`
- **Purpose**: Append-only history of all analysis executions
- **Columns** (existing, reused):
  - `id` (PK, UUID), `user_id` FK → `users.id`, `run_type` FK → `run_types.code`, `status`
  - `engine_version`, `input_media` JSONB, `result` JSONB, `error` JSONB
  - `created_at`, `completed_at`
- **Reuse**: Full — provides appearance memory provenance
- **Constraints**: `status IN ('pending', 'completed', 'failed')` CK
- **Indexes**: `ix_analysis_runs_user_id_created_at`, `ix_analysis_runs_user_id_run_type_created_at`

### 1.4 `saved_looks`
- **Purpose**: User-saved recommendations with idempotency
- **Columns** (existing, reused):
  - `id` (PK, UUID), `user_id` FK → `users.id` ON DELETE CASCADE
  - `look_id` FK → `looks.code` ON DELETE SET NULL
  - `title` (user-provided or catalog title)
  - `snapshot` JSONB — full run result at save time
  - `idempotency_key` unique per user (uq_saved_looks_idempotency)
  - `source_run_id` FK → `analysis_runs.id` (provenance: which analysis produced this save)
  - `created_at`
- **Reuse**: Full — behavior memory; decision engine already checks `preferredLookIds` from preferences
- **Constraints**: `CheckConstraint(title_len 1-200)`, unique `user_id + idempotency_key`
- **Indexes**: `ix_saved_looks_user_id_created_at`

### 1.5 `learning_signals`
- **Purpose**: Append-only log of all user interaction signals
- **Columns** (existing, reused):
  - `id` (PK, UUID), `user_id` FK → `users.id` ON DELETE CASCADE
  - `signal_type` FK → `signal_types.code` ON DELETE RESTRICT
  - `label` human-readable description
  - `context` JSONB — signal-specific keys (e.g. `{"run_id": "...", "run_type": "outfit"`)
  - `occurred_at`
- **Reuse**: Full — signal history; currently not consumed by decision engine (G-P0-1 gap)
- **Constraints**: `CheckConstraint(label_len 1-200)`
- **Indexes**: `ix_learning_signals_user_id_occurred_at`

### 1.6 `signal_types`
- **Purpose**: Vocabulary of allowed signal types
- **Columns** (existing, reused):
  - `code` PK, `label`, `sort_order`, `active`, `created_at`, `updated_at`
- **Reuse**: Full — existing types: `look_saved`, `analysis_updated`, `item_added`, `style_updated`, `occasion_preferred`, `assistant_message`, `suggestion_opened`, `assistant_navigation`
- **P1 Gap**: May need to add `look_passed` enum value (DB-P1-1)

### 1.7 `run_types`
- **Purpose**: Vocabulary of analysis run types
- **Columns** (existing, reused):
  - `code` PK, `label`, `sort_order`, `active`, `created_at`, `updated_at`
- **Reuse**: Full — existing types include `hairstyle`, `outfit`

### 1.8 `looks`
- **Purpose**: Catalog of hair/grooming looks (system knowledge)
- **Columns** (existing, reused):
  - `code` PK, `title`, `image_ref` JSONB, `content_version`, `published_at`, `deprecated_at`
  - `payload` JSONB, `created_at`, `updated_at`
- **Reuse**: Full — decision engine candidate source

---

## 2. Proposed New Columns / Tables

Only the following changes are required. All other required data already exists in the schema.

### 2.1 `user_state.style_profile` — provenance tracking (no new column)
- **Current**: `style_profile` JSONB stores `faceShape`, `skinTone`, `bodyType`, `styleType`
- **Enhancement**: Existing `source_run_id` provenance tracked via `saved_looks.source_run_id → analysis_runs.id`
- **Reason**: No new column needed; provenance already linked through saved looks

### 2.2 `user_state` — `preference_version` column (P3 only)
- **Proposed column**: `preference_version` int, nullable, default 0
- **Migration**: Add column with default 0; increment on preference persistence change
- **Reason**: Enables preference drift detection (G-P3-1); P0/P1 do not require this
- **Dependency**: P3 feature gate

### 2.3 `signal_types` — `look_passed` enum value (P1 only)
- **Proposed row**: `code='look_passed'`, label='Look passed', sort_order, active=true
- **Migration**: Insert into `signal_types` table; no schema change needed (code is Text PK)
- **Reason**: Required for G-P1-4 "pass/not interested" feedback loop (look_passed signal type)
- **Dependency**: P1 feature gate

### 2.4 `learning_signals` — index recommendation (P0 only)
- **Proposed index**: Composite index on `(user_id, signal_type, occurred_at)` for signal history queries
- **Reason**: Performance optimization for consuming signal history in decision engine; existing index is `(user_id, occurred_at)`
- **Migration**: Alembic migration; no data change required
- **Dependency**: P0 (quick win)

### 2.5 `recommendation_history` — optional table (P2 only)
- **Proposed table**: `recommendation_history` with columns: `id`, `user_id`, `run_id`, `look_id`, `match_score`, `confidence`, `match_reasons` JSONB, `viewed_at`, `created_at`
- **Reason**: P2 refinement; not required for P0/P1 baseline
- **Dependency**: P2 feature gate

---

## 3. Data Mutability & Ownership Rules

| Source | Table/Column | Mutable? | User-editable? | Owner |
|---|---|---|---|---|
| Analysis runs | `analysis_runs` | System (append-only) | No | System |
| Style profile | `user_state.style_profile` | System (new analysis) | No | System (AI-inferred) |
| Preferences | `user_state.preferences` | System (write path) | Yes (preferences screen) | User-stated |
| Saved looks | `saved_looks` | System (TRX-3 atomic) | Yes (save/unsave action) | User-saved |
| Learning signals | `learning_signals` | System (append-only) | No | System-derived |
| Signal types | `signal_types` | System (enum insert) | No | System |

**Key distinctions** (per audit Step 3):
- **AI-inferred**: `style_profile` attributes from analysis runs — never user-editable directly
- **User-stated**: `preferred_occasions` from preferences screen — persist via write path
- **User-saved**: `saved_looks` rows — explicit save action
- **System-derived**: completeness score, confidence, style score — computed from above

---

## 4. Provenance Rules

1. **Saved look → analysis run**: `saved_looks.source_run_id` FK → `analysis_runs.id` links any saved look back to its producing analysis run
2. **Analysis run → user state**: `CreateOutfitRun` TRX-6 updates `user_state.style_profile` with image-derived attributes; `source_run_id` on the run links the profile to the analysis
3. **Signal provenance**: `learning_signals.context` JSONB carries signal-specific keys (e.g. `{"run_id": "...", "run_type": "outfit"}` for `analysis_updated`; `{"look_id": "...", "source_context": "hairstyle"}` for `look_saved`)
4. **Preference origin**: `user_state.preferences` `preferred_occasions` stored as camelCase on wire, snake_case in DB; source attribution not currently labeled (P3-G-P3-5 enhancement)

---

## 5. Summary of Database Changes by Priority

| Priority | Change | Table | Column/Type | Migration |
|---|---|---|---|---|
| **P0** | Index addition | `learning_signals` | `(user_id, signal_type, occurred_at)` | Alembic index migration |
| **P0** | Ensure `preferred_occasions` in API response | `user_state.preferences` JSONB | No schema change | Existing; API mapper fix |
| **P1** | Add `look_passed` signal type | `signal_types` | New row (code, label, sort_order, active) | Alembic data migration |
| **P3** | Add `preference_version` column | `user_state` | `preference_version` int, default 0 | Alembic schema migration |

**No new tables required for P0/P1**. All required data exists in the current schema. P2 optional: `recommendation_history` table. P3: `preference_version` column on `user_state`.

---

## 6. Index Strategy (existing + proposed)

| Index | Table | Columns | Purpose |
|---|---|---|---|
| `uq_users_auth_pair` | `users` | `auth_provider`, `auth_subject` | Ownership scoping (OW-1) |
| `uq_saved_looks_idempotency` | `saved_looks` | `user_id`, `idempotency_key` | Idempotency enforcement (TRX-3) |
| `pk_users` | `users` | `id` | Primary key |
| `pk_user_state` | `user_state` | `user_id` | Primary key FK |
| `pk_analysis_runs` | `analysis_runs` | `id` | Primary key |
| `pk_saved_looks` | `saved_looks` | `id` | Primary key |
| `pk_learning_signals` | `learning_signals` | `id` | Primary key |
| `pk_signal_types` | `signal_types` | `code` | Primary key |
| `ix_analysis_runs_user_id_created_at` | `analysis_runs` | `user_id`, `created_at` | Run history per user |
| `ix_analysis_runs_user_id_run_type_created_at` | `analysis_runs` | `user_id`, `run_type`, `created_at` | Run type filtering |
| `ix_saved_looks_user_id_created_at` | `saved_looks` | `user_id`, `created_at` | Saved look history |
| `ix_learning_signals_user_id_occurred_at` | `learning_signals` | `user_id`, `occurred_at` | Signal timeline |
| **proposed** | `learning_signals` | `user_id`, `signal_type`, `occurred_at` | Signal history queries (P0) |