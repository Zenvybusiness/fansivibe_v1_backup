# Fansivibe — MVP Scope & Implementation Priority Map

> Final synthesis of all companion inventories (`FEATURE_INVENTORY.md`,
> `SCREEN_DATA_INVENTORY.md`, `DATA_MODEL_INVENTORY.md`, `FEATURE_DATA_MATRIX.md`,
> `DATA_OWNERSHIP.md`, `AI_DATA_FLOW.md`, `STORAGE_INVENTORY.md`,
> `ACTION_API_INVENTORY.md`, `STATE_EDGE_CASE_INVENTORY.md`,
> `UI_UX_GAP_REPORT.md`, `ARCHITECTURE_GAP_REPORT.md`).
>
> Classifies features/data requirements into P0–P3. **Not prioritized by
> technical convenience** — by core value, dependency relationships, user
> journey, architecture validation, required data foundations, existing working
> UI, and the actual current product scope.
>
> **This is a plan only. Nothing is implemented.**

---

## Priority definitions

| Priority | Meaning |
| --- | --- |
| **P0** | Required for the **first real production vertical slice** — a coherent, authenticated, end-to-end path that delivers core value and validates the architecture. |
| **P1** | Required for the **next core features** — completes the primary user journey (save/retrieve, events, profile). |
| **P2** | **Supporting features** — broaden value; depend on P0/P1 foundations. |
| **P3** | **Future/optional** — require real AI, media, or multi-tenant capability that does not exist today. |

---

## Part 1 — P0: First production vertical slice

### The vertical slice (one sentence)

**"Sign in → my wardrobe → my personalized assistant"** — an authenticated user
whose wardrobe and assistant data live in the backend, served through the
per-feature repositories, over a typed contract, grounded in backend-owned
knowledge.

### Why this slice

- **Core Fansivibe value:** the assistant + wardrobe are the product's heart; a
  slice without them validates nothing about the product.
- **Existing working UI:** Wardrobe and Assistant screens already work
  (assistant has the only real pipeline). Wiring them to a backend is a UI-visible
  win with near-zero new UI.
- **Architecture validation:** exercises auth, persistence split, API contract,
  repository boundary, knowledge boundary, and error handling — every
  REQUIRED_BEFORE_BACKEND item in `ARCHITECTURE_GAP_REPORT.md`.
- **User journey:** account → data → personalized output is the whole core loop.

### P0 scope (with dependency roots)

