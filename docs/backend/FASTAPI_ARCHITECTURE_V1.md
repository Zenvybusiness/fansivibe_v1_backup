# Fansivibe — FastAPI Architecture V1 (Consolidated)

> **STEP 5 FINAL REVIEW — consolidated backend architecture.** Cross-checks the
> STEP 5 design documents against STEP 2 (Feature + Data Inventory), STEP 3
> (Domain Model), STEP 4 (PostgreSQL Database Design), and the **real Fansivibe
> repository**, identifies inconsistencies, and consolidates the accepted
> architecture into one reference for **API Contract Design**.
>
> **Scope:** review + consolidation only. **No application code modified, no
> backend changes implemented.**
>
> **Review set (15 documents):**
> `BACKEND_ARCHITECTURE_RULES.md`, `BACKEND_MODULE_MAP.md`,
> `BACKEND_FOLDER_STRUCTURE.md`, **`REPOSITORY_ARCHITECTURE.md` (⚠ not found —
> see Finding F-1)**, `DEPENDENCY_RULES.md`, `APPLICATION_USE_CASES.md`,
> `DECISION_ENGINE_ARCHITECTURE.md`, `AI_INTEGRATION_ARCHITECTURE.md`,
> `KNOWLEDGE_ARCHITECTURE.md`, `API_LAYER_ARCHITECTURE.md`,
> `ERROR_HANDLING.md`, `BACKGROUND_JOB_ARCHITECTURE.md`,
> `AUTH_AUTHORIZATION_ARCHITECTURE.md`, `MEDIA_UPLOAD_ARCHITECTURE.md`,
> `OBSERVABILITY.md`.

---

## 0. Cross-check findings (review output)

Cross-checked against `docs/architecture/` (STEP 2: ACTION_API_INVENTORY
32 actions, FEATURE_INVENTORY, FEATURE_DATA_MATRIX, DATA_MODEL_INVENTORY,
MVP_SCOPE), `docs/architecture/FANSIVIBE_DOMAIN_MODEL_V1.md` (STEP 3:
E1–E10), `docs/database/` (STEP 4: TABLE_DEFINITIONS 14 tables,
TRANSACTION_BOUNDARIES TRX-1…8, DATABASE_DESIGN_RULES PR-1…12,
SECURITY_PRIVACY_DESIGN MS10.3), and the real repo (`backend/app`, `backend/tests`).

### Consistency confirmed (no issue)

| Cross-check | Result |
| --- | --- |
| Layer separation (API→Application→Domain←Infrastructure) | Consistent across all 14 docs; BA-2/BA-3/BA-5 upheld. |
| Dependency direction (DR-0…6, F-1…13) | No domain→FastAPI/SQLAlchemy/HTTP/AI leak in any doc. |
| 33 use cases ↔ 32 ACTION_API actions | Consistent: actions 27 & 4 are carried (UC-22 navigation, UC-5/9 anonymous precondition). |
| Module tables ↔ TABLE_DEFINITIONS (user-owned) | All 14 STEP-4 tables are owned by exactly one module; no user-table orphan. |
| AI status (AI-0 honesty) | NOW = `AIProvider`/`TextEnrichmentProvider` (matches real `llm_backend.py`); face/hair/outfit/image analysis = FUTURE — correct, no overclaim. |
| Assistant DTO freeze (A3.1 KEEP) | `models/schemas.py` → `api/schemas/assistant.py` verbatim; wire shape preserved. |
| Error taxonomy ↔ ERROR_HANDLING | 12 categories consistent across API layer, AI, media, jobs. |
| Transaction boundaries (TRX-1…8) | Referenced consistently in use cases; analysis write-once (TRX-5); AI never in DB transaction (AI-5). |
| Background jobs (BJ-0/BJ-1) | Only face/outfit analysis ASYNC now; sync-by-default; no Celery/Redis. Matches repo (no queue infra). |
| Media (PR-8) | Bytes never in PG/app memory; `media_assets` non-table; M16 sealed until MS10.3. |
| Auth (OW-1) | All 8 required resource examples mapped; 404-not-403; no auth in domain. |
| Observability (ER-4) | Never-log list matches task; allow-list-only detail. |
| Migration (M1–M6) | Maps the 7 real files; 19 tests stay green through M1/M2. |

