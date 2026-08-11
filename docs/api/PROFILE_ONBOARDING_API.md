# Fansivibe — API Contract: Profile, Preferences & Onboarding

> **STEP 6 — API CONTRACT DESIGN.** Defines the **field-level API contract for
> the user-profile, preferences, goals, style-preferences and appearance-
> capability surface** — the operations that seed (onboarding), read, and
> update a user's style profile and preferences. It is the focused companion
> to `API_CONTRACT_RULES.md` (§12 catalog + §13.2 profile sketches) and
> `API_INVENTORY.md` (§5.3 users): it fixes the wire shapes, validation, and
> security posture of the profile/preferences surface only.
>
> **Status: contract design only. Profile/preferences are NOT implemented.**
> No code, no `deps.py`, no routers, no SQL, no Flutter changes, no
> dependencies. The live contract (`GET /health`,
> `POST /v1/assistant/chat`) is preserved unchanged; the assistant stays
> unauthenticated until the auth decision lands (F-5).
>
> **Source of truth:** the real Fansivibe repository and the accepted docs —
> STEP 2 `ACTION_API_INVENTORY.md` (actions 28, 32), STEP 3
> `FANSIVIBE_DOMAIN_MODEL_V1.md` (E1 `User`, E1.1 `UserState`), STEP 4
> `TABLE_DEFINITIONS.md` (`users`, `user_state`), `TRANSACTION_BOUNDARIES.md`
> (TRX-3/TRX-6 sync), `APPLICATION_USE_CASES.md` (UC-5…UC-9),
> `AUTH_AUTHORIZATION_ARCHITECTURE.md` (OW-1, 404-not-403), STEP 5
> `ERROR_HANDLING.md` (12-category taxonomy), STEP 6 `API_CONTRACT_RULES.md`
> (canonical catalog §12 + §13.2 sketches) + `API_INVENTORY.md`, and the
> sibling contract `AUTH_API.md` (which defines the auth operations this doc
> references).

---

## 1. Purpose and scope

This document defines, for every **required** profile / preferences /
onboarding operation, the ten contract attributes the STEP 6 design task
asks for:

1. **method**
2. **path**
3. **request schema**
4. **response schema**
5. **validation rules**
6. **authentication requirements**
7. **authorization**
8. **errors**
9. **side effects**
10. **domain entities involved**

(plus, where meaningful, the security considerations each operation must
honor).

It also **selects the operation set**: of the candidate operations (update
profile, update preferences, update settings, sync, and the three "topics" in
the task — **goals**, **style preferences**, **appearance capability
progress**), only those the actual Fansivibe product and the accepted
inventory support are defined here. Nothing is invented beyond the
feature/data inventory.

**What it does not do:** implement the profile module, write schemas or
routers, modify Flutter, or change the live assistant contract. The profile
module (M2) is P0 but its write endpoints wait on the auth seam (D-AUTH-1);
this doc fixes the contract and seams so the adapter is replaceable.

### 1.1 Grounding facts (re-verified)

- **Onboarding is entirely optional-input.** The real flow is
  `splash → entry → vibe-select → (camera-permission → photo-capture →
  ai-analysis → your-analysis) → account-creation → home`
  (`SCREEN_DATA_INVENTORY.md` §2, `FEATURE_INVENTORY.md` §1). **Both the vibe
  and the AI analysis are skippable**: the entry screen offers "Analyze My
  Style" **or** "Explore Without Scanning" (`photoPath: false`), and
  vibe-select offers "I'm not sure — skip for now" which proceeds with
  `vibe: null` (`vibe_select_screen.dart:90-96`). The product therefore must
  not force an analysis or a photo; the contract below must support
  completing onboarding with **no style data at all**.
- **Today the app persists nothing from onboarding.** `FEATURE_INVENTORY.md`
  §1: "onboarding outcome not persisted into … any store; analysis results are
  simulated". The backend has **no profile endpoints at all** — the only live
  endpoint is unauthenticated `POST /v1/assistant/chat` (+ `GET /health`).
- **`StyleVibe` is a value object / preference reference** (`VALUE_OBJECTS.md`
  row 7) with exactly 6 values: `minimalist`, `bold`, `classic`, `trendy`,
  `natural`, `edgy` (`onboarding_data.dart:3-20`). It maps to the persisted
  `StyleProfile.styleType`.
- **Analysis output is display-only and not persisted.** `AnalysisResult`
  (`score`, `silhouetteLabel`, `observations`, `palette: List<PaletteSwatch>`,
  `formalityLabel`) is a simulated, on-device result
  (`onboarding_data.dart:33-53`). The canonical `StyleProfile`
  (`API_CONTRACT_RULES.md` §13.2) has **no palette/color field** — there is no
  stored "color palette", and the onboarding swatch display is derived output.
- **`styleType` (vibe) is self-reported; the rest of the profile is
  analysis-derived.** The persisted model today (`UserModel`,
  `learning/models.dart`) holds `face` (`FaceProfile`: optional `faceShape`,
  `skinTone`, `bodyType`, `styleType`), `styleType`, and `preferredOccasions`
  — the profile edit (action 28) is a stub ("ephemeral widget state"). The
  profile mock shows the same DNA as free-form display values
  (`profile_mock_data.dart:47-52`: skinTone "Warm Medium", faceShape "Oval",
  bodyType "Athletic", styleType "Modern Minimalist").
