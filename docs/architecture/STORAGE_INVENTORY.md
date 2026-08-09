# Fansivibe — Storage Inventory

> Companion to `DATA_MODEL_INVENTORY.md`, `FEATURE_DATA_MATRIX.md`,
> `DATA_OWNERSHIP.md`, and `AI_DATA_FLOW.md`.
>
> For every important data object this document assigns its **future** storage
> category (1–7), records its **current** location, the **reason** for the
> choice, and a **retention** policy.
>
> This is documentation only — **no storage is implemented, no dependencies are
> added.** Current locations are verified against source.

---

## Storage categories

| # | Category | Meaning |
| --- | --- | --- |
| 1 | **PostgreSQL relational data** | Normalized rows with keys/FKs (users, wardrobe_items, events, saved_look refs, signals). |
| 2 | **PostgreSQL JSONB candidate** | Flexible/evolving payloads that benefit from `jsonb` querying but stay in Postgres (user model, analysis snapshots, context). |
| 3 | **Object storage** | Blobs: user photos, face scans, outfit photos, wardrobe images, generated images. Referenced by URL from rows. |
| 4 | **Cache** | Recomputed/transient values served fast, evicted freely (scores, feeds, sessions, aggregations). |
| 5 | **External service** | Third-party owned data we consume/route (weather API, LLM, purchase/entitlements, image analysis). |
| 6 | **Temporary processing data** | Mid-pipeline state with no durable value (processing stages, scan buffers, in-flight conversation). |
| 7 | **Static knowledge/content** | System-authored reference data shipped as config/catalog (looks, options, vocabularies, plans, tips). |

---

## Part 1 — Special-attention objects

The ten objects the task calls out, with a full treatment.

### 1.1 Profile photos

- **Current:** none — no photo entity. `ProfileData.avatarInitials` is a String
  (`profile_mock_data.dart:1`); no image is captured, stored, or rendered.
- **Future storage:** **3 — Object storage** (with a `user.avatar_url` reference
  in PostgreSQL, and cached thumbnails in 4).
- **Reason:** a user-uploaded avatar is a binary blob; Blob storage + URL
  reference is the standard split. Thumbnail generation goes to object storage;
  the derived thumbnail URL is cached.
- **Retention:** keep until replaced/deleted by the user; soft-delete on account
  deletion.

### 1.2 Face scans

- **Current:** transient. Hairstyle/Grooming screens use a `CameraController`;
  the captured `xFile.path` is held as a local `String` (`outfit_scan_screen.dart:199`
  is the same pattern; no face path is persisted). `FaceProfile` in the
  `UserModel` blob holds only attributes (never written — `setFace` is uncalled).
- **Future storage:** **3 — Object storage** (the scan image) + **2 — JSONB** for
  the derived `FaceProfile` snapshot in `UserModel`.
- **Reason:** the image is the raw evidence the AI needs (and the user may want
  to re-run analysis); the *attributes* are the durable user profile. Store both,
  keep the image referenceable for re-analysis.
- **Retention:** sensitive/private — auto-expire the raw scan after analysis
  unless the user saves it; keep attributes for the life of the profile.

### 1.3 Outfit photos

- **Current:** transient — `outfit_scan_screen.dart:199` keeps `localPath`
  (camera `XFile.path`) in widget state only; the analysis is a static mock.
- **Future storage:** **3 — Object storage** (source image, referenced by
  `outfit_scan.image_url` row).
- **Reason:** binary blob that grounds the scan analysis and saved-look visuals.
- **Retention:** auto-expire unsaved scans (e.g. 30 days); keep if attached to a
  saved look.

### 1.4 Wardrobe images

- **Current:** no image entity. Wardrobe items are text fields; the "image" slot
  is a `FansiImageWell` gradient placeholder (`shared/components/fansi_image_well.dart:11`).
  Discover uses bundled `assets/images/items/*.jpg` `imageUrl` strings
  (`discover_mock_data.dart:112+`), not user images.
- **Future storage:** **3 — Object storage** per user-uploaded item photo,
  referenced by `wardrobe_items.image_url`; **7** for the bundled catalog assets
  (stay as static assets).
- **Reason:** user item photos are user blobs; catalog item photos are static
  content and should not move to object storage.
- **Retention:** user images — until the item is deleted (delete on cascade);
  catalog assets — tied to content version.

### 1.5 Generated images

- **Current:** none exist. No generation feature produces an image; look cards
  render placeholders.
- **Future storage:** **3 — Object storage** (generated looks/outfit visuals),
  **4 — Cache** for ephemeral generation previews.