### Findings (must be addressed)

- **F-1 — Missing deliverable:** `REPOSITORY_ARCHITECTURE.md` is listed in the
  STEP 5 set but **does not exist** in `docs/backend/`. Its content is
  consolidated here (§5) from `BACKEND_FOLDER_STRUCTURE.md` §5.1,
  `DEPENDENCY_RULES.md`, and STEP 4 (PR rules, repository contracts). It is
  **not** an architecture inconsistency — repository contracts are implied
  throughout — but the standalone document was never written.
- **F-2 — Knowledge-table definition gap (STEP 4 ↔ module map):**
  - Module map M5 owns `looks`, `categories`, `colors`, `occasions`,
    `size_categories`; STEP 4 `TABLE_DEFINITIONS.md` §7.2 references
    `wardrobe_categories(code)`, `colors(code)`, `materials(code)`,
    `event_types(code)`, `signal_types(code)`, `subscription_plans(code)`,
    `run_types(code)`, `looks(code)` as FK targets — but **none of these
    knowledge tables are defined as `TABLE:` sections** (only `looks` is,
    line 247).
  - **Naming inconsistency:** module map uses `categories`, DB uses
    `wardrobe_categories`. One canonical name must be chosen.
  - Resolution: **M3 (SQL migrations)** must finalize the knowledge
    vocabulary table set + names per `KNOWLEDGE_ARCHITECTURE.md` §4 (storage
    by lifecycle). Not a blocker for contract design; a blocker for M3.
- **F-3 — R51-note tables undefined:** M1 lists `sessions`/tokens and M4 lists
  `assistant_messages` with "(R51 note)" — neither exists in TABLE_DEFINITIONS.
  This is consistent with the open decisions (auth provider; conversation
  retention) but must be resolved when those decisions land, before M3.
- **F-4 — Cross-module table writes (minor):** M13 `outfits` writes
  `analysis_runs.outfit` (owned by M12) and `saved_looks` (owned by M7). This
  is legal under DR-0 (data path via repositories) but requires the strict
  public-contract discipline of BA-10/DR-4 — enforce at implementation.
- **F-5 — Assistant endpoint unauthenticated:** consistent with "auth not
  implemented" and MVP (single AI service), but the API layer must keep
  `POST /v1/assistant/chat` public until D-AUTH-1 lands; auth MUST NOT be
  added to it retroactively without a contract decision (API-1 additive-only).

### Over-engineering audit (none found)

- No Celery/Redis/queue/worker (BJ-1); no external tracing system (request-ID
  correlation only); no repository abstraction layer beyond what data
  boundaries need (BA-10); no empty layers; no module without a product/
  domain basis (BMM-0); media sealed until its gate; AI FUTURE capabilities
  explicitly not implemented. **No unnecessary modules** — all 16 + ai_engine
  map to STEP 2/3 entities or cross-cutting seams.

### Security-boundary audit (complete)

- Auth boundary (D-AUTH-1 seam, 401/403/404 semantics, OW-1 on all 8 resource
  examples, admin/system principal separation, no token logging) — **complete**.
- Media privacy (MS10.3, private-by-default, signed URLs, erasure) — **complete**.
- Error leak prevention (ER-0…3), observability never-log (ER-4) — **complete**.

---

## 1. Architecture overview

Modular **monolith**, four layers:
`api` → `application` → `domain` ← `infrastructure` (BA-2).

- **Domain** — pure Python, no framework/AI/DB imports (BA-3): intent, tools,
  dialogue, generation/scoring rules, value objects. This is what
  `backend/app/ai/` already implements and moves to `domain/services/`.
