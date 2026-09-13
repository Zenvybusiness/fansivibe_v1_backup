# Fansivibe — API Security Review

> **STEP 6 — API CONTRACT DESIGN.** Reviews **every proposed Fansivibe API**
> against a fixed security checklist: authentication, authorization, user
> ownership, input validation, file validation, rate-limiting requirements,
> sensitive-data exposure, ID-enumeration risk, mass-assignment risk,
> excessive-response data, and AI prompt/data leakage — with special focus on
> the seven privacy-sensitive assets (user photos, face data, grooming data,
> wardrobe, events, assistant conversations, subscription data).
>
> **Status: review only. No fixes implemented.** This document verifies the
> accepted contracts (the 48-endpoint inventory in `API_INVENTORY.md`, the
> rules in `API_CONTRACT_RULES.md`, the module contracts) against those
> dimensions, records what already holds, and registers the residual gaps as
> a **findings register** (§8) with recommended controls to land at
> implementation milestones. It **does not** mount an endpoint, change a wire
> shape, add a header, or write code. It deliberately **does not invent**
> protections the contracts do not contain, and it separates "the design
> already covers this" from "the design leaves this open."
>
> **Source of truth:** the accepted security/API docs — `AUTH_AUTHORIZATION_ARCHITECTURE.md`
> (Bearer, OW-1, 404-not-403, admin/system scope), `ERROR_HANDLING.md` and
> `API_ERROR_CONTRACT.md` (ER-0/1/2/3, the 12-category taxonomy, leak
> prevention), `MEDIA_UPLOAD_ARCHITECTURE.md` and `API_LAYER_ARCHITECTURE.md`
> (API-36…39 file uploads), `SECURITY_PRIVACY_DESIGN.md` (per-category
> sensitivity/ownership/erasure), `AI_INTEGRATION_ARCHITECTURE.md` +
> `AI_DATA_FLOW.md` (AI internals never on the wire), the module contracts
> (SCAN, APPEARANCE, HAIRSTYLE, ASSISTANT, AUTH, PROFILE, WARDROBE,
> DAILY_OUTFIT_EVENTS, RECOMMENDATION, FEEDBACK_LEARNING, SUBSCRIPTION),
> `PAGINATION_FILTERING.md`, and the live repo (`backend/app/main.py` — only
> `GET /health` + `POST /v1/assistant/chat` exist).

---

## 1. Purpose, scope, and method

This document answers: **do the proposed APIs satisfy the required security
controls, and where do they not?** It reviews every endpoint in the accepted
inventory (48 + additive/gated + non-client-facing), each against the eleven
checklist dimensions and the seven protected data categories.

### 1.1 The review method

1. **Inventory.** Take the 48 endpoints from `API_INVENTORY.md` §4 (verified
   1:1 against `API_CONTRACT_RULES.md` §12 and the module contracts).
2. **Dimension check.** For each endpoint, record its auth requirement,
   ownership guard, input validation, media handling, rate limiting, and the
   data it returns (matrix, §7).
3. **Cross-doc verification.** Every control claim is traced to the accepted
   architecture/API docs by `file:line`; nothing is asserted from memory.
4. **Gap register.** Only genuine residual risks become findings (§8), each
   with the recommended control and the milestone where it lands. Fixes are
   **not** implemented here.
5. **Current-vs-target honesty.** Where the *current* system differs from the
   contract (the live assistant endpoint), the difference is called out
   explicitly and the contract's target is what is reviewed.

### 1.2 Scope boundaries

- **In scope:** the public HTTP contract surface (all `/v1` endpoints +
  `/health`), the additive/gated endpoints defined in the module contracts
  (assistant conversation family, single-item reads), and the non-client-facing
  paths that touch the same data (subscription webhook, admin knowledge seed,
  account erasure).
- **Out of scope (referenced, not re-designed):** the concrete auth provider
  (D-AUTH-1), the media privacy policy (MS10.3, seals M16), conversation
  retention (G6/G7), payment provider choice (R51), the AI providers
  themselves (`AI_INTEGRATION_ARCHITECTURE.md`), and database-layer security
  (`SECURITY_PRIVACY_DESIGN.md`). Each is a *gate* the contract already
  depends on; this review verifies the contract holds under them and flags
  where a gate must be decided before mounting.

### 1.3 Grounding facts (re-verified)

- **Only two endpoints are live:** `GET /health` and `POST /v1/assistant/chat`
  (`backend/app/main.py:18,23`) — the latter **unauthenticated** today
  (`ASSISTANT_API.md:199`, `AUTH_AUTHORIZATION_ARCHITECTURE.md:216-218`).
- **Everything else is contract design, unmounted.** Gated/sealed modules are
  **not** mounted and return no fake 200 (API-12): auth-dependent endpoints
  until D-AUTH-1, media (M16) until MS10.3, feedback (M11) until the UI is
  accepted, conversations until retention (G6/G7).
- **The security architecture is already accepted and consistent:**
  - Bearer auth via `api/deps.py → user_id`, never client-supplied identity
    (`API_LAYER_ARCHITECTURE.md` API-9; `API_CONTRACT_RULES.md` C-9/C-15).
  - Owner-only ownership with **404-not-403** everywhere (OW-1, API-10).
  - One frozen 12-category error taxonomy; `details` is allow-list-only;
    stack/SQL/provider/prompt/token/user-content never on the wire
    (ER-0/ER-1/ER-2/ER-3; `API_CONTRACT_RULES.md` §14).
  - CRITICAL-sensitivity for appearance/image data; private-by-default media;
    complete erasure (CASCADE + blob cleanup + external cancel)
    (`SECURITY_PRIVACY_DESIGN.md` §3/§5).
- **The review finds the design strong by construction**, with a small
  residual-gap set: unquantified rate limits (§5.5), current-state assistant
  exposure (F-1), media deep-inspection (F-3), snapshot provenance (F-4),
  login enumeration control (F-5), AI data-minimization (F-6), and three
  accepted idempotency trade-offs (F-7/F-8). None requires a contract change.

---

## 2. Source of truth and inputs

| Concern | Source |
| --- | --- |
| Endpoint inventory (48) | `API_INVENTORY.md` §4 (lines 114–161); `API_CONTRACT_RULES.md` §12 |
| Authentication / Bearer / deps.py | `API_LAYER_ARCHITECTURE.md` §5 (API-5/6); `API_CONTRACT_RULES.md` §5 (C-9/C-15); `AUTH_API.md` |
| Authorization / OW-1 / 404-not-403 / admin | `AUTH_AUTHORIZATION_ARCHITECTURE.md` §4–§5; `API_CONTRACT_RULES.md` C-9; `API_RESPONSE_CONVENTIONS.md` §5 |
| Input validation (422, vocab, DTO) | `API_CONTRACT_RULES.md` C-6 (API-13…16), §10; `API_ERROR_CONTRACT.md` §5.1/§6 |
| File/media validation | `MEDIA_UPLOAD_ARCHITECTURE.md` §4.1–4.10; `API_LAYER_ARCHITECTURE.md` §14 (API-36…39); `SCAN_API.md` §5.4 |
| Rate limiting | `API_LAYER_ARCHITECTURE.md` §12 (`429`); `API_ERROR_CONTRACT.md` §5.6; module contracts' error tables |
| Sensitive-data exposure / never-expose | `ERROR_HANDLING.md` §6 (ER-0…3); `API_CONTRACT_RULES.md` §14; `SECURITY_PRIVACY_DESIGN.md` §3/§6 |
| Protected-data categories | `SECURITY_PRIVACY_DESIGN.md` §3–§4; `DATA_OWNERSHIP.md` |
| ID enumeration / identifiers | `API_CONTRACT_RULES.md` C-13 (PR-3); `API_RESPONSE_CONVENTIONS.md` §8 |
| Mass assignment / server-owned fields | `API_CONTRACT_RULES.md` C-9/C-13; `PROFILE_ONBOARDING_API.md` §5.2/§5.4; module DTO sketches |
| Excessive response data / summaries | `PAGINATION_FILTERING.md` §8/§9; `API_RESPONSE_CONVENTIONS.md` §6 |
| AI prompt/data leakage | `AI_INTEGRATION_ARCHITECTURE.md` §5–§8; `AI_DATA_FLOW.md`; `API_CONTRACT_RULES.md` C-8; `HAIRSTYLE_RECOMMENDATION_API.md` §4.8 |
| Live surface | `backend/app/main.py` (health + chat only) |

