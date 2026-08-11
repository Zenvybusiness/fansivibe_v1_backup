# Fansivibe — API Contract: Subscriptions & Feature Entitlements

> **STEP 6 — API CONTRACT DESIGN.** Defines the **production subscription and
> feature-entitlement API contract** based on the finalized domain model. The
> **CURRENT** state is documented first (the subscription surface as it exists
> today — a Flutter stub with mock plans and **no backend endpoint at all**),
> then the **TARGET** contract (the two accepted inventory operations plus the
> honest treatment of the candidate operations: list plans, cancel, restore,
> entitlements, usage). It is the focused companion to `API_CONTRACT_RULES.md`
> (§12.14 subscriptions, §11 idempotency), `API_INVENTORY.md` (endpoints 45–46,
> §5.15), `APPLICATION_USE_CASES.md` (UC-33), `TABLE_DEFINITIONS.md`
> (`subscriptions`), and the domain model docs (E10, R44/R45/R46/R51/R-A20,
> G11), and it sits beside the sibling contracts `AUTH_API.md` (Bearer, OW-1,
> erasure → 409 cancel-first), `PROFILE_ONBOARDING_API.md` (M2 profile surface),
> and `FEEDBACK_LEARNING_API.md` (feature usage = the `LearningSignal` trace).
>
> **Status: contract design only. Nothing is implemented.** No code, no
> routers, no `deps.py`, no SQL migrations, no dependencies, no Flutter changes.
> **No payment provider is integrated** and **no billing is implemented**. The
> two accepted operations are **not mounted** until auth (D-AUTH-1) and the
> M15 module land; the provider webhook stays server-to-server (R51); no fake
> 200 before the gates (API-12).
>
> **Source of truth:** the real Fansivibe repository — the Flutter subscription
> stub (`lib/features/profile/presentation/subscription_screen.dart`,
> `lib/features/profile/data/profile_mocks.dart` `SubscriptionPlan`/`plans`,
> `lib/app/router/app_router.dart:402-404`,
> `lib/features/profile/presentation/profile_screen.dart:128-129`,
> `lib/features/onboarding/data/onboarding_data.dart` `allCapabilities`) and
> the backend (`backend/app/` — **no subscription code exists**), plus the
> accepted STEP 3/4/5/6 docs — `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` (§3.3–3.6),
> `DOMAIN_RELATIONSHIPS.md` (R10, R44–R46, R51),
> `TABLE_DEFINITIONS.md` (`subscriptions`, `subscription_plans`),
> `APPLICATION_USE_CASES.md` (UC-33 §5.12), STEP 6 `API_CONTRACT_RULES.md`
> (§12.14/§11/§9/§13) + `API_INVENTORY.md` (endpoints 45–46) +
> `AUTH_API.md` (§ delete account, 409 cancel-first) +
> `ERROR_HANDLING.md` (§5.10 EXTERNAL_SERVICE_FAILURE, §5 taxonomy) +
> `FASTAPI_ARCHITECTURE_V1.md` (M15).

---

## 1. Purpose and scope

This document answers the STEP 6 subscription task in two clearly separated
halves:

- **CURRENT (§3)** — the subscription surface as it actually exists today:
  the Flutter `SubscriptionScreen` stub, its mock plan data, its behavior, and
  its limitations. Critically, there is **no backend subscription endpoint** —
  nothing to preserve, only the product surface to document. Nothing here is
  speculative.
- **TARGET (§4–§5)** — the production subscription contract derived from the
  finalized domain model: the **two accepted inventory operations** (endpoints
  45/46) with exact paths, DTOs, idempotency, and errors, plus the **honest
  disposition of every candidate operation** the task lists — get current
  subscription, list plans, start subscription, cancel subscription, restore
  subscription, get feature entitlements, get feature usage — grounded in the
  domain model (entitlement is **derived**, never stored; payment/billing is
  **external**, R51; feature usage **is** the existing signal trace).

The task's candidate list is mapped explicitly (§4.2 operation selection):

- **get current subscription** — A-1 (inventoried 45) — §5.1
- **start subscription** — A-2 (inventoried 46, UC-33) — §5.2
- **list plans** — **NOT a subscription-module endpoint** — plans are system
  knowledge content (K9.1), finalized at M3 — §4.4.1
- **cancel subscription** — **external lifecycle** (R51), reflected via the
  provider webhook — no client endpoint — §4.4.2
- **restore subscription** — rides the existing sync contract (UC-9) + the
  A-1 server read — no dedicated endpoint — §4.4.3
- **get feature entitlements** — **derived** (R45/R-A20); no per-user rows
  until P3; not an endpoint today — §4.4.4
- **get feature usage** — maps 1:1 to the `LearningSignal` trace (E7); no new
  endpoint — §4.4.5

**The three binding design rules of this document:**

