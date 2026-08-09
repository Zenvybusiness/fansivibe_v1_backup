# Fansivibe — Personal Appearance Domain Model

> **STEP 3 (continuation) — DOMAIN MODEL DESIGN.** Defines the domain model for
> Fansivibe's personal-appearance system — the face/hair/grooming/color/style
> knowledge the product builds about a person — classifying each concept as
> **current profile state**, **historical analysis**, **derived information**,
> **user preference**, or **AI-generated information**, and defining their
> relationships.
>
> **Source of truth:** the real repository
> (`newproject/flutter_application_1` + `backend/`) and the STEP 2/STEP 3
> documents (`AI_DATA_FLOW.md`, `DATA_OWNERSHIP.md`, `DOMAIN_ENTITIES.md`,
> `DOMAIN_MODEL_RULES.md`, `DOMAIN_STATE_AND_HISTORY.md`, `AI_DOMAIN_MODEL.md`).
>
> **Status:** documentation only. **No SQL, no tables, no UI changes, no AI
> implemented.**
>
> **Task rule honored:** "model only concepts supported by the actual product".
> Several names on the task list — **Hair Profile**, **Color Profile**, **AI
> Capability Progress** — have **no data model in the product today**; they exist
> only as capability-config entries and mock outputs. This document models them
> as **PLANNED domain targets** and is explicit about what exists vs. what is
> defined-as-future, so the Step 4 schema never invents persistence for them.

---

## 1. Verified reality check (before any modeling)

| Fact | Evidence |
| --- | --- |
| `FaceProfile` exists but is **never written** | `setFace` has no caller (verified); `learning/data/models.dart:50` fields stay null |
| **No `HairProfile`, `ColorProfile`, or "Appearance Intelligence" classes exist** | grep over `lib/` — no such models |
| "Appearance Intelligence" is **UI copy** | `entry_screen.dart:203` "APPEARANCE INTELLIGENCE"; `your_analysis_screen.dart:266` heading + ":307" "unlock your full Appearance Intelligence" |
| "AI Capability Progress" is **static config + a label** | `allCapabilities` (`onboarding_data.dart:79`); "2 of 7 capabilities active" (`your_analysis_screen.dart:289`); Face/Color Analysis marked `active` are **marketing copy — no computation** (`AI_DATA_FLOW.md` Part D.1) |
| Hair/Grooming "results" are **static mocks** | `HairstyleAnalysisResult` (`hairstyle_mock_data.dart:88`), `GroomingAnalysisResult` (`grooming_mock_data.dart:223`) — no computation |
| Style DNA is a **mock, disconnected from `FaceProfile`** | `StyleDnaData` (`profile_mock_data.dart:145`) / `StyleDnaContext` (`daily_outfit_mock_data.dart:213`) share the same 4 fields; `UI_UX_GAP_REPORT.md` #6 |
| Onboarding face-analysis output is **dead code** | `AnalysisResult`/`OnboardingResult` (`onboarding_data.dart:33/69`) — never referenced |
| Color content is **config + display** | `PaletteSwatch` (`onboarding_data.dart:49`), `ColorPaletteDisplay` (widget) — no profile |
| Style Score is **computed in-memory** | `60 + wardrobe.clamp(0,20) + savedLooks*2.clamp(0,20)` (`learning_service.dart:224`); history = mock |

**Consequence:** of the nine concepts, only **Face Profile (target)**, **Style
Profile/Style DNA**, **Appearance Analysis (target)**, and **Style Score** have
real (if dead/mock) data shapes. The rest are config, copy, or planned.

---

## 2. The nine concepts — classification

| # | Concept | Primary category | Secondary | Status |
| --- | --- | --- | --- | --- |
| 1 | **Face Profile** | **CURRENT PROFILE STATE** (value object content) | AI-generated content; user-owned | Target only — never written |
| 2 | **Hair Profile** | **CURRENT PROFILE STATE** (PLANNED) | AI-generated content | **Planned** — capability config + mock output only |
| 3 | **Grooming Profile** | **CURRENT PROFILE STATE** (PLANNED) | AI-generated content + user preference inputs | **Planned** — capability config + mock output only |
| 4 | **Style Profile / Style DNA** | **CURRENT PROFILE STATE** (Style Profile) + **DERIVED INFORMATION** (Style DNA) | styleType = user preference | Style Profile target; DNA mock today |
| 5 | **Color Profile** | **CURRENT PROFILE STATE** (PLANNED) | AI-generated content | **Planned** — capability config + palette config only |
| 6 | **Appearance Intelligence** | Not data — **SYSTEM NARRATIVE / derived umbrella** | — | UI copy only |
| 7 | **AI Capability Progress** | **SYSTEM CONFIGURATION** (static) | effective availability = derived | No per-user state; do not model rows |
| 8 | **Appearance Analysis** | **HISTORICAL ANALYSIS** (run) + **AI-GENERATED INFORMATION** (result) | = `AnalysisRun` + snapshot | No runs exist (mock/dead) |
| 9 | **Style Score** | **DERIVED INFORMATION** (current) + **HISTORICAL ANALYSIS** (`StyleScoreRecord`) | formula | Current computed; history mock |