---

## 3. Executive summary

### 3.1 Posture by dimension

| # | Dimension | Posture | Headline result |
| --- | --- | --- | --- |
| 1 | Authentication | **Sound design**; one current-state gap | Bearer everywhere in contract; live assistant endpoint is public today (F-1). |
| 2 | Authorization & ownership | **Verified strong** | OW-1 + 404-not-403 on every user-owned endpoint; admin/system closed by default. |
| 3 | Input validation | **Sound design**; one current-state gap | Typed DTOs + vocab → 422; assistant input unbounded today, capped in target (F-1). |
| 4 | File/media validation | **Designed**; two gaps to close at M16 | Two-phase, MIME allow-list, size, HEAD-verified; no dimension bounds / deep inspection (F-3). |
| 5 | Rate limiting | **Gap — category only** | `429 RATE_LIMITED` + `Retry-After` everywhere; **no quantified thresholds** anywhere (F-2). |
| 6 | Sensitive data exposure | **Verified strong** | ER-0/1/2/3; CRITICAL data owner-only, bytes never logged/echoed; no provider/prompt/token leakage. |
| 7 | ID enumeration | **Verified strong** | UUID identifiers; uniform 404-not-403; login prefers uniform 401 (F-5 as implementation note). |
| 8 | Mass assignment | **Verified strong**; one data-integrity note | Tight DTOs; user_id/timestamps/run_type/status/flags server-owned; save-snapshot provenance note (F-4). |
| 9 | Excessive response data | **Verified strong** | Summary lists, no message previews, no run `result` in history, bounded `top`/`alternatives`. |
| 10 | AI prompt/data leakage | **Verified strong** | No provider/model/prompt/raw-output on the wire; degraded boolean only; `reason` never in prompts (F-6 as minimization note). |

### 3.2 Headline findings (see §8 for the full register)

- **F-1 (HIGH, current-state only):** `POST /v1/assistant/chat` is public,
  client-trusted context, and unbounded today. The target resolves all three
  (additive auth, server-wins context R47, input caps) — but they must land
  before the endpoint becomes the product surface.
- **F-2 (HIGH):** rate limiting is specified as a category with `Retry-After`
  but **no thresholds** exist for any endpoint — public chat, auth, analysis,
  and generation are all unmetered in the contract.
- **F-3 (MEDIUM):** media validation covers MIME + size (declared + verified)
  but **no dimension bounds and no deep content inspection** are specified.
- **F-4 (MEDIUM):** the save-snapshot flow (`POST /v1/looks/saved`,
  `/v1/outfits/saved`, `/v1/looks/today/save`) structurally validates the
  client-supplied `snapshot` but does **not** provenance-verify it against the
  producing run — a user can persist self-authored "AI recommendation"
  content as their history.
- **F-5 (MEDIUM):** login account enumeration — uniform `401` required; the
  inherited `404` branch must be avoided at implementation.
- **F-6 (MEDIUM):** AI **data minimization** is not quantified — what exact
  context/image data is transmitted to providers is an implementation
  decision; the contract only guarantees the response never leaks internals.

### 3.3 What was verified as already holding (no finding)

Ownership (OW-1/404-not-403), UUID identifiers, typed/vocab validation,
ER-0/1 leak prevention, token hygiene (never stored/logged), MediaRef-only +
private-by-default media + owner-scoped signed URLs, AI-internals-never-on-wire
(C-8), summary-only lists, complete erasure, gating discipline (no fake 200),
and idempotency on every double-write-prone save. Detailed in §6 and §9.

---

## 4. Protected assets and threat model

The seven categories the task flags, their sensitivity, where they live on the
surface, and the endpoints that touch them (sensitivity per
`SECURITY_PRIVACY_DESIGN.md` §3/§4):

| Protected asset | Sensitivity | Surface (endpoints) | Primary risks the design must prevent |
| --- | --- | --- | --- |
| User photos (scan images, wardrobe item images, generated images) | CRITICAL | 36/37 (analysis submits), 47/48 (media, sealed), 12/13 (wardrobe `imageRef`) | cross-user byte access, public exposure, leakage into logs/responses/errors, erasure failure |
| Face data | CRITICAL | 37 (hairstyle analysis), profile `styleProfile` (7/10), assistant `UserContext.face` (16), run results (39) | biometric-adjacent exposure, client-authored "truth", leakage to logs/LLM, retention |
| Grooming data | CRITICAL (attributes) / LOW (options) | 38 (grooming analysis), profile, run results | same as face; free-text injection surface |
| Wardrobe | MEDIUM (metadata) / CRITICAL (images) | 11–15 | cross-user item access, image attachment forgery, delete leaving bytes |
| Events | MEDIUM | 26–30 | cross-user access, notes/location (personal context) exposure, delete integrity |
| Assistant conversations | CRITICAL | 16 (chat, public today), 17 (feedback), A-3/4/5 (gated) | message content leakage, retention, prompt injection, cross-user conversation access |
| Subscription data | HIGH | 45/46 + server-to-server webhook | payment-detail exposure, entitlement forgery, cross-user read, erasure of external state |

Threat-model statement: the dominant threat is **cross-user data access and
data leakage**, followed by **abuse of unmetered public/AI surfaces**, and then
**data-integrity/forgery of derived content**. The contracts neutralize the
first with OW-1 + 404-not-403 + ER-0; the second is the largest residual gap
(F-2); the third is partially open (F-4).

---

## 5. Review by dimension

### 5.1 Authentication

**Contract requirement.** Every protected endpoint takes
`Authorization: Bearer <token>`; `api/deps.py` resolves it to a `user_id`
(UUID); missing/invalid/expired/revoked → `401 AUTHENTICATION_ERROR` +
`WWW-Authenticate: Bearer` (`API_LAYER_ARCHITECTURE.md` API-5/6;
`API_CONTRACT_RULES.md` §5; `AUTH_API.md:132-134`). Tokens are issued only by
`POST /v1/auth/*`, revoked by logout; the backend **never stores passwords or
refresh secrets** and never logs tokens (`AUTH_API.md:66-68,143-148,329-330`;
`API_CONTRACT_RULES.md:407-408,679-680`). Provider tokens are exchanged and
discarded, never stored/echoed (`AUTH_API.md:265-268`). Identity for domain
logic is `user_id` only (F-3).

**Verification result — sound design, one current-state gap.**

- **Verified:** all 44 user endpoints in the inventory are `auth` (`API_INVENTORY.md`
  matrix `INV:1154-1158`); the only public endpoints are auth-entry
  (02–04), knowledge (18–22), health (01), and assistant chat (16, public
  today) (`API_CONTRACT_RULES.md:170-176`). No endpoint trusts a client-supplied
  `user_id` (C-9/C-15). Register requires `Idempotency-Key` to prevent
  duplicate accounts (`AUTH_API.md:135-136`). No anonymous *write* endpoint
  exists — anonymous local data only reaches the backend through `POST
  /v1/users/me/sync` after account creation (API-8; `API_CONTRACT_RULES.md:177-179`).