1. **Entitlement is derived state, never stored (R45, PR-2).**
   `CapabilityAvailability` is recomputed at read time from *plan config × the
   `subscriptions` row* — there is **no** per-user entitlement/features column
   and no entitlement endpoint. The `Subscription` DTO is the wire shape of the
   user-owned `subscriptions` state row, nothing more.
2. **Payment and billing are an external seam (R51), not a backend
   feature.** The backend integrates **no payment provider** (this task) and
   never stores payment details. The provider webhook is **server-to-server**
   (system principal), **idempotent**, and **never inside a DB transaction**;
   `POST /v1/subscriptions` only *initiates* the purchase (payment call after
   commit) and records entitlement state. Cancellation is likewise external.
3. **The TARGET adds nothing beyond the accepted inventory (API-2/API-12).**
   Only endpoints 45/46 exist in the 48-endpoint catalog for subscriptions;
   every other candidate operation is either **external** (cancel), **rides an
   existing contract** (restore → UC-9 + A-1), **knowledge-content** (list
   plans → M3), or **derived/existing** (entitlements, usage). No invented
   endpoints, no fake 200.

**What it does not do:** implement anything, mount endpoints, add auth before
D-AUTH-1, integrate a payment provider, design billing, invent a
`subscriptions.status` vocabulary (open until the billing integration), define
the `subscription_plans` knowledge table (M3), or add entitlement/usage/cancel
endpoints that the product/domain model does not support.

### 1.1 Grounding facts (re-verified)