- **Reason:** AI-generated images are large blobs; store only when the user saves
  the look (else cache/regenerate on demand).
- **Retention:** cache evictable immediately; saved generated images follow the
  saved-look retention.

### 1.6 AI analysis results

- **Current:** static mocks — `OutfitAnalysisData.mock`, `HairstyleAnalysisResult.mock`,
  `GroomingAnalysisResult.mock`, and onboarding `AnalysisResult` (dead code). All
  verified as no-computation constants.
- **Future storage:** **2 — PostgreSQL JSONB** for the result snapshot (sections,
  detected items, scores) linked to the source image + scan run; **6** for the
  mid-pipeline processing state.
- **Reason:** the result is a structured, evolving shape (good fit for JSONB) and
  must be linked to user + image + feature run; it is reproducible from inputs.
- **Retention:** keep the *latest* per source image; older runs retained only if
  the user saves the look (else delete with the image).

### 1.7 Recommendations

- **Current:** static — `OutfitRecommendation.mock`, `DailyOutfitData.mock`,
  catalog `REFINED_OFFICE`/`TEXTURED_QUIFF`/`STRUCTURED_GOATEE`, offline `_LookCard`.
- **Future storage:** **1 — PostgreSQL** (recommendation rows: type, refs to
  user/look/context, match score) + **7** for the *catalog* the rules/AI selects
  from; **4** for the current/latest recommendation shown to the user.
- **Reason:** a recommendation is a *relationship* (user × occasion × look) worth
  a relational row; the recommendation *content* is knowledge content.
- **Retention:** keep as history for personalization (see historical gap in
  `DATA_MODEL_INVENTORY` §19.6); catalog is versioned content.

### 1.8 Knowledge data

- **Current:** duplicated across codebases — `backend/app/data/catalog.py`
  (`WARDROBE`, `REFINED_OFFICE`, `OCCASIONS`, `NAVIGATION_MAP`, tips),
  Flutter mocks (`WardrobeMockData`, `DiscoverLookData`, `BuilderOption`,
  `GroomingOption`, `EventType`, style/occasion vocabularies), offline `_LookCard`.
- **Future storage:** **7 — Static knowledge/content** served by the backend as
  configuration (the authoritative source), cached on-device in **4**.
