# Fansivibe — Step 2 Final Report: Complete Inventory & Audit

> Consolidated output of STEP 2. Synthesizes the 12 inventory documents and
> records the final cross-check audit against the real source at
> `newproject/flutter_application_1` and `backend/`.
>
> **Status: READY FOR STEP 3 (DOMAIN MODEL DESIGN).**
> One cross-reference erratum was found during the audit and is reported in
> section 13 (it does not change the domain-model inputs).

## 1. Current product feature map

From `FEATURE_INVENTORY.md`. Thirteen Flutter features + one backend feature +
one presentation-only placeholder.

| # | Feature | Dir | Status |
| --- | --- | --- | --- |
| 1 | Onboarding | `lib/features/onboarding/` | Partially implemented (flow wired; capture simulated) |
| 2 | Home | `lib/features/home/` | UI-only; cards are mock |
| 3 | Discover | `lib/features/discover/` | UI-only; mock look catalog |
| 4 | Wardrobe | `lib/features/wardrobe/` | Local persistence works (only CRUD owner) |
| 5 | Stylist | `lib/features/stylist/` | UI-only; mock style catalog |
| 6 | Outfit Scan | `lib/features/outfit_scan/` | Mock pipeline + transient image; no real analysis |
| 7 | Outfit Builder | `lib/features/outfit_builder/` | Mock pipeline; preferences via route extra |
| 8 | Hairstyle | `lib/features/hairstyle/` | UI-only; placeholder FaceScan, mock results |
| 9 | Grooming | `lib/features/grooming/` | Mock pipeline; preferences via route extra |
| 10 | Events | `lib/features/events/` | Local signal write only; events not persisted |
| 11 | Profile | `lib/features/profile/` | UI-only; mock stats, mock saved looks |
| 12 | Assistant | `lib/features/assistant/` | Only real AI pipeline; remote + offline fallback |
| 13 | Learning | `lib/features/learning/` | Local persistence engine (wardrobe, looks, signals, style score) |
| 14 | Backend AI | `backend/` | FastAPI prototype; only `/v1/assistant/chat`; no DB/auth |
| 15 | Scan Center | `lib/features/scan_center/` | Presentation-only; deprecated flow, routes dead code |

## 2. Current screen map

From `SCREEN_DATA_INVENTORY.md`. Verified against `app_router.dart`.

- **Router:** go_router 17.2.3, single `GoRouter`, `initialLocation: '/entry'`,
  5-tab `StatefulShellRoute.indexedStack` (`/home`, `/discover`, `/stylist`,
  `/wardrobe`, `/profile`). Route names centralized in `RouteNames`.
- **41 GoRoutes / 41 path entries**; **43 screens** documented (the +2 are the
  inline first-visit branches `FirstTimeHomeScreen` / `FirstTimeLightPathHomeScreen`
  rendered inside the single `/home` route).
- **Splash registered but unreachable** — nothing navigates to `/splash`.
- **Missing-data fallbacks:** 8 route builders render a shared `FansiErrorView`
  (see erratum in section 13); `hairstyle-details` renders a blank `SizedBox`.

## 3. Current data map

From `DATA_MODEL_INVENTORY.md`. Data classification legend: **Mock** (hardcoded
constants), **Local** (SharedPreferences via `features/learning`), **Remote**
(HTTP — Assistant only), **Ephemeral** (widget state), **Route extra** (GoRouter).

- **Canonical persisted models:** `UserModel`, `WardrobeItem`,
  `SavedLookPreview`/`SavedLookDetail`, `LearningSignal`, `WardrobeSnapshot`,
  `AnalysisResult` (dead), `SavedLookSet` (dead). Persisted as one JSON blob in
  `LocalStore`.
- **Backend DTOs (mirror):** `schemas.py` ↔ `models.dart` — a deliberate,
  currently-consistent mirrored contract (gap A3.1).
- **Backend catalog:** 24 `WardrobeItem` seed entries, 6 categories/colors in
  `catalog.py` (prototype only).
- **Not yet modeled anywhere:** `User` (identity), event entity, history,
  saved-look payloads, media references.

## 4. Feature → data relationships

From `FEATURE_DATA_MATRIX.md`. Consolidated future storage mapping (rows =
feature, columns = canonical model ownership).

- Wardrobe is the single-owner feature for `WardrobeItem` (3 shape copies:
  mock data, local model, backend DTO — plus 1 alternative).
- Saved-look flows route through `LearningService.addSavedLook` regardless of
  originating screen (Daily Outfit, Discover, Outfit Analysis, Builder).
