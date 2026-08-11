# Fansivibe — API Contract: Recommendation Feedback & Personalization Signals

> **STEP 6 — API CONTRACT DESIGN.** Defines the **field-level API contract for
> recommendation feedback and personalization signals**: the raw user feedback
> write, the assistant card-interaction signal write, and the derived
> personalization summary read — and separates **raw user feedback** from
> **derived preference signals**, supporting only the feedback actions actually
> identified in STEP 2 (action inventory) and STEP 3 (domain model). It is the
> focused companion to `API_CONTRACT_RULES.md` (§12.9 learning, §12.10
> feedback, §11 idempotency, §13 DTO sketches) and `API_INVENTORY.md`
> (endpoints 35 feedback, 17 assistant card feedback, 34 learning summary,
> 23/42/33 save), and it sits beside the sibling contracts
> `RECOMMENDATION_API.md` (the save path every recommendation funnels through,
> §4.8), `DAILY_OUTFIT_EVENTS_API.md` (D-3 save, referenced), `AUTH_API.md`
> (identity/ownership), and the assistant surface (card interaction feedback).
>
> **Status: contract design only. The feedback + personalization APIs are NOT
> implemented.** No code, no `deps.py`, no routers, no SQL migrations, no
> dependencies, no Flutter changes. The live contract (`GET /health`,
> `POST /v1/assistant/chat`) is preserved unchanged. `POST /v1/feedback` is
> **feature-gated (M11) and NOT mounted** — there is **no feedback UI today**
> (verified); it ships only when the Flutter feedback UI is accepted (API-12).
> The assistant card feedback endpoint and the learning summary stay P1 and
> **unmounted** until the auth seam (D-AUTH-1) lands (API-12) — no fake 200
> before then.
>
> **Source of truth:** the real Fansivibe repository and the accepted docs —
> the real features (`assistant_service.dart` card-interaction signals,
> `learning_service.dart` style-score derivation, `profile_mocks.dart` "Haptic
> Feedback" settings row), STEP 3 `AI_DOMAIN_MODEL.md` (§4.5 Recommendation
> Feedback, R-A13→R-A16) + `FANSIVIBE_DOMAIN_MODEL_V1.md` (E7 `LearningSignal`),
> STEP 4 `TABLE_DEFINITIONS.md` (`learning_signals`, `feedback_events`* P1,
> `signal_types`/`style_score_records`/`activity_days`) +
> `DATABASE_DESIGN_RULES.md` (PR-7 history/state split) +
> `BUSINESS_CONSTRAINTS.md` (BC-38/39, BC-41) + `TRANSACTION_BOUNDARIES.md`
> (TRX-3), STEP 5 `APPLICATION_USE_CASES.md` (UC-15 save, UC-23 assistant card
> feedback, UC-32 feedback) + `DECISION_ENGINE_ARCHITECTURE.md` (Stage 8
> Feedback, role catalogue), STEP 6 `API_CONTRACT_RULES.md`
> (§12.9/§12.10/§11/§13) + `API_INVENTORY.md` (endpoints 35/17/34/23/42/33) +
> `ACTION_API_INVENTORY.md` (#26/27/31) + `UI_UX_GAP_REPORT.md` (#17).

---

## 1. Purpose and scope

This document defines, for every **required operation** on this surface, the
contract attributes the STEP 6 design task asks for — **method, path, request
schema, response schema, validation, authorization, errors, ownership,
idempotency, and personalization effect** (plus security considerations, side
effects, and domain entities, following the same convention as the sibling
contracts). The task's coverage list is mapped operation by operation (§3,
§5):

- **LIKE / DISLIKE (rating a recommendation)** — §5.1 (F-1, **gated** —
  `POST /v1/feedback`)
- **SAVE (the real, supported feedback action)** — §5.4 (F-4, **referenced** —
  `POST /v1/looks/saved` / `POST /v1/outfits/saved` / `POST /v1/looks/today/save`)
- **IGNORE / dismiss** — §3/§4.3 (**NOT supported** — no action, UI, signal
  type, or endpoint exists)
- **WEAR (mark as worn)** — §3/§4.3 (**NOT supported** — no action or concept
  exists beyond the conditional `today_look_records` P1 decision)
- **REGENERATE** — §5.5 (F-5, **referenced** — a generation action, *not* a
  feedback signal write)
- **SHARE** — §3/§4.3 (**NOT supported** — no action, UI, or endpoint exists)
- **assistant card interaction (opened / navigated)** — §5.2 (F-2 — the only
  client-facing signal input)
- **derived personalization summary** — §5.3 (F-3, **referenced** —
  `GET /v1/learning/summary`)

**The three binding design rules of this document:**

1. **Raw user feedback and derived preference signals are separate.**
   `POST /v1/feedback` writes **append-only raw reactions**
   (`feedback_events`, the user event; R-A13) that **FEED** the derived
   preference loop **via aggregation — never as state** (R-A14→R-A15). The
   typed, backend-written `learning_signals` rows are the evidence; the
   mutable `user_state.preferences`/style profile is the derived projection
   (PR-7). The wire separates `rating`/`reason` (raw) from the learning
   summary (derived) — the client never writes a "preference" or a signal
   directly (§4.2).
2. **M10 is the sole writer of `learning_signals` (PR-7).** Signals are
   written **by the backend** from other use cases (save, analysis, events),
   never by the client directly. **No public signal-submit endpoint exists** —
   the assistant card feedback endpoint (§5.2, UC-23) is the *only*
   client-facing signal input, and it is restricted to card interactions.
3. **LIKE / DISLIKE exist only as `POST /v1/feedback` rating values; every
   other candidate action is supported exactly where the domain supports it.**
   Only **SAVE** is a real, supported feedback action today (actions
   12/14/17/22/24 → `look_saved` signal, TRX-3). **IGNORE / WEAR / SHARE have
   no action, no UI, no signal type, and no endpoint** — they are explicitly
   excluded (§3, §4.3, §8), exactly like archive/weather were excluded in the
   sibling docs. **REGENERATE** is a generation action (endpoint 32/41), not a
   feedback write.

