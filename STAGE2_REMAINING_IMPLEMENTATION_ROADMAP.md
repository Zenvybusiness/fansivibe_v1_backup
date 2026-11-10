# Fansivibe — Stage 2 Remaining Implementation Roadmap
## Practical Implementation Sequence & Feature Milestones from Current State to Stage 2 Completion

**Document Version:** 1.0.0  
**Audit Date:** November 1, 2026  
**Status:** Authoritative Post-P0-4 Strategic Roadmap  

---

## 1. Executive Phasing Strategy

Following the complete verification of the foundational P0 milestone (P0-1 Multi-Item Wear Logging, P0-2 Grooming Analysis Repair, P0-3 Style Preferences Persistence, and P0-4 Wardrobe Cloud Media Storage), Fansivibe is positioned to complete **Stage 2: User-Facing Product Development**.

The remaining work is structured into four focused, sequential phases:
1. **Phase 2.2: Stylist Experience & Versatility (Core Stage 2 Completion)** — *Interactive Outfit Component Swapping (P1-1) and Enriched Saved Look Hydration & Linking (P1-2).*
2. **Phase 2.3: Environmental Context & Adaptation** — *Weather-Aware Location Seeding (P1-3).*
3. **Phase 2.4: Deep Personalization & Ingestion Efficiency** — *Closed-Loop Stylist Preference Learning (P2-1) and Wardrobe Batch Ingestion (P2-2).*
4. **Phase 2.5: Generative Visual Styling & Monetization (Stage 2 Exit / Production Prerequisites)** — *Generative Virtual Try-On Stage F1 (P2-3), Subscriptions & Billing (P3-1), and Production Hardening.*

```
+─────────────────────────────────────────────────────────────────────────────+
|                         REMAINING ROADMAP PHASES                            |
+─────────────────────────────────────────────────────────────────────────────+
|  PHASE 2.2: STYLIST EXPERIENCE & VERSATILITY (MUST-HAVE STAGE 2 COMPLETION) |
|  ├── P1-1: Interactive Outfit Component Swapping (RECOMMENDED NEXT)         |
|  └── P1-2: Enriched Saved Look Hydration & Wardrobe Linking                 |
+─────────────────────────────────────────────────────────────────────────────+
                                       │
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|  PHASE 2.3: ENVIRONMENTAL CONTEXT & ADAPTATION                              |
|  └── P1-3: Weather-Aware Location Seeding for Daily Looks                   |
+─────────────────────────────────────────────────────────────────────────────+
                                       │
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|  PHASE 2.4: DEEP PERSONALIZATION & INGESTION EFFICIENCY                     |
|  ├── P2-1: Closed-Loop Stylist Preference Learning                          |
|  └── P2-2: Multi-Item Wardrobe Batch Ingestion                              |
+─────────────────────────────────────────────────────────────────────────────+
                                       │
                                       ▼
+─────────────────────────────────────────────────────────────────────────────+
|  PHASE 2.5: GENERATIVE VISUAL STYLING & MONETIZATION (STAGE 2 EXIT)         |
|  ├── P2-3: Generative Virtual Try-On Pipeline (Stage F1)                    |
|  ├── P3-1: In-App Purchases & Subscription Billing                          |
|  ├── P3-2: Calendar Synchronization & Trip Packing Assistant                |
|  └── P3-3: In-App Customer Support & Help Desk                              |
+─────────────────────────────────────────────────────────────────────────────+
                                       │
                                       ▼ (Subject to Decision M14)
+─────────────────────────────────────────────────────────────────────────────+
|  PHASE 2.6: DISCOVERY COMMERCE (BLOCKED BY DECISION M14)                    |
|  └── P3-4: Discovery Commerce & Affiliate Shopping                          |
+─────────────────────────────────────────────────────────────────────────────+
```

---

## 2. Phase 2.2: Stylist Experience & Versatility (Required for Stage 2 Completion)

### Milestone P1-1: Interactive Outfit Component Swapping
- **Feature ID:** `P1-1` (FEAT-10 Extension)
- **Priority:** **P1**
- **Current Status:** **COMPLETE AND VERIFIED (Executed 2026-11-02)** — 21 backend tests passed, 9 Flutter tests passed, 0 migrations, full guest-mode local isolation.
- **Target Outcome:**
  On `OutfitRecommendationScreen`, users can tap "Replace" on any unpinned individual garment slot, view compatible alternative garments from their wardrobe, pin pieces they want to protect, preview the swap with real-time canonical compatibility recalculation, and confirm or cancel in-place.
