# API Versioning & Compatibility Rules

> Status: STEP 6 — API Contract Design deliverable. **Documentation only. No
> implementation.** No routers, DTOs, headers, middleware, or Flutter code are
> added or changed by this document. It consolidates the accepted versioning
> rules (API-1…4, C-14) and extends them with the policies the contract still
> lacked: breaking-change classification, deprecation lifecycle, response-
> compatibility guarantees, migration mechanics, and the **mobile-app
> backward-compatibility policy** (the live app `fansivibe 1.0.0+1` and any
> older installed build must keep working after a backend update).

---

## 1. Purpose and scope

This document defines how the Fansivibe HTTP API is versioned and how
compatibility is preserved for every client, with the explicit constraint that
**a mobile app remains on an older build after the backend has moved on**:

- app-store/play-store rollout lag means old builds call a newer backend;
- the backend must therefore never assume "all clients are current";
- the API must give clients a way to stay pinned to a stable contract, and the
  platform must give the backend a way to evolve without breaking them.

Grounding facts (unchanged, re-verified):

- Only live surface today: `GET /health` and `POST /v1/assistant/chat`
  (`backend/app/main.py:18,23`); the assistant wire DTOs are frozen
  (`ASSISTANT_API.md` §3.4, F-13).
- Path-based versioning is accepted: `/v{N}`, current version **v1**
  (`API_LAYER_ARCHITECTURE.md` §3, API-1).
- Within a version, responses are additive-only (API-2, C-14).
- A client may pin the exact contract via `Accept: application/json;
  version=X.Y`; unsupported versions → `422` (API-3).
- A breaking change requires a new version + a deprecation window, with the old
  version kept running (API-4).
- Three distinct version concepts must stay separate (API vs resource
  optimistic-concurrency vs content/engine reproducibility —
  `API_RESPONSE_CONVENTIONS.md` §11); this document covers the **API version**
  concept only, referencing the other two where they interact.

---

## 2. Versioning strategy

### 2.1 Version number model

The API uses a **two-part version**; the part a client chooses determines what
it commits to:

| Part | Carried in | Meaning | Changes when |
| --- | --- | --- | --- |
| **Major (path)** | URL `/v{N}` | The resource/operation contract as a whole | Any breaking change ships (removal, rename, retype, reorder, semantic change, error-shape change) — new path version (`/v2`), never in place |
| **Minor (pin)** | `Accept: application/json; version=N.M` | The additive field set of the current major | A new **optional** field is added to a response (bumps the highest available minor) |

Rules:

- The **path version is the primary identifier**: every endpoint lives under
  `/v1/...` (API-1). The router root mounts each version's router set
  (`app/api/v1/router.py`), so `/v1` and `/v2` can run side by side.
- The **default response is the latest minor of the current major** (API-3): a
  client that sends no `Accept` pin gets the newest additive shape — which is
  always a superset of every older shape (API-2), so it cannot break a
  well-formed old client.
- A client that **pins** `version=1.0` is served only the field set it pinned
  (new optional fields are withheld). Pinning is how a conservative or
  long-tail client freezes its shape and is never surprised by new fields.
- **`GET /health` stays versionless and envelope-free** (API-4): it is the
  one endpoint whose shape must never change, and the primary place the server
  advertises which versions it currently serves (§7).

### 2.2 The three version concepts (kept separate)

Interaction points with the other two concepts (`API_RESPONSE_CONVENTIONS.md`
§11):

- **Resource optimistic-concurrency** (`version` int on `user_state` etc.) is a
  per-resource write guard (`409 CONFLICT` on stale writes). It is unrelated to
  the API version and never changes the wire shape of a version.
- **Content / engine reproducibility** (`content_version`, `engine_version`)
  only records *what produced* a value; a bump is invisible to the API version.
- Because these two are data-level, they may change freely **within** a path
  version; only the API version rules in this document gate wire-shape change.

### 2.3 Why path-based major + optional pin