- **Gap F-1:** the live `POST /v1/assistant/chat` is unauthenticated and stays
  so until D-AUTH-1 (`ASSISTANT_API.md:199,393-399`). It carries client-sent
  appearance context today (`ASSISTANT_API.md:239`). Target: additive Bearer
  auth, server-derived context, no breaking change to the frozen wire
  (F-13).
- **Residual note:** `Idempotency-Key` is a header, hashed server-side, never
  logged raw (`API_CONTRACT_RULES.md:381-386`).

### 5.2 Authorization & user ownership

**Contract requirement.** Invariant **OW-1**: every user-owned resource is
created/read/updated/deleted strictly under the authenticated `user_id` — set
from the principal at insert, filtered at every query, guarded at every write,
inherited by children (`AUTH_AUTHORIZATION_ARCHITECTURE.md` §4.5–4.6;
`API_CONTRACT_RULES.md` C-9). A foreign or non-existent resource id →
`404 NOT_FOUND`, **never 403** (API-10, "no existence leak"); `403` is
reserved for authenticated-but-disallowed admin paths
(`API_RESPONSE_CONVENTIONS.md:146-148`; `API_ERROR_CONTRACT.md:80-82`). Admin
and system access are separate, narrow, audited scopes — default closed
(`AUTH_AUTHORIZATION_ARCHITECTURE.md` §4.7).

**Verification result — verified strong, no exception found.**

- Every user-owned endpoint is owner-scoped in its contract: wardrobe
  (`WARDROBE_API.md:304-308`), analysis runs (`SCAN_API.md:338-340,617-624`),
  saved looks (`HAIRSTYLE_RECOMMENDATION_API.md:380-382`), events
  (`DAILY_OUTFIT_EVENTS_API.md:345-350`), subscriptions
  (`SUBSCRIPTION_API.md:307-310`), assistant conversations
  (`ASSISTANT_API.md:400-402`), feedback targets (`FEEDBACK_LEARNING_API.md:358-364`),
  profile (`PROFILE_ONBOARDING_API.md:270-275`).
- Media ownership is enforced at the object-key namespace
  (`users/{user_id}/...`), so even a valid signed URL cannot cross users
  (`MEDIA_UPLOAD_ARCHITECTURE.md` §4.5; `SCAN_API.md:316-317`). Child/parent
  chains (run → media → result) inherit the parent's owner check
  (`AUTH_AUTHORIZATION_ARCHITECTURE.md` §4.6).
- Admin (knowledge seed, M5 P2) and system (subscription webhook, erasure)
  paths are separate principals, never reachable from a user token
  (`API_CONTRACT_RULES.md:184-186`; `SUBSCRIPTION_API.md:348-358`).
- No user-accessible admin path exists in the inventory.

### 5.3 Input validation

**Contract requirement.** Every body/query is a typed Pydantic DTO; controlled
vocabularies are validated server-side → `422 VALIDATION_ERROR` with
`details.field_errors [{field,error,allowed?}]`; not-found vs invalid is
distinguished (404 vs 422); no free-form `?filter=json` (API-13…16,
API-23…27; `API_CONTRACT_RULES.md` C-6, §10; `API_ERROR_CONTRACT.md` §5.1/§6).

**Verification result — sound design, one current-state gap.**

- **Verified:** vocab-validated category/color/material/eventType/occasion/
  style/run_type (`WARDROBE_API.md:76-80,259-260`; `DAILY_OUTFIT_EVENTS_API.md:264-266`;
  `SCAN_API.md:522-523`); dates not-in-past (`DAILY_OUTFIT_EVENTS_API.md:267-270`);
  email normalized + bounded, password policy 8–128, displayName 1–100
  (`AUTH_API.md:210-216`); `page_size ∈ [1,100]`, unknown sort key → 422
  (`PAGINATION_FILTERING.md:168-169,243`); `run_id`/`item_id`/`event_id` must
  be valid UUIDs → 422 on malformed (`SCAN_API.md:620`); sync blob size guard
  → 413 (`PROFILE_ONBOARDING_API.md:485-486`); feedback `reason` bounded;
  `rating` a controlled vocabulary pending the design (PR-12)
  (`FEEDBACK_LEARNING_API.md:307-310,320-322`).
- **Gap F-1 (input half):** today `POST /v1/assistant/chat` accepts unbounded
  `messages`/`content`, free-string roles, no turn cap, no content-safety
  check (`ASSISTANT_API.md:238,339`). Target caps: role allow-list, `content`
  ≤ ~2000 chars, ≤ ~50 turns → 422 (`ASSISTANT_API.md:565-570`).
- **Note:** validation is server-side only; Flutter never enforces security
  (`SCAN_API.md:756-757`; `AUTH_API.md:418-420`).

### 5.4 File & media validation

**Contract requirement.** Multipart `image` part (never base64), upload-then-
insert (TRX-1), validation **before** upload (type/size/dimension → 413/422,
API-38), private by default (API-39); M16 two-phase: declared metadata at
`POST /media/uploads` (purpose allow-list, size, MIME allow-list) and
verification at `/complete` via object-storage HEAD (size, content-type,
checksum) — bytes never buffer through FastAPI RAM (PR-8)
(`API_LAYER_ARCHITECTURE.md` §14; `MEDIA_UPLOAD_ARCHITECTURE.md` §4.1–4.4;
`SCAN_API.md:553-571`).

**Verification result — designed; two gaps to close at M16.**

- **Verified:** MIME allow-list `image/jpeg|png|webp` (+ `heic` if supported);
  per-purpose size limits (config-driven, e.g. 15–20 MB vision input); MIME/
  size **checked twice** (declared + HEAD-verified); rejected blobs marked for
  orphan sweep; signed PUT URLs are short-lived, single-key, owner-scoped;
  download URLs minted per-request, never persisted
  (`MEDIA_UPLOAD_ARCHITECTURE.md` §4.2/4.4/4.8; `SCAN_API.md:566-571`).
