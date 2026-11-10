# STAGE 2 P1-1: PHASE 0 ARCHITECTURE AUDIT
## Interactive Outfit Component Swapping

**Feature:** P1-1 — Interactive Outfit Component Swapping  
**Date:** 2026-11-02  
**Status:** PHASE 0 COMPLETE — READY FOR PHASE 1 IMPLEMENTATION  
**Boundary:** Read-only audit completed; zero code or database mutations performed.

---

## 1. Executive Summary

This architecture audit verifies the repository state, data models, scoring engine entry points, API routing conventions, and Flutter presentation layers required to implement **P1-1: Interactive Outfit Component Swapping**.

Key findings:
1. **Zero Database Migrations Required:** Outfit generation is read/derive-only (TRX-2) and saved outfits utilize the existing `saved_looks` table with JSON snapshots (TRX-3). Slot replacement and compatibility recalculation operate on in-memory representations and return updated `OutfitRecommendation` value objects. Shared databases `fansivibe` and `fansivibe_test` remain untouched at migration revision `0032`, and the repository migration head remains strictly at `0036`.
2. **Canonical Compatibility Engine Available:** The canonical scoring engine `score_outfit_candidate` in `backend/app/domain/services/analysis_rules.py` sums coverage, color harmony, natural materials, seasonal consistency, formality balance, occasion match, palette points, fit points, user preferences, favorites, feedback, and wear history. Recommendation synthesis in `_to_recommendation` converts scored candidates to the wire `OutfitRecommendation` schema with grounded explanation reasons.
3. **Flutter UI Seam Identified:** `lib/features/outfit_builder/presentation/outfit_recommendation_screen.dart` renders `OutfitComponentCard` for each outfit piece with an existing placeholder `onReplace: () { SnackBar('Replace ${component.name} coming soon'); }`. This is the exact integration point for `OutfitSlotSwapSheet`.
4. **Wardrobe Image Pipeline Reusable:** P0-4 Phase 4 cloud media retrieval (`WardrobeItemImage`, `WardrobeCacheManager`, presigned GET URLs) is fully operational and will be reused without architecture changes.
5. **Guest Mode Isolation (D10 Option A):** Guest wardrobe items reside on-device in `LocalWardrobeRepository` (`LearningService`). Guest slot swapping runs purely locally on-device without authenticated API requests or database persistence.

---

## 2. Backend Architecture & Responsibilities

### 2.1 Relevant Files
| File Path | Component | Responsibility |
|---|---|---|
| `backend/app/api/routers/outfits.py` | API Router | Exposes `/v1/outfits/generate` and `/v1/outfits/saved`. Handles authentication (`get_current_user_id`), request validation, and error mapping. |
| `backend/app/api/schemas/outfits.py` | Pydantic Schemas | Defines wire models: `OutfitGenerateRequest`, `OutfitComponent`, `OutfitRecommendation`. |
| `backend/app/application/outfits.py` | Use Cases | Implements `GenerateOutfit` and `SaveOutfit`. Encapsulates candidate generation, ranking, deterministic seed selection, and `_to_recommendation` transformation. |
| `backend/app/domain/services/analysis_rules.py` | Decision Engine | Implements canonical scoring `score_outfit_candidate`, `_to_recommendation` reason synthesis, and candidate structures. |
| `backend/app/domain/services/outfit_compatibility.py` | Compatibility Rules | Defines slot definitions (`LookSlotDefinition`), canonical slot-to-category mapping (`CANONICAL_SLOT_CATEGORIES`), and multi-category compatibility evaluation. |
| `backend/app/domain/value_objects.py` | Value Objects | Defines `OutfitCandidate(top_ids, bottom_ids, outerwear_ids, footwear_ids, accessory_ids, compatibility, score, ...)`. |
| `backend/app/infrastructure/db/repositories.py` | Repositories | `WardrobeItemRepositorySQL` provides owner-scoped item lookups (`get_by_id`, `get_for_user`, `list_for_user`). |
| `backend/app/api/routers/wardrobe.py` | Wardrobe API | Provides `GET /v1/wardrobe/items` with category filtering and dynamic presigned GET media URLs. |