---

## 3. The concepts in detail

### 3.1 Face Profile

- **Classification:** **CURRENT PROFILE STATE.** The face attributes a user
  carries: `faceShape`, `skinTone`, `bodyType`, `styleType`
  (`FaceProfile`, `learning/data/models.dart:50`). Embedded as a value object in
  `StyleProfile` (R13).
- **AI-generated vs user-created:** the *content* is **AI-generated** (from face
  analysis); the *state* is **user-owned** and durable once accepted
  (`DATA_OWNERSHIP.md` §`FaceProfile`).
- **Not derived, not historical:** it is a projection of the latest *accepted*
  analysis run, not recomputed from other data — and the producing run (not this
  profile) is the history. Profile carries `source_run_id` provenance
  (`DOMAIN_STATE_AND_HISTORY.md` §5.1).
- **Today:** the value object exists; nothing writes it (`setFace` uncalled).

### 3.2 Hair Profile

- **Classification:** **CURRENT PROFILE STATE (PLANNED).** The user's durable
  hair attributes (e.g. hair type, current length, style affinity) that a hair
  analysis would write. **No such model exists in the product.**
- **What exists today:** the **Hairstyle Profile capability flag**
  (`allCapabilities`, inactive — "Try a hairstyle scan") and mock analysis output
  (`HairstyleAnalysisResult` with `faceShape`/`skinTone`/`styleDna` + top
  recommendation, `hairstyle_mock_data.dart:88`).
- **AI-generated:** would be produced by hair analysis; **user-owned** once
  accepted. Same lifecycle as Face Profile.
- **Design note:** do **not** create a `HairProfile` table yet. When a hair
  pipeline and "Save Style" land (P1), it becomes a profile projection with
  provenance to an `AnalysisRun` (hair) — exactly the Face Profile pattern
  (`DOMAIN_ENTITIES.md` #30 conditional).

### 3.3 Grooming Profile

- **Classification:** **CURRENT PROFILE STATE (PLANNED)** with a **USER
  PREFERENCE** input. The user's durable grooming attributes (beard style,
  density, color, glasses) that a grooming analysis writes.
- **What exists today:** the **Grooming Profile capability flag** (inactive),
  mock `GroomingAnalysisResult` (`grooming_mock_data.dart:223`), and the
  `GroomingOption` **input vocabularies** the user picks from (face shape, beard
  style, density, color — `grooming_mock_data.dart:16`).
- **Two data natures:** the *inputs* the user chooses are **user preference**
  (durable, referencing `GroomingOption` vocab ids); the *analysis output*
  (recommended style) is **AI-generated**; the *accepted profile state* is
  **current profile state**.
- **Today:** inputs are ephemeral widget state (`FEATURE_DATA_MATRIX.md` §10);
  nothing persists.

### 3.4 Style Profile / Style DNA

- **Classification:** two aspects of one concept:
  - **Style Profile** = **CURRENT PROFILE STATE** — the aggregate of
    `styleType` + `FaceProfile` (and future hair/grooming/color attributes)
    owned 1:1 by `User` (R1/R13). `styleType` is also a **USER PREFERENCE**
    (chosen from the 6 `StyleVibe` options in onboarding).
  - **Style DNA** = **DERIVED INFORMATION** — the display view
    (`StyleDnaData`/`StyleDnaContext`: skinTone/faceShape/bodyType/styleType)
    rendered from `FaceProfile` (R14). Recomputed, never stored as truth.
- **AI-generated:** the *attributes* (face shape, skin tone, body type) are
  AI-produced; the *style type* is user-chosen (preference).
