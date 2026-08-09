# Fansivibe — Feature → Data Matrix

> Companion to `FEATURE_INVENTORY.md`, `SCREEN_DATA_INVENTORY.md`, and
> `DATA_MODEL_INVENTORY.md`. For every major feature this document answers
> 12 data questions (display / user-create / user-modify / AI-consume /
> AI-generate / persist / temporary / cross-feature / external / PostgreSQL /
> object-storage / cache-only) and summarizes them in a matrix.
>
> This is **documentation only**. No implementation, no database tables, no UI
> changes.
>
> Scope: the REAL Fansivibe app (`newproject/flutter_application_1`) and backend
> (`backend/`, FastAPI, no DB/auth yet). Claims are verified against source.

## Legend

- **Persistent today** = written through `LearningService`/`LocalStore` into the
  `UserModel` JSON blob (SharedPreferences `fansivibe.user_model.v1`).
- **Temporary today** = widget/route state only, lost on restart.
- **Mock today** = hardcoded in the app or backend catalog; flagged `*mock*`.
- **PostgreSQL / object storage / cache-only** = future target per
  `DATA_MODEL_INVENTORY.md` §19, not implemented.
- Feature names link to the per-feature sections.

---

## Summary matrix

| Feature | Input Data | Output Data | Persistent Data | Temporary Data | External Data | AI Data |
| --- | --- | --- | --- | --- | --- | --- |
| [Onboarding](#1-onboarding) | chosen vibe, camera/gallery image `*mock*` | analysis score/palette/observations `*mock*`, display name, styleType | display name → UserModel; styleType (target) | captured image path, form fields, analysis animation | camera/gallery (device) | mock analysis; future real face analysis |
| [Home](#2-home-dashboard) | UserModel name, save actions | greeting, today's look `*mock*`, style score `*mock*`, streak `*mock*`, insight `*mock*`, quick actions | saved look via `addSavedLook` | date label, onboarding extras, first-visit flag | none | none (all cards mock; future personalized today's look) |
| [Wardrobe](#3-wardrobe) | add-item form selections, image | wardrobe items grid, categories, insight `*mock*`, item detail | `WardrobeEntry` via `addItem`; sets `UserSession.hasSavedWardrobeItem` | form selections, picked image path, snackbar feedback | camera/gallery (device) | wardrobe insight `*mock*`; future image tags |
| [Assistant](#4-assistant) | chat messages | reply text, suggestion cards, clarifications, navigation | `LearningSignal`s (`assistant_message`, `suggestion_opened`, `assistant_navigation`) | conversation list, pending state | FastAPI `POST /v1/assistant/chat`, optional Ollama | replies + intent classification; consumes user context; offline rules fallback |
| [Stylist](#5-stylist-hub) | none | static action grid | none | none | none | none |
| [Discover](#6-discover) | none (catalog), filter selections, save tap | look cards (for-you/trending), detail (score/reasons/ensemble/alternatives) `*mock*` | saved look titles via `addSavedLook` | filters, scroll state | none | match scores + reasons `*mock*`; future personalized matching |
| [Outfit Scan](#7-outfit-scan) | captured outfit image | readiness checks, processing stages, analysis sections, detected items `*mock*`, save look | saved look via `addSavedLook` | image path, stage timers | none today; future image-analysis service | analysis + detected items `*mock*`; future real analysis |
| [Outfit Builder](#8-outfit-builder) | occasion/mood/fit/color preference selections | generation stages, outfit recommendation (components, reasons, metrics) `*mock*` | none (Save is snackbar-only) | preference selection (route extra), stage timers | none today; future generation service | recommendation `*mock*`; future preference-driven generation |
| [Hairstyle](#9-hairstyle) | face scan (camera), save style | scan checks, processing stages, top rec + alternatives, match scores `*mock*` | none (FaceProfile never written by UI) | captured face, stage timers | none today; future face-analysis service | recommendations `*mock*`; future real face analysis |
| [Grooming](#10-grooming) | grooming input options, save style | processing stages, recommendation + details `*mock*` | none | input selection, stage timers | none today; future analysis service | recommendation `*mock*`; future real analysis |
| [Events](#11-events) | event form (title/date/type) | event list, detail | `addPreferredOccasion(eventType)` → preferredOccasions | event list + form (widget state), no event rows persisted | none | none; future outfit-planning per event |
| [Profile](#12-profile-and-sub-features) | preference/settings selections | stats, level/rank/XP `*mock*`, style DNA `*mock*`, achievements `*mock*`, saved looks (mock list), subscription plans `*mock*` | none directly (disconnected from UserModel) | preferences, settings toggles | none | style DNA `*mock*`; future derived from face profile |
| [Learning (core)](#13-learning-core-domain) | writes from wardrobe/events/discover/outfit_scan/home/assistant | UserModel aggregate, change notifications | entire UserModel blob | in-memory singleton cache | none | none directly (styleScore computed); context source for Assistant |

---

## Per-feature detail

Each feature answers the 12 data questions. Numbers match the task prompt:

1. What data does the feature display?
2. What data does the user create?
3. What data does the user modify?
4. What data does the AI consume?
5. What data does the AI generate?
6. What data must persist?
7. What data can be temporary?
8. What data comes from another feature?
9. What data comes from an external service?
10. What data should eventually be stored in PostgreSQL?
11. What data should eventually be stored in object storage?
12. What data should remain generated/cache-only?

---

### 1. Onboarding

1. **Displays** — vibe/`StyleVibe` choices, analysis progress, analysis result
   (score, palette swatches, capability tags) `*mock*`, account/display-name form.
2. **User creates** — chosen vibe, mock analysis selections, display name.
3. **User modifies** — nothing after submission.
4. **AI consumes** — (future) captured face/outfit image and chosen vibe.
5. **AI generates** — analysis result `*mock*` (`AnalysisResult`/`OnboardingResult`
   are dead models — `onboarding_data.dart`, see DATA_MODEL_INVENTORY §19).
6. **Must persist** — display name (into UserModel); styleType (target, API
   exists but nothing calls it).
7. **Temporary** — captured image path, form fields, analysis animation state.
8. **From another feature** — none (entry point; seeds Home/Profile).
9. **External** — camera/gallery (device); future image-analysis service.
10. **PostgreSQL** — user identity/profile row, analysis result, style preference.
11. **Object storage** — captured face/outfit image.
12. **Cache-only** — analysis progress animation; nothing else.

### 2. Home (dashboard)

1. **Displays** — greeting (name from onboarding, default `Alex`), today's look
   card, style score card, streak card, wardrobe insight card, quick actions.
2. **User creates** — nothing directly; can save the daily outfit.
3. **User modifies** — nothing.
4. **AI consumes** — (future) UserModel to personalize today's look/insight.
5. **AI generates** — today's look, style score, streak, insight — all `*mock*`
   (`TodaysLookData`, `StyleScoreData`, `StyleStreakData`, `AIWardrobeInsightData`).
6. **Must persist** — saved look via `addSavedLook` (DailyOutfitScreen:1172);
   records no other state.
7. **Temporary** — computed date label, onboarding extras (vibe, name,
   `hasAnalysis`), first-visit gate (`UserSession.hasSavedWardrobeItem` read at
   HomeScreen:25).
8. **From another feature** — UserModel name; `hasSavedWardrobeItem` flag set by
   Wardrobe; onboarding vibe.
9. **External** — none.
10. **PostgreSQL** — daily outfit feed, style-score history, streak, insight
    (each needs per-user rows; currently static).
11. **Object storage** — today's-look / insight card images.
12. **Cache-only** — greeting, quick actions, date label.

### 3. Wardrobe

1. **Displays** — item grid by category, wardrobe insight banner, item detail.
2. **User creates** — wardrobe items (name/category/color/texture/notes) via the
   Add Item sheet; `_toEntry` → `LearningService.addItem` (WardrobeScreen:301).
3. **User modifies** — item favorite toggle; edit/delete are snackbar-only stubs.
4. **AI consumes** — items (via `AssistantUserContext` wardrobe mirror for the
   assistant; future personalization).
5. **AI generates** — wardrobe insight `*mock*` (`WardrobeInsightData`).
6. **Must persist** — `WardrobeEntry` list inside UserModel; sets
   `UserSession.hasSavedWardrobeItem = true` (WardrobeScreen:302).
7. **Temporary** — add-item form selections, picked image path, snackbars.
8. **From another feature** — none (wardrobe is the source of truth; consumed
   by Assistant/Discover). `defaultWardrobe` seed comes from Learning.
9. **External** — camera/gallery (device); future image tagging.
10. **PostgreSQL** — wardrobe_items table (one row per item, user_id FK).
11. **Object storage** — item images (IDs referenced from wardrobe rows).
12. **Cache-only** — category counts, filter state.

### 4. Assistant

1. **Displays** — chat messages, suggestion cards, clarifying questions,
   navigation prompts.
2. **User creates** — chat messages (`MessageData`).
3. **User modifies** — nothing.
4. **AI consumes** — message history + `AssistantUserContext` (wardrobe, face,
   savedLooks, preferredOccasions) via `LearningService.attachLearning`.
5. **AI generates** — reply text, cards, clarifications, navigation intent;
   intent classification (backend `intent.py`); optional LLM-enriched copy
   (`llm_backend.py`, Ollama). Fallback: `OfflineAssistant` rules engine.
6. **Must persist** — learning signals only (`assistant_message`,
   `suggestion_opened`, `assistant_navigation`) via `recordSignal`. Conversation
   itself is not persisted.
7. **Temporary** — conversation list, typing/pending state.
8. **From another feature** — Learning UserModel (context + signals); mock
   catalog for offline replies.
9. **External** — backend FastAPI `POST /v1/assistant/chat` (default
   `http://localhost:8000`, 12 s timeout, null → offline fallback); optional
   Ollama.
10. **PostgreSQL** — (future) conversation/message history, assistant usage
    signals (today persisted inside UserModel blob).
11. **Object storage** — none.
12. **Cache-only** — reply-text enrichment, offline rules engine outputs.

### 5. Stylist (hub)

1. **Displays** — static grid of action tiles (Outfit Scan, Builder, Hairstyle,
   Grooming, Discover, Events).
2. **User creates** — nothing.
3. **User modifies** — nothing.
4. **AI consumes** — nothing.
5. **AI generates** — nothing.
6. **Must persist** — nothing.
7. **Temporary** — nothing.
8. **From another feature** — none (pure navigation hub).
9. **External** — none.
10. **PostgreSQL** — (future) capability/feature-flag configuration, action
    catalog (per DATA_MODEL_INVENTORY §13 `AiCapability`).
11. **Object storage** — none.
12. **Cache-only** — the action grid itself (static).

### 6. Discover

1. **Displays** — look cards (For You / Trending tabs), filter chips, look
   detail (score breakdown, reasons, ensemble, alternative looks).
2. **User creates** — saves looks; filter selections.
3. **User modifies** — nothing (save is additive).
4. **AI consumes** — (future) user wardrobe + look catalog for
   `wardrobeMatchCount`/alternatives; today the LookDetails fields are `*mock*`.
5. **AI generates** — match scores, recommendation reasons, alternatives —
   `*mock*` (`MatchScoreDetails`, `RecommendationReason`, `EnsembleComponent`).
6. **Must persist** — saved look titles via `addSavedLook` (LookDetails:327).
7. **Temporary** — active filters, scroll state, look id navigation arg.
8. **From another feature** — Learning (save target); (future) Wardrobe for
   matching.
9. **External** — none (looks come from `DiscoverMockData`, mirroring backend
   catalog looks).
10. **PostgreSQL** — looks catalog, user saved-look references (join rows).
11. **Object storage** — look/ensemble item images.
12. **Cache-only** — trending feed, filter option lists.

### 7. Outfit Scan

1. **Displays** — camera preview, readiness checks (lighting/frame/angle),
   processing stages, analysis sections (scores, `DetectedClothingItem`s),
   Generate Look result.
2. **User creates** — captured outfit image path; saved look.
3. **User modifies** — nothing.
4. **AI consumes** — (future) captured outfit image + user wardrobe.
5. **AI generates** — analysis sections, detected items, scores — `*mock*`
   (`OutfitScanAnalysis`, `AnalysisSection`, `ProcessingStage`).
6. **Must persist** — saved look via `addSavedLook` (OutfitAnalysis:260).
7. **Temporary** — image path, per-stage processing timers, camera session.
8. **From another feature** — Learning (save target).
9. **External** — camera (device); future image-analysis service.
10. **PostgreSQL** — scan analysis results, detected items.
11. **Object storage** — captured outfit image.
12. **Cache-only** — processing-stage animation progress.

### 8. Outfit Builder

1. **Displays** — preference chips (occasion/mood/fit/color palette), generation
   stages, outfit recommendation (components, reasons, metrics).
2. **User creates** — preference selections; Save Outfit (snackbar only).
3. **User modifies** — nothing.
4. **AI consumes** — (future) preferences + user wardrobe.
5. **AI generates** — recommendation `*mock*` (`OutfitRecommendation`,
   `OutfitComponent`, `GenerationStage`).
6. **Must persist** — nothing today (Save Outfit is a snackbar; no
   `addSavedLook`/`addItem` call).
7. **Temporary** — preference selection passed as route extra, stage timers.
8. **From another feature** — none today; (future) Wardrobe + Learning.
9. **External** — none today; future generation service.
10. **PostgreSQL** — outfit recommendations, saved outfits.
11. **Object storage** — component images.
12. **Cache-only** — generation stages, preference chips.

### 9. Hairstyle

1. **Displays** — face scan checks, processing stages, analysis result (top
   recommendation + alternatives), detail screen.
2. **User creates** — captured face; Save Style (snackbar only).
3. **User modifies** — nothing.
4. **AI consumes** — (future) face image/profile; offline assistant reuses
   `HairstyleAnalysisResult.mock` for replies.
5. **AI generates** — recommendations + match scores `*mock*`
   (`HairstyleRecommendation`, `HairstyleProcessingStage`, `FaceScanCheck`).
6. **Must persist** — nothing today. `FaceProfile` exists (Learning) with
   `setFace` API, but **no screen calls it** — face data is never persisted.
7. **Temporary** — captured face, stage timers, scan state.
8. **From another feature** — Learning owns the (unwritten) `FaceProfile`;
   Assistant reads it (empty) for context.
9. **External** — camera (device); future face-analysis service.
10. **PostgreSQL** — face profile rows, hairstyle recommendations.
11. **Object storage** — face image.
12. **Cache-only** — scan checks + processing stages.

### 10. Grooming

1. **Displays** — grooming input options (facial-hair state, style preference),
   processing stages, recommendation + details.
2. **User creates** — grooming inputs; Save Style (snackbar only).
3. **User modifies** — nothing.
4. **AI consumes** — (future) face profile + grooming inputs.
5. **AI generates** — recommendation `*mock*` (`GroomingRecommendation`,
   `GroomingOption`, `GroomingProcessingStage`).
6. **Must persist** — nothing today.
7. **Temporary** — input selection, stage timers.
8. **From another feature** — Learning (target `FaceProfile`, unwritten).
9. **External** — none today; future analysis service.
10. **PostgreSQL** — grooming recommendations, face profile.
11. **Object storage** — face image.
12. **Cache-only** — processing stages.

### 11. Events

1. **Displays** — event list, add-event form, event details.
2. **User creates** — events (title, date, type).
3. **User modifies** — nothing.
4. **AI consumes** — (future) events for outfit planning per occasion.
5. **AI generates** — (future) outfit recommendation per event.
6. **Must persist** — `addPreferredOccasion(eventType.name)` on add
   (AddEventScreen:116); **the event rows themselves are NOT persisted** — held
   in `EventListScreen` state only.
7. **Temporary** — event list + form (widget state), event type vocabulary
   (`EventType`, `EventListScreen`).
8. **From another feature** — none.
9. **External** — none.
10. **PostgreSQL** — events table; preferredOccasions (from UserModel blob → rows).
11. **Object storage** — none.
12. **Cache-only** — event-type vocabulary today; should become shared config
   (see DATA_MODEL_INVENTORY §19 duplicate vocabularies).

### 12. Profile (and sub-features)

1. **Displays** — stats (items/outfits/events), level/rank/XP, style DNA
   (palette, archetype), achievements, saved looks, menu; sub-features:
   Preferences (switches/sliders), Saved Looks (cards), Subscription (plans),
   Support (topics), Settings (toggles), Upgrade (plans).
2. **User creates** — preference selections, settings toggles.
3. **User modifies** — preferences/settings (all ephemeral, widget state).
4. **AI consumes** — nothing directly; (future) `FaceProfile` to derive style DNA.
5. **AI generates** — style DNA `*mock*` (`StyleDnaData` disconnected from
   persisted `FaceProfile`).
6. **Must persist** — nothing today. Saved Looks screen shows
   `ProfileMockData.savedLooks`, **not** the persisted `UserModel.savedLooks`.
7. **Temporary** — preferences, settings, support-topic navigation.
8. **From another feature** — should read Learning UserModel (stats/saved
   looks/style type) but currently uses mocks.
9. **External** — none; (future) purchase/entitlement service for subscription.
10. **PostgreSQL** — user profile/stats, achievements, subscription, preferences,
    saved-look references.
11. **Object storage** — avatar images.
12. **Cache-only** — subscription plans, support topics, achievement catalog
    (static content).

### 13. Learning (core, cross-cutting)

Not a screen — the persistence/repository layer owned by `features/learning`.
Included because every other feature's persist/duplicate answers resolve here.

1. **Displays** — nothing (notifies listeners; Wardrobe reads `wardrobe`).
2. **User creates** — `UserModel` aggregate via the feature write APIs above.
3. **User modifies** — wardrobe items, preferred occasions, saved looks,
   signals (all via public methods).
4. **AI consumes** — the whole aggregate as `AssistantUserContext` mirror.
5. **AI generates** — computed `styleScore` (derived, not AI).
6. **Must persist** — the full UserModel JSON blob (SharedPreferences
   `fansivibe.user_model.v1`) via `LocalStore`; seeded `defaultWardrobe`.
7. **Temporary** — in-memory singleton cache of UserModel.
8. **From another feature** — writes from Wardrobe, Events, Discover, Outfit
   Scan, Home, Assistant; read by Assistant and Wardrobe.
9. **External** — none.
10. **PostgreSQL** — users, wardrobe_items, saved_looks, preferred_occasions,
    learning_signals (split from the single blob).
11. **Object storage** — none (image references only).
12. **Cache-only** — `styleScore` derivation and the singleton cache (source of
    truth is durable storage).

---

## Consolidated future storage mapping

Aggregation of questions 10–12 across all features.

### → PostgreSQL (split from the single UserModel blob + new entities)

| Group | Source today | Features |
| --- | --- | --- |
| User identity + profile (name, styleType, stats, level/XP) | UserModel | Onboarding, Home, Profile |
| Wardrobe items | `UserModel.wardrobe` | Wardrobe, Learning |
| Face profile | `FaceProfile` (never written) | Hairstyle, Grooming, Learning |
| Saved looks (reference rows) | `UserModel.savedLooks` (never read by UI) | Discover, Outfit Scan, Home, Profile |
| Preferred occasions | `UserModel.preferredOccasions` | Events, Learning |
| Learning signals | `UserModel.signals` | Assistant, Learning |
| Events | EventListScreen state (lost) | Events |
| Scan/analysis results + detected items | mock, unpersisted | Outfit Scan, Hairstyle, Grooming |
| Recommendations (outfit/hairstyle/grooming) | mock, unpersisted | Outfit Builder, Hairstyle, Grooming |
| Style-score/streak history | mock cards | Home |
| Daily/today's look feed | mock + backend catalog | Home, Discover |
| Conversations + assistant signals | signals only, chat lost | Assistant |
| Capability/feature flags, action catalog | static UI | Stylist, Profile |

### → Object storage

| Data | Features |
| --- | --- |
| Captured outfit images | Outfit Scan, Outfit Builder components |
| Captured face images | Onboarding, Hairstyle, Grooming |
| Wardrobe item images | Wardrobe |
| Look / ensemble images | Discover, Home |
| Avatar images | Profile |

### → Generated / cache-only (never durable)

| Data | Features |
| --- | --- |
| Processing-stage animation progress | Outfit Scan, Outfit Builder, Hairstyle, Grooming |
| Greeting, date label, quick actions | Home, Stylist |
| Active filters, scroll state, route args | Discover, Wardrobe |
| Offline rules engine outputs | Assistant |
| Subscription plans, support topics, achievements catalog | Profile |
| Preference/settings toggles (until a settings store exists) | Profile |

---

## Cross-feature data ownership notes

- **`UserSession.hasSavedWardrobeItem`** — user flag written by Wardrobe, read by
  Home for the onboarding gate; lives outside `features/learning`.
- **Saved looks** — created by Discover, Outfit Scan, and Home (all call
  `addSavedLook`); displayed by Profile from a **mock**, never from the
  persisted list.
- **Wardrobe** — single source of truth in Learning; consumed (read) by
  Assistant context and (future) Discover matching.
- **Face profile** — API exists (`setFace`) but no feature writes it; every
  consumer (Hairstyle, Grooming, Assistant, Profile style DNA) sees empty/mock.
- **Occasion/style vocabularies** — duplicated in Events, Builder, Assistant,
  Discover, Profile; no shared config source (see DATA_MODEL_INVENTORY §19).
