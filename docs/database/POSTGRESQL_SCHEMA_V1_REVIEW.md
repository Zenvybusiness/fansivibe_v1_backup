# POSTGRESQL_SCHEMA_V1 — Final Design Review

**Deliverable:** STEP 4 — FINAL DATABASE DESIGN REVIEW
**Status:** READY FOR SQL/MIGRATION DESIGN (with non-blocking clarifications)
**Reviewed against:**
- `FANSIVIBE_DOMAIN_MODEL_V1.md` (STEP 3 canonical domain model)
- STEP 2 inventories (FEATURE_DATA_MATRIX, ACTION_API_INVENTORY, DOMAIN_RELATIONSHIPS, DATA_OWNERSHIP, STORAGE_INVENTORY, SCREEN_DATA_INVENTORY)
- Live source facts (backend catalog/intent/engine, Flutter mock data, learning/assistant signal emission, onboarding/profile/discover vocabulary)

## 1. Review scope and method

This review verifies the 11 STEP 4 design documents for **internal consistency** and
**consistency with the canonical domain model and the real source of truth**:

| # | Document | Focus |
|---|----------|-------|
| 1 | DATABASE_DESIGN_RULES.md | Contracts, PR-1..PR-12 |
| 2 | DOMAIN_TABLE_MAPPING.md | Entity → table resolution |
| 3 | TABLE_DEFINITIONS.md | 23 tables, columns, PKs, defaults |
| 4 | RELATIONSHIP_CONSTRAINTS.md | FKs, delete actions, no-FK-to-trigger |
| 5 | HISTORY_AND_VERSIONING.md | Never-overwrite invariant, history |
| 6 | JSONB_STRATEGY.md | When JSONB is / is not used, no GIN |
| 7 | INDEX_STRATEGY.md | 14 btree indexes, user_id-leading |
| 8 | MEDIA_STORAGE_DESIGN.md | MediaRef, no blobs, MS10.3 gate |
| 9 | SECURITY_PRIVACY_DESIGN.md | Ownership boundary, erasure |
| 10 | BUSINESS_CONSTRAINTS.md | BC-1..BC-60 (schema keeps BC-1..BC-51) |
| 11 | TRANSACTION_BOUNDARIES.md | TRX-1..TRX-8 |

Cross-check dimensions: missing/unnecessary tables, duplicated data, incorrect
relationships, missing FKs, unsafe cascades, incorrect nullability, missing
constraints, inappropriate JSONB, missing indexes, privacy problems,
history/versioning problems, unsupported assumptions.

## 2. Source-of-truth re-verification (anchor facts)

The following facts were re-confirmed directly against the repository during this
review and are the evidentiary basis for the findings in §3.

| Fact | Evidence |
|------|----------|
| Backend look suggestions have **no stable id** — `SuggestionCard` has only `kind, title, subtitle, score, items, action` | `backend/app/models/schemas.py:51-58` |
| Backend occasion vocabulary = exactly **5**: `casual, office, date, party, travel` | `backend/app/data/catalog.py:153` |
| Flutter event-type vocabulary = **8**: `casual, formal, business, date, party, travel, workout, other` | `newproject/flutter_application_1/lib/features/events/data/event_mock_data.dart:10-31` |
| Backend outfit looks are keyed by **title** inside `OCCASION_TO_LOOK`; hairstyle/grooming/wardrobe-insight/style-tip cards are assistant cards, not looks | `backend/app/data/catalog.py:155-194` |
| Intent normalization: `work/office/meeting/interview → office`; clarification option `Office` | `backend/app/ai/intent.py:26-27,109-110`, `backend/app/ai/engine.py:30` |
| Persisted wardrobe category vocabulary = `tops, bottoms, outerwear, footwear, accessories` | `wardrobe_mock_data.dart:85,91` |
| Add-item UI codes map onto persisted vocabulary: `shoes → footwear`, `layers → outerwear` (plus a filter-only `all`) | `wardrobe_mock_data.dart:310-323` |
| Add-item palette: **18 colors**, **16 textures** | `wardrobe_mock_data.dart:414-433`, `435-452` |
| Learning signals = **5**: `item_added, analysis_updated, style_updated, look_saved, occasion_preferred` | `learning_service.dart:270-311` |
| Assistant signals = **3**: `assistant_message, suggestion_opened, assistant_navigation` | `assistant_service.dart:55,91,95` |
| → **signal_types seed = 8 total** | §3 |
| `UserModel` stores `face` (FaceProfile), `styleType`, `savedLooks: List<String>`, `preferredOccasions: List<String>` | `learning/data/models.dart:106-171` |
| Saved looks persist **only title + score** (`SavedLookPreview`); no look snapshot fields | `profile/profile_mock_data.dart` |
| Style vocabulary sources: profile mocks `Modern Minimalist` / `Classic Elegance`; discover style tags `Classic, Refined, Timeless`; occasion options `Casual, Smart Casual, Business, Formal, Streetwear` | `profile_mocks.dart:79-82,110` |
| Onboarding style vocab = `StyleVibe` enum with 6 values (gradient-backed) | `onboarding_data.dart:3-26` |
| No auth anywhere; account creation navigates home directly | Flutter auth flow |
| No feedback/like/dislike/rating feature anywhere | feature tree |
| No weather persistence anywhere | feature tree |
| Onboarding face analysis not persisted; conversation not persisted; events are widget-state only | screens + mock data |
| Navigation actions = **7** targets: open_outfit, open_hairstyle, open_grooming, open_wardrobe, open_stylist, open_daily, open_discover | `backend/app/data/catalog.py` NAVIGATION_MAP |
| Default wardrobe has 24 items with categories; items with ids 16, 18 exist | `wardrobe_mock_data.dart` |