- **There is no subscription backend surface today.** `backend/app/` contains
  **no** subscription route, DTO, or repository — `schemas.py` defines only the
  assistant/wardrobe DTOs; the only live routes are `GET /health` and
  `POST /v1/assistant/chat` (`main.py`). The subscription feature is entirely a
  Flutter stub (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.3; `ACTION_API_INVENTORY.md`
  #30 "purchase is a stub").
- **The Flutter surface is one read-only screen.** `SubscriptionScreen`
  (`subscription_screen.dart`, 229 lines) renders `ProfileMockData.plans` — 3
  `SubscriptionPlan` cards (Free $0, Premium $9.99 **Popular**, Elite $19.99,
  each with a `features: List<String>` list) plus a footer "Cancel anytime ·
  No hidden fees". Route `RouteNames.profileSubscription` = `'profile-subscription'`
  → `/profile/subscription` (`app_router.dart:402-404`); pushed from
  `ProfileScreen._handleMenuAction` case `'subscription'`
  (`profile_screen.dart:128-129`).
- **Every subscribe CTA is a no-op.** "Current Plan" / "Subscribe" buttons call
  `onPressed: () {}` (`subscription_screen.dart:197`); no purchase, no state,
  no loading/empty/error states (`SCREEN_DATA_INVENTORY.md` §11.4).
- **`SubscriptionPlan` is a display-only mock, not an entity.** Fields
  `name`, `price` (display string, e.g. `"$9.99"` — **no money math**), `period`,
  `features`, `isPopular` (`profile_mocks.dart:31-45`). It has **no `id`/`code`**
  — the `planCode` the inventory requires does not exist in the mock.
- **Entitlement does not exist.** `allCapabilities` (`onboarding_data.dart:79-119`)
  is a static list of 7 `AiCapability` items whose `active` flags are **marketing
  copy with no gating** (`AI_DATA_FLOW.md` Part D.1; `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md`
  §3.5). No feature is gated by plan today.
- **Feature usage = the existing signal trace.** `Feature Usage` maps 1:1 to
  `LearningSignal` (E7, 8 types), append-only, M10 sole writer
  (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.6; `FEEDBACK_LEARNING_API.md`).
- **The accepted inventory has exactly two subscription operations** — endpoint
  45 `GetSubscription` (`GET /v1/subscriptions/me`) and endpoint 46
  `SubscribeToPlan` (`POST /v1/subscriptions`, UC-33), both auth + owner (OW-1),
  both P2 (`API_INVENTORY.md` §5.15, §5.15 table at lines 158-159; module M15 —
  `FASTAPI_ARCHITECTURE_V1.md:149`).
- **`subscriptions` is a current-state table, 0..1 per user.** `id uuid PK`,
  `user_id uuid UNIQUE FK→users CASCADE` (R10), `plan_code text FK→
  subscription_plans.code RESTRICT`, `status text` (vocabulary **open** — set
  with the billing integration), `started_at`, `renews_at` (nullable;
  non-recurring), `external_ref` (nullable; R51), `created_at/updated_at`
  (`TABLE_DEFINITIONS.md:483-505`). **Entitlement is derived from config × this
  row** (PR-2, R45), never stored.
- **`subscription_plans` is a referenced knowledge table, not yet defined.**
  It is the FK target for `plan_code` and carries `price_display text` (no money
  math) + optional `features jsonb` (PR-12); the knowledge vocabulary tables are
  finalized at **M3** (`TABLE_DEFINITIONS.md:576-582`; `FASTAPI_ARCHITECTURE_V1.md`
  F-2).
- **`Idempotency-Key` is required on `POST /v1/subscriptions`** and **not**
  on `GET /v1/subscriptions/me` (naturally idempotent read)
  (`API_CONTRACT_RULES.md` §11, line 377).
- **Payment failures use 402/424, store failure 503.** `EXTERNAL_SERVICE_FAILURE`
  maps to 502 (identity) / 503 (other) / **402/424 (payment outcome)** for UC-33
  (`ERROR_HANDLING.md` §5.10; `API_LAYER_ARCHITECTURE.md:238`). 404-not-403 for
  foreign/non-existent resources (OW-1, API-10).
- **Account erasure requires cancel-first.** `DELETE /v1/users/me` → **409
  CONFLICT** "active subscription must be cancelled first — external
  entitlement, R51" (`AUTH_API.md:388`); erasure cascades external subscription
  cancellation (TRX-8).
- **No auth anywhere yet.** All subscription operations gate on D-AUTH-1; the
  `Subscription` surface ships no auth semantics until then.

---

## 2. Source of truth and inputs

| Concern | Source |
| --- | --- |
| Live wire contracts | `backend/app/models/schemas.py`, `backend/app/main.py` (no subscription surface) |
| Flutter surface | `subscription_screen.dart`, `profile_mocks.dart:31-45,160-199`, `profile_screen.dart:128-129`, `app_router.dart:402-404` |
| Accepted endpoints | `API_INVENTORY.md` §5.15 (45/46), §5.15 table (158-159) |
| Canonical endpoint rules | `API_CONTRACT_RULES.md` §12.14, §11, §9, §13 |
| Use cases | `APPLICATION_USE_CASES.md` UC-33 (§5.12), UC-9 (`SyncLocalData`) |
| Storage | `TABLE_DEFINITIONS.md` `subscriptions` (483-505), `subscription_plans` (576-582) |
| Domain model | `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.3–3.6, §4; `DOMAIN_RELATIONSHIPS.md` R10/R44/R45/R46/R51 |
| Entitlement semantics | `AI_DOMAIN_MODEL.md` R-A20; `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.5 (derived, P3); G11 |
| Errors | `ERROR_HANDLING.md` §5.10, §5 taxonomy; `API_LAYER_ARCHITECTURE.md` OW-1 |
| Auth / erasure | `AUTH_API.md` § account deletion (409 cancel-first, R51); `AUTH_AUTHORIZATION_ARCHITECTURE.md` |
| Module map | `FASTAPI_ARCHITECTURE_V1.md` M15 |
| Feature usage | `FEEDBACK_LEARNING_API.md`; `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.6 |

---

## 3. CURRENT — the subscription surface as it exists today

> This section documents only what is actually in the repository. **There is no
> API to review** — so unlike the assistant contract, the "current API" is the
> Flutter stub surface. **Nothing here is a design proposal.**

### 3.1 Current surface — no backend endpoint

| Attribute | Value |
| --- | --- |
| **Backend endpoint** | **None.** No `subscriptions` route, DTO, or repository exists in `backend/app/`. |
| **Flutter screen** | `SubscriptionScreen` (`subscription_screen.dart`) |
| **Route** | `profileSubscription` → `/profile/subscription` (`app_router.dart:402-404`) |
| **Entry** | `ProfileScreen` menu `'subscription'` → `pushNamed` (`profile_screen.dart:128-129`) |
| **Data source** | `ProfileMockData.plans` (static const, `profile_mocks.dart:160-199`) |
| **Auth** | **None** — no `Authorization`, no user scoping, no account. |
| **Purchase** | **None** — all CTAs are `onPressed: () {}` no-ops. |
| **Entitlement** | **None** — no feature is gated by plan. |

### 3.2 Current request model

**None.** There is no network request. The screen reads a static const list
`ProfileMockData.plans` locally; nothing is sent anywhere and nothing is read
from a server.

### 3.3 Current response / data model

The only "response" is the local mock catalog (`profile_mocks.dart:31-45,
160-199`):

```dart
class SubscriptionPlan {
  final String name;          // "Free" | "Premium" | "Elite"
  final String price;         // display string "$0" | "$9.99" | "$19.99"
  final String period;        // "/month"
  final List<String> features; // marketing copy — no gating
  final bool isPopular;       // Premium only
}

static const List<SubscriptionPlan> plans = [ /* Free, Premium, Elite */ ];
```

| Plan | Price | Period | Popular | Feature highlights (copy) |
| --- | --- | --- | --- | --- |
| Free | `$0` | /month | no | Basic style score; 3 saved looks; wardrobe ≤20; standard recs |
| Premium | `$9.99` | /month | **yes** | Advanced analytics; unlimited looks/wardrobe; AI outfit gen; priority support |
| Elite | `$19.99` | /month | no | Everything in Premium; stylist review; exclusive insights; early access; VIP |

**Structural honesty (AI-0):** no `planCode`/id, no status, no dates, no
`external_ref` — these are **not modeled** in the mock. The `features` strings
are display copy, **not** capability/entitlement data.

### 3.4 Current behavior

- The screen renders three `_PlanCard`s from `ProfileMockData.plans`
  (`subscription_screen.dart:13,59-64`), each a `FansivibeCard`
  (`CardVariant.high` for the popular plan) with name, price+period, feature
  list, and a full-width button labeled **"Current Plan"** for `Free` and
  **"Subscribe"** otherwise (`subscription_screen.dart:218`).
- All buttons call `onPressed: () {}` — **no purchase, no navigation, no
  state change** (`subscription_screen.dart:197`).
- Footer text "Cancel anytime · No hidden fees" is static
  (`subscription_screen.dart:68`).
- No loading, empty, or error states; no server interaction
  (`SCREEN_DATA_INVENTORY.md` §11.4).
- Widget coverage: `profile_screens_test.dart` renders the screen; the mock
  data and layout are asserted, not any network behavior.

### 3.5 Current limitations

| # | Limitation | Evidence | Resolved by (TARGET) |
| --- | --- | --- | --- |
| L1 | **No backend endpoint at all** — the screen renders local mocks; there is nothing to call. | `backend/app/` (no subscription code) | §5.1/§5.2 (inventoried 45/46, gated on D-AUTH-1/M15) |
| L2 | **No plan identity** — `SubscriptionPlan` has no `planCode`/id, but the contract requires `SubscribeRequest { planCode }`. | `profile_mocks.dart:31-45` | §4.4.1 (plan codes come from the M3 knowledge catalog, not the mock) |
| L3 | **Subscribe is a no-op** — `onPressed: () {}`; no purchase, no 402/404/503 handling. | `subscription_screen.dart:197` | §5.2 (A-2 + webhook semantics; UI flow out of scope here) |
| L4 | **No entitlement/gating** — `allCapabilities.active` and plan `features` are marketing copy. | `onboarding_data.dart:79-119`; §3.5 | §4.4.4 (derived R45; per-user rows only at P3, G11) |
| L5 | **No account/auth** — the screen is anonymous; no `user_id`, no ownership. | `F-5` (no auth) | §4.3.1 (gates D-AUTH-1) |
| L6 | **No `subscriptions` state** — no status, dates, or renewal anywhere. | `subscription_screen.dart` | §5.1 (A-1 `Subscription` DTO) |
| L7 | **No cancel/restore surface** — nothing models lifecycle. | §3.4 | §4.4.2/§4.4.3 (external + sync-ride semantics) |

---

## 4. TARGET — the production subscription & entitlement contract

### 4.1 Design intent: preserve the accepted inventory, extend honestly

The TARGET anchors on the **two accepted operations (45/46)** and defines the
disposition of every candidate the task lists. It integrates **no payment
provider** and **no billing** — it documents the contract the product will need,
with every gate explicit:

| Layer | Today (CURRENT) | Target (TARGET) | Change type |
| --- | --- | --- | --- |
| Subscription state read | none (no endpoint) | `GET /v1/subscriptions/me` → `Subscription` | new endpoint (inventoried 45) |
| Subscribe | no-op button | `POST /v1/subscriptions` (initiation; provider webhook completes) | new endpoint (inventoried 46, UC-33) |
| Plan catalog | `ProfileMockData.plans` | knowledge content served from the M3 catalog (stable `planCode`) | data source (M3) |
| Entitlement | none (marketing copy) | **derived** at read time (R45) from plan × subscription | semantics (P3, G11) |
| Cancel | none | **external** provider lifecycle (R51), state via webhook | external seam |
| Restore | none | rides UC-9 sync + A-1 read | no new endpoint |
| Feature usage | signal trace | the existing `LearningSignal` history | no new endpoint |
| Auth | none | Bearer → `user_id` once D-AUTH-1 | additive (gated) |

### 4.2 Operation selection

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| A-1 | **Get current subscription** | **Required** — `GET /v1/subscriptions/me` | Inventoried endpoint 45; read the user's entitlement state. §5.1. |
| A-2 | **Start subscription** | **Required** — `POST /v1/subscriptions` | Inventoried endpoint 46, UC-33; initiate purchase via the provider, state via webhook. §5.2. |
| A-3 | **List plans** | **NOT defined here** | Plans are system **knowledge content** (K9.1), finalized at M3 (`subscription_plans`); the knowledge surface serves them — not a subscription-module endpoint. §4.4.1. |
| A-4 | **Cancel subscription** | **NOT defined (external)** | Cancellation is the external provider's lifecycle (R51); the backend reflects it via the webhook. No client endpoint in the inventory. §4.4.2. |
| A-5 | **Restore subscription** | **NOT defined (rides existing)** | Device/account restore is `POST /v1/users/me/sync` (UC-9); subscription state re-reads via A-1 (server is source of truth). §4.4.3. |
| A-6 | **Get feature entitlements** | **NOT defined (derived)** | `CapabilityAvailability` is derived (R45/R-A20) from config × subscription at read time; no per-user rows until P3 (G11). §4.4.4. |
| A-7 | **Get feature usage** | **NOT defined (existing trace)** | Feature usage **is** the `LearningSignal` history (E7, 8 types); aggregates derived. §4.4.5. |

### 4.3 Shared semantics (apply to A-1/A-2)

#### 4.3.1 Auth and ownership

- **Gated on D-AUTH-1:** no subscription endpoint is mounted until auth lands
  (API-12 — no fake 200). Today the surface is anonymous.
- **Bearer token:** `Authorization: Bearer <token>` → `user_id` via `deps.py`
  (API-5/API-6); missing/invalid/expired/revoked → `401 AUTHENTICATION_ERROR`
  + `WWW-Authenticate`.
- **Owner-scoping (OW-1, API-10):** every subscription operation resolves under
  the authenticated `user_id`. A user can never read/write another user's
  subscription — a foreign/non-existent row returns **404-not-403** (no
  existence leak). `subscriptions.user_id` is the owner key (`TABLE_DEFINITIONS.md`).
- **Identity = user_id only (F-3):** bodies carry no email/name/token; the
  domain sees only `user_id`.
- **Path-collision guard:** `/v1/subscriptions/me` and `/v1/subscriptions`
  register under the M15 module (`subscriptions`), no shadowing
  (`API_CONTRACT_RULES.md` §7).

#### 4.3.2 Entitlement is derived, never stored (R45)

- **There is no entitlement endpoint and no entitlement column.** Feature
  availability is **recomputed at read time** from *`subscription_plans`
  config × the `subscriptions` row* (R45, PR-2; `TABLE_DEFINITIONS.md` "derived
  facts are never stored"). The client derives "what am I allowed to do" from
  the `planCode` + the capability catalog (K9.1).
- **`CapabilityAvailability` is a derived 1:1 view** (R45/R-A20/P13), recomputed
  on entitlement change; **no per-user entitlement rows exist or should be
  created** until a real capability/unlock system lands (**P3**, G11)
  (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.5).
- The `Subscription` DTO therefore exposes **planCode + lifecycle dates**, the
  inputs the client needs to derive entitlement — not a stored entitlement
  list.

#### 4.3.3 Errors, idempotency, correlation

- **Typed error contract (A3.3/E13.1):** subscription endpoints return the
  frozen `{ error: { code, message, details? } }` body with the 12-category
  taxonomy (`ERROR_HANDLING.md` §5). `details` is allow-listed — field names,
  allowed values, `request_id`; never SQL, stack traces, tokens, or payment
  details (ER-0/ER-1).
- **Idempotency (API-33…35):** `POST /v1/subscriptions` **requires
  `Idempotency-Key`** (repeat with same key + `user_id` → original result;
  conflicting payloads → 409). `GET /v1/subscriptions/me` is naturally
  idempotent (no key).
- **Correlation:** every response carries `X-Request-Id` (echoed from the
  request when present) — a request-id, never user data (`OBSERVABILITY.md`).
- **Rate limiting:** `429 RATE_LIMITED` with `Retry-After` in `details` once
  infrastructure exists.

#### 4.3.4 The provider webhook (server-to-server, R51)

- The billing/entitlement provider callback is **server-to-server** (system
  principal — no Bearer user token), **idempotent**, and **never runs inside a
  DB transaction** (R51; `API_CONTRACT_RULES.md` §12.14; UC-33 "external payment
  call runs after commit").
- The webhook updates the `subscriptions` row (status/`renews_at`/
  `external_ref`) **only** — **payment details are never stored**; the backend
  keeps entitlement state alone.
- This is the mechanism that *completes* A-2 (activation) and *reflects* A-4
  (cancellation/expiry) — the client-facing surface never talks to the provider.

### 4.4 Candidate operations — honest dispositions

#### 4.4.1 A-3 — List plans: knowledge content, not a subscription endpoint

- Plans are **system-owned knowledge content** (`subscription_plans` — price is
  `price_display text` with **no money math**, `features jsonb` for
  config-driven capability names, PR-12) (`TABLE_DEFINITIONS.md:576-582`).
- The catalog is finalized at **M3** (knowledge vocabulary), served by the
  **knowledge surface** (public, read-mostly, `X-Knowledge-Version`, like the
  M5 public catalog endpoints — `API_INVENTORY.md` §5.6) — **not** by a
  subscription-module endpoint.
- The `SubscriptionScreen` must switch its data source from
  `ProfileMockData.plans` to this catalog (resolving L2: stable `planCode` ids),
  which is a **data-source change under M3**, out of scope for the subscription
  module.
- **Contract consequence:** `SubscribeRequest.planCode` is validated against the
  knowledge catalog → `422 VALIDATION_ERROR` (unknown code) and the webhook/use
  case → `404 NOT_FOUND` (plan no longer available).

#### 4.4.2 A-4 — Cancel: external lifecycle (R51)

- Cancellation is the **external provider's** operation; the backend does not
  cancel anything itself (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.3 lifecycle
  "activate → renew → cancel/expire (via external service)").
- The backend **reflects** the cancelled state via the provider webhook (§4.3.4)
  and its own state remains **consistent with erasure**: `DELETE /v1/users/me`
  returns **409 CONFLICT** when a subscription is active — "must be cancelled
  first — external entitlement, R51" (`AUTH_API.md:388`), and account erasure
  cascades external cancellation (TRX-8).
- **No client cancel endpoint exists in the 48-endpoint inventory** — a
  client-facing cancel would be an accepted decision (in-product provider
  redirect vs provider UI) and is **not defined here** (API-12).

#### 4.4.3 A-5 — Restore: rides the existing sync contract

- Device/account restore is **`POST /v1/users/me/sync`** (UC-9, endpoint 10 —
  upserts the local `UserModel` snapshot in one transaction, `Idempotency-Key`
  required) (`API_INVENTORY.md:345-364`).
- Subscription state is **user-owned current state on the server** (R10);
  after login/restore the client simply **re-reads it via A-1**
  (`GET /v1/subscriptions/me`) — the server is the source of truth. **No
  dedicated restore endpoint.**

#### 4.4.4 A-6 — Feature entitlements: derived, not an endpoint

- `CapabilityAvailability` is **derived** from *capability/feature catalog
  (config) × subscription state* (R45/R46/R-A20, `AI_DOMAIN_MODEL.md:296`); it is
  **not an entity** and **not persisted** (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md`
  §3.5).
