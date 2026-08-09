# Fansivibe — Account & Assistant Domain Model

> **STEP 3 (continuation) — DOMAIN MODEL DESIGN.** Defines the domain
> boundaries for Fansivibe's account/subscription system and the AI assistant
> chat surface, using the STEP 2 inventory to **distinguish what already exists
> from future requirements** — without forcing authentication-provider
> implementation details into the domain model.
>
> **Source of truth:** the real repository
> (`newproject/flutter_application_1` + `backend/`) and the STEP 2/STEP 3
> documents (`ACTION_API_INVENTORY.md`, `DATA_OWNERSHIP.md`,
> `AI_DATA_FLOW.md`, `ARCHITECTURE_GAP_REPORT.md`, `STORAGE_INVENTORY.md`,
> `DOMAIN_ENTITIES.md`, `DOMAIN_MODEL_RULES.md`, `AI_DOMAIN_MODEL.md`).
>
> **Status:** documentation only. **No SQL, no tables, no UI changes, no auth
> implemented.**

---

## 1. Verified reality check — what exists vs. what is future

| Concept | Status today | Evidence |
| --- | --- | --- |
| **Authentication** | **None.** "Create Account" (email/password/name), social sign-in, and "Maybe Later — Save Locally" all just navigate Home | `account_creation_screen.dart:74-98` — three branches, zero auth calls |
| **User Account** | **Missing concept** (no user entity; only the anonymous on-device `UserModel` blob) | `DATA_MODEL_INVENTORY.md` §19.6; `ARCHITECTURE_GAP_REPORT.md` AU11.1 |
| **Subscription** | **Stub only.** `SubscriptionScreen` + mock plans; subscribe/upgrade = SnackBar | `ACTION_API_INVENTORY.md` #30; `MVP_SCOPE.md` P2 |
| **Subscription Plan** | **Mock** `SubscriptionPlan` (`profile_mocks.dart:31`) | `DATA_OWNERSHIP.md` §Profile |
| **Feature Entitlement** | **None.** `allCapabilities` "active" flags are marketing copy, no gating | `AI_DATA_FLOW.md` Part D.1; `DOMAIN_RELATIONSHIPS.md` R45/R46 |
| **Feature Usage** | **Signals only** — `LearningSignal` (8 types) in `UserModel.signals` | `DATA_OWNERSHIP.md` §`LearningSignal` |
| **AI Assistant Conversation** | **Transient** widget state (`AssistantService._messages`), cleared on exit; nothing persisted | `AI_DATA_FLOW.md` Part A; `DATA_OWNERSHIP.md` §`AssistantMessage` |
| **Assistant Message** | **DTO** (mirrored 1:1 with backend `schemas.py`); transient in-memory | `assistant/data/models.dart:108`; `ARCHITECTURE_GAP_REPORT.md` A3.1 (KEEP) |
| **Assistant Action** | **Config + mapping.** `SuggestionCard.action` + `AssistantRoutes.routeFor` + backend `NAVIGATION_MAP` | `assistant_routes.dart:8` (16 action ids); `DATA_OWNERSHIP.md` §Stylist/Assistant |

---

## 2. The nine concepts — verdict

| # | Concept | Verdict | Category |
| --- | --- | --- | --- |
| 1 | **Authentication** | Not a domain entity — an **external process/service** | External data (identity at the boundary) |
| 2 | **User Account** | **ENTITY** — `User` (E1, aggregate root) | Current profile state / identity |
| 3 | **Subscription** | **ENTITY** (E10, P2) | Current state + external entitlement |
| 4 | **Subscription Plan** | Not an entity | System knowledge (config) |
| 5 | **Feature Entitlement** | Not an entity today | Derived view (config × subscription) |
| 6 | **Feature Usage** | **HISTORICAL RECORD** — `LearningSignal` (E7) | Historical, append-only |
| 7 | **AI Assistant Conversation** | Not an entity today (transient); **historical if retained** (undecided) | Temporary state → conditional history |
| 8 | **Assistant Message** | Not an entity — **DTO** + value object | DTO (wire shape) / transient |
| 9 | **Assistant Action** | Not an entity | System knowledge (action vocabulary + mapping) |

**Only two true entities: `User` (account) and `Subscription` (P2).** Everything
else is an external process, config, a derived view, history, a DTO, or a
transient conversation.

---

## 3. The concepts in detail

### 3.1 Authentication

- **Purpose:** verifying who the user is. Today it is a **mock UI** — all three
  account-creation branches simply navigate Home
  (`account_creation_screen.dart:74-98`).
