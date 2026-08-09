# Fansivibe — Value Objects

> **STEP 3 (continuation) — DOMAIN MODEL DESIGN.** Reviews the proposed domain
> entities and identifies the concepts that should be **VALUE OBJECTS** rather
> than independent entities, and for each candidate explains why it is a value
> object, whether it has identity, whether it can be shared, whether it should
> be embedded, and whether it needs persistence.
>
> **Source of truth:** the real repository
> (`newproject/flutter_application_1` + `backend/`) and the STEP 2/STEP 3
> documents (`DOMAIN_MODEL_RULES.md` §1 category 2, `DOMAIN_ENTITIES.md`,
> `DOMAIN_RELATIONSHIPS.md`, `DATA_MODEL_INVENTORY.md` §19.1 duplicate
> families, `AI_DOMAIN_MODEL.md`, `STYLE_WARDROBE_DOMAIN_MODEL.md`).
>
> **Status:** documentation only. **No SQL, no tables, no UI changes.**

---

## 1. What makes something a value object

From the taxonomy (`DOMAIN_MODEL_RULES.md` §1 category 2), a value object:

1. **Has no identity** — it is defined entirely by its attributes; there is no
   "which score 87" question, only "a score of 87".
2. **Is immutable** — it is replaced whole, never mutated in place.
3. **Is interchangeable** — two identical values are equivalent and one can
   replace the other with no effect.
4. **Lives inside an owner** — it is embedded in an entity, DTO, or snapshot;
   it does not exist standalone.

The identity test is decisive: **if the product never refers to the thing by a
stable id and never stores it as its own lifecycle-bearing record, it is a value
object, not an entity.** (Entity definition: `DOMAIN_ENTITIES.md` four tests —
identity + lifecycle + durability + product behavior.)

**The persistence nuance:** a value object *itself* is not persisted as an
entity — but its **value** may be persisted **inside its owner** (a column or
JSONB field), and a **snapshot** of it may be retained for history (e.g.
`StyleScoreRecord`, `SavedLook` payload). Persisting a value is not the same as
giving it entity status.

---

## 2. Candidate value objects — verdict

| # | Candidate | Verdict | Current representation |
| --- | --- | --- | --- |
| 1 | **Color** | **VALUE OBJECT** (value ref) | `WardrobeItem.color` string; `ColorOption` vocab; `colorHex` on pieces |
| 2 | **Score** | **VALUE OBJECT** (derived) | `StyleScore`, `matchScore`, `MatchScoreDetails`, `SavedLookDetail.score` |
| 3 | **Confidence** | **VALUE OBJECT** (AI, optional) | none computed today (`AI_DATA_FLOW.md` Part D.3) |
| 4 | **Location** | **VALUE OBJECT** (candidate; not used) | none in the product |
| 5 | **Money** | **VALUE OBJECT** | `SubscriptionPlan.price` is a display String today |
| 6 | **Date Range** | **VALUE OBJECT** | `UserEvent.date/time`, `SubscriptionPlan.period`, activity days |
| 7 | **Style Vibe** | **VALUE OBJECT / config + preference ref** | `StyleVibe` enum (6 values) |
| 8 | **Occasion** | **VALUE OBJECT / config ref** | `EventType` ids, `occasionOptions`, `OccasionFilters`, backend `OCCASIONS` (4 copies) |
| 9 | **Clothing Attribute** | **VALUE OBJECT** (value refs) | category/color/material/fit ids on items and pieces |
| 10 | **Weather Snapshot** | **VALUE OBJECT** (external cache) | `'68°F • Partly Cloudy'` literal |
| 11 | **AI Reason** | **VALUE OBJECT** (AI output) | `RecommendationReason`, `reasons[]`, per-component reasons |

None of these is promoted to an entity — each is detailed below.

---

## 3. The candidates in detail

### 3.1 Color

- **Why a value object:** a color is fully defined by its value (e.g. `navy`,
  `#1E3A8A`); it has no identity, lifecycle, or independent business rules.
- **Has identity?** No. "Which navy?" is meaningless; two `navy` values are
  interchangeable.
- **Can be shared?** Yes, **by reference through the vocabulary**: the canonical
  color list (system knowledge) is shared by all users; a user item stores the
  color **id**, never a per-user copy (`DOMAIN_MODEL_RULES.md` rule 3). The
  *instance* of a color on an item is per-item but equal by value.