- **Application** — the 33 use cases (UC-1…33); orchestration, no business
  rules in widgets/HTTP; the **only** place that maps requests → domain
  behavior (BA-7).
- **API** — FastAPI routers + `deps.py` (auth/current-user), DTO schemas
  (`api/schemas/`), single error mapper. Screens/Flutter never call AI
  providers directly — only this service (frozen A3.1 mirror).
- **Infrastructure** — adapters behind ports: `db/`, `external/ai.py`
  (`llm_backend.py` seam), `external/knowledge.py`, `auth/`, `storage/`
  (future), `jobs.py`, `events.py` (BA-6 external-by-port).

Key invariants: **K9.1/BA-11** one knowledge source; **BAR-0** backend
represents the domain model, not the Flutter UI; **AI-5** AI never inside a
DB transaction; **PR-8** no bytes in PG; **OW-1** every user resource
owner-scoped.

---

## 2. Module map

16 modules + `ai_engine` (domain-only) + `media` (sealed). Selected by
**BMM-0** (module exists only if product + domain model support it).

| Mod | Name | P0/P1/P2 | Owned tables | Notes |
| --- | --- | --- | --- | --- |
| M1 | `auth` | P0 | `users` (row), `sessions` (R51 note) | seam `verify_access_token→Principal`; D-AUTH-1 open |
| M2 | `users` | P0 | `users`, `user_state` | E1 |
| M3 | `wardrobe` | P0 | `wardrobe_items`, `items` (ref) | E2 |
| M4 | `assistant` | P0 | `assistant_messages` (R51 note) | A3.1 DTOs |
| M5 | `knowledge` | P0→P2 | `looks`, vocab (F-2) | K9.1 single source |
| M6 | `ai_engine` | P0 | (none) | domain-only |
| M7 | `saved_looks` | P1 | `saved_looks` | E4 |
| M8 | `events` | P1 | `user_events` | E3 |
| M9 | `daily_outfit` | P1 | `today_look_records` (cond.) | derived |
| M10 | `learning` | P1 | `learning_signals`, `style_score_records`, `activity_days` | E7/E8/E9 |
| M11 | `feedback` | P1 (gated) | `feedback_events` | feature-gated |
| M12 | `analysis` | P2 | `analysis_runs` | E6; ASYNC |
| M13 | `outfits` | P2 | `analysis_runs.outfit`, `saved_looks` (F-4) | value object |
| M14 | `discover` | P2 | `looks`, `categories` (read) | feed |
| M15 | `subscriptions` | P2 | `subscriptions` | E10 |
| M16 | `media` | P2 (sealed) | MediaRef columns, ObjectStorage port | MS10.3 gate |

---

## 3. Folder structure

Target tree (from `BACKEND_FOLDER_STRUCTURE.md` §5):

```
backend/
  app/
    config/          settings + config (inside layers, not a peer — §5.1)
    api/             deps.py, schemas/ (assistant.py = A3.1 KEEP), routers/
    application/     use_cases/ (UC-1…33 files match module map)
    domain/          services/ (engine, intent, tools, decision_engine),
                     entities/ (STEP 3 derived), value_objects/
    infrastructure/
      db/            repositories + session
      external/      ai.py (llm_backend seam), knowledge.py (catalog seed)
      auth/          provider adapter
      storage/       object storage adapter (M16)
      jobs.py        in-process async runner
      events.py      domain events
  tests/             unit/ (19 tests move unchanged)
```

Import matrix and module↔folder map M1–M16 are in `BACKEND_FOLDER_STRUCTURE.md`
§4/§6. **Current→target migration** is listed in §19 here and §7 of that doc.

---

## 4. Dependency direction

- **DR-0…6:** API→Application→Domain; Infrastructure implements Domain ports;
  AI adapters→AI interfaces; Knowledge adapters→Knowledge interfaces;
  repositories are the only data path (DR-10/BA-10).
