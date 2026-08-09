# Fansivibe — Domain State vs. History

> **STEP 3 (continuation) — DOMAIN MODEL DESIGN.** Classifies every Fansivibe
> domain object as **CURRENT STATE** (the user's present, mutable world) or
> **HISTORICAL** (an append-only, immutable trace of what happened), so the
> Step 4 database never conflates the two and never overwrites history.
>
> **Source of truth:** the real repository
> (`newproject/flutter_application_1` + `backend/`), the 12 STEP 2 inventory
> documents, and the STEP 3 companions `DOMAIN_MODEL_RULES.md`,
> `DOMAIN_ENTITIES.md` (entity key E1–E10), `DOMAIN_RELATIONSHIPS.md`
> (relationship key R1–R51).
>
> **Status:** documentation only. No SQL, no tables, no repositories, no
> services, no Flutter/UI/routing changes, no dependencies, no code deleted.
> This classifies *what the Step 4 schema must keep as state vs. as history*; it
> does not implement either.

---

## 1. The core principle — never overwrite history

The single most important design rule for Fansivibe's storage is:

> **A historical record is a fact about a point in time and is never mutated or
> replaced. "Updating" a user's present state must never rewrite the historical
> trace that produced it.**

Concretely this means the domain keeps **two separate piles of data** that share
a relationship but never share rows:

- **HISTORY** = append-only, immutable events/snapshots (`AnalysisRun`,
  `LearningSignal`, `StyleScoreRecord`, `ActivityDay`, saved-look snapshots,
  and the conditional `Today'sLookRecord` / `RecommendationHistory`).
- **CURRENT STATE** = the user's present, editable world (`User` identity,
  `StyleProfile`/`FaceProfile`, `Wardrobe` collection, `SavedLook` list,
  `UserPreferences`, `Subscription` state).

When a new analysis arrives it **creates a new history record and updates the
current projection** — it never rewrites the old history record
(`DOMAIN_RELATIONSHIPS.md` R15/R39/R40). Deleting an item today removes the
*current* `WardrobeItem`; the `item_added` signals that trace it stay
(`DATA_OWNERSHIP.md` deletion matrix — HISTORICAL is append-only, soft-delete
only).

### The flow that keeps this honest

```
  Face scan (media, transient)
        │ executes
        ▼
  AnalysisRun E6 (HISTORICAL, immutable, append-only)
        │ holds
        ▼
  AnalysisResult snapshot (AI output, immutable once written)
        │ accepted  "latest wins" (R15)
        ▼
  StyleProfile.FaceProfile (CURRENT STATE, mutable projection)
        ▲
        └──── provenance: source_run_id ──► the run that produced these values
```

The current profile is **a projection of accepted history**, not a place where
history is overwritten. Every value in the projection can name the run that
produced it (provenance); the runs remain reproducible even after the
projection moves on.

---

## 2. State vs. history decision procedure

For any domain object, answer in order:

1. **Is it a record of an event/snapshot that happened at a point in time and
   must never change?** → **HISTORICAL** — append-only, immutable, soft-delete
   only (`LearningSignal`, `AnalysisRun`, `StyleScoreRecord`, `ActivityDay`,
   snapshots, future feedback/history records).
2. **Is it the user's present world that can be edited/deleted today?** →
   **CURRENT STATE** — mutable, scoped to `User` (`WardrobeItem`, `UserEvent`,
   `SavedLook` list, `StyleProfile`, `UserPreferences`, `Subscription`).
3. **Can it be recomputed from durable inputs (formula, aggregation, view)?**
   → **DERIVED** — never stored as truth; current value = cache, history (if
   kept) = immutable snapshots (`StyleScore` current vs `StyleScoreRecord`,
   `StyleDna` view, match scores, `Today'sLook`).
4. **Is it an output of analysis/AI that is not user-authored?** → **AI output
   / generated** — never a source of truth
   (`DOMAIN_MODEL_RULES.md` rule 3; `DATA_OWNERSHIP.md` rule 3). Its *record*
   (the run) is history; its *content* (the result) is a snapshot inside that
   history; its *acceptance into the user's state* updates the current
   projection with provenance.
5. **Is it shared system content?** → **SYSTEM KNOWLEDGE** — versioned
   content, not user history and not user state (`Look`, vocabularies).

A single concept may occupy **both piles with different shapes** — that is the
whole point of this document:

| Concept | Current state (mutable projection) | History (immutable, append-only) |
| --- | --- | --- |
| Face attributes | `StyleProfile.FaceProfile` (replaced on new accepted analysis) | `AnalysisRun` (face) + `AnalysisResult` snapshot |
| Style score | computed `StyleScore` (cache) | `StyleScoreRecord` (dated snapshots) |
| Wardrobe | `WardrobeItem` rows (edit/delete) | `LearningSignal` (`item_added`) + `ActivityDay` usage |
| Saved looks | `SavedLook` list (add/remove) | `look_saved` signal + saved snapshot (immutable) |
| Today's look | today's cached derived view | `Today'sLookRecord` (P1 decision, per-day rows) |
| Recommendations | — (never stored as state) | `RecommendationHistory` (P3 decision) + `look_saved` |

---

## 3. Master classification

For every STEP 3 entity and the special-attention concepts the task lists.
Legend: **Y** = yes, **N** = no, **P** = pending product decision
(P1/P3 from `MVP_SCOPE.md`), **semi** = dual nature (see note).

| Concept (ref) | Current state? | Historical? | Immutable? | Mutable? | Derived? | Recalculable? | Note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `User` (E1) | **Y** | N | N | Y (identity/name/anonymous) | N | N (identity is a fact) | Root; not recomputed |
| `StyleProfile` + `FaceProfile` (E1 value) | **Y** | N (projection of runs) | N | Y (replaced whole on new accepted analysis) | Semi (AI-produced content) | Only via a new run (not bit-reproducible) | Keep `source_run_id` provenance |
| `WardrobeItem` (E2) | **Y** | N (only its signals are) | N | Y (favorite, edit) | N (user-authored) | N | Delete removes current row; signals remain |
| `UserEvent` (E3) | **Y** (semi) | Semi — dated but editable | N | Y (edit/delete) | N | N | Calendar row, not audit history |
| `SavedLook` (E4) | **Y** (list) | Semi — each save is a dated event | N (list) / Y (snapshot) | Y (list add/remove) | N | N | The save *snapshot* is immutable once written |
| `Look` (E5 catalog) | N | N | Y (versioned content) | Y (content mgmt only) | N | N | System knowledge, never user state/history |
| `AnalysisRun` (E6) | N | **Y** | **Y** | N | N (recorded event) | **Y** — inputs + snapshot + engine version | The heart of "don't overwrite history" |
| `LearningSignal` (E7) | N | **Y** | **Y** | N | N | N (raw event, replayed not recomputed) | Append-only; soft-delete/retention |
| `StyleScoreRecord` (E8) | N | **Y** | **Y** | N | **Y** (from formula) | **Y** — recompute from durable inputs | Stored for trend; never edited |
| `ActivityDay` (E9) | N | **Y** | **Y** | N | **Y** (from activity) | **Y** | Streak timeline; append-only |
| `Subscription` (E10, P2) | **Y** | N (billing history is external) | N | Y (activate/renew/cancel) | N | N | Entitlement state from external service |
| `Today'sLookRecord` (P1) | N | **P1 Y** | **Y** | N | **Y** | **Y** (regenerated; kept for history) | "What I wore" per user/day |
| `RecommendationHistory` (P3) | N | **P3 Y** | **Y** | N | **Y** (AI-output snapshot) | **Y** with snapshot; else recomputable only | Shown/saved recs for analytics |
| Face Analysis | N (result) / Y (accepted attrs) | **Y** (run) | Y (run + snapshot) | N (run) / Y (profile) | AI-generated | **Y** — old runs reproducible from inputs | Special attention §5.1 |
| Hair Analysis | N (mock result) | **P1 Y** (run when pipeline lands) | Y | N | AI-generated | **Y** | Special attention §5.2 |
| Grooming Analysis | N (mock result) | **P1 Y** | Y | N | AI-generated | **Y** | Special attention §5.3 |
| Style DNA | **Y** as derived view | N (recomputes) | N | N (recomputed) | **Y** | **Y** — from `FaceProfile` | Never stored as truth; §5.4 |
| Style Score (current) | **Y** as cache | N (history = `StyleScoreRecord`) | N | N (recomputed) | **Y** | **Y** — formula | `60 + wardrobe.clamp(0,20) + savedLooks*2.clamp(0,20)`; §5.5 |
| Scans | N | **Y** (`AnalysisRun`) | **Y** | N | N | **Y** | §5.6 |
| Recommendations | N (AI output) | **P3 Y** (history) + `look_saved` signal | Y (snapshot if kept) | N | **Y** | **Y** (regenerable; exact shown result only with snapshot) | §5.7 |
| Recommendation Feedback | N (feature missing) | **future Y** (event log) | **Y** | N | N (user event) | N | §5.8 |
| Wardrobe usage | N (only the wardrobe is state) | **Y** (signals, activity, score recs) | **Y** | N | Semi | Replayable | §5.9 |
| Daily Outfit | **Y** as today's derived view | **P1 Y** (`Today'sLookRecord`) | Y (snapshot) | N (regenerated) | **Y** | **Y** | §5.10 |
| AI Capability Progress | N (no per-user state) | N | N/A | N/A | Derived availability | N/A | §5.11 |

---

## 4. Why the current `UserModel` blob already breaks this rule

Today everything lives in one mutable JSON blob
(`fansivibe.user_model.v1`, `features/learning`). In it, history and current
state are the same object:

- `signals` (history) sit beside `wardrobe`/`savedLooks`/`face` (current state)
  in one mutable `UserModel` (`learning/data/models.dart:106`).
- `savedLooks: List<String>` is a **mutable list of titles** — the save event
  (history) and the current collection (state) are the same rows, so removing a
  saved look erases the only trace of the save (`UI_UX_GAP_REPORT.md` #7).
- `face` is current state with no run linkage — nothing can answer "which
  analysis produced this profile?" (`DOMAIN_RELATIONSHIPS.md` 4.3/4.16).
- The score is recomputed in memory (`learning_service.dart`) and the "history"
  shown on Home/Profile is a **mock** (`StyleScoreData`) disconnected from any
  record (`DATA_MODEL_INVENTORY.md` §3.1).

The Step 4 split fixes this by separating the two piles (§6); the blob is a
*migration* target, not a schema design (`STORAGE_INVENTORY.md` Part 4 #1,
`ARCHITECTURE_GAP_REPORT.md` P7.1).

---

## 5. Special-attention deep dives

### 5.1 Face Analysis

- **Current state:** the accepted attributes in `StyleProfile.FaceProfile`
  (`faceShape`, `skinTone`, `bodyType`, `styleType`). Mutable, replaced whole
  when a new analysis is accepted (`DOMAIN_ENTITIES.md` #4; R13/R15).
- **History:** the `AnalysisRun` (face scan) + its immutable `AnalysisResult`
  snapshot, linked to the source `MediaRef` (R37). Every scan is a new run;
  nothing ever mutates an old run.
- **Immutable?** The run + snapshot, yes. The profile, no.
- **Derived?** The profile content is AI-produced (not computed from other user
  data), so it is not "derived" in the recompute sense — it is regenerable only
  by a *new* run.
- **Recalculated?** A new scan reproduces a new (similar, not identical)
  analysis. **Previous results must remain reproducible** — keep media ref +
  result snapshot + engine/config version so a past run can be re-displayed or
  re-audited (`STORAGE_INVENTORY.md` §1.6: "latest per source image; older runs
  retained only if the user saves the look" — the run is never destroyed, only
  pruned per retention).
- **Today:** nothing is written — `setFace` has no caller (`AI_DATA_FLOW.md`
  Part D.6). The domain model defines the target, not current behavior.

### 5.2 Hair Analysis

- **Current state:** none today — no persisted hair-style profile state; the
  result is a mock (`HairstyleAnalysisResult`, `AI_DATA_FLOW.md` Part B).
- **History:** a `HairstyleRecommendation`/result is AI output; when a real
  hair-analysis pipeline and "Save Style" land (P1), each execution creates an
  `AnalysisRun` (hairstyle) with an immutable result snapshot
  (`DOMAIN_ENTITIES.md` #30 conditional).
- **Immutable / derived / recalculable:** same pattern as §5.1 — run immutable,
  content AI-generated, previous runs reproducible from inputs + snapshot.
- **Do not overwrite:** a new hair analysis replaces nothing today; when it
  lands it must add runs, not rewrite a "current hair profile" that erases the
  old one.

### 5.3 Grooming Analysis

- Identical structure to §5.2 (`GroomingAnalysisResult` mock, `GroomingOption`
  vocabulary, `FaceScanCheck` config gates it — `DOMAIN_ENTITIES.md` #29/31).
- Future runs are `AnalysisRun` (grooming) with immutable snapshots; beard/
  glasses recommendations are AI output regenerable from inputs + catalog.

### 5.4 Style DNA

- **Classification:** a **derived view** over `StyleProfile`/`FaceProfile`
  (`StyleDnaData`/`StyleDnaContext` mocks — `DATA_OWNERSHIP.md` DERIVED).
- **Current state?** No — it renders from the current profile; it is not
  stored. **Historical?** No. **Immutable?** No (recomputed). **Mutable?** No.
  **Derived?** Yes. **Recalculated?** Yes, on demand from `FaceProfile`.
- **Reproducibility:** because it derives from `FaceProfile`, a previous DNA
  remains *re-derivable* as long as the `AnalysisRun` that produced the face
  attributes is retained (§5.1). It is never saved as its own history.

### 5.5 Style Score

- **Current:** a computed cache (`StyleScoreData`) from the verified formula
  `60 + wardrobe.length.clamp(0,20) + savedLooks.length*2.clamp(0,20)`
  (`learning_service.dart:224`).
- **History:** `StyleScoreRecord` (E8) — dated snapshots, append-only,
  immutable, derived from durable inputs (`wardrobe` count, `savedLooks` count,
  signals). This is what the Home trend / Profile history should read (today a
  mock).
- **Derived / recalculated?** Yes — any stored record can be recomputed from
  the inputs at that time; but the *snapshot* is kept because the inputs change
  (removing an item should not rewrite the score history).
- **Do not overwrite:** deleting a wardrobe item lowers today's score but must
  **not** edit past `StyleScoreRecord` rows — history records the score as it
  was when recorded.

### 5.6 Scans

- **Classification:** `AnalysisRun` = **historical** (append-only linkage
  record: user, feature type, source `MediaRef`, timestamp, result snapshot,
  optional `SavedLook` link — R37–R40).
- **Immutable?** Yes. **Mutable?** No. **Derived?** No (a recorded event).
  **Recalculated?** The *result* is reproducible from inputs + engine version;
  the *run* itself is never regenerated or edited.
- **Do not overwrite:** re-running a scan creates a new run; the old run, its
  snapshot, and its linkage to the source image are untouched. Retention may
  prune old runs per policy (`STORAGE_INVENTORY.md` §1.6), which is deletion of
  history under a rule — never an in-place mutation.

### 5.7 Recommendations

- **Current state?** No — an `OutfitRecommendation`/`HairstyleRecommendation`/
  `GroomingRecommendation` is **AI output**, regenerable from
  inputs (`StyleProfile` + `Wardrobe` + `Look`) (R21–R26); it is never stored as
  truth (`DATA_OWNERSHIP.md` rule 3).
- **History:** today the only durable trace is the `look_saved` signal when the
  user saves. A full `RecommendationHistory` (E-conditional, P3) would be an
  **immutable, append-only** record of shown/saved recommendations referencing
  `Look` + snapshot + score.
- **Reproducibility:** regenerable from current inputs, but the **exact
  previously shown result** is reproducible only if a snapshot was kept
  (inputs change over time). Policy: if the product ever needs "what did we
  recommend last month", persist the shown snapshot; otherwise recompute.
- **Do not overwrite:** showing a new recommendation must not erase the record
  of the previous one (P3 history), and a user's later wardrobe edits must not
  rewrite the score/reasons shown at the time of a saved recommendation
  (hence `SavedLook` snapshots, R31).

### 5.8 Recommendation Feedback

- **Current state?** No — **the feature does not exist today** (verified: no
  rating/feedback UI; `UI_UX_GAP_REPORT.md` #17; `ACTION_API_INVENTORY.md` #31;
  `DOMAIN_RELATIONSHIPS.md` 4.12 R27).
- **When it lands:** feedback is a **historical event** (user-owned,
  append-only, immutable), not state. It links a recommendation (or its source
  `Look`/`AnalysisRun`) to the user's reaction.
- **Derived?** No — a raw user event. **Recalculated?** No.
- **Why it matters:** feedback is the explicit signal that connects
  recommendation → user preference (see §7 flow); it aggregates into the
  user's derived preference state over time without ever overwriting it.

### 5.9 Wardrobe usage

- **Current state:** the `Wardrobe` collection of `WardrobeItem` (E2) — mutable,
  user-authored, editable/deletable.
- **History:** every use is traced as **immutable** `LearningSignal`
  (`item_added`, `analysis_updated`, `style_updated`, `look_saved`,
  `occasion_preferred`, assistant signals — 8 types), plus derived
  `ActivityDay` (styled days) and `StyleScoreRecord`. Usage history is what
  powers learning (`DOMAIN_RELATIONSHIPS.md` R41–R43).
- **Do not overwrite:** editing or deleting a wardrobe item never edits the
  signals about it; `item_added` remains a fact even after the item is gone.
  The wardrobe is a projection over user input + history; history stays.

### 5.10 Daily Outfit

- **Current state:** today's derived daily look card
  (`DailyOutfitData`/`TodaysLookData`) — regenerated daily from
  `StyleProfile` + `Wardrobe` + `UserEvent` + weather + `Look` (R49–R50);
  cache-only today.
- **History:** conditional `Today'sLookRecord` (P1) — per-user/per-day immutable
  snapshots ("what I wore today"). If the product wants look history it is
  append-only rows; otherwise it stays a derived cache
  (`STORAGE_INVENTORY.md` Part 2; `DOMAIN_ENTITIES.md` conditional).