- Cross-feature access happens through public service contracts; no feature
  reaches into another feature's data layer directly.

## 5. Data ownership

From `DATA_OWNERSHIP.md`.

- **Single persistence owner:** `LearningService`/`LocalStore` owns all local
  persistence (F1.1 — KEEP).
- **Master classification** assigns exactly one owning feature per canonical
  model and one storage home per field.
- **Cross-cutting ownership rules (design constraints):** no feature accesses
  another feature's internals; UI widgets must not persist; screens must not
  call APIs directly; AI must receive typed structured data.
- **Missing concepts** (ownership pending DB design): `User`, event, history,
  media. **Ambiguous ownership** (decisions needed in Step 3): e.g. where
  assistant context/wardrobe snapshot formally lives.

## 6. AI data dependencies

From `AI_DATA_FLOW.md`.

- **Only real AI pipeline:** Assistant → `POST /v1/assistant/chat` →
  `engine.py` (system prompt + `_context_summary` of up to 12 wardrobe items) →
  typed `ChatReply` → offline mirror fallback.
- **"Face Analysis" / "Color Analysis" are marketing copy only:** the
  `allCapabilities` list flags them `active: true` (verified at
  `onboarding_data.dart:83,94`) but no computation exists anywhere.
- **Learning signals** (8 types) feed the style score; 5 are emitted by
  `learning_service.dart` (`item_added`, `analysis_updated`, `style_updated`,
  `look_saved`, `occasion_preferred`), 3 by the assistant
  (`assistant_message`, `suggestion_opened`, `assistant_navigation`).
- **Style score** (verified): `60 + wardrobe.length.clamp(0,20) +
  savedLooks.length × 2 .clamp(0,20)`.

## 7. Storage requirements

From `STORAGE_INVENTORY.md`.

- **Today:** one JSON blob (`UserModel`) in `LocalStore` (SharedPreferences).
  No database, no backend storage.
- **Special attention:** the `UserModel` blob must split before real rows exist
  (gap P7.1); media (face/outfit images) has no storage today and needs a
  privacy-aware design (MS10.3).
- **Categories to consolidate:** identity, wardrobe, saved looks, signals/history,
  preferences, media — each with a target home (relational vs object storage vs
  config catalog).

## 8. API requirements

From `ACTION_API_INVENTORY.md`.

- **32 user actions** mapped to future backend operations across 8 areas
  (auth, wardrobe, events, saved looks, discover, analysis, assistant,
  profile/subscriptions).
- **Today only 1 live endpoint:** `POST /v1/assistant/chat` (no auth, no DB).
- **Required future contracts:** typed HTTP errors
  (401/404/422/409/413/429/503) with a consistent error body; idempotency for
  save-look/save-outfit; sync semantics for `POST /users/me/sync`; offline
  capability so local data can sync later (A3.2, A3.3, E13.1).

## 9. State & edge cases

From `STATE_EDGE_CASE_INVENTORY.md`. Verified baseline + required changes.

- **Capture failure silently continues** in Outfit Scan (verifiable in router:
  `scan-processing` accepts a nullable image path) — must block + retry.
- **Missing-data fallbacks** cover 8 routes (see erratum) + blank `SizedBox`
  for hairstyle details.
- **Persist-once semantics:** `LearningService.load()` adopts persisted data only
  if `persisted.wardrobe.isNotEmpty`; event writes only add an occasion signal
  (event itself is lost).
- **No feedback/rating feature exists** anywhere.
- **Offline vs error is indistinguishable** in the Assistant (both fall back).
- **Camera edges:** FaceScan has no camera; onboarding capture is simulated.
- **Portrait lock / image handling** and signal-vocabulary drift between the 4
  event/occasion vocabularies documented as baseline risks.

## 10. Required UI/UX changes

From `UI_UX_GAP_REPORT.md`. **9 UI_CHANGE_REQUIRED, 11 UI_CHANGE_RECOMMENDED,
3 NO_UI_CHANGE** (design-system tokens are used consistently — no violations).

Top REQUIRED items: capture failure handling; Save Outfit/Save Style wiring;
Wardrobe/Event edit-delete; Profile dashboard + Saved Looks reading persisted
data instead of mocks; real camera for Face Scan and onboarding capture;
hairstyle-details error view.

## 11. Architecture gaps

From `ARCHITECTURE_GAP_REPORT.md`. **8 KEEP / 15 REQUIRED_BEFORE_BACKEND /
12 CHANGE_LATER / 7 FUTURE.**

- **KEEP (8):** single persistence owner, boundary conversion, UI-only dups,
  mirrored DTO contract, repository pattern, backend-as-prototype,
  feature-first structure, honest AI status.