## 3. Cross-check findings

Findings are classified **P0** (must fix before SQL design), **P1** (must resolve
before migration seed data), and **P2** (informational / accepted design decision).

| ID | Severity | Location | Finding | Resolution |
|----|----------|----------|---------|------------|
| F1 | P1 | TABLE_DEFINITIONS §6 `looks` (PK = `code`) | Backend look suggestions have **no stable code** (see anchor fact 1). `saved_looks.look_id → looks.code` and `looks` seed depend on codes that do not exist yet. | Migration step must assign stable `code` values to the 5 `OCCASION_TO_LOOK` looks (e.g. `refined-office`, `casual-look`, ...). These are the only backend looks. The hairstyle/grooming/wardrobe-insight/style-tip cards are **assistant cards, not looks** — they must NOT become `looks` rows. |
| F2 | P2 | TABLE_DEFINITIONS §6 `occasions` vs `event_types` | Two distinct vocabularies confirmed in source: backend **5** occasions (`casual, office, date, party, travel`) vs Flutter **8** event types (incl. `formal, business, workout, other`). Schema correctly models them as two reference tables. | Keep two tables. Seed `occasions` from backend list; seed `event_types` from Flutter list. Note `office` is an occasion only; `business`/`formal` are event types only. |
| F3 | P1 | `wardrobe_categories` seed | Persisted category vocabulary = 5 values (`tops/bottoms/outerwear/footwear/accessories`). UI add-item codes `shoes`/`layers`/`all` are UI-layer aliases/filters, not persisted categories. | Seed exactly the 5 canonical categories. Do not seed `shoes`/`layers`/`all`. |
| F4 | P1 | `colors`, `materials` seeds | Add-item palette provides **18 colors / 16 textures**, but the **default wardrobe items** and backend catalog use additional values (e.g. `Light Wash` denim, `Stainless Steel` watch band). Reference tables must cover the union of both. | Seed the union of palette values + default-wardrobe/backend values. |
| F5 | P1 | `signal_types` seed | Learning (5) + assistant (3) = **8** distinct signal types. | Seed exactly these 8 `signal_types` rows. |
| F6 | P2 | `run_types` seed | Schema defines `outfit / face / hairstyle / grooming`. Source analysis features today: outfit scan, hairstyle, grooming. `face` is forward-looking (FaceData exists in `UserContext`, but no face analysis feature is shipped). | Seed 4 rows; `face` is a planned capacity. Document as such, not a live feature. |
| F7 | P2 | `styles` reference table | Style vocabulary is fragmented in source: onboarding `StyleVibe` (6), profile mocks, discover tags. No single canonical source today. | Confirm seed source in migration step (recommend onboarding `StyleVibe` as canonical; map discover/profile tags to it). |
| F8 | P2 | `users` (auth columns) | No auth exists anywhere. `users.auth_provider / auth_subject` are **designed-for**, consistent with DOC-1. Schema is correct to model them now. | No change. Note account creation currently navigates home without credentials — auth is future work. |
| F9 | P2 | `feedback_events` | No feedback/like/dislike feature exists in source. Feature is P1-gated and empty-gated (row present only when feature ships). Consistent. | No change. |
| F10 | P2 | No `weather` / `conversation` / onboarding table | Confirmed: no weather persistence, conversation is transient, onboarding face analysis is not persisted, events are widget-state only. Correctly absent from schema. | No change. |
| F11 | P2 | `subscriptions`, `settings`, `notifications` (P1/P2/P3) | No source feature yet; forward-looking, correctly staged. | No change. |
| F12 | P2 | CASCADE review | 12 CASCADE / 7 RESTRICT / 5 SET NULL. Account deletion = full CASCADE erasure. No unsafe cascade chain found. | No change. |
| F13 | P2 | Index review | 14 btree indexes, all `user_id`-leading; cover the documented access patterns (wardrobe list by category, look history, events by date, subscriptions by user, etc.). No speculative index. | No change. |
| F14 | P2 | JSONB boundaries | JSONB used only for user-defined payload / never-overwrite snapshots / MediaRef refs / `looks.payload`. No GIN. No JSONB on a query axis. Matches JSONB_STRATEGY. | No change. |
| F15 | P2 | History/versioning | Never-overwrite invariant + append-only grant model (TRX-5) verified consistent. `saved_looks` stores a snapshot (per F1, `look_id` is SET NULL). | No change. |
| F16 | P2 | BC coverage | BC-1..BC-51 held; BC-52..BC-60 deferred to feature/API design. No unsupported constraint claimed at DB level. | No change. |
| F17 | P2 | TRX boundaries | TRX-1..TRX-8 map to single-write-owner operations; no cross-table multi-write claimed outside these. Matches DATA_OWNERSHIP. | No change. |