- **Style preferences are mostly display-only mock.** `PreferencesScreen`
  renders four chip groups — Style Vibe, Color Palette, Fit Preference,
  Occasion Focus (`profile_mocks.dart:76-113`) — with **no save API wired**
  (`ACTION_API_INVENTORY.md` action 28 = "stub (ephemeral widget state)").
  Of the four, only **Occasion Focus → `preferences.preferredOccasions`**
  (vocab codes) and **Style Vibe → `styleProfile.styleType`** have persisted
  fields today. Color Palette and Fit Preference have **no persisted key**.
- **Goals do not exist as a product concept.** The only occurrence anywhere
  is `StyleStreakData.weeklyGoal` (int, mock value `7`) — a **static constant
  in the home streak card** (`home_mock_data.dart:239-244`), classified
  **"UI-only, Historical"** (`DATA_MODEL_INVENTORY.md` line 307). There is no
  goals entity in E1.1 `UserState`, no goals table in the 23-table set, no use
  case, no action, and no endpoint in the 48-endpoint inventory.
- **Appearance capability progress is system config, not user data.** The
  capability grid (`YourAnalysisScreen` + home) renders `allCapabilities` — a
  **static const of 7 capabilities, 2 marked active**
  (`onboarding_data.dart:79-120`). `APPEARANCE_DOMAIN_MODEL.md` row 7: **SYSTEM
  CONFIGURATION**, "No per-user state; do not model rows";
  `HISTORY_AND_VERSIONING.md` §5.12: config-only, availability is a derived
  view over config × subscription; a Color Profile is **PLANNED** — "capability
  config + palette config only" (`APPEARANCE_DOMAIN_MODEL.md` row 5).
- **The write paths that exist in the inventory are**: `PATCH /v1/users/me`
  (UC-7 UpdateProfile, action 28), `PUT /v1/users/me/preferences` (UC-8
  UpdatePreferences, action 28), `PUT /v1/users/me/settings` (endpoint 09,
  action 28), and `POST /v1/users/me/sync` (UC-9 SyncLocalData / UC-5
  onboarding completion, action 32, P7.1) — the **post-account-merge path**
  that upserts the full local `UserModel` blob in one transaction.
- **`ProfileView`** (read, §13.2) = `{ displayName*, styleProfile,
  preferences, settings, flags, version* }`; `StyleProfile = { faceShape?,
  skinTone?, bodyType?, styleType?, sourceRunId? }`; `Preferences` is **sparse
  JSONB** whose only sketch-defined key is `preferredOccasions?: string[]`
  (vocab codes).
- **Naming note:** the canonical catalog names the PATCH profile field
  **`styleDna`** (`API_CONTRACT_RULES.md` §12.6; `API_INVENTORY.md` §5.3 item
  07), while the read/wire entity is **`styleProfile`** (§13.2). Both refer to
  the same `StyleProfile` value; the naming reconciliation is an open decision
  (§8.2).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `API_CONTRACT_RULES.md` | Canonical catalog §12.6 (users: PATCH `/users/me`, PUT `/preferences`, PUT `/settings`, POST `/users/me/sync`), §13.2 ProfileView/StyleProfile/Preferences/SyncRequest/SyncReceipt sketches, §5 Bearer/authz, §9 error contract, API-2 additive-only, API-12 no-fake-200. |
| `API_INVENTORY.md` | Endpoints 06–10 (§5.3 users) — GetProfile, UpdateProfile, UpdatePreferences, UpdateSettings, SyncLocalData; UC-5 onboarding → endpoint 10 (line 1205). |
| `AUTH_API.md` | Sibling STEP 6 contract; owns register/social/login/logout/`GET /v1/users/me`/`DELETE /v1/users/me`. This doc references it instead of re-defining. |
| `AUTH_AUTHORIZATION_ARCHITECTURE.md` | D-AUTH-1 seam, current-user resolution (`deps.py`), OW-1, 404-not-403. |
| `APPLICATION_USE_CASES.md` | UC-5 `CompleteOnboarding`, UC-6 `GetProfile`, UC-7 `UpdateProfile`, UC-8 `UpdatePreferences`, UC-9 `SyncLocalData`. |
| `TABLE_DEFINITIONS.md` | `users` (display_name CHECK 1..100), `user_state` (JSONB projection: styleProfile, preferences, settings, flags, version). |
| `TRANSACTION_BOUNDARIES.md` | TRX-3/TRX-6 sync transaction; version guard on writes. |
| `ERROR_HANDLING.md` | 12-category taxonomy: VALIDATION_ERROR (422), AUTHENTICATION_ERROR (401), NOT_FOUND (404), CONFLICT (409, `details.kind`), RATE_LIMITED (429 + `Retry-After`), MEDIA_FAILURE (413). |
| `APPEARANCE_DOMAIN_MODEL.md` / `HISTORY_AND_VERSIONING.md` | Capability progress = config-only, no per-user rows (§5.12); Color Profile planned, config-only. |
| `DATA_MODEL_INVENTORY.md` | `StyleStreakData` (weeklyGoal) classified UI-only display; no goals entity. |
| `VALUE_OBJECTS.md` | StyleVibe = value object / preference ref (row 7); Occasion = config ref (row 8). |

