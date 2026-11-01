# Fansivibe Stage 1 — Existing Capabilities Report

**Document Type:** Reusable Architecture and Shipped Capability Catalog  
**Date:** 2026-10-31  
**Repository:** `/home/tony/projects/fansivibe_v1_backup`  
**Committed Baseline:** Commit `97f6ded99d3f3e67b477616380320058cd396f48` (`main`)  
**Methodology:** Static code, schema, and API route inspection.

---

## 1. Executive Overview

Fansivibe contains substantial, robustly engineered production capabilities across its backend and Flutter client. Rather than needing a rewrite, the platform possesses core engines that can be directly reused for Stage 1. 

Key capabilities confirmed operational in the codebase:
- A deterministic 9-stage Decision Engine (`backend/app/domain/services/analysis_rules.py`).
- Real computer vision adapters for facial geometry (`VisionAppearanceAnalysisAdapter`) and garment analysis (`VisionGarmentAnalysisAdapter`).
- Shipped Outfit Scan garment observation (commit `97f6ded`).
- Multi-retailer e-commerce offer catalog and product redirection (`0031`, `0032`).
- Comprehensive wardrobe management with wear tracking and fit confidence (`0023`).
- Client-generated idempotency keys on all analysis submissions (`0025`).
- Digital Atelier UI system with strict 65% visual / 35% content card proportions.

Below is an exhaustive catalog of what Fansivibe already possesses, where each component resides, and the specific limitations to address.

---

## 2. Capability Catalog

### 2.1 Person and Profile Data

#### What It Does
- Persists user authentication identity, display name, account status, and timestamps.
- Manages user style profile, preferences, and flags in structured JSONB columns on `user_state`.
- Merges partial appearance updates without overwriting existing non-empty attributes.
- Exposes profile read (`GET /v1/users/me`), preferences update (`PATCH /v1/users/me`), and account erasure (`DELETE /v1/users/me`).

#### Where It Lives
- **Database Models**:
  - `backend/app/infrastructure/db/models.py::Users` (table `users`, lines 92–115)
  - `backend/app/infrastructure/db/models.py::UserState` (table `user_state`, lines 118–132)
- **Repositories**:
  - `backend/app/infrastructure/db/repositories.py::UserStateRepositorySQL` (lines 265–350)
  - `backend/app/infrastructure/db/repositories.py::AuthRepositorySQL`
- **Application Services**:
  - `backend/app/application/users.py::GetProfile`
  - `backend/app/application/users.py::UpdatePreferences`
  - `backend/app/application/auth.py::DeleteAccount`
- **API Routers & Schemas**:
  - `backend/app/api/routers/users.py` (`get_me`, `update_me`, `delete_me`)
  - `backend/app/api/schemas/users.py::ProfileView`, `StyleProfile`
- **Flutter Client**:
  - `newproject/flutter_application_1/lib/features/profile/presentation/profile_screen.dart`
  - `newproject/flutter_application_1/lib/shared/utils/local_storage.dart`

#### Remaining Limitations
- `style_profile` is a flat JSONB object rather than a typed domain entity.
- Flutter `ProfileScreen` reads local storage (`LocalStorage.userProfile`) and `LearningService`, ignoring the backend `ProfileView.styleProfile`.
- No per-attribute provenance: single `source_run_id` covers the entire JSONB object.
- No compare-and-swap (CAS) check on `user_state.version` during profile updates.

---

### 2.2 Appearance Analysis

#### What It Does
- Accepts uploaded user images in JPEG, PNG, or WebP format up to 20 MB.
- Computes SHA-256 media hashes and constructs typed `MediaRef` structures.
- Invokes computer vision analysis through `AppearanceAnalysisPort`.
- Extracts facial geometry, specifically `face_shape` (`round`, `oval`, `square`, `rectangular`, `heart`, `diamond`).
- Fails honestly when no face is detected (`AppearanceAnalysisError("no_face_detected")`).

#### Where It Lives
- **Domain Ports & Models**:
  - `backend/app/domain/ports/external.py::AppearanceAnalysisPort`
  - `backend/app/domain/models/value_objects.py::AppearanceProfile`, `MediaRef`
- **Adapters**:
  - `backend/app/infrastructure/external/vision_appearance_adapter.py::VisionAppearanceAnalysisAdapter`
  - `backend/app/infrastructure/external/development_adapters.py::DevelopmentAppearanceAnalysisAdapter`
- **Application Services**:
  - `backend/app/application/analysis.py::CreateHairstyleImageRun`
  - `backend/app/application/analysis.py::read_image_bytes`, `build_media_ref`
- **Flutter Flow**:
  - `newproject/flutter_application_1/lib/features/onboarding/presentation/screens/photo_capture_screen.dart`
  - `newproject/flutter_application_1/lib/features/hairstyle/presentation/hairstyle_scan_screen.dart`

