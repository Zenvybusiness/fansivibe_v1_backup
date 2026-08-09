# Fansivibe — Architecture Gap Report

> Analyzes the REAL Fansivibe architecture against the discovered feature and
> data requirements (all companion docs in this directory).
>
> Identifies gaps in: Flutter data flow, model boundaries, API boundaries,
> repository boundaries, backend services, domain boundaries, persistence
> requirements, AI boundaries, knowledge boundaries, media storage,
> authentication, authorization, and error handling.
>
> **No changes are implemented. The current architecture is not replaced. No
> dependencies are added.** This report classifies findings so the design phase
> can sequence its work. Every claim is verified against source.

---

## Classification legend

| Class | Meaning | When it applies |
| --- | --- | --- |
| **KEEP** | Current approach is sound; retain it | now |
| **CHANGE_LATER** | Needs change, but during/after backend work — not blocking | with or after backend |
| **REQUIRED_BEFORE_BACKEND** | A decision/contract that must exist before the real backend is built, or the backend is built on wrong foundations | before backend |
| **FUTURE** | Beyond near-term; only after the basic product works | later |

---

## Part 1 — Findings by area

### 1. Flutter data flow

| # | Finding | Class |
| --- | --- | --- |
| F1.1 | **Single persistence owner** (`features/learning` owns the only durable store + repository contract) | **KEEP** |
| F1.2 | Screens read static mocks directly; only Wardrobe + Assistant use the repository | CHANGE_LATER |
| F1.3 | Cross-feature data passed via **route extras** (looks, items, events, prefs) instead of shared repositories | CHANGE_LATER |
| F1.4 | `UserSession.hasSavedWardrobeItem` — user flag outside `features/learning`; resets on restart and flips the home onboarding branch | REQUIRED_BEFORE_BACKEND |
| F1.5 | Presentation layer mutates domain directly (WardrobeScreen calls `LearningService.instance.addItem` + `_toEntry` in the screen) | CHANGE_LATER |
| F1.6 | LocalStore degrades to in-memory (tests) and swallows write errors — no failure path to UI | REQUIRED_BEFORE_BACKEND |

### 2. Model boundaries

