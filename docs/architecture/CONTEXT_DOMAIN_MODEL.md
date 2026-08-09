# Fansivibe — Context Domain Model (Events · Daily Outfit · Weather · Discover)

> **STEP 3 (continuation) — DOMAIN MODEL DESIGN.** Defines the domain concepts
> around Fansivibe's *contextual* surfaces — events and event styling, the daily
> outfit, weather, and discover content — using the STEP 2 inventory to keep
> only the concepts the product actually requires. **No unnecessary entities
> are invented.**
>
> **Source of truth:** the real repository
> (`newproject/flutter_application_1` + `backend/`) and the STEP 2/STEP 3
> documents (`DATA_MODEL_INVENTORY.md`, `DATA_OWNERSHIP.md`,
> `SCREEN_DATA_INVENTORY.md`, `ACTION_API_INVENTORY.md`, `STORAGE_INVENTORY.md`,
> `DOMAIN_ENTITIES.md`, `DOMAIN_RELATIONSHIPS.md`, `DOMAIN_STATE_AND_HISTORY.md`).
>
> **Status:** documentation only. **No SQL, no tables, no UI changes.**

---

## 1. Verified reality check (source facts)

| Concept | What exists today | Evidence |
| --- | --- | --- |
| **Events** | `UserEvent` (id, name, date, time, `eventType`, `hasOutfitRecommendation`) — **widget state only, lost on restart**; only the occasion reaches learning | `event_mock_data.dart:34`; `add_event_screen.dart:116` → `addPreferredOccasion` |
| **Event Styling** | A capability flag (inactive) + a flow: "Generate Outfit" **navigates to the builder with NO event data** | `event_details_screen.dart:316-318` (`context.pushNamed(RouteNames.buildOutfit)`); `allCapabilities` "Event Styling" inactive |
| **Daily Outfit** | `DailyOutfitData`/`TodaysLookData` static mocks (title, components, weather, styleDna, score); save → `addSavedLook` | `daily_outfit_mock_data.dart`; `daily_outfit_screen.dart:1172` |
| **Weather Context** | A **fake literal** `'68°F • Partly Cloudy'` — no API | `home_mock_data.dart:63`; `daily_outfit_mock_data.dart:65` |
| **Discover Content** | `DiscoverLookData` static feed (forYou/trending mocks, 12 look cards, filters, match scores, reasons) | `discover_mock_data.dart`; `DATA_MODEL_INVENTORY.md` §6 |
| **Saved Discover Content** | Save Look → `addSavedLook`; persisted only as a **title string** in `UserModel.savedLooks`; Saved Looks screen reads a mock | `look_details_screen.dart:327`; `UI_UX_GAP_REPORT.md` #7 |

---

## 2. The six concepts — verdict

| # | Concept | Verdict | Category |
| --- | --- | --- | --- |
| 1 | **Events** | **ENTITY** — `UserEvent` (E3) | User-owned domain entity |
| 2 | **Event Styling** | **Not a data concept** — a capability + flow | Capability config + process; no entity |
| 3 | **Daily Outfit** | **Derived snapshot** (conditional history P1) | Derived data / AI output (cache) |
| 4 | **Weather Context** | **External data** (cache-only) | External service |
| 5 | **Discover Content** | **SYSTEM KNOWLEDGE** — `Look` catalog (E5) | System knowledge content |
| 6 | **Saved Discover Content** | **ENTITY** — `SavedLook` (E4) | User-owned domain entity |

**Only two true entities are required here — `UserEvent` and `SavedLook`.** The
other four concepts are a capability, a derived snapshot, an external cache, and
a knowledge catalog. Inventing entities for them (e.g. a `Weather` table, an
`EventStyling` row, a per-user `DiscoverItem`) would duplicate storage and
contradict `DOMAIN_ENTITIES.md`.

---

## 3. The concepts in detail

### 3.1 Events

- **Purpose:** a user-created, dated occasion that gives outfit recommendations
  context ("what am I dressing for"). The occasion type is the signal that
  reaches learning today.
- **Ownership:** user-owned; feature owner = `features/events` (persisted truth
  through `features/learning` per the single-persistence-owner rule).
- **Lifecycle:** create (Add Event form) → edit/delete (**stubs today** —
  `event_details_screen.dart:320` "Edit Event coming soon") → delete by user.
  Currently **lost on restart** (`DATA_OWNERSHIP.md` §`UserEvent`).
- **Relationships:** references `EventType` vocabulary (8 types: casual, formal,
  business, date, party, travel, workout, other — `event_mock_data.dart:10`);
  FEEDS `PreferredOccasions` preference (`addPreferredOccasion`); optionally
  GENERATES an outfit recommendation (R35); links to `SavedLook` when an outfit
  is kept.