**No P0 findings.** Two findings (F1, F3–F7) are seed-data responsibilities that must
be resolved during the SQL/migration design step, not schema-structure defects.

## 4. The 11-point conclusion

### 4.1 Approved tables (all 23)
All 23 logical tables are approved as designed, with the reference-table seed
inputs from §3 (F1, F3–F7) as prerequisites:

- **Core (P0):** `users`, `analysis_runs`, `wardrobe_items`, `outfit_history`,
  `looks`, `saved_looks`
- **P1:** `user_events`, `subscriptions`, `feedback_events`, `assistant_cards`
- **P2:** `settings`, `notifications`
- **P3 (conditional):** `analytics_events`
- **Reference:** `run_types`, `occasions`, `event_types`, `wardrobe_categories`,
  `colors`, `materials`, `styles`, `signal_types`, `plans`

No unnecessary table, no missed table.

### 4.2 Rejected tables (correctly absent)
`weather`, `conversations`, `onboarding_state`, `media_assets` (blobs), any
auth/session table, any feedback-like feature table (before its P1 gate).

### 4.3 Tables requiring clarification before SQL design
None. The clarifications in §3 are **seed-data** clarifications, not structural.

### 4.4 Approved relationships
- 24 FKs total: 12 CASCADE, 7 RESTRICT, 5 SET NULL.
- `looks.code` string PK (F1) confirmed as the right key given the source has no
  numeric look ids.
- No-FK-to-trigger rule respected: `analysis_runs` results and `outfit_history`
  link only via `analysis_run_id`; no cross-feature FK into feature-internal data.
- Every FK is single-owner (one writer per table).

### 4.5 Required constraints
BC-1..BC-51 as enumerated. Notably: UNIQUE per user on `outfit_history` reference
pointers, `saved_looks`, `user_events` (identity), `subscriptions.active` single
row per user via partial unique index, not-null + check on core P0 columns,
soft-delete flag on P1/P2 tables, default JSONB `{}` where user-defined.

### 4.6 Required indexes
14 btree indexes + PK indexes; all access patterns covered. No composite
non-`user_id`-leading index invented.

### 4.7 JSONB boundaries
Approved set: `users.style_preferences`, `analysis_runs.result_payload`,
`outfit_history.snapshot`, `wardrobe_items.custom_metadata`, `looks.payload`.
No JSONB for query axes, no GIN.

### 4.8 Media strategy
`MediaRef` (object-store pointer + hash + tier) only; no blobs in Postgres.
S3/object storage lifecycle owns bytes; DB owns references. Consistent with
MEDIA_STORAGE_DESIGN.

### 4.9 Privacy strategy
- Ownership boundary: every table keyed by `user_id` (or `provider_subject`
  for `users`), all queries scoped.
- No private image data stored as blobs; only refs.
- No auth tokens or secrets anywhere in the schema.
- No feedback/analytics of personal image content.
- Account deletion = full CASCADE erasure incl. MediaRef orphan handling.

### 4.10 Migration considerations
- Forward-only, versioned migrations; single owner per table preserved.
- Seed inputs required (from §3): 5 `looks.code`, 5 `occasions`, 8 `event_types`,
  5 `wardrobe_categories`, union `colors`, union `materials`, 4 `run_types`,
  8 `signal_types`, styles from onboarding `StyleVibe`.
- `saved_looks` and `outfit_history` snapshots migrate from current profile
  mocks (`SavedLookPreview`, event mocks) where real.
- P1/P2/P3 tables and `feedback_events` created structurally but empty/gated.

### 4.11 Open questions
Resolved within the design (all answered by source facts or staging decisions):

1. Do looks have ids? → No; string `code` PK assigned by seed (F1). ✔
2. Do occasions = event types? → No; two vocabularies, two tables (F2). ✔
3. Category vocabulary union (F3, F4). ✔
4. Signal vocabulary (F5). ✔
5. What does `users` auth look like? → Designed-for; no auth yet (F8). ✔
6. Feedback/weather/conversation persistence? → Deliberately absent (F9, F10). ✔

## 5. Verdict

**STEP 4 DATABASE DESIGN COMPLETE — READY FOR SQL/MIGRATION DESIGN.**

The 11 STEP 4 documents are internally consistent and consistent with the STEP 3
domain model, STEP 2 inventories, and the live source of truth. No structural
defect was found. All open items are seed-data inputs (look codes, vocabulary
unions) that belong to the SQL/migration design step, not to the schema itself.

---

*Review performed against source as of this repository state. Findings are
anchored to the file:line evidence listed in §2.*