---

## 3. Operation selection (define only the required operations)

The candidate operations were each evaluated against the product requirements
and the accepted inventory. **Five are required and defined/referenced in §5;
three "topics" from the task are deliberately NOT defined as APIs today** and
are evaluated in §3.1–§3.3.

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| P-1 | **Get profile (read)** | **Required** — `GET /v1/users/me` | UC-6, endpoint 06. **Defined in `AUTH_API.md` §5.5**; §5.1 here adds the profile-field semantics (styleProfile/preferences/flags) it serves. |
| P-2 | **Update profile** | **Required** — `PATCH /v1/users/me` | UC-7, endpoint 07, action 28. Carries displayName + `styleDna` (incl. onboarding vibe → `styleType`). §5.2. |
| P-3 | **Update preferences** | **Required** — `PUT /v1/users/me/preferences` | UC-8, endpoint 08, action 28. Sparse JSONB, vocab-validated (incl. `preferredOccasions`). §5.3. |
| P-4 | **Sync local data (onboarding completion)** | **Required** — `POST /v1/users/me/sync` | UC-9 / UC-5 onboarding → endpoint 10, action 32 (post-account merge, P7.1). Full `UserModel` blob in one transaction. §5.4. |
| P-5 | **Update settings** | **Required (referenced, not re-defined)** — `PUT /v1/users/me/settings` | Endpoint 09, action 28. Controlled keys only; out of this step's scope, defined with the M2 module. §5.5. |
| — | **Goals** | **NOT required now** | §3.1. |
| — | **Onboarding swatch / color-palette endpoint** | **NOT required now** | §3.2. |
| — | **Appearance capability progress API** | **NOT required now** | §3.3. |

### 3.1 Goals — not required today

The task asked for a "goals" contract. The product has **no goals feature**:
`weeklyGoal` is a static display constant in the home streak card
(`home_mock_data.dart:239-244`, mock value `7`), classified **UI-only**
(`DATA_MODEL_INVENTORY.md` line 307). There is no goals entity, table, use
case, action, or endpoint. **No goals API is defined.**

**Forward contract (only if a user-set goal ships):** a user-authored goal
would be an explicit user preference (DOMAIN_MODEL_RULES row 7) and would fold
into the existing sparse `preferences`/`settings` JSONB (written via P-3/P-5)
— **no new endpoint and no goals table** (PR-12: no speculative tables/rows).
It is **not** placed in `flags`: `flags` is a server-derived projection, and no
trusted-server goal computation can be confirmed from the real app today. This
is recorded as an open decision (§8.3), never invented now (API-2).

### 3.2 Onboarding "swatches" / color-palette endpoint — not required

A dedicated onboarding swatch-write endpoint was evaluated and **rejected**:

- There is **no swatch picker** in onboarding — the user picks a **vibe**
  (StyleVibe → `styleType`); the color palette shown on `your-analysis` is the
  **simulated analysis output** (`AnalysisResult.palette`,
  `onboarding_data.dart:37`) and is display-only.
- `StyleProfile` and `Preferences` (§13.2) have **no palette/color field**, and
  a Color Profile is at most **PLANNED config** (`APPEARANCE_DOMAIN_MODEL.md`
  row 5) — storing palette swatches would create data no accepted table has.
- The vibe is captured by P-2 (`styleDna.styleType`, self-reported, **no
  `sourceRunId` needed** — see §5.2), so the offline/instant path works through
  the existing `PATCH /v1/users/me` without a full-blob write or a new path.

Adding `POST /v1/users/me/swatches` would be an **invented API** (no inventory
support) and is excluded — recorded as an open decision (§8.4).

### 3.3 Appearance capability progress — config-only, no API

The task asked for an "appearance capability progress" contract. The product
surface is real (`YourAnalysisScreen` + home capability grid), but the
backing data is **static system config**: `allCapabilities` = 7 capabilities,
2 marked active (`onboarding_data.dart:79-120`); `HISTORY_AND_VERSIONING.md`
§5.12 and `APPEARANCE_DOMAIN_MODEL.md` row 7 classify it **SYSTEM
CONFIGURATION** with **no per-user rows and no progress log**. **No capability
endpoint and no capability table is defined.**

**Contract decision:** capability status is **client-computed and
server-transparent** — the client derives active/locked from its local config
× the user's own data signals (e.g. has a face analysis → Face Analysis /
Color Analysis active; wardrobe items exist → Wardrobe Intelligence; an event
exists → Event Styling; entitlement → Shopping Assistant), with unlock hints
from config. `ProfileView` **does not** include a `capabilities` field (it is
not a stored field — API-2 forbids adding storage-driven fields speculatively).

**Forward contract (only if the catalog becomes server-served):** the catalog
is knowledge/content and belongs under `/v1/knowledge/*` (M5, additive, per
K9.1) — still with **no per-user rows**; derivation stays a read-time view.
Recorded as an open decision (§8.5).

---

## 4. Shared semantics (apply to every operation below)

### 4.1 Base URL, headers, format

- All endpoints under `/v1` (API-1); JSON bodies `application/json;
  charset=UTF-8`; keys camelCase; timestamps ISO-8601 UTC (API-19).