- **Do not overwrite:** each day's record (if kept) is immutable; a new day
  never edits the previous day's entry.

### 5.11 AI Capability Progress

- **Current state?** No per-user capability state exists today.
  `allCapabilities` is **static system config** (`onboarding_data.dart:79`):
  7 capabilities, 2 marked `active` (Face Analysis, Color Analysis) —
  marketing copy with no computation behind them (`AI_DATA_FLOW.md` Part D.1;
  "2 of 7 capabilities active" — `your_analysis_screen.dart:289`).
- **History?** No — there is no progress log, no unlock events, nothing
  persisted ("Save My Progress" is a stub; `DOMAIN_RELATIONSHIPS.md` 4.15).
- **Immutable / mutable / derived?** Config is system-owned; the user's
  *effective* availability is a **derived** view over config × subscription
  (R45/R46) once entitlement exists (P3).
- **Do not model** per-user capability rows or a progress history until a real
  capability/unlock system lands (`MVP_SCOPE.md` P3). If it does: unlocks =
  user state (mutable), unlock/usage events = history (immutable).

---

## 6. Reproducibility policy for previous AI results

"Should previous AI results remain reproducible?" — the answer is
**category-dependent**, and this is a Step 4 storage decision this doc pins as
the domain default:

| Previous AI result | Reproducible? | How |
| --- | --- | --- |
| `AnalysisRun` result (face/hair/grooming/outfit) | **Yes (recommended)** | Keep inputs (`MediaRef`) + immutable result snapshot + engine/config version; retention per `STORAGE_INVENTORY.md` §1.6 |
| Recommendation shown to the user | **Only with `RecommendationHistory` (P3)** | Snapshot (look ref + score + reasons) at show time; otherwise recomputable-from-current only |
| Saved look's score/reasons | **Yes** | `SavedLook` snapshot (R31) captures them at save time, so later edits don't change them |
| Style DNA view | **Yes (re-derivable)** | From `FaceProfile`; retains value while the producing `AnalysisRun` is kept |
| Style score at date T | **Yes** | `StyleScoreRecord` snapshot; also recomputable from inputs-at-T if kept |
| Today's look at date D | **Only with `Today'sLookRecord` (P1)** | Per-day immutable snapshot; else regenerable only |
| Insight cards / match scores | No (recomputable) | Never stored; regenerate from wardrobe × catalog |

Binding rule repeated from the companions: **AI output is never a source of
truth — but an AI *event* (a run, a shown recommendation, a save) is a
historical fact that must remain reproducible.** Persist inputs + the user
outcome (saved-look ref, signal) + an immutable snapshot when the product
needs to answer "what did the product tell me back then".

---

## 7. Flows the schema must preserve

```
Recommendation (AI output, shown)
        │ user reacts            [future feature]
        ▼