- **Dependencies:** `FEAT-08` (Recommendation Engine), `FEAT-10` (Outfit Builder), `P0-1` (Wear Logging), `P0-4` (Media Storage). **ALL SATISFIED.**
- **Backend Scope:**
  - Add use case `SwapOutfitComponent` in `backend/app/application/outfits.py`.
  - Add endpoint `POST /v1/outfits/swap-slot` accepting `{outfit_id, pinned_item_ids: List[UUID], target_category: str}`.
  - Scores candidate wardrobe items in `target_category` against pinned items using `analysis_rules.py` heuristics.
  - Returns ranked list of alternatives with individual item match scores and reasons.
- **Flutter Scope:**
  - Create bottom sheet widget `OutfitSlotSwapSheet` in `lib/features/outfit_builder/presentation/widgets/`.
  - Add "Swap" button on `WardrobeItemCard` within `OutfitRecommendationScreen` and `DailyOutfitScreen`.
  - In-place replacement state management updating the active recommendation and `% Ensemble Match`.
- **Database Scope:** None (zero schema migrations).
- **AI / Model Scope:** Heuristic candidate scoring in `analysis_rules.py`.
- **Testing Requirements:**
  - Unit tests verifying only owned items of the target category are returned.
  - Integration tests verifying the resulting ensemble passes minimum validity (top + bottom).
  - Widget tests verifying bottom sheet renders, user selection swaps the card, and wear logging logs the newly swapped item.
- **Acceptance Criteria:**
  - User can swap an item in an outfit with 2 taps.
  - Swapping shoes updates the shoe card and recalculates the ensemble match percentage.
  - Tapping "Wear This Look" logs the swapped ensemble atomically via `POST /v1/wardrobe/wears`.
- **Known Risks:** None. Highly isolated, zero database risk.

---

### Milestone P1-2: Enriched Saved Look Hydration & Wardrobe Linking
- **Feature ID:** `P1-2` (FEAT-15 Extension)
- **Priority:** **P1 (Critical UX Fidelity)**
- **Current Status:** **COMPLETE AND VERIFIED (Executed 2026-11-02)** — 12 backend tests passed (100%), 16 Flutter tests passed (100%), 0 migrations, read-only snapshot preservation, OW-1 scoping, P0-1 wear integration, and D10 Option A guest mode.
- **Target Outcome:**
  `SavedLooksScreen` displays rich hero cards with actual garment thumbnail mosaics. Tapping a saved look opens a dedicated `LookDetailsScreen` showing fully hydrated garment cards with brand, tags, and photos. Users can tap into individual garments to view their details or tap a prominent "Wear This Look Today" action button.
- **Dependencies:** `FEAT-04` (Wardrobe Items), `FEAT-15` (Saved Looks), `P0-1` (Wear Logging), `P0-4` (Media Storage).
- **Backend Scope:**
  - Update `GET /v1/looks/saved` and `GET /v1/looks/saved/{id}` in `backend/app/api/routers/looks.py` with optional `?include_items=true`.
  - Join `saved_looks.snapshot.selectedItemIds` against `wardrobe_items` to return populated item objects with presigned GET URLs (`imageUrl`).
  - Gracefully flag deleted garments as `isArchived: true` rather than omitting them.
- **Flutter Scope:**
  - Update `SavedLooksScreen` to render multi-image mosaic preview cards using `WardrobeItemImage`.
  - Build `LookDetailsScreen` rendering component garment cards.
  - Wire "Log Wear Today" button on `LookDetailsScreen` via `logEnsembleWear` and `EnsembleWearConfirmationSheet`.
- **Database Scope:** None (zero migrations).
- **Testing Requirements:**
  - Pytest verifying `GET /v1/looks/saved?include_items=true` returns hydrated items and handles archived items.
  - Widget tests verifying look cards render thumbnails and tapping "Wear This Look" triggers wear logging.
- **Acceptance Criteria:**
  - Saved look cards display real garment photos instead of generic placeholder icons.
  - Users can record wearing a saved look directly from the archive with one tap.

---

## 3. Phase 2.3: Environmental Context & Adaptation (Important Improvements)

### Milestone P1-3: Weather-Aware Location Seeding for Daily Looks
- **Feature ID:** `P1-3` (FEAT-14 Extension)
- **Priority:** **P1 (Personalization Depth)**
- **Current Status:** Placeholder (Daily look uses static default: 20°C, clear).
- **Target Outcome:**
  `DailyOutfitScreen` incorporates real-time local temperature and precipitation. Outfits adapt intelligently (e.g. recommending raincoats/boots during rain, breathable fabrics during heatwaves) with a clear contextual chip: *"Curated for 14°C & Rain in Seattle"*.
- **Dependencies:** `FEAT-08`, `FEAT-14`, External Weather API.
- **Backend Scope:**
  - Add weather proxy endpoint `GET /v1/weather/current` or accept `temp_c`, `condition`, and `precipitation` parameters in `GET /v1/looks/today`.
  - Update `analysis_rules.py` with temperature-bracket scoring (e.g. outerwear required if temp < 15°C; penalty on heavy knits if temp > 25°C).
