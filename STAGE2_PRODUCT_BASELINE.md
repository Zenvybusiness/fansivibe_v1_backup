# Fansivibe — Stage 2: Product Baseline Assessment

**Status:** COMPLETE — Authoritative Technical & Architectural Baseline  
**Date:** 2026-10-31  
**Scope:** Static, evidence-based baseline of the complete Fansivibe application following Stage 1D closure  
**Branch:** `main` (clean working tree with preserved Stage 1D changes)

---

## 1. Executive Summary

Stage 1D successfully achieved foundational hardening of Fansivibe's person model, recommendation integrity, privacy partitioning, and conversational AI assistant. All 11 batches of Stage 1D (Batches 1A through 4B.4 plus 4B.5 final audit) were verified with 446 passing backend tests, 337 passing Flutter tests, clean static analysis (`flutter analyze` 0 issues), and zero unapproved schema or contract migrations.

Fansivibe is now transitioning into **Stage 2: User-Facing Product Development**.

This document establishes the verified technical baseline of the repository across:
1. Flutter client application structure and navigation.
2. FastAPI backend API architecture and endpoints.
3. PostgreSQL database schema, tables, and relationships.
4. Authentication and guest-user flows.
5. Wardrobe management and garment records.
6. AI Stylist and recommendation systems.
7. Outfit Builder and Outfit Scan capabilities.
8. Hairstyle and grooming features.
9. AI image processing and local model integrations.
10. User profile and appearance data persistence.
11. Existing screens, incomplete features, placeholders, and broken user journeys.

---

## 2. Comprehensive Architectural Baseline

### 2.1 Flutter Application Structure and Navigation

- **Location:** [`newproject/flutter_application_1/lib/`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib)
- **Framework & State Management:** Flutter 3.x (Dart 3.x). State management utilizes scoped `ChangeNotifier` / `ListenableBuilder`, repository injection, and reactive session listeners (`AuthSession.authVersion`).
- **Routing Architecture:** Centrally managed declarative routing using `package:go_router` (DEC-008).
  - Central Route Registry: [`route_names.dart`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/app/router/route_names.dart) defines 37 static route name constants.
  - Router Configuration: [`app_router.dart`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/app/router/app_router.dart) defines the `GoRouter` instance with `initialLocation: '/entry'`.
  - Declarative Auth Guard: [`auth_guard.dart`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/app/router/auth_guard.dart) enforces zero-network synchronous redirection. Authenticated sessions on auth-only routes (`/entry`, `/sign-in`, `/create-account`, `/onboarding/account`) redirect to `/home`. Unauthenticated navigation to shell routes redirects to `/entry`. Explicit guests (`LocalStorage.savedLocally == true`) are permitted to browse all 5 shell tabs and `/assistant`, but are blocked from `/reasoning`.
- **Navigation Shell:** `StatefulShellRoute.indexedStack` maintains persistent tab state across 5 primary tabs:
  1. **Home (`/home`):** `HomeScreen`, with nested routes `/home/daily-outfit` (`DailyOutfitScreen`) and `/home/try-on` (`TryOnScreen`).
  2. **Discover (`/discover`):** `DiscoverScreen`, with nested route `/discover/look-details` (`LookDetailsScreen`).
  3. **Stylist (`/stylist`):** `StylistScreen`, with nested flows for Outfit Scan (`scanOutfit` -> `scanProcessing` -> `scanAnalysis`), Outfit Builder (`buildOutfit` -> `outfitGeneration` -> `outfitRecommendation`), Hairstyle (`hairstyle` -> `hairstyleProcessing` -> `hairstyleResult` -> `hairstyleDetails`), Grooming (`grooming` -> `groomingProcessing` -> `groomingResult` -> `groomingDetails`), and Events (`events` -> `eventAdd` / `eventDetails` / `eventEdit`).
  4. **Wardrobe (`/wardrobe`):** `WardrobeScreen`, with nested routes `/wardrobe/add-category` (`AddWardrobeCategoryScreen`), `/wardrobe/add-item` (`AddWardrobeItemScreen`), and `/wardrobe/item-details` (`WardrobeItemDetailsScreen`).
  5. **Profile (`/profile`):** `ProfileScreen`, with nested routes `/profile/preferences` (`PreferencesScreen`), `/profile/saved-looks` (`SavedLooksScreen`), `/profile/subscription` (`SubscriptionScreen`), `/profile/support` (`SupportScreen`), and `/profile/settings` (`SettingsScreen`).