- **Today:** the DNA is a **mock disconnected from `FaceProfile`**
  (`UI_UX_GAP_REPORT.md` #6); the profile's face content is never written.

### 3.5 Color Profile

- **Classification:** **CURRENT PROFILE STATE (PLANNED).** The user's durable
  color attributes (season/palette, best colors) that color analysis writes.
  **No such model exists in the product.**
- **What exists today:** the **Color Analysis capability flag** (marked `active`
  — **no computation behind it**, `AI_DATA_FLOW.md` Part D.1), `PaletteSwatch`
  config (`onboarding_data.dart:49`), the `ColorPaletteDisplay` widget, and
  color-harmony strings on outfit metrics (e.g. `colorHarmony` in
  `OutfitRecommendation`).
- **AI-generated:** would be produced by color analysis; **user-owned** once
  accepted. Same pattern as Face/Hair/Grooming Profile.
- **Design note:** do **not** model a `ColorProfile` table; the onboarding
  palette selection is the only current trace (as config/selection), and a
  future analysis would write a profile projection with run provenance.

### 3.6 Appearance Intelligence

- **Classification:** **NOT a data concept.** "Appearance Intelligence" is the
  **system/UX narrative** for the aggregate of appearance capabilities +
  derived awareness — literally the heading on the onboarding capabilities panel
  (`your_analysis_screen.dart:266`) and the entry tagline
  (`entry_screen.dart:203`).
- **What it aggregates (conceptually):** the current appearance profile
  (Style Profile + Face/Hair/Grooming/Color attributes) + the derived capability
  availability + the outputs of appearance analyses. It has no identity,
  lifecycle, or storage.
- **Modeling rule:** treat it as a **derived umbrella/summary**, not an entity,
  not a table, not persisted state. Any screen that displays it aggregates from
  the real concepts below (`AI_DOMAIN_MODEL.md` — same treatment as the
  capability narrative).

### 3.7 AI Capability Progress

- **Classification:** **SYSTEM CONFIGURATION** (static) with a **DERIVED**
  effective-availability view. `allCapabilities` (`onboarding_data.dart:79`) is
  backend/system-authored config: 7 capabilities, 2 `active`; "2 of 7
  capabilities active" is a derived count label, not stored progress
  (`your_analysis_screen.dart:289`).
- **No per-user progress exists** — nothing records "unlocked" or tracks
  progress toward a capability (`DOMAIN_STATE_AND_HISTORY.md` §5.11;
  `AI_DOMAIN_MODEL.md` §4.6).
- **Modeling rule:** do **not** create capability-progress rows. If a real
  capability/unlock system lands (P3): unlocks = **current profile state**
  (user-owned, mutable), unlock/usage events = **historical**, availability =
  **derived** from config × subscription. Until then, config only.
- **Relationship:** capability config **GATES** which Appearance Analysis
  features can run (R-A19).

### 3.8 Appearance Analysis

- **Classification:** **HISTORICAL ANALYSIS** (the run) + **AI-GENERATED
  INFORMATION** (the result). This is the general concept realized by
  `AnalysisRun` (E6) with an immutable `AnalysisResult` snapshot — covering
  face analysis (onboarding, planned), hairstyle analysis, grooming analysis,
  and outfit scan (media-linked; `STORAGE_INVENTORY.md` §1.6).
- **Immutable / append-only:** yes — every execution is a new run; the result
  is a snapshot never edited; old runs stay reproducible via inputs + snapshot +
  engine/model version (`DOMAIN_STATE_AND_HISTORY.md` §5.1–5.3, §6).
- **Feeds the profile:** the *accepted* attributes update the current profile
  projection (R15/R-A2) — never an overwrite of the run.
- **Today:** no runs exist; the intended onboarding shape is the dead
  `AnalysisResult`/`OnboardingResult` (`onboarding_data.dart:33/69`); hair/
  grooming "analysis" are static mocks.

### 3.9 Style Score

- **Classification:** **DERIVED INFORMATION** (current) + **HISTORICAL
  ANALYSIS** (`StyleScoreRecord`).
  - **Current:** a computed value — `60 + wardrobe.length.clamp(0,20) +
    savedLooks.length*2.clamp(0,20)` (`learning_service.dart:224`); a derived
    cache, never stored as truth (`StyleScoreData` is its UI render).
  - **History:** `StyleScoreRecord` (E8) — dated, append-only, immutable
    snapshots of the computed score, so trends survive input changes
    (`DOMAIN_STATE_AND_HISTORY.md` §5.5).
- **AI-generated?** No — deterministic formula, not AI (noted in
  `AI_DATA_FLOW.md` B6).
- **Derived from:** wardrobe count + saved-look count (R43) and, over time,
  signals. **Not an appearance-profile value** — it belongs to the learning
  cluster, but appears here because the task lists it; it does not describe
  appearance, it scores style progress.

---

## 4. Relationships

Legend (from `DOMAIN_RELATIONSHIPS.md`): **COMPOSITION / REFERENCE /
DERIVED_FROM / PRODUCES / FEEDS / GATES** × 1:1 / 1:N / N:M. `(planned)` /
`(P3)` = prospective.

| # | Concept A | Relationship | Concept B | Cardinality | Note |
| --- | --- | --- | --- | --- | --- |
| P1 | `User` | COMPOSITION | Style Profile | 1:1 | = R1; created-with/deleted-with |
| P2 | Style Profile | COMPOSITION | Face Profile (value) | 1:1 | = R13; container mandatory, face content optional (empty today) |
| P3 | Style Profile | COMPOSITION (planned) | Hair Profile / Grooming Profile / Color Profile (values) | 0..1:1 each | future attribute projections |
| P4 | Style Profile | DERIVED_FROM | Style DNA view | 1:1 | = R14; recomputed on demand |
| P5 | Style Profile | REFERENCE | `StyleVibe` vocabulary | N:1 | `styleType` = user preference referencing vocab id |
| P6 | Appearance Analysis (run) | PRODUCES | AnalysisResult (AI, snapshot) | 1:0..1 | = R38; written on completion |
| P7 | Appearance Analysis (run) | PRODUCES → DERIVED_FROM | Face/Hair/Grooming/Color profile attributes | 1:1 latest | accepted attributes update the projection; provenance `source_run_id`; = R15/R-A2 |
| P8 | Appearance Analysis (run) | REFERENCE | `MediaRef` (source image) | 0..1:1 | the evidence; = R37 |
| P9 | Appearance Analysis (run) | REFERENCE | AI Model Version | 0..1:1 | reproducibility trace; R-A3 |
| P10 | Appearance Analysis (run) | FEEDS | `LearningSignal` (`analysis_updated`) | 1:N | append-only trace |
| P11 | Grooming inputs (user choice) | REFERENCE | `GroomingOption` vocab | N:1 | user preference; ids, not free text |
| P12 | AI Capability (config) | GATES | Appearance Analysis / profile features | N:M | which analyses may run; R-A19 |
| P13 | AI Capability (config) × `Subscription` | DERIVED_FROM | CapabilityAvailability (derived) | 1:1 | prospective; = R45/R-A20 |
| P14 | AI Capability (config) | DERIVED_FROM | "Appearance Intelligence" umbrella (narrative) | N:1 | the UI label aggregates config + profiles |
| P15 | Style Profile + Wardrobe + SavedLooks | DERIVED_FROM | Style Score (current, formula) | N:1 | = R43; recomputed |
| P16 | Style Score | FEEDS → DERIVED_FROM | `StyleScoreRecord` (historical) | N:1 | dated snapshots; = R41 |
| P17 | Style Score / profile state | DERIVED_FROM | AI Decision Context (`AssistantUserContext`) | 1:1 per request | profile feeds the assistant; = R47/R-A16 |

### Relationship rules (appearance cluster)

1. **One current-profile projection, many historical runs.** The profile is the
   mutable "who is the user now"; every analysis is an immutable run that can
   feed it (P7). Never store analysis results as profile truth and never mutate
   runs.
2. **Attribute content is AI-generated, acceptance is user-state.** The raw
   attributes come from analysis; once accepted they are user-owned current
   state with provenance.
3. **Profiles are projections over value objects.** Face/Hair/Grooming/Color
   attributes are embedded values inside `StyleProfile` — no separate tables
   until a feature writes them (P2/P3).
4. **Style DNA and Style Score are derived and never stored as truth.**
   (P4, P15). Only their historical snapshots (`StyleScoreRecord`) persist.
5. **Capability and "Appearance Intelligence" are config/narrative.** No
   per-user capability-progress rows and no umbrella table (P12–P14).

---

## 5. Current vs historical vs derived state

| Concept | Current profile state | Historical analysis | Derived info | User preference |
| --- | --- | --- | --- | --- |
| Face Profile | **yes** (target) | no (run is) | no | — |
| Hair Profile | **planned** | no | no | — |
| Grooming Profile | **planned** | no | no | inputs = yes |
| Style Profile | **yes** | no | no | `styleType` = yes |
| Style DNA | — | — | **yes** | — |
| Color Profile | **planned** | no | no | — |
| Appearance Intelligence | — | — | umbrella narrative | — |
| AI Capability Progress | (unlocks: planned) | (events: planned) | availability = yes | — |
| Appearance Analysis | — | **yes** (run) | — | — |
| Style Score | — | `StyleScoreRecord` = yes | **yes** (current) | — |

---

## 6. AI-generated vs user-created

| Concept | AI-generated content | User-created / chosen | System-authored (config) |
| --- | --- | --- | --- |
| Face Profile | **yes** (attributes) | accepted state | — |
| Hair / Grooming / Color Profile | **yes** (attributes) | grooming inputs / `styleType` | — |
| Style DNA | derived from AI content | — | — |
| Appearance Analysis | **yes** (result) | source image capture | — |
| Style Score | no (formula) | wardrobe + saves | — |
| AI Capability / Appearance Intelligence | — | — | **yes** (config + copy) |

---

## 7. The appearance pipeline

```
  Capture (face/outfit image, MediaRef)
        │ executes
        ▼
  Appearance Analysis (HISTORICAL run = AnalysisRun) ──► AI Model Version ref
        │ PRODUCES
        ▼
  AnalysisResult snapshot (AI-GENERATED, immutable)
        │ accepted (latest wins)            │
        ▼                                  ▼
  StyleProfile.FaceProfile (CURRENT)   LearningSignal('analysis_updated')
        │                              (HISTORICAL)
        ▼
  Style DNA view (DERIVED)   Hair/Grooming/Color attributes (PLANNED)
        │
        ▼
  AI Decision Context (DERIVED) ──► assistant / recommendations
        ▲
        │
  Style Score (DERIVED) ◄── wardrobe + savedLooks    ──► StyleScoreRecord (HISTORICAL)
        │
  AI Capability config (SYSTEM CONFIGURATION) ── GATES ──► which Appearance Analyses run
        └──► "Appearance Intelligence" (narrative umbrella over the whole cluster)
```

---

## 8. Report — what was found & what must be modeled next

### What was found

- **Only 4 of the 9 concepts have a real (if dead/mock) data shape:** Face
  Profile (value object, never written), Style Profile/Style DNA (target +
  derived mock), Appearance Analysis (dead `AnalysisResult` + no runs), and
  Style Score (computed; history mock).
- **3 concepts must be modeled as PLANNED, not implemented:** Hair Profile,
  Grooming Profile, and Color Profile exist only as `allCapabilities` flags
  (Hairstyle Profile / Grooming Profile inactive; Color Analysis "active" is
  **marketing copy with no computation**) and mock outputs. **No tables or
  rows** should be created for them until a real pipeline writes attributes
  (P1).
- **2 concepts are deliberately NOT data:** **Appearance Intelligence** is UI
  copy (an umbrella narrative), and **AI Capability Progress** is static config
  + a derived count — **no per-user progress state exists**, so none is modeled
  (unlocks/events become state/history only if a P3 capability system lands).
- **The pattern is uniform:** every appearance attribute is AI-generated
  content accepted into a user-owned current-profile projection, with the
  producing `AnalysisRun` as immutable, reproducible history and the accepted
  value carrying provenance. Style DNA and Style Score are derived and never
  stored as truth.

### What must be modeled next (dependency order, none implemented)

1. **Step 4 storage:** `AnalysisRun` + result snapshot rows (JSONB); the
   `StyleProfile`/`FaceProfile` current-state projection (JSONB) with
   `source_run_id`; `StyleScoreRecord` history; config stores for
   `allCapabilities` and model versions. **No** hair/grooming/color profile
   tables until their pipelines exist.
2. **Face-analysis pipeline (P1):** the only writer of `FaceProfile` today is
   the uncalled `setFace`; nothing can produce appearance history until this
   lands.
3. **Capability/unlock system decision (P3):** before "AI Capability Progress"
   can become per-user state/history.
4. **Typed analysis API (A3.2/A3.3):** the appearance analysis contract
   (face/hair/grooming/color) once real pipelines exist; the assistant DTO
   already carries `FaceData` (KEEP mirrored).
5. **Style Score / Style DNA wiring (P1):** connect the derived views to the
   real profile and records (`UI_UX_GAP_REPORT.md` #6).

---

## Constraints honored

- **No SQL, no tables, no repositories, no services, no AI implemented, no UI
  changes.**
- No new dependencies, no code deleted, nothing invented: planned concepts are
  explicitly flagged PLANNED and are modeled only as the capability config the
  product actually has.
- Every claim about current behavior was verified against source (`setFace`
  uncalled, no HairProfile/ColorProfile classes, "Appearance Intelligence" copy,
  "2 of 7 active", formula, dead `AnalysisResult`, mock hair/grooming results).
- The real Fansivibe repository is the source of truth; the separate reference
  project was not used.