- Protected endpoints send `Authorization: Bearer <token>` (API-5). Missing /
  invalid / expired / revoked → `401 AUTHENTICATION_ERROR` +
  `WWW-Authenticate: Bearer` (API-7, ERROR_HANDLING §5.2).
- `POST /v1/users/me/sync` requires `Idempotency-Key` (C-12, API-33); `PATCH`
  and `PUT` are naturally idempotent (no key).
- Every response echoes `X-Request-Id` (OBSERVABILITY §4.1).

### 4.2 Optimistic versioning (P-2)

`user_state.version` is the optimistic-concurrency guard (inventory 07,
"guarded by optimistic version"). P-2 carries the client's current `version`
via the **`If-Match` header**; on mismatch the server returns
`409 CONFLICT` with `details.kind="version"` and the client must re-fetch
(`GET /v1/users/me`), reconcile, and retry. Reads and the full-blob sync
(P-4) do not use `If-Match` — P-4 resolves conflicts instead (see §5.4).

### 4.3 Error body (frozen, API-28)

```
{ "error": { "code": "<one of the 12>", "message": "<safe client message>", "details": {...} } }
```

`details` is allow-listed only (ER-1): field errors + allowed values (422),
`kind` (`version`, `sync`, 409), `maxBytes` (413). **Never** the user's
appearance data, analysis internals, or provider details (C-7/C-8, ER-0/ER-2).

### 4.4 Public vs auth, ownership, sensitivity

| Requirement | Endpoints |
| --- | --- |
| **Auth** (Bearer → `user_id`) | `GET /v1/users/me`, `PATCH /v1/users/me`, `PUT /v1/users/me/preferences`, `PUT /v1/users/me/settings`, `POST /v1/users/me/sync`. |
| **Public** | none in this surface (register/login live in `AUTH_API.md`). |

Authorization is **owner-only (OW-1)** with **404-not-403** (API-10): every
endpoint here reads/writes only the caller's own `user_state`. `styleProfile`
is **CRITICAL-sensitivity** appearance data (SECURITY_PRIVACY_DESIGN §3):
HTTPS only, owner-only, never cached on shared storage, never logged
(ER-4, MS10.3). Preferences and settings are lower-sensitivity but follow the
same owner-only path.

---

## 5. Operation contracts

### 5.1 P-1 — Get profile (`GetProfile`, UC-6) — reference

- **Method / path:** `GET /v1/users/me` — **fully defined in `AUTH_API.md`
  §5.5**; not re-defined here.
- **Profile semantics served by this doc:**
  - `styleProfile.styleType` — the chosen vibe (`StyleVibe` code or absent);
    self-reported, no run required.
  - `styleProfile.faceShape / skinTone / bodyType` — analysis-derived; present
    only when an analysis run exists (`sourceRunId` set).
  - `preferences.preferredOccasions` — vocab-coded occasion list (P-3).
  - `flags` — server-derived projection flags; **not** a goals store (§3.1).
  - `version` — optimistic-concurrency counter (P-2 `If-Match`).
- **Errors:** `200`; `401 AUTHENTICATION_ERROR`; `404 NOT_FOUND` (token valid
  but account gone). Owner-only; never an existence oracle on another user.
- **Side effects:** none — a pure read; it does not refresh or modify
  `user_state`, create audit/learning rows, or rotate any token.
- **Domain entities involved:** E1 `User` (displayName); E1.1 `UserState`
  (StyleProfile, Preferences, Settings, Flags, version).

---

### 5.2 P-2 — Update profile (`UpdateProfile`, UC-7)

- **Method / path:** `PATCH /v1/users/me`
- **Request schema** (`application/json`):

```
{
  "displayName": "Alex",                // optional, trimmed, 1..100 chars
  "avatarMediaRef": { ... },            // optional, MediaRef — GATED (see below)
  "styleDna": {                         // optional partial; catalog name (§12.6)
    "styleType":   "minimalist",        // self-reported vibe; StyleVibe allow-list; NO run required
    "sourceRunId": "4f0d…",             // run id; REQUIRED when any analysis-derived field is set
    "faceShape":   "oval",              // analysis-derived → requires sourceRunId
    "skinTone":    "warm_medium",       // analysis-derived → requires sourceRunId
    "bodyType":    "athletic"           // analysis-derived → requires sourceRunId
  }
}
```

  - The `styleDna` object is a **merge patch**: omitted keys are unchanged;
    `null` clears a key. Written into `user_state.styleProfile` (the §13.2
    entity; naming note §1.1 / §8.2).
  - Carried with the client's `If-Match: <version>` header (§4.2).

- **Response schema:** `200 OK` — the updated `ProfileView` (bare, no
  envelope, identical shape to `AUTH_API.md` §5.5).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  — only the caller's own profile (OW-1, 404-not-403).