- **Ubiquitous Action:** `FloatingAssistantButton` mounted directly on `RouterShell` ([`router_shell.dart:19`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/app/router/router_shell.dart#L19)), providing instant access to `/assistant` from any primary screen.
- **Design System ("Digital Atelier"):** Implemented via custom design tokens:
  - `FansivibeColors`: Dark luxury palette (Background `#0D0D0E`, Surface `#141416`, Accent Gold `#C5A059`, Success `#4E9F6E`, Warning `#D99B36`, Error `#CF4B4B`).
  - `FansivibeTypography`: Serifs for titles, sans-serifs for body/metrics.
  - `FansivibeSpacing` & `FansivibeRadius`: Strict scale (8px, 12px, 16px, 20px, 24px).
  - Visual Proportions: 65% visual / 35% content card layout enforced across recommendations.

---

### 2.2 Backend API Architecture and Endpoints

- **Location:** [`backend/app/`](file:///home/tony/projects/fansivibe_v1_backup/backend/app)
- **Framework:** Python FastAPI with Pydantic v2 schemas and SQLAlchemy 2.0.
- **Application Lifespan:** [`main.py:74-96`](file:///home/tony/projects/fansivibe_v1_backup/backend/app/main.py#L74-L96) initiates background model warmups and Ollama probes on startup.
- **Security & Telemetry Middleware:** Injects correlation ID (`X-Request-Id`), security headers (`nosniff`, `DENY`, `strict-origin-when-cross-origin`, HSTS), and records HTTP request metrics.
- **Mounted Routers (16 Total):**
  1. `auth` (`/v1/auth`): `POST /register` (201, Idempotency-Key), `POST /login` (200), `POST /logout` (204), `POST /social` (502 intentionally).
  2. `users` (`/v1/users`): `GET /me` (200), `PATCH /me` (200, updates `preferred_occasions`), `DELETE /me` (204 cascade).
  3. `wardrobe` (`/v1/wardrobe`): `GET /items` (200 paged), `POST /items` (201), `GET /items/{id}` (200), `PATCH /items/{id}` (200), `DELETE /items/{id}` (204), `GET /insight` (200/204), `POST /wears` (201, Idempotency-Key), `GET /wears` (200 paged), `GET /wear-summary` (200).
  4. `outfits` (`/v1/outfits`): `POST /generate` (200/204, derives ensemble), `POST /saved` (201, freezes outfit).
  5. `analysis` (`/v1/analysis`): `POST /hairstyle` (202), `POST /grooming` (202), `POST /outfit` (202), `POST /garment` (202), `GET /runs/{run_id}` (200), `GET /runs` (200 paged), `POST /hairstyle/ephemeral` (200 sync guest), `POST /outfit/ephemeral` (200 sync guest), `POST /grooming/ephemeral` (200 sync guest), `POST /garment/ephemeral` (200 sync guest).
  6. `looks` (`/v1/looks`): `GET /today` (200/404), `POST /today` (200/404 regenerate), `POST /today/save` (201), `POST /saved` (201), `GET /saved` (200 paged), `DELETE /saved/{id}` (204), `GET /` (200 Discover catalog feed), `GET /for-you` (200 personalized feed), `GET /{look_id}` (200 look details).
  7. `events` (`/v1/events`): `POST /` (201), `GET /` (200 upcoming window), `PUT /{id}` (200 full replace), `DELETE /{id}` (204), `POST /{id}/outfit` (200/204 event outfit).
  8. `assistant` (`/v1/assistant`): `POST /feedback` (204 suggestion feedback), `POST /chat-with-image` (200 multipart garment chat), `POST /chat` (200 in `main.py`).
  9. `learning` (`/v1/learning`): `GET /summary` (200 derived style score, streak, breakdown).
  10. `feedback` (`/v1/feedback`): `POST /` (204 reaction).
  11. `knowledge` (`/v1/knowledge`): `GET /looks`, `GET /categories`, `GET /colors`, `GET /occasions`, `GET /items`, `GET /ffo`.
  12. `reasoning` (`/v1/reasoning`): `POST /` & `POST /query` (200 grounded fashion reasoning over FFO corpus).
  13. `discovery` (`/v1/discovery`): `GET /for-you`, `GET /looks/complete`, `GET /trending`, offers, click attribution, events batch ingest.
  14. `trending` (`/v1/trending`): `GET /`, `GET /{trend_id}`.
  15. `trend_analysis` (`/v1/trends`): `GET /analysis`.
  16. `tryon` (`/v1/tryon`): `POST /jobs` (202 mock submission), `GET /jobs/{id}` (200 poll), `GET /jobs/{id}/image` (mock SVG).

---

### 2.3 PostgreSQL Database Schema and Relationships

- **Database Engine:** PostgreSQL 15+ (SQLAlchemy 2.0 ORM, psycopg3 binary driver).
- **Migration State:** Alembic migration chain with 31 revision scripts (`0001` through `0032_offer_click_attribution.py`). Migration head strictly `0032` (dev DB head `0029`).
- **Core Database Entities (32 Tables):**
  1. **Users & Auth:** `users` (id, email, password_hash, display_name), `user_sessions` (session_id, user_id, token_hash, expires_at), `user_state` (user_id PK/FK, `style_profile` JSONB, `preferences` JSONB, `version` INT for CAS).
  2. **Wardrobe System:** `wardrobe_categories` (code, label, sort_order), `colors` (code, label, hex), `materials` (code, label), `wardrobe_items` (id UUID PK, user_id FK, name, category, color, material, is_favorite, fit, fit_confidence, image_ref JSONB sidecar, timestamps), `wardrobe_wear_groups` (id UUID PK, user_id FK, idempotency_key UNIQUE, item_ids JSONB, worn_at), `wardrobe_wear_events` (id UUID PK, wardrobe_item_id FK, user_id FK, wear_group_id FK, worn_at).
  3. **Analysis & Vision Runs:** `run_types`, `analysis_runs` (id UUID PK, user_id FK, run_type, status, engine_version, knowledge_version, input_media JSONB MediaRef, result JSONB, error JSONB, idempotency_key).
  4. **Looks & Saves:** `looks` (catalog looks), `saved_looks` (id UUID PK, user_id FK, look_id, title, source_context: hairstyle/grooming/outfit/daily, snapshot JSONB with selectedItemIds, source_run_id).
  5. **Signals & Telemetry:** `signal_types`, `learning_signals` (id, user_id FK, signal_type, context JSONB, created_at), `activity_days` (user_id FK, day DATE, UNIQUE), `feedback_events` (id, user_id FK, rating, reason, target_look_id, target_saved_look_id).
  6. **Calendar & Events:** `event_types` (code, label, sort_order), `user_events` (id UUID PK, user_id FK, event_type_id FK, title, event_date DATE, event_time TIME, location, notes).
  7. **Discovery & Commerce:** `products`, `product_source_map`, `product_observations`, `search_interest_observations`, `media_attention_observations`, `media_attention_contributing_records`, `discovery_events`, `retailers`, `product_variants`, `retailer_offers`, `offer_price_history`, `collection_runs`, `raw_source_records`.

---

### 2.4 Authentication and Guest-User Flows

- **Authentication Protocol:** Custom secure bearer-token session model (`D-AUTH-1`). Password hashing via `bcrypt`, session resolution via `user_sessions` table.
- **Guest Separation (Founder Decision D10 Option A):**
  - Unauthenticated users can choose "Continue Without Account" on `/entry` or `/onboarding/result`.
  - Sets `LocalStorage.savedLocally = true`.
  - Guest users are assigned zero database identity (`user_id = None`), zero database writes, and zero appearance persistence.
  - Ephemeral repository adapters (`EphemeralWardrobeItemRepository`, `EphemeralUserStateRepository`) handle guest outfit generation in memory.
  - Guest analysis execution runs via synchronous endpoints (`POST /v1/analysis/*/ephemeral`), returning analysis results without persisting database run rows.
- **Guest-to-Authenticated Conversion Flow:**
  - When a guest subsequently registers or signs in, [`post_auth_flow.dart:36-84`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/auth/presentation/post_auth_flow.dart#L36-L84) triggers `handlePostAuthConversion`.
  - Detects unmigrated device-local items (`local-*`) and preferred occasions.
  - Prompts user with `showGuestMergeDialog` offering three explicit choices: **Merge** (uploads wardrobe via `WardrobeRepository.createItem` and syncs occasions), **Keep on Device** (no upload), or **Discard** (clears device items).
  - Biometric and face appearance data are strictly excluded from migration per D10 Option A.

---

### 2.5 Wardrobe Management and Garment Records

- **Server-Side Capabilities:** Full CRUD operations over `wardrobe_items`.
- **Filtering & Search:** Supports filtering by category and color codes, sorting by `created_at`, `updated_at`, `name`, and offset pagination (`page`, `page_size`).
- **Controlled Vocabulary:** Strict server validation against `wardrobe_categories` (`tops`, `bottoms`, `outerwear`, `footwear`, `accessories`), `colors`, and `materials`.
- **Garment Metadata:** Preserves `name`, `category`, `color`, `material`, `is_favorite`, `fit` (Slim, Regular, Relaxed, Oversized, Tailored, Loose), `fit_confidence`, and `image_ref` JSONB sidecar.
- **Wear Tracking Architecture (STEP 15.4B & 17.2):**
  - Durable wear group ledger (`wardrobe_wear_groups`) guarantees idempotency.
  - Item-level events (`wardrobe_wear_events`) track individual garment wears.
  - Read-only wear summary endpoint (`GET /v1/wardrobe/wear-summary`) exposes wear counts, last worn dates, most worn, least worn, unworn, and category frequency.
- **Client Presentation:**
  - `WardrobeScreen` renders category tabs, item grid/list, wardrobe health insight card, and wear summary card.
  - `AddWardrobeItemScreen` supports manual garment entry as well as pre-filling from Outfit Scan observations (`AddWardrobeItemArgs`).
  - `WardrobeItemDetailsScreen` displays garment attributes and provides a single-item "I wore this today" action button.

---

### 2.6 AI Stylist and Recommendation System

- **Canonical Recommendation Engine:** [`GenerateOutfit`](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/outfits.py) use case and [`analysis_rules.py`](file:///home/tony/projects/fansivibe_v1_backup/backend/app/domain/services/analysis_rules.py).
- **12-Term Candidate Scoring Pipeline:**
  1. Hard constraint validation: mandatory top + bottom.
  2. Occasion alignment points (`_occasion_points`, +5.0 pts).
  3. Body fit harmony (`_fit_points`, +5.0 pts).
  4. Palette compatibility (`_palette_points`, +5.0 pts).
  5. Color harmony scoring (monochromatic, complementary, analogous).
  6. Material compatibility.
  7. Saved looks positive reinforcement (+0.03 pts).
  8. Wear frequency decay / penalty for over-worn garments.
  9. Favorite item boost.
  10. Seasonality matching.
  11. Contrast and visual balance.
  12. Negative feedback suppression.
- **Deterministic Selection:** `select_best_outfit_candidate` guarantees reproducible winners across identical inputs.
- **Conversational Assistant Harmonization:**
  - `assistant_chat` in `main.py` delegates directly to `GenerateOutfit.derive_with_reason`.
  - Both `reply.cards` and `reply.outfitIntelligence` populate from the same single execution.
  - Authenticated turns strictly derive wardrobe and profile from PostgreSQL.
  - Guest turns execute over in-memory ephemeral adapters.
  - Empty or invalid wardrobe states return typed error cards without synthetic garment fabrication.

---

### 2.7 Outfit Builder and Outfit Scan

- **Outfit Builder Flow:**
  - Input: `BuildOutfitScreen` captures occasion, mood, preferred fit, color palette, and optional `preferredItemId`.
  - Occasion context transparency notice: Discloses that occasion is factored into recommendation while date/time/location are not.
  - Derivation: `OutfitGenerationScreen` calls `POST /v1/outfits/generate`.
  - Recommendation Display: `OutfitRecommendationScreen` renders title, `% Ensemble Match` score, component items with grounded reasons, color harmony, body fit, occasion match, and improvement suggestion.
  - Actions: "Save Outfit" (`POST /v1/outfits/saved`), "Regenerate" (variant seeds), "Try On (Test Preview)".
- **Outfit Scan Flow:**
  - Capture: `OutfitScanScreen` captures or selects garment/outfit photo.
  - Processing: `OutfitProcessingScreen` invokes `POST /v1/analysis/outfit` (authenticated) or `POST /v1/analysis/outfit/ephemeral` (guest).
  - Vision Execution: Concurrently evaluates appearance (face shape) via `OllamaVisionAppearanceAdapter` and garment attributes via `OllamaVisionGarmentAdapter`.
  - Analysis Results: `OutfitAnalysisScreen` displays detected garment observations with AI estimate confidence badges, review status (`Needs Review` vs `Confirmed`), and prefilled "Add to Wardrobe" button. Displays person appearance attributes with verified "Save Appearance Profile" persistence status (`profile_persistence`).

---

### 2.8 Hairstyle and Grooming Features

- **Hairstyle Recommendation:**
  - Capture: `FaceScanScreen` supports single portrait photo or guided 3-angle captures (front, left, right).
  - Processing: `FaceProcessingScreen` executes `HairstyleService` calling `POST /v1/analysis/hairstyle` or `POST /v1/analysis/hairstyle/ephemeral`.
  - Vision & Rules: `OllamaVisionAppearanceAdapter` determines face shape. Canonical `analysis_rules.recommend_hairstyle` ranks hairstyles from catalog based on face shape compatibility and saved looks. Zero fabrication: unmeasured face shape never defaults to oval.
  - Results: `HairstyleResultScreen` displays top recommendation and alternatives with semantic confidence badges (`High / Moderate / Limited Confidence`), grounded reasons, and "Save Style" action (`POST /v1/looks/saved`).
- **Grooming Recommendation:**
  - Input: `GroomingInputScreen` allows manual chip selection of face shape, beard style, beard density, and beard color.
  - Canonical Ranking: `grooming_rules.recommend_grooming` ranks beard and eyewear styles from catalog.
  - Results: `GroomingResultScreen` and `GroomingDetailsScreen` display match scores, grooming specifications, and grounded reasons.

---

### 2.9 AI Image Processing and Local Model Integrations

- **Local Inference Engine:** Ollama instance running locally (default `http://localhost:11434`).
- **Qualified Models:**
  - Vision: `qwen2.5vl:3b` in active local deployment (or `llama3.2-vision` fallback).
  - Fashion Reasoning: `qwen2.5vl:3b` qualified per DEC-030 (with strict FFO contract validation). Note: `qwen3-vl:4b-instruct` was disqualified due to empty-string abstention failures and OOM crashes on 6 GB hardware.
- **Vision Adapters:**
  - `OllamaVisionAppearanceAdapter`: Sends raw image bytes to model with strict JSON prompt; extracts `face_shape` and `confidence` (floor 0.35); maps to canonical 6 face shapes; fails closed on missing face or ambiguous subjects.
  - `OllamaVisionGarmentAdapter`: Sends raw image bytes to model with structured garment prompt; extracts `category`, `subcategory`, `color`, `pattern`, `material`, `style`, `fit`, `confidence`; coerces unknown categories to null without failing.
- **Reasoning Pipeline (`FashionReasoner`):** Grounded in 26 formal schemas of the Fansivibe Fashion Ontology (`backend/app/data/ffo`), validating statements, evidence IDs, and versions before emitting structured reasoning.
- **Try-On Scaffolding:** Stage F0 mock implementation in `tryon.py` and `TryOnScreen`. Generates synthetic SVG labeled "TEST DATA". No commercial or local generative try-on model is integrated yet.

---

### 2.10 User Profile and Appearance Data

- **Storage Entity:** `user_state` table in PostgreSQL.
- **Attributes Structure:**
  - `style_profile`: JSONB containing `face_shape`, `skin_tone`, `body_type`, `style_type`, and `source_run_id`.
  - `preferences`: JSONB containing `preferred_occasions` and optional styling constraints.
  - `version`: Integer column providing atomic optimistic concurrency control (CAS).
- **Field-Level Provenance:** `_provenance_{attr}` tracks whether an attribute was confirmed by user or inferred by AI. User-confirmed attributes are protected against lower-confidence overwrites.
- **Style Score Calculation (DEC-020):**
  - Base: 60 points.
  - Wardrobe Points: 1 point per owned item, capped at 20 points.
  - Saved Points: 2 points per saved look, capped at 20 points.
  - Total Style Score: 60 to 100 points.
  - Style Streak: Consecutive active calendar days recorded in `activity_days`.
- **Client Profile Screen:** [`profile_screen.dart`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/profile/presentation/profile_screen.dart) hydrates from `GET /v1/users/me`, `GET /v1/learning/summary`, `GET /v1/looks/saved`, and `GET /v1/wardrobe/items`. Displays Style DNA, Style Score breakdown, wardrobe counts, and saved looks.

---

### 2.11 Existing Screens, Incomplete Features, Placeholders, and Broken User Journeys

The static source-code audit identified the following concrete gaps, placeholders, and broken journeys:

1. **Broken Journey: Authenticated Grooming Input Bypass:**
   - *Evidence:* In [`grooming_input_screen.dart:55-63`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/grooming/presentation/grooming_input_screen.dart#L55-L63), the user selects face shape, beard style, density, and color. However, in [`grooming_processing_screen.dart:78-95`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/grooming/presentation/grooming_processing_screen.dart#L78-L95), `_runAuthenticated()` executes `_service.runAnalysis()` which takes **no parameters** and calls backend `POST /v1/analysis/grooming` with empty body. In [`backend/app/application/analysis.py:743-744`](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/analysis.py#L743-L744), `CreateGroomingRun` inspects `user_state.style_profile` and raises `422 INSUFFICIENT_USER_DATA` if `face_shape` is missing.
   - *User Impact:* Authenticated users who enter their grooming preferences manually on screen get an immediate failure if they haven't completed a face scan, despite having explicitly chosen their face shape on the previous screen.

2. **Placeholder Feature: Virtual Try-On (Stage F0 Scaffolding):**
   - *Evidence:* [`tryon.py:1-13`](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/routers/tryon.py#L1-L13) and [`try_on_screen.dart:18-29`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/try_on/presentation/try_on_screen.dart#L18-L29).
   - *User Impact:* The "Try On" button produces an SVG labeled "TEST DATA" with mock visual composite. No genuine diffusion or generative try-on pipeline exists.

3. **Placeholder Screen: Subscription (`/profile/subscription`):**
   - *Evidence:* [`subscription_screen.dart:13-14, 196-224`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/profile/presentation/subscription_screen.dart#L13-L14). Renders static mock data (`ProfileMockData.plans`). The "Subscribe" button has an empty callback `onPressed: () {}`.
   - *User Impact:* Users cannot view live subscriptions, upgrade, or manage billing.

4. **Placeholder Screen: Support (`/profile/support`):**
   - *Evidence:* [`support_screen.dart:13, 106, 135`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/profile/presentation/support_screen.dart#L13). Renders static topics and a "Send us a message" tile with empty callbacks `onTap: () {}`.
   - *User Impact:* Users cannot contact support, report bugs, or submit inquiries.

5. **Placeholder Screen: Settings (`/profile/settings`):**
   - *Evidence:* [`settings_screen.dart:19, 79-90`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/profile/presentation/settings_screen.dart#L19). Switches toggle local widget state in memory without persisting to backend or local storage.
   - *User Impact:* Settings reset on app reload; notifications, dark mode, and privacy toggles are non-functional.

6. **Partially Implemented Screen: Preferences (`/profile/preferences`):**
   - *Evidence:* [`preferences_screen.dart:18-29, 92-100`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/profile/presentation/preferences_screen.dart#L18-L29). Only "Occasion Focus" syncs to backend `preferred_occasions` via `PATCH /v1/users/me`. All other style preferences (palette, fit, vibe) remain local mock options.

7. **Incomplete Action: "Wear This Look" on Daily Outfit & Recommendations:**
   - *Evidence:* In [`daily_outfit_screen.dart`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/home/presentation/daily_outfit_screen.dart), tapping "Wear This" shows a snackbar but does not log a wear action (DEC-012 deferred multi-item wear capture). In [`outfit_recommendation_screen.dart`](file:///home/tony/projects/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/outfit_builder/presentation/outfit_recommendation_screen.dart), there is no wear logging affordance at all.
   - *User Impact:* While the backend has a complete multi-item wear ledger (`POST /v1/wardrobe/wears`), wear logging is restricted to single items on `WardrobeItemDetailsScreen`. Users cannot record wearing an entire recommended outfit from the daily or builder screens.

8. **Missing Feature: Outfit Component Swapping:**
   - *Evidence:* Documented in `PRODUCT_BLUEPRINT.md` and `SCREEN_MAP.md` as "Replace Component". Does not exist in `OutfitRecommendationScreen` or `DailyOutfitScreen`. Users must either accept all components or regenerate the entire look.

---

## 3. Baseline Summary Matrix

| Capability Domain | Implementation Status | Technical Maturity | Primary Artifacts |
| :--- | :--- | :--- | :--- |
| **Declarative Router & Shell** | Complete & Verified | Production Ready | `app_router.dart`, `route_names.dart`, `auth_guard.dart` |
| **Authentication & Sessions** | Complete & Verified | Production Ready | `routers/auth.py`, `AuthSession.dart`, `users.py` |
| **Guest Separation (D10 Option A)**| Complete & Verified | Production Ready | `ephemeral_*.py`, `your_analysis_screen.dart` |
| **Wardrobe Management (CRUD)** | Complete & Verified | Production Ready | `routers/wardrobe.py`, `wardrobe_screen.dart` |
| **Wear Logging & Summary (Single)** | Complete & Verified | Production Ready | `wardrobe_wear_*.py`, `wear-summary` |
| **Multi-Item Outfit Wear Logging** | Backend Ready / UI Missing | High (Backend) / Gap (UI) | `routers/wardrobe.py:321`, `daily_outfit_screen.dart` |
| **Outfit Generation & Scoring** | Complete & Verified | Production Ready | `GenerateOutfit`, `analysis_rules.py` |
| **Outfit Builder UI Flow** | Complete & Verified | Production Ready | `build_outfit_screen.dart`, `outfit_recommendation_screen.dart` |
| **Outfit Scan & Garment Extraction**| Complete & Verified | Production Ready | `analysis.py`, `outfit_analysis_screen.dart` |
| **Hairstyle Recommendations** | Complete & Verified | Production Ready | `hairstyle_result_screen.dart`, `analysis_rules.py` |
| **Grooming Recommendations** | Implemented (Auth Gap) | Functional with defect | `grooming_result_screen.dart`, `grooming_input_screen.dart` |
| **Today's Look (Home Feed)** | Complete & Verified | Production Ready | `looks.py:today`, `daily_outfit_screen.dart` |
| **Saved Looks Collection** | Complete & Verified | Production Ready | `looks.py:saved`, `saved_looks_screen.dart` |
| **Fashion Reasoning (FFO/Ollama)** | Complete & Verified | Production Ready | `reasoning.py`, `fashion_reasoning_screen.dart` |
| **Event Planning Flow** | Complete & Verified | Production Ready | `routers/events.py`, `event_list_screen.dart` |
| **Preferences Screen** | Partial | Partial | `preferences_screen.dart`, `users.py:PATCH` |
| **Virtual Try-On** | UI Only / Mock Scaffolding | Mock Only | `tryon.py`, `try_on_screen.dart` |
| **Subscription & Billing** | UI Only / Placeholder | Non-functional | `subscription_screen.dart` |
| **Support & Inquiries** | UI Only / Placeholder | Non-functional | `support_screen.dart` |
| **Application Settings** | UI Only / Placeholder | Non-functional | `settings_screen.dart` |