#### Remaining Limitations
- Only `face_shape` is populated; `skin_tone`, `body_type`, and `style_type` are forced to empty strings by adapter design.
- `AppearanceProfile` lacks an embedded confidence field; confidence is derived later during candidate scoring.
- Scoring helper functions fall back to `"oval"` if face shape is missing (`analysis_rules.py:168`).

---

### 2.3 Hairstyle and Grooming

#### What It Does
- Recommends hairstyle and grooming looks based on measured face shape and catalog compatibility rules.
- Deterministically scores catalog candidates, applying bonuses for suitable facial geometry and penalties for ill-fitting cuts.
- Returns a structured result with top recommendation, scored alternatives, styling direction, and match percentage.
- Supports saving looks directly to the user's collection via `POST /v1/looks/saved`.

#### Where It Lives
- **Domain Services**:
  - `backend/app/domain/services/analysis_rules.py::recommend_hairstyle`, `score_hairstyle_candidate`, `rank_candidates`
  - `backend/app/domain/services/grooming_rules.py::recommend_grooming`, `score_grooming_candidate`
- **Application Services**:
  - `backend/app/application/analysis.py::CreateHairstyleImageRun`, `CreateGroomingImageRun`
  - `backend/app/application/saved_looks.py::SaveLook`
- **API Routers**:
  - `backend/app/api/routers/analysis.py::analyze_hairstyle_image`, `analyze_grooming_image`
  - `backend/app/api/routers/saved_looks.py::save_look`
- **Flutter Presentation**:
  - `newproject/flutter_application_1/lib/features/hairstyle/presentation/hairstyle_result_screen.dart`
  - `newproject/flutter_application_1/lib/features/hairstyle/presentation/hairstyle_processing_screen.dart`
  - `newproject/flutter_application_1/lib/features/grooming/`

#### Remaining Limitations
- Hairstyle image scan does not consume saved looks or user preferences.
- Flutter DTO (`hairstyle_mock_data.dart`) discards backend `confidence` and `needs_more_data`.
- Grooming scan relies on request-supplied parameters without real facial hair image analysis.

---

### 2.4 Outfit Analysis

#### What It Does
- Upgraded in commit `97f6ded` (Batch 2) to execute dual independent analysis branches: appearance and garment analysis.
- Calls `GarmentAnalysisPort` to observe clothing category, primary colors, material, pattern, and fit.
- Produces composite analysis snapshot containing appearance, hairstyle direction, detected garments, and typed errors (`garment_error`, `appearance_error`).
- Flutter renders detected garments, visual chips (category, color, fit), and honest unavailable notes.

#### Where It Lives
- **Domain Ports**:
  - `backend/app/domain/ports/external.py::GarmentAnalysisPort`
  - `backend/app/domain/models/value_objects.py::GarmentProfile`
- **Adapters**:
  - `backend/app/infrastructure/external/vision_garment_adapter.py::VisionGarmentAnalysisAdapter`
- **Application Use Cases**:
  - `backend/app/application/analysis.py::CreateOutfitRun` (lines 193–415)
  - `backend/app/application/analysis.py::EphemeralOutfitAnalysis` (lines 1040–1120)
- **API Endpoints**:
  - `POST /v1/analysis/outfit` (authenticated asynchronous)
  - `POST /v1/analysis/outfit/ephemeral` (guest synchronous)
- **Flutter Presentation**:
  - `newproject/flutter_application_1/lib/features/outfit_scan/presentation/outfit_scan_screen.dart`
  - `newproject/flutter_application_1/lib/features/outfit_scan/presentation/outfit_analysis_screen.dart`

#### Remaining Limitations
- Garment observations are not persisted into a durable person model or wardrobe.
- Garment confidence and `needs_review` are not surfaced as separate UI scores.
- "Save Profile" on Outfit Analysis screen is an API no-op because appearance is saved during the run.

---

### 2.5 Wardrobe Management

#### What It Does
- Complete wardrobe inventory CRUD: add item, update item, favorite item, delete item, list items with pagination.
- Stores garment attributes: category, subcategory, primary/secondary colors, material, pattern, fit, fit_confidence, image_ref JSONB sidecar.
- Tracks item wear history and groups multi-item wear events (`WardrobeWearGroups`).
- Emits `item_added` learning signal post-commit (C-07).

#### Where It Lives
- **Database Models**:
  - `backend/app/infrastructure/db/models.py::WardrobeItems` (table `wardrobe_items`, lines 410–445)
  - `backend/app/infrastructure/db/models.py::WardrobeWearGroups`, `WardrobeWearEvents`