- **Validation:**
  - `displayName` — trimmed, 1–100 chars (BC-9).
  - `styleType` ∈ {`minimalist`, `bold`, `classic`, `trendy`, `natural`,
    `edgy`} (StyleVibe allow-list, API-14) — self-reported, settable **without**
    `sourceRunId` (this is the onboarding offline/instant path).
  - Analysis-derived fields (`faceShape`, `skinTone`, `bodyType`) **require
    `sourceRunId`** — they are the normalized outcome of an analysis run; a
    derived field without a run id → **422**. Values are vocab-validated
    (allowed values in `details`; codes finalized with the knowledge layer,
    §8.6). "Retake analysis" = a new run → P-2 replaces the derived fields +
    `sourceRunId` in one patch.
  - Version mismatch → **409** `details.kind="version"` (no silent overwrite).
  - Unknown keys → **422**; `styleDna` must stay within the §13.2 entity
    (no palette/color field exists — §3.2).
  - `avatarMediaRef` — **gated**: accepted only when M16 media uploads are
    live (MS10.3 seal, API-12); sending it before then → **422** (unsupported
    field), never silently ignored.
- **Errors:** `200`; `401`; `404 NOT_FOUND` (account gone); `422
  VALIDATION_ERROR` (field errors + allowed values, derived-without-run,
  unsupported avatar); `409 CONFLICT` (`details.kind="version"`); `429
  RATE_LIMITED`.
- **Security considerations:**
  - `styleDna` (appearance) is **CRITICAL** — HTTPS, owner-only, never logged
    (ER-4, MS10.3); the analysis-derived fields are never a client-authored
    "truth" — the `sourceRunId` pins them to a server-verified run
    (C-16/BAR-0).
  - Optimistic concurrency prevents lost updates from two devices; no
    full-profile read-modify-write is required for a single field (the
    offline path writes `styleType` alone without a full blob).
  - 404-not-403: a valid token for a deleted account gets `404`, not a
    per-field existence leak.
- **Side effects:**
  - **Write:** merges the patch into `user_state.styleProfile` (+
    `displayName` on E1 `User`) and bumps `user_state.version`; a partial
    patch never touches other profile/preference keys.
  - **No cross-write:** this endpoint never changes `preferences`,
    `settings`, `flags`, or relational rows (those belong to P-3/P-5/P-4).
  - **Retake-analysis path:** a P-2 with new analysis-derived fields +
    `sourceRunId` *replaces* the previous derived fields and run reference —
    it does not append history rows (analysis provenance lives on the run
    entity, E6, via its own write path, TRX-5).
  - **No side effects on failure:** a `409`/`422`/`401` writes nothing.
- **Domain entities involved:** E1 `User` (displayName; `avatarMediaRef` is a
  MediaRef value, M16-gated); E1.1 `UserState.styleProfile` (StyleProfile:
  styleType / faceShape / skinTone / bodyType / sourceRunId); E6 `AnalysisRun`
  (referenced via `sourceRunId` — read-only pin, not written here).

---

### 5.3 P-3 — Update preferences (`UpdatePreferences`, UC-8)

- **Method / path:** `PUT /v1/users/me/preferences`
- **Request schema:** `Preferences` — **sparse JSONB, merge semantics**
  (inventory 08: "merge changed preference key/values into the `user_state`
  JSONB document"). Keys not present are left unchanged; only vocabulary-
  validated keys are accepted.

```
{
  "preferredOccasions": ["smart_casual", "business"]   // optional; vocab occasion codes (K9.1)
  // other keys: none defined today (controlled allow-list; §3.1 goals, §3.3 capability NOT keys)
}
```

- **Style-preferences mapping (PreferencesScreen, 4 sections):** of the four
  chip groups rendered (`profile_mocks.dart:76-113`), only two map to a
  persisted field; the other two are **display-only mock with no server key**
  (PR-12 — no speculative preference fields):

| PreferencesScreen section | Persisted location | Notes |
| --- | --- | --- |
| **Style Vibe** | `styleProfile.styleType` (via P-2, not here) | persisted; `StyleVibe` value object |
| **Occasion Focus** | `preferences.preferredOccasions` (this endpoint) | persisted; vocab occasion codes |
| **Color Palette** | *(none)* | display-only; derived from analysis (§3.2) |
| **Fit Preference** | *(none)* | display-only mock; no field today |

- **Response schema:** `200 OK` — the updated `Preferences` (sparse object,
  bare, no envelope).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1, 404-not-403).
- **Validation:**
  - Every key ∈ controlled allow-list; unknown keys → **422** with `details`
    (allowed keys).
  - `preferredOccasions` — array of **vocab occasion codes** (K9.1); a code
    not in the knowledge vocabulary → **422** with allowed values.
  - Values are trimmed; arrays are deduplicated server-side.
- **Errors:** `200`; `401`; `404`; `422 VALIDATION_ERROR` (unknown keys,
  invalid vocab codes); `429 RATE_LIMITED`.
- **Security considerations:**
  - Preferences are owner-only and low-sensitivity; they are **not** stored as
    free text — vocab codes only (no free-form inputs, no injection surface).
  - Never logged; merge semantics mean a partial write never wipes other
    preferences.
  - No goals or capability keys are accepted here today (§3.1, §3.3).
- **Side effects:**
  - **Write:** merges the sparse keys into `user_state.preferences` JSONB
    (e.g. replaces `preferredOccasions`); omitted keys are untouched (merge,
    not replace — inventory 08).
  - **No cross-write:** never touches `styleProfile`, `settings`, or
    relational rows; the Style Vibe chip maps to `styleType` **via P-2**, not
    here.
  - **No side effects on failure:** a `422`/`401` writes nothing.
