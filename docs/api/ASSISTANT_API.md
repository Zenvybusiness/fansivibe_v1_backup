# Fansivibe — API Contract: Assistant

> **STEP 6 — API CONTRACT DESIGN.** Reviews the **existing** Fansivibe
> assistant API (documented as CURRENT), then defines the **production
> assistant API contract** (documented as TARGET) based on the finalized domain
> model. The TARGET covers the conversational surface — messages, assistant
> actions, context, card feedback, and conversation history (where supported) —
> and shows how the assistant grounds in **structured domain data without
> exposing database implementation details**. It is the focused companion to
> `API_CONTRACT_RULES.md` (§12.4 assistant, §8.1 bare single-resource rule,
> §9 error contract, §13.4 frozen assistant DTOs) and `API_INVENTORY.md`
> (endpoints 16–17), and it sits beside the sibling contracts
> `FEEDBACK_LEARNING_API.md` (UC-23 card-interaction signals, M10 sole writer),
> `AUTH_API.md` (Bearer, OW-1), `RECOMMENDATION_API.md` (the shared
> recommendation shapes the cards point at), and `ERROR_HANDLING.md` (typed
> error taxonomy).
>
> **Status: contract design only. Nothing is implemented.** No code, no
> routers, no `deps.py`, no SQL migrations, no dependencies, no Flutter changes.
> The **live contract is preserved unchanged**: `GET /health` and `POST
> /v1/assistant/chat` keep working verbatim (A3.1, F-13). The chat endpoint
> **stays unauthenticated** until the auth seam (D-AUTH-1) lands; the
> conversation-history surface is **additive and gated** on the undecided
> conversation-retention decision (G6/G7) — no fake 200 before either gate
> (API-12).
>
> **Source of truth:** the real Fansivibe repository — the running backend
> (`backend/app/main.py`, `app/models/schemas.py`, `app/ai/engine.py`,
> `app/ai/intent.py`, `app/ai/tools.py`, `app/ai/llm_backend.py`,
> `app/data/catalog.py`) and the Flutter assistant feature
> (`lib/features/assistant/` — `models.dart`, `assistant_client.dart`,
> `offline_assistant.dart`, `assistant_service.dart`,
> `assistant_routes.dart`), plus the accepted STEP 3/4/5/6 docs —
> `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` (§3.7 conversation, §3.8 message,
> §3.9 assistant action, G6–G10), `DOMAIN_RELATIONSHIPS.md` (R47
> `AssistantUserContext`), `STORAGE_INVENTORY.md` (§1.10 transient
> conversations), `TABLE_DEFINITIONS.md` (`learning_signals`, 8 signal types),
> `APPLICATION_USE_CASES.md` (UC-22, UC-23),
> `AUTH_AUTHORIZATION_ARCHITECTURE.md` (OW-1, `conversations.user_id` M4),
> `ERROR_HANDLING.md` (A3.3/E13.1), STEP 6 `API_CONTRACT_RULES.md`
> (§12.4/§13.4/§9/§11) + `API_INVENTORY.md` (endpoints 16/17) +
> `FEEDBACK_LEARNING_API.md` (§5.2 F-2).

---

## 1. Purpose and scope

This document answers the STEP 6 assistant task in two clearly separated
halves:

- **CURRENT API (§3)** — the assistant as it actually exists today: its one
  endpoint, its request model, its response model, its behavior, and its
  limitations. Nothing here is speculative.
- **TARGET API (§4–§5)** — the production assistant contract derived from the
  finalized domain model: the same live endpoint preserved verbatim, the
  additional card-feedback endpoint (already inventoried), and the additive,
  gated conversation-history surface — plus the contract-level semantics
  (auth, typed errors, repository-loaded context, structured domain grounding,
  learning signals) that turn the prototype into a production assistant
  **without ever changing the frozen wire shape**.

The task's coverage list is mapped explicitly:

- **conversations** — §4.5, A-3/A-4 (additive, gated on retention)
- **messages** — §3.2/§3.3 (current), §4.5 (retained-message shape)
- **assistant actions** — §4.4.3 (the controlled action vocabulary, G8–G10)
- **context** — §3.2 (current client-sent snapshot), §4.4.2 (server-derived
  `AssistantUserContext`, R47)
- **conversation history** — §4.5, A-3/A-4/A-5 (additive, gated)

**The three binding design rules of this document:**

1. **The live assistant contract is frozen (A3.1, F-13).** `AssistantRequest`
   and `AssistantReply` field names, order, and types must never change — no
   additive reorder/rename/retype (F-13). The TARGET therefore *extends around*
   the frozen DTOs (new endpoints, headers, semantics) and never *into* them.
   The single live wire contract (`POST /v1/assistant/chat`, mirrored 1:1 by
   `schemas.py` ↔ `models.dart`) is preserved through every migration step
   (19 tests stay green).
2. **The assistant is a thin, typed projection of the domain — never of the
   database (C-7) and never of an AI provider (C-8).** It grounds in domain
   entities through repository ports (context builder), returns DTO-only
   shapes with stable codes, and exposes no table/column/SQL names and no
   provider/model names or prompts on the wire (ER-0). When the product is
   authenticated, the engine's inputs change from the client-sent `UserContext`
   to repository-loaded state (R47) — the wire `user` field stays frozen.
3. **Learning is backend-owned, not client-submitted (PR-7).** M10 is the
   sole writer of `learning_signals`; there is **no** signal-submit endpoint.
   The only client-facing signal input is `POST /v1/assistant/feedback`
   (UC-23, endpoint 17): `opened` → `suggestion_opened`, `navigated` →
   `assistant_navigation`. The assistant `assistant_message` signal is written
   by the backend once persistence lands — replacing today's client-local
   `recordSignal` calls.

**What it does not do:** implement anything, mount endpoints, add auth before
D-AUTH-1, unseal M16, change the frozen assistant DTOs, invent a conversation
table, or add a signal-submit endpoint. The conversation-history endpoints are
**additive** (not in the accepted 48-endpoint inventory) and **gated** on the
conversation-retention decision — documented now so the shape is settled, never
mounted before the product decides (G6/G7, API-2/API-12).

### 1.1 Grounding facts (re-verified)

- **The assistant is the only live AI surface in the product.** The backend
  exposes exactly two endpoints — `GET /health` and `POST /v1/assistant/chat`
  (`backend/app/main.py`) — and the assistant is the **only remote screen**
  (`SCREEN_DATA_INVENTORY.md` §10.2: "Only remote screen: AssistantScreen
  (backend `/v1/assistant/chat`…)"). Feature priority **P1** (`FEATURE_INVENTORY.md`
  §12).