- **Forbidden (F-1…F-13), merge-blocking:** Domain↛FastAPI/SQLAlchemy/HTTP/
  config; UI concepts↛domain; DB models↛API contracts; AI provider leakage;
  frozen assistant DTOs must not be re-shaped.
- **Enforcement:** import-linter (locks DR/F), composition-root-only DI,
  a frozen-contract test guarding the A3.1 DTOs. All 14 docs are consistent
  with these rules (no violations found in cross-check).

---

## 5. Repository architecture

> **F-1:** `REPOSITORY_ARCHITECTURE.md` was never created. This section
> consolidates the repository contract implied by the accepted docs.

- **Purpose (BA-10):** repositories are the **only data access path** for
  application/domain. They wrap SQLAlchemy sessions + row↔domain mapping;
  no ORM types escape into domain (F-3).
- **Contract per aggregate:** e.g. `WardrobeItemRepository.save/get/get_by_owner/
  delete` — every user query carries `user_id` (OW-1 → 404-not-403).
- **Write-once guard (TRX-5):** analysis completion uses a guarded
  `UPDATE … WHERE status='pending'`; repositories expose it.
- **No repository for knowledge reads** — knowledge is read via the
  `KnowledgeSource` port (KN-1) from `infrastructure/external/knowledge.py`,
  seeded from `catalog.py`; knowledge writes happen only on seed/version bump.
- **Transactions:** repositories participate in the unit-of-work of the
  surrounding use case (TRX-1…8); AI calls and object-storage writes are
  **outside** the DB transaction (AI-5, TRX-1 §5).
- **Retention/pruning** and **orphan sweep** run as jobs using the same
  repositories (job architecture §5).

---

## 6. Application use cases

33 use cases (UC-1…33), each with the 9 required fields (id, module,
use-case name, action/trigger, input, domain steps, writes, errors, priority).
All 32 ACTION_API actions covered (actions 27, 4 carried). Files named after
the module map. P0 = UC-1…14 (plus assistant UC-22), P1 = UC-15…21 + 23/30/31,
P2 = remainder. Transaction boundaries cited per use case (TRX-1…8).

---

## 7. Decision Engine

Thin orchestrator + stateless stages:
**Context Builder → Candidate Generation → Filtering → Scoring → Ranking →
Explanation → Recommendation → Feedback** (`DECISION_ENGINE_ARCHITECTURE.md`).

- **DE-0:** rules-only mode always works; AI enrichment additive.
- 10 context inputs; decomposition into `domain/services/` files; explanation
  cites the rule version (KN-1 versioning).
- **Today:** rules-only (engine tools). **FUTURE:** `RecommendationProvider`
  AI candidates. Recommendation generation stays **SYNC** (BJ-0).

---

## 8. AI integration

7-concern separation; **AI-0 honesty**:

| Capability | Status |
| --- | --- |
| `AIProvider` (model backend) | **NOW** (Ollama, optional, degrades) |
| `TextEnrichmentProvider` | **NOW** |
| `RecommendationProvider` | rules NOW, AI FUTURE |
| `FaceAnalysisProvider` / `HairAnalysisProvider` / `OutfitAnalysisProvider` / `ImageAnalysisProvider` | **FUTURE** |

Common `CapabilityResult` envelope (input/output shapes, confidence,
model_version, timeout, failure mode, retry, logging). Timeouts 20–30s,
retry 1x. **AI never in a DB transaction (AI-5).** Async runs (analysis)
use the job pattern (TRX-5). Matches the real repo: only `llm_backend.py`
exists; no analysis code.

---

## 9. Knowledge integration

One knowledge source (**K9.1/BA-11**), system-owned, no `user_id` on
knowledge rows (**KN-0**). **KN-1 storage by lifecycle:** static/versioned/
file-backed rules (style, color, face guidance, occasion→look map) vs
DB-backed+versioned content rows (`looks`, item catalog, hairstyle/grooming).
Three-way versioning (schema / knowledge / engine). Knowledge never deleted
(TRX-8). `catalog.py` becomes the seed file for
`infrastructure/external/knowledge.py`. **F-2** gap: vocabulary table set
must be finalized at M3.