- **REQUIRED_BEFORE_BACKEND (15):** session flag → user model, LocalStore
  failure path, canonical domain models, API contract + typed errors, per-feature
  repositories, ownership decisions, blob split, backend = knowledge source,
  media privacy policy, auth, anonymous→sync, user scoping, typed error contract,
  store-failure handling.
- **CHANGE_LATER (12)** and **FUTURE (7):** screen→repo decoupling, dead-model
  removal, face pipeline, versioned config, media pipeline/object storage, real
  AI confidence, multi-device — none block Step 3 domain modeling.

## 12. P0 / P1 / P2 scope

From `MVP_SCOPE.md`.

- **P0 vertical slice — "Sign in → my wardrobe → my personalized assistant":**
  auth (register/login/social + anonymous→sync), canonical persisted models,
  typed API + error contract, `POST /users/me/sync` blob split, per-feature
  repository interfaces (learning/wardrobe/assistant), wardrobe CRUD, assistant
  auth + typed errors, backend knowledge source for P0 vocab, ownership fix for
  `hasSavedWardrobeItem`, store-failure handling.
- **Explicitly NOT in P0:** real AI models, media pipeline, Discover matching,
  analysis features, events, profile stats, score/streak history, feedback,
  weather, subscription.
- **P1/P2:** core features (analysis, builder persistence, discover) then
  supporting features (events, profile, subscription); **P3** future/optional.

## 13. Open questions & audit erratum

Audit re-verified the highest-risk claims against source; all spot-checks passed
(style-score formula, 24-item wardrobe mirrors across mock/local/catalog,
`allCapabilities` flags, 8 signal types, `mockEvents` = 4, splash unreachable,
hairstyle-details `SizedBox`, `savedLooks: List<String>`, inline first-visit
home branches, greeting default name 'Alex').

**ERRATUM — FansiErrorView count (7 → 8):** `SCREEN_DATA_INVENTORY.md`,
`STATE_EDGE_CASE_INVENTORY.md`, and `UI_UX_GAP_REPORT.md` (row 20) state that
**7** detail routes render `FansiErrorView`. The router has **8** fallback sites:

| Route | app_router.dart |
| --- | --- |
| look-details | :158 |
| outfit-generation | :212 |
| grooming-processing | :277 |
| grooming-result | :294 |
| grooming-details | :313 |
| event-details | :339 |
| wardrobe-add-item | :367 |
| wardrobe-item-details | :377 |

(5 use generic `_missingDataScreen()`; 3 use `_missingDataScreenWithText`.)
This is a cross-reference counting error only — it does not change any domain
inputs. Recommend updating the "7" → "8" in the three source docs when the
docs next receive edits.

Remaining open questions carried into Step 3 (from the inventories):
1. Where does `User` (identity) formally live once auth exists?
2. Ownership of the assistant's wardrobe-context snapshot (canonical vs derived)?
3. Does the "knowledge source" become a backend catalog table or a served
   config contract for P0 vocab?
4. Event entity — is it an ownable persisted entity or a wardrobe/look trigger?

## 14. Recommendations for Step 3 (domain model design)

1. Design canonical **domain models** first (M2.1): `User`, `WardrobeItem`,
   `SavedLook`, `LearningSignal`, plus new `Event`, `AnalysisResult`, media refs —
   using the master classification in `DATA_OWNERSHIP.md` as the single-owner
   source of truth.
2. Design the **typed API + error contract** (A3.2/A3.3/E13.1) against the
   canonical models, starting with the P0 endpoints in section 12.
3. Define the **backend storage split** (P7.1): relational rows for canonical
   entities + JSONB for remaining `UserModel` fields + a decision on media.
4. Define per-feature **repository interfaces** (R4.2) so screens keep working
   while the mock→backend swap happens behind the seam.
5. Design **auth + anonymous→sync** (AU11.1/AU11.2) and the
   **`hasSavedWardrobeItem` → user-model ownership fix** (F1.4) together with
   the `User` model, since they are interdependent.
6. Resolve the four open questions in section 13 before finalizing model shapes.
7. Keep the `KEEP (8)` findings intact; do not re-architect working seams.

---

## Audit summary

- 12/12 inventory documents present and internally structured as expected.
- Spot-check verification of high-risk claims: all matched source.
- One cross-reference erratum found and reported (section 13), no scope impact.
- No blockers for domain modeling; all REQUIRED_BEFORE_BACKEND items are
  design-phase inputs, not implementation tasks.

STEP 2 COMPLETE — READY FOR DOMAIN MODEL DESIGN