Feedback (HISTORICAL, append-only, immutable)
        │ aggregates over time
        ▼
User Preference Signal / preferred-style state (derived user state, mutable)

        Historical Analysis              Scan (media)
                │                             │ executes
                ▼                             ▼
        AnalysisRun (immutable) ◄──────── AnalysisRun (immutable)
                │ accepted                    │ holds
                ▼                             ▼
        Current Profile (mutable)        AnalysisResult snapshot (AI)
        │ provenance: source_run_id           │ saved by user
        │                                     ▼
        ▼                               SavedLook snapshot (immutable)
        StyleProfile.FaceProfile

        User actions (add item, save look, add event)
                │
                ▼
        LearningSignal (append-only, immutable)
                │ FEEDS
                ▼
        StyleScoreRecord · ActivityDay   (immutable, derived)
                │ FEEDS
                ▼
        StyleScore (current) · Streak (current)   (derived cache)

        Today'sLook (derived, regenerated daily)
                │ P1: if history wanted
                ▼
        Today'sLookRecord (immutable per-day rows)
```

Every arrow crossing from **history** to **current state** is a *projection*
(derive, accept, aggregate) — never a rewrite of the source history.

---

## 8. Rules the Step 4 schema must enforce

1. **History is append-only.** `AnalysisRun`, `LearningSignal`,
   `StyleScoreRecord`, `ActivityDay`, and any future
   `Today'sLookRecord`/`RecommendationHistory`/`Feedback` rows are created once
   and never updated; edits and deletes apply to current state only
   (`DOMAIN_MODEL_RULES.md` invariant 5).