| Item | Why P0 | Depends on | Existing UI | Validates |
| --- | --- | --- | --- | --- |
| Auth: register/login/social + anonymous→sync (AU11.1, AU11.2; ACTION_API #1–4, #32) | every relational write is user-scoped; the backend data model needs user_id | — | AccountCreationScreen, EntryScreen | auth boundary, session handling |
| Canonical persisted domain models (M2.1 subset: user, wardrobe item, saved-look ref, signal, look) | DB tables + API shapes need one canonical shape | ownership decisions (D6.2) | — | model boundaries |
| Typed API + error contract (A3.2, A3.3, E13.1) | every endpoint must be built on it | canonical models | — | API boundary, error handling |
| User model sync API — `POST /users/me/sync`, JSONB + relational split (P7.1; ACTION_API #32) | the blob must split before real rows exist | auth, models | LocalStore path | persistence split |
| Per-feature repository interfaces: learning, wardrobe, assistant (R4.2) | the seam to swap mocks→backend | — | (interfaces only) | repository boundary |
| Wardrobe CRUD wired to server (ACTION_API #5–8) | core user-owned entity, feeds assistant/looks | auth, repos, contract | WardrobeScreen (works today) | end-to-end write path |
| Assistant `POST /v1/assistant/chat` + auth + typed errors (ACTION_API #25–27) | the only real AI pipeline; must become the authenticated reference | auth, contract, knowledge | AssistantScreen (works today) | AI boundary, offline fallback |
| Backend = single knowledge source for P0 vocab (categories/colors, occasions) (K9.1 subset) | "no hardcoded backend-controlled categories"; app fetches/caches | contract | wardrobe Add Item, assistant | knowledge boundary |
| Ownership fixes: `hasSavedWardrobeItem` → user model (F1.4) | session flag currently flips the home branch | — | HomeScreen gate | domain boundaries |
| LocalStore/store failure path (F1.6, E13.3) | silent persistence failures are unacceptable in production | — | — | error handling |

### Explicitly NOT in P0

- Real AI models, media pipeline, Discover matching, analysis features, events,
  profile stats, score/streak history, feedback ratings, weather, subscription.

---

## Part 2 — P1: Next core features

Completes the primary user journey on top of P0. Each has existing UI that is
currently mock/stub.

| Item | Why P1 | Notes |
| --- | --- | --- |
| Saved looks end-to-end (ACTION_API #12/14/17/22/24; UI gap #2/#3/#7) | user saves looks in 4 places but can't see them — core loop | wire the 3 working save paths + Saved Looks screen to server; enable Save Outfit / Save Style stubs |
| Events: persist + CRUD + generate-for-event (ACTION_API #9–11; gap #5) | events are user-created and currently lost | unblock edit/delete stubs; carry event occasion into outfit generation |
| Profile wired to real user data + aggregates (ACTION_API #28; gap #6) | the dashboard must reflect actual state | read user model/aggregates; add empty/loading/error states |
| Today's look + home cards served by backend (ACTION_API #12–13; gap #11) | the daily look is the daily product surface | bind `GET /looks/today`; honest weather/insight slots |
| Full knowledge rollout — all vocabularies from backend (K9.1 full) | removes the 4× duplicated vocabularies | discover filters, builder options, grooming options, event types |
| Capture integrity + privacy copy (gap #1, #18) | a scan must not proceed without an image; appearance data needs privacy explanation | block silent capture-failure; privacy notices on capture flows |
| Feedback actions (like/dislike/why) (gap #17; ACTION_API #31) | the learning loop needs explicit user signals | lightweight controls on AI outputs |
| Score/streak history + aggregates (P7.2 partial) | per-user score/streak rows enable the home + profile cards | derived from signals |
| Face profile pipeline: `setFace` written from real scans (D6.3; gap #8/#9) | enables personalized hairstyle/grooming/assistant | real camera for FaceScan + onboarding capture, or gallery upload |

---

## Part 3 — P2: Supporting features

Broaden value once P0/P1 foundations exist.

| Item | Why P2 | Notes |
| --- | --- | --- |
| Discover feed from backend knowledge (filters/catalog) | content is knowledge; matching stays rules/mock | `GET /looks` from backend knowledge source |
| Hairstyle / grooming / outfit-scan **analysis contract + processing** | analysis result is currently a fixed timer over mocks | server-driven analysis state; can remain rules-based, no real model |
| Outfit builder server-side generation (rule-based, wardrobe-grounded) | generation becomes real (still not AI) | `POST /outfits/generate` from wardrobe + preferences |
| Wardrobe insights (derived) | derived from wardrobe data | replaces the 3 static insight shapes |
| Settings/preferences persistence | user settings should survive restart | `PUT /users/me/preferences` (JSONB) |
| Offline queue + sync retry | production-grade offline behavior | companion to the anonymous→sync path |
| Media pipeline + object storage (item/look photos) (MS10.1/10.2) | real photos become possible | requires media privacy policy (decided in P0) |
| Screen-state inventory rollout (loading/empty/error/retry) | per-screen, with each backend binding | no speculative UI before its binding |
| Subscription basic (ACTION_API #30) | monetization | plans stay knowledge content; purchase via external service |
| Legacy model cleanup (M2.3, B5.3, K9.3) | remove dead models; unify engine spec; versioned config | done opportunistically with each migration |

---

## Part 4 — P3: Future / optional

Require capability that does not exist today (real models, media, multi-tenant).

| Item | Why P3 |
| --- | --- |
| Real AI models (face/outfit analysis, generation, confidence, explanations) | no model exists today; would not validate P0; mock data remains the honest UI |
| Generated images | no generation exists; needs object storage + models |
| Personalized matching beyond rules (real Discover scoring) | depends on real AI + history |
| Weather integration (external service) | today it is a fake literal; low value until looks depend on it |
| Multi-device authorization / sharing / social | no authz model; single-user scope is correct first |
| Contract versioning / migration framework | only needed after real endpoints stabilize |
| Achievements / ranks / XP as real entities | mock-only today; derived aggregates are P2 at best |
| Recommendation history analytics | needs long-running production data |
| Onboarding real face analysis | depends on real face models |

---

## Part 5 — What to build / not build

### MUST NOT be built yet

- **Real AI models** (no capability exists; building fake "AI" contradicts the
  honest-AI finding AI8.1). Keep results mocked until a real model exists.
- **Object storage / media pipeline** — no real images exist anywhere
  (`FansiImageWell` placeholders, transient paths).
- **Weather integration** — the field is a hardcoded literal; low value now.
- **Multi-device authorization / sharing** — single-user scope is correct first.
- **Contract versioning framework** — nothing stable to version yet.
- **Speculative UI states** (loading/empty/error/retry) for features whose
  backend binding isn't scheduled — violates "no speculative UI" (gap #16).
- **New entities beyond the P0 set** (achievements, XP, recommendation-history,
  subscription state) until the P0/P1 slice validates the foundation.

### What should remain mocked

- All **AI analysis results** (scan, hairstyle, grooming, builder, discover
  matching, style DNA, onboarding analysis) — static mocks until real AI.
- **Streak / score / rank / XP / achievements** numbers (derived, later real).
- **Weather literal**, **subscription plans**, **support topics**, **settings
  lists** (knowledge content — move to backend *source* in P1, but the UI values
  stay as-is until then).
- **Generated images** (none exist).
- **Offline assistant rules** for non-core replies (keep until engine dedup).

### What can be postponed

- P2/P3 items above; specifically real analysis/generation, media, weather,
  subscription purchases, sharing, versioning, XP/achievements, real onboarding
  face analysis.

### What is blocking backend development (the P0 prerequisite set)

1. Auth design (register/login/social + anonymous→sync) — **AU11.1/11.2**
2. Canonical domain models — **M2.1**
3. API + typed error contract — **A3.2/3.3, E13.1**
4. Per-feature repository interfaces — **R4.2**
5. Ownership decisions (session flag, events, saved looks) — **F1.4, D6.2**
6. Storage split design (blob → JSONB + rows) — **P7.1**
7. Backend as single knowledge source — **K9.1**
8. Media privacy policy — **MS10.3**
9. User scoping (user_id FK / ownership) — **AZ12.3**

None of these is implementation — they are the decisions/contracts from
`ARCHITECTURE_GAP_REPORT.md` Part 2 that must precede endpoint/table design.

### What can be developed independently (in parallel, non-blocking)

- **Local UI fixes from `UI_UX_GAP_REPORT.md`** that need no backend: capture
  failure block (gap #1), enable edit/delete item + event (gaps #4/#5), enable
  Save Outfit / Save Style (gaps #2/#3), Saved Looks reads persisted list
  (gap #7), `hairstyle-details` FansiErrorView (gap #10), offline notice in
  Assistant (gap #13), privacy copy (gap #18), neutral copy for fabricated
  numbers (gap #19), greeting neutral fallback (gap #14).
- **Dead-model cleanup** (M2.3).
- **Offline engine spec dedup** (B5.3) — single rules spec, independent of backend.
- **Camera/state-machine hardening** for OutfitScan (already built; no backend).
- **Test coverage** for first-time/onboarding/stylist screens (verified gaps).
- **Repository interface definitions** (R4.2) — pure contracts, no wiring.

---

## Part 6 — Sequencing summary

```
P0  Auth → models → contract → user-model sync → repositories →
    wardrobe CRUD → authenticated assistant → backend knowledge → ownership/error fixes
P1  saved looks · events · profile · today's look · full knowledge ·
    capture integrity + privacy · feedback · score/streak history · face pipeline
P2  discover feed · analysis contract · builder generation · insights ·
    settings · offline queue · media pipeline · screen states · subscription · cleanup
P3  real AI · generated images · personalized matching · weather · multi-device ·
    versioning · XP/achievements · recommendation analytics · onboarding face AI
```

**Dependency rule applied throughout:** P0 delivers the foundations that P1's
existing UI can consume; P2 broadens; P3 waits on capabilities that don't exist
today. Nothing is prioritized by technical convenience — the sequence follows
core value (authenticated, personalized assistant + wardrobe) first.