- Today `allCapabilities.active` flags are **marketing copy** (L4); no gating
  exists (R46: static config, no per-user state — prospective).
- **No entitlement endpoint is defined.** A capability gating surface would be a
  P3 capability/unlock decision (G11) and would derive from the `planCode` +
  knowledge catalog client-side — **not** a stored entitlement API.

#### 4.4.5 A-7 — Feature usage: the existing signal trace

- Feature usage maps **1:1 to the `LearningSignal` trace** (E7, 8 types),
  append-only, **M10 sole writer** (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.6).
- Per-feature aggregates (`ActivityDay`, `StyleScoreRecord`) are **derived
  records** — **no new entity, no new endpoint** (PR-2). Any analytics/usage UI
  consumes the existing signal/history surface (`FEEDBACK_LEARNING_API.md`),
  not a subscription-module endpoint.

---

## 5. Operation contracts

Each operation follows the sibling convention: method/path, request schema,
response schema, validation, authorization, errors, security, side effects,
domain entities, plus status flags.

### 5.1 A-1 — Get current subscription (`GetSubscription`, endpoint 45)

- **Method / path:** `GET /v1/subscriptions/me`
- **Status:** **inventoried, NOT mounted** (P2, module M15; gates on D-AUTH-1).
  No fake 200 (API-12).