- **Domain entities involved:** E1.1 `UserState.preferences` (sparse JSONB;
    occasion vocab references — the only owned entity). Style Vibe ↔
    `StyleProfile.styleType` (E1.1) is read by the client but written via P-2.

---

### 5.4 P-4 — Sync local data / onboarding completion (`SyncLocalData`, UC-9; UC-5 onboarding)

- **Method / path:** `POST /v1/users/me/sync` — `Idempotency-Key` **required**
  (C-12): a retried sync must not duplicate rows.
- **Purpose:** the **post-account-merge path** (action 32, P7.1): upload the
  full local `UserModel` snapshot built during onboarding/offline usage and
  split it into relational rows (wardrobe / events / saved-looks) + the
  `user_state` projection in **one true transaction** (TRX-3/TRX-6), resolving
  server-vs-device conflicts.
- **Request schema:**

```
{
  "wardrobe":        [ ...WardrobeItem ],   // required, full local list
  "savedLooks":      [ ...SavedLookRef ],   // required, full local list
  "events":          [ ...UserEvent ],      // optional
  "preferences":     { ...Preferences },    // optional, sparse (P-3 rules)
  "styleProfile":    { ...StyleProfile },   // optional, as in §13.2
  "flags":           { ...Flags },          // derived-flags container (server-validated)
  "clientTimestamp": "2026-08-10T…Z"        // required, ISO-8601 UTC
}
```

- **Response schema:** `200 OK` — `SyncReceipt` (bare, no envelope):

```
{
  "mergedProfile": { /* ProfileView */ },
  "conflicts":     [ { "resource": "wardrobe", "kind": "latest-wins" } ],   // latest-wins | append | needs-review
  "syncedAt":      "2026-08-10T…Z"
}
```

- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1, 404-not-403). Until auth lands (F-5), the client keeps its local
  `UserModel` and syncs later once the account exists — the endpoint is
  **designed now, not mounted** until the auth seam (D-AUTH-1) + sync pipeline
  exist (API-12; same convention as the sealed modules).
- **Validation:**
  - Full-schema validation of every embedded DTO (same field rules as their
    individual endpoints); any invalid item → **422** with field errors (the
    whole transaction rolls back — no partial merge).
  - `clientTimestamp` is the conflict-ordering clock; server-validated.
  - `styleProfile` follows the §13.2 entity and the §5.2 rules (analysis-derived
    fields require `sourceRunId`).
  - `flags` — derived flags are **recomputed server-side**, not trusted from
    the client; user-authored flag values (if any) are allow-listed.
  - Payload size guard → **413** `details.maxBytes` (oversized blobs rejected
    whole, TRX-safe).
- **Errors:** `200`; `401`; `404`; `409 CONFLICT` (`details.kind="sync"` — a
  conflict resolution the merge cannot auto-solve; client reviews and
  re-syncs); `413 MEDIA_FAILURE` (too large); `422 VALIDATION_ERROR`; `429
  RATE_LIMITED`.
- **Security considerations:**
  - The payload is the user's **own** full state incl. CRITICAL appearance
    data — owner-only, HTTPS, never logged (ER-4).
  - Idempotency-keyed: a retry never duplicates wardrobe/saved-look rows.
  - The single transaction (TRX-3/6) means sync either fully lands or fully
    rolls back — no half-merged profile.
  - Conflicts are returned to the client with an explicit `kind`; the server
    never silently drops user data.
- **Side effects (all in the one true transaction, TRX-3/TRX-6):**
  - **Upserts relational rows** from the blob: E2 `WardrobeItem`, E3
    `UserEvent`, E4 `SavedLook` (deduped by client ids / Idempotency-Key).
  - **Rewrites the `user_state` projection** (styleProfile, preferences,
    settings, flags) and bumps `version`.
  - **Recomputes server-side flags** and persists a `SyncReceipt`-level
    conflict decision where the merge can auto-resolve (`latest-wins` /
    `append`); only unsolvable cases return `409 kind="sync"`.
  - **Learning-signal merge (E7):** sync applies any queued local
    `LearningSignal`s so derived signals are not lost on device change —
    signals remain owned/aggregated server-side, never accepted verbatim as
    profile truth.
  - **Failure = rollback:** any invalid embedded item (`422`), oversized
    payload (`413`), or unsolvable conflict (`409`) rolls the whole
    transaction back — no partial merge.
- **Domain entities involved:** E1 `User` (account resolution); E1.1
  `UserState` (projection rewrite); E2 `WardrobeItem`; E3 `UserEvent`;
  E4 `SavedLook`; E7 `LearningSignal`; E6 `AnalysisRun` (referenced via
  `styleProfile.sourceRunId`, read-only pin); E5 `Look` (catalog — as the
  reference target of saved-look refs, never written).

---

### 5.5 P-5 — Update settings (`UpdateSettings`, endpoint 09) — reference

- **Method / path:** `PUT /v1/users/me/settings` — **referenced, not
  re-defined** in this step (out of scope; controlled app-toggle keys live in
  `user_state.settings` and are defined with the M2 module). Same auth/owner/
  validation posture as P-3 (sparse, controlled keys, vocab-validated → 422).
  The Flutter `SettingsScreen` mock toggles (Notifications, Sound, Haptics,
  Theme, Units, Data Saver — `profile_mocks.dart:234-269`) are the display
  surface; persistence is out of this step's scope.