- **Gap F-3:** no **dimension** bounds (pixel limits) and no **deep content
  inspection** (re-encoding, malware/phishing scan, or NSFW screening) are
  specified anywhere. API-38 mentions "dimension limits" but the media and
  scan contracts only implement MIME + size. Both can be closed inside the
  sealed M16/processing job without a wire change (`MEDIA_UPLOAD_ARCHITECTURE.md`
  §4.2: "AI/malware inspection (if required) runs in the async processing
  job").
- **Note:** M16 is sealed until MS10.3; the inline `image` part on analysis
  submits (36/37) currently carries only the pre-run content-type/size check
  (`SCAN_API.md:379-380,450-451`).

### 5.5 Rate limiting

**Contract requirement.** The taxonomy reserves `429 RATE_LIMITED` + 
`Retry-After` for register/login/feedback throttling
(`API_LAYER_ARCHITECTURE.md:237`; `ERROR_HANDLING.md` §5.6;
`API_ERROR_CONTRACT.md` §5.6). The task asks to **verify rate-limiting
requirements** — i.e. not just the category but the requirement per surface.

**Verification result — gap (F-2, HIGH).**

- Every module error table lists `429 RATE_LIMITED` on "any endpoint" +
  `Retry-After` (e.g. `WARDROBE_API.md:590`, `DAILY_OUTFIT_EVENTS_API.md:596`,
  `RECOMMENDATION_API.md:498`, `FEEDBACK_LEARNING_API.md:582`,
  `SCAN_API.md:771`, `AUTH_API.md:432`), and `ASSISTANT_API.md:442-443` flags
  the **public chat endpoint as a prime 429 candidate**.
- **But no contract states a threshold** (requests/minute, per-IP vs per-user
  vs per-account, per-endpoint or per-plan quotas). `AUTH_API.md:223-226,306-307`
  specify the *dimensions* (per IP **and** per email/account) but not numbers.
- **Recommended control (lands at M1 rate-limit infra, not here):** quantified
  limits at least for (a) public auth endpoints per IP + per email/account,
  (b) public assistant chat per IP + per user once auth lands, (c) AI/analysis
  and generation endpoints per user (cost control), (d) feedback. All with
  `Retry-After`; `X-Request-Id` is explicitly **not** a rate-limit key
  (`API_RESPONSE_CONVENTIONS.md:444-445`).

### 5.6 Sensitive data exposure

**Contract requirement.** `details` is allow-list-only (ER-1); never SQL,
stack traces, table/column names, provider/model names, prompts, tokens,
credentials, session ids, or **user content** (image bytes, face data,
wardrobe snapshots, messages) on the wire or in logs (ER-0/ER-4)
(`ERROR_HANDLING.md` §6; `API_CONTRACT_RULES.md` §14; `API_ERROR_CONTRACT.md` §9).
CRITICAL appearance/image data: owner-only, never cached on shared storage,
bytes never logged or echoed — only `MediaRef` travels (MS10.3).

**Verification result — verified strong.**

- Face/scan media: "image bytes never logged and never echoed in responses or
  errors — only the `MediaRef` travels" (`SCAN_API.md:341-344`;
  `APPEARANCE_API.md:339-342`). Error bodies across all modules repeat the
  no-echo list verbatim (`SCAN_API.md:326-329`; `HAIRSTYLE_RECOMMENDATION_API.md:369-371`;
  `RECOMMENDATION_API.md:423-429`).
- Analysis-derived attributes are **never client-authored truth** — they reach
  the profile only via `sourceRunId` pinning to an owned, completed run
  (`APPEARANCE_API.md:405-407,565-571`; `PROFILE_ONBOARDING_API.md:352-354`).
- Conversations: list rows expose `messageCount` only, **no message preview**
  (`ASSISTANT_API.md:633-636`); transcripts are owner-only, never logged
  (`ASSISTANT_API.md:663`).
- Learning summary exposes typed signal labels, **never raw feedback text**
  (`FEEDBACK_LEARNING_API.md:313-317,476-479`); feedback `reason` is stored but
  never surfaced via summary/other reads (`FEEDBACK_LEARNING_API.md:604-606`).
- Subscription DTO exposes `planCode/status/startedAt/renewsAt` only — no
  payment details, `external_ref` omitted by default
  (`SUBSCRIPTION_API.md:453-456`).
- Logging policy: auth tokens, context snapshots, image bytes, conversation
  text, and user payloads are never logged; only metadata-level access events
  for CRITICAL appearance data and entitlement changes
  (`SECURITY_PRIVACY_DESIGN.md` §6.2; `ERROR_HANDLING.md` §7).

### 5.7 ID enumeration risk

**Contract requirement.** User-owned identifiers are server-generated UUIDs
(unguessable); knowledge items use stable text codes; clients never generate
ids (C-13, PR-3; `API_RESPONSE_CONVENTIONS.md` §8). A syntactically wrong id →
422; a well-formed foreign/non-existent id → 404, never 403 — no existence
oracle (`API_RESPONSE_CONVENTIONS.md:377-378`). Login should be uniform-401
(`AUTH_API.md:302-305`).

**Verification result — verified strong; one implementation note (F-5).**

- **Verified:** all user-owned ids are UUIDs and DB-owned: `run_id`
  (`SCAN_API.md:620`), `item_id` (`WARDROBE_API.md:564`), `event_id`
  (`DAILY_OUTFIT_EVENTS_API.md:569`), `saved_look_id`, `conversation_id`
  (UUID, `ASSISTANT_API.md:658`). Recommendation ids are stable catalog codes
  (public knowledge, not sensitive) (`HAIRSTYLE_RECOMMENDATION_API.md:112-116`).
  Every module's error table includes "404-not-403, no existence leak"
  (e.g. `WARDROBE_API.md:587`, `SCAN_API.md:768`, `FEEDBACK_LEARNING_API.md:580`).
- **F-5:** login currently inherits a `404` branch from UC-3; the contract
  already instructs uniform `401` for both "no such account" and "wrong
  password" — this must be honored at M1 (`AUTH_API.md:302-305`). Social
  sign-in has no 404 path (always 401/409) (`AUTH_API.md:271-272`).
- **Note:** 404 for the caller's *own deleted account* is not an enumeration
  oracle (`AUTH_API.md:368-369`; `PROFILE_ONBOARDING_API.md:293-294`).

### 5.8 Mass assignment risk

**Contract requirement.** Every request is a bounded typed DTO enumerating the
accepted fields; server-owned fields (`user_id`, `id`, `createdAt`,
`updatedAt`, `run_type`, `status`, `engine_version`, `version`, derived
`flags`, `isOwned`) are never client-writable (C-9/C-13;
`API_RESPONSE_CONVENTIONS.md` §8/§11).

**Verification result — verified strong; one data-integrity note (F-4).**

- **Verified:** creation DTOs are minimal — analysis submits accept only
  `image` + typed fields / `options` (Phase 28: no face-profile reference;
  `SCAN_API.md:357-361,415-418,493-501`);
  wardrobe create/patch field lists exclude `id/user_id/createdAt/updatedAt`
  (`WARDROBE_API.md:313-322,435-437`); event create/update exclude id/timestamps,
  and `hasOutfitRecommendation` is explicitly **not stored**
  (`DAILY_OUTFIT_EVENTS_API.md:301-311`); `POST /v1/users/me/sync` carries no
  `user_id`, derived `flags` are **recomputed server-side**, and `styleProfile`
  derived fields require `sourceRunId` (`PROFILE_ONBOARDING_API.md:449-458,481-484`);
  the client **never names a `signal_type`** (M10 sole writer, PR-7)
  (`FEEDBACK_LEARNING_API.md:281-284,565`); subscription accepts only
  `planCode`, status/renewal updated only by the webhook
  (`SUBSCRIPTION_API.md:470,354-356`).
- **F-4 (note):** the save endpoints accept a client-supplied `snapshot` blob
  (`SaveLookRequest.snapshot`) that is **structurally validated** at save time
  (`RECOMMENDATION_API.md:478`; `HAIRSTYLE_RECOMMENDATION_API.md:561,572`) but
  not **provenance-verified** against the producing run. There is no
  cross-user or elevation vector (the snapshot is owner-owned and its
  recommendation ids are catalog codes), but the user can persist fabricated
  "AI recommendation" content as their own history. Recommended control (at
  M7 implementation): when the snapshot claims a `sourceRunId`/producing
  surface, verify the referenced run is owned and its result matches; never
  trust a bare client snapshot as server-verified AI output.

### 5.9 Excessive response data

**Contract requirement.** Lists return summary DTOs where the DTO is heavy;
no run `result` in history rows; no conversation previews; `top`/`alternatives`
are bounded; cursor feed carries no `total`; the only wrapper is the list
envelope (API-18) (`PAGINATION_FILTERING.md` §8; `API_RESPONSE_CONVENTIONS.md` §6).

**Verification result — verified strong.**