- **The request/response contract is typed and mirrored 1:1.**
  `backend/app/models/schemas.py` ↔ `lib/features/assistant/data/models.dart`
  define `AssistantRequest`/`AssistantReply`/`ChatMessage`/`UserContext`/
  `SuggestionCard`/`ClarificationOption`/`NavigationRequest`/`WardrobeItem`/
  `FaceData` verbatim (A3.1). These are **frozen** (`API_CONTRACT_RULES.md`
  §13.4, F-13).
- **Behavior is a deterministic rules engine with optional LLM text
  enrichment.** `engine.py` classifies intent (`intent.py`, 10 intents) →
  detects occasion → applies a dialogue policy (greeting/thanks/navigate/
  clarify/unknown/outfit-with-or-without-occasion) → builds typed suggestion
  cards (`tools.py` grounded in `catalog.py` + `UserContext`) → optionally
  enriches the reply text via Ollama (`llm_backend.py`, 8s timeout,
  degrade-to-rules on any failure). Structure is always ours; the LLM only
  writes natural language (`engine.py:9-11`).
- **The endpoint is stateless, unauthenticated, and the client holds the
  conversation.** Each call sends the full message history + a `UserContext`
  snapshot; the server returns one `AssistantReply`; nothing is stored server-
  side (UC-22 non-transactional; conversation transient by default).
- **Conversation persistence is deliberately undecided.** The conversation is
  **TEMPORARY PROCESSING STATE** today, cleared on exit
  (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.7, `STORAGE_INVENTORY.md` §1.10).
  If retained it becomes a **HISTORICAL RECORD** (append-only per-user
  conversations, JSONB, `conversation_id` linking messages, G6/G7); if not,
  only the three assistant signals persist. Module map M4 listed an
  `assistant_messages` "(R51 note)" table that **does not exist** in
  `TABLE_DEFINITIONS.md` (`FASTAPI_ARCHITECTURE_V1.md` F-3) — resolved only
  when the retention decision lands.
- **`AssistantUserContext` is a derived DTO, never stored (R47).** Wardrobe +
  StyleProfile/face + savedLooks + preferredOccasions, snapshotted per request
  (`DOMAIN_RELATIONSHIPS.md` R47; `assistant_service.dart:41` `_buildContext`).
  Today it is client-sent; in the production backend the use case loads it from
  repositories once auth/DB land (`BACKEND_ARCHITECTURE_RULES.md` §6.1).
- **Learning signals (8 types).** `learning_signals` P0 append-only rows with
  no FK to the triggering entity (BC-41); the assistant-related types are
  `assistant_message`, `suggestion_opened`, `assistant_navigation`
  (`TABLE_DEFINITIONS.md` §4.3; `FEEDBACK_LEARNING_API.md` §1.1). M10 is the
  **sole writer** (PR-7); the only client-facing signal input is `POST
  /v1/assistant/feedback` (UC-23, endpoint 17, `AssistantCardFeedback {
  cardId?, interactionType }` → 204, errors 401 only).