- **Side effects:** merge-controlled `user_state.settings` keys only (same
  merge semantics as P-3); never touches preferences/styleProfile/flags.
- **Domain entities involved:** E1.1 `UserState.settings`.

---

### 5.6 Onboarding flow (a sequence of the above — no new endpoint)

Onboarding is **not** an endpoint; it is the orchestration of P-2/P-3/P-4 over
the account from `AUTH_API.md`. Both required paths accept a **zero-data
onboarding** (no vibe, no analysis, no photo — the "Explore Without Scanning"
/ "skip for now" reality, §1.1):

**Path A — targeted writes (online):**
`POST /v1/auth/register` (AUTH_API §5.1) → optional `PATCH /v1/users/me`
with `styleDna.styleType` (vibe; no run needed) and, if analysis was run, the
derived fields + `sourceRunId` → optional `PUT /v1/users/me/preferences`
(occasions) → confirm with `GET /v1/users/me`.

**Path B — post-account merge (offline-first, UC-9 / UC-5):**
build the full local `UserModel` during onboarding/offline use → after the
account exists, one `POST /v1/users/me/sync` (Idempotency-Key) → `SyncReceipt`
carries the merged profile + conflicts.

**Completion semantics:** onboarding-complete is a **client-side** concern —
the router dispatches `FirstTimeHomeScreen` vs home from a local session flag
(`SCREEN_DATA_INVENTORY.md`); there is **no server "onboarding complete"
flag or endpoint**. The server only ever reflects whatever style data the user
actually provided.

---

## 6. Validation reference (shared)

| Field | Rules | Source |
| --- | --- | --- |
| `displayName` | trimmed, 1–100 chars | `users` CHECK BC-9 |
| `styleType` | ∈ {`minimalist`, `bold`, `classic`, `trendy`, `natural`, `edgy`}; self-reported, no run | StyleVibe allow-list (API-14), VALUE_OBJECTS row 7 |
| `faceShape` / `skinTone` / `bodyType` | vocab-validated (allowed values in `details`); **require `sourceRunId`** | K9.1 vocab (codes at §8.6); run pinning C-16 |
| `sourceRunId` | UUID of an owned, completed analysis run | `analysis_runs` ownership |
| `preferredOccasions` | array of vocab occasion codes (K9.1); deduplicated | VOCAB occasion codes (VALUE_OBJECTS row 8) |
| `version` | `If-Match` header on PATCH; mismatch → 409 | user_state.version |
| `clientTimestamp` | ISO-8601 UTC; conflict-ordering clock | sync |
| Field errors | `422` + `details: [{field, error, allowed?}]` | API-30, ERROR_HANDLING §5.1 |

All validation is **server-side** (Flutter never enforces security) and returns
the **safe client message**, never internal details (ER-2).

---

## 7. Error reference for this surface

| `error.code` | HTTP | When | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | bad displayName/styleType/derived-without-run/vocab code/unknown preference key/unsupported avatar | field errors + allowed values in `details` |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | `/users/me` when the account is gone | 404-not-403; never another user |
| `CONFLICT` | 409 | PATCH version mismatch (`kind="version"`); sync merge unsolvable (`kind="sync"`) | `details.kind` |
| `RATE_LIMITED` | 429 | any write endpoint | + `Retry-After` |
| `MEDIA_FAILURE` | 413 | sync payload too large | `details.maxBytes`; whole-transaction rollback |

---

## 8. Open decisions (carried forward, unchanged where already recorded)

1. **D-AUTH-1 — auth provider** — unchanged; gates mounting P-2…P-4 (they wait
   on the auth seam; the sync endpoint is designed but **NOT mounted** until the
   sync pipeline exists — API-12).
2. **`styleDna` vs `styleProfile` naming** — the PATCH request field is
   `styleDna` (§12.6 / inventory 07) while the entity/view is `styleProfile`
   (§13.2). Same value; reconcile to one name at M2 implementation.
3. **Goals** — no goals feature in the product; `weeklyGoal` is UI-only display
   copy (§3.1). If a user-set goal ships, it becomes a controlled
   `preferences`/`settings` key (P-3/P-5), **no new endpoint or table**.
4. **Onboarding swatches** — explicitly excluded (§3.2); the palette is derived
   analysis output with no stored field. A Color Profile (palette config) stays
   **PLANNED config** only.
5. **Appearance capability catalog** — client config today; forward server-serve
   under `/v1/knowledge/*` (M5, additive) if ever decided; **never per-user
   rows** (PR-12, HISTORY_AND_VERSIONING §5.12).
6. **Analysis-derived vocab codes** — `faceShape`/`skinTone`/`bodyType` value
   codes are finalized with the knowledge layer (K9.1); until then the contract
   pins them to runs and rejects free text.
7. **Avatar media** — `avatarMediaRef` is accepted only after M16 media uploads
   unseal (MS10.3); gated 422 before then.