- **Repositories**:
  - `backend/app/infrastructure/db/repositories.py::WardrobeItemRepositorySQL`
  - `backend/app/infrastructure/db/repositories.py::WardrobeWearRepositorySQL`
- **Application Services**:
  - `backend/app/application/wardrobe.py::AddWardrobeItem`, `UpdateWardrobeItem`, `ListWardrobeItems`, `RecordWearGroup`
- **API Routers**:
  - `backend/app/api/routers/wardrobe.py`
- **Flutter Presentation**:
  - `newproject/flutter_application_1/lib/features/wardrobe/presentation/wardrobe_screen.dart`
  - `newproject/flutter_application_1/lib/features/wardrobe/presentation/add_wardrobe_item_screen.dart`

#### Remaining Limitations
- Fit attributes require `fit_confidence >= 0.6` to impact recommendation scoring.
- Pattern and style attributes are stored inside `image_ref` JSONB sidecar without first-class SQL columns.
- Manual item entry requires extensive manual dropdown selection.

---

### 2.6 Recommendation and Ranking Engine

#### What It Does
- Generates outfit candidates from owned wardrobe items across essential categories (top, bottom, footwear, optional outerwear/accessories).
- Implements bounded, deterministic scoring across 10 sub-terms:
  - Base compatibility: coverage (35), color (5), material (5), season (5), formality (5), occasion (5), palette (5), fit (5) = 70 max.
  - Preference signals: preferred items (+5 per item, cap 15), favorites (+5 per item, cap 15).
  - Feedback signals: liked look (+4/+2, cap +6), disliked look (-4/-2, floor -6).
  - Wear signals: worn combination (+2, cap 2).
  - Full candidate score clamped in [0.0, 100.0].
- Deterministic multi-stage tie-breaking: score descending, selected item count descending, canonical item ID lexical ascending.
- Surfaces grounded, human-readable explanations describing why items were paired.

#### Where It Lives
- **Domain Logic**:
  - `backend/app/domain/services/analysis_rules.py::score_outfit_candidate`, `compose_candidate_score`
  - `backend/app/domain/services/analysis_rules.py::rank_outfit_candidates`, `select_best_outfit_candidate`
  - `backend/app/domain/services/analysis_rules.py::candidate_feedback_points`, `candidate_wear_points`
- **Application Orchestration**:
  - `backend/app/application/outfits.py::GenerateOutfit.derive_with_reason`
- **API Routers**:
  - `backend/app/api/routers/outfits.py::generate_outfit`
- **Flutter UI**:
  - `newproject/flutter_application_1/lib/features/outfit_builder/presentation/outfit_generation_screen.dart`
  - `newproject/flutter_application_1/lib/features/outfit_builder/presentation/outfit_recommendation_screen.dart`

#### Remaining Limitations
- "Style Score Impact" in UI is actually the ensemble match percentage.
- `backend/app/ai/tools.py` contains hardcoded bypasses for the assistant chat that skip this engine.
- Outfit Builder does not read `style_profile` (appearance/face shape).

---

### 2.7 Knowledge and Catalog

#### What It Does
- Curated fashion knowledge system separating system-owned knowledge from user-generated data.
- System vocabulary tables (`categories`, `colors`, `occasions`, `size_categories`, `items`, `looks`).
- In-memory curated catalog (`KNOWLEDGE_VERSION = "1.1"` in `backend/app/data/catalog.py`).
- Fashion Formal Ontology (FFO) integration with cryptographic digest verification.
- System knowledge rows are immutable to user erasure (`TRX-8`).

#### Where It Lives
- **Domain Ports**:
  - `backend/app/domain/ports/external.py::KnowledgeSource`
- **Infrastructure Adapters**:
  - `backend/app/infrastructure/external/knowledge.py::CatalogKnowledgeSource`
- **Data & Seed**:
  - `backend/app/data/catalog.py`
  - `backend/alembic/versions/0001_initial_schema.py` (vocabulary tables)
- **Repositories**:
  - `backend/app/infrastructure/db/repositories.py::VocabularyRepositorySQL`, `LookRepositorySQL`

#### Remaining Limitations
- Catalog copy contains static claims ("warm medium skin tones", "your Style DNA") that are not grounded in user data.
- Dual-source reality: saves validate against static catalog, while feedback checks database `looks` table.

---

### 2.8 Feedback and Learning

#### What It Does
- Captures explicit user sentiment: `feedback_events` records like and dislike reactions with optional reasons.
- Captures wear history: `wardrobe_wear_groups` and `wardrobe_wear_events`.
- Emits structured audit signals: `learning_signals` records `look_saved`, `analysis_updated`, `outfit_selected`, `item_added`.
- Builds deterministic `FeedbackContext` to adjust candidate scoring in Outfit Builder.
- Computes Style Score (base 60 + wardrobe/look points).

