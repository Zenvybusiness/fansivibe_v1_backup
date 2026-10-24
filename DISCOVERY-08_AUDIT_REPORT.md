# DISCOVERY-08 — Data Quality and Discovery Relevance Audit Report

**Project:** Fansivibe  
**Document Status:** OFFICIAL AUDIT REPORT & PRIORITIZED ROADMAP  
**Task Identifier:** DISCOVERY-08  
**Audit Date:** 2026-10-14  
**Auditor:** Antigravity Pair Programming Agent  
**Execution Mode:** READ-ONLY AUDIT (No implementation changes, zero database mutations, zero git commits)  
**Alembic Migration Head:** `0029 (head)` (Strictly Verified)  
**FFO Corpus Digest:** `967f891e4c91d4e9463be5ea183b62ad3f3548f35c1b1e4d8678da49bf4d2581` (Strictly Verified)  
**Production Demand Signal:** `DEMAND_SIGNAL_AVAILABLE = False` (Strictly Preserved)  
**Digital Atelier Design System:** 65% visual / 35% content card proportions strictly preserved  

---

## 1. Executive Summary

### 1.1 Overview and Objective
Following the reported completion of tasks DISCOVERY-01 through DISCOVERY-07B, this audit provides an evidence-based, empirical assessment of Fansivibe's Discover system across its three core experiences:
1. **For You:** Personalized fashion recommendations utilizing user profile, style DNA, preferences, budget, and wardrobe context.
2. **Trending:** Macro fashion trend discovery grounded in empirical evidence, maintaining strict separation between catalog activity, media attention, and consumer demand.
3. **Complete Looks:** Multi-category coordinated ensembles assembled from catalog items and authenticated user wardrobes.

The objective was not merely to check whether endpoints respond with HTTP 200, but to determine whether the existing implementation delivers useful, relevant, diverse, and trustworthy discovery.

### 1.2 Overall Readiness of the Three Discover Experiences

| Experience | Operational Status | Data Integrity & Correctness | Discovery Utility & Relevance | Overall Readiness |
|---|---|---|---|---|
| **For You** | **Connected (Stage 2)**: FastAPI endpoint `/v1/discovery/for-you` connected to Flutter `EstablishedUserForYouFeed` with server category filtering and pagination. | **Severely Impaired**: Preferences schema disconnect (`snake_case` in DB vs `camelCase` in Python) silently zeroes preference scoring for all existing users. Guests and cold-start users receive flat, identical scores (15.0%) broken only by arbitrary UUID string sorting. | **Low**: 100% synthetic seed products with unroutable image domains (`cdn.fixture.test`). Recommendations lack diversity controls and repeat items across sections. | **Early Prototype / Blocked for Production** |
| **Trending** | **Connected (Read-only)**: `/v1/discovery/trending` and `TrendingEvidenceStatusCard` render honest catalog facts; `DEMAND_SIGNAL_AVAILABLE = False` is strictly enforced. | **High (Backend) / Disconnected (UI)**: D6/D7 fail-closed engine correctly marks 100% of seed observations as fixture-derived, insufficient evidence, unpublishable. However, surrounding Flutter UI renders hardcoded mock cards claiming "1.4K SAVES" and "Most saved across global wishlists". | **Moderate**: Honest status card is informative, but candidate grid is empty by design (as required by truth-in-evidence rules); editorial cards show static mock data. | **Stage 1 Complete / Gated by Real Data Sources** |
| **Complete Looks** | **Connected (Stage 2)**: `/v1/discovery/looks/complete` connected to Flutter `EnsembleCurationCard` with candidate selector chips, INR budget filters, and wardrobe anchor styling. | **High Correctness**: Wardrobe items contribute ₹0 to catalog spend; owner-scoping strictly prevents cross-user access; bundle purchasing is honestly disclosed as unavailable. | **Severely Low Diversity**: Combinatorial Cartesian product algorithm results in diversity collapse: requesting 5 looks yields the identical 4-piece outfit with only the accessory swapped. Enforces all 5 slots when available, causing $0$ results on modest budgets ($\le ₹5,000$). | **Prototype Stage / Needs Diversity Re-ranking** |

---

### 1.3 The Five Highest-Impact Findings