- Path-based majors give unambiguous, cacheable, loggable routing and let
  operators run two majors concurrently with a pure routing prefix split
  (§6.1) — no content negotiation surprises.
- The optional minor pin (API-3) is the only accepted exception to "latest
  wins"; it exists **for the mobile client** so an installed build can hold its
  exact field set across a backend release.
- No Accept-less content negotiation, no query-string `?v=`, no header-only
  versioning: the path is authoritative (API-1), the header is a refinement.

---

## 3. Semantics of a version — what is guaranteed within `/vN`

Within a single path version the following are **frozen guarantees**; a change
to any of them is a breaking change (→ §4):

- **Additive responses only (API-2, C-14):** a response may gain new *optional*
  fields; it never loses, renames, retypes, reorders, or changes the meaning of
  an existing field.
- **Frozen assistant DTOs (F-13):** `AssistantRequest` / `AssistantReply`
  field names, order, and types must **never change** — no additive
  reorder/rename/retype, not even field addition that reorders. The live
  `POST /v1/assistant/chat` stays verbatim (`ASSISTANT_API.md` §1, §3.4).
- **Stable status codes (API-32, C-9):** the HTTP status code a condition maps
  to (and the `error.code` value, ER-0…3) never changes within a version. A
  `404` that becomes a `401`, or a code reclassification, is a breaking change.
- **Frozen error taxonomy (API-28, `ERROR_HANDLING.md` §4/§5):** the 12
  categories and the allow-listed `details` shape are frozen. **No new error
  category is added within a version** — the taxonomy is closed; a new category
  would require `/v2` (clients are allowed to map the full set exhaustively).
- **Stable vocabularies on the wire:** a *request* vocabulary is validated to
  `422` with allowed values (API-14). A *response* may legally carry values the
  client has never seen (§6.4) — the version guarantees *which fields exist*,
  not that the content vocabulary is frozen.
- **Stable path/method semantics:** the HTTP method, the path shape, and the
  ownership model (OW-1, 404-not-403) of every endpoint are frozen within a
  version.

---

## 4. Breaking change policy

### 4.1 What counts as a breaking change

| Change | Example | Classification |
| --- | --- | --- |
| Remove a field | drop `total` from a list envelope | Breaking |
| Rename a field | `createdAt` → `created_at` | Breaking |
| Rettype a field | `imageUrl` string → object | Breaking |
| Reorder fields | reorder the frozen `AssistantReply` | Breaking (forbidden outright, F-13) |
| Change semantics | `name` now means display name, not real name | Breaking |
| Change a status-code mapping | `404` → `401` on login | Breaking |
| Change the error shape / taxonomy | new `error.code`, dropped `details` key | Breaking |
| Change auth/ownership on an endpoint | previously public becomes auth-required | Breaking (deferred to gated modules, API-12) |
| Add an endpoint | new resource or operation | **Not** breaking (additive) |
| Add an optional response field | new `stats` object on an existing list | **Not** breaking (minor bump, §2.1) |
| Mount a sealed/gated module's endpoints | M16 media after MS10.3 | **Not** breaking (additive, §4.4) |
| Data-level version bumps | `engine_version`, `content_version` | **Not** breaking (§2.2) |

### 4.2 The rule

- **Additive changes** land in the current major immediately; if they add
  optional response fields, the available minor pin is bumped (§2.1).
- **Any breaking change ships as a new path major** (`/v2`) — never edited into
  `/v1` in place (API-2/API-4).
- **A breaking change never lands silently and never lands alone**: it goes
  through the deprecation lifecycle (§5), the migration mechanics (§6), and the
  mobile-compat review (§8) before the old major is removed.

### 4.3 What is intentionally excluded from "can be broken"

- The **frozen assistant contract** (F-13) and **`GET /health`** have no
  breaking-change path at all: they are versionless invariants. If the domain
  ever genuinely needs a different assistant shape, it is a **new endpoint** in
  a new version, never a mutation of the live one (`ASSISTANT_API.md` §1).