**What it does not do:** implement anything, mount endpoints, change the frozen
assistant DTOs, invent a signal-submit or preference-write API, invent LIKE/
DISLIKE/IGNORE/WEAR/SHARE surfaces that no action/UI/UC supports, or re-own the
save path (that is referenced from `RECOMMENDATION_API.md` §4.8). The feedback
and assistant-card-feedback endpoints are owned by this doc; the save and
regenerate endpoints are referenced and kept identical to their contracts.

### 1.1 Grounding facts (re-verified)

- **There is no feedback UI today.** No rating control exists anywhere in the
  product — the only "feedback" string is the **"Haptic Feedback" settings
  toggle** (`profile_mocks.dart:248`), which is a settings row, not user
  feedback (`ACTION_API_INVENTORY.md` #31; `UI_UX_GAP_REPORT.md` #17). So
  `POST /v1/feedback` is a **derived, feature-gated requirement** (UC-32,
  endpoint 35): its contract is defined now, it is **NOT mounted** until the
  Flutter feedback UI is accepted (API-12, M11 sealed).
- **The feedback surfaces that DO exist today are client-local signals and a
  local style score.** `assistant_service.dart` records `suggestion_opened` /
  `assistant_navigation` **locally only** (`:91`, `:95` — no backend call);
  `learning_service.dart` derives a **progressive style score** (`60 + 1/wardrobe
  item (max +20) + 2/saved look (max +20)`) and records `addItem` /
  `addSavedLook` / `addPreferredOccasion` / `recordSignal` locally. The server
  surface these traces must become is the contract below.
- **`learning_signals` is the P0 append-only history** (`TABLE_DEFINITIONS.md`
  §4.3): `id`, `user_id` FK users CASCADE, `signal_type` FK `signal_types`
  RESTRICT, `label [1,200]`, `context jsonb?` (never a filter axis),
  `occurred_at`. **8 seeded signal types**: `item_added`, `analysis_updated`,
  `style_updated`, `look_saved`, `occasion_preferred`, `assistant_message`,
  `suggestion_opened`, `assistant_navigation`. Append-only INSERT/SELECT
  grants only (PR-2/PR-5). **Intentionally no FK to the triggering entity** —
  deleting current state (a saved look, a wardrobe item, an event) **never**
  deletes history (BC-41; `DATABASE_DESIGN_RULES.md` §10 rule 3).
- **`feedback_events` is a P1 row created only when the rating UI lands**
  (`TABLE_DEFINITIONS.md` §4.4): `id`, `user_id` FK users CASCADE,
  `target_look_id` FK looks SET NULL, `target_saved_look_id` FK saved_looks
  SET NULL, `rating` NOT NULL (**exact vocabulary pending the feedback design**,
  BC-38/39, PR-12), `reason?`, `occurred_at`. One concept shared by the
  wardrobe + general recommendation clusters. **FEEDS the derived-preference
  loop via aggregation, never stored as state.**
- **M10 is the sole writer of `learning_signals` (PR-7)** — "Signals are
  written by the backend (from other use cases), never by the client directly.
  There is **no** public signal-submit endpoint" (`API_CONTRACT_RULES.md`
  §12.9; `API_INVENTORY.md` §5.10). The only client-facing signal input is
  `POST /v1/assistant/feedback` (endpoint 17, UC-23):
  `AssistantCardFeedback { cardTitle|cardId, interactionType }` → 204,
  errors 401 only, P0/P1 (module P0; signal persistence P1).
