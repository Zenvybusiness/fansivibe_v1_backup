# Fansivibe — Stage 2: Product Development Roadmap

**Document Type:** Strategic Product Development Roadmap  
**Status:** Canonical Active Roadmap  
**Date:** October 31, 2026  
**Audited Against:** Git Working Tree (commit `19c35b4`, Stage 1D completion)

---

## 1. Executive Summary & Strategy

Following the successful completion and closure of Stage 1D (Architecture Hardening, Recommendation Integrity, and Ephemeral Guest Isolation), Fansivibe transitions into **Stage 2: User-Facing Product Development**.

Fansivibe is not starting from zero. The platform possesses:
- A complete Flutter 5-tab shell with state restoration, persistent routing, and zero-network guest isolation (D10 Option A).
- A 16-router FastAPI backend with transactional PostgreSQL persistence (32 tables) and Alembic migrations.
- A canonical 12-term candidate scoring engine (`analysis_rules.py`), harmonized assistant chat, and local Ollama vision pipeline.

The central strategic challenge of Stage 2 is **closing the daily engagement and retention loop**. While wardrobe management and outfit generation are mathematically robust, critical user journeys (such as logging worn outfits, persisting full style preferences, and seamless grooming analysis) have minor disconnections between the Flutter UI and backend. 

Stage 2 focuses on turning existing architectural assets into a cohesive, rewarding, and retention-focused personal styling companion.

---

## 2. Product Development Opportunities & Evaluation

Eight candidate opportunities were identified and evaluated across seven strict product criteria:
1. **User Value:** Impact on user satisfaction, daily habit formation, and style confidence.
2. **Product Differentiation:** Competitive advantage over generic wardrobe apps.
3. **Infrastructure Reuse:** Extent of existing backend, database, and UI logic directly leveraged.
4. **Implementation Complexity:** Engineering effort, risk of regression, and delivery scope.
5. **Technical Dependencies:** Prerequisites required before implementation.
6. **Privacy & Data Integrity:** Compliance with appearance privacy and sensitive biometric rules.
7. **Independent Deliverability:** Ability to ship in focused, verifiable milestones without architectural rewrites.

### Evaluation Scorecard

| Opportunity | User Value | Differentiation | Infra Reuse | Complexity | Dependencies | Privacy Risk | Independent? | Priority |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Multi-Item Outfit Wear Logging** | **Highest** | **High** | **Highest (100% API ready)** | **Low** | None | Low | **Yes** | **P0** |
| **Grooming Input Flow Repair** | **High** | **Medium** | **High (Rules ready)** | **Low** | None | Low | **Yes** | **P0** |
| **Style Preferences & Settings Sync** | **High** | **Medium** | **High (Schema ready)** | **Low** | None | Low | **Yes** | **P0** |
| **Wardrobe Cloud Image Persistence** | **Highest** | **Medium** | **Medium (Needs upload API)** | **Medium** | Storage setup | Low | **Yes** | **P0** |
| **Interactive Outfit Component Swapping** | **High** | **Highest** | **High (Engine ready)** | **Medium** | Wear logging | Low | **Yes** | **P1** |
| **Enriched Saved Look Hydration** | **Medium** | **Medium** | **High (Join queries)** | **Low** | None | Low | **Yes** | **P1** |
| **Weather-Aware Daily Seeding** | **High** | **High** | **High (Rules ready)** | **Medium** | Weather API | Low | **Yes** | **P1** |
| **Generative Virtual Try-On (Stage F1)** | **High** | **Highest** | **Low (Needs diffusion)** | **Highest** | GPU / Queue | Medium | **No** | **P2** |

---

## 3. Prioritized Stage 2 Roadmap

### P0: Essential Product Functionality (Integrity & Core Loops)
*Must be completed first to eliminate broken journeys and activate the daily retention loop.*

```
+-----------------------------------------------------------------------------+
|                                    P0                                       |
|  +---------------------------+       +------------------------------------+ |
|  | P0-1: Multi-Item Wear Log | ----> | P0-2: Grooming Analysis Bug Fix   | |
|  +---------------------------+       +------------------------------------+ |
|                |                                       |                    |
|                v                                       v                    |
|  +---------------------------+       +------------------------------------+ |
|  | P0-3: Preferences Sync    | ----> | P0-4: Wardrobe Media Cloud Sync    | |
|  +---------------------------+       +------------------------------------+ |
+-----------------------------------------------------------------------------+
```