- **Persistent?** **No today** (widget state) — must become user-owned rows
  (P1; `STORAGE_INVENTORY.md` Part 2). **External?** No. **Generated?** No
  (user-created). **Historical?** Semi — dated, but *editable*; primary nature
  is current state with historical aspects (`DOMAIN_ENTITIES.md` E3).

### 3.2 Event Styling

- **Purpose:** the *flow* of styling an outfit for an event. As a concept it is
  the **Event Styling capability** (`allCapabilities`, inactive — "Add an event")
  plus the generate-outfit action on an event.
- **Ownership / lifecycle / persistence:** **none as data** — it is a capability
  flag (system config) + a process. No entity, no rows.
- **Relationships:** `UserEvent` → occasion → outfit recommendation (R35); the
  occasion vocabulary is the only durable input.
- **The one real requirement STEP 2 surfaces:** the current flow **loses
  context** — `_generateOutfit` navigates to the builder with no event data
  (`event_details_screen.dart:316-318`). The future flow must **seed the
  occasion** into generation (`ACTION_API_INVENTORY.md` #11: "future endpoint
  must seed the occasion").
- **Persistent?** No. **External?** No. **Generated?** The recommended outfit is
  AI output (regenerable). **Historical?** No (the *recommendation occurrence*
  would be history only via `RecommendationHistory`, P3).

### 3.3 Daily Outfit

- **Purpose:** today's personalized look card (components, style-DNA line,
  weather line, score) on Home — `DailyOutfitData`/`TodaysLookData` mocks.
- **Ownership:** `features/home` displays; `features/learning` persists saves;
  content derives from wardrobe/profile/events/weather + `Look` knowledge.
- **Lifecycle:** **regenerated daily**; a save creates a `SavedLook`
  (`daily_outfit_screen.dart:1172`); per-day history only if the P1 decision
  (`Today'sLookRecord`) is made.
- **Relationships:** DERIVED_FROM `StyleProfile` + `Wardrobe` + `UserEvent` +
  Weather + `Look` (R49); weather FEEDS it (R50); save → `SavedLook` (R30/R31).
- **Persistent?** No (cache). **External?** No. **Generated?** Yes — derived
  AI-output snapshot (mock today). **Historical?** Conditional — `Today'sLookRecord`
  (P1) if "what I wore" history is wanted (`DOMAIN_ENTITIES.md` conditional).

### 3.4 Weather Context