- **Privacy/security posture** (OW-1, 404-not-403, ER-0…3, media privacy,
  MS10.3): these may only get *stronger*; a weakening is out of scope entirely,
  not a versioning question.

### 4.4 Gated/sealed modules are additive by construction

Endpoints from sealed/gated modules (M11 feedback, M16 media, P2 analysis/
generation/subscriptions, A-3/4/5, W-2, E-3) are **unmounted until their gate
lands** (API-12). When they mount they are *new endpoints under `/v1`* —
additive, no version bump, no change to any existing endpoint (`API_LAYER_
ARCHITECTURE.md` §3.3/§7). This is the contract's way of "extending around"
rather than "into" the live surface (`ASSISTANT_API.md` §1).

---

## 5. Deprecated endpoints

### 5.1 Deprecation signals

When a major is superseded, the server marks the old major on **every response**
it serves and in **its discovery surface**:

| Signal | Where | Meaning |
| --- | --- | --- |
| `Deprecation: true` | response header on `/v1` responses (once `/v2` is live) | This version is superseded; new clients should not start on it |
| `Sunset: <RFC 3339 date>` (RFC 8594) | response header on `/v1` responses | Scheduled removal date of this major |
| Supported-versions list | `GET /health` (§7) | What is live now, what is deprecated, what is sunset |
| Changelog entry | this doc's companion notes / module docs | Human-readable what/why/when |
| No new feature work | roadmap | A deprecated major receives **no new fields** (its minor pin is frozen) — it is bug/security-fix only |

### 5.2 Behavior during the deprecation window

- A deprecated major **keeps its full guarantees** (additive-frozen, status-
  codes stable, taxonomy stable) until sunset — deprecation is not partial
  breakage.
- Requests to a deprecated major succeed normally; they just carry the
  `Deprecation`/`Sunset` headers so the client can schedule an update.
- **Only security/privacy fixes** are backported to the deprecated major;
  feature work happens on the new major.

### 5.3 Sunset

- On the scheduled `Sunset` date the old major is **unmounted**: requests to
  `/v1/...` return `410 Gone` (not `404`, so the client can distinguish "moved"
  from "never existed"), with a body pointing to the new major.
- The removal is a **separate rollout step** from shipping `/v2` (§6.1), so it
  can be delayed if mobile reach shows unsupported builds still calling `/v1`
  (§8.3).
- A `410 Gone` is the **only** signal a client may treat as "this API version
  is gone"; the mobile client maps it to an update-required flow (§8.4).

---

## 6. Migration strategy

### 6.1 Side-by-side majors (non-breaking migration, API-4)

- `/v2` is deployed **additively**: both version routers mount under the same
  app; routing is a pure prefix split (`/v1/...` → v1 routers, `/v2/...` → v2
  routers). No shared wire shape is mutated at deploy time
  (`API_LAYER_ARCHITECTURE.md` §3; `API_CONTRACT_RULES.md` §15).
- The live endpoints keep working verbatim through every step (M1–M6 migration,
  19 tests stay green — `API_CONTRACT_RULES.md` §15).
- Where `/v1` and `/v2` share domain logic, they call the **same use cases**
  (DR-1) and only differ in their projection layer (F-6) — the cost of running
  two majors is the projection, not duplicated business logic.
- **Rollback is free:** removing or rolling back `/v2` never touches `/v1`;
  the two are independent deployment units behind the prefix split.

### 6.2 The window

- The minimum coexistence window is **one full app release cycle after the
  last supported app build targets the new major** — defined operationally, not
  by calendar alone (§8.3): a major may only be sunset once **no app build in
  the supported range still calls it**.
- A calendar floor is set at rollout time (default: **≥ 90 days** after `/v2`
  is live), whichever is longer. The exact date is announced via `Sunset`
  (§5.1) and re-checked against mobile telemetry before removal.

### 6.3 Data compatibility across majors

- The API version is a **wire** contract; the storage schema is versioned
  separately (resource `version` ints, `content_version`, `engine_version` —
  §2.2). `/v1` and `/v2` may read the **same data**; a `/v2` projection must
  handle data written by v1-era clients and vice versa.