- **Should be embedded?** Yes — the color id is a field on `WardrobeItem.color`
  and on outfit-piece value objects; `colorHex` on pieces is a presentation
  value, not domain data (`STYLE_WARDROBE_DOMAIN_MODEL.md` §3.4).
- **Needs persistence?** The **vocabulary** is persisted as system knowledge
  (config); the **chosen value** is persisted as the id column on the owning
  item. No `colors` per-user table.

### 3.2 Score

- **Why a value object:** a score is a computed number (or breakdown) with no
  identity — `StyleScore`, `matchScore`, `MatchScoreDetails` (overall/fit/
  colorHarmony/occasion/creativity). Recomputed from durable inputs
  (`DOMAIN_MODEL_RULES.md` invariant 6).
- **Has identity?** No. "The score 87" has no id.
- **Can be shared?** No meaningful sharing — scores are **derived per user**
  (wardrobe × catalog, formula). They are not shared content.
- **Should be embedded?** Yes — in the current profile (as a derived cache),
  in a recommendation (matchScore), and in a `SavedLook` snapshot.
- **Needs persistence?** The *current* score: no (recomputed). **History**: yes
  — but as **immutable snapshot records** (`StyleScoreRecord`, E8), not as a
  standalone score entity. A snapshot is persistence of a value, not entity
  status (`DOMAIN_STATE_AND_HISTORY.md` §5.5).

### 3.3 Confidence

- **Why a value object:** a model's confidence is a number + scope (fit/color/
  occasion) attached to a recommendation — no identity, derived, AI-produced
  (`AI_DOMAIN_MODEL.md` §4.4).
- **Has identity?** No.
- **Can be shared?** No — per-recommendation.
- **Should be embedded?** Yes — in the recommendation value object (optional).
- **Needs persistence?** No, except inside a **history snapshot** when the
  product must recall "how confident was the model then". **Today no confidence
  is computed** — card scores are catalog constants, not confidence
  (`AI_DATA_FLOW.md` Part D.3).

### 3.4 Location

- **Why a value object:** if location is ever introduced (event venue, weather
  geocoding), it is a coordinate + label + optional timezone — fully defined by
  attributes.
- **Has identity?** No. (A stored *place* with an id would be a different,
  entity-like concept — but that does not exist and is not required.)
- **Can be shared?** Possibly (e.g. a venue name), but today it is **not used at
  all** — no location data anywhere in the product (verified: no address/geo in
  `features/events` or elsewhere).
- **Should be embedded?** Yes — inside `UserEvent` or the weather snapshot if
  added. **Not modeled now.**
- **Needs persistence?** Only as part of its owning row. No `locations` table.

### 3.5 Money

- **Why a value object:** an amount + currency is defined by its value, with
  arithmetic rules; it has no identity.
- **Has identity?** No.
- **Can be shared?** Yes, as part of shared content — `SubscriptionPlan.price`
  belongs to the plan (knowledge), not to a user.
- **Should be embedded?** Yes — inside `SubscriptionPlan` config; today it is a
  **display String** (`'$4.99/mo'`, `profile_mocks.dart` `SubscriptionPlan`),
  not a typed money value.