- **Purpose:** temperature/conditions context for the daily outfit ("68°F •
  Partly Cloudy").
- **Ownership:** **external provider** (weather API, future); today a fake
  literal (`home_mock_data.dart:63`; `daily_outfit_mock_data.dart:65`).
- **Lifecycle:** fetched/refreshed; **cache-only with a short TTL — never a DB
  table** (`STORAGE_INVENTORY.md` §1.9, cat 4).
- **Relationships:** FEEDS `Today'sLook`/Daily Outfit (R50); optional feed into
  outfit generation.
- **Persistent?** No (cache). **External?** **Yes** — the only clearly external
  concept here. **Generated?** No (third-party value). **Historical?** No
  (evictable cache; no history requirement).

### 3.5 Discover Content

- **Purpose:** the look catalog/feed the product recommends from — `Look` (E5),
  the canonical system-owned knowledge entity. `DiscoverLookData` is one of its
  4 mirrored shapes (`DATA_MODEL_INVENTORY.md` §19.1).
- **Ownership:** system/backend knowledge source (content-managed, versioned,
  never user-tied); the discover feature *serves* it.
- **Lifecycle:** authored → versioned → deprecated by content management; never
  created/edited by users.
- **Relationships:** `SavedLook` → `Look` by id (R30); match scores/reasons
  derived from wardrobe × catalog (R25/R26); occasion/style vocab tags (R28);
  filter vocabularies drive the feed.
- **Persistent?** Knowledge content (catalog store / served config), never
  per-user rows. **External?** No (bundled assets; content is ours). **Generated?**
  Content is authored; the *scoring* is AI output (mock today). **Historical?**
  No (versioned content, not append-only).

### 3.6 Saved Discover Content

- **Purpose:** the user's durable record of choosing to keep a discovered look —
  the `SavedLook` entity (E4) with a snapshot of what was saved.
- **Ownership:** user-owned; persisted truth in `features/learning` (today only
  a title; the Saved Looks screen reads a mock — `UI_UX_GAP_REPORT.md` #7).
- **Lifecycle:** created from the Discover save path
  (`look_details_screen.dart:327` → `addSavedLook`); removable by the user (no
  UI today); snapshot immutable once written.
- **Relationships:** `SavedLook` → `Look` (catalog ref, R30); optional
  `AnalysisRun` link (R32); embeds snapshot payload (R31); FEEDS
  `StyleScoreRecord`/`ActivityDay` (R33).
- **Persistent?** **Yes (target)** — entity rows + snapshot. **External?** No.
  **Generated?** No — user chooses to save; the referenced content is
  knowledge/AI. **Historical?** Yes — each save is a dated event with an
  immutable snapshot (`DOMAIN_STATE_AND_HISTORY.md` §5.10).

---

## 4. Relationships

Legend (from `DOMAIN_RELATIONSHIPS.md`): **COMPOSITION / REFERENCE /
DERIVED_FROM / GENERATED_FROM / FEEDS** × 1:1 / 1:N / N:M.
`(P1)`/`(P3)`/`(planned)` = pending.

| # | Concept A | Relationship | Concept B | Cardinality | Note |
| --- | --- | --- | --- | --- | --- |
| C1 | `User` | COMPOSITION | `UserEvent` | 1:N (0..N) | = R4; optional, deleted-with-user |
| C2 | `UserEvent` | REFERENCE | `EventType` vocab | N:1 | = R34; type required |
| C3 | `UserEvent` | FEEDS | `PreferredOccasions` preference | N:1 | = R36; `addPreferredOccasion` |
| C4 | `UserEvent` | GENERATED_FROM (planned) | OutfitRecommendation | 1:N | = R35; future flow must seed the occasion |
| C5 | Daily Outfit | DERIVED_FROM | `StyleProfile` + `Wardrobe` + `UserEvent` + Weather + `Look` | 1:1 | = R49; regenerated daily |
| C6 | Weather (external) | FEEDS | Daily Outfit | 1:1 | = R50; cache, short TTL |
| C7 | Daily Outfit | REFERENCE | `SavedLook` (via save) | 0..N:1 | = R30/R31; `daily_outfit_screen.dart:1172` |
| C8 | Daily Outfit | (P1) recorded → | `Today'sLookRecord` | 1:0..1 | per-day immutable snapshot if history wanted |
| C9 | `Look` (catalog) | REFERENCE | occasion/style vocab | N:M | = R28; feed tags |
| C10 | `Look` | DERIVED_FROM | MatchScore / reasons (values) | 1:1 | = R25/R26; wardrobe × catalog |
| C11 | `Look` | served → | Discover feed (DTOs) | 1:N | `DiscoverLookData` = display shape |
| C12 | `User` | COMPOSITION | `SavedLook` | 1:N (0..N) | = R5; from Discover save path |
| C13 | `SavedLook` | REFERENCE | `Look` | 0..1:1 | = R30; catalog id, not just title |
| C14 | `SavedLook` | COMPOSITION | snapshot value objects | 0..N:1 | = R31; immutable at save time |
| C15 | `SavedLook` | FEEDS → DERIVED_FROM | `StyleScoreRecord` + `ActivityDay` | N:1 | = R33; `look_saved` |
| C16 | Event Styling capability (config) | GATES | event → outfit flow | 1:1 | inactive today; no data rows |

### Relationship rules (context cluster)

1. **Only `UserEvent` and `SavedLook` are durable entities here.** Everything
   else — daily outfit (derived), weather (external cache), discover content
   (knowledge), event styling (capability) — is non-entity by design.
2. **Occasion is the shared, id-referenced vocabulary.** Events, looks, and
   recommendations all point at the one occasion vocabulary; nothing copies it
   per user (C2, C9).
3. **Weather never persists and never owns data.** It feeds the daily outfit as
   a cache value (C6); no table, no history.
4. **Daily Outfit is a derived snapshot, not state.** Regenerated daily;
   history is an explicit P1 decision (`Today'sLookRecord`, C8).
5. **Discover saves are entities; discover items are knowledge.** The user's
   saved record (`SavedLook`) references the shared catalog by id (C13) — never
   copies the look content.

---

## 5. Persistent · external · generated · historical — summary

| Concept | Persistent? | External? | Generated? | Historical? |
| --- | --- | --- | --- | --- |
| **Events** (`UserEvent`) | **No today → must be rows** | No | No (user-created) | Semi (dated, editable) |
| **Event Styling** | No (capability/flow) | No | Recommendation = AI output | No |
| **Daily Outfit** | No (cache) | No | **Yes** (derived snapshot) | Conditional (P1) |
| **Weather Context** | **No** (cache) | **Yes** | No | No |
| **Discover Content** (`Look`) | Knowledge store | No | Content authored; scoring AI | No (versioned) |
| **Saved Discover Content** (`SavedLook`) | **Yes (target)** | No | No (user save) | **Yes** (event + snapshot) |

---

## 6. The context flow

```
  EVENTS (UserEvent, entity — user-owned)
    ├─ occasion ──► PreferredOccasions (preference) ──► next decision context
    └─ Generate Outfit (planned) ──► OutfitRecommendation (AI, seeded with occasion)
                                          ▲
  WEATHER (external cache) ────────────────┘
                                          │
  Daily Outfit (DERIVED snapshot) ◄───────┘  (StyleProfile + Wardrobe + Look)
    ├─ save ──► SavedLook (entity) ──► snapshot + 'look_saved' signal
    └─ (P1) ──► Today'sLookRecord (historical, per-day)

  DISCOVER CONTENT (Look, knowledge catalog)
    ├─ served as feed (DiscoverLookData shapes)
    ├─ match scores derived from wardrobe × catalog (AI, mock)
    └─ save ──► SavedLook (entity) ──► references Look by id
```

---

## 7. What is actually required (per Step 2) — nothing invented

| Concept | Required? | Form required |
| --- | --- | --- |
| **Events** | **Yes (P1)** | `UserEvent` rows + edit/delete wiring; the occasion already feeds learning |
| **Event Styling** | **Yes as flow** | Fix the context-loss (`event_details_screen.dart:316`); no new entity — occasion vocabulary + recommendation link suffice |
| **Daily Outfit** | **Yes as derived** | Regenerable snapshot; `Today'sLookRecord` only if P1 history is chosen |
| **Weather Context** | **Yes as feed** | External cache with short TTL; **never** a table |
| **Discover Content** | **Yes as knowledge** | One canonical `Look` catalog source (resolves the 4 mirrored shapes) |
| **Saved Discover Content** | **Yes (P1)** | `SavedLook` entity + snapshot payload; Saved Looks screen reads the real list |

**Not modeled (deliberately):** a `Weather` table, an `EventStyling` record, a
per-user `DiscoverItem`/feed row, and a `DailyOutfit` persistence table (its
history is the P1-gated `Today'sLookRecord`, and its current value is cache).

---

## 8. Report — what was found & what must be modeled next

### What was found

- **Two entities, four non-entities.** Only `UserEvent` and `SavedLook` are
  true domain entities in this cluster. Event Styling is a capability+flow,
  Daily Outfit is a derived snapshot, Weather is external cache, Discover
  Content is knowledge — inventing entities for them would duplicate storage.
- **The occasion vocabulary is the connective tissue** — events, looks, and
  recommendations all reference one canonical occasion list; per-user
  `PreferredOccasions` is a derived preference referencing its ids.
- **Two Step 2 gaps shape this cluster's future:** events are **not persisted**
  (lost on restart) and **Generate Outfit loses event context**
  (`event_details_screen.dart:316-318`); weather is a **fake literal**; and
  saved looks persist **only titles** with the screen reading a mock.
- **Clean state split:** current state = event + saved-look lists; derived =
  daily outfit; external cache = weather; knowledge = discover content; history
  = saved-look save events/snapshots (+ optional `Today'sLookRecord`, P1).

### What must be modeled next (dependency order, none implemented)

1. **Step 4 storage:** `UserEvent` + `SavedLook` rows; `Today'sLookRecord` (only
   if P1 is accepted); cache policy for weather; content store for the `Look`
   catalog + occasion vocabulary.
2. **Events CRUD API (A3.2/A3.3, P1):** persist the widget-state events; wire
   edit/delete (`UI_UX_GAP_REPORT.md` #5).
3. **Occasion-seeded generation (P1):** fix `_generateOutfit` to carry the event
   occasion into the builder (`ACTION_API_INVENTORY.md` #11).
4. **Weather provider (P3):** replace the literal with an external cache feed —
   no schema change beyond a cache.
5. **Saved-look payload + read path (P1):** `SavedLook` full snapshot and the
   Saved Looks screen reading the persisted list (`UI_UX_GAP_REPORT.md` #7).

---

## Constraints honored

- **No SQL, no tables, no repositories, no services, no UI changes.**
- No new dependencies, no code deleted, no entity invented beyond what STEP 2
  supports; every concept and relationship traces to a STEP 2 reference and
  verified source (event_details_screen, event_mock_data, home/daily_outfit
  mock weather literals, discover_mock_data, look_details_screen save path).
- The real Fansivibe repository is the source of truth; the separate reference
  project was not used.