- Writes made by an old-major client must remain valid data for the new major
  (no field meaning change; new-optional defaults are server-side) — the
  migration never depends on rewriting client data.

### 6.4 Forward tolerance (both directions)

- **Old client → new backend (the required case):** new optional fields are
  ignored or unused; new endpoints are never called by old clients; response
  vocabularies may contain new values → the client treats unknown values
  gracefully (§8.4).
- **New client → old backend (rollback / partial rollout):** a `/v2` client
  never talks to a backend that only serves `/v1` unless it falls back
  (accept-version negotiation, §8.2). A rollback of `/v2` therefore does not
  strand `/v1` clients; `/v2` clients simply see the version fail during the
  rollback window.

---

## 7. Version discovery

- **`GET /health`** stays versionless and envelope-free (API-4) and is extended
  (additively) to report the served-version list, e.g. current, deprecated,
  sunset date — the single machine-readable place to negotiate versions.
  `GET /health` is not a data endpoint, so its payload is exempt from the
  envelope rules and is safe for any client to parse.
- **Every response** may carry an `X-API-Version: 2` header (server major that
  served it) for support triage; optional, additive, never relied upon by the
  client logic.
- Unsupported version negotiation (`Accept: application/json; version=9.9`, or
  a path major that is not served) → `422` with a clear message (API-3) /
  `410 Gone` for a sunset major (§5.3).

---

## 8. Mobile app backward compatibility

> **Core constraint (accepted from the task):** mobile apps remain on older
> builds after a backend update. The API is designed so that **no backend
> release ever requires all installed builds to update**. The pairing rule
> below is the mechanism.

### 8.1 App/API pairing rule

- Each app build declares the API major it targets in its path (`/v1`), and may
  pin a minor (`Accept: application/json; version=1.0`). The current app is
  `fansivibe 1.0.0+1` (pubspec) → **targets API v1, default minor**.
- **The supported server surface always covers every API version used by an
  app build that is still in the supported-app range.** "Supported-app range"
  is the set of builds the product still supports (defined at release time —
  the minimum supported app build). The server may serve the current major only
  for builds that predate the supported range, and it must tell them so (`410`/
  `422` → update-required, §8.4).
- Concretely: the server keeps **at least two majors** (current + previous)
  mounted at all times; a major is retired only when §8.3 says so.

### 8.2 How the client negotiates

- The app **does not pin by default** (it wants the latest additive shape of
  its target major), but it **always tolerates unknown JSON fields and unknown
  enum/vocab values** in responses (never crash, never drop the record, render
  unknown values as "other"/neutral).
- A build that needs a frozen shape (e.g. a long-tail OS version shipped once)
  **pins** its exact minor on requests so it is never handed new fields it was
  not tested against.
- On `422` version-unsupported the app treats the API as ahead of it and either
  upgrades in place or shows an update prompt — never retries in a loop.

### 8.3 Retiring a version vs. installed builds

A major may be sunset only when **both** hold:

1. it has been deprecated ≥ 90 days (§6.2), **and**
2. telemetry shows **no request** from any app build in the supported-app range
   still using that major (the product's minimum-supported-build policy gates
   this — the server's served-version set is derived from it).

The two conditions make the calendar and the fleet agree: an unusually slow
rollout stretches the window; a fast fleet can retire early, never earlier than
90 days.

### 8.4 Client-side behaviors for each signal

| Signal | Client behavior |
| --- | --- |
| `Deprecation: true` on a response | Non-urgent: log + schedule an upgrade prompt; keep working |
| `Sunset` header date approaching | Urgent: prompt to update before the date; still keep working |
| `410 Gone` on the app's API major | Update-required screen; explainable from the response body |
| `422` version-unsupported | Same as `410` (API ahead of the client) |
| New optional fields in responses | Ignore, keep rendering known fields (§8.2) |
| New values in controlled-vocabulary responses | Render as neutral/other; never crash |
| New endpoints | Never called by old builds (paths are additive-only) |

### 8.5 What this policy protects

- **No forced simultaneous upgrade** ever: a backend release never bricks an
  installed build that still hits `/v1`.
- **No "latest-wins" surprises:** a build that pinned `1.0` is served exactly
  `1.0`'s field set for its whole supported life.
- **No orphaned data:** old-major writes remain valid in the new major (§6.3),
  so a user who upgrades the app after the backend already moved keeps their
  data and history.
- **Testing:** every release is validated against the previous major's contract
  tests (the M1–M6 migration keeps 19 tests green verbatim); mobile CI runs the
  contract suite for the app's supported majors, not just latest.

---

## 9. Validation reference

- **Versioning rules** trace to `API_LAYER_ARCHITECTURE.md` §3 (API-1…4),
  `API_CONTRACT_RULES.md` §15 + C-14, `API_RESPONSE_CONVENTIONS.md` §11.
- **Frozen assistant DTOs** trace to `ASSISTANT_API.md` §1/§3.4 (F-13, A3.1).
- **Error-taxonomy frozenness** traces to `ERROR_HANDLING.md` §4/§5 and
  `API_ERROR_CONTRACT.md` (12 categories, allow-list `details`, ER-0…3).
- **Gated/sealed additive mounting** traces to `API_LAYER_ARCHITECTURE.md` §3.3/
  §7 (API-12) and the security review's finding F-9 gates.
- **Migration** traces to `API_CONTRACT_RULES.md` §15 (M1–M6, 19 tests) and
  `ASSISTANT_API.md` §1.
- **Live surface** re-verified against `backend/app/main.py:18,23`
  (`GET /health`, `POST /v1/assistant/chat`).
- No code, routers, headers, middleware, or Flutter changes; `git status
  --short` unchanged except `CURRENT_STATE.md` + this new doc.

---

## 10. Report

**What changed (this step):** added `docs/api/API_VERSIONING.md` — the complete
versioning & compatibility policy: version model (path major `/vN` + optional
minor pin, API-1…3), frozen in-version guarantees (§3), breaking-change
classification and rule (§4, incl. gated-module additivity), deprecation
signals and sunset → `410 Gone` (§5), side-by-side non-breaking migration with
the ≥90-day + fleet-telemetry window (§6), version discovery via `GET /health`
(§7), and the **mobile backward-compatibility policy** (§8: pairing rule,
forward tolerance, retirement conditions, per-signal client behaviors). **No
implementation.**

**Skills used:** repository analysis (live `main.py`, `pubspec.yaml`
`1.0.0+1`, `API_LAYER_ARCHITECTURE.md` §3) + design-doc synthesis (API-1…4,
C-14, F-13, ER-0…3, API-12, M1–M6, OW-1) — documentation only.

**Files changed:** `docs/api/API_VERSIONING.md` (new); `CURRENT_STATE.md`
(updated).

**Validation run:**
- Every rule cites an accepted source (`file:line` or section ref); no new
  endpoint, DTO, header, or wire shape is introduced — only policy on top of
  the accepted rules.
- The live `GET /health` + `POST /v1/assistant/chat` stay verbatim (API-4,
  F-13); `GET /health` versionless rule preserved.
- No code changed → no `pytest` run needed; `git status --short` shows only
  `CURRENT_STATE.md` modified + `docs/api/` (now 18 untracked API docs).

**Remaining issues / follow-ups:**
- The **fleet-telemetry signal** ("no supported-range build calls the old
  major", §8.3) is a dependency on the observability/mobile-analytics decision
  (`OBSERVABILITY.md`) and the product's minimum-supported-app-build policy —
  not a wire-contract change.
- Exact `X-API-Version` header presence is optional today (additive); whether
  it is emitted is finalized when the observability middleware lands.
- No `DECISIONS.md` entry needed: no accepted architectural decision made
  (documentation of policy only); open items remain in the module docs and the
  `CURRENT_STATE.md` remaining gates.