| # | Finding | Class |
| --- | --- | --- |
| M2.1 | 11 duplicated concept families (wardrobe item ×4, outfit piece ×5, style DNA ×4, today's look ×4, saved look ×3, insight ×3, quick action ×2, match score ×5, stage ×4, occasion vocab ×4, style vocab ×4) — no canonical domain models | REQUIRED_BEFORE_BACKEND (domain-shape decisions) |
| M2.2 | UI-only duplicates (processing stages, quick actions, filter/option vocabularies) work correctly today | KEEP (collapse only when refactor warranted) |
| M2.3 | Dead models `AnalysisResult`/`OnboardingResult` (never referenced) | CHANGE_LATER (delete or promote) |
| M2.4 | `AssistantUserContext` re-shapes domain data (wardrobe/face) inside the assistant feature instead of consuming the contract directly | CHANGE_LATER |
| M2.5 | Persistence↔UI conversion at the boundary (`_toEntry` WardrobeItemData→WardrobeEntry) is the correct pattern; keep it | **KEEP** |

### 3. API boundaries

| # | Finding | Class |
| --- | --- | --- |
| A3.1 | Client DTOs mirror backend schemas **1:1** — the wire contract is a single source of truth | **KEEP** |
| A3.2 | Only one endpoint exists (`POST /v1/assistant/chat`); the other ~8 required operations (auth, wardrobe, events, looks, analysis, generation, sync) have no contract | REQUIRED_BEFORE_BACKEND (contract design; not implementation) |
| A3.3 | No typed error contract; client treats any failure as "unreachable → offline fallback", which hides real errors | REQUIRED_BEFORE_BACKEND |
| A3.4 | No versioning/migration strategy for the DTO contract | FUTURE |

### 4. Repository boundaries

| # | Finding | Class |
| --- | --- | --- |
| R4.1 | Only `LearningRepository`/`LearningService` exists — the app's single data access boundary | **KEEP** (pattern) |
| R4.2 | Other features have **no repository layer**; screens depend on mocks/route-extras, so there is no seam to swap in backend data | REQUIRED_BEFORE_BACKEND (per-feature repositories) |
| R4.3 | The repository returns a mutable aggregate; no query/view models for screens (e.g., profile stats) | CHANGE_LATER |

### 5. Backend services

| # | Finding | Class |
| --- | --- | --- |
| B5.1 | Backend is a single assistant prototype (`engine`/`intent`/`tools`/`llm_backend` + catalog, no DB/auth) | **KEEP** (as prototype) |
| B5.2 | No service boundaries exist for user, wardrobe, events, looks, analysis, generation, media, sync, subscription | FUTURE |
| B5.3 | The assistant rules engine is **duplicated** in `OfflineAssistant` (on-device) and the backend — no shared spec | CHANGE_LATER |

### 6. Domain boundaries

| # | Finding | Class |
| --- | --- | --- |
| D6.1 | Feature-first modular structure is respected; features read mocks, not each other's internals | **KEEP** |
| D6.2 | Ambiguous ownership: `UserEvent` (created in events, only occasion reaches learning), saved looks (3 owners, mock display), vocabularies (4 independent copies) — ownership must be settled to define tables | REQUIRED_BEFORE_BACKEND |
| D6.3 | `FaceProfile`/`setFace` is a dead pipeline (never written) — the face domain boundary is unused | CHANGE_LATER |

### 7. Persistence requirements

| # | Finding | Class |
| --- | --- | --- |
| P7.1 | Single JSON blob (`UserModel`) mixes user data, saved looks, and append-only signals | REQUIRED_BEFORE_BACKEND (split design per STORAGE_INVENTORY) |
| P7.2 | Events are unpersisted (widget state); saved-look full payload missing; score/streak history missing | FUTURE (new entities) |
| P7.3 | No migration path from the `v1` blob to a real DB (no versioning/backfill) | CHANGE_LATER |

### 8. AI boundaries

| # | Finding | Class |
| --- | --- | --- |
| AI8.1 | Only the Assistant is real AI-ish (rules + optional Ollama text enrichment); all other "AI" results are static mocks | **KEEP** (honest; don't pretend otherwise) |
| AI8.2 | No confidence/explanation fields in the contract; scores are static catalog constants | FUTURE (with real models) |
| AI8.3 | Boundary between **knowledge content** (catalog cards) and **AI-generated results** is blurred — the contract serves static catalog items as if AI-produced | CHANGE_LATER |
| AI8.4 | AI input boundary is incomplete: `FaceProfile` never populated; captured images never uploaded | CHANGE_LATER |

### 9. Knowledge boundaries

| # | Finding | Class |
| --- | --- | --- |
| K9.1 | Vocabularies/catalogs duplicated 3–4× across app, offline engine, and backend — **violates "no hardcoded backend-controlled categories"** | REQUIRED_BEFORE_BACKEND (backend becomes single knowledge source; app fetches/caches) |
| K9.2 | The 24-item wardrobe + 5 looks exist in multiple mirrors (`defaultWardrobe`, `WardrobeMockData`, `catalog.WARDROBE`, `_LookCard`) | REQUIRED_BEFORE_BACKEND (part of K9.1) |
| K9.3 | Knowledge content currently hardcoded as code constants, not versioned/config-managed | CHANGE_LATER |

### 10. Media storage

| # | Finding | Class |
| --- | --- | --- |
| MS10.1 | No media pipeline: all images are `FansiImageWell` placeholders; captured images are transient `xFile.path` strings | FUTURE |
| MS10.2 | No image references in persisted models (wardrobe items have no imageUrl) — object-storage model undeveloped | FUTURE |
| MS10.3 | Privacy model for appearance media (face/outfit) undefined (upload, retention, deletion) | REQUIRED_BEFORE_BACKEND (policy decision) |

### 11. Authentication

| # | Finding | Class |
| --- | --- | --- |
| AU11.1 | No auth, no user entity; account creation is a mock that navigates home | REQUIRED_BEFORE_BACKEND (every relational write needs a user id) |
| AU11.2 | No token/session handling, no anonymous→account sync path (the "Save Locally" flow exists but has no merge story) | REQUIRED_BEFORE_BACKEND |

### 12. Authorization

| # | Finding | Class |
| --- | --- | --- |
| AZ12.1 | No authorization model; all data is single-user device-local | **KEEP** (today) |
| AZ12.2 | Multi-device / owner-scoping / sharing rules undefined | FUTURE |
| AZ12.3 | Per-user ownership scoping for future rows (user_id FK / RLS) must be part of the DB design | REQUIRED_BEFORE_BACKEND |

### 13. Error handling

| # | Finding | Class |
| --- | --- | --- |
| E13.1 | No typed error contract; client collapses every failure into "offline fallback" (Assistant) or silence (local writes) | REQUIRED_BEFORE_BACKEND |
| E13.2 | No loading/empty/error/retry states on most screens; `hairstyle-details` renders a blank on missing data | CHANGE_LATER (with backend bindings) |
| E13.3 | Local store errors are swallowed; no user-facing failure path for persistence | REQUIRED_BEFORE_BACKEND |

---

## Part 2 — Significant findings in detail

### F1.4 + D6.2 — Ownership of session flag, events, saved looks

- **Gap:** `UserSession.hasSavedWardrobeItem` lives in `shared/` (resets on
  restart, flips Home's first-visit branch). `UserEvent` is owned by events but
  only the occasion reaches learning. Saved looks are persisted by learning but
  displayed from a mock in profile.
- **Why it matters:** the DB/service design cannot assign tables without these
  ownership answers; the session flag currently produces inconsistent UI across
  launches.
- **Required before backend:** assign ownership (flag → user model; events →
  events feature; saved looks → learning, display = derived). This is a decision,
  not implementation.

### M2.1 + K9.1 — Duplicate concept families and knowledge copies

- **Gap:** 11 concept families are modeled 3–5×; vocabularies/catalog are copied
  across app + offline + backend.
- **Why it matters:** the backend cannot serve one canonical shape while the app
  keeps four; drift already exists (occasion vocabularies disagree across
  events/builder/discover).
- **Required before backend:** pick canonical domain models (the DB candidates
  from DATA_MODEL_INVENTORY §19.3) and make the backend the single knowledge
  source. UI-only duplicates may stay.

### A3.3 + E13.1 — No typed error contract

- **Gap:** the client cannot distinguish auth (401), not-found (404), invalid
  input (422), conflict (409), or service failure (503); every failure is
  "unreachable → offline".
- **Why it matters:** error semantics must exist before endpoints are built, or
  every future endpoint needs retrofitting.
- **Required before backend:** a typed error contract (status + structured body)
  agreed with the client; client maps to the states in
  STATE_EDGE_CASE_INVENTORY.

### R4.2 + F1.2 — No per-feature repository seam

- **Gap:** only learning has a repository; other features read mocks directly,
  so there is no place to inject backend-backed data.
- **Why it matters:** the backend cannot be wired feature-by-feature without a
  data boundary in each feature.
- **Required before backend:** define per-feature repository interfaces (contract
  only) so mocks and backend both implement them.

### AU11.1 — No authentication

- **Gap:** every future relational write is user-scoped (STORAGE_INVENTORY cat
  1), but there is no user entity or token.
- **Why it matters:** the backend's data model (user_id FKs) and endpoint auth
  are prerequisites for everything else.
- **Required before backend:** auth design (register/login/social/anonymous→sync)
  — the product already has the UI flows (AccountCreationScreen) and the sync
  requirement (ACTION_API_INVENTORY #32).

### P7.1 — Single blob mixes categories

- **Gap:** the `UserModel` blob holds user data, saved looks, and append-only
  signals in one JSON blob.
- **Why it matters:** STORAGE_INVENTORY assigns those to different categories
  (relational rows + JSONB + history); the blob must be split in the migration.
- **Required before backend:** agree the split + migration order; not the
  implementation.

### B5.3 — Duplicated assistant engine

- **Gap:** `OfflineAssistant` mirrors `engine.py`/`intent.py`/`tools.py`.
- **Why it matters:** business logic in two codebases with no shared spec drifts
  (already: occasion vocab and navigation targets differ subtly).
- **Change later:** single rule spec (data-driven), or generated source, once
  the backend is real.

---

## Part 3 — Consolidated classification

| Class | Findings |
| --- | --- |
| **KEEP (8)** | F1.1 single persistence owner; M2.5 boundary conversion; M2.2 UI-only dups work; A3.1 mirrored DTO contract; R4.1 repository pattern; B5.1 backend as prototype; D6.1 feature-first structure; AI8.1 honest AI status |
| **REQUIRED_BEFORE_BACKEND (15)** | F1.4 session flag → user model; F1.6 LocalStore failure path; M2.1 canonical domain models; A3.2 API contract design; A3.3 typed errors; R4.2 per-feature repositories; D6.2 ownership decisions; P7.1 blob split; K9.1 backend = knowledge source; MS10.3 media privacy policy; AU11.1 auth; AU11.2 anonymous→sync; AZ12.3 user scoping; E13.1 typed error contract; E13.3 store-failure handling |
| **CHANGE_LATER (12)** | F1.2 screens→repos; F1.3 route extras→repos; F1.5 screen→service decoupling; M2.3 dead models; M2.4 AssistantUserContext; R4.3 view models; B5.3 engine dedup; D6.3 face pipeline; AI8.3 knowledge-vs-AI blur; K9.3 versioned config; P7.3 migration path; E13.2 UI states |
| **FUTURE (7)** | A3.4 contract versioning; B5.2 service boundaries; P7.2 new entities (events/history/saved-look payload); AI8.2 confidence/explanation; MS10.1 media pipeline; MS10.2 image refs/object storage; AZ12.2 multi-device/sharing |

---

## Part 4 — Sequencing guidance (design-phase, not implementation)

1. **Before backend (REQUIRED_BEFORE_BACKEND):** settle ownership (F1.4, D6.2),
   canonical domain models (M2.1), the typed API + error contract (A3.2, A3.3),
   per-feature repository interfaces (R4.2), storage split + media privacy policy
   (P7.1, MS10.3), and the auth + anonymous→sync design (AU11.1, AU11.2,
   AZ12.3). Without these, backend tables/endpoints would be built on the
   duplicated/ambiguous shapes the inventories documented.
2. **With/after backend (CHANGE_LATER):** move screens off mocks/route-extras
   onto repositories (F1.2, F1.3), decouple presentation from services (F1.5),
   delete/promote dead models (M2.3), unify the engine spec (B5.3), revive the
   face pipeline (D6.3), and add screen states with each binding (E13.2).
3. **Later (FUTURE):** media pipeline + object storage (MS10.1, MS10.2), new
   entities (P7.2), real AI confidence/explanation (AI8.2), service boundaries
   (B5.2), multi-device authorization (AZ12.2), contract versioning (A3.4).

## Constraints honored

- Nothing implemented; the current architecture is not replaced; no
  dependencies added; no full-app restructure recommended anywhere.