- Run-history rows carry **no `result`**; full immutable result only via the
  owned detail read (`SCAN_API.md:711-712`; `APPEARANCE_API.md:538-539`).
- Conversation summaries carry `messageCount` only (`ASSISTANT_API.md:633-636`).
- Saved-look list rows are summaries; full snapshot via detail read (the
  single saved-look read is additive, not in the inventory)
  (`PAGINATION_FILTERING.md:347-349`).
- Wardrobe list returns full `WardrobeItem[]` — acceptable: it is the owner's
  own small-ish data and the detail screen is served from it today
  (W-2 additive) (`WARDROBE_API.md:334-336`).
- Media is never in responses — `MediaRef` only, signed URLs minted per
  request (`API_CONTRACT_RULES.md:154-159`).
- Feed limits are deliberately tighter: cursor `limit` default 20 / max 50
  (`PAGINATION_FILTERING.md:208`).

### 5.10 AI prompt & data leakage

**Contract requirement.** No provider/vendor/model names, prompts, sampling
parameters, token counts, or raw model output on the wire (C-8, F-7, AI-0);
degraded fallback surfaces as a neutral `details.degraded` boolean only;
`CapabilityResult.raw_provider` is internal-only; `engine_version` is the only
provenance exposed; feedback `reason`/user content is **never** injected into
prompts (`API_CONTRACT_RULES.md` C-8/§14; `HAIRSTYLE_RECOMMENDATION_API.md` §4.8;
`AI_INTEGRATION_ARCHITECTURE.md` §8).

**Verification result — verified strong; one minimization note (F-6).**

- **Verified:** the no-internals rule is repeated binding in every
  recommendation/analysis doc and the assistant contract (`RECOMMENDATION_API.md:423-429`;
  `ASSISTANT_API.md:276-277,577-580`). Assistant context is derived per
  request, **never stored** (R47), and the LLM sees only a server-side
  `_context_summary` that "never leaves the server" (`ASSISTANT_API.md:423-425`).
  The AI never navigates — the client executes (G9) (`ASSISTANT_API.md:496`).
  Feedback `reason` is "**never** injected into the engine's internal prompts"
  (`HAIRSTYLE_RECOMMENDATION_API.md:611-613`). Confidence is never computed
  (AI-0); scores are deterministic; reasons are grounded
  (`RECOMMENDATION_API.md:300-320`).
- **F-6 (note):** **data minimization** for what is actually *sent to
  providers* (which image regions, which wardrobe/face fields, how much
  conversation context) is not quantified in the contract — the guarantee is
  on the response/leak side. Recommended control (at the AI-integration
  milestone): a documented per-capability minimization policy (send only what
  the capability needs, redact/scale images, no PII beyond the task), and
  prompt-injection hardening for the assistant (role/content allow-lists,
  output validation) alongside the input caps.

---

## 6. Protected data deep-dives

For each protected category: sensitivity, exposure surface, controls present,
and residual findings.

### 6.1 User photos (scans, wardrobe item images, generated images)

- **Sensitivity:** CRITICAL (`SECURITY_PRIVACY_DESIGN.md` §3.2/§3.3/§4.3).
- **Surface:** analysis submits (36/37, inline `image`), media uploads
  (47/48, sealed until MS10.3), wardrobe item `imageRef` (12/13).
- **Controls present:** bytes never in PostgreSQL or FastAPI RAM (PR-8,
  `MEDIA_UPLOAD_ARCHITECTURE.md` §1); object keys namespaced
  `users/{user_id}/...` (`SCAN_API.md:316-317`); private by default; signed
  URLs short-lived + owner-scoped + single-key, never persisted
  (`MEDIA_UPLOAD_ARCHITECTURE.md` §4.8); MIME allow-list + size checked twice;
  orphan sweep + erasure deletes bytes (`SECURITY_PRIVACY_DESIGN.md` §5.2);
  bytes never logged (`ERROR_HANDLING.md` §5.8).
- **Residual:** F-3 (dimension + deep inspection), sealed until MS10.3.

### 6.2 Face data

- **Sensitivity:** CRITICAL (biometric-adjacent) (`SECURITY_PRIVACY_DESIGN.md` §4.1).
- **Surface:** 37 (hairstyle analysis: image pass or empty-body profile-only pass over `style_profile` by `user_id`, Phase 28), profile
  `styleProfile.faceShape/skinTone/bodyType` (7/10), assistant
  `UserContext.face` (16), run results (39).
- **Controls present:** attributes are analysis-derived, never client-authored
  — `sourceRunId` pins them to an owned completed run
  (`APPEARANCE_API.md:405-407,565-571`); CRITICAL no-echo/no-log
  (`APPEARANCE_API.md:339-342`); `FaceData` travels frozen inside the
  assistant contract and is never changed by this surface
  (`APPEARANCE_API.md:132-135`); erasure cascades all face data
  (`SECURITY_PRIVACY_DESIGN.md` §5).
- **Residual:** F-1 (assistant `UserContext.face` is client-sent today),
  F-6 (minimization to the face-analysis provider).

### 6.3 Grooming data

- **Sensitivity:** CRITICAL attributes / LOW options (`SECURITY_PRIVACY_DESIGN.md` §4.5).
- **Surface:** 38 (grooming analysis, `options` only), profile, run results.
- **Controls present:** options are **vocab codes only — no free text, no
  injection surface** (`SCAN_API.md:528-530`; `APPEARANCE_API.md:470-473`);
  owner-only, 404-not-403; results are regenerable recommendations, never
  stored truth (BAR-0); same no-echo/no-log posture as face.
- **Residual:** none specific (covered by F-6 minimization note).

### 6.4 Wardrobe