### 2.2 Canonical Slot and Category Definitions
The canonical slots defined in `CANONICAL_SLOT_CATEGORIES` and `_OUTFIT_SLOT_ORDER` are:
- `top` / `tops`
- `bottom` / `bottoms`
- `footwear` / `shoes`
- `outerwear`
- `accessories`

In `OutfitCandidate`, each slot maps to corresponding ID tuples:
- `tops` → `top_ids: tuple[str, ...]`
- `bottoms` → `bottom_ids: tuple[str, ...]`
- `footwear` → `footwear_ids: tuple[str, ...]`
- `outerwear` → `outerwear_ids: tuple[str, ...]`
- `accessories` → `accessory_ids: tuple[str, ...]`

### 2.3 Existing Scoring Engine Flow
```
User Wardrobe Items 
  → Load owner wardrobe (WardrobeItemRepositorySQL, OW-1 scoped)
  → Construct OutfitCandidate with replaced slot item
  → score_outfit_candidate(candidate, items_by_id, preferred_item_ids, occasions, palette, fit, feedback_context)
  → _to_recommendation(winner, by_record, occasion, mood, fit, color_palette, occasions)
  → OutfitRecommendation DTO (title, matchScore, components, reasons, colorHarmony, bodyFit, occasionMatch, etc.)
```

---

## 3. Flutter Architecture & Responsibilities

### 3.1 Relevant Files
| File Path | Component | Responsibility |
|---|---|---|
| `lib/features/outfit_builder/presentation/outfit_recommendation_screen.dart` | UI Screen | Displays recommendation hero, match score circle, component cards, metrics, and actions. |
| `lib/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart` | UI Widgets | `OutfitComponentCard` (renders icon, name, category, color, material, reason, Replace button). |
| `lib/features/outfit_builder/data/outfit_models.dart` | Models | `OutfitRecommendation`, `OutfitComponent`, `OutfitGenerateRequest`, `OutfitResult`. |
| `lib/features/outfit_builder/data/outfit_client.dart` | API Client | HTTP client with Bearer auth, error mapping (`OutfitFailure`), and 12s timeout. |
| `lib/features/outfit_builder/data/outfit_repository.dart` | Repository | `OutfitBuilderRepository` and `OutfitBuilderRepositoryImpl`. |
| `lib/features/wardrobe/data/wardrobe_repository.dart` | Wardrobe Repo | `WardrobeRepository` interface and `WardrobeRepositoryImpl` for listing user garments. |
| `lib/features/wardrobe/data/local_wardrobe_repository.dart` | Guest Wardrobe | Local on-device storage for guest wardrobe items. |
| `lib/features/wardrobe/presentation/widgets/wardrobe_widgets.dart` | Image Widgets | `WardrobeItemImage` with L1/L2 caching, fallback icons, and 65/35 card styling. |

### 3.2 Candidate Selection & Preview Flow
1. User taps "Replace" on `OutfitComponentCard`.
2. `OutfitRecommendationScreen` opens `OutfitSlotSwapSheet`.
3. `OutfitSlotSwapSheet` fetches candidate wardrobe items for that slot's category (filtering out the current garment).
4. User selects a replacement garment.
5. App requests swap evaluation from `OutfitBuilderRepository.swapSlot(...)` (or local evaluation for guests).
6. Sheet renders preview: previous garment vs new garment, updated match score, updated reasons, and changed metrics.
7. User confirms swap: sheet returns the updated `OutfitRecommendation` to `OutfitRecommendationScreen`.
8. User cancels: sheet dismisses, leaving original outfit intact.

---

## 4. Security, Ownership & Pinning Preservation

### 4.1 Server-Side Ownership Enforcement (OW-1)
- The backend resolves `user_id` strictly from the verified JWT.
- Every garment in `currentGarmentIds` and `replacementGarmentId` is validated against `WardrobeItemRepositorySQL.get_by_id(user_id=user_id, item_id=...)`.
- If any garment ID does not exist or belongs to another user, the request fails with HTTP 404 (OW-1, 404-not-403).
- Client-supplied scores, names, or ownership claims are discarded; all data is fetched from the database.

### 4.2 Pinned Garment Invariants
- Users can pin components in `OutfitRecommendationScreen` to prevent them from being replaced.
- If a swap request targets a slot whose garment ID is in `pinnedGarmentIds`, the backend rejects the request with HTTP 409 Conflict (`code="PINNED_SLOT_CONFLICT"`).
- All other pinned garment IDs are asserted to remain present in the resulting outfit.

