# Fansivibe — Stage 2 Next Feature Recommendation
## Formal Recommendation & Implementation Scope for Milestone P1-1: Interactive Outfit Component Swapping

**Document Version:** 1.0.0  
**Date:** November 1, 2026  
**Auditor / Agent:** Antigravity AI  
**Status:** PROPOSAL & IMPLEMENTATION BLUEPRINT (Awaiting Explicit User Authorization)  

---

## 1. Executive Recommendation

Following the successful completion and verification of the foundational P0 milestone (P0-1 Multi-Item Wear Logging, P0-2 Grooming Analysis Repair, P0-3 Preferences & Settings Persistence, and P0-4 Wardrobe Cloud Media Storage), it is formally recommended that:

> **P1-1: Interactive Outfit Component Swapping** be authorized as the immediate next implementation task in Stage 2.

This recommendation was selected over alternative roadmap candidates (P1-2 Enriched Saved Looks, P1-3 Weather Seeding, and P2-3 Virtual Try-On) after rigorous dependency, user value, and technical risk evaluations.

---

## 2. Eleven-Point Decision Analysis

### 1. Why This Feature Should Be Next
Fansivibe's core value proposition is an intelligent personal stylist. With P0-1 (Wear Logging) and P0-4 (Wardrobe Media Cloud Sync) now complete, the platform has a functional daily loop and high-fidelity visual cards. However, the outfit generation experience remains **all-or-nothing**:
- The AI generates a 4-item ensemble (e.g., blazer, shirt, trousers, shoes).
- If 3 items are perfect but 1 item is disliked by the user (e.g., they prefer sneakers over dress shoes), the user cannot swap the shoes.
- Their only option is to discard the entire outfit by tapping "Regenerate" (which randomizes all 4 items) or accept an outfit they do not want to wear.
Introducing component swapping transforms the application from a rigid suggestion engine into an **interactive, collaborative styling canvas**.

### 2. What User Problem It Solves
- **Eliminates the "All-or-Nothing" Frustration:** Users gain granular agency to customize specific outfit components to match their mood, comfort, or daily activities.
- **Drives Wardrobe Discovery:** Users discover alternative items in their closet that pair harmoniously with the rest of the outfit.
- **Directly Feeds Wear Logging (P0-1):** Once customized, users tap "Wear This Look Today" on the customized outfit, immediately recording accurate wear data.

### 3. What is Already Implemented & Can Be Reused
- **Canonical 12-Term Candidate Scoring (`analysis_rules.py`):** Functions `_palette_points`, `_fit_points`, `_occasion_points`, and `candidate_feedback_points` are already fully implemented and mathematically verified.
- **Deterministic Derivation (`GenerateOutfit` in `outfits.py`):** Capable of generating candidates and computing match metrics.
- **Wardrobe Media Pipeline (P0-4):** Presigned GET URLs and `WardrobeItemImage` multi-source caching are complete, allowing alternative garments to render instantly in bottom sheets.
- **Digital Atelier UI Components:** `FansiHeroCard`, `FansiButton`, `FansiBadge`, and `FansivibeSpacing` design tokens are ready.

### 4. What Remains Missing
- **Backend API:** An endpoint (`POST /v1/outfits/swap-slot`) that accepts pinned garment IDs, evaluates candidate replacements in a target category from the user's wardrobe, scores each candidate against the pinned items, and returns ranked alternatives with compatibility reasons.
- **Flutter UI:** A "Swap" icon button on outfit component cards, an `OutfitSlotSwapSheet` modal bottom sheet displaying alternative garments, and state management in `OutfitGenerationScreen` and `DailyOutfitScreen` that swaps the item in-place and updates the `% Ensemble Match` score.

### 5. What It Depends On
- `FEAT-08` (Recommendation Engine) — **Complete & Verified**
- `FEAT-10` (Outfit Builder) — **Complete & Verified**
- `FEAT-04` (Wardrobe Inventory & Cloud Media) — **Complete & Verified**
- `P0-1` (Ensemble Wear Logging) — **Complete & Verified**
- **External Dependencies:** ZERO external APIs, ZERO cloud provisioning, ZERO hardware requirements.
- **Database Migrations:** ZERO schema migrations.

### 6. What Other Features Depend on It
- **P1-3 (Weather-Aware Seeding):** Uses component swapping to suggest weather-specific alternatives (e.g. swap light jacket for trench coat).
- **P2-3 (Generative Virtual Try-On Stage F1):** Users select and swap garments interactively before requesting a generative try-on render.
- **P2-1 (Preference Learning):** Explicit swap actions provide clean negative signals (swapped-out item) and positive signals (selected replacement item).

### 7. Estimated Implementation Complexity
- **Complexity Rating:** **Low-Medium**
- **Engineering Effort:** 1 focused milestone.
- **Architectural Risk:** Minimal. No database tables modified; purely additive use case and UI sheet.