- **Needs persistence?** Only as a field of the plan config (and, in the future,
  a subscription's charge record from the external payment service). **No money
  math exists in the product today**; when it does, use an amount+currency value
  object, never floats, and never a standalone entity.

### 3.6 Date Range

- **Why a value object:** a start/end pair (or date + time) is fully defined by
  its endpoints; no identity or lifecycle of its own.
- **Has identity?** No.
- **Can be shared?** No meaningful sharing — a range belongs to its owner.
- **Should be embedded?** Yes — `UserEvent.date`/`time` (currently separate
  Strings in `event_mock_data.dart:34`), `SubscriptionPlan.period`, an
  `ActivityDay` day, a subscription active window.
- **Needs persistence?** As columns/fields **inside the owning entity** — a
  subscription's period persists within `Subscription`, an event's date within
  `UserEvent`. No `date_ranges` table.

### 3.7 Style Vibe

- **Why a value object:** `StyleVibe` (enum, 6 values: Minimalist/Bold/Classic/
  Trendy/Natural/Edgy, `onboarding_data.dart:1`) is a **system-authored
  vocabulary**; the *chosen* vibe is a **user preference** that references it.
  Neither is an entity.
- **Has identity?** No — it is an enumerated value; the *choice* on the user is
  a preference field referencing the vibe id.
- **Can be shared?** Yes — the vibe definition (label + description + gradient)
  is shared system content; the user's choice is per-user.
- **Should be embedded?** Yes — the choice is `StyleProfile.styleType`
  (`DOMAIN_RELATIONSHIPS.md` P5); the definition is config.
- **Needs persistence?** The definition: config; the choice: a field on the
  current profile. No `style_vibes` per-user table.

### 3.8 Occasion

- **Why a value object:** an occasion is a **vocabulary value** referenced by
  id — from events (`EventType`), looks, recommendations
  (`selectedOccasion`), and filters. The canonical vocabulary is system
  knowledge; per-user `PreferredOccasions` is a derived preference referencing
  ids (`DOMAIN_MODEL_RULES.md` §2.7; `CONTEXT_DOMAIN_MODEL.md` C2/C9).
- **Has identity?** The *vocabulary entries* have stable ids (they are config
  content); the *value used on a record* is a plain reference, not an entity.
- **Can be shared?** Yes — one canonical occasion list resolves the 4 duplicated
  copies (`DATA_MODEL_INVENTORY.md` §19.1).
- **Should be embedded?** Yes — as the occasion id field on `UserEvent`,
  `Look`, and recommendation value objects.
- **Needs persistence?** The vocabulary: config store; the reference: a column
  on the owning row. No per-user occasion tables.

### 3.9 Clothing Attribute

- **Why a value object:** a clothing attribute is a **chosen value** (category,
  color, material/texture, fit) referencing a **knowledge vocabulary**; it has
  no identity of its own (`STYLE_WARDROBE_DOMAIN_MODEL.md` §3.3/§3.4).
- **Has identity?** The vocabulary entries have ids (config); the attribute
  *value on an item* does not.
- **Can be shared?** Yes, via the shared vocabularies — never copied per user
  (`DOMAIN_MODEL_RULES.md` rule 3).
- **Should be embedded?** Yes — as id fields on `WardrobeItem` and on the
  canonical outfit-piece value object.
- **Needs persistence?** The vocabularies: config; the chosen values: columns on
  the owning item/piece. No per-attribute tables.

### 3.10 Weather Snapshot

- **Why a value object:** a weather reading (temperature + condition +
  humidity + timestamp) is an **external cache** fully defined by its values —
  `'68°F • Partly Cloudy'` literal today (`home_mock_data.dart:63`).
- **Has identity?** No.
- **Can be shared?** Yes — a reading applies to everyone nearby; it is cached,
  not owned (`STORAGE_INVENTORY.md` §1.9, cat 4).
- **Should be embedded?** Yes — inside the Daily Outfit context (R50) and any
  weather-affected recommendation; never a table.
- **Needs persistence?** **No** — evictable cache with a short TTL; never a DB
  row, never history.

### 3.11 AI Reason

- **Why a value object:** a recommendation reason (`RecommendationReason`
  title/description/icon; `reasons[]`; per-component reasons) is AI output
  without identity — regenerated with the recommendation
  (`AI_DOMAIN_MODEL.md` §4.3; `DOMAIN_RELATIONSHIPS.md` R26).
- **Has identity?** No. Two identical reasons are interchangeable.
- **Can be shared?** The *wording* may be authored/knowledge-like, but a reason
  travels with its recommendation; not shared content.
- **Should be embedded?** Yes — inside the recommendation value object and (as
  part of the payload) inside a `SavedLook` snapshot.
- **Needs persistence?** Not standalone. **But it must be snapshotted** when the
  user saves a look, so later catalog/wardrobe edits cannot rewrite the reason
  that was shown (`SavedLook` payload, R31 — `DOMAIN_STATE_AND_HISTORY.md` §5.7).

---

## 4. Summary

| Candidate | Value object? | Has identity? | Can be shared? | Embedded? | Needs persistence? |
| --- | --- | --- | --- | --- | --- |
| **Color** | yes | no | via vocab id | in item/piece | vocab config + id column |
| **Score** | yes | no | no (derived) | in profile/rec/snapshot | no (current); snapshots as `StyleScoreRecord` |
| **Confidence** | yes | no | no | in recommendation | only in history snapshots; not computed today |
| **Location** | yes (candidate) | no | possible | in event/weather if added | not used today |
| **Money** | yes | no | in plan config | in `SubscriptionPlan` | as plan field; no math today |
| **Date Range** | yes | no | no | in owning entity | as columns inside the owner |
| **Style Vibe** | yes (config + choice) | no | definition shared | choice in `StyleProfile` | config + profile field |
| **Occasion** | yes (vocab ref) | entries: config ids | yes (canonical) | id field on event/look/rec | vocab config + id column |
| **Clothing Attribute** | yes (value ref) | vocab entries: ids | yes | id fields on item/piece | vocab config + id columns |
| **Weather Snapshot** | yes | no | yes (cached) | in daily-outfit context | **no** (cache only) |
| **AI Reason** | yes | no | no | in recommendation/snapshot | snapshotted in `SavedLook` payload |

---

## 5. Boundary cases — when a value object crosses into persistence/history

A value object does **not** become an entity just because it is stored. These
are the deliberate boundaries:

1. **Score → `StyleScoreRecord`.** The current score is derived and discarded;
   the *trend* is kept as immutable dated snapshots (E8). Snapshot = history of
   a value, not a score entity.
2. **AI Reason / match score → `SavedLook` payload.** The reasons and score shown
   at save time are frozen into the saved-look snapshot (R31) so later changes
   can't rewrite what the user saw.
3. **Weather → cache.** Never durable; shared cache value with a short TTL.
4. **Assistant message → (undecided) conversation history.** `AssistantMessage`
   is a DTO/value today; only a product decision to *retain conversations* would
   turn its collection into a historical record — and even then the message is
   still a value embedded in a history row, not an entity
   (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` §3.7/§3.8).

## 6. Things that LOOK like value objects but are NOT

The identity test cuts both ways — these are **not** value objects despite
looking simple:

| Concept | Why it is an entity/config, not a value object |
| --- | --- |
| `SavedLook` | has a stable id + lifecycle (add/remove) — an entity (E4) |
| `Look` (catalog) | has a stable id, versioned content — system knowledge entity (E5) |
| `SubscriptionPlan` | catalog entry with an id + lifecycle (content-managed) — system config |
| `AI Model Version` | registry entry with an id — system config |
| `WardrobeItem` | has an id + lifecycle (create/edit/delete) — an entity (E2) |
| `UserEvent` | has an id + lifecycle (create/edit/delete) — an entity (E3) |
| `MediaRef` | **borderline**: it is a value *object* (a reference) today, but it points at a durable blob whose lifecycle follows its owner; it stays a value object (`DOMAIN_ENTITIES.md` §3.1) |

---

## 7. Report — what was found & what must be modeled next

### What was found

- **All 11 candidates are value objects** — none earns entity status under the
  four tests. The common reasons: no identity (score, confidence, reason,
  weather), vocabulary reference semantics (color, occasion, clothing
  attribute, style vibe), or attribute-only nature (money, location, date
  range).
- **The recurring persistence pattern:** vocabularies persist as **system
  knowledge config**; chosen values persist as **id columns on the owning
  entity**; derived values persist only as **immutable snapshots** for history
  (`StyleScoreRecord`, `SavedLook` payload). No value object gets its own table.
- **Three caveats surfaced:** Money is a display String today (no typed
  amount+currency — no math exists); Location is not used at all (model only if
  a future feature needs it); Confidence is never computed (scores are catalog
  constants) — its value-object shape is defined for the future, not observed
  behavior.
- **The boundary cases are the design risk:** the only way these values reach
  durable storage is inside a snapshot/history record, which is exactly the
  AI-output-never-truth rule (`DOMAIN_MODEL_RULES.md` invariant 1).

### What must be modeled next (dependency order, none implemented)

1. **Step 4 storage:** value objects become columns (id refs, dates, cached
  values) or JSONB fields inside their owning rows; vocabularies become config
  stores; snapshots (`StyleScoreRecord`, `SavedLook` payload) become JSONB/rows.
  **No value-object tables.**
2. **Typed API contract (A3.2/A3.3):** DTOs carry these values inline (colors by
  id, scores/reasons as numbers/lists) — never expose "entities" for them.
3. **Money typing (future):** when pricing math is needed, replace the display
  String with an amount+currency value object inside `SubscriptionPlan`.
4. **Location (future):** introduce a `Location` value object only when a
  feature (event venue, weather geocoding) actually needs it.

---

## Constraints honored

- **No SQL, no tables, no repositories, no services, no UI changes.**
- No new dependencies, no code deleted; every claim about current representation
  verified against source (`SubscriptionPlan.price` String, `StyleVibe` enum,
  weather literal, no location data, no confidence computed).
- Every verdict traces to the STEP 2/STEP 3 taxonomy and duplicate-family
  analysis; the real repository is the source of truth and the separate
  reference project was not used.