---

## 5. Guest Mode Isolation (D10 Option A)

- Guests have no authenticated session (`isGuestUser == true`).
- No requests are sent to `/v1/outfits/swap-slot` or `/v1/outfits/candidates`.
- Candidates are loaded from `LocalWardrobeRepository.listItems(category: ...)`.
- Swapped outfit preview is computed on-device using local candidate replacement and score estimation.
- No guest records, image uploads, or UUID rows are created in PostgreSQL.

---

## 6. Database and Migration Verdict

- **Migration Required:** **NO**.
- **Schema Modification:** **NONE**.
- **Head Status:** `0036 (head)` preserved.
- **Shared DB Status:** `fansivibe` and `fansivibe_test` preserved at `0032`.

---

## 7. Implementation Plan

### Phase 1: Backend Implementation
1. Add schemas in `backend/app/api/schemas/outfits.py`:
   - `OutfitSlotSwapRequest` (occasion, mood, fit, colorPalette, currentGarmentIds, slot, replacementGarmentId, pinnedGarmentIds).
   - `OutfitCandidatesRequest`, `OutfitCandidatesResponse`.
   - `OutfitSlotSwapResponse`.
2. Implement use case `SwapOutfitSlot` in `backend/app/application/outfits.py`:
   - Validates ownership of all garments.
   - Enforces slot category compatibility.
   - Enforces pinning constraints.
   - Replaces slot in `OutfitCandidate`.
   - Recalculates compatibility with `score_outfit_candidate`.
   - Generates updated `OutfitRecommendation` via `_to_recommendation`.
3. Add endpoints in `backend/app/api/routers/outfits.py`:
   - `POST /v1/outfits/swap-slot`
   - `POST /v1/outfits/candidates`

### Phase 2: Backend Tests
1. Unit tests:
   - Valid slot swap (top, bottom, footwear, outerwear, accessories).
   - Compatibility score and reason recalculation.
   - Unsupported slot rejection (422).
   - Category mismatch rejection (422).
   - Duplicate garment rejection (422).
   - Pinned slot replacement rejection (409).
   - Pinned garments preservation verification.
2. Security tests:
   - Unauthenticated access (401).
   - Cross-user garment injection (404).
   - Malformed UUID handling (422).

### Phase 3: Flutter Implementation
1. Update `lib/features/outfit_builder/data/outfit_models.dart`:
   - `OutfitSlotSwapRequest`, `OutfitSlotSwapResponse`, `OutfitCandidateItem`.
2. Update `lib/features/outfit_builder/data/outfit_client.dart` & `outfit_repository.dart`:
   - Add `swapSlot` and `getCandidates` methods.
3. Create `lib/features/outfit_builder/presentation/widgets/outfit_slot_swap_sheet.dart`:
   - Candidate selector, preview comparison, match score update, confirmation/cancellation.
4. Update `lib/features/outfit_builder/presentation/outfit_recommendation_screen.dart`:
   - Component pinning toggle.
   - Wire `OutfitComponentCard` `onReplace` to `OutfitSlotSwapSheet`.
   - Handle confirmed swap and update active recommendation state.

### Phase 4: Flutter Tests
1. Widget and unit tests for `OutfitSlotSwapSheet`.
2. Pinning interaction tests in `OutfitRecommendationScreen`.
3. Candidate loading, error, empty, and preview confirmation tests.
4. Guest-mode local candidate and swap tests.

### Phase 5 & 6: Regression, Documentation & Final Audit
1. Run existing backend and Flutter suites.
2. Produce required deliverables:
   - `STAGE2_P1_1_IMPLEMENTATION_REPORT.md`
   - `STAGE2_P1_1_SECURITY_AUDIT.md`
   - `STAGE2_P1_1_BACKEND_TEST_REPORT.md`
   - `STAGE2_P1_1_FLUTTER_TEST_REPORT.md`
   - `STAGE2_P1_1_REGRESSION_REPORT.md`
   - `STAGE2_P1_1_REMAINING_RISKS.md`
3. Update `CURRENT_STATE.md`.