2. **Current state is a projection with provenance.** `StyleProfile.FaceProfile`
   and the current score/streak name their sources (`source_run_id`; formula
   inputs); they never *contain* history.
3. **Deleting current state never deletes history.** Removing an item, event,
   or saved look leaves its signals/runs intact (soft-delete/retention is the
   only history-removal path — `DATA_OWNERSHIP.md` deletion matrix).
4. **Derived values recompute; snapshots persist.** Current `StyleScore`, Style
   DNA, match scores, and today's look are never written as truth; their
   historical need is met by immutable snapshots (`StyleScoreRecord`,
   `Today'sLookRecord`, `RecommendationHistory`).
5. **AI events stay reproducible.** Keep the durable inputs + immutable result
   snapshot + engine/config version so a previous analysis can be re-displayed
   or audited (§6).
6. **Feedback and capability progress** are modeled only when the features
   exist (feedback P1, capability unlocks P3) — as event history + derived
   state respectively, never speculative tables today.

---

## 9. Report — what was found & what must be modeled next

### What was found

- Fansivibe's domain splits cleanly into **history** (`AnalysisRun`,
  `LearningSignal`, `StyleScoreRecord`, `ActivityDay`, snapshots) and **current
  state** (`User`, `StyleProfile`/`FaceProfile`, `Wardrobe`, `SavedLook` list,
  `UserPreferences`, `Subscription`) — but today both live in **one mutable
  blob**, which is precisely why "history vs state" must be decided now.