---

## 10. API architecture

Conventions API-1…44: `/v1` path versioning, additive-only; Bearer via
`deps.py` → `user_id`; **404-not-403** (API-10); no envelope for single
resources (assistant unchanged), list envelope `{items,page,page_size,total}`;
typed errors `{error:{code,message,details}}`; `202 + run_id` polling for
analysis (API-41); `Idempotency-Key` for saves/sync; multipart
upload-then-insert (API-44). Live `POST /v1/assistant/chat` preserved as-is.

---

## 11. Error handling

Exactly **12 categories** (VALIDATION_ERROR, AUTHENTICATION_ERROR,
AUTHORIZATION_ERROR, NOT_FOUND, CONFLICT, RATE_LIMITED, AI_FAILURE,
MEDIA_FAILURE, DATABASE_FAILURE, EXTERNAL_SERVICE_FAILURE,
PROCESSING_FAILURE, INSUFFICIENT_USER_DATA) with 6 fields each (internal
exception, domain error, application error, API response, HTTP status, safe
client message + logging). Leak prevention ER-0…3 (allow-listed details,
never stack/SQL/token/content). Taxonomy frozen once shipped. Mapper in
`api/errors.py`.

---

## 12. Background jobs

**SYNC** (recommendation, daily outfit, event) vs **ASYNC** (face/outfit
analysis, generated images FUTURE) vs **OPTIONAL ASYNC** (wardrobe image
processing, large media — M16-gated). Job = DB row (`analysis_runs`),
status row-derived, write-once (TRX-5), retry 1x transient-only, timeouts
per capability, safe failure codes, result persisted once. **In-process
runner only; no Celery/Redis/queue** (BJ-1).

---

## 13. Authentication / authorization

- **Auth provider:** external/delegated behind `verify_access_token→Principal`
  seam (`infrastructure/auth/`); D-AUTH-1 open; backend never stores passwords
  or refresh secrets.
- **Token validation:** Bearer in `deps.py`: format, revocation, expiry/
  audience → 401 + `WWW-Authenticate`; no token logging.
- **Identity:** `users.user_id` only into domain (F-3); FK on user tables.
- **Current user:** `get_current_user_id` per-request, threaded through
  application→domain.
- **Authorization:** identity/scope (401/403) + ownership (**404-not-403**).
  403 reserved for authenticated-but-disallowed (admin path from user token).
- **OW-1:** all 8 examples scoped (wardrobe, scans, photos, recommendations,
  saved looks, feedback, events, conversations).
- **Admin/system:** separate principal, `require_admin`, service principal for
  workers, default closed, audited.

---

## 14. Media architecture

No app-memory proxy (**PR-8**): Flutter → `POST /v1/media/uploads` → signed
PUT → object storage → `POST /complete` (HEAD/size/hash verify + MediaRef
insert, TRX-1) → optional async AI → domain result. `media_assets` is a
non-table (MediaRef JSONB). Private-by-default (MS10.3); signed URLs
short-lived, owner-scoped, minted per request, never persisted; public only
for whitelisted generated output. Orphan sweep + erasure jobs. **M16 sealed
until MS10.3; not implemented today.**

---

## 15. Observability

Structured JSON logs, request-ID correlation (= tracing model; no external
system). Events: request, use case (enum), AI op (model_version, shapes,
never content), duration, DB failure (safe code only), external failure,
jobs (job_id/run_id). Levels DEBUG/INFO/WARN/ERROR. **Never logged (ER-4):**
passwords, auth tokens, raw private images, unnecessary sensitive appearance
data — enforced by allow-list-only `detail` (structural, not aspirational).

---

## 16. P0 backend scope (M1–M4 + P0 slice)