- **Boundary rule (task requirement):** authentication-provider implementation
  details (OAuth flows, token handling, password hashing, session cookies) are
  the **auth service's** concern and are **NOT domain entities**. The domain
  holds only the *result* at the boundary: an **opaque auth identity reference**
  on the `User` account (provider kind + provider subject id) so the domain is
  provider-agnostic.
- **Ownership / lifecycle:** external service owns the flows; the domain owns
  the linked identity. **Persistent?** The identity link on `User` — yes
  (future). **External?** **Yes** (auth provider). **Generated?** No.
  **Historical?** No.
- **Categories:** EXTERNAL (identity at the boundary) + SYSTEM process.

### 3.2 User Account

- **Purpose:** the `User` aggregate root — the account identity that scopes every
  user-owned entity and is the reason every future relational write is
  user-scoped (`ACTION_API_INVENTORY.md` Part 4 #1; AU11.1, AZ12.3).
- **Ownership:** `auth`/account feature (future); created through the onboarding
  `AccountCreationScreen` UI today (mock).
- **Fields (domain facts, not auth internals):** stable account id; **auth
  identity reference** (provider kind + subject id — §3.1); display name;
  **anonymous-vs-account state** (the "Maybe Later — Save Locally" path →
  anonymous→sync merge, AU11.2); membership/subscription reference.
- **Lifecycle:** register (email/password/social) → authenticate → update →
  delete (cascades user-owned data per retention).
- **Persistent?** Yes (future; the device `UserModel` blob is today's anonymous
  stand-in). **External?** No. **Generated?** No. **Historical?** No — current
  identity state.

### 3.3 Subscription

- **Purpose:** the user's paid entitlement state (active plan + period). Today
  purchase is a stub (`ACTION_API_INVENTORY.md` #30).
- **Ownership:** user-owned *state*; the *billing/entitlement* is an external
  service (`STORAGE_INVENTORY.md` cat 5).
- **Relationships:** references `SubscriptionPlan` (config, R44); feeds derived
  **Feature Entitlement** (R45/R-A20).
- **Lifecycle:** activate → renew → cancel/expire (via external service).
- **Persistent?** Yes (entity, P2). **External?** Entitlement result — yes;
  the state — user-owned. **Generated?** No. **Historical?** No (current state;
  billing history is external).

### 3.4 Subscription Plan

- **Purpose:** the catalog of offered plans (mock `SubscriptionPlan`). System
  content every user reads — not a per-user record.
- **Ownership:** system/content management; backend-controlled
  (`ARCHITECTURE.md` "no hardcoded backend-controlled categories").
- **Relationships:** referenced by id from `Subscription` (R44); capability
  gating derives from the plan's entitlements (R45).
- **Persistent?** Knowledge content (versioned store). **External?** No.
  **Generated?** No (authored). **Historical?** No (versioned, content-managed).

### 3.5 Feature Entitlement

- **Purpose:** which features/capabilities a user's account+subscription actually
  unlocks (e.g. Face Analysis, Wardrobe Intelligence, Assistant).
- **Classification:** **not an entity today.** It is a **derived view** over
  (capability/feature catalog × subscription state)
  (`DOMAIN_RELATIONSHIPS.md` R45/R46; `AI_DOMAIN_MODEL.md` R-A20). No per-user
  entitlement rows exist or should be created until a real capability/unlock
  system lands (P3).
- **Persistent?** No (derived). **External?** No. **Generated?** No (derived).
  **Historical?** No.
- **Status note:** `allCapabilities` "active" flags are marketing copy with no
  gating today (`AI_DATA_FLOW.md` Part D.1).

### 3.6 Feature Usage

- **Purpose:** the append-only trace of how the user uses features — the raw
  material for learning and future analytics.
- **Classification:** **HISTORICAL RECORD** — realized by `LearningSignal` (E7,
  8 types: `item_added`, `analysis_updated`, `style_updated`, `look_saved`,
  `occasion_preferred`, `assistant_message`, `suggestion_opened`,
  `assistant_navigation`). Derived aggregates on top (`ActivityDay`,
  `StyleScoreRecord`) are separate derived records.
- **Ownership:** user-owned history; written by `LearningService` + features.
- **Persistent?** Yes (append-only; soft-delete/retention only). **External?**
  No. **Generated?** No (recorded events). **Historical?** **Yes.**
- **Note:** "Feature Usage" as a *concept* maps 1:1 to the existing signal trace
  — no new entity is needed; feature-specific aggregates are derived.

### 3.7 AI Assistant Conversation

- **Purpose:** the chat session (user + assistant turns) shown in
  `assistant_screen`. Today it lives in `AssistantService._messages` and is
  **cleared on exit** (`DATA_OWNERSHIP.md` §`AssistantMessage`).
- **Classification:** **TEMPORARY PROCESSING STATE** today. Persisting it is an
  **undecided privacy/product choice** (`STORAGE_INVENTORY.md` §1.10): if
  retained → **HISTORICAL RECORD** (append-only per-user conversations, JSONB),
  plus a `conversation_id` linking messages; if not → stays ephemeral and only
  the `assistant_message`/`suggestion_opened`/`assistant_navigation` signals
  persist.
- **Ownership:** `features/assistant`; user-owned if retained.
- **Persistent?** No (transient; retention undecided). **External?** No.
  **Generated?** The assistant turns are AI output; the user turns are
  user-authored. **Historical?** Conditional (retention decision).
- **Relationship:** 1:N to `AssistantMessage`.

### 3.8 Assistant Message

- **Purpose:** one turn in a conversation — `role` (user/assistant), `text`,
  `cards`, `clarifications`, `navigation`, `pending`
  (`assistant/data/models.dart:108`).
- **Classification:** **DTO / value object.** It is the wire shape mirrored 1:1
  with backend `schemas.py` (KEEP — `ARCHITECTURE_GAP_REPORT.md` A3.1). Not a
  domain entity, not persisted today.
- **Ownership:** assistant feature (client) + backend engine (server).
- **Persistent?** No (unless conversation retention is accepted). **External?**
  The backend-generated content comes over the wire — yes in transit; the DTO
  itself is ours. **Generated?** Assistant turns = AI output; user turns =
  user-authored. **Historical?** Only within an retained conversation.
- **Note:** do **not** promote `AssistantMessage` to an entity; if conversations
  are kept, the retained shape is a historical record built from this DTO's
  content (`DOMAIN_MODEL_RULES.md` §2.9).

### 3.9 Assistant Action

- **Purpose:** the controlled action vocabulary the AI may request the client to
  perform (open a feature) — `SuggestionCard.action` values mapped to app routes
  by `AssistantRoutes.routeFor` (`assistant_routes.dart:8`, 16 ids:
  `open_outfit`, `open_hairstyle`, `open_grooming`, `open_wardrobe`,
  `open_stylist`, `open_daily`, `open_discover`, `home`, `profile`,
  `daily-outfit`, `hairstyle`, `grooming`, `build-outfit`, `wardrobe`, `stylist`,
  `discover`; fallback → stylist) and mirrored by the backend `NAVIGATION_MAP`
  and the quick-action configs (`QuickActionData`/`StylistActionData`).
- **Classification:** **SYSTEM CONFIGURATION** (action vocabulary + route
  mapping) — the AI never navigates by itself; it returns an action id and the
  client executes it (`assistant_routes.dart:4-6`).
- **Ownership:** system (config shared by assistant, stylist, quick actions,
  backend). One canonical source required (3 mirrors today).
- **Persistent?** Config store. **External?** No. **Generated?** No (authored).
  **Historical?** No — but *executing* an action emits historical signals
  (`suggestion_opened`, `assistant_navigation`).

---

## 4. Relationships

Legend (from `DOMAIN_RELATIONSHIPS.md`): **REFERENCE / COMPOSITION /
DERIVED_FROM / FEEDS / GATES** × 1:1 / 1:N / N:M. `(future)`/`(P2)`/`(P3)`/
`(undecided)` = pending.

| # | Concept A | Relationship | Concept B | Cardinality | Note |
| --- | --- | --- | --- | --- | --- |
| G1 | Authentication (external) | **REFERENCE** | `User` account (auth identity link) | 1:1 | boundary result; provider-agnostic |
| G2 | `User` | (future) 0..1 REFERENCE | `Subscription` | 0..1:1 | membership link; = R10 |
| G3 | `Subscription` | REFERENCE | `SubscriptionPlan` (config) | 0..1:1 | = R44; plan required when subscribed |
| G4 | `Subscription` × feature/capability catalog | DERIVED_FROM | Feature Entitlement (derived) | 1:1 | = R45/R-A20; prospective |
| G5 | `User` | COMPOSITION (append-only) | Feature Usage = `LearningSignal` | 1:N | = R7; signals are the usage trace |
| G6 | `User` | (future) 1:N REFERENCE | AI Assistant Conversation | 0..N:1 | if retention is accepted |
| G7 | AI Assistant Conversation | COMPOSITION | Assistant Message (DTO) | 1:N | transient today; historical if kept |
| G8 | Assistant Message | REFERENCE | Assistant Action (action id / route) | 0..1:1 | via `SuggestionCard.action` / `NavigationRequest.route` |
| G9 | Assistant Action (config) | DERIVED_FROM | route mapping (`AssistantRoutes`) | 1:1 | the client executes, never the AI |
| G10 | Assistant Action | FEEDS (on execute) | Feature Usage (`suggestion_opened`, `assistant_navigation`) | 1:N | signals record the action occurrence |
| G11 | `User` | GATES (via entitlement) | Assistant features / capabilities | N:M | derived gating, prospective |

### Relationship rules (account/assistant cluster)

1. **Auth stays at the boundary.** The domain stores an opaque identity
   reference, never provider implementation details (G1).
2. **The account is the root; entitlement and usage hang off it.** Subscription
   (G2), signals (G5), conversations (G6) are all user-scoped.
3. **Entitlement is derived, never stored per user** until a capability system
   exists (G4, G11).
4. **Conversations and messages are transient DTOs** unless the product decides
   to retain them — that decision is the only thing that would turn them into
   history (G6, G7).
5. **The AI never navigates; it emits a config action id.** Action vocabulary +
   route mapping are system config; the execution is traced by signals (G8–G10).

---

## 5. What exists vs. future — boundary summary

| Concept | Exists today | Future requirement | Storage category (if/when) |
| --- | --- | --- | --- |
| Authentication | Mock UI only | Real auth + anonymous→sync (AU11.1/AU11.2) | External service |
| User Account | — (blob stand-in) | `User` entity + identity link | Relational row |
| Subscription | Stub screen | `Subscription` entity (P2) | Relational state + external entitlement |
| Subscription Plan | Mock | Content-managed plan catalog | Knowledge/config |
| Feature Entitlement | — (marketing flags) | Derived gating (P3) | Derived view, no rows |
| Feature Usage | `LearningSignal` (8 types) | Feature-specific derived aggregates | Append-only history |
| Conversation | Transient, cleared | Retention decision (undecided) | JSONB if retained, else temp |
| Assistant Message | DTO (mirrored, KEEP) | same shape; persisted only if retained | DTO / retained JSONB |
| Assistant Action | Config + route map (3 mirrors) | one canonical action source | Knowledge/config |

---

## 6. Report — what was found & what must be modeled next

### What was found

- **Two entities, seven non-entities.** Only `User` (account) and `Subscription`
  (P2) are domain entities. Authentication is an external process, plans and
  actions are config, entitlement is derived, usage is the existing signal
  history, and conversations/messages are transient DTOs.
- **Auth is deliberately kept at the boundary** (task rule): the domain holds an
  opaque identity reference; OAuth/hashing/token details stay in the auth
  service.
- **Three today-vs-future gaps drive this cluster:** there is **no auth at all**
  (three account-creation branches just navigate Home), **no subscription
  entity** (mock plans + stub purchase), and the **conversation is ephemeral**
  (retention is an undecided privacy/product choice — only signals persist).
- **Feature Usage already exists as `LearningSignal`** — no new entity needed;
  the assistant action vocabulary (16 ids) is already a controlled config that
  the AI may not navigate with directly.

### What must be modeled next (dependency order, none implemented)

1. **Auth + anonymous→sync design (AU11.1/AU11.2, P0):** defines `User`'s
   fields (identity link, anonymous flag) and the device↔account merge for the
   `UserModel` blob — the prerequisite for every relational write.
2. **Step 4 storage:** `User` + `Subscription` rows, signal history,
   plan/action config stores; JSONB *only if* conversation retention is accepted.
3. **Typed API + error contract (A3.2/A3.3, P0):** `/auth/*`, `/users/me`,
   `POST /users/me/sync`, assistant endpoints — carrying these boundaries.
4. **Subscription implementation (P2)** + **capability gating (P3):** only then
   does Feature Entitlement become a real derived view.
5. **Conversation-retention decision:** the single open product choice that
   decides whether `AssistantMessage`/conversation become history.

---

## Constraints honored

- **No SQL, no tables, no repositories, no services, no UI changes, no auth
  implemented.**
- No new dependencies, no code deleted, nothing invented: every exists/future
  claim traces to source (`account_creation_screen.dart:74-98`,
  `assistant_routes.dart:8`, `assistant/data/models.dart:108`, `profile_mocks.dart:31`)
  and STEP 2 refs.
- Authentication-provider implementation details are explicitly kept out of the
  domain model (task requirement).
- The real Fansivibe repository is the source of truth; the separate reference
  project was not used.