- **Nothing in the current app overwrites history** because *nothing is
  historical yet* except `LearningSignal`; everything else is mock or
  ephemeral (`DATA_OWNERSHIP.md` §"History vs snapshot").
- **The three analysis families** (face/hair/grooming) share one pattern:
  immutable `AnalysisRun` + snapshot as history, mutable profile projection as
  current state, and **previous results kept reproducible** via inputs +
  snapshot + engine version.
- **Two special cases are explicitly NOT history or state today:** AI
  Capability Progress (static config only — do not model) and Recommendation
  Feedback (feature missing — model as future immutable event history).
- **Style Score / Style DNA / Today's Look / Recommendations** are the
  derived/AI cluster: recomputable from durable inputs, never stored as truth,
  with **optional immutable snapshots** (`StyleScoreRecord` needed;
  `Today'sLookRecord` P1; `RecommendationHistory` P3) where the product needs
  to recall the past.

### What must be modeled next (dependency order, none implemented)

1. **Step 4 storage split:** separate tables/JSONB for current state vs.
   append-only history, with `source_run_id` provenance on profile projections
   and immutable snapshot columns on `AnalysisRun`/`SavedLook`/`Today'sLookRecord`.
2. **Typed API + error contract (A3.2/A3.3):** current-state endpoints
   (wardrobe CRUD, events, saved looks, profile) must not expose history
   mutation; history is read-only (`GET` only) until a retention/export feature
   exists.
3. **Retention policy** per `STORAGE_INVENTORY.md` — prune old `AnalysisRun`
   snapshots under rules; soft-delete signals; never in-place edit.
4. **P1/P3 decisions** (already flagged): persist `Today'sLookRecord`,
   `RecommendationHistory`; build feedback; land real face/hair/grooming
   pipelines so `AnalysisRun` history actually exists.
5. **Auth + anonymous→sync (AU11.1/AU11.2):** history and current state must
   merge identically across devices (both are user-scoped; history stays
   append-only during merge).

---

## Constraints honored

- No SQL, no tables, no repositories, no services, no schema.
- No Flutter/UI/routing changes, no dependencies, no code deleted.
- Every classification traces to `DOMAIN_ENTITIES.md` / `DOMAIN_RELATIONSHIPS.md`
  and a STEP 2 inventory reference; verified against source where it claims
  behavior (`setFace` uncalled, formula, `allCapabilities` 2-of-7, no feedback
  UI, save stubs).
- The real Fansivibe repository is the source of truth; the separate reference
  project was not used.