1. **Preference Schema Key Disconnect Silently Neutralizes Real User Personalization (P0 - Correctness / Relevance)**
   - *Evidence:* In the PostgreSQL database (`fansivibe`), `user_state.preferences` stores preferences in `snake_case` (e.g., `{"preferred_occasions": ["casual", "business"]}`). However, `backend/app/application/for_you.py` (lines 102–132) extracts preferences using `camelCase` keys (`stored_prefs.get("preferredOccasions")`, `stored_prefs.get("preferredCategories")`, etc.).
   - *Impact:* For every real user in the database (including test users Tony and trigma), extracted preferences are empty tuples `()`. Personalization falls back to 8 neutral dimensions, zeroing the preference match score ($0.0/40$) and occasion style score ($0.0/10$). Real user preferences have zero effect on ranking.

2. **100% Synthetic Seed Catalog with Non-Routable Image Hosts (P0 - Data Quality / Integrity)**
   - *Evidence:* All 60 products in the database are synthetic fixtures (`attributes.fixture = True`, `attributes.synthetic = True`) sourced exclusively from `fashion_seed`. Every product image URL points to `https://cdn.fixture.test/fashion/SEED-*.jpg`.
   - *Impact:* `.test` is an RFC 2606 reserved domain that cannot resolve on public DNS. No real image bytes can be loaded on mobile or web clients outside synthetic mock test harnesses. Zero commercial, retailer-verified products exist in storage.

3. **Complete Looks Combinatorial Diversity Collapse (P1 - Discovery Quality / Algorithm)**
   - *Evidence:* `assemble_look_combinations` evaluates permutations via `itertools.product(*pool_per_slot)` and sorts by `(-compatibility_score, total_catalog_price)`. In testing against the database, requesting 5 looks returned 5 looks with the exact same Top (Ajrakh Shirt), Bottom (Carpenter Pants), Footwear (Espadrilles), and Outerwear (Harrington Jacket), differing only by the accessory slot (Cap vs Scarf vs Tote vs Leather Belt vs Brass Belt).
   - *Impact:* The user experiences "multi-look browsing" as viewing the exact same outfit 5 times with a minor accessory swap. Furthermore, the algorithm forces all 5 slots whenever candidates exist, failing to generate 2-piece or 3-piece outfits and returning 0 looks when budget is $\le ₹5,000$.

4. **Client-Side Search Disconnect from Server-Side Pagination (P1 - User Experience / Correctness)**
   - *Evidence:* In `existing_user_for_you_widgets.dart`, `BecauseYouLikeSection` filters products by search query purely in Flutter client memory (`catalog.where(...)`).
   - *Impact:* Search only evaluates the currently loaded candidate page (20 items). Matching products located on Page 2 or 3 of the catalog are completely missed. The user is misled to believe an item does not exist. The backend `/v1/discovery/for-you` API lacks a `q` search parameter.

5. **Semantic Contradiction in Trending Tab: Factual Backend vs Fabricated Mock UI (P1 - Trust / Compliance)**
   - *Evidence:* The backend D6/D7 trend engine and `TrendingEvidenceStatusCard` strictly enforce factual integrity: `DEMAND_SIGNAL_AVAILABLE = False`, catalog facts only, zero demand claims. However, adjacent components in `discover_screen.dart` render hardcoded mock editorial cards claiming `"1.4K SAVES"`, `"920 SAVES"`, and `"Most saved across top global wishlists"` (featuring mock Zara and Adidas items).
   - *Impact:* The screen simultaneously claims "Direct consumer demand signals remain unavailable" in one card while displaying fabricated save counts and wishlist superlatives in adjacent cards, compromising user trust and semantic integrity.

---

### 1.4 Verification Matrix: Directly Verified vs Prior Claims