- **Assistant actions are a controlled 16-id vocabulary, system config.**
  `SuggestionCard.action` / `NavigationRequest.route` values are mapped to app
  routes by `AssistantRoutes.routeFor` (`assistant_routes.dart`, 16 ids);
  the AI **never navigates by itself** (G9). The vocabulary has **3 mirrors
  today** (`assistant_routes.dart`, backend `NAVIGATION_MAP` in `engine.py:70`,
  and the quick-action/stylist configs) — one canonical source is required
  (G9, `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.9).
- **The 19 pytest cases and the Flutter widget/service tests are the
  compatibility gate.** `tests/test_engine.py` (12 cases) + `test_intent.py`
  pin intent routing and the reply shape; `assistant_screen_test.dart` +
  `offline_assistant_test.dart` pin the client. Every migration step must keep
  them green (`API_CONTRACT_RULES.md` §15).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `backend/app/main.py` | The live endpoint: `POST /v1/assistant/chat`, `response_model=AssistantReply`, no auth, no error mapping. |
| `backend/app/models/schemas.py` | The frozen wire DTOs (A3.1) — `AssistantRequest`, `AssistantReply`, `ChatMessage`, `UserContext`, `WardrobeItem`, `FaceData`, `SuggestionCard`, `ClarificationOption`, `NavigationRequest`. |
| `backend/app/ai/engine.py` / `intent.py` / `tools.py` / `llm_backend.py` | Current behavior: intent routing, dialogue policy, tool cards, optional Ollama enrichment. |
| `backend/app/data/catalog.py` | The static knowledge the tools ground in today (looks, occasions, navigation map). |
| `lib/features/assistant/data/models.dart` | The mirrored Flutter DTOs (KEEP — A3.1). |
| `lib/features/assistant/data/assistant_client.dart` | POST shape, 12s timeout, null-on-failure (offline fallback trigger). |
| `lib/features/assistant/data/offline_assistant.dart` | The on-device rules mirror — the degraded UX contract. |
| `lib/features/assistant/domain/assistant_service.dart` | History held client-side; `_buildContext` (R47); local `recordSignal` for `assistant_message`/`suggestion_opened`/`assistant_navigation`. |
| `lib/features/assistant/presentation/assistant_routes.dart` | The 16-id action→route mapping the client executes. |
| `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` | §3.7 conversation (transient→conditional history), §3.8 message (DTO, not an entity), §3.9 action (config), G6–G10. |
| `DOMAIN_RELATIONSHIPS.md` / `STORAGE_INVENTORY.md` | R47 context snapshot; §1.10 transient conversations / retention principle. |
| `TABLE_DEFINITIONS.md` / `BUSINESS_CONSTRAINTS.md` | `learning_signals` (8 types, append-only, BC-41); no `conversations`/`assistant_messages` table. |
| `APPLICATION_USE_CASES.md` | UC-22 (live, non-transactional), UC-23 (single INSERT `learning_signals`). |
| `AUTH_AUTHORIZATION_ARCHITECTURE.md` | OW-1; Assistant Conversations → `conversations.user_id` (M4) if retained. |
| `ERROR_HANDLING.md` | Typed 12-category errors (A3.3/E13.1) — the TARGET error body; never leaks internals. |
| STEP 6 siblings | `API_CONTRACT_RULES.md` (§12.4/§13.4/§8.1/§9/§11), `API_INVENTORY.md` (endpoints 16–17), `FEEDBACK_LEARNING_API.md` (§5.2 F-2, §4.4 wire DTOs), `AUTH_API.md`, `RECOMMENDATION_API.md`. |

---

## 3. CURRENT API — the assistant as it exists today

> This section documents only what is actually live in the repository. It is
> the basis for the TARGET contract in §4/§5 and the "current limitations"
> that the TARGET resolves. **Nothing here is a design proposal.**

### 3.1 Current endpoint

| Attribute | Value |
| --- | --- |
| **Method / path** | `POST /v1/assistant/chat` |
| **Purpose** | The conversational assistant: intent classification → tool selection → dialogue policy → typed structured reply; optional LLM text enrichment that degrades to rules. |
| **Auth** | **None** — public (F-5). No `Authorization`, no user scoping. |
| **Sync/async** | **Sync** — one HTTP call, one `AssistantReply`. No `202`, no polling. |
| **Versioning** | Path `/v1`; no `Accept` negotiation, no knowledge/version header. |
| **Response format** | Bare `AssistantReply` — **no envelope**, no `data` wrapper (F-13, API-17). |
| **Idempotency** | None — each call is a new exchange (API-33; chat is on the never-idempotent list). |
| **Server behavior on failure** | Pydantic 422 for malformed bodies (FastAPI default — not the typed error contract); otherwise 200. The **client** falls back to `OfflineAssistant` on network failure/timeout — a degraded UX, not a surfaced error. |
| **Also live** | `GET /health` → `{"status": "ok"}` (versionless). |

**Implementation** (`backend/app/main.py:23-25`):

```python
@app.post("/v1/assistant/chat", response_model=AssistantReply)
def assistant_chat(request: AssistantRequest) -> AssistantReply:
    return engine.handle(request)
```

The route has no `deps.py` auth dependency, no exception mapper, and no
pagination/idempotency/request-id machinery. It is the entire production
backend surface for the assistant today.

### 3.2 Current request model

`AssistantRequest` (frozen, `schemas.py`):

```json
{
  "messages": [ { "role": "user", "content": "what should I wear to a date?" } ],
  "user": {
    "wardrobe":   [ { "id": "11", "name": "Dark Denim Jeans", "category": "bottoms",
                      "color": "Indigo", "material": "Denim", "isFavorite": true } ],
    "face":            { "faceShape": "oval", "skinTone": null, "bodyType": null, "styleType": null },
    "savedLooks":      [ "Modern Minimalist" ],
    "preferredOccasions": [ "date" ]
  }
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `messages` | `ChatMessage[]` | The full conversation history the **client** holds; `ChatMessage { role*, content* }` with free-string `role`/`content`. Unbounded length. |
| `user` | `UserContext?` | On-device user-model snapshot (R47) — `wardrobe: WardrobeItem[]`, `face?: FaceData`, `savedLooks: string[]`, `preferredOccasions: string[]`. Optional (may be omitted/`null`). |
| `WardrobeItem` | — | `id, name, category, color, material?, isFavorite` (a subset of the production `WardrobeItem` — no `imageRef`/timestamps). |
| `FaceData` | — | `faceShape?, skinTone?, bodyType?, styleType?` — the mirrored `StyleProfile.FaceProfile` projection (R15). |

**What is accepted but unused by the engine today:** `preferredOccasions` is
serialized and accepted but **never read** by `engine.py`/`tools.py`;
`face.skinTone`/`face.bodyType`/`face.styleType` are accepted but only
`face.faceShape` is consumed (`tools.py:36`).

### 3.3 Current response model

`AssistantReply` (frozen, `schemas.py`):

```json
{
  "intent": "outfit",
  "text": "For date, I'd go with the Date Night Refined — Tap the card to build it.",
  "cards": [
    { "kind": "outfit", "title": "Date Night Refined", "subtitle": "…",
      "score": 89, "items": ["Leather Chelsea Boots - Footwear", "…"],
      "action": "open_outfit" }
  ],
  "clarifications": [ { "label": "Casual", "value": "casual" } ],
  "navigation": null
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `intent` | `string` | One of the 10 intent ids (`outfit`, `hairstyle`, `grooming`, `wardrobe`, `navigate`, `tip`, `greeting`, `thanks`, `clarify`, `unknown`). |
| `text` | `string` | The natural-language reply (rules text, optionally LLM-enriched). |
| `cards` | `SuggestionCard[]` | Typed suggestion cards — `kind` (e.g. `outfit`/`hairstyle`/`grooming`/`wardrobe`/`tip`), `title`, `subtitle`, `score?` (0–100), `items: string[]`, `action?` (one of the 16 action ids). |
| `clarifications` | `ClarificationOption[]` | Tappable follow-up chips — `{ label, value }`; the client sends `value` back as the next user message. |
| `navigation` | `NavigationRequest?` | `{ route, label }` — a **route request**, never an actual navigation; the client executes it via go_router (G9). |

**Structural honesty (AI-0):** no `confidence`, no `tradeOffs`, no
timestamps/expiry, no stable recommendation id on the cards — these are simply
**not modeled today** (never fabricated). The reply carries no DB references
and no provider/model names (C-7/C-8 hold even in the prototype).

### 3.4 Current behavior

The request flow (`engine.py:91-170`):

1. **Empty history** → greeting with no cards (`engine.py:94-98`).
2. **Intent classification** — deterministic regex/keyword router over the last
   user message (`intent.py:65-99`): greeting (≤3 tokens), thanks (≤4 tokens),
   navigation (priority), then grooming/hairstyle/wardrobe/outfit/tip keyword
   sets, short input → `clarify`, else `unknown`.
3. **Occasion detection** — a regex over the occasion vocabulary +
   `work/office/meeting/interview` → normalized (`intent.py:102-111`).
4. **Dialogue policy** (`engine.py:109-164`):
   - greeting/thanks/navigate → canned + optional `navigation`;
   - clarify/unknown → help text + the four "what can you do" chips;
   - outfit **without** an occasion → clarification with the 5 occasion chips
     (casual/office/date/party/travel);
   - a bare occasion word (e.g. `date`) → **promoted to an outfit request**
     (`engine.py:105-107`);
   - outfit/hairstyle/grooming/wardrobe with params → tool cards.
5. **Tools** (`tools.py`) — `recommend_outfit` (occasion → `OCCASION_TO_LOOK`,
   else the look using the most owned items), `recommend_hairstyle` (by
   `face.faceShape`), `recommend_grooming` (fixed pair), `wardrobe_summary`
   (counts from context), `daily_tip`. All cards are drawn from the static
   `catalog.py` — **no DB, no AI provider**.
6. **Optional LLM text enrichment** (`engine.py:166-168`) — if Ollama is
   available, `llm_backend.enrich_reply` rewrites only `reply.text` from a
   context summary (`_context_summary`, `engine.py:37-51`); any failure returns
   the base text. The structured shape never changes.
7. **Return** — bare `AssistantReply` (200).

**The client half** (`assistant_service.dart`):

- Holds `_messages` in memory (`AssistantMessage` list); `clear()` wipes it on
  exit.
- Sends **the whole non-pending history** plus `_buildContext()` (a live
  snapshot from `LearningRepository` — the on-device `UserModel` blob) on every
  call (`assistant_service.dart:51-83`).
- On `null` from the server (network/timeout/non-200) falls back to
  `OfflineAssistant.replyFor(...)` — the on-device mirror of `engine.py`
  (`offline_assistant.dart`).
- Records **local-only** learning signals: `assistant_message` on send
  (`:55`), `suggestion_opened` when a card is opened (`:91`),
  `assistant_navigation` when a nav request is executed (`:95`) — stored in the
  on-device `UserModel.signals`, **never sent to any backend**.
- `SuggestionCard.action` / `NavigationRequest.route` are mapped to app routes
  by `AssistantRoutes.routeFor` (`assistant_routes.dart:8-28`).

### 3.5 Current limitations

| # | Limitation | Evidence | Resolved by (TARGET) |
| --- | --- | --- | --- |
| L1 | **No auth** — public endpoint, anonymous calls, no user scoping; cannot serve per-user conversations or personalized repository state. | `main.py:23`; `F-5` | §4.3.1 (additive auth once D-AUTH-1) |
| L2 | **No conversation persistence** — history is in-memory client state, cleared on exit; only local signals survive. | `assistant_service.dart:28,98-102`; §3.7/§1.10 | §4.5 (additive, gated on retention) |
| L3 | **Context is client-trusted** — the server uses whatever `UserContext` the client sends (or none); no repository-loaded state, so "personalization" can be stale, spoofed, or absent. | `engine.py:37-51`; `R47` | §4.4.2 (repository-loaded `AssistantUserContext`) |
| L4 | **No typed error contract** — FastAPI default 422 body on malformed input; no `{error:{code,message,details}}`, no 401/404/429; clients cannot switch on stable codes. | `main.py` (no mapper); A3.3/E13.1 | §4.3.3, §7 |
| L5 | **No idempotency / request-id / rate limiting** — no `Idempotency-Key`, no `X-Request-Id`, no 429 guard on a public AI endpoint. | `API_CONTRACT_RULES.md` §11 | §4.3.3 (chat never idempotent by design; request-id + 429 additive) |
| L6 | **Card interactions are client-local only** — `suggestion_opened`/`assistant_navigation` are written to the on-device blob; no server-side learning input exists (the product has no card-feedback endpoint). | `assistant_service.dart:90-96`; `FEEDBACK_LEARNING_API.md` §1.1 | §5.2 (A-2 `POST /v1/assistant/feedback`) |
| L7 | **`preferredOccasions` and most `FaceData` fields are dead on the wire** — accepted, never read by the engine. | `engine.py:37-51`; `tools.py:36` | §4.4.2 (context builder consumes the full DTO) |
| L8 | **Cards carry no stable domain references** — `SuggestionCard` has `kind`/`title`/`items` strings but no stable look code / recommendation id (PR-3), so an `opened` card cannot be traced to a canonical look for learning. | `schemas.py:51-57`; §3.3 | §4.4.1 (stable `Look` codes; `cardId` on feedback) |
| L9 | **Action vocabulary is triplicated** — `assistant_routes.dart`, backend `NAVIGATION_MAP`, and quick-action/stylist configs each hold a copy; drift risk. | `assistant_routes.dart:8`; `engine.py:70-88` | §4.4.3 (single canonical source; server emits only known ids) |
| L10 | **Unbounded, free-form input** — `messages` and `content` have no length/turn caps, no role allow-list beyond convention, no content-safety check. | `schemas.py:41-48` | §5.1 (validation) |
| L11 | **No offline/online parity guarantee** — `offline_assistant.dart` is a hand-maintained third mirror of the looks/rules; it can drift from `catalog.py`. | `offline_assistant.dart:26-33` | §4.3.4 (degrade contract kept; rules single-sourced) |
| L12 | **No conversation-history surface at all** — the chat transcript cannot be listed, resumed, or deleted server-side. | only `assistant_client.dart` POST | §4.5 (additive, gated) |

---

## 4. TARGET API — the production assistant contract

### 4.1 Design intent: preserve the contract, extend the surface

The TARGET has one non-negotiable anchor: **the live contract is frozen
(A3.1/F-13) and the product's only real AI pipeline stays untouched in shape.**
Everything else the production assistant needs is added *around* that shape:

| Layer | Today (CURRENT) | Target (TARGET) | Change type |
| --- | --- | --- | --- |
| Chat wire DTOs | `AssistantRequest`/`AssistantReply` | **identical** | none (frozen) |
| Chat endpoint | `POST /v1/assistant/chat` public | **same path/method**; gains auth (additive) + typed errors | behavior-only |
| Context source | client-sent `UserContext` snapshot | repository-loaded `AssistantUserContext` (wire `user` stays frozen) | engine input (server-side) |
| Card feedback | client-local signals only | `POST /v1/assistant/feedback` → backend signal (UC-23) | new endpoint (inventoried 17) |
| Conversation history | none | additive `GET/DELETE /v1/assistant/conversations*` | **gated** on retention decision |
| Errors | FastAPI default | frozen `{error:{code,message,details}}` (A3.3) | contract semantics |

**Two rules follow from F-13 and shape every TARGET decision:**

- **Never add fields to the frozen DTOs.** Conversation resumption/association,
  request correlation, etc. ride **new endpoints or additive headers**
  (`X-Conversation-Id`, `X-Request-Id`) — never new keys in `AssistantRequest`/
  `AssistantReply`.
- **Never remove/renamed anything live.** `GET /health` stays versionless;
  `POST /v1/assistant/chat` works verbatim at every migration step (19 tests
  stay green).

### 4.2 Operation selection

The production assistant surface owns exactly **two inventoried operations**
(16/17) plus an **additive, gated history family**. Every operation is grounded
in an accepted use case / inventory row:

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| A-1 | **Send assistant message** | **Required — live** — `POST /v1/assistant/chat` | UC-22, endpoint 16, action 25. The frozen live contract; behavior-only additions (auth, typed errors, server-loaded context). §5.1. |
| A-2 | **Submit assistant card feedback** | **Required** — `POST /v1/assistant/feedback` | UC-23, endpoint 17, actions 26/27. The **only client-facing signal input** (M10 sole writer, PR-7). §5.2. |
| A-3 | **List conversations** | **Additive — gated** — `GET /v1/assistant/conversations` | Conversation history only if the retention decision lands (G6/G7, §1.10). §5.3. |
| A-4 | **Get conversation transcript** | **Additive — gated** — `GET /v1/assistant/conversations/{conversation_id}` | Same gate; the retained message shape (G7) built from the frozen DTO content. §5.4. |
| A-5 | **Delete a conversation** | **Additive — gated** — `DELETE /v1/assistant/conversations/{conversation_id}` | Same gate; current-state conversation removal (retention windows config-driven). §5.5. |
| — | **Signal-submit endpoint** | **NOT defined** | M10 is the sole writer (PR-7); the client never names a `signal_type` (`FEEDBACK_LEARNING_API.md` §3). |
| — | **Direct preference / profile writes via the assistant** | **NOT defined** | Preferences/profile are owned by M2 (`PROFILE_ONBOARDING_API.md`); the assistant only *reads* them through context. |
| — | **Media in assistant replies** | **NOT defined** | Cards are text/DTO; image/media travel via `MediaRef` on knowledge/saved-look surfaces (M16 sealed, MS10.3) — not through the frozen reply. |

### 4.3 Shared semantics (apply to every operation below)

#### 4.3.1 Auth and ownership

- Public **today** (F-5): `POST /v1/assistant/chat` stays unauthenticated until
  D-AUTH-1 lands; auth must **not** be added retroactively without a contract
  decision (API-1 additive-only; `FASTAPI_ARCHITECTURE_V1.md` F-5).
- **Additive auth** (once D-AUTH-1 + `deps.py`): `Authorization: Bearer
  <token>` on all assistant endpoints; `GET /health` stays public. Missing /
  invalid / expired / revoked → `401 AUTHENTICATION_ERROR` +
  `WWW-Authenticate` (`API_LAYER_ARCHITECTURE.md` §4.2).
- **Owner-scoping (OW-1, API-10):** every user-owned resource the assistant
  touches is resolved under the authenticated `user_id` — a foreign or
  non-existent `conversation_id` returns **404-not-403** (no existence leak).
- **Identity = user_id only (F-3):** the assistant endpoints carry no email/
  name/token in bodies; the domain sees only `user_id` (`AUTH_AUTHORIZATION_
  ARCHITECTURE.md` §4.3).
- **Path-collision guard:** `/v1/assistant/feedback` and the additive
  `/v1/assistant/conversations*` register alongside `/v1/assistant/chat`
  under the assistant module (M4) — no shadowing (`API_CONTRACT_RULES.md` §7).

#### 4.3.2 Context loading (R47)

- The **wire `user` field stays frozen** (F-13) and remains the anonymous /
  offline path: if present it is still a valid snapshot.
- In the **authenticated production path**, the chat use case loads
  `AssistantUserContext` from repositories (wardrobe, style profile, saved
  looks, preferred occasions) through the module ports (`BACKEND_ARCHITECTURE_
  RULES.md` §6.1; `DECISION_ENGINE_ARCHITECTURE.md` Stage 1 Context Builder).
- **Precedence** when both a client `user` snapshot and server state exist is a
  recorded open decision (§8.5) — the default design is **server state wins,
  `user` ignored when a valid token is present** (the server is the source of
  truth; the frozen field exists for backward compatibility and anonymous
  mode). Never merge into a hybrid truth.
- Context is **never persisted with the message** (R47: snapshot per request,
  never stored) — except the ephemeral `_context_summary` string the
  enrichment provider sees server-side, which never leaves the server (C-8).

#### 4.3.3 Errors, idempotency, correlation

- **Typed error contract (A3.3/E13.1):** assistant endpoints return the frozen
  `{ error: { code, message, details? } }` body with the 12-category taxonomy
  (`ERROR_HANDLING.md` §5): `VALIDATION_ERROR` 422, `AUTHENTICATION_ERROR`
  401, `NOT_FOUND` 404, `RATE_LIMITED` 429. `details` is allow-listed only —
  field names, allowed values, `request_id`; never SQL, stack traces, tokens,
  user text, or provider names (ER-0/ER-1).
- **Idempotency:** `POST /v1/assistant/chat` is **never** idempotent (each call
  is a new exchange, §11); A-2 is **not** keyed (each interaction appends a
  signal row, `FEEDBACK_LEARNING_API.md` §8.4); reads (A-3/A-4) are naturally
  idempotent; A-5 DELETE is naturally idempotent.
- **Correlation:** every response carries `X-Request-Id` (echoed from the
  request when present) — a request-id, never user data (`API_LAYER_
  ARCHITECTURE.md` §3; `OBSERVABILITY.md`).
- **Rate limiting:** the public chat endpoint is a prime 429 candidate once
  infrastructure exists; `Retry-After` in `details` (`ERROR_HANDLING.md` §5.5).

#### 4.3.4 Offline / degraded behavior contract

- The **client offline fallback is a feature, not an error**: a network
  failure or timeout → `OfflineAssistant` — the user keeps a functional
  assistant with zero network (critical for low-end devices). This is **not**
  a surfaced error (UC-22: "backend-unreachable → client offline fallback").
- The server keeps its degrade-safe design: LLM enrichment failure returns the
  rules text (BA-8). A degraded enrichment surfaces as `details.degraded:
  true` on 200 (boolean only — never the internal fallback path, C-8).
- Offline parity is a **rules-single-source** concern: the on-device mirror and
  the server engine draw from the same knowledge (K9.1); see §8.6.

### 4.4 Structured domain grounding without database internals

The TARGET guarantees that the assistant "uses structured domain data without
exposing database implementation details" (C-7/C-8/ER-0):

#### 4.4.1 Cards and domain references

- `SuggestionCard` stays the frozen 6-field shape; its `kind` is a typed
  surface (`outfit`/`hairstyle`/`grooming`/`wardrobe`/`tip`) and its content is
  a **DTO projection**, never a row.
- **Stable codes instead of DB ids (PR-3):** wherever a card points at a
  canonical object it references the **`Look` catalog code** (E5, K9.1) — the
  same stable code the knowledge endpoints serve — never a numeric/table key.
  Today the catalog cards are title-keyed (`catalog.py`); the TARGET requires
  the engine to carry the stable `code` internally and, for **card feedback**
  (A-2), surface it as the optional `cardId` (L8).
- No table names, column names, ORM types, or schema shapes on the wire (F-6).

#### 4.4.2 Context as a derived domain DTO

- `AssistantUserContext` (R47) is the **domain contract for what the assistant
  knows**: wardrobe items (E2), face/style profile (E1.1), saved looks (E4),
  preferred occasions (preference). These are domain entities/value objects —
  loaded through repository ports, never constructed from SQL in a router.
- The server-side context builder consumes the **full** DTO (resolving L7):
  `faceShape` drives hairstyle, `styleType`/`preferredOccasions` seed outfit
  context, `savedLooks`/`wardrobe` ground tips — all through the accepted
  domain rules (`DECISION_ENGINE_ARCHITECTURE.md` Stage 1–4).
- The wire `user` object is the **serialization of that same domain DTO** — so
  the client and server speak one domain vocabulary, and the frozen wire
  remains an honest projection of the domain.

#### 4.4.3 Assistant actions — one controlled vocabulary

- `SuggestionCard.action` and `NavigationRequest.route` are **controlled action
  ids** from the 16-id vocabulary (`open_outfit`, `open_hairstyle`,
  `open_grooming`, `open_wardrobe`, `open_stylist`, `open_daily`,
  `open_discover`, `home`, `profile`, `daily-outfit`, `hairstyle`, `grooming`,
  `build-outfit`, `wardrobe`, `stylist`, `discover`) — the **client executes**,
  the AI never navigates (G9).
- The TARGET requires **one canonical source** for the action→route map
  (resolving L9): the server emits only ids in the vocabulary; the client maps
  id→route in one place; quick-action/stylist configs reference the same ids.
  The exact home (knowledge config vs shared constant) is K9.1-scoped (§8.6).
- Executing an action emits the historical signals (`suggestion_opened` via
  A-2 opened, `assistant_navigation` via A-2 navigated — G10), keeping the
  "action" concept configuration-only and the learning trace append-only.

### 4.5 Conversations, messages, and conversation history (additive, gated)

The conversation itself is **transient by default**; persistence is an
**undecided privacy/product choice** (§1.10, G6/G7). The TARGET therefore
defines the *shape* the history surface would take **if the retention decision
lands** — it is additive (not in the accepted inventory) and **not mounted**
until then (API-12). No fake 200.

- **Conversation = user-owned, message-ordered transcript (G6/G7).** If
  retained: `Conversation { conversationId, userId (server-side), startedAt,
  updatedAt, messages[] }`; each retained message is built **from the frozen
  `AssistantMessage` DTO content** (`role`, `content`, `cards`,
  `clarifications`, `navigation`, plus `createdAt`) — the DTO is **not**
  promoted to an entity, it becomes the serialized content of a historical
  record (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.8 note). Storage decision
  (JSONB row set vs table) is resolved with the retention decision before M3
  (`FASTAPI_ARCHITECTURE_V1.md` F-3).
- **Association on chat:** `POST /v1/assistant/chat` stays stateless on the
  wire (frozen). If retention lands, the client associates turns with an
  **additive `X-Conversation-Id` header** (a header — not a DTO field, honoring
  F-13); the server creates a conversation on first use. This is the
  recommended mechanism; alternative designs are §8.3.
- **Reading/writing history:** A-3 (list), A-4 (transcript), A-5 (delete) —
  all auth + owner (OW-1, 404-not-403), all naturally idempotent, all gated.
  There is **no server-side edit/append endpoint** — messages are append-only
  within a retained conversation, and only whole-conversation deletion exists
  (current-state removal; retention windows config-driven).
- **Erasure (TRX-8):** account deletion cascades conversations server-side;
  the API exposes only the user's own path (`AUTH_API.md`; `AUTH_AUTHORIZATION_
  ARCHITECTURE.md` §5 — `conversations.user_id`).
- **Signals survive regardless.** Even with transient conversations (the
  default), `assistant_message`, `suggestion_opened`, and `assistant_navigation`
  persist as append-only history (BC-41) — conversation deletion never deletes
  signals.

---

## 5. Operation contracts

Each operation follows the sibling convention: method/path, request schema,
response schema, validation, authorization, errors, security, side effects,
domain entities, plus status flags.

### 5.1 A-1 — Send assistant message (`SendAssistantMessage`, UC-22, endpoint 16 — **live, frozen**)

- **Method / path:** `POST /v1/assistant/chat`
- **Status:** **LIVE today** (A3.1). Wire DTOs frozen (F-13). Behavior-only
  TARGET additions listed below are **not yet mounted** and gate on D-AUTH-1 /
  M2 / M4.
- **Request schema** (`AssistantRequest`, frozen §13.4):

```
{ "messages": [ { "role": "user", "content": "…" } ],
  "user": { "wardrobe": [ WardrobeItem ], "face": FaceData?,
            "savedLooks": string[], "preferredOccasions": string[] } }   // user optional
```

- **Response schema:** `200 OK` — bare `AssistantReply` (§13.4, frozen):
  `{ intent, text, cards: SuggestionCard[], clarifications:
  ClarificationOption[], navigation?: NavigationRequest }`. No envelope.
- **Validation (TARGET):** `messages` non-empty; `role` ∈ {`user`,
  `assistant`}; `content` bounded (e.g. ≤ 2000 chars) and ≤ a turn cap (e.g.
  50 turns) → `422 VALIDATION_ERROR` with `details.field`/`details.allowed`;
  when `user` is present its vocabulary fields (category/color/occasion codes,
  face shape) validate against K9.1 → `422` (API-14). These are additive
  server-side guards — they never change the DTO shape.
- **Authorization:** public **today** (F-5). Additive: `Bearer` →
  `user_id` once D-AUTH-1; missing/invalid → `401`.
- **Errors (TARGET):** `200`; `422 VALIDATION_ERROR`; `401 AUTHENTICATION_
  ERROR` (when auth lands); `429 RATE_LIMITED`; network failure → **client
  offline fallback, not an error**.
- **Idempotency:** **never** (each call = a new exchange; API-33).
- **Security considerations:** no internals (no prompts, provider/model names,
  or raw model output — C-8); degraded enrichment → `details.degraded: true`
  boolean only; user text/context never echoed in errors or logs (ER-0);
  `X-Request-Id` correlation.
- **Side effects (TARGET):** **non-transactional** today (UC-22). Once
  persistence lands: the backend writes the `assistant_message` signal via the
  M10 seam (PR-7 — **replacing** today's client-local `recordSignal`
  (`assistant_service.dart:55`)); if retention lands, append to the
  `X-Conversation-Id` conversation (§4.5).
- **Domain entities:** E2 `WardrobeItem`, E1.1 `StyleProfile/FaceProfile`,
  E4 `SavedLook`, E5 `Look` (via tools/knowledge), E7 `LearningSignal`
  (`assistant_message`), Assistant Action config (G8–G10).
- **Priority:** P0 (live).

### 5.2 A-2 — Submit assistant card feedback (`SubmitAssistantCardFeedback`, UC-23, endpoint 17)

- **Method / path:** `POST /v1/assistant/feedback`
- **Status:** **inventoried, NOT mounted** (module P0; signal persistence P1).
  Registers alongside `/v1/assistant/chat` under M4 (path-collision guard, §7).
- **Request schema** (`AssistantCardFeedback`, §4.4 of `FEEDBACK_LEARNING_API`):

```
{ "cardId": "look_suggestion_04",    // optional — the suggestion card's stable code/title
  "interactionType": "opened" }      // required — "opened" | "navigated"
```

- **Response schema:** `204 No Content`.
- **Validation:** `interactionType` ∈ {`opened`, `navigated`} → `422`; `cardId`
  bounded (≤ 200). **Existence/ownership of a card is not required** — cards
  are ephemeral suggestions; the reference is the interaction's own content.
- **Authorization:** **auth** (Bearer); **owner** (OW-1) — always the caller's
  own interaction. `401` when unauthenticated.
- **Errors:** `204`; `401`; `422 VALIDATION_ERROR`; `429 RATE_LIMITED`.
- **Idempotency:** **not keyed** — each interaction appends a signal row;
  a retry appends another evidence row (recorded, §8.4 of
  `FEEDBACK_LEARNING_API`).
- **Security considerations:** the only client-facing signal input (PR-7) —
  the client **never names a `signal_type`**; the backend maps the interaction
  to the signal. No internals; the reference is the caller's own content.
- **Side effects:** single **append-only INSERT `learning_signals`** (tier 1,
  UC-23 canonical): `opened` → `suggestion_opened` (action #26), `navigated` →
  `assistant_navigation` (action #27); `label` = the card reference. **P0/P1**:
  module P0, persistence P1.
- **Personalization effect:** opened/navigated patterns tune the assistant's
  future suggestions via Context Builder on the **next** run — never a
  single-event flip (Stage 8 Feedback, R-A16).
- **Domain entities:** E7 `LearningSignal` (via M10 seam).
- **Priority:** P0/P1.

### 5.3 A-3 — List conversations (`ListConversations`, **additive — gated**)

- **Method / path:** `GET /v1/assistant/conversations`
- **Status:** **additive** (not in the accepted inventory) and **gated** on the
  conversation-retention decision (G6/G7). **NOT mounted**; no fake 200.
- **Request schema:** `?page=&page_size=&sort=updated_at` (list envelope
  conventions, API-18/20/22).
- **Response schema:** `200 OK` — `ConversationList` envelope `{ items:
  ConversationSummary[], page, page_size, total }`; `ConversationSummary {
  conversationId, startedAt, updatedAt, messageCount }` — **no message preview**
  (avoid leaking user content in a list).
- **Validation:** pagination bounds (API-22); `sort` ∈ allowed keys.
- **Authorization:** **auth**; **owner** (OW-1) — always the caller's own
  conversations; `401`; `429`.
- **Errors:** `200`; `401`; `429`. (Empty list is `200` with `total: 0` — not
  an error.)
- **Security considerations:** per-user rows only; no other user's data.
- **Side effects:** none (read).
- **Domain entities:** Conversation (G6, user-owned, only if retained) —
  no entity today (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.7).
- **Priority:** n/a (open — lands only with the retention decision).

### 5.4 A-4 — Get conversation transcript (`GetConversation`, **additive — gated**)

- **Method / path:** `GET /v1/assistant/conversations/{conversation_id}`
- **Status:** **additive — gated** (as A-3). **NOT mounted.**
- **Request schema:** none (path id only).
- **Response schema:** `200 OK` — `Conversation { conversationId, startedAt,
  updatedAt, messages: RetainedMessage[] }`; `RetainedMessage { role, content,
  cards, clarifications, navigation, createdAt }` — **the frozen
  `AssistantMessage` DTO content** (G7: the historical record is built from the
  DTO's content, not a new entity).
- **Validation:** `conversation_id` format (UUID); existence/ownership.
- **Authorization:** **auth**; **owner** (OW-1) — a foreign/non-existent id →
  **404-not-403** (no existence leak, API-10).
- **Errors:** `200`; `401`; `404 NOT_FOUND`; `429`.
- **Security considerations:** message content is user/assistant authored —
  served only to the owner; never logged (ER-0).
- **Side effects:** none (read).
- **Domain entities:** Conversation + retained messages (G6/G7, conditional).
- **Priority:** n/a (open).

### 5.5 A-5 — Delete a conversation (`DeleteConversation`, **additive — gated**)

- **Method / path:** `DELETE /v1/assistant/conversations/{conversation_id}`
- **Status:** **additive — gated** (as A-3). **NOT mounted.**
- **Request schema:** none.
- **Response schema:** `204 No Content`.
- **Validation:** `conversation_id` format; existence/ownership.
- **Authorization:** **auth**; **owner** (OW-1); foreign/non-existent →
  **404-not-403**.
- **Errors:** `204`; `401`; `404`; `429`.
- **Idempotency:** naturally idempotent (delete-only; no archive column —
  current-state removal).
- **Security considerations:** deletion removes the conversation **only**; the
  `assistant_message`/`suggestion_opened`/`assistant_navigation` signals
  **survive** (BC-41 — no FK from signals to the conversation); account erasure
  (TRX-8) is the only cascade.
- **Side effects:** remove the user's conversation record; retention windows
  (config-driven) decide background pruning of older transcripts.
- **Domain entities:** Conversation (G6, conditional).
- **Priority:** n/a (open).

---

## 6. Validation reference

- **CURRENT (verified against the real repo):** `main.py` exposes exactly
  `GET /health` + `POST /v1/assistant/chat`; `schemas.py` DTOs mirror
  `models.dart` field-for-field (A3.1); `engine.py`/`intent.py`/`tools.py`/
  `catalog.py` implement the 10-intent dialogue policy; `llm_backend.py`
  degrades to rules; `assistant_service.dart` holds history, builds R47
  context, records the three signals locally, falls back to
  `offline_assistant.dart`.
- **TARGET A-1/A-2 trace 1:1 to accepted inventory** — A-1→16/UC-22,
  A-2→17/UC-23; paths/methods/auth/UC/errors identical to `API_CONTRACT_RULES`
  §12.4 and `API_INVENTORY` §5.5; no invented endpoints. A-3/A-4/A-5 are
  **explicitly additive + gated** (documented §3/§4.5/§8.3), following the
  same honesty pattern as WARDROBE W-2 / DAILY_OUTFIT_EVENTS E-3.
- **Wire shapes are the frozen shapes** — `AssistantRequest`/`AssistantReply`
  identical to §13.4; `AssistantCardFeedback` identical to
  `FEEDBACK_LEARNING_API` §5.2/§4.4; retained messages are the frozen
  `AssistantMessage` DTO content (G7). `confidence`/`tradeOffs`/timestamps
  honestly absent (AI-0).
- **Learning contract verified against PR-7/BC-41** — M10 sole writer; no
  signal-submit endpoint; A-2 is the only client-facing signal input;
  interaction→signal mapping (`opened`→`suggestion_opened`,
  `navigated`→`assistant_navigation`) identical to `FEEDBACK_LEARNING_API`
  §5.2.
- **No-internals (C-7/C-8/ER-0) structurally enforced** — DTO-only responses,
  stable `Look` codes (PR-3), action vocabulary config (G9), `details`
  allow-list, `details.degraded` boolean.
- **Frozen live contract (F-13/API-2)** — no field reorder/rename/retype;
  19 pytest cases + assistant widget/service tests stay green through every
  migration step.

---

## 7. Error reference

Frozen 12-category taxonomy (`ERROR_HANDLING.md` §5); one body
`{ error: { code, message, details? } }` (A3.3). Assistant-relevant rows:

| `code` | HTTP | Applies to | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | A-1 (messages/context), A-2 (`interactionType`) | `details.field` / `details.allowed`; never echoes user text |
| `AUTHENTICATION_ERROR` | 401 | A-1 (when auth lands), A-2, A-3/A-4/A-5 | `WWW-Authenticate`; no token in logs |
| `NOT_FOUND` | 404 | A-4/A-5 (foreign/non-existent id) | **404-not-403** (API-10) |
| `RATE_LIMITED` | 429 | all (public chat is prime target) | `Retry-After` in `details` |
| — | 200 | A-1 network failure | **not** an error — client offline fallback |

CURRENT today: only FastAPI default 422; no typed body — documented as L4.

---

## 8. Open decisions

Unchanged decisions carried forward (affect the assistant contract only when
they land):

1. **Auth provider (D-AUTH-1)** — gates A-1 auth + A-2/A-3/A-4/A-5 mounting;
   chat stays public until then (F-5).
2. **Conversation retention (G6/G7, §1.10)** — the gate for A-3/A-4/A-5 and
   the `assistant_messages` storage shape (JSONB vs table; resolved before M3,
   `FASTAPI_ARCHITECTURE_V1.md` F-3).
3. **Conversation association mechanism** — recommended additive
   `X-Conversation-Id` header vs alternative (per-user current conversation;
   a resume endpoint); chosen with #2.
4. **`assistant_message` signal provenance** — confirmed as backend-written via
   the M10 seam once persistence lands (PR-7), replacing today's client-local
   `recordSignal` (`assistant_service.dart:55`).
5. **Context precedence** — server state wins over a client `user` snapshot
   when a valid token is present (default) vs explicit merge; decided at M4.
6. **Canonical action vocabulary source (G9)** — the 16-id action→route map's
   single home (knowledge config K9.1 vs shared constant); resolves L9.
7. **Rules single-sourcing for offline parity (L11)** — one knowledge/rules
   source feeding `catalog.py` and `offline_assistant.dart`.
8. **Rate limiting + request-id infrastructure** — when 429/`X-Request-Id`
   become enforced (not a wire-shape change).
9. **Unchanged project-wide opens** — knowledge shape (K9.1), media privacy
   (MS10.3), feedback design (PR-12), User fields, Today'sLookRecord (P1),
   RecommendationHistory (P3).

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/ASSISTANT_API.md` — a review of
the **CURRENT** assistant API (endpoint/request/response/behavior/limitations,
all verified against the live repo) and the **TARGET** production assistant
contract (A-1 chat live+frozen, A-2 card feedback, A-3/A-4/A-5 conversation
history additive + gated), covering conversations, messages, assistant actions,
context, and conversation history, with structured-domain-grounding semantics
(no DB internals, no AI/provider internals, stable codes, one action
vocabulary, M10 sole writer). **No implementation.**

**Skills used:** repository analysis (live `main.py`, `schemas.py`,
`engine.py`, `intent.py`, `tools.py`, `llm_backend.py`, `catalog.py`,
`models.dart`, `assistant_client.dart`, `offline_assistant.dart`,
`assistant_service.dart`, `assistant_routes.dart`, backend + Flutter tests) +
design-doc synthesis (ACCOUNT_ASSISTANT_DOMAIN_MODEL G6–G10, R47,
STORAGE_INVENTORY §1.10, TABLE_DEFINITIONS signals, UC-22/UC-23, OW-1,
ERROR_HANDLING taxonomy, API_CONTRACT_RULES §12.4/§13.4/§9/§11,
API_INVENTORY 16/17, FEEDBACK_LEARNING_API §5.2) — documentation only.

**Files changed:** `docs/api/ASSISTANT_API.md` (new).

**Validation run:**
- **CURRENT section is a verified snapshot, not a proposal** — every claim
  traced to `main.py:23`, `schemas.py`, `engine.py:91-170`, `intent.py:65`,
  `tools.py:36`, `llm_backend.py`, `assistant_client.dart`,
  `assistant_service.dart:51-96`, `offline_assistant.dart`,
  `assistant_routes.dart:8`.
- **TARGET operations trace 1:1 to accepted inventory** — A-1→16/UC-22,
  A-2→17/UC-23 (paths/methods/auth/UC/errors identical to §12.4 and §5.5); the
  conversation family A-3/A-4/A-5 is **additive + gated**, documented, not
  invented as mounted endpoints (API-2/API-12).
- **Frozen contract preserved** — DTOs identical to §13.4; A-2 shape identical
  to `FEEDBACK_LEARNING_API` §5.2; F-13 honored (no field added to the frozen
  DTOs — conversation association via additive header); 19 pytest cases +
  assistant widget/service tests stay green (no code touched).
- **`git status --short`:** `docs/api/` holds API_CONTRACT_RULES.md +
  API_INVENTORY.md + AUTH_API.md + PROFILE_ONBOARDING_API.md + APPEARANCE_API.md
  + SCAN_API.md + HAIRSTYLE_RECOMMENDATION_API.md + RECOMMENDATION_API.md +
  WARDROBE_API.md + DAILY_OUTFIT_EVENTS_API.md + FEEDBACK_LEARNING_API.md +
  ASSISTANT_API.md (untracked) + CURRENT_STATE.md; no code, directories, or
  files created.

**Remaining:** STEP 6 design continues (assistant contract complete; feedback
+ learning, daily-outfit + events, wardrobe, common-recommendation, scan-system,
hairstyle-recommendation, appearance, profile + auth contracts complete).
A-2 and the gated history family are **not mounted** until D-AUTH-1 / the
retention decision (API-12); no fake 200 before then. Open decisions in §8.