---

#### Feature P0-1: Multi-Item Outfit Wear Logging & Daily Engagement Loop
- **User Problem:** Users receive curated outfits from "Today's Look", "Outfit Builder", or "Saved Looks", but cannot log the outfit as worn. Tapping "Wear This Look" on the home screen only shows a transient snackbar without recording the wear. Wear counts in the wardrobe only increment if the user drills into individual item detail screens one by one. Consequently, wardrobe wear decay scoring and Style Streaks remain stagnant.
- **Proposed User Experience:**
  1. Tapping "Wear This Look" on `DailyOutfitScreen` or "Log Wear Today" on `OutfitRecommendationScreen` triggers an immediate optimistic wear logging action.
  2. Flutter submits all garment IDs in the outfit to `POST /v1/wardrobe/wears`.
  3. A celebratory sheet displays: *"Look logged for today! +1 to your Style Streak"*.
  4. Wardrobe items reflect updated wear counts; the home screen updates the daily wear status badge to "Worn Today".
- **Existing Implementation to Reuse:**
  - Backend `POST /v1/wardrobe/wears` (`app/api/routers/wardrobe.py`) already accepts 1..10 `itemIds` in a single transactional wear group.
  - PostgreSQL tables `wardrobe_wear_groups` and `wardrobe_wear_events` are already fully implemented with idempotency keys.
  - Domain wear decay calculations and `GET /v1/wardrobe/wear-summary` are fully operational.
- **New Frontend Work:**
  - Create `WardrobeService.logEnsembleWear({required List<String> itemIds, String? context})`.
  - Connect "Wear This Look" button in `lib/features/home/presentation/screens/daily_outfit_screen.dart`.
  - Add "Log Wear" floating or prominent action button to `lib/features/outfit_builder/presentation/screens/outfit_recommendation_screen.dart`.
  - Add "Log Wear" action to `lib/features/saved_looks/presentation/screens/look_details_screen.dart`.
- **New Backend Work:** None. API is 100% implemented, tested, and verified.
- **Database Changes:** None.
- **AI / Model Requirements:** None.
- **Dependencies:** FEAT-04, FEAT-06, FEAT-14.
- **Acceptance Criteria:**
  - Tapping "Wear This Look" logs all item IDs atomically via `POST /v1/wardrobe/wears`.
  - Idempotency key prevents double-counting on rapid double-taps.
  - Wear counts on all component items in the wardrobe increment by 1.
  - User can view logged wear in `GET /v1/wardrobe/wear-summary`.

---

#### Feature P0-2: Authenticated Grooming Analysis & Profile Repair
- **User Problem:** Authenticated users who enter face shape and beard details in `GroomingInputScreen` experience a crash (`422 INSUFFICIENT_USER_DATA`) because `GroomingProcessingScreen` sends an empty body (`{}`) to `POST /v1/analysis/grooming`. If the user hasn't previously performed a full camera Face Scan, the backend cannot find `face_shape` in `user_state.style_profile` and aborts.
- **Proposed User Experience:**
  - User fills out manual grooming parameters (Face Shape, Beard Style, Density, Sensitivity) and taps "Analyze Grooming".
  - Analysis processes seamlessly and renders personalized beard-to-face shape compatibility advice and grooming maintenance steps.
  - The manually selected face shape automatically populates the user's profile if it was previously unset.
- **Existing Implementation to Reuse:**
  - `GroomingInputScreen`, `GroomingProcessingScreen`, `GroomingResultScreen`.
  - Backend domain service `grooming_rules.py` with 100% complete compatibility matrix.
  - `POST /v1/analysis/grooming` endpoint.
- **New Frontend Work:**
  - Update `GroomingService.runAnalysis()` and `GroomingProcessingScreen._runAuthenticated()` to pass user-selected form values: `face_shape`, `beard_style`, `beard_density`, `skin_sensitivity`.
- **New Backend Work:**
  - Update `GroomingAnalysisRequest` in `app/api/routers/analysis.py` to accept optional `face_shape: Optional[str] = None`.
  - In `CreateGroomingRun`, fall back to the request payload's `face_shape` if `user_state.style_profile.face_shape` is null.
  - Persist the provided face shape into `user_state.style_profile.face_shape` if previously unset.