- **Flutter Scope:**
  - Integrate `geolocator` or city selector in Settings.
  - Render weather context chip on `DailyOutfitScreen`.
- **External Dependencies:** Open-Meteo API (free, zero API key required) or Apple WeatherKit.
- **Testing Requirements:** Tests verifying extreme temperatures enforce appropriate outerwear and footwear.

---

## 4. Phase 2.4: Deep Personalization & Ingestion Efficiency

### Milestone P2-1: Closed-Loop Stylist Preference Learning
- **Feature ID:** `P2-1` (FEAT-18 Extension)
- **Priority:** **P2**
- **Target Outcome:**
  The AI Stylist dynamically adjusts candidate scoring based on long-term user behavior. If a user consistently dislikes double-breasted blazers, avoids yellow tones, or frequently wears loose fits, the engine dynamically penalizes conflicting garments and boosts preferred aesthetics.
- **Dependencies:** `FEAT-08`, `FEAT-15`, `FEAT-18`, cumulative wear and feedback history.
- **Backend Scope:** Preference vector calculation service updating user scoring profile based on `learning_signals` and `feedback_events`.

### Milestone P2-2: Multi-Item Wardrobe Batch Ingestion
- **Feature ID:** `P2-2` (FEAT-05 & FEAT-11 Extension)
- **Priority:** **P2**
- **Target Outcome:**
  Users can upload 5–10 photos of closet racks or outfits at once. An asynchronous vision pipeline segments and extracts individual garments into a staging queue for rapid one-tap batch approval.
- **Dependencies:** `FEAT-04`, `FEAT-11`, `P0-4` (Media Storage), background worker queue.

---

## 5. Phase 2.5: Generative Visual Styling & Monetization (Stage 2 Exit / Release Prerequisites)

### Milestone P2-3: Generative Virtual Try-On Pipeline (Stage F1)
- **Feature ID:** `P2-3` (FEAT-19)
- **Priority:** **P2**
- **Target Outcome:**
  Replace Stage F0 mock SVG ("TEST DATA") with true generative AI try-on. User uploads full-body reference portrait; selected outfit garments are realistically warped and composited onto user silhouette using diffusion models.
- **Dependencies:** GPU infrastructure (ComfyUI / IDM-VTON server or serverless GPU endpoint).

### Milestone P3-1: In-App Purchases & Subscription Billing
- **Feature ID:** `P3-1` (FEAT-20)
- **Priority:** **P3**
- **Target Outcome:**
  Activation of Free, Pro ($9.99/mo), and Atelier ($19.99/mo) subscriptions via RevenueCat / Stripe / StoreKit 2.

### Milestone P3-2: Calendar Synchronization & Trip Packing Assistant
- **Feature ID:** `P3-2` (FEAT-16 Extension)
- **Priority:** **P3**
- **Target Outcome:**
  Two-way synchronization with iOS EventKit and Android CalendarProvider; multi-day trip packing list generator.

### Milestone P3-3: In-App Customer Support & Help Desk
- **Feature ID:** `P3-3` (FEAT-21)
- **Priority:** **P3**
- **Target Outcome:**
  Functional ticketing and support contact channel replacing static FAQ placeholders.

### Milestone P3-4: Discovery Commerce & Affiliate Shopping
- **Feature ID:** `P3-4` (FEAT-24)
- **Priority:** **P3 (Blocked by Decision M14)**
- **Target Outcome:**
  Product recommendation cards link to retailer affiliate purchase slots upon founder unsealing of Decision M14.

---

## 6. Categorized Milestone Summary

### Category 1: Required for Stage 2 Completion
1. **P1-1: Interactive Outfit Component Swapping** *(Zero blockers, highest user impact).*
2. **P1-2: Enriched Saved Look Hydration & Wardrobe Linking** *(Zero blockers, closes visual fidelity).*

### Category 2: Important User-Facing Improvements
3. **P1-3: Weather-Aware Location Seeding for Daily Looks.**
4. **P2-1: Closed-Loop Stylist Preference Learning.**
5. **P2-2: Multi-Item Wardrobe Batch Ingestion.**

### Category 3: Optional Future Enhancements & Monetization
6. **P2-3: Generative Virtual Try-On Pipeline (Stage F1).**
7. **P3-1: In-App Purchases & Subscription Billing.**
8. **P3-2: Calendar Sync & Trip Packing Assistant.**
9. **P3-3: In-App Customer Support.**
10. **P3-4: Discovery Commerce (Subject to Decision M14).**

### Category 4: Production-Release Prerequisites (Operational)
- Apply Alembic migrations `0033 -> 0036` to shared developer/production databases.
- Provision live Cloudflare R2 staging bucket and verify live storage tests.
- Implement Phase 13 operational orphan storage reconciliation worker.
- Unify Style Score and streak calculation exclusively from backend PostgreSQL ledger.