### 8. Required Backend Work
1. **Schema Definition (`backend/app/api/schemas/outfits.py`):**
   - Define `OutfitSlotSwapRequest`:
     ```python
     class OutfitSlotSwapRequest(BaseModel):
         pinnedItemIds: list[UUID] = Field(..., min_length=1, max_length=9)
         targetCategory: str = Field(..., min_length=1)
         occasion: Optional[str] = None
         palette: Optional[str] = None
         fit: Optional[str] = None
     ```
   - Define `OutfitSlotSwapResponse` with ranked candidate garments, compatibility scores, and grounded rationale.
2. **Application Service (`backend/app/application/outfits.py`):**
   - Implement `SwapOutfitComponent` use case: queries user's wardrobe for items in `targetCategory` excluding pinned items; computes compatibility score against pinned items via `analysis_rules.py`; returns top 10 ranked alternatives.
3. **Router Endpoint (`backend/app/api/routers/outfits.py`):**
   - Add `POST /v1/outfits/swap-slot` with JWT authentication and OW-1 scoping.

### 9. Required Flutter Work
1. **Client & Repository Layer:**
   - Add `swapSlot({required List<String> pinnedItemIds, required String targetCategory, ...})` in `OutfitClient` and `OutfitRepository`.
2. **Interactive Presentation Widget:**
   - Create `OutfitSlotSwapSheet` (`lib/features/outfit_builder/presentation/widgets/outfit_slot_swap_sheet.dart`):
     - Displays current item being replaced at top.
     - Horizontally scrollable or grid list of alternative garments from user's wardrobe with category icon, thumbnail, name, and compatibility badge (`% Match`).
     - Tapping an alternative triggers in-place replacement.
3. **Integration into Screens:**
   - Update `OutfitRecommendationScreen`: add "Swap" action icon to each component card.
   - Update `DailyOutfitScreen`: add "Swap" action icon to each component card.
   - Recalculate `% Ensemble Match` score upon replacement.

### 10. Required Testing
1. **Backend Tests (`backend/tests/test_outfit_swap.py`):**
   - Rejects unowned wardrobe items (OW-1 404).
   - Rejects swap request with missing target category (422).
   - Returns only garments matching `targetCategory`.
   - Verified candidate scoring matches canonical 12-term rules.
   - Empty alternative category returns graceful empty list (no crash).
2. **Flutter Widget & Unit Tests (`test/outfit_swap_test.dart`):**
   - Tapping "Swap" on an item opens `OutfitSlotSwapSheet`.
   - Selecting a replacement item updates the card on screen.
   - Ensemble match score recalculates truthfully.
   - "Wear This Look Today" logs the updated ensemble containing the new item.

### 11. Risks If Implemented in the Wrong Order
- If P1-3 (Weather) were built before P1-1, weather recommendations would still be rigid all-or-nothing outfits without user override capability.
- If P2-3 (VTON) were built before P1-1, expensive diffusion renders would be wasted on outfits with individual disliked garments that the user could not modify.

---

## 3. Alternative Candidates Evaluated & Why Deferred

| Candidate Feature | Priority | Evaluation Verdict | Rationale for Deferral |
|:---|:---:|:---:|:---|
| **P1-2: Enriched Saved Look Hydration** | P1 | **Strong Runner-Up (Scheduled Immediately After P1-1)** | Solves historical review fidelity, but does not impact the active outfit generation and daily wearing experience. P1-1 creates the custom looks that users will then want to save and view. |
| **P1-3: Weather-Aware Location Seeding** | P1 | Deferred to Phase 2.3 | Requires selecting and provisioning an external weather API and client geolocation permissions. |
| **P2-3: Generative Virtual Try-On** | P2 | Deferred to Phase 2.5 | Highest complexity; requires dedicated GPU diffusion infrastructure and asynchronous job queuing. |

---

## 4. Exact Implementation Scope for P1-1

When authorized, the P1-1 task will be strictly bounded to:
1. **Zero Database Migrations:** No Alembic migrations or schema changes.
2. **Zero Modification of Unrelated Screens:** Changes restricted strictly to `backend/app/application/outfits.py`, `backend/app/api/routers/outfits.py`, `lib/features/outfit_builder/`, and `DailyOutfitScreen`.
3. **Preservation of Digital Atelier Design Tokens:** Adherence to the 65/35 visual card proportion rule and dark luxury palette.
4. **Preservation of Decision D10 Option A:** Guest users test swapping locally over ephemeral memory without database writes.
5. **Comprehensive Automated Test Coverage:** Dedicated pytest module and Flutter widget test suite.

---

## 5. Strict Stop Condition Compliance

This document completes the architectural recommendation deliverable.

**STOP CONDITION:**
- **No implementation of P1-1 has been started.**
- **No application code, tests, or configurations have been altered.**
- **The agent is now stopping execution and awaiting explicit user authorization before proceeding.**