| Subsystem / Capability | Verification Status | Direct Verification Method & Evidence |
|---|---|---|
| **Git Working Tree Baseline** | **Directly Verified** | `git status -s` shows 16 modified files and 24 untracked files from DISCOVERY-02 through 07B. Branch `main` at `02ff73a`. All uncommitted work preserved intact. |
| **Alembic Migration Head** | **Directly Verified** | Executed `backend/.venv/bin/alembic heads` $\rightarrow$ strictly `0029 (head)`. |
| **FFO Corpus Digest** | **Directly Verified** | Executed in-process Python verification against `load_documents()` and `build_index()` $\rightarrow$ hash `967f891e4c91d4e9463be5ea183b62ad3f3548f35c1b1e4d8678da49bf4d2581` (100% match). |
| **Database State & Isolation** | **Directly Verified** | Connected via psycopg to PostgreSQL. `fansivibe` (dev DB) contains 60 products, 60 observations, 84 users, 76 user_states, 46 wardrobe items. `fansivibe_test` contains 0 rows across all tables. |
| **Cold-Start Personalization Ranking** | **Directly Verified** | Invoked `PersonalizeForYou(user_id=None, is_guest=True)` $\rightarrow$ returned 20 items, all with identical score `15.0`. Tie-breaker is pure UUID alphabetical sort. |
| **Authenticated Personalization Ranking** | **Directly Verified** | Invoked `PersonalizeForYou(user_id=Tony)` $\rightarrow$ identified `preferred_occasions` dropped due to `camelCase` vs `snake_case` mismatch. Wardrobe complementarity (+10 pts) and budget (+15 pts) produced top score `25.0%`. |
| **Trending Signal Integrity** | **Directly Verified** | Invoked `AnalyzeTrends` on dev DB $\rightarrow$ 60 observations, 5 candidates, all marked `stage=insufficient_evidence`, `publishable=False`, `is_fixture=True`. |
| **Complete Looks Compatibility & Budget** | **Directly Verified** | Tested `AssembleCompleteLooks(limit=5)` $\rightarrow$ wardrobe items contribute ₹0; ₹10k budget enforced; identified diversity collapse (identical 4 pieces across all 5 looks). |
| **Client Search & Pagination** | **Directly Verified** | Traced Flutter UI code in `existing_user_for_you_widgets.dart` $\rightarrow$ confirmed search is client-side over loaded page only. |
| **Live Affiliate / PA-API Provider Pipelines** | **Supported Only by Prior Reports** | Historical reports (DISCOVERY-01) state Amazon PA-API, Flipkart Affiliate, and Rainforest are unconfigured; directly verified 0 commercial rows in DB. |
| **GDELT Live Ingestion** | **Supported Only by Prior Reports** | Prior reports state GDELT is subject to historical archive timeouts; verified `media_attention_observations` has 0 rows in PostgreSQL. |

---

## 2. Product Catalog Data Quality Scorecard

### 2.1 Product Completeness Scorecard
*Denominator: Exactly 60 products in PostgreSQL `fansivibe` database (`products` table).*  
*Inspection Method: Full table dump via `psycopg` querying all columns and JSONB attribute keys.*

| Attribute | Completeness Count | Percentage | Notes & Values |
|---|---|---|---|
| **Product ID (UUID)** | 60 / 60 | 100.0% | Deterministically generated UUIDs. |
| **Title** | 60 / 60 | 100.0% | Realistic fashion titles; all prefixed with `[Seed]`. Length: 25–58 chars. |
| **Category** | 60 / 60 | 100.0% | Tops (14), Bottoms (12), Outerwear (12), Footwear (12), Accessories (10). |
| **Subcategory** | 60 / 60 | 100.0% | 25 distinct subcategories (e.g. shirt, kurta, trousers, jacket, sneakers, belt). |
| **Brand** | 60 / 60 | 100.0% | 17 realistic brands (Atelier Nord: 7, Harbor & Thread: 7, Gully Street: 7, etc.). |
| **Price** | 60 / 60 | 100.0% | Min: ₹999.00, Max: ₹14,999.00, Avg: ₹3,894.00, Median: ₹2,999.00. |
| **Currency** | 60 / 60 | 100.0% | 100% `INR`. |
| **Availability (Stock)** | 60 / 60 | 100.0% | 100% `True` (all marked in stock). |
| **Image URLs** | 60 / 60 | 100.0% | Exactly 1 image URL per product. |
| **Image URL Validity** | **0 / 60** | **0.0%** | All point to `cdn.fixture.test` (RFC 2606 reserved domain; unroutable). |
| **Material (Attribute)** | 60 / 60 | 100.0% | Detailed values (e.g. `khadi_cotton`, `block_print_cotton`, `french_terry_cotton`). |
| **Color (Attribute)** | 60 / 60 | 100.0% | Detailed values (e.g. `ecru`, `washed_black`, `indigo`, `olive`, `navy`). |
| **Fit (Attribute)** | 60 / 60 | 100.0% | Values: `relaxed`, `regular`, `boxy`, `slim`, `tailored`, `oversized`. |
| **Silhouette (Attribute)**| 60 / 60 | 100.0% | Values: `short_kurta`, `mandarin_collar`, `oversized`, `tapered`, etc. |
| **Occasion (Attribute)** | **0 / 60** | **0.0%** | Not present in product attributes; inferred via category rules in `analysis_rules.py`. |
| **Season (Attribute)** | 60 / 60 | 100.0% | 100% marked `all-season`. |
| **Test Barcode (GTIN-14)**| 60 / 60 | 100.0% | Stored in `attributes.identifiers.gtin` with valid GS1 modulo-10 check digits. |
| **Synthetic Flag** | 60 / 60 | 100.0% | `attributes.synthetic = True`. |
| **Fixture Flag** | 60 / 60 | 100.0% | `attributes.fixture = True`. |