- **Request schema:** none (path only). Naturally idempotent read.
- **Response schema:** `200 OK` — bare `Subscription` (no envelope, single
  resource — §8.1 bare rule; `API_INVENTORY.md:1071`):

```
{ "planCode": "premium",        // stable code, M3 knowledge catalog (PR-3)
  "status": "active",            // vocabulary pending (open decision §8)
  "startedAt": "2026-08-01T10:00:00Z",
  "renewsAt":   "2026-09-01T10:00:00Z" }   // null for non-recurring
```

- **Validation:** none (read; path has no variables).
- **Authorization:** **auth** (Bearer → `user_id` once D-AUTH-1); **owner**
  (OW-1) — always the caller's own row.
- **Errors:** `200`; `401 AUTHENTICATION_ERROR`; `404 NOT_FOUND` (**no
  subscription** — the user has never subscribed; and 404-not-403 for foreign
  rows, API-10); `429 RATE_LIMITED`.
- **Security considerations:** exposes entitlement state only — no payment
  details, no `external_ref` on the wire unless accepted (default: **omitted**);
  never logs the row.
- **Side effects:** none (read).
- **Domain entities:** E10 `Subscription` (R10, 0..1 per user); derived
  `CapabilityAvailability` (R45) is *not* returned — client derives.