- **Reason:** this is reference data the backend must control ("no hardcoded
  backend-controlled categories"); catalog edits are content management, not user
  data. A DB (1/2) is optional only for versioned/content-managed catalogs.
- **Retention:** versioned; ship-and-cache; no user data lifecycle.

### 1.9 Weather data

- **Current:** a hardcoded display String — `weather: '68°F • Partly Cloudy'`
  (`home_mock_data.dart:63`, `daily_outfit_mock_data.dart:65`); no API call.
- **Future storage:** **5 — External service** (weather provider, cached).
- **Reason:** weather is third-party data — Fansivibe never owns it; fetch
  location-based conditions and cache briefly (minutes-to-hours) for the today's
  look card.
- **Retention:** cache only (short TTL); never persist history unless the user's
  look history references it.

### 1.10 Assistant conversations

- **Current:** ephemeral — `AssistantService._messages` (`assistant_service.dart:27`)
  is a `ChangeNotifier` list, cleared on `clear()`; request history is rebuilt per
  message; only `recordSignal` traces persist.
- **Future storage:** **2 — PostgreSQL JSONB** (or 1 with a message table) if
  conversations are kept; **6** for the in-flight session.
- **Reason:** conversations are privacy-sensitive and currently intentionally
  transient; retaining them enables continuity/context but needs an explicit
  product decision + retention window. The minimal durable trace (signals) stays
  relational.
- **Retention:** if retained, keep messages for a short window (e.g. 30–90 days)
  and never store the raw user context snapshot; signals are long-lived.

---

## Part 2 — Master table

| Data | Current Location | Future Storage | Reason | Retention |
| --- | --- | --- | --- | --- |
| User identity/account (name, auth) | `AccountCreationScreen` form (mock; no `User` entity) | **1 PostgreSQL** (`users` row) | per-user relational core | life of account |
| `UserModel` aggregate (wardrobe+face+styleType+savedLooks+occasions+signals) | SharedPreferences blob `fansivibe.user_model.v1` via `LocalStore` | **2 JSONB** (`user_model` snapshot) | evolving shape, single atomic write | life of account; re-seeded on reset |
| Wardrobe item (`WardrobeEntry`) | inside UserModel blob (`addItem`) | **1 PostgreSQL** (`wardrobe_items`, user_id FK) | relational rows with FKs/counts | until user deletes; cascade |
| Wardrobe item images | none (gradient placeholder) | **3 Object storage** + `image_url` on row | user blob | until item deleted |
| Face profile (`FaceProfile` attributes) | inside UserModel blob (never written) | **2 JSONB** in user_model | attributes derived from scan | life of profile |
| Face scan image | transient camera path | **3 Object storage** | raw evidence for analysis | auto-expire unless saved |
| Learning signals (`LearningSignal`) | inside UserModel blob (`recordSignal`) | **1 PostgreSQL** (`learning_signals`, user_id FK) | append-only analytics history | long-lived; soft-delete/retention rules |
| Saved looks (persisted titles) | `UserModel.savedLooks` (List\<String\>) | **1 PostgreSQL** (saved_look + look_ref join) | relational reference rows | until user removes |
| Saved-look full payload (components/date/items) | `SavedLookPreview`/`SavedLookDetail` mocks only | **2 JSONB** snapshot on saved_look | captured at save time | until user removes |
| User events (`UserEvent`) | `EventListScreen` widget state (lost) | **1 PostgreSQL** (`events`, user_id FK) | relational, dated, user-owned | until user deletes; completed events archived |
| Event types / occasion vocabulary | `EventType` + builder/assistant/discover/profile vocabularies (4 copies) | **7 Static knowledge/content** (backend config) | backend-controlled reference | versioned |
| Style vocabulary (vibes/styles) | `StyleVibe`, profile preferences, builder moods, discover filters (4 copies) | **7 Static knowledge/content** | backend-controlled reference | versioned |
| Style score (current) | computed in-memory `LearningService.styleScore`; mock `StyleScoreData` | **4 Cache** (current) + **1 PostgreSQL** (score history) | current = recomputed; history = relational | history long-lived; current evictable |
| Streak data | `StyleStreakData` mock | **1 PostgreSQL** (streak/activity rows) | per-user historical state | long-lived |
| Achievements / ranks / XP | `AchievementData`, `GlobalRankData`, `StyleProgressData` mocks | **1 PostgreSQL** (derived aggregates) + **7** (definitions) | aggregation over history | long-lived |
| Style DNA (`StyleDnaData`/`StyleDnaContext`) | mocks, disconnected from FaceProfile | **2 JSONB** (derived from face profile) | recomputed view | recomputed on demand |
| Today's look (`DailyOutfitData`/`TodaysLookData`) | mock consts | **1 PostgreSQL** (daily_look row per user/day) + **4** (current) | dated snapshot; current cached | keep recent (e.g. 7–30 days); history for personalization |
| Look catalog (`DiscoverLookData`, looks) | Flutter mocks + backend catalog | **7 Static knowledge/content** | system-authored feed | versioned |
| Match scores + reasons + alternatives (Discover) | baked into `DiscoverLookData` mocks | **2 JSONB** (per-user per-look scoring snapshot) or **4** (recomputed) | derived from wardrobe+catalog | recomputable; cache-only unless saved |
| Wardrobe insight | 3 mock shapes + catalog `WARDROBE_INSIGHT` | **4 Cache** (derived) over **1** wardrobe data | derived from wardrobe | recomputed |
| Outfit scan analysis result | `OutfitAnalysisData.mock` | **2 JSONB** linked to image + run | structured snapshot | keep latest per image; else evict |
| Outfit scan processing stages | `ProcessingStage` timer state | **6 Temporary processing data** | pure choreography | discard on completion |
| Outfit scan source image | transient path | **3 Object storage** | grounds analysis/saved look | auto-expire unless saved |
| Outfit builder recommendation | `OutfitRecommendation.mock` | **1 PostgreSQL** (saved outfit rows) + **4** (current) | user×prefs relationship | keep if saved; else cache |
| Outfit builder options | `BuilderOption` vocab | **7 Static knowledge/content** | backend-controlled | versioned |
| Hairstyle recommendation + result | `HairstyleAnalysisResult.mock` | **2 JSONB** (result) + **7** (catalog content) | structured snapshot + content | latest per scan; content versioned |
| Grooming recommendation + result | `GroomingAnalysisResult.mock` | **2 JSONB** (result) + **7** (catalog content) | structured snapshot + content | latest per scan; content versioned |
| Face/grooming input options | `GroomingOption`, `FaceScanCheck` | **7 Static knowledge/content** | reference config | versioned |
| Profile dashboard stats | `ProfileData` mock | **1 PostgreSQL** (derived aggregates) | aggregation over user data | recomputed; cache |
| Profile photos / avatar | none (`avatarInitials` String) | **3 Object storage** + URL row | user blob | until replaced/deleted |
| Generated images | none (placeholder wells) | **3 Object storage** (saved) / **4** (preview cache) | large blobs | cache evictable; saved follow look retention |
| Weather data | `'68°F • Partly Cloudy'` mock String | **5 External service** + **4 Cache** | third-party owned | cache TTL minutes–hours; no history |
| Assistant conversation | `AssistantService._messages` (widget state) | **2 JSONB** (if retained) or **6** (in-flight only) | privacy-sensitive, product decision | short window if retained; else session-only |
| Assistant context snapshot (`AssistantUserContext`) | built per request | **6 Temporary processing data** (never stored) | transient grounding | discard |
| Assistant signals | `UserModel.signals` | **1 PostgreSQL** | trace for learning | long-lived |
| Catalog: outfits/hairstyles/grooming/tips/navigation | `backend/app/data/catalog.py` + mirrors | **7 Static knowledge/content** | single authoritative source | versioned; cache on device |
| `defaultWardrobe` seed (24 items) | `learning_service.dart:9` const | **7 Static knowledge/content** (seed) → **1** on first user save | initial user wardrobe | seed versioned; user rows durable |
| Subscription plans | `ProfileMockData.plans` mock | **7 Static knowledge/content** + **1** (user subscription state) | plan catalog + per-user entitlement | catalog versioned; entitlement life of account |
| Support topics / settings / preferences | `SupportTopic`, `SettingsItem`, `PreferenceOption` mocks | **7 Static knowledge/content** + **2 JSONB** (user prefs) | catalog + user prefs | prefs life of account; catalog versioned |
| Backend request/response DTOs (`schemas.py` ↔ `models.dart`) | code (wire contract) | — (not stored; see note) | boundary contract, not data | n/a |
| Feature/capability flags (`AiCapability`, `UserSession` flag) | static list / in-memory static | **2 JSONB** (user flags) + **7** (capability catalog) | user flag belongs in user model | life of account |

---

## Part 3 — Category consolidation

### 1. PostgreSQL relational data
users, wardrobe_items, saved_look refs, learning_signals, events, score/streak
history, achievements/ranks (aggregates), daily_look rows, saved outfits.

### 2. PostgreSQL JSONB candidates
`UserModel` snapshot, face profile attributes, analysis result snapshots,
saved-look payloads, per-look scoring snapshots, user preferences/flags.

### 3. Object storage
profile/avatar photos, face scans, outfit photos, wardrobe item images,
generated images (saved), look/ensemble visuals.

### 4. Cache
current style score, today's look (current), quick actions/greeting, discover
feed, wardrobe insight, generated-image previews, weather, current
recommendation.

### 5. External service
weather provider, optional LLM (Ollama already), future image-analysis,
purchase/entitlements.

### 6. Temporary processing data
processing-stage choreography, scan buffers, in-flight conversation, assistant
context snapshot, generation previews (pre-save).

### 7. Static knowledge/content
all catalogs + vocabularies (looks, occasions, styles, options, event types,
tips, navigation, plans, support topics, capability config, `defaultWardrobe`
seed, bundled asset images).

---

## Part 4 — Design implications (observed, not decided)

1. **The UserModel blob today is a mix of 1, 2, and historical data** — the
   future split is: JSONB keeps the aggregate, relational rows absorb wardrobe/
   events/signals/saved-look refs, object storage absorbs images.
2. **Every "image" is currently a placeholder** (`FansiImageWell`) — introducing
   real photos is where object storage becomes necessary; nothing today needs it.
3. **Knowledge data is duplicated 3–4×** across app/offline/backend — its single
   home is category 7 (backend-controlled), cached on-device. This resolves the
   duplicate-family problem in `DATA_MODEL_INVENTORY` §19.1 without a DB.
4. **Weather is external + cache**, never a DB table — currently it is a fake
   literal; when wired it must stay out of durable storage.
5. **Conversations are deliberately transient** — choosing to persist them (2) is
   a privacy/product decision the repo does not make; the minimal trace (signals)
   is the safe default.
6. **AI analysis is snapshot-able** (JSONB) and recomputable — the durable inputs
   are user data + catalog + the source image (object storage); results can be
   cache-only unless the user saves them.
7. **Retention principle:** user blobs (3) follow user lifecycle; derived data
   (4) is evictable; history (1) is append-only with retention rules; content (7)
   is versioned and never tied to a user.