- **Database Changes:** None.
- **AI / Model Requirements:** None (uses algorithmic `grooming_rules.py`).
- **Dependencies:** FEAT-12, FEAT-13.
- **Acceptance Criteria:**
  - Authenticated user without prior face scan enters face shape on screen and receives valid grooming recommendations.
  - Backend updates `user_state.style_profile` with face shape.
  - No 422 errors returned.

---

#### Feature P0-3: Style Preferences & Application Settings Persistence
- **User Problem:** Archetype selections (Minimalist, Classic, Streetwear, Bold) in `StylePreferencesScreen` and settings toggles (Push Notifications, Dark Mode, Biometric Lock) in `SettingsScreen` do not persist to the server or local storage. Changes are discarded as soon as the user exits the screen.
- **Proposed User Experience:**
  - In `StylePreferencesScreen`, selecting style archetypes, fit preferences, and formality priorities saves instantly with a subtle confirmation indicator.
  - Toggling notifications, theme, or privacy preferences in `SettingsScreen` persists across app restarts and syncs to `user_state.settings`.
- **Existing Implementation to Reuse:**
  - Backend `PATCH /v1/users/me` endpoint.
  - `user_state` PostgreSQL table containing `style_profile` (JSONB) and `settings` (JSONB) columns.
- **New Frontend Work:**
  - Update `lib/features/profile/presentation/screens/style_preferences_screen.dart` to submit archetype and fit selections to `UserService.updatePreferences()`.
  - Update `lib/features/settings/presentation/screens/settings_screen.dart` to save to `SharedPreferences` locally and dispatch settings update to backend.
- **New Backend Work:**
  - Verify that `UserUpdateRequest` schema permits partial updates to `style_profile` (archetype, fit) and `settings` dictionary.
- **Database Changes:** None (`user_state` JSONB columns already exist).
- **AI / Model Requirements:** None (persisted archetypes directly influence candidate scoring weights in `analysis_rules.py`).
- **Dependencies:** FEAT-17, FEAT-22.
- **Acceptance Criteria:**
  - Archetype and settings changes persist across cold app restarts.
  - Backend `GET /v1/users/me` reflects updated `style_profile` and `settings`.

---

#### Feature P0-4: Wardrobe Photo Cloud Storage & Media Sync
- **User Problem:** Wardrobe item photos are stored solely as local cache file URIs on the user's mobile device (`file:///data/...`). If the user logs in on another device or reinstalls the app, their wardrobe items lose their garment photos.
- **Proposed User Experience:**
  - Taking a photo when adding a garment or scanning an outfit seamlessly uploads the image to Fansivibe media storage.
  - Garment cards and recommendation cards load high-fidelity cached images across any device.
- **Existing Implementation to Reuse:**
  - `wardrobe_items.image_ref` JSONB column.
  - `AddGarmentScreen` and `OutfitScanScreen` image picker logic.
- **New Frontend Work:**
  - Add multipart upload handler in `WardrobeRepository` and `OutfitScanService`.
  - Replace raw local file URI display with network image loader supporting local cached fallbacks (`CachedNetworkImage`).
- **New Backend Work:**
  - Implement `POST /v1/wardrobe/items/{id}/photo` supporting multipart form-data.
  - Implement secure local/S3/MinIO media storage provider generating authenticated access URLs.
  - Update `wardrobe_items.image_ref` with uploaded asset URL and thumbnail URL.
- **Database Changes:** None.
- **AI / Model Requirements:** None.
- **Dependencies:** FEAT-04, FEAT-05.
- **Acceptance Criteria:**
  - Uploaded garment photo generates public/signed HTTPS URL.
  - Photo renders properly in Flutter on clean install without local file cache.

---

### P1: Major User-Facing Improvements (Style Experience & Flexibility)
*Expands functionality to deliver high perceived user value and styling versatility.*