- **Priority:** P2.

### 5.2 A-2 — Start subscription (`SubscribeToPlan`, UC-33, endpoint 46)

- **Method / path:** `POST /v1/subscriptions`
- **Status:** **inventoried, NOT mounted** (P2, module M15; gates on D-AUTH-1).
  No fake 200 (API-12).
- **Request schema** (`SubscribeRequest { planCode }`):

```
{ "planCode": "premium" }   // required; validated against M3 knowledge catalog
```

  **Header:** `Idempotency-Key` **required** (API-35).
- **Response schema:** `200` (existing subscription updated) / `201 Created`
  (new subscription) — bare `Subscription` (same DTO as A-1).
- **Behavior:** **initiation only** — the use case validates the plan, records/
  updates the `subscriptions` state row, then **calls the external payment/
  entitlement provider after commit** (TRX-1…8; UC-33: "payment call runs after
  commit; the entitlement row UPDATE is single-row tier 1"). The provider
  callback (webhook, §4.3.4) **completes** the purchase and confirms the
  entitlement. **No payment provider is integrated by this task.**
- **Validation:** `planCode` required + exists in the M3 knowledge catalog →
  `422 VALIDATION_ERROR` (unknown/malformed code); payload shape → `422`.
- **Authorization:** **auth**; **owner** (OW-1).
- **Errors:** `200/201`; `401`; `402/424 EXTERNAL_SERVICE_FAILURE` (**payment
  outcome** — e.g. card declined); `404 NOT_FOUND` (plan no longer available);
  `409 CONFLICT` (Idempotency-Key replay with conflicting payload);
  `503 EXTERNAL_SERVICE_FAILURE` (store/provider unreachable); `429`.
- **Security considerations:** **payment details never stored** (R51); no card/
  provider data in bodies or logs (ER-0); `external_ref` stored server-side,
  never on the wire by default; `Idempotency-Key` hashed, never logged raw.
- **Side effects:** upsert one `subscriptions` row (tier 1); external provider
  call **after commit**; webhook updates status/`renews_at`/`external_ref`.
  Feature availability changes are **derived** from the new `planCode` (R45) —
  no entitlement rows written.
- **Domain entities:** E10 `Subscription`; `SubscriptionPlan` (config, R44);
  external entitlement/payment service (R51).
- **Priority:** P2.

---

## 6. Validation reference

- **CURRENT (verified against the real repo):** `backend/app/` has **no**
  subscription route, DTO, or repository — only `GET /health` +
  `POST /v1/assistant/chat` (`main.py`); `schemas.py` holds no `Subscription`
  type. Flutter: `SubscriptionScreen` renders `ProfileMockData.plans`
  (`subscription_screen.dart:13`), all CTAs are `onPressed: () {}`
  (`:197`), route `profileSubscription` → `/profile/subscription`
  (`app_router.dart:402-404`), pushed from `profile_screen.dart:128-129`;
  `SubscriptionPlan` has no id/code (`profile_mocks.dart:31-45`);
  `allCapabilities` flags are copy (`onboarding_data.dart:79-119`).
- **TARGET A-1/A-2 trace 1:1 to accepted inventory** — A-1→45, A-2→46/UC-33;
  paths/methods/auth/errors identical to `API_CONTRACT_RULES.md` §12.14 and
  `API_INVENTORY.md` §5.15 (lines 158-159, 1058-1097); **no invented
  endpoints** (API-2/API-12).
- **Idempotency verified** — `POST /v1/subscriptions` requires
  `Idempotency-Key` (`API_CONTRACT_RULES.md:377`); the read is naturally
  idempotent.
- **Entitlement is derived (R45/PR-2)** — no stored entitlement column, no
  entitlement endpoint; `CapabilityAvailability` recomputed from config × the
  `subscriptions` row (`TABLE_DEFINITIONS.md:485-488`); per-user rows deferred
  to P3 (G11, `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.5).
- **Payment/billing external (R51)** — webhook server-to-server, idempotent,
  never in a DB transaction; payment details never stored (`API_CONTRACT_RULES.md`
  §12.14; UC-33 §5.12); **no provider integrated by this task**.
- **No-internals (C-7/ER-0)** — DTO-only responses, stable `planCode` codes
  (PR-3), `details` allow-list; no table/column names, no payment data.
- **Erasure consistency** — `DELETE /v1/users/me` → 409 cancel-first (R51,
  `AUTH_API.md:388`); erasure cascades external cancellation (TRX-8).

---

## 7. Error reference

Frozen 12-category taxonomy (`ERROR_HANDLING.md` §5); one body
`{ error: { code, message, details? } }` (A3.3). Subscription-relevant rows:

| `code` | HTTP | Applies to | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | A-2 (`planCode` shape/knowledge) | `details.field` / `details.allowed`; never echoes user text |
| `AUTHENTICATION_ERROR` | 401 | A-1/A-2 (once D-AUTH-1) | `WWW-Authenticate`; no token in logs |
| `NOT_FOUND` | 404 | A-1 (no subscription), A-2 (plan gone) | **404-not-403** (API-10); no existence leak |
| `CONFLICT` | 409 | A-2 (Idempotency-Key replay, conflicting payload); erasure with active subscription (`AUTH_API.md:388`) | cancel-first is external (R51) |
| `EXTERNAL_SERVICE_FAILURE` | **402/424** | A-2 — **payment outcome** | `details.source` internal-only (ER-0); no payment details |
| `EXTERNAL_SERVICE_FAILURE` | **503** | A-2 — store/provider unreachable | "temporarily unavailable, try again later" |
| `RATE_LIMITED` | 429 | A-1/A-2 | `Retry-After` in `details` |

CURRENT today: **no subscription endpoints exist** — no errors, no fake 200.

---

## 8. Open decisions

1. **Auth provider (D-AUTH-1)** — gates mounting A-1/A-2; the surface stays
   anonymous until then (F-5, API-12).
2. **`subscriptions.status` vocabulary** — explicitly **open**; set only with
   the billing integration (`TABLE_DEFINITIONS.md:499`, §16). Not invented here.
3. **`subscription_plans` knowledge table + plan codes (M3)** — the catalog
   (codes, `price_display`, `features jsonb`) is finalized at M3; A-2 validation
   and the `SubscriptionScreen` data source depend on it (L2/L6).
4. **Payment provider choice (R51 seam)** — the external billing/entitlement
   service is undecided; the webhook contract (§4.3.4) is provider-agnostic.
   **No provider integrated by this task.**
5. **Client-facing cancel UX** — external provider redirect vs in-product;
   an accepted decision is required before any cancel endpoint (currently **NOT
   defined**, §4.4.2).
6. **Capability gating (G11, P3)** — when a real capability/unlock system lands,
   entitlement becomes per-user derived state; today it is static config
   (R46) with no gating (L4).
7. **`external_ref` on the wire** — default **omitted** (server-internal,
   R51); accepted only if a client use case requires it.
8. **Unchanged project-wide opens** — knowledge shape (K9.1), media privacy
   (MS10.3), feedback design (PR-12), User fields, Today'sLookRecord (P1),
   RecommendationHistory (P3).

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/SUBSCRIPTION_API.md` — a review
of the **CURRENT** subscription surface (a Flutter stub with `ProfileMockData.plans`
and **no backend endpoint** — verified against the repo) and the **TARGET**
production subscription & feature-entitlement contract: A-1 `GET
/v1/subscriptions/me` (endpoint 45) and A-2 `POST /v1/subscriptions` (endpoint
46, UC-33) preserved verbatim, plus the honest disposition of every candidate
operation — list plans (knowledge content, M3), cancel (external R51), restore
(rides UC-9 + A-1), feature entitlements (derived R45, P3), feature usage (the
existing `LearningSignal` trace). **No implementation; no payment provider; no
billing.**

**Skills used:** repository analysis (no subscription backend code in
`backend/app/`; `subscription_screen.dart`, `profile_mocks.dart`,
`profile_screen.dart`, `app_router.dart`, `onboarding_data.dart`) + design-doc
synthesis (ACCOUNT_ASSISTANT_DOMAIN_MODEL §3.3–3.6, DOMAIN_RELATIONSHIPS
R10/R44–R46/R51, AI_DOMAIN_MODEL R-A20, TABLE_DEFINITIONS `subscriptions` +
`subscription_plans`, UC-33/UC-9, OW-1, ERROR_HANDLING §5.10,
API_CONTRACT_RULES §12.14/§11/§9, API_INVENTORY 45/46, AUTH_API 409 cancel-first,
FASTAPI_ARCHITECTURE M15) — documentation only.

**Files changed:** `docs/api/SUBSCRIPTION_API.md` (new).

**Validation run:**
- **CURRENT is a verified snapshot, not a proposal** — every claim traced to
  `backend/app/` (no subscription code), `subscription_screen.dart:13,197,218`,
  `profile_mocks.dart:31-45,160-199`, `profile_screen.dart:128-129`,
  `app_router.dart:402-404`, `onboarding_data.dart:79-119`.
- **TARGET operations trace 1:1 to accepted inventory** — A-1→45, A-2→46/UC-33
  (paths/methods/auth/UC/errors identical to §12.14 and §5.15); the remaining
  candidates are **external / existing-contract / knowledge / derived** — none
  invented as mounted endpoints (API-2/API-12).
- **Derived-entitlement rule honored (R45/PR-2)** — no entitlement column,
  no entitlement endpoint, no per-user rows until P3 (G11).
- **External-payment rule honored (R51)** — no provider integrated, webhook
  server-to-server/idempotent/never-in-transaction, payment details never stored.
- **`git status --short`:** `docs/api/` holds API_CONTRACT_RULES.md +
  API_INVENTORY.md + AUTH_API.md + PROFILE_ONBOARDING_API.md + APPEARANCE_API.md
  + SCAN_API.md + HAIRSTYLE_RECOMMENDATION_API.md + RECOMMENDATION_API.md +
  WARDROBE_API.md + DAILY_OUTFIT_EVENTS_API.md + FEEDBACK_LEARNING_API.md +
  ASSISTANT_API.md + **SUBSCRIPTION_API.md** (untracked) + CURRENT_STATE.md; no
  code, directories, or files created.

**Remaining:** STEP 6 design continues. A-1/A-2 are **not mounted** until
D-AUTH-1 / M15 (API-12); no fake 200 before then. `subscriptions.status`
vocabulary and the plan catalog wait on the billing integration and M3
respectively (open decisions §8). The next STEP 6 contract candidates include
any remaining feature modules and the media/outfits surface.