#### Where It Lives
- **Database Tables**:
  - `feedback_events`, `wardrobe_wear_groups`, `wardrobe_wear_events`, `learning_signals`
- **Application Services**:
  - `backend/app/application/feedback.py::RecordFeedback`
  - `backend/app/application/learning.py::CalculateStyleScore`
- **Domain Integration**:
  - `backend/app/domain/services/analysis_rules.py::build_feedback_context`
- **Flutter UI**:
  - `newproject/flutter_application_1/lib/features/saved_looks/presentation/saved_looks_screen.dart` (like/dislike toggles)
  - `newproject/flutter_application_1/lib/features/home/presentation/widgets/backend_summary_cards.dart`

#### Remaining Limitations
- Feedback controls only exist on saved looks, not on initial recommendation screens or look details.
- `learning_signals` is write-only and never read by recommendation engines.
- Style Score is a usage/inventory counter rather than an evaluation of aesthetic quality.

---

### 2.9 Guest and Authenticated Flows

#### What It Does
- Safe architectural isolation: guests browse local wardrobe and discover feeds without session tokens.
- Ephemeral server endpoints (`POST /v1/analysis/outfit/ephemeral`) allow guest scans without database writes.
- Point-of-action sign-in prompts (`promptGuestSignIn`) capture `PendingAuthIntent`.
- Post-authentication migration (`GuestDataMigration`) transfers local wardrobe items and preferred occasions.
- Relaunch resume via `hasCachedOutfitPreview()`.

#### Where It Lives
- **Flutter Architecture**:
  - `newproject/flutter_application_1/lib/shared/utils/guest_mode.dart`
  - `newproject/flutter_application_1/lib/shared/utils/pending_auth_intent.dart`
  - `newproject/flutter_application_1/lib/features/auth/data/guest_data_migration.dart`
  - `newproject/flutter_application_1/lib/features/auth/presentation/post_auth_flow.dart`
- **Backend Protection**:
  - `backend/app/api/deps.py::get_current_user_id` (JWT requirement)
  - `backend/app/api/routers/analysis.py` (separate ephemeral routes)

#### Remaining Limitations
- Guest onboarding analysis is never persisted server-side.
- Guest migration explicitly discards face attributes, style type, and analysis blobs without user disclosure.
- "Save My Progress" on guest preview records only a sign-in intent, not the analysis payload.

---

### 2.10 Database and APIs

#### What It Does
- 32 Alembic migrations establishing relational schema with check constraints and foreign-key cascades.
- FastAPI REST routers with Pydantic validation schemas.
- Client-generated idempotency keys (`Idempotency-Key` header with `uq_analysis_runs_idempotency` constraint) on all analysis endpoints.
- Multi-retailer offer persistence (`retailers`, `retailer_offers`, `offer_price_history`) with affiliate click attribution (`0031`, `0032`).

#### Where It Lives
- **Migrations**:
  - `backend/alembic/versions/0001_initial_schema.py` through `0032_offer_click_attribution.py`
- **Models & Repositories**:
  - `backend/app/infrastructure/db/models.py`
  - `backend/app/infrastructure/db/repositories.py`
- **Routers**:
  - `backend/app/api/routers/` (analysis, outfits, wardrobe, saved_looks, events, today, discover, users, auth, feedback)

#### Remaining Limitations
- Dev database migration head is frozen at `0029` while test database migration head is `0032`.
- `user_state.version` exists in schema but is not checked or incremented by repository update methods.

---

### 2.11 Flutter UI and State Management

#### What It Does
- Complete client application implementing Digital Atelier luxury aesthetic (deep charcoal background `#131313`, warm amber/gold accents `#D4AF37`, refined typography).
- Enforces strict 65% visual / 35% content card proportion rule (`FansivibeCard`).
- Declarative navigation via `GoRouter` with authentication guards and guest mode route resolvers.
- Unified discovery experience with Trending and For You feeds, search filtering, and offer bottom sheets.

#### Where It Lives
- **Theme & Components**:
  - `newproject/flutter_application_1/lib/shared/theme/fansivibe_colors.dart`
  - `newproject/flutter_application_1/lib/shared/components/fansivibe_card.dart`
- **Routing**:
  - `newproject/flutter_application_1/lib/app/router/app_router.dart`
- **Features**:
  - `newproject/flutter_application_1/lib/features/` (onboarding, hairstyle, outfit_builder, outfit_scan, wardrobe, discover, events, profile)

#### Remaining Limitations
- Profile screen reads local storage and `LearningService` instead of backend API.
- Hairstyle result models drop backend uncertainty primitives (`confidence`, `needs_more_data`).
- No account deletion UI in profile settings.

---
*End of Stage 1 Existing Capabilities Report.*