#### Feature P1-1: Interactive Outfit Component Swapping
- **User Problem:** When users receive an AI-generated outfit recommendation with 3 ideal items and 1 suboptimal item (e.g., they prefer sneakers over dress boots), they currently must either accept the entire ensemble or regenerate everything from scratch.
- **Proposed User Experience:**
  - Each item card on `OutfitRecommendationScreen` features a subtle "Swap" icon.
  - Tapping "Swap" on an item opens a bottom sheet displaying alternative items from the user's wardrobe in that category (e.g., alternative footwear).
  - Alternatives are ranked by color harmony and formality compatibility with the remaining pinned items.
  - Selecting an alternative swaps the item into the outfit in-place and recalculates the `% Ensemble Match` score.
- **Existing Implementation to Reuse:**
  - `analysis_rules.py` candidate scoring logic.
  - `outfit_recommendation_screen.dart` component card layouts.
- **New Frontend Work:**
  - Swap bottom sheet widget: `OutfitSlotSwapSheet`.
  - Dynamic slot replacement state management in `OutfitGenerationController`.
- **New Backend Work:**
  - Add `POST /v1/outfits/swap-slot` accepting `{outfit_id, pinned_item_ids: [...], target_category: "footwear"}`.
  - Invokes `analysis_rules.score_candidate()` against remaining wardrobe items.
- **Database Changes:** None.
- **AI / Model Requirements:** Candidate scoring heuristics.
- **Dependencies:** FEAT-08, FEAT-10.
- **Acceptance Criteria:**
  - Swapping an item updates the outfit card immediately.
  - Only wardrobe items matching the target category are offered as candidates.
  - Overall match score updates accurately.

---

#### Feature P1-2: Enriched Saved Look Hydration & Wardrobe Linking
- **User Problem:** Saved looks persist item IDs as raw JSON strings. On `LookDetailsScreen`, items are displayed without their full active wardrobe metadata (e.g. brand, current wear count, last worn date), disconnecting saved looks from active wardrobe management.
- **Proposed User Experience:**
  - Tapping a saved look loads fully hydrated item cards with brand, tags, and current wear counters.
  - If a wardrobe item was deleted after the look was saved, the UI gracefully flags the item as "Archived Garment" rather than breaking.
  - User can tap any item in the saved look to navigate directly to its `WardrobeItemDetailsScreen`.
- **Existing Implementation to Reuse:**
  - `GET /v1/looks/saved` (`app/api/routers/saved_looks.py`).
  - `LookDetailsScreen` in `lib/features/saved_looks/presentation/screens/look_details_screen.dart`.
- **New Frontend Work:**
  - Cross-reference saved look `items` list with `WardrobeRepository` cache.
  - Render rich garment cards with navigation hooks.
- **New Backend Work:**
  - Add `?include_items=true` parameter to `GET /v1/looks/saved` to return populated item objects in the response.
- **Database Changes:** None.
- **AI / Model Requirements:** None.
- **Dependencies:** FEAT-04, FEAT-15.
- **Acceptance Criteria:**
  - Saved look displays item names, photos, and categories instead of UUIDs.
  - Tapping an item navigates to wardrobe item details.

---

#### Feature P1-3: Weather-Aware Location Seeding for Daily Looks
- **User Problem:** Today's Look currently relies on static default weather parameters (temperature: 20°C, condition: "clear"). It does not adapt to actual local meteorological conditions (e.g. rain, snow, high heat).
- **Proposed User Experience:**
  - DailyOutfitScreen requests location permission (or allows setting a default city in Settings).
  - Automatically fetches local weather (temperature, precipitation, wind).
  - Daily look prioritizes rainwear for stormy days or breathable linens for hot days, displaying a weather chip: *"Curated for 14°C & Light Rain in London"*.
- **Existing Implementation to Reuse:**
  - Weather temperature and condition scoring logic in `analysis_rules.py`.
- **New Frontend Work:**
  - Client-side weather fetching or GPS coordinates transmission to `today_service.dart`.
  - Weather summary chip on `DailyOutfitScreen`.
- **New Backend Work:**
  - Integrate lightweight weather proxy endpoint `GET /v1/weather/forecast` or accept `lat`/`lon` on `GET /v1/looks/today`.
- **Database Changes:** None.
- **AI / Model Requirements:** None.
- **Dependencies:** FEAT-08, FEAT-14.
- **Acceptance Criteria:**
  - Recommendations reflect precipitation and temperature constraints.
  - Appropriate outerwear is recommended when temperature < 15°C.