### 2.2 Duplication and Anomaly Analysis
- **Duplicate Products:** 0 duplicates. All 60 products have unique titles, unique GTIN barcodes, and unique product URLs.
- **Source Map Integrity:** `product_source_map` has exactly 60 rows, mapping 60 distinct `source_product_id`s to 60 distinct `product_id`s under source `fashion_seed`.
- **Observation History:** Exactly 60 observation rows in `product_observations`.
- **Idempotency:** Re-running the collection pipeline resulted in `fetched=60, inserted=0, updated=0, skipped=60, failed=0` (verified in `collection_runs` run #2).
- **Implausible Values:** Zero invalid prices, negative values, or empty title strings.

### 2.3 Classification and FFO Mapping Coverage
*Evaluation: Executed `map_product_attributes_to_ffo` across all 60 catalog products.*

| Metric | Result | Detail |
|---|---|---|
| **Total Mapped Concepts** | 172 concepts | Across 60 products. |
| **Mean Concepts Per Product** | 2.87 concepts | Min: 1 concept, Max: 6 concepts. Products with 0 concepts: 0. |
| **Ontology Verification** | **100.0% Verified** | 172/172 mapped concepts exist in verified canonical FFO corpus. 0 unverified concepts. |
| **Concepts by Entity Kind** | `material`: 57<br>`fit`: 38<br>`aesthetic`: 24<br>`color`: 19<br>`culture`: 11<br>`textile`: 9<br>`silhouette`: 5<br>`footwear`: 5<br>`accessory`: 2<br>`garment`: 1<br>`bag`: 1 | Materials and fits map well; garment silhouettes and accessories have low coverage. |
| **Unmapped Attributes** | `style_tags`: 58/60 (96.7%)<br>`silhouette`: 55/60 (91.7%)<br>`subcategory`: 51/60 (85.0%)<br>`color`: 41/60 (68.3%)<br>`fit`: 22/60 (36.7%)<br>`material`: 3/60 (5.0%) | Bridge lacks mappings for complex colors (`ecru`, `washed_black`, `dusty_rose`), garment silhouettes (`long_kurta`, `mandarin_collar`), and artisanal style tags (`artisan`, `heritage`). |
| **Mapping Provenance** | Rule-tracked | Every mapping records rule provenance (e.g. `rule:fit_normalization`, `rule:style_tag_aesthetic`, `rule:material_composite_cotton`). |

---

## 3. For You Personalization and Ranking Scorecard

### 3.1 Scoring Formula and Dimension Breakdown
Implemented in `backend/app/domain/services/personalization.py`:

$$\text{Total Score} = \min(100.0, \, S_{\text{pref}} + S_{\text{style}} + S_{\text{wardrobe}} + S_{\text{budget}})$$

1. **Preference Match ($S_{\text{pref}} \in [0.0, 40.0]$):**
   - Category match: $+10.0$ pts
   - Brand match: $+10.0$ pts
   - Color match: $+8.0$ pts
   - Material match: $+6.0$ pts
   - Fit match: $+3.0$ pts
   - Silhouette match: $+3.0$ pts
   - *Missing preference dimensions remain neutral ($0.0$ pts) and are tracked in `neutral_dimensions`.*
2. **Style Profile Match ($S_{\text{style}} \in [0.0, 25.0]$):**
   - Aesthetic / Style type match: $+15.0$ pts
   - Occasion alignment: $+10.0$ pts
3. **Wardrobe Complementarity ($S_{\text{wardrobe}} \in [0.0, 20.0]$):**
   - Palette synergy (neutral color or matches frequent/favorite wardrobe colors): $+10.0$ pts
   - Category gap filling (user owns $< 2$ items in category): $+5.0$ pts
   - Natural material synergy: $+5.0$ pts
   - *Neutral ($0.0$ pts) when user has no wardrobe.*
4. **Budget & Availability ($S_{\text{budget}} \in [0.0, 15.0]$):**
   - In-stock verified: $+5.0$ pts
   - Verified price present: $+5.0$ pts
   - Within budget (or no budget constraint set): $+5.0$ pts

### 3.2 Evaluation of Determinism and Differentiation

| User Context | Observed Score Range | Differentiating Factors | Ranking Determinism | Semantic Accuracy |
|---|---|---|---|---|
| **Guest / Cold-Start** | **Flat 15.0% for 100% of products** | None. All products receive identical scores ($0 + 0 + 0 + 15$). | Ordered by UUID string ascending (`str(item.id)`). | **Misleading**: Displays "15% STYLE MATCH" on every item when no style match occurred. It is purely a commercial-validity score. |
| **Authenticated (with Wardrobe & Profile)** | **20.0% to 25.0%** (Tony) | Wardrobe palette match (+10 pts) and category gap filling (+5 pts). | Deterministic: `(-score, -created_at, str(item.id))`. | **Artificially Low**: Score is depressed to $\le 25\%$ because preference keys are dropped by the `camelCase`/`snake_case` bug. |

### 3.3 Known Limitations
- **Offline Relevance Benchmark:** Fansivibe has **zero offline relevance benchmarks** (e.g., NDCG@10, MRR, or human relevance judgment sets) for product recommendations. Personalization scoring is a heuristic rules engine, not an empirically validated machine learning ranker.
- **Recommendation Pool Boundary:** `for_you.py` caps initial candidate retrieval to 500 items (`max_pages = min(first_page.total_pages, 5)`). If the catalog expands beyond 500 items, products beyond item 500 are never retrieved or scored.
- **Section Duplication:** Section 1 (Personalized Hero) displays `_apiRecommendations.first` (Item #1). Section 5 (Grid) displays `_apiRecommendations.sublist(1)` (Items #2–20). This avoids immediate duplicate rendering between hero and grid, but hero items remain visible if the user changes categories or resets filters.

---

## 4. Trending Evidence Integrity Scorecard

### 4.1 Signal Status by Evidence Domain

| Evidence Signal Domain | Architectural Component | Operational Status | Evidence Integrity & Truth-in-Reporting Verdict |
|---|---|---|---|
| **Catalog Activity** | D6 Trend Intelligence Engine (`trends.py`), `product_observations` table | **Operational (Dev DB)** | **Verified & Honest**: 60 observations analyzed across 5 categories. Accurately reports listing counts and observation frequencies. Correctly flags all seed data with `REASON_FIXTURE` and enforces `publishable = False`. |
| **Media Attention** | D9B GDELT Collection (`gdelt_source.py`), `media_attention_observations` table | **Inactive / Unverified** | **Verified Absent in DB**: Table `media_attention_observations` contains 0 rows in PostgreSQL. Historical 7-day GDELT queries timed out in task D9C.2. No active live media attention ingestion is running. |
| **Consumer Demand** | `search_interest_observations`, Google Trends / PA-API | **Explicitly Unavailable** | **Verified Preserved**: `DEMAND_SIGNAL_AVAILABLE = False` is strictly hardcoded in `trends.py`. Direct-demand signals (`search_interest`, `sales_velocity`, `review_growth`) return `available = False, value = None`. |

### 4.2 UI Integrity vs Backend Engine Integrity
- **Backend Integrity:** 100% compliant. The D6/D7 engine never converts catalog listing frequency into consumer demand claims.
- **Flutter UI Disconnect:** In `discover_screen.dart`, while `TrendingEvidenceStatusCard` accurately displays `DEMAND_SIGNAL_AVAILABLE = False` and `insufficient_evidence`, the rest of the Trending tab displays hardcoded mock editorial cards:
  - `SpotlightHeroCard`: hardcoded styling hero.
  - `EditorialLookCard`: hardcoded `"1.4K SAVES"` and `"920 SAVES"`.
  - `EditorialCommerceItemCard`: hardcoded `"Most saved across top global wishlists"`.
  - These hardcoded cards create a direct semantic contradiction with the honest status card.

---

## 5. Complete Looks Quality Scorecard

### 5.1 Architectural & Compatibility Assessment

| Dimension | Implementation | Assessment & Evidence |
|---|---|---|
| **Slot Coverage** | `DEFAULT_OUTFIT_SLOTS` defines `top` (req), `bottom` (req), `footwear` (opt), `outerwear` (opt), `accessories` (opt). | **Enforces All Available Slots**: If candidates exist for optional slots, the algorithm generates only 5-piece combinations, ignoring valid 2- or 3-piece looks. |
| **Compatibility Scoring** | Category completeness (25 pts), Color harmony (25 pts), Material synergy (20 pts), Style/FFO alignment (15 pts), Silhouette balance (15 pts). | **Rules-Based & Explainable**: Verified in test suite. Gives honest neutral scores when materials or colors are unstated. |
| **Budget Enforcement** | Catalog items: $\sum \text{price} \le \text{max\_budget}$. | **Verified Correct**: Accurately sums catalog prices. Returns 0 looks when budget is lower than minimum 5-piece combination. |
| **Wardrobe Integration** | Owned wardrobe items priced at ₹0 catalog spend. | **Verified Correct**: In live DB test with Tony's wardrobe, 3 wardrobe pieces contributed ₹0.00; total catalog price was ₹5,598.00 (only for jacket + cap). |
| **Anchor Isolation** | Locks outfit around owned item or catalog item. | **Verified Secure**: Foreign wardrobe item ID fails closed with 404; unauthenticated guest anchor fails closed with 401. |
| **Bundle Purchasing** | `bundlePurchasable = False` | **Verified Disclosed**: Wire DTO and Flutter UI explicitly state bundle purchasing is unavailable; individual items must be acquired separately. |

### 5.2 Combinatorial Diversity Collapse
- **Finding:** Testing with `limit = 5` demonstrated that the assembly algorithm produces identical 4-piece cores:
  - Look 1: Ajrakh Shirt + Carpenter Pants + Khadi Espadrilles + Harrington Jacket + **Corduroy Cap** (₹12,795)
  - Look 2: Ajrakh Shirt + Carpenter Pants + Khadi Espadrilles + Harrington Jacket + **Silk Scarf** (₹12,995)
  - Look 3: Ajrakh Shirt + Carpenter Pants + Khadi Espadrilles + Harrington Jacket + **Market Tote** (₹13,195)
  - Look 4: Ajrakh Shirt + Carpenter Pants + Khadi Espadrilles + Harrington Jacket + **Leather Belt** (₹13,595)
  - Look 5: Ajrakh Shirt + Carpenter Pants + Khadi Espadrilles + Harrington Jacket + **Brass Belt** (₹13,895)
- **Root Cause:** Standard Cartesian product loops outer slots first and breaks ties with price ascending. Once the top-scoring (Top, Bottom, Footwear, Outerwear) quad is evaluated, the tie-breaker exhaustively enumerates the accessory pool before ever trying a different shirt, jacket, or pair of pants.
- **Impact:** Requesting multiple looks fails to provide aesthetic variety.

---

## 6. Interaction Feedback Map

| User Action | Device-Local vs Persisted | Associated User | Defined Schema & Idempotency | Consumed by Ranking Pipeline? | Claimed vs Actual Behavior |
|---|---|---|---|---|---|
| **Save Product (Heart icon)** | Device-Local only (`LocalStorage.savedLookIds`) | None | None (no network payload) | **No** (ignored by backend) | Claimed "Learning style affinity" is purely an on-device integer counter (`styleScore`); zero backend effect. |
| **Save Editorial Look** | Device-Local only (`LocalStorage.savedLookIds`) | None | None | **No** (ignored by backend) | Updates local `LearningService.savedLooks` list; zero backend effect. |
| **Click Product / View Detail** | Device-Local only (in-memory route or snackbar) | None | None | **No** | Local UI action only; no backend event emitted. |
| **Dismiss Product** | **Not Implemented** | N/A | N/A | N/A | No dismiss button or negative feedback mechanism exists in Discover UI. |
| **Select Complete Look Candidate** | Device-Local widget state (`_selectedLookIndex`) | None | None | **No** | Re-renders card details in Flutter; zero persistence. |
| **Tap Outbound "Shop"** | Device-Local dialog / snackbar | None | None | **No** | Shows "Synthetic Demo Product" dialog or "Opening retailer..." snackbar; no affiliate link tracking. |
| **Add Item to Wardrobe** | **Persisted on Backend** (`POST /v1/wardrobe`) | Authenticated `user_id` | `WardrobeItemCreate`, session auth | **Yes (Indirectly)** | New wardrobe items are ingested into PostgreSQL and subsequently read by `PersonalizeForYou` and `AssembleCompleteLooks`. |
| **AI Stylist Reaction** | **Persisted on Backend** (`POST /v1/feedback`) | Authenticated `user_id` | `FeedbackCreate`, `Idempotency-Key` header | **No (For Discover)** | Only accepts AI Stylist hairstyle/grooming `look_id`; does not accept catalog products or complete looks. |

---

## 7. Performance, Reliability, and Security Audit

### 7.1 Database Query Efficiency & N+1 Analysis
- **For You Personalization:**
  - Authenticated query executes: 1 profile query (`user_state`) + 2 wardrobe queries (count + get) + 2 candidate retrieval queries (count + get with limit 100).
  - Total: **5 queries per request**. Bounded and performant for single-user load.
  - However, if the catalog exceeds 100 items, `for_you.py` executes sequential paginated candidate retrieval queries (up to 5 queries), generating up to **9 queries per request**.
- **Complete Looks Assembly:**
  - Evaluates 5 slots sequentially. For each slot, it executes `count_candidates` + `get_candidates`.
  - Total: **10 database queries per assembly request** (plus 2 wardrobe queries if authenticated).
  - *Recommendation:* Consolidate slot retrieval into a single SQL query: `SELECT * FROM products WHERE category IN ('tops', 'bottoms', 'footwear', 'outerwear', 'accessories') ...`.

### 7.2 Security, Isolation, and Privacy Boundaries
- **Guest / Authenticated Isolation:** Verified strictly enforced in `api/deps.py` (`get_optional_user_id`). Invalid tokens fail closed with HTTP 401 instead of silently falling back to guest. Guest requests cannot query user profiles or user wardrobes.
- **Wardrobe Ownership Guard:** In `AssembleCompleteLooks`, specifying a foreign wardrobe item ID fails closed with HTTP 404 (or `ValueError`); guests attempting to anchor to a wardrobe item receive HTTP 401.
- **Sensitive Data Logging:** Audited `discovery.py`, `for_you.py`, `complete_looks.py`, and `grounded_explanations.py`. Zero logging of passwords, tokens, auth headers, or private user image bytes.

### 7.3 Test Suite Integrity
- **Backend Tests:** 33/33 unit tests pass cleanly in 0.66s. All 43 DB-backed tests skip cleanly in offline environments, preventing accidental truncation of development QA data.
- **Flutter Tests:** 63/63 Discover tests in `test/discover_unified_widgets_test.dart`, `test/discover_unified_api_test.dart`, `test/discover_screens_test.dart`, and `test/for_you_test.dart` pass 100%. Full Flutter suite passes 1,378/1,378 tests (100%).
- **Static Analysis:** `flutter analyze lib/features/discover/` is 100% clean (0 issues).

---

## 8. Prioritized Implementation Plan

| Priority | Task Identifier | Task Name | User & System Impact | Engineering Effort | Dependencies | Testability |
|---|---|---|---|---|---|---|
| **P0** | **DISCOVERY-09A** | **User Preferences Schema Normalization (`snake_case` / `camelCase`)** | **High**: Unblocks personalization for all existing and new authenticated users. Restores preference match scores from $0$ to up to $40$ pts. | **Low** (1 day) | None (in-place fix in `for_you.py` and `user_state.py`) | Unit & integration tests in `test_for_you_personalization.py` |
| **P1** | **DISCOVERY-09B** | **Complete Looks Diversity Re-ranking & Flexible Slot Cardinality** | **High**: Eliminates diversity collapse. Enables true multi-look discovery (distinct tops/bottoms) and allows 2-piece / 3-piece outfits under modest budgets ($\le ₹5,000$). | **Medium** (2 days) | DISCOVERY-04 assembly service | Deterministic combination tests in `test_complete_looks.py` |
| **P1** | **DISCOVERY-09C** | **Server-Backed Discovery Search (`q` query parameter)** | **High**: Fixes client-side search disconnect. Allows searching the entire catalog across all pages, titles, brands, and categories. | **Medium** (2 days) | FastAPI discovery router & Flutter client | Wire tests in `test_discovery_api.py` and Flutter widget tests |
| **P1** | **DISCOVERY-09D** | **Trending Screen De-mocking & Semantic Alignment** | **High**: Eliminates deceptive mock claims ("1.4K SAVES", mock Zara/Adidas items) surrounding the honest evidence status card. | **Low** (1 day) | Flutter `discover_screen.dart` | Widget tests in `discover_screens_test.dart` |
| **P2** | **DISCOVERY-10A** | **Discover Interaction Telemetry (`POST /v1/discovery/events`)** | **Medium**: Enables server-side tracking of product impressions, clicks, saves, and affiliate clicks for future learning. | **Medium** (3 days) | Requires new table or ledger (gated by Alembic head 0029 approval) | Integration tests in `test_discovery_events.py` |
| **P2** | **DISCOVERY-10B** | **Permitted Public Catalog Enrichment (Routable CDN Assets)** | **High**: Replaces unroutable `cdn.fixture.test` URLs with accessible public domain or permitted fixture assets. | **Medium** (2 days) | Offline fixture assets | Seed validation in `test_fashion_catalog_seed.py` |

---

## 9. Recommended Next Milestone: TASK DISCOVERY-09A

### Rationale
**TASK DISCOVERY-09A (User Preferences Schema Normalization)** should precede all other tasks.

- **Why First:** It is a zero-risk, high-impact correctness fix that directly repairs the broken link between stored user preferences and the recommendation scoring engine. It requires zero database migrations, zero external credentials, zero API contract changes, and zero changes to frozen FFO reasoning contracts.
- **Scope of Change:**
  - Update `backend/app/application/for_you.py` (lines 102–132) to accept both `snake_case` and `camelCase` keys when extracting `user_state.preferences`:
    - `preferred_categories` / `preferredCategories`
    - `preferred_occasions` / `preferredOccasions`
    - `preferred_brands` / `preferredBrands`
    - `preferred_colors` / `preferredColors`
    - `preferred_materials` / `preferredMaterials`
    - `excluded_categories` / `excludedCategories`
  - Update `PersonalizationPreferences` extraction to normalize case and strip whitespace robustly.
- **Acceptance Criteria:**
  - Running `PersonalizeForYou` for user Tony (`308eb2ea-af86-4806-97ea-66076b703ef5`) extracts `preferred_occasions = ('casual', 'business')` and reflects occasion matching in the style score breakdown ($+10.0$ pts) and match reasons.
  - All existing unit tests pass cleanly without regression.
  - Zero database schema migrations added.

---

## 10. Audit Sign-Off and Execution Boundaries

- **Code Modifications in this Audit:** Exactly **0 production files modified**.
- **Database Records Changed:** Exactly **0 rows inserted, updated, or deleted**.
- **Frozen Boundaries Maintained:**
  - Alembic head strictly `0029 (head)`.
  - FFO reasoning contracts, prompts, benchmarks, and corpus digest (`967f891e4c91d4e9463be5ea183b62ad3f3548f35c1b1e4d8678da49bf4d2581`) untouched.
  - `DEMAND_SIGNAL_AVAILABLE = False` strictly preserved.
  - Flutter Digital Atelier 65/35 card proportions untouched.
  - Installed local AI model untouched.
  - Zero external HTTP API calls made.

*Audit complete. Awaiting explicit user approval before proceeding to implementation.*