8. All other open decisions from `API_CONTRACT_RULES.md` §16 and
   `AUTH_API.md` §8 remain open and are unaffected.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/PROFILE_ONBOARDING_API.md` — the
field-level API contract for the profile / preferences / onboarding surface:
UpdateProfile (PATCH `/v1/users/me`), UpdatePreferences (PUT
`/v1/users/me/preferences`), SyncLocalData (POST `/v1/users/me/sync`), with
GetProfile and UpdateSettings referenced (AUTH_API §5.5 / M2) and an onboarding
sequence that requires **zero forced input**. Every operation carries the full
required attribute set — method, path, request schema, response schema,
validation, authentication, authorization, errors, **side effects**, and
**domain entities involved** (§5). Three task topics — **goals,
onboarding swatches, appearance capability progress** — were evaluated and
deliberately **NOT defined as APIs** (§3.1–§3.3), each with a forward contract.
Profile/preferences are **not** implemented.

**Skills used:** repository + documentation analysis (ACTION_API actions 28/32,
domain E1/E1.1, `TABLE_DEFINITIONS` `users`/`user_state`, TRX-3/6 sync, UC-5…9,
ERROR_HANDLING 12-category taxonomy, API_INVENTORY §5.3/§6, APPEARANCE_DOMAIN_
MODEL + HISTORY_AND_VERSIONING §5.12 config-only capability, DATA_MODEL_
INVENTORY `StyleStreakData` UI-only, live `onboarding_data.dart` /
`profile_mocks.dart` / `home_mock_data.dart` / `learning/models.dart`) —
documentation only.

**Files changed:** `docs/api/PROFILE_ONBOARDING_API.md` (new);
`CURRENT_STATE.md` (status).

**Validation run:**
- **Every defined operation traces 1:1 to the accepted inventory** — P-1→UC-6 /
  endpoint 06, P-2→UC-7 / 07, P-3→UC-8 / 08, P-4→UC-9 + UC-5 onboarding / 10,
  P-5→09. No invented endpoints: goals, swatches, and capability progress are
  explicitly excluded (§3.1–§3.3); paths/methods/auth/UC/errors identical to
  `API_CONTRACT_RULES.md` §12.6 and `API_INVENTORY.md` §5.3; the per-operation
  **domain-entity and side-effect** attributes are consistent with the
  inventory's §5.3 "related domain entities" and TRX-3/TRX-6 transaction
  boundaries.
- **Wire shapes match the P0 sketches (§13.2)** — `ProfileView`,
  `StyleProfile`, `Preferences`, `SyncRequest`, `SyncReceipt`, `Conflict`
  identical to the sketch; `ProfileUpdateRequest` uses the catalog's literal
  `styleDna` field name (§12.6) with the naming reconciliation recorded (§8.2).
  No field removed, renamed, or retyped; the only additions are documented
  gating notes (avatar media, derived-without-run), not new stored data (API-2).
- **Product grounding re-verified against the real repo** — vibe + analysis
  are optional and skippable (`vibe_select_screen.dart:90-96`, entry-screen
  "Explore Without Scanning"); `weeklyGoal` is a UI-only streak-card constant
  (`home_mock_data.dart:239-244`, DATA_MODEL_INVENTORY line 307); capability
  progress is static config with no per-user rows (APPEARANCE_DOMAIN_MODEL
  row 7, HISTORY_AND_VERSIONING §5.12); `preferredOccasions` + `styleType` are
  the only persisted style fields in `UserModel`.
- **Auth/authorization consistent** — all write endpoints auth + owner-only
  (OW-1, 404-not-403); `If-Match` version guard (409 `kind="version"`);
  Idempotency-Key on sync; frozen 12-category error codes; 401 +
  `WWW-Authenticate`, 429 + `Retry-After`.
- **`git status --short`:** `docs/api/` holds API_CONTRACT_RULES.md,
  API_INVENTORY.md, AUTH_API.md, PROFILE_ONBOARDING_API.md (untracked) +
  `CURRENT_STATE.md`; no code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- P-2…P-4 are **not mounted** until the auth seam (D-AUTH-1) and the sync
  pipeline exist; the sync endpoint is designed now but must not return fake
  success before then (API-12).
- Naming reconciliation `styleDna` vs `styleProfile` (§8.2) and the
  analysis-derived vocab codes (§8.6) are decided at M2 with the knowledge
  layer.
- Goals and capability progress remain **open decisions**, not features — no
  speculative tables, rows, or endpoints (PR-12).
- Other open decisions unchanged: auth provider (D-AUTH-1) incl. refresh-
  session conditional, User fields, Today'sLookRecord (P1),
  RecommendationHistory (P3), conversation retention, K9.1 knowledge shape,
  media-privacy (MS10.3), feedback design.

**Assumptions recorded:**
- The vibe (`styleType`) is self-reported and may exist without an analysis
  run; analysis-derived fields are always pinned to a `sourceRunId`.
- `weeklyGoal` is display copy, not user data; no goals API until the product
  adds user-set goals (then a preference key, still no endpoint/table).
- Capability status is client-computed from config × the user's own data; the
  server is transparent and stores no capability state.
- Onboarding completion is client-side; the server only persists what the user
  actually provided (vibe, occasions, analysis-derived profile).

**Constraints honored:** no implementation (profile/preferences NOT created),
the live assistant contract untouched (F-5), no invented APIs (goals/swatches/
capability excluded; sync is the inventory's own UC-9/UC-5 path), scope limited
to `docs/api/PROFILE_ONBOARDING_API.md` + `CURRENT_STATE.md`.