Modules **M1–M6** (`auth` seam, `users`, `wardrobe`, `assistant`,
`knowledge` P0 subset, `ai_engine`). Use cases **UC-1…14 + UC-22**. Targets
(`MVP_SCOPE.md` Part 1): sign in → my wardrobe → my assistant; knowledge
vocab P0 subset (categories/colors/occasions/looks) as single source (K9.1);
assistant contract frozen. **P0 slice = `POST /v1/assistant/chat` + wardrobe
CRUD + knowledge endpoints**, behind M1–M3 structure. Auth lands with
D-AUTH-1.

## 17. P1 backend scope

Modules **M7–M11** (`saved_looks`, `events`, `daily_outfit`, `learning`,
`feedback` gated). Use cases **UC-15…21, 23, 30, 31**. Completes primary
journey: save/retrieve looks, events→outfit, today's look (conditional),
style score/streak (derived rows), feedback (feature-gated). Knowledge full
rollout begins.

## 18. P2 backend scope

Modules **M12–M16** (`analysis`, `outfits`, `discover`, `subscriptions`,
`media` sealed). Use cases **UC-24…29, 32, 33**. Async analysis runs
(TRX-5), outfit generation, discover feed, subscriptions (E10), media
pipeline + object storage (after MS10.3). No P3 (RecommendationHistory,
real AI runs) until gates land (M6).

---

## 19. Migration strategy from the current backend

From `BACKEND_ARCHITECTURE_RULES.md` §9, with the 7 real files and 19 tests:

- **M1 — structure-first, no behavior change:** create the folder skeleton
  (`app/{config,api,application,domain,infrastructure}`); move
  `engine.py`/`intent.py`/`tools.py` → `domain/services/`,
  `llm_backend.py` → `infrastructure/external/ai.py`,
  `catalog.py` → `infrastructure/external/knowledge.py`,
  `schemas.py` → `api/schemas/assistant.py` (verbatim A3.1) behind a
  composition root in `main.py`. `POST /v1/assistant/chat` + **19 pytest
  cases stay green.**
- **M2 — typed error contract (non-breaking):** `api/errors.py` mapper,
  exception bases, taxonomy registry (12 categories), allow-listed details,
  logging config (OBSERVABILITY §15), request-id middleware.
- **M3 — PostgreSQL infrastructure:** SQL migrations (Alembic-vs-SQL
  decision); create the 14 STEP-4 tables + **knowledge vocabulary tables
  (resolves F-2/F-3)**; seed knowledge per KN-1 from `catalog.py`; no
  production connection yet.
- **M4 — P0 vertical slice:** UC-1…14 + UC-22 wired; assistant still the
  frozen contract; auth behind D-AUTH-1.
- **M5 — P1 + P2 features** (per MVP_SCOPE Parts 2/3).
- **M6 — P3 / future** (real AI analysis, media, subscription) only when
  their gates land.

---

## Consistency verdict

The architecture is **internally consistent** across all critical seams
(layers, dependency direction, module/table ownership, AI seams, error
taxonomy, job model, security boundaries, media, observability). The
cross-check found **no contradictions, no unnecessary modules, no
dependency violations, no domain/database/AI-provider leakage, no API/domain
coupling, no over-engineering, and no missing security, transaction, or
background-processing boundaries.**

Four catalogued, **non-blocking** items to close during contract/M3 design:
- **F-1** `REPOSITORY_ARCHITECTURE.md` missing → consolidated in §5 here;
  recommend creating the standalone doc to complete the STEP 5 set.
- **F-2** knowledge vocabulary table set + naming (`categories` vs
  `wardrobe_categories`) not defined in STEP 4 → finalize at M3.
- **F-3** `sessions`/`assistant_messages` pending auth + conversation-
  retention decisions → resolve before M3.
- **F-4** cross-module table writes (M13) → enforce public contracts.

---

## STEP 5 COMPLETE — READY FOR API CONTRACT DESIGN