---

### P2: Advanced AI & Personalization (Deep Style Intelligence)
*Delivers cutting-edge personalization and visual AI capabilities.*

#### Feature P2-1: Closed-Loop Stylist Preference Learning
- **User Problem:** User reactions (likes, dislikes, logged wears) on outfits are stored in database records but do not alter future candidate rankings.
- **Proposed User Experience:**
  - Stylist gets progressively smarter: if a user consistently dislikes double-breasted blazers or frequently wears dark denim, the recommendation engine dynamically adjusts weighting coefficients to align with observed behavior.
- **Technical Scope:** Incorporate feedback history into `analysis_rules.py` scoring pipeline; calculate preference vectors from `learning_feedback`.
- **Dependencies:** FEAT-08, FEAT-15, FEAT-18.

#### Feature P2-2: Multi-Item Wardrobe Batch Ingestion
- **User Problem:** Manually adding 40+ wardrobe items one-by-one is tedious.
- **Proposed User Experience:**
  - User takes multiple photos or uploads a batch of closet photos; Ollama vision classifies and segments items into a staging queue for one-tap approval.
- **Technical Scope:** Batch vision worker; background classification queue; Flutter staging review screen.
- **Dependencies:** FEAT-04, FEAT-11.

#### Feature P2-3: Generative Virtual Try-On Pipeline (Stage F1)
- **User Problem:** Try-On is currently a placeholder canvas with synthetic SVG "TEST DATA".
- **Proposed User Experience:**
  - User uploads a full-body reference photo. Selected outfit items are realistically warped and blended onto their body silhouette using diffusion models.
- **Technical Scope:** Asynchronous diffusion/warping pipeline integration (IDM-VTON / ComfyUI); job queue management (`try_on_jobs`); result polling and caching.
- **Dependencies:** FEAT-04, FEAT-10, FEAT-19.

---

### P3: Future Enhancements (Scale, Monetization & Ecosystem)
*Longer-term commercial and platform initiatives.*

1. **P3-1: In-App Purchases & Subscription Billing:** Stripe / RevenueCat integration for Pro and Atelier tiers.
2. **P3-2: Calendar Sync & Trip Packing Assistant:** Auto-sync calendar events and generate multi-day trip packing checklists.
3. **P3-3: Live Stylist Support & Community Sharing:** In-app styling consultations and lookbook sharing.
4. **P3-4: Discovery Commerce & Affiliate Purchasing:** Activation of Decision M14 once commercial affiliate network contracts are executed.

---

## 4. Stage 2 Implementation Phases & Sequencing

```
+-------------------------------------------------------------------------------+
|  PHASE 2.1: INTEGRITY & CORE RETENTION LOOP (Sprints 1 - 2)                   |
|  - P0-1: Multi-Item Outfit Wear Logging (Immediate First Feature)             |
|  - P0-2: Authenticated Grooming Analysis & Profile Repair                     |
|  - P0-3: Style Preferences & Application Settings Persistence                 |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|  PHASE 2.2: MEDIA & ENRICHED STYLE EXPERIENCE (Sprints 3 - 4)                 |
|  - P0-4: Wardrobe Photo Cloud Storage & Media Sync                            |
|  - P1-1: Interactive Outfit Component Swapping                                |
|  - P1-2: Enriched Saved Look Hydration & Wardrobe Linking                     |
|  - P1-3: Weather-Aware Location Seeding for Daily Looks                       |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|  PHASE 2.3: ADVANCED PERSONALIZATION & INTELLIGENCE (Sprints 5 - 6)           |
|  - P2-1: Closed-Loop Stylist Preference Learning                              |
|  - P2-2: Multi-Item Wardrobe Batch Ingestion                                  |
|  - P2-3: Generative Virtual Try-On Scaffolding (Stage F1)                     |
+-------------------------------------------------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|  PHASE 2.4: MONETIZATION & ECOSYSTEM EXPANSION (Sprints 7+)                   |
|  - P3-1: In-App Purchases & Subscriptions                                     |
|  - P3-2: Calendar Sync & Packing Assistant                                    |
|  - P3-4: Discovery Commerce Activation (Subject to M14 resolution)            |
+-------------------------------------------------------------------------------+
```