- **SAVE is the real feedback action.** Saving any recommendation — daily look
  (action 12, endpoint 33), discover look (action 14, endpoint 23), scan
  generated look (action 17), hairstyle/grooming style (actions 22/24, endpoint
  23), builder outfit (action 19, endpoint 42) — is **UC-15
  `SaveRecommendation`** consolidated on `POST /v1/looks/saved` (endpoint 23;
  the builder's `POST /v1/outfits/saved` = endpoint 42). Each save is **one
  true transaction (TRX-3)**: `INSERT saved_looks` + `INSERT
  learning_signals(look_saved)`; `Idempotency-Key` required
  (`API_CONTRACT_RULES.md` §11). This is the personalization signal the task's
  SAVE action maps to — it is **referenced, not re-defined** here.
- **REGENERATE is a generation action, not a feedback write.** `POST
  /v1/looks/today` (endpoint 32) and `POST /v1/outfits/generate` (endpoint 41)
  derive a fresh value object per `?seed=`; no signal is written on generation
  itself (TRX-2). "Regenerate" is **not** a `learning_signals` type; the
  absence of a save after a regenerate is at most implicit evidence for the
  derived-preference loop — no dedicated signal/endpoint exists (§5.5).
- **The decision engine closes the loop without storing raw feedback.**
  Stage 8 Feedback (`DECISION_ENGINE_ARCHITECTURE.md` §5.8) accepts user
  feedback (card interaction, save, rating, dismiss), translates it into typed
  learning signals **via the application layer** (the engine defines the signal
  shape, never writes rows), and feeds it back into Context Builder for the
  **next** run. It is **forbidden from** writing history itself (TRX-3 persists
  it), **over-correcting** (single feedback never flips a hard rule), and
  storing raw user comments inside the engine. Role catalogue: "User feedback
  (signals: saved, opened, rated) → Feedback → Context Builder (next run)" —
  repeated "saved/dismissed" patterns adjust scores/ranking via learning
  signals; **never** flip a hard business rule instantly.
- **The task's candidate actions map to the accepted inventory exactly.**
  F-1 `POST /v1/feedback` (35, UC-32, gated); F-2 `POST /v1/assistant/feedback`
  (17, UC-23); F-3 `GET /v1/learning/summary` (34); F-4 SAVE (23/42/33,
  referenced, TRX-3); F-5 REGENERATE (32/41, referenced, generation). LIKE /
  DISLIKE are **rating values** inside F-1 — not endpoints. IGNORE / WEAR /
  SHARE are **excluded** — no action, UI, signal type, or endpoint exists.
- **Idempotency:** `POST /v1/feedback` **requires** `Idempotency-Key` **when it
  ships** (§11 keyed list). `POST /v1/assistant/feedback` is **not** in the
  keyed list — each card interaction is an append-only signal row; a retry
  appends another row, and the inventory records no key requirement (§8.4
  documents the choice). `GET /v1/learning/summary` is a read (naturally
  idempotent). SAVE is keyed (TRX-3); REGENERATE is never idempotent (each call
  derives a new value).
- **Path-collision guard:** `/v1/assistant/feedback` must be registered
  alongside `/v1/assistant/chat` under the assistant module
  (`API_CONTRACT_RULES.md` §7); `/v1/feedback` is a distinct top-level resource.
  `/v1/looks/saved` and `/v1/looks/today/save` already follow the saved-looks
  collision rules (`DAILY_OUTFIT_EVENTS_API.md` §1.1).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `ACTION_API_INVENTORY.md` | #26 Open assistant suggestion card (local `suggestion_opened` signal; future `POST /assistant/feedback`), #27 Navigate via assistant (`assistant_navigation`), #31 Submit feedback/rating (**missing feature**). |
| `UI_UX_GAP_REPORT.md` | #17 — no feedback/rating action anywhere; recommended change = lightweight like/dislike/why on AI outputs wired to future `POST /feedback`. |
| `assistant_service.dart` | The real card-interaction signals (`suggestion_opened` `:91`, `assistant_navigation` `:95`) — the client renderings of F-2's `interactionType`. |
| `learning_service.dart` | `styleScore` derivation (base 60, +1/item max +20, +2/saved look max +20), `addItem`/`addSavedLook`/`addPreferredOccasion`/`recordSignal` — grounding F-3's summary semantics. |
| `profile_mocks.dart` | `:248` "Haptic Feedback" settings row — the *only* "feedback" string; proves no rating UI exists (F-1 gated). |
| `AI_DOMAIN_MODEL.md` | §4.5 Recommendation Feedback (historical record, feature missing); R-A13 (feedback → history) → R-A14 (FEEDS → LearningSignal) → R-A15 (aggregates → derived preference) → R-A16 (derived → next decision context). |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | E7 `LearningSignal`; E8 `StyleScoreRecord`; E9 `ActivityDay`. |
| `TABLE_DEFINITIONS.md` | `learning_signals` (8 types, append-only, no FK to triggering entity), `feedback_events`* (P1 feature-gated), `signal_types` vocab, `style_score_records`; PR-1/2/3/5/7. |
| `DATABASE_DESIGN_RULES.md` | PR-7 history/current-state split; §10 rule 3 (deleting current state never deletes history); §4.3/§4.4 append-only grants. |
| `BUSINESS_CONSTRAINTS.md` | BC-38/BC-39 (feedback area), BC-41 (history survives current-state deletion), PR-12 (rating vocabulary pending). |
| `TRANSACTION_BOUNDARIES.md` | TRX-3 (save = snapshot + `look_saved` signal, one true transaction); TRX-2 (generation = computation). |
| `APPLICATION_USE_CASES.md` | UC-15 `SaveRecommendation`, UC-23 `SubmitAssistantCardFeedback` (single INSERT `learning_signals`), UC-32 `SubmitRecommendationFeedback`. |
| `DECISION_ENGINE_ARCHITECTURE.md` | Stage 8 Feedback (§5.8); role catalogue: user feedback (saved/opened/rated) → Feedback → Context Builder (next run). |
| `API_CONTRACT_RULES.md` | §12.9 learning (M10 sole writer), §12.10 feedback (gated, keyed when live), §11 idempotency list, §13 DTO sketches, §9 errors. |
| `API_INVENTORY.md` | Endpoints 35 (feedback, gated), 17 (assistant card feedback), 34 (learning summary), 23/42/33 (save, referenced), 32/41 (regenerate, referenced). |
| Sibling contracts | `RECOMMENDATION_API.md` (§4.8 save path, UC-15), `DAILY_OUTFIT_EVENTS_API.md` (D-3), `AUTH_API.md` (Bearer, OW-1), assistant surface (F-2's home). |
| `ERROR_HANDLING.md` | 12-category taxonomy: VALIDATION_ERROR (422), AUTHENTICATION_ERROR (401), NOT_FOUND (404), CONFLICT (409), RATE_LIMITED (429). |

---

## 3. Operation selection (define only the required operations)

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| F-1 | **LIKE / DISLIKE (rate a recommendation)** | **Required — gated** — `POST /v1/feedback` | UC-32, endpoint 35, action #31 (**missing feature**). Raw user reaction (`rating` = LIKE/DISLIKE value + optional `reason` + optional target). **NOT mounted** until the Flutter feedback UI is accepted (API-12, M11 sealed); `Idempotency-Key` **when it ships** (§11). §5.1. |
| F-2 | **Assistant card interaction (opened / navigated)** | **Required** — `POST /v1/assistant/feedback` | UC-23, endpoint 17, actions #26/#27. The **only client-facing signal input** (M10 sole writer, PR-7). §5.2. |
| F-3 | **Derived personalization summary** | **Required (referenced)** — `GET /v1/learning/summary` | Endpoint 34, M10. Derived `styleScore`/`breakdown`/`streak`/`recentSignals` (E7/E8/E9). §5.3. |
| F-4 | **SAVE** | **Required (referenced)** — `POST /v1/looks/saved` \| `POST /v1/outfits/saved` \| `POST /v1/looks/today/save` | UC-15, endpoints 23/42/33, actions 12/14/17/19/22/24. The real feedback action: TRX-3 snapshot + `look_saved` signal. Owned by M7 — referenced, not re-defined. §5.4. |
| F-5 | **REGENERATE** | **Required (referenced)** — `POST /v1/looks/today` \| `POST /v1/outfits/generate` | UC-16/29, endpoints 32/41, actions 13/20. A **generation** action, **not** a feedback signal write (no signal type exists). §5.5. |
| — | **IGNORE / dismiss** | **NOT defined** | Stage 8 names "dismiss" as an engine **input**, but there is no UI control, no action, no `signal_types` entry, and no endpoint — an invented surface (API-2). §4.3, §8. |
| — | **WEAR (mark as worn)** | **NOT defined** | No "worn" action, concept, signal type, or endpoint exists anywhere (only the conditional `today_look_records` P1 decision touches "today", and that is a daily-look trace, not a wear event). §4.3, §8. |
| — | **SHARE** | **NOT defined** | No share action, UI, or endpoint exists in the product (verified in the action inventory). §4.3, §8. |
| — | **Signal-submit / preference-write endpoints** | **NOT defined** | M10 is the **sole writer** of `learning_signals` (PR-7); the client never writes a signal or a preference directly — only F-2 (card interactions) and F-1 (raw reactions, gated). |

### 3.1 What this surface is (and is not)

The feedback + personalization surface is a **write-once, read-derived** loop:
raw user reactions and card interactions are append-only history; the
personalization **summary** is derived from that history + current state
(PR-7). The client-facing writes are exactly two — the gated raw-reaction
endpoint and the assistant card-interaction endpoint:

```
feedback: POST /v1/feedback                      → 201/204   (F-1; raw reaction, GATED — NOT mounted)
signal:   POST /v1/assistant/feedback            → 204       (F-2; card interaction — the only signal input)
summary:  GET  /v1/learning/summary              → LearningSummary (F-3; derived, referenced)
save:     POST /v1/looks/saved | /v1/outfits/saved | /v1/looks/today/save → SavedLook (F-4; TRX-3, referenced)
generate: POST /v1/looks/today | /v1/outfits/generate → TodayLook/OutfitRecommendation (F-5; generation, referenced)
```

There is **no** signal-submit endpoint, **no** preference-write endpoint,
**no** LIKE/DISLIKE/IGNORE/WEAR/SHARE endpoint beyond the single gated
`/v1/feedback`, and **no** dedicated "regenerate-signal" or "saved-as-worn"
write. The backend derives `learning_signals` from the other use cases (save,
analysis, events) and only F-2 lets the client surface a signal — and only for
card interactions.

---

## 4. Shared semantics (apply to every operation below)

### 4.1 Base URL, headers, format

- All endpoints under `/v1` (API-1); JSON bodies `application/json;
  charset=UTF-8`; keys camelCase; timestamps ISO-8601 UTC (API-19).
- Protected endpoints send `Authorization: Bearer <token>` (API-5). Missing /
  invalid / expired / revoked → `401 AUTHENTICATION_ERROR` +
  `WWW-Authenticate: Bearer` (API-7, ERROR_HANDLING §5.2). D-AUTH-1 gates
  mounting of every protected endpoint in this doc (API-12) — no fake 200.
- `Idempotency-Key` **required** on `POST /v1/feedback` **when it ships**
  (§4.5); **not required** on `POST /v1/assistant/feedback` (§8.4 — the
  inventory does not key it); a read on `GET /v1/learning/summary`;
  **required** on the referenced save endpoints (TRX-3); **never** on
  regenerate (each call derives a new value).
- Every response echoes `X-Request-Id` (OBSERVABILITY §4.1).

### 4.2 Raw user feedback vs derived preference signals (the core split)

This document treats the two as **separate kinds of data** with **separate
write paths**:

| Kind | Rows | Writer | Client input? | Lifetime |
| --- | --- | --- | --- | --- |
| **Raw user feedback** | `feedback_events` (P1, feature-gated) | the backend, **on F-1** (`POST /v1/feedback`, UC-32) | YES — `rating` + `reason?` + optional target | append-only; never mutated, never state |
| **Card-interaction signal** | `learning_signals` (P0) | the backend, **on F-2** (`POST /v1/assistant/feedback`, UC-23) | YES — `cardTitle/cardId` + `interactionType` | append-only; evidence for learning |
| **Derived preference signals** | `learning_signals` (P0) | **M10 only** (PR-7), from *other* use cases (save, analysis, events) | NO — never written by the client directly | append-only |
| **Derived preference state** | `user_state.preferences`, style profile projection (P0) | the backend (aggregation, R-A15) | NO — never written by the client directly | mutable current state (PR-7) |

The **wire** keeps these apart: F-1 carries `rating`/`reason` (a raw user
reaction, which FEEDS the aggregation — R-A14→R-A15); F-3 returns the
**derived** summary. No endpoint accepts a "preference" object or a raw
`learning_signals` row from the client.

### 4.3 Signal vocabulary — the 8 types (and the excluded actions)

- The `signal_type` on the wire is a **stable vocab code** (`signal_types.code`,
  PR-2), one of the **8 seeded types** (`TABLE_DEFINITIONS.md` §4.3/§5.9):
  `item_added`, `analysis_updated`, `style_updated`, `look_saved`,
  `occasion_preferred`, `assistant_message`, `suggestion_opened`,
  `assistant_navigation`.
- The assistant card feedback endpoint accepts `interactionType` that maps to
  **`suggestion_opened`** (action #26) and **`assistant_navigation`**
  (action #27) — the two client-surfaceable signal kinds. **No other
  `signal_type` is client-addressable** (M10 sole writer).
- **Excluded actions, explicitly NOT signal types or endpoints** (API-2, PR-12):
  `ignored` / `dismissed` (an engine-stage input only, never a persisted signal
  today), `worn`, and `shared`. LIKE/DISLIKE are **not** signal types either —
  they are `rating` values on the raw-reaction row (§4.4), aggregated into the
  derived preference state by the backend (R-A15), never a `signal_type` the
  client writes.

### 4.4 The wire DTOs

```
FeedbackCreate       { rating*, reason?, targetLookId?, targetSavedLookId? }   // F-1 (raw reaction)
                     //   rating: controlled vocabulary — PENDING the feedback design (BC-38/39,
                     //   PR-12); the task's LIKE/DISLIKE are rating values, not free strings.
                     //   targetLookId | targetSavedLookId: exactly one optional target (owned).
AssistantCardFeedback{ cardTitle?|cardId, interactionType* }                   // F-2 (card interaction)
                     //   interactionType: 'opened' | 'navigated' (the two signals the UI fires).
LearningSummary      { styleScore*, breakdown*, streak*, recentSignals* }      // F-3 (derived)
                     //   styleScore: derived 0–100 int (60 base, +1/item ≤20, +2/saved ≤20);
                     //   breakdown: component contributions; streak: E9 activity days;
                     //   recentSignals: last N typed signal labels (E7) — evidence, never the
                     //   raw feedback text.
```

- F-1's `rating` vocabulary is **defined by the feedback design when the UI
  ships** — this doc does **not** invent `like`/`dislike` spellings as a frozen
  contract (§8.5). `reason` is optional, bounded free text (the "why").
- F-1 targets exactly one owned resource: `targetLookId` (a catalog `looks.code`)
  **or** `targetSavedLookId` (a `saved_looks.id`) — validated for existence +
  ownership (`404-not-403`). Neither is required (a general rating is valid).
- F-3 is **derived**, never client-authored: `styleScore` follows the accepted
  progressive derivation and the `LearningService` math; the client renders it
  read-only (actions 8/28 profile).

### 4.5 Idempotency (per the frozen list, §11)

| Endpoint | `Idempotency-Key` | Why |
| --- | --- | --- |
| `POST /v1/feedback` (F-1) | **Required when it ships** | in the §11 keyed list; prevents duplicate reactions on client retry |
| `POST /v1/assistant/feedback` (F-2) | **Not keyed** | the inventory records no key; each card interaction appends an evidence row (§8.4) |
| `GET /v1/learning/summary` (F-3) | n/a (read) | naturally idempotent |
| save endpoints (F-4, referenced) | **Required** | TRX-3, in the §11 list |
| regenerate endpoints (F-5, referenced) | **Never** | each call derives a new value (like analysis submission, §11) |

### 4.6 Error body (frozen, API-28)

```
{ "error": { "code": "<one of the 12>", "message": "<safe client message>", "details": {...} } }
```

`details` is allow-listed only (ER-1): field errors + allowed values (422),
target resource ids (own resource only), `request_id` (500). **Never** another
user's data, raw feedback text beyond the request echo, provider internals, or
derived-preference internals (C-7/C-8, ER-0/ER-2).

### 4.7 Auth, ownership, privacy

| Requirement | Endpoints |
| --- | --- |
| **Auth** (Bearer → `user_id`) | `/v1/feedback` (F-1), `/v1/assistant/feedback` (F-2), `/v1/learning/summary` (F-3), and the referenced save endpoints. |
| **Public** | none on this surface (all feedback/learning data is private). |

Authorization is **owner-only (OW-1)** with **404-not-403** (API-10): a foreign
or non-existent `targetLookId`/`targetSavedLookId` → `404`, never `403` (no
existence leak). A user's feedback, signals, and derived summary are **never**
served from another user's data. Feedback `reason` and card labels are
privacy-sensitive (Fansivibe privacy rule): the client never logs them; the
API never echoes them beyond the request/response pair; the derived summary
never includes raw feedback text.

### 4.8 Personalization effect (how feedback changes future decisions)

Each feedback write closes the loop exactly as `DECISION_ENGINE_ARCHITECTURE.md`
defines it (§5.8 Stage 8 + §6 role catalogue):

- **SAVE (F-4)** → `look_saved` signal → repeated saved patterns **boost**
  look/outfit scoring and ranking for the user (via learning signals → Context
  Builder next run). This is the strongest, supported personalization signal.
- **Card interaction (F-2)** → `suggestion_opened` / `assistant_navigation`
  signals → the assistant's future suggestions adapt to which cards the user
  opens and where they navigate.
- **Raw reaction (F-1, gated)** → `feedback_events` → **aggregated** by the
  backend (R-A15) into the derived preference state, which the next decision
  context reads (R-A16). A single LIKE/DISLIKE **never** flips a hard rule or a
  score instantly (no over-correcting, §5.8); only repeated patterns adjust
  scores/ranking.
- **REGENERATE (F-5)** has **no direct personalization effect** — it is a
  generation action. Its only influence is implicit: regenerating without
  saving is weak negative evidence the backend *may* aggregate (no signal is
  written on generation; no over-correcting).
- **Hard limits:** feedback never writes history itself (TRX-3 persists it in
  the application layer), never flips a hard business rule, and never stores
  raw user comments inside the engine (§5.8).

---

## 5. Operation contracts

### 5.1 F-1 — Submit recommendation feedback (`SubmitRecommendationFeedback`, UC-32, endpoint 35 — **gated**)

- **Method / path:** `POST /v1/feedback`
- **Status:** **GATED — NOT mounted.** No feedback UI exists (verified:
  `ACTION_API_INVENTORY.md` #31, `UI_UX_GAP_REPORT.md` #17); the endpoint stays
  unmounted until the Flutter feedback UI is accepted (API-12, M11 sealed).
  Contract defined now so the UI wires to a frozen shape.
- **Request schema** (`FeedbackCreate`, §4.4):

```
{
  "rating": "like",                     // required — controlled vocabulary (PENDING the feedback
                                        //   design; LIKE/DISLIKE values are the task's actions)
  "reason": "Prefers lighter layers",   // optional — bounded free text ("why")
  "targetLookId": "smart_casual_01",    // optional — catalog looks.code (owned)
  "targetSavedLookId": "uuid",          // optional — saved_looks.id (owned); at most one target
}
```

- **Response schema:** `201 Created` (when a representation is meaningful) or
  `204 No Content` (accepted ack) — the inventory lists both (`201/204`).
- **Validation:** `rating` must be a value of the accepted vocabulary (→ `422`
  with allowed values in `details`; exact set pending §16/§8.5); `reason`
  bounded; `targetLookId`/`targetSavedLookId` — at most one, valid + **owned**
  (foreign/non-existent → `404-not-403`).
- **Authorization:** **auth** (Bearer); **owner** (OW-1; 404-not-403 on
  targets).
- **Errors:** `201/204`; `401`; `404 NOT_FOUND` (target not owned/never
  existed); `422 VALIDATION_ERROR` (rating vocab/bounds/target cardinality);
  `429 RATE_LIMITED`.
- **Security considerations:** no internals; the `reason` is privacy-sensitive
  and never echoed outside the pair; no existence leak via targets.
- **Side effects:** **append-only INSERT `feedback_events`** (P1 — the table
  exists only when the feature lands). The reaction **FEEDS** the
  derived-preference aggregation (R-A14→R-A15); it never rewrites the target
  run/snapshot/ranking. `Idempotency-Key` **required when it ships** (§4.5).
- **Personalization effect:** repeated LIKE/DISLIKE patterns are aggregated
  into the derived preference state (R-A15), which the next decision context
  reads (R-A16) — **gradual**, never a single-event flip (§4.8).
- **Domain entities involved:** `FeedbackEvent` (value object); E7
  `LearningSignal` (optional link, R-A14); E4 `SavedLook` / E5 `Look`
  (optional targets, SET NULL FKs).

### 5.2 F-2 — Submit assistant card feedback (`SubmitAssistantCardFeedback`, UC-23, endpoint 17)

- **Method / path:** `POST /v1/assistant/feedback`
- **Request schema** (`AssistantCardFeedback`, §4.4):

```
{
  "cardId": "look_suggestion_04",   // optional — the suggestion card id/title
  "interactionType": "opened"       // required — 'opened' | 'navigated' (the two card signals)
}
```

- **Response schema:** `204 No Content`.
- **Validation:** `interactionType` must be one of the two supported values →
  `422`; `cardTitle/cardId` bounded. Existence/ownership of a card is not
  required (cards are ephemeral suggestions).
- **Authorization:** **auth** (Bearer); **owner** (OW-1) — always the caller's
  own interaction.
- **Errors:** `204`; `401` (only, per the inventory); `422 VALIDATION_ERROR`
  (bad interaction type); `429 RATE_LIMITED`.
- **Security considerations:** no internals; the card reference is the
  interaction's own content, never another user's data.
- **Side effects:** **single append-only INSERT `learning_signals`** (tier 1,
  UC-23 canonical) with `signal_type` = `suggestion_opened` (action #26) or
  `assistant_navigation` (action #27) and `label` = the card reference. **This
  is the only client-facing signal input** (M10 sole writer, PR-7 — the client
  never names a `signal_type`; it supplies an interaction and the backend maps
  it). P0/P1: module P0, signal persistence P1.
- **Personalization effect:** the opened/navigated pattern tunes the
  assistant's future suggestions via Context Builder (next run) — §4.8.
- **Domain entities involved:** E7 `LearningSignal` (via M10 seam).

### 5.3 F-3 — Get learning summary (`GetLearningSummary`, endpoint 34 — referenced, M10)

- **Method / path:** `GET /v1/learning/summary`
- **Status:** **referenced** — owned by M10 (`API_INVENTORY.md` §5.10,
  `API_CONTRACT_RULES.md` §12.9); defined here for the personalization read the
  task asks for. Stays P1 and unmounted until D-AUTH-1 (API-12).
- **Request schema:** none.
- **Response schema:** `200 OK` — `LearningSummary { styleScore, breakdown,
  streak, recentSignals }` (§4.4). **Derived** — styleScore follows the
  accepted 0–100 progressive derivation; recentSignals are typed labels (E7),
  **never raw feedback text**.
- **Validation:** none (read).
- **Authorization:** **auth** (Bearer); **owner** (OW-1) — always the caller's
  own summary.
- **Errors:** `200`; `401`; `429 RATE_LIMITED`.
- **Security considerations:** derived from the caller's own history + current
  state only; never includes another user's data or raw `reason` text.
- **Side effects:** none — a pure read.
- **Personalization effect:** n/a (a read); it *surfaces* the result of the
  feedback loop (style score, streak, recent signals) for the profile screens
  (actions 8/28).
- **Domain entities involved:** E7 `LearningSignal`; E8 `StyleScoreRecord`;
  E9 `ActivityDay`.

### 5.4 F-4 — Save (referenced, owned by M7)

- **Method / path:** `POST /v1/looks/saved` (endpoint 23, UC-15) · `POST
  /v1/outfits/saved` (endpoint 42, UC-30) · `POST /v1/looks/today/save`
  (endpoint 33, the daily surface's save path).
- **Status:** **referenced** — the task's SAVE action; owned by M7
  (`RECOMMENDATION_API.md` §4.8, `DAILY_OUTFIT_EVENTS_API.md` §5.3). Not
  re-defined here.
- **Request schema:** the type DTO snapshot verbatim + `sourceContext` +
  **`Idempotency-Key` required** (TRX-3).
- **Response schema:** `201 Created` — `SavedLook`.
- **Validation:** snapshot structural validity + title `[1,200]` (BC-11) →
  `422`.
- **Authorization:** **auth** (Bearer); **owner** (OW-1).
- **Errors:** `201`; `401`; `404`; `409 CONFLICT` (duplicate); `422`;
  `429 RATE_LIMITED`.
- **Side effects:** **one true transaction (TRX-3)**: `INSERT saved_looks` +
  `INSERT learning_signals(look_saved)`.
- **Personalization effect:** the `look_saved` signal is the strongest
  supported personalization input — repeated saves boost future look/outfit
  scoring and ranking (§4.8, §3.1).
- **Domain entities involved:** E4 `SavedLook`; E7 `LearningSignal`.

### 5.5 F-5 — Regenerate (referenced, a generation action — NOT feedback)

- **Method / path:** `POST /v1/looks/today` (endpoint 32, UC-16, action 13) ·
  `POST /v1/outfits/generate` (endpoint 41, UC-28/29, actions 18/20).
- **Status:** **referenced** — the task's REGENERATE action; owned by M9/M13.
  Kept **out of this surface's write set**: regenerating is a **generation
  action**, and **no feedback signal is written on it** (TRX-2; there is no
  `regenerated` signal type — §4.3).
- **Request schema:** `?seed=` (optional; produces a different result per
  seed) — see `DAILY_OUTFIT_EVENTS_API.md` §5.2 / `RECOMMENDATION_API.md`.
- **Response schema:** `200 OK` — a fresh `TodayLook` / `OutfitRecommendation`.
- **Authorization:** **auth** (Bearer); **owner**.
- **Errors:** `200`; `401`; `422`; `503 EXTERNAL_SERVICE_FAILURE`
  (generation — C-8: no provider internals); `429`.
- **Side effects:** none persistent — a regenerable computation (TRX-2). **Not
  idempotent**.
- **Personalization effect:** none direct. The only *implicit* evidence is the
  user regenerating **without saving**; the backend may aggregate that weakly
  (never a hard flip, §4.8) but no signal or endpoint exists today (§8.6).
- **Domain entities involved:** today's look / outfit (value objects); E2/E5.

### 5.6 The feedback + learning flow (a sequence of the accepted endpoints — no new endpoint)

```
raw:     POST /v1/feedback (F-1; GATED — not mounted until the feedback UI)  → 201/204
          └─ INSERT feedback_events (P1) ──FEEDS──► derived preference aggregation (R-A15)
signal:  POST /v1/assistant/feedback (F-2; the only client-facing signal input) → 204
          └─ INSERT learning_signals (suggestion_opened | assistant_navigation)
save:    POST /v1/looks/saved | /v1/outfits/saved | /v1/looks/today/save (F-4; referenced)
          └─ TRX-3: INSERT saved_looks + INSERT learning_signals(look_saved)
generate: POST /v1/looks/today | /v1/outfits/generate (F-5; referenced — NO signal written)
summary: GET  /v1/learning/summary (F-3; derived read) → LearningSummary
          └─ reads E7/E8/E9 (history + current state), never raw feedback text
personalize: next decision (Context Builder) reads the derived preference state (R-A16)
```

---

## 6. Validation reference (shared)

| Field | Rules | Source |
| --- | --- | --- |
| `rating` (F-1) | required, accepted vocabulary → 422 + allowed values (**exact set pending the feedback design**, BC-38/39, PR-12) | §16 / §8.5, UC-32 |
| `reason` (F-1) | optional bounded free text ("why") | §4.4, feedback design |
| `targetLookId` | optional catalog `looks.code`, valid + owned → 404-not-403 | §4.4, TABLE_DEFINITIONS `looks` |
| `targetSavedLookId` | optional `saved_looks.id`, valid + owned → 404-not-403 | §4.4, TABLE_DEFINITIONS `saved_looks` |
| target cardinality | **at most one** target per reaction → 422 | §4.4 |
| `interactionType` (F-2) | required, one of `opened`/`navigated` → 422 | UC-23, §4.4 |
| `cardTitle`/`cardId` (F-2) | optional, bounded | §4.4 |
| `signal_type` (labels) | always backend-mapped; the client never names a type | PR-7, §4.3 |
| `LearningSummary` fields | derived, never client-authored; `recentSignals` = typed labels only | §4.4, E7/E8/E9 |
| `snapshot` (F-4 save) | the type DTO verbatim; structural validity at save time | R31, BC-11 |

All validation is **server-side** (Flutter never enforces security) and
returns the **safe client message**, never internals (ER-2).

---

## 7. Error reference for this surface

| `error.code` | HTTP | When | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | bad `rating`/vocab, bad `interactionType`, reason/target bounds, target cardinality | field errors + allowed values in `details` |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | feedback/save target not owned or never existed; account gone | 404-not-403, no existence leak |
| `CONFLICT` | 409 | duplicate save (F-4, referenced) | `details.kind` |
| `RATE_LIMITED` | 429 | any endpoint | + `Retry-After` |

F-1/F-2/F-3 and the referenced save endpoints never surface raw feedback text,
provider internals, or derived-preference internals (C-7/C-8, ER-0/ER-2).

---

## 8. Open decisions (carried forward, unchanged where already recorded)

1. **D-AUTH-1 — auth provider** — unchanged; gates mounting the P1 feedback/
   learning surfaces (endpoints stay unmounted until the seam lands, API-12).
2. **Feedback UI** — `POST /v1/feedback` (UC-32) is gated on an **accepted
   Flutter feedback UI** (M11 sealed); no fake 200 before then (API-12).
   `UI_UX_GAP_REPORT.md` #17 recommends lightweight like/dislike/why on AI
   outputs — the acceptance of that UI is the unlock.
3. **Rating vocabulary** — `FeedbackCreate.rating` values (the task's
   LIKE/DISLIKE) are **defined by the feedback design** (BC-38/39, PR-12; §16
   open decision 8). This doc deliberately does not freeze `like`/`dislike`
   spellings as a contract until then (API-2: no silent change).
4. **Idempotency-Key on F-2** — the inventory does **not** key
   `POST /v1/assistant/feedback` (§4.5); a retry appends another evidence row.
   Additive if the product wants duplicate-suppression on card interactions.
5. **`reason` privacy** — free-text "why" is stored (P1 `feedback_events.
   reason`) but never exposed via the summary/other reads; retention is a
   future decision.
6. **Regenerate-as-signal** — REGENERATE (F-5) writes **no** signal today
   (§5.5). If the product wants "regenerated without save" as explicit weak
   negative evidence, that is a new `signal_type` + backend-write decision
   (PR-7: still never client-written).
7. **IGNORE / WEAR / SHARE** — **deliberately not defined** (§3, §4.3): no
   action, UI, signal type, or endpoint exists. Each would be a product + schema
   decision first (and — for signals — a backend-write decision under PR-7).
8. **`recommendation_history` (P3)** — the historical trace is conditional; if
   it ships it adds a read but **not** a new feedback write (R-A13 stays a
   raw-user-event concept; the current `feedback_events` already covers it).
9. All other open decisions from `API_CONTRACT_RULES.md` §16,
   `RECOMMENDATION_API.md` §8, `DAILY_OUTFIT_EVENTS_API.md` §8, and the sibling
   contracts remain open and are unaffected.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/FEEDBACK_LEARNING_API.md` — the
field-level API contract for **recommendation feedback and personalization
signals**. It maps the task's candidate actions to the accepted inventory and
supports only the feedback actions actually identified in STEP 2/3: **F-1**
`POST /v1/feedback` (LIKE/DISLIKE rating — **gated**, no UI today), **F-2**
`POST /v1/assistant/feedback` (the only client-facing signal input), **F-3**
`GET /v1/learning/summary` (derived personalization read), **F-4** SAVE
(referenced, TRX-3), **F-5** REGENERATE (referenced — a generation action, not
a feedback write). IGNORE / WEAR / SHARE are **explicitly excluded** (no
action/UI/UC/endpoint/signal type). It **separates raw user feedback
(`feedback_events`) from derived preference signals (`learning_signals` +
derived state, M10 sole writer, PR-7)** and defines each operation's
method/path/request/response/validation/auth/ownership/idempotency and
**personalization effect**. Nothing is implemented.

**Skills used:** repository + documentation analysis (the real
`assistant_service.dart` card signals `:91`/`:95`, `learning_service.dart`
styleScore, `profile_mocks.dart:248` "Haptic Feedback" settings row;
`learning_signals` + `feedback_events`* + `signal_types`/`style_score_records`
tables; PR-7/BC-41/BC-38/39/TRX-3/TRX-2; UC-15/UC-23/UC-32; AI_DOMAIN_MODEL
§4.5 + R-A13→R-A16; DECISION_ENGINE Stage 8 + role catalogue; ACTION_API
#26/#27/#31; UI_UX_GAP_REPORT #17; API_CONTRACT_RULES §12.9/§12.10/§11/§13;
API_INVENTORY endpoints 35/17/34/23/42/33/32/41; RECOMMENDATION_API §4.8;
ERROR_HANDLING taxonomy) — documentation only.

**Files changed:** `docs/api/FEEDBACK_LEARNING_API.md` (new);
`CURRENT_STATE.md` (status).

**Validation run:**
- **Every required operation traces 1:1 to the accepted inventory** — F-1→35/
  UC-32 (gated), F-2→17/UC-23, F-3→34, F-4→23/42/33/UC-15 (referenced), F-5→
  32/41/UC-16/29 (referenced). Paths/methods/auth/UC/errors identical to
  `API_CONTRACT_RULES.md` §12.9/§12.10 and `API_INVENTORY.md` §5.10/§5.11/
  §5.7/§5.13. No invented endpoints (IGNORE/WEAR/SHARE and signal-submit/
  preference-write surfaces explicitly excluded; regenerate kept out of the
  feedback write set).
- **Raw feedback and derived signals are separated** — F-1 writes append-only
  `feedback_events` (raw reactions) that FEED aggregation (R-A14→R-A15); F-2
  is the only client-facing signal input; M10 is the sole writer of
  `learning_signals` (PR-7); F-3 returns only the derived summary, never raw
  feedback text. Signal vocabulary stays the accepted 8 types; no client-
  named `signal_type`.
- **Wire shapes match the accepted sketches AND the real product** —
  `FeedbackCreate`/`AssistantCardFeedback` field names from §12.10/§12.3 and
  the `assistant_service.dart` signals; `LearningSummary` from §12.9 and the
  `LearningService` math; the rating vocabulary is honestly **pending** the
  feedback design (BC-38/39, PR-12), never frozen prematurely.
- **Auth/authorization/errors consistent** — all protected endpoints auth +
  owner-only (OW-1, 404-not-403); frozen 12-category errors; `POST
  /v1/feedback` keyed **when it ships**, save keyed (TRX-3), F-2 not keyed
  (recorded §8.4), regenerate never idempotent (§11).
- **`git status --short`:** `docs/api/` now holds API_CONTRACT_RULES.md,
  API_INVENTORY.md, AUTH_API.md, PROFILE_ONBOARDING_API.md, APPEARANCE_API.md,
  SCAN_API.md, HAIRSTYLE_RECOMMENDATION_API.md, RECOMMENDATION_API.md,
  WARDROBE_API.md, DAILY_OUTFIT_EVENTS_API.md, FEEDBACK_LEARNING_API.md
  (untracked) + `CURRENT_STATE.md`; no code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- The P1 feedback/learning endpoints are **not mounted**: `POST /v1/feedback`
  until the feedback UI is accepted (API-12, M11); F-2/F-3 until D-AUTH-1.
- Open/additive: rating vocabulary (§8.3), F-2 idempotency (§8.4), `reason`
  retention (§8.5), regenerate-as-signal (§8.6), IGNORE/WEAR/SHARE (each a
  product + schema decision, §8.7), `recommendation_history` P3 (§8.8).
- Other open decisions unchanged: auth provider (D-AUTH-1), MS10.3 media
  privacy, K9.1 knowledge shape, conversation retention.

**Assumptions recorded:**
- LIKE / DISLIKE are **rating values** inside `POST /v1/feedback`, not
  endpoints and not `signal_type`s; their exact spellings wait for the feedback
  design (PR-12).
- SAVE is the only **fully supported** feedback action today (actions
  12/14/17/19/22/24 → `look_saved` signal, TRX-3); it is referenced from M7,
  not re-defined.
- REGENERATE writes **no** feedback signal (generation, TRX-2) — kept out of
  this surface's write set.
- IGNORE / WEAR / SHARE are **excluded**: no action, UI, signal type, or
  endpoint exists in STEP 2/3 (verified), so no contract is invented (API-2).
- The assistant card feedback endpoint is the **only** client-facing signal
  input (M10 sole writer, PR-7), and it is restricted to the two card
  interactions (`opened`/`navigated`).
- The learning summary is **derived** and never includes raw feedback text.

**Constraints honored:** no implementation, the live assistant contract
untouched, no invented APIs (IGNORE/WEAR/SHARE, signal-submit and
preference-write excluded honestly; the rating vocabulary left pending),
DTO/UC/endpoint shapes kept identical to the accepted contract and sibling
docs, the no-internals rule enforced, the UI Change Safety Rule (no UI
touched), and the Scope rule (this document + `CURRENT_STATE.md` only).