- **Sensitivity:** MEDIUM metadata / CRITICAL images (`SECURITY_PRIVACY_DESIGN.md` §4.4).
- **Surface:** 11–15.
- **Controls present:** owner-scoped with 404-not-403 on every item
  (`WARDROBE_API.md:304-308`); vocab-validated category/color/material, no
  free strings (`WARDROBE_API.md:259-260`); `imageRef` ownership checked
  (cannot attach another user's media) (`WARDROBE_API.md:398-406`); insight
  grounded, no fabricated gaps (`WARDROBE_API.md:510-512`); item deletion
  enqueues out-of-DB byte deletion + orphan sweep, history survives by design
  (BC-41) (`WARDROBE_API.md:454-461`).
- **Residual:** F-8 (create not idempotency-keyed — duplicate rows on retry,
  explicitly accepted), F-3 (media inspection via M16).

### 6.5 Events

- **Sensitivity:** MEDIUM (user-authored, can carry personal context)
  (`SECURITY_PRIVACY_DESIGN.md` §4.8).
- **Surface:** 26–30.
- **Controls present:** owner-scoped with 404-not-403
  (`DAILY_OUTFIT_EVENTS_API.md:345-350`); `eventType` vocab-validated;
  `eventDate` not-in-past (`DAILY_OUTFIT_EVENTS_API.md:264-270`); events are
  **not image-bearing** (no media surface) (`DAILY_OUTFIT_EVENTS_API.md:349`);
  notes/location are owner-served, never logged; derived event outfit is
  regenerable, never a stored child (TRX-7) (`DAILY_OUTFIT_EVENTS_API.md:513-520`).
- **Residual:** F-8 (create not keyed, accepted); E-3 single-event GET is
  additive (no leak — the list serves the details screen today).

### 6.6 Assistant conversations

- **Sensitivity:** CRITICAL (can restate appearance data and personal context)
  (`SECURITY_PRIVACY_DESIGN.md` §4.7).
- **Surface:** 16 (chat, public today), 17 (feedback), A-3/4/5 (conversation
  list/transcript/delete — additive, gated on G6/G7, **not mounted**).
- **Controls present:** transient by default — nothing stored server-side
  (`ASSISTANT_API.md:126-136`); R47 context never persisted with a message
  (`ASSISTANT_API.md:423-425`); if retention lands, short window + append-only
  + whole-conversation delete only (`ASSISTANT_API.md:527-534`); list shows
  `messageCount` only, no previews (`ASSISTANT_API.md:633-636`); per-user
  conversation ids, 404-not-403 on foreign ids (`ASSISTANT_API.md:400-402,658`);
  erasure cascades conversations (`ASSISTANT_API.md:532-534`); signals survive
  conversation deletion (BC-41) (`ASSISTANT_API.md:535-538`).
- **Residual:** F-1 (public + client-trusted today), F-7 (feedback not keyed —
  duplicate evidence rows accepted), and the retention gate itself (G6/G7)
  must be decided before A-3/4/5 mount. The additive `X-Conversation-Id` header
  must be owner-validated when supplied (server creates on first use)
  (`ASSISTANT_API.md:522-526`).

### 6.7 Subscription data

- **Sensitivity:** HIGH (entitlement/paid state) (`SECURITY_PRIVACY_DESIGN.md` §4.9).
- **Surface:** 45 (GET `/v1/subscriptions/me`), 46 (POST `/v1/subscriptions`),
  server-to-server billing webhook (non-client-facing).
- **Controls present:** entitlement is **derived**, never stored (R45)
  (`SUBSCRIPTION_API.md:78-82`); **payment details never stored** — the
  backend keeps entitlement state only (R51) (`SUBSCRIPTION_API.md:83-88,489-491`);
  webhook is server-to-server, idempotent, never inside a DB transaction
  (`SUBSCRIPTION_API.md:348-358`); `planCode` vocab-validated → 422
  (`SUBSCRIPTION_API.md:375-377`); `Idempotency-Key` required on POST, hashed,
  never logged raw (`SUBSCRIPTION_API.md:339-341`); owner-only, 404-not-403,
  no existence leak (`SUBSCRIPTION_API.md:307-310`); `external_ref` omitted on
  the wire by default (`SUBSCRIPTION_API.md:453-456`); account erasure is
  **cancel-first** → 409 until the external subscription is cancelled
  (`AUTH_API.md:386-389`; `SUBSCRIPTION_API.md:156-159`).
- **Residual:** F-2 (no quantified 429 thresholds), `subscriptions.status`
  vocabulary open (set only with billing integration).

---

## 7. Per-endpoint security matrix

Verified against `API_INVENTORY.md` §4 (48 endpoints) + additive/gated + non
client-facing. **Auth:** `public` / `auth` (Bearer → user_id). **Owner:** owner-
scoped OW-1 with 404-not-403. **Validate:** typed DTO + vocab → 422; **Media:**
media/file validation where applicable. **Rate:** 429 category present.
**Findings:** reference the §8 register ID, or `—` when verified clean.

### 7.1 The 48-endpoint inventory

| # | Method + path | Auth | Owner | Key security notes | Findings |
| --- | --- | --- | --- | --- | --- |
| 01 | GET `/health` | public | — | versionless, envelope-free, no user data | — |
| 02 | POST `/v1/auth/register` | public | — | Idempotency-Key; rate-limit per IP+email; uniform-401 posture | F-2, F-5 |
| 03 | POST `/v1/auth/social` | public | — | provider allow-list; provider token discarded; no 404 oracle | F-2 |
| 04 | POST `/v1/auth/login` | public | — | rate-limit per IP+account; **uniform 401** for no-account/wrong-password | F-2, F-5 |
| 05 | POST `/v1/auth/logout` | auth | self | revokes own session only; idempotent; token never logged | — |
| 06 | GET `/v1/users/me` | auth | OW-1 | returns own profile incl. CRITICAL styleProfile | — |
| 07 | PATCH `/v1/users/me` | auth | OW-1 | If-Match version guard (409); derived fields require `sourceRunId` | — |
| 08 | PUT `/v1/users/me/preferences` | auth | OW-1 | vocab codes only; unknown key → 422 | — |
| 09 | PUT `/v1/users/me/settings` | auth | OW-1 | controlled keys only | — |
| 10 | POST `/v1/users/me/sync` | auth | OW-1 | full-schema validation + rollback; `flags` recomputed; size 413; Idempotency-Key | — |
| 11 | GET `/v1/wardrobe/items` | auth | OW-1 | owner-scoped list; vocab filters; pagination [1,100] | — |
| 12 | POST `/v1/wardrobe/items` | auth | OW-1 | vocab + `imageRef` ownership check; not keyed → duplicate rows | F-8 |
| 13 | PATCH `/v1/wardrobe/items/{item_id}` | auth | OW-1 | 404-not-403; PATCH never touches user_id/id/createdAt | — |
| 14 | DELETE `/v1/wardrobe/items/{item_id}` | auth | OW-1 | 404-not-403; out-of-DB byte deletion after commit | — |
| 15 | GET `/v1/wardrobe/insight` | auth | OW-1 | grounded, no fabricated gaps; 204 when empty | — |
| 16 | POST `/v1/assistant/chat` | **public today** | — | unbounded input; client-sent `user` context; no rate limit yet | **F-1**, F-2 |
| 17 | POST `/v1/assistant/feedback` | auth | OW-1 | interactionType allow-list; cardId bounded; not keyed → dup evidence | F-7 |
| 18–22 | GET `/v1/knowledge/*` | public | — | no user data; `X-Knowledge-Version`; read-only | — |
| 23 | POST `/v1/looks/saved` | auth | OW-1 | Idempotency-Key; snapshot structurally validated, not provenance-verified | F-4 |
| 24 | GET `/v1/looks/saved` | auth | OW-1 | summary rows; owner-only | — |
| 25 | DELETE `/v1/looks/saved/{saved_look_id}` | auth | OW-1 | 404-not-403 | — |
| 26 | POST `/v1/events` | auth | OW-1 | vocab eventType; date not-in-past; not keyed → duplicate rows | F-8 |
| 27 | GET `/v1/events` | auth | OW-1 | `EventSummary[]`, no outfit snapshot | — |
| 28 | PUT `/v1/events/{event_id}` | auth | OW-1 | full replace; 404-not-403 | — |
| 29 | DELETE `/v1/events/{event_id}` | auth | OW-1 | 404-not-403; history survives (BC-41) | — |
| 30 | POST `/v1/events/{event_id}/outfit` | auth | OW-1 | occasion pre-seeded; regenerable value object; never idempotent | — |
| 31 | GET `/v1/looks/today` | auth | OW-1 | derived per user (own wardrobe × profile × events) | — |
| 32 | POST `/v1/looks/today` | auth | OW-1 | `?seed=` regenerate; never idempotent | — |
| 33 | POST `/v1/looks/today/save` | auth | OW-1 | Idempotency-Key; snapshot structurally validated | F-4 |
| 34 | GET `/v1/learning/summary` | auth | OW-1 | typed labels only, never raw feedback text | — |
| 35 | POST `/v1/feedback` | auth | OW-1 | **gated (NOT mounted)**; rating vocab pending; Idempotency-Key when live | F-2 |
| 36 | POST `/v1/analysis/outfit` | auth | OW-1 | inline image; pre-run MIME/size → 413/422; async 202 | F-2, F-3 |
| 37 | POST `/v1/analysis/hairstyle` | auth | OW-1 | image pass or empty-body profile-only pass (no reference, Phase 28); face = CRITICAL; pre-run checks | F-2, F-3 |
| 38 | POST `/v1/analysis/grooming` | auth | OW-1 | empty JSON `{}` profile-only pass (no reference, Phase 28); vocab options only, no free text | F-2 |
| 39 | GET `/v1/analysis/runs/{run_id}` | auth | OW-1 | UUID; 404-not-403; full immutable result to owner only | — |
| 40 | GET `/v1/analysis/runs` | auth | OW-1 | summary rows (no `result`); run_type filter | — |
| 41 | POST `/v1/outfits/generate` | auth | OW-1 | sync rules-based; 204 empty wardrobe; never idempotent | F-2 |
| 42 | POST `/v1/outfits/saved` | auth | OW-1 | Idempotency-Key; snapshot structurally validated | F-4 |
| 43 | GET `/v1/looks` | auth | OW-1 | cursor feed; engine-ranked; no re-sort (API-27); `isOwned` personalization | — |
| 44 | GET `/v1/looks/{look_id}` | auth | OW-1 | catalog `code`; 404-not-403 | — |
| 45 | GET `/v1/subscriptions/me` | auth | OW-1 | entitlement state only; 404 when never subscribed | — |
| 46 | POST `/v1/subscriptions` | auth | OW-1 | Idempotency-Key; planCode vocab; payment outcome 402/424; not mounted | F-2 |
| 47 | POST `/v1/media/uploads` | auth | OW-1 | **sealed**; declared MIME/size/purpose; owner-scoped signed URL | F-3 |
| 48 | POST `/v1/media/uploads/{id}/complete` | auth | OW-1 | **sealed**; HEAD-verified; MediaRef insert (TRX-1) | F-3 |

### 7.2 Additive / gated (defined, **not mounted** — no fake 200, API-12)

| Endpoint | Auth | Owner | Security notes | Finding |
| --- | --- | --- | --- | --- |
| GET `/v1/assistant/conversations` (A-3) | auth | OW-1 | gated on G6/G7; summaries `messageCount` only, no preview | — |
| GET `/v1/assistant/conversations/{id}` (A-4) | auth | OW-1 | transcript owner-only; 404-not-403 | — |
| DELETE `/v1/assistant/conversations/{id}` (A-5) | auth | OW-1 | whole-conversation delete only; signals survive (BC-41) | — |
| GET `/v1/wardrobe/items/{item_id}` (W-2) | auth | OW-1 | single-item read, additive; served from list today | — |
| GET `/v1/events/{event_id}` (E-3) | auth | OW-1 | single-event read, additive; served from list today | — |

### 7.3 Non-client-facing (system/admin)

| Path | Principal | Security notes |
| --- | --- | --- |
| Subscription billing webhook | system (server-to-server) | idempotent; never in a DB transaction; updates status/renewsAt/external_ref only; no payment data stored |
| Knowledge seed/write (M5 P2) | admin (`require_admin`) | no user-accessible admin path |
| Account erasure / deletion | server-side | full CASCADE + blob cleanup + external cancel; **cancel-first** 409 for active subscription |

---

## 8. Findings register

Severity: **HIGH** = must be closed before the surface becomes the product;
**MEDIUM** = should be closed at the owning milestone; **LOW** = accepted
trade-off or implementation detail. All are recommendations; **no fix is
implemented here.**

| ID | Severity | Dimension | Surface | What the design already does | Gap | Recommended control (future) | Trace |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F-1 | HIGH (current-state) | Authentication, validation, sensitive data | `POST /v1/assistant/chat` | Target: additive Bearer auth, server-wins context (R47), input caps, no-internals | Live endpoint is public, client-trusted context, unbounded input today | Land with D-AUTH-1 + M4: additive auth, server-derived context, caps (≤2000 chars/≤50 turns), rate limit | ASSISTANT_API 199/238/332/339/393-399/418-425/565-570 |
| F-2 | HIGH | Rate limiting | All surfaces; especially public chat + auth + AI endpoints | `429 RATE_LIMITED` + `Retry-After` category everywhere | **No quantified thresholds** anywhere | Quantify per-surface limits at M1 rate-limit infra: per IP + per email/account for auth; per IP + per user for chat; per user for analysis/generation/feedback; `Retry-After` honored | API_LAYER:237; AUTH 223-226/306-307; ASSISTANT 442-443; SCAN:771; module error tables |
| F-3 | MEDIUM | File/media validation | Analysis submits (36/37), media uploads (47/48) | MIME allow-list + size + HEAD verification (two-phase); no bytes in RAM | No **dimension bounds**, no deep content inspection (re-encode/malware/NSFW) | Close inside sealed M16/processing job: pixel bounds, re-encode to allow-list codec, content screening | MEDIA_UPLOAD 4.2/4.4; SCAN 379-380/566-571; API_LAYER API-38 |
| F-4 | MEDIUM | Mass assignment / data integrity | `POST /v1/looks/saved`, `/v1/outfits/saved`, `/v1/looks/today/save` | Structural validation of `snapshot`; owner-owned; immutable (TRX-3); no cross-user vector | Snapshot not **provenance-verified** against a producing run → self-fabricated "AI" content in history | At M7: when `snapshot`/`source_run_id` claims a producing surface, verify the referenced run is owned + result matches; treat unverifiable snapshots as client-authored, not server AI output | RECOMMENDATION 395-400/478; HAIR 561/572; EVENTS 579-580 |
| F-5 | MEDIUM | ID enumeration | `POST /v1/auth/login`, register | Owner 404-not-403 everywhere; no 404 on social | Login inherits a `404` branch from UC-3 → account oracle | Honor the contract's uniform-`401` instruction at M1 (no account ⇔ wrong password) | AUTH_API 302-305/271-272 |
| F-6 | MEDIUM | AI prompt/data leakage | All AI surfaces (16, 36-38, 41, 30/31) | No internals on the wire; R47 never stored; `reason` never in prompts; degraded boolean only | **Data minimization** to providers (what image/context is sent) not quantified; prompt-injection hardening not specified | At AI-integration milestone: per-capability minimization policy, redaction/scaling of images, prompt-injection defenses alongside caps | AI_INTEGRATION §8; ASSISTANT 423-425/565-570; HAIR 611-613 |
| F-7 | LOW | Idempotency (accepted) | `POST /v1/assistant/feedback` | Append-only evidence rows; no key in the §11 list | Retry appends a duplicate signal row | Accepted design trade-off; revisit if duplicate evidence distorts learning | FEEDBACK_LEARNING 335/601-603 |
| F-8 | LOW | Idempotency (accepted) | `POST /v1/wardrobe/items`, `POST /v1/events` | Typed DTOs; 409 on dup save elsewhere | Create not Idempotency-keyed → duplicate rows on retry | Accepted (inventory does not key them); additive if duplicate suppression wanted | WARDROBE 607-609; EVENTS 613-615 |
| F-9 | LOW | Authorization | `X-Conversation-Id` header (A-3/A-4/A-5) | Additive header; server creates conversation on first use; 404-not-403 | A supplied conversation id must be ownership-validated before association/read | Enforce OW-1 on any client-supplied `X-Conversation-Id` at M4 | ASSISTANT 400-402/522-526 |

---

## 9. Verified strengths (controls that already hold — no finding)

These are the protections the accepted contracts already guarantee, confirmed
across every module:

1. **Ownership is structural (OW-1 + 404-not-403).** Every user-owned endpoint
   resolves `user_id` from the token and filters by it; foreign/non-existent
   ids → 404, never 403, never an existence hint (`API_CONTRACT_RULES.md` C-9;
   `API_RESPONSE_CONVENTIONS.md:146-148`; module error tables).
2. **UUID identifiers, server-generated.** No sequential ids, no client-
   generated ids; knowledge uses stable non-sensitive catalog codes
   (C-13, PR-3; `API_RESPONSE_CONVENTIONS.md` §8).
3. **Typed + vocab validation everywhere.** Typed Pydantic DTOs; controlled
   vocabularies → 422 with allowed values; no free strings, no `?filter=json`
   (`API_CONTRACT_RULES.md` C-6, §10).
4. **ER-0/ER-1/ER-2 leak prevention.** `details` allow-list-only; safe messages
   built in one mapper; stack/SQL/provider/prompt/token/user-content never on
   the wire (`ERROR_HANDLING.md` §6; `API_ERROR_CONTRACT.md` §9).
5. **Token hygiene.** Backend never stores passwords/refresh secrets; provider
   tokens discarded; tokens never logged or in URLs; only `accessToken` on
   issue (`AUTH_API.md` 66-68/265-268/329-330).
6. **Media is private by default and never in JSON.** MediaRef-only, object-key
   namespacing, short-lived owner-scoped signed URLs, two-phase validation,
   bytes never in PostgreSQL/RAM/logs (PR-8, MS10.3; `MEDIA_UPLOAD_ARCHITECTURE.md`).
7. **AI internals never on the wire.** No provider/model/prompt/raw output;
   degraded boolean only; `engine_version` the only provenance; `reason` never
   in prompts (C-8; `HAIRSTYLE_RECOMMENDATION_API.md` §4.8).
8. **Summary-only lists.** No run `result`, no conversation previews, bounded
   `top`/`alternatives`, tighter cursor limit (`PAGINATION_FILTERING.md` §8).
9. **Idempotency on every double-write-prone save.** Register, sync, saved
   looks, today-save, outfits-saved, feedback (when live), subscriptions
   (`API_CONTRACT_RULES.md` §11).
10. **Complete erasure.** Full CASCADE + blob cleanup + external subscription
    cancellation; cancel-first 409 (`SECURITY_PRIVACY_DESIGN.md` §5;
    `SUBSCRIPTION_API.md:156-159`).
11. **Gating discipline.** Sealed/gated modules unmounted with no fake 200
    (API-12); additive endpoints clearly marked.
12. **Request-ID correlation.** `X-Request-Id` echoed everywhere; `details.request_id`
    on 5xx; bounded format; never a security carrier
    (`API_RESPONSE_CONVENTIONS.md` §12).

---

## 10. Validation reference

- **Every endpoint in the matrix is from the accepted inventory** —
  `API_INVENTORY.md` §4 (lines 114–161) verified 1:1 against
  `API_CONTRACT_RULES.md` §12.1–12.16; additive/gated and non-client-facing
  endpoints traced to their module contracts (ASSISTANT A-3/4/5, WARDROBE W-2,
  DAILY_OUTFIT_EVENTS E-3, SUBSCRIPTION webhook, knowledge seed, erasure).
- **Every control claim is cited to an accepted doc** by `file:line`
  (AUTH_AUTHORIZATION OW-1/404-not-403; ERROR_HANDLING/API_ERROR_CONTRACT
  ER-0…3; MEDIA_UPLOAD §4; SECURITY_PRIVACY §3–§5; AI_INTEGRATION §8;
  API_LAYER API-5/6/13…16/33…39; API_CONTRACT_RULES §14; module contracts).
- **No contract change is proposed.** The findings register recommends controls
  that land at existing milestones (M1 rate-limit/auth, M4 assistant, M7 save,
  M16 media, AI-integration) — no new endpoint, header, DTO field, or wire
  shape is introduced.
- **Current-state claims are verified against the live repo:** only `GET
  /health` + `POST /v1/assistant/chat` exist (`backend/app/main.py:18,23`);
  the assistant endpoint is unauthenticated today (ASSISTANT_API §3).
- No code, routers, DTOs, or Flutter changes; `git status --short` shows only
  this doc + `CURRENT_STATE.md` (no `pytest` run needed).

---

## 11. Open decisions (security-relevant)

Each is a **gate** the contracts already depend on; the review flags what must
be decided before the relevant surface mounts:

1. **D-AUTH-1 (auth provider)** — gates 401/403 on every protected endpoint
   and additive assistant auth; also determines token/refresh semantics.
2. **Rate-limit thresholds (F-2)** — no contract number exists; the quantified
   policy lands with M1 rate-limit infrastructure.
3. **MS10.3 (media privacy)** — seals M16; also where dimension bounds and
   deep content inspection (F-3) land.
4. **Conversation retention (G6/G7)** — gates the A-3/4/5 conversation family
   and any `assistant_messages` persistence; default remains transient.
5. **Feedback design (PR-12)** — fixes the `rating` vocabulary before F-1
   (feedback) mounts.
6. **AI provider + minimization policy (F-6)** — the concrete provider and the
   per-capability data-minimization policy land with the AI integration.
7. **Save-snapshot provenance (F-4)** — whether a bare client snapshot is ever
   treated as server-verified AI output; decide at M7.
8. **Unchanged project-wide opens** — User fields, Today'sLookRecord (P1),
   RecommendationHistory (P3), `subscriptions.status` vocabulary, K9.1 shape.

---

## 12. Report, assumptions, constraints

**What changed (this step):** added `docs/api/API_SECURITY_REVIEW.md` — a
review of every proposed API against the security checklist: the eleven
dimensions (§5), the seven protected-data deep-dives (§6), the per-endpoint
security matrix for all 48 inventory endpoints + additive/gated + non-client-
facing paths (§7), the findings register (F-1…F-9, §8), and the verified
strengths (§9). **No fixes implemented; no contract changed; no endpoint
mounted.**

**Skills used:** repository analysis (the accepted security/API docs +
`backend/app/main.py` live-surface verification) + security-design review —
documentation only.

**Files changed:** `docs/api/API_SECURITY_REVIEW.md` (new).

**Validation run:**
- Every matrix row traced to `API_INVENTORY.md` §4 and the module contracts;
  every control claim cited by `file:line` to an accepted source.
- Findings are honest — verified gaps only; accepted trade-offs (F-7/F-8) are
  labeled as accepted; current-state gaps (F-1) are separated from contract
  gaps.
- Code fences balanced (1 in §1.1 diagram context; counted inline examples);
  `git status --short`: docs/api/ holds the 17 untracked API docs
  (API_SECURITY_REVIEW.md added) + modified `CURRENT_STATE.md`; no code,
  directories, or files created.

**Remaining:** STEP 6 design continues. Security controls land at their
milestones (M1 auth/rate-limit, M4 assistant auth + caps, M7 snapshot
provenance, M16 media + MS10.3, AI integration minimization) — this review is
the checklist against which those implementations will be validated. Open
decisions in §11.

---

## Constraints honored

- **No implementation:** no code, routers, dependencies, DTOs, Flutter
  changes, or mounted endpoints; the live contract (`GET /health`,
  `POST /v1/assistant/chat`) is untouched.
- **No contract change:** no new endpoint, header, field, or wire shape;
  findings recommend controls at existing milestones only.
- **No fabricated controls:** protections not present in the accepted docs are
  recorded as findings, not asserted as present.
- **Privacy-sensitive treatment:** face, grooming, wardrobe, photo, event,
  conversation, and subscription data are treated as CRITICAL/HIGH per
  `SECURITY_PRIVACY_DESIGN.md`; no appearance data is described in a way that
  shames or exposes it.
- **Scope rule:** this document reviews the API surface only; database-layer,
  auth-provider, media-privacy, and AI-provider design are referenced as
  gates, not re-designed.
