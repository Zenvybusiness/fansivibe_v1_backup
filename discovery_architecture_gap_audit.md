# Fansivibe Discovery Architecture Gap Audit and Implementation Roadmap

**Document Status**: COMPREHENSIVE ARCHITECTURAL AUDIT & IMPLEMENTATION ROADMAP  
**Task Identifier**: TASK DISCOVERY-01  
**Execution Date**: 2026-10-13  
**Auditor**: Antigravity Pair Programming Agent  
**Alembic Migration Head**: `0029` (Strictly Verified)  
**Backend Test Suite**: 1,961 passed, 1 skipped (100% clean)  
**Flutter Test Suite**: 1,340 passed, 0 failed across 107 test files (100% clean)  
**Flutter Static Analysis**: 0 issues (`flutter analyze` 100% clean)  
**Installed Local Model**: `qwen3-vl:4b-instruct` (4.4B Q4_K_M, digest `ee4b975b58c1`)  
**Reasoning Qualification**: `qwen2.5vl:3b` affirmed per DEC-030; `qwen3-vl:4b-instruct` declared incompatible for reasoning  
**Production Demand Signal**: `DEMAND_SIGNAL_AVAILABLE = False` (Strictly Preserved)  
**Code Changes in this Task**: ZERO (Audit and Planning Only)

---

## 1. Executive Summary

This audit establishes the comprehensive, empirical baseline of Fansivibe's **Discovery architecture** across:
1. **For You** — personalized fashion recommendations and shoppable product matching.
2. **Trending** — evidence-backed macro fashion trend discovery.
3. **Complete Looks** — coordinated multi-product outfits and wardrobe-complementary ensembles.

### Core Audit Verdict
Fansivibe contains mature, rigorously tested foundational subsystems:
- A sophisticated **database schema** (PostgreSQL 18.6, Alembic head `0029`) supporting raw ingestion, canonical product identity, observation history, search interest, and media attention.
- A deterministic **product normalization and identity engine** (`normalization.py`, `product_identity.py`) adhering to DEC-023/DEC-024.
- A fail-closed **Trend Intelligence Engine** (D6 `trends.py`, D7 `trend_analysis.py`) validated against FFO JSON Schemas with `DEMAND_SIGNAL_AVAILABLE = False`.
- A frozen **Fashion Ontology & Reasoning framework** (FFO v1.0, 3T admission, 3P selector, SHA-256 corpus digest).
- An award-winning **Flutter Digital Atelier presentation layer** (`discover_screen.dart`, `existing_user_for_you_widgets.dart`) observing the strict 65% visual / 35% content card proportion rule.

**However, Discovery is NOT operationally connected end-to-end**:
1. **Zero Real Catalog Products in Storage**: The `products`, `product_source_map`, and `product_observations` tables contain **0 rows** in development/production databases.
2. **Surface Disconnect in Flutter**:
   - The Flutter `DiscoverScreen` connects via `DiscoverRepositoryImpl` to `GET /v1/looks`, which serves only the **8 static hairstyle and grooming styles** from `catalog.py`.
   - The `Trending` tab displays hardcoded editorial mock cards (`look_urban_minimal`, `Tailored Wool Coat`, `Samba OG Archive`) with mock strings (`1.4K SAVES`).
   - The `For You` tab for established users renders `EstablishedUserForYouFeed`, which builds hardcoded mock product models (`hero_cos_overshirt`, `COS`, ₹12,500).
   - The Flutter `trending_client.dart` calls legacy endpoint `GET /v1/trending` (an in-memory test fixture), but is entirely unused by `DiscoverScreen`.
   - The Flutter client has **zero integration** with the D7 `GET /v1/trends/analysis` endpoint.
3. **No External Live Data Flowing**:
   - GDELT DOC 2.0 collection is implemented with 5.5s pacing and exponential backoff, but its live availability remains **unverified** following read timeout on cold historical archives (D9C.2).
   - Google Trends API is an application-gated Alpha with credentials **not configured**.
   - Commercial e-commerce/affiliate feeds (Flipkart, Amazon.in PA-API, Myntra) have **zero configured credentials or live pipelines**.
4. **No Discovery Interaction Tracking**: User clicks, saves, dwell time, and outbound affiliate actions in Discover do not write to any persistent event ledger.

The system requires an incremental, phased implementation to connect the permitted data ingestion pipeline to canonical storage, shared intelligence, candidate ranking, grounded explanations, and the Flutter presentation layer.

---

## 2. Component-by-Component Architectural Audit Matrix

| # | Architecture Component | Actual Files & Classes | Database Tables | Status | Reusable Dependencies | Missing Connections & Gaps | Credentials / External Req. | Local Dev Feasibility |
|---|---|---|---|---|---|---|---|---|
| **1** | **External Data Sources** | `backend/app/infrastructure/external/fixture_source.py`<br>`synthetic_search_interest_source.py`<br>`gdelt_source.py` | None | **Partially Implemented / Unverified** | `SourceAdapter` protocol, `RawSourceRecord`, `SourceBatch` | No real fashion catalog source active; GDELT live collection unverified (D9C.2 timeout); Google Trends alpha gated | YouTube API key, GDELT (public), Amazon PA-API, Flipkart Affiliate, Google Trends Alpha | **Yes** (via bundled offline fixtures & synthetic sources) |
| **2** | **Source Adapters** | `app.infrastructure.external.fixture_source.FixtureSourceAdapter`<br>`app.infrastructure.external.gdelt_source.GdeltSourceAdapter`<br>`SyntheticSearchInterestAdapter` | None | **Partially Implemented** | `SourceAdapter` base protocol, `SourceError` taxonomy, cooperative deadline | Missing commercial product catalog adapter (Flipkart/Rainforest/Amazon); missing fashion RSS/runway adapter | None for offline adapters; Affiliate/API keys for live adapters | **Yes** (100% offline via `FixtureSourceAdapter`) |
| **3** | **Ingestion, Normalization & Product Identity** | `app.domain.services.normalization.normalize_product`<br>`app.domain.services.product_identity.resolve_identity`<br>`app.application.collection.CollectSource` | `collection_runs`<br>`raw_source_records`<br>`products`<br>`product_source_map`<br>`product_observations` | **Implemented (Backend Core)** | `payload_hash` SHA-256, GTIN check-digit validator, conservative matching (DEC-023) | Batch pipeline not scheduled; no automated product categorization into FFO taxonomy; zero rows in DB | None (pure Python and PostgreSQL) | **Yes** (100% operable locally) |
| **4** | **Product Catalog, Images & Search Index** | `app.infrastructure.db.models.Product`<br>`ProductSourceMap`<br>`ProductObservation`<br>`alembic/versions/0026_discovery_foundation.py` | `products`<br>`product_source_map`<br>`product_observations` (0 rows) | **Partially Implemented (Schema only, empty data)** | PostgreSQL 18.6 JSONB indexing, `products` category/brand B-tree indexes | Zero rows populated; no full-text search index (`tsvector`); no vector embedding index; image URLs stored as strings without CDN verification | None | **Yes** (local PostgreSQL) |
| **5** | **User Profile, Wardrobe & Context** | `app.infrastructure.db.models.UserState`<br>`WardrobeItems`<br>`WardrobeWearEvents`<br>`UserEvent`<br>`SavedLooks` | `user_state`<br>`wardrobe_items` (46 rows)<br>`wardrobe_wear_events`<br>`user_events`<br>`saved_looks` (8 rows) | **Implemented (User Domain)** | `UserStateRepositorySQL`, `WardrobeItemRepositorySQL`, `WearSummary` (DEC-012) | Disconnected from Discover: user style DNA, wardrobe items, and wear events are never queried by Discover feeds | None | **Yes** (local PostgreSQL) |
| **6** | **Shared Discovery Intelligence Layer** | `app.data.ffo.schemas/*`<br>`app.data.ffo.corpus.py`<br>`app.domain.services.ffo_retrieval.py`<br>`app.domain.services.conclusion_admission.py` | FFO JSON Schema files, corpus digest | **Implemented (Offline FFO)** | FFO v1.0 schemas (product, trend, outfit), 3T admission rules, 3P selector | No bridge linking commercial `products` table rows to FFO concept nodes; no shared candidate generation | None | **Yes** (local Python) |
| **7** | **Trending Intelligence** | `app.domain.services.trends.compute_trend_candidates`<br>`app.application.trends.AnalyzeTrends`<br>`app.api.routers.trend_analysis.py`<br>`GET /v1/trends/analysis` | `product_observations`<br>`search_interest_observations`<br>`media_attention_observations` | **Partially Implemented (Engine ready, signal unverified)** | D6 engine, D7 API, FFO schema validation, `DEMAND_SIGNAL_AVAILABLE = False` | `DEMAND_SIGNAL_AVAILABLE = False` blocks publication; Flutter has zero connection to D7 API; M14 `/v1/trending` is a test fixture | None for catalog growth; GDELT/Trends for demand signals | **Yes** (returns typed `insufficient_evidence` honest state) |
| **8** | **For You Personalization** | `backend/app/application/discover.py` (`GetForYouFeed`)<br>`backend/app/api/routers/looks.py` (`GET /v1/looks/for-you`) | `saved_looks`<br>`looks` (8 rows) | **Partially Implemented (Hair/Grooming only; Products Missing)** | +0.03 saved-look boost precedent, cursor pagination (`_paginate`) | Endpoint only re-sorts 8 hairstyle/grooming looks; zero product recommendations; Flutter displays mock data for established users | None | **Yes** |
| **9** | **Candidate Generation, Hard Filters & Ranking** | `app.domain.services.analysis_rules.py`<br>`app.application.outfits.py` | None | **Missing for Discovery Products** (Implemented for Wardrobe Outfits) | `rank_outfit_candidates`, deterministic tie-breaking, budget rebalancing | No candidate retrieval for catalog products; no price/gender/stock hard filters; no diversity re-ranking for Discover | None | **Yes** |
| **10** | **Explanation Engine** | `app.domain.services.analysis_rules.py`<br>`app.domain.services.ffo_reasoning.py`<br>`test_p2s2_explainability.py` | None | **Missing for Products / Trends** (Implemented for Outfits & FFO) | Grounded reason composition rules (`FIT_REASON`, `PALETTE_REASON`) | Discover returns hardcoded strings in Flutter ("Matches your neutral palette"); no backend explanation generator for products | None | **Yes** |
| **11** | **Complete Looks & Product Matching** | `backend/app/application/outfits.py` (`GenerateOutfit`)<br>`newproject/flutter_application_1/.../existing_user_for_you_widgets.dart` | None | **Missing for Commercial Products** (Implemented for Wardrobe Outfits) | FFO `outfit.schema.json` compatibility model, Outfit generator | Commercial items cannot be combined into outfits; "Complete the Look" (pairing product with user wardrobe) is a mock UI snackbar | None | **Yes** |
| **12** | **Flutter API Integration & Presentation** | `newproject/flutter_application_1/lib/features/discover/presentation/discover_screen.dart`<br>`discover_client.dart`<br>`trending_client.dart` | Client local storage | **Partially Implemented (UI complete, API disconnected)** | Digital Atelier design tokens, 65/35 card proportions, `SpotlightHeroCard`, `LookCard` | UI falls back to hardcoded mock cards; `trending_client.dart` is unused; D7 API is never called; established user feed is synthetic | None | **Yes** |
| **13** | **Interaction Events & Feedback Loop** | `backend/app/api/routers/feedback.py`<br>`backend/app/api/routers/wardrobe.py`<br>`lib/shared/analytics/analytics_service.dart` | `feedback_events`<br>`learning_signals`<br>`activity_days`<br>`wardrobe_wear_events` | **Partially Implemented (Outfits only; Discover Missing)** | M10/M11 signal write pipeline, `activity_days` streak tracking, wear ledger | Discover impressions, clicks, wishlist saves, and outbound affiliate taps do not emit backend events or update user affinity | None | **Yes** |

---

## 3. Data-Source and External Provider Readiness Matrix

| Provider & API | Data Provided & Product Use | Authentication / Prerequisites | Current Access Status | Official Credential Setup Page | Terms, Rate Limits & Attribution Rules | Local Dev vs Production Requirements | Fallback Strategy |
|---|---|---|---|---|---|---|---|
| **A. Flipkart Affiliate API** | Indian fashion catalog, SKU search, INR pricing, stock status, CDN image URLs | Registered Affiliate account, `Fk-Affiliate-Id`, `Fk-Affiliate-Token` | **Missing / Not Configured** | `https://affiliate.flipkart.com` | - Standard affiliate request throttling<br>- Prohibits image scraping/self-hosting<br>- Direct hotlinking to `rukminim1.flixcart.com`<br>- Solely to promote sales | Dev: Seeded offline fixture records (`fixture_source.py`)<br>Prod: Active Affiliate credentials in env | Bundled offline product fixtures |
| **B. Amazon.in PA-API 5.0** | Amazon India catalog, ASIN search, live INR pricing, prime/stock status, CDN images | AWS Access Key, Secret Key, Associate Tag. **Gate: 3 qualifying sales in 180 days** | **Application Gated / Not Configured** | `https://affiliate-program.amazon.in`<br>`https://webservices.amazon.com/paapi5` | - 1 req/sec initial, dynamically throttled<br>- Direct hotlinking to `m.media-amazon.com`<br>- Daily price/availability refresh mandatory<br>- Image caching prohibited | Dev: Mock/fixture products<br>Prod: AWS IAM credentials + Associate Tag | Rainforest API (commercial proxy) or offline fixtures |
| **C. Rainforest API** | Commercial proxy scraping Amazon.in product data, search, and pricing | Commercial SaaS API key (`rainforestapi.com`) | **Missing / Not Configured (Paid SaaS)** | `https://rainforestapi.com` | - Tiered monthly credits ($18–$66/mo)<br>- Returns direct Amazon CDN image URLs<br>- Subject to Amazon trademark rules | Dev: Mock responses<br>Prod: Paid API key via `RAINFOREST_API_KEY` | Offline product fixtures |
| **D. Myntra / Ajio (via Cuelinks)** | Affiliate deep-link monetization and campaign tracking (no product feeds) | Cuelinks Publisher account, API token | **Missing / Not Configured** | `https://developers.cuelinks.com` | - Link wrapping only; **NO product feeds or search API**<br>- Commercial affiliate monetization | Dev: Standard mock URLs<br>Prod: Cuelinks publisher token in env | Direct merchant product links |
| **E. Google Trends (BigQuery)** | Macro country-level search interest & top rising queries | GCP Project, Service Account JSON with BigQuery Data Viewer permissions | **Missing / Not Configured** | `https://cloud.google.com/bigquery` | - 1 TB/month free query tier<br>- Top 25 national terms daily<br>- 30-day partition TTL in public dataset<br>- Bulk raw data redistribution prohibited | Dev: Synthetic search interest (`synthetic_search_interest_source.py`)<br>Prod: GCP Service Account JSON | Synthetic search interest adapter |
| **F. Google Trends API (Alpha)** | Relative search interest curves across fashion concepts and categories | Application-gated Alpha access approval from Google Search team | **Application Gated / Unverified** | `https://developers.google.com/search/apis/trends` | - Terms and quotas non-public until accepted<br>- Rolling 5-year window, daily/weekly intervals<br>- Relative scaled metrics (not absolute volume) | Dev: Synthetic search interest<br>Prod: Approved Alpha credentials | Synthetic search interest adapter |
| **G. GDELT DOC 2.0 API** | Global editorial press attention, article counts, outlet diversity | Public unauthenticated API (`api.gdeltproject.org`). No key needed. | **Implemented / Unverified (Read Timeout)** | `https://www.gdeltproject.org` | - Minimum pacing interval: 5.5s (DEC-029)<br>- Exponential backoff base: 5.0s<br>- Shared-IP rate limits<br>- Read timeout on cold 7-day archive queries | Dev: SimulatedClock offline tests (`test_d9b_gdelt_collection.py`)<br>Prod: 24h rolling index queries only | Fail-closed (`status="failed"`, 0 observation rows) |
| **H. YouTube Data API v3** | Video velocity, fashion/style (Cat 26) creator engagement in India | GCP API Key with YouTube Data API v3 enabled | **Missing / Not Configured** (Setting field exists: `youtube_data_api_key`) | `https://console.cloud.google.com/apis/library/youtube.googleapis.com` | - 10,000 quota units/day default<br>- `videos.list` = 1 unit per call<br>- Max 30-day statistics cache<br>- Mandatory YouTube branding | Dev: Test adapter fixtures<br>Prod: GCP API key in `YOUTUBE_DATA_API_KEY` | Test adapter fixtures |
| **I. Social Platforms (Pinterest, Meta, TikTok)** | Aesthetic trends, hashtag velocity, runway commentary | Highly restricted / Gated / Prohibited | **Prohibited / Incompatible** | N/A | - **Pinterest**: India (`IN`) excluded from API enum<br>- **Instagram**: 30 hashtags/7d limit blocks discovery<br>- **Meta Content Library**: Commercial use banned<br>- **TikTok**: Banned in India under Sec 69A IT Act | Permanent Exclusion from India commercial pipeline | Rely on permitted sources (YouTube, GDELT, Google Trends) |
| **J. Local Ollama & Backend AI** | Multimodal appearance/garment analysis; FFO reasoning | Local Ollama daemon (`http://127.0.0.1:11434`) | **Operational (Vision) / Gated (Reasoning)** | Local installation | - `qwen3-vl:4b-instruct` installed (4.4B)<br>- Operates vision inference reliably<br>- Incompatible for FFO reasoning per DEC-030 (empty answer on abstention; 6GB OOM-kill)<br>- `qwen2.5vl:3b` affirmed qualified reasoning model | Dev: Local Ollama on port 11434<br>Prod: Local Ollama daemon | Rule-based decision engine |

---

## 4. Preservation of Architectural Boundaries and Existing Work

During this audit, all repository rules and architectural freezes were strictly verified:
1. **FFO Reasoning Integrity**: Zero changes to `reasoning_prompt.py`, `conclusion_admission.py`, `ffo_ref_selector.py`, `ffo_reasoning.py`, `ffo_benchmark.py`, benchmarks (`benchmark_v01.json`, `benchmark_heldout_3ai.json`), and the FFO corpus digest.
2. **D6/D7 Trend Architecture**: `DEMAND_SIGNAL_AVAILABLE = False` is strictly preserved in `backend/app/domain/services/trends.py` (line 61) and `trend_analysis.py`. Catalog activity is never labeled as consumer demand.
3. **Database Schema & Migrations**: Alembic migration head remains strictly `"0029"` (`0029_media_attention_observations.py`). Zero new migrations added.
4. **Design System & Card Proportions**: The Flutter Digital Atelier card proportions (65% visual area / 35% content area) in `LookCard`, `SpotlightHeroCard`, and `EditorialCommerceItemCard` remain intact.
5. **Installed AI Model**: Local model `qwen3-vl:4b-instruct` remains untouched; no model pulling or switching was performed.
6. **Code Isolation**: Zero production code was modified during this audit.

---

## 5. End-to-End Discovery Implementation Roadmap

The target implementation builds a **thin, complete, verifiable end-to-end path** across:
$$\text{Permitted Data Source} \longrightarrow \text{Raw Records} \longrightarrow \text{Normalized Products} \longrightarrow \text{Discovery Intelligence} \longrightarrow \text{Candidates} \longrightarrow \text{Ranking} \longrightarrow \text{Explanations} \longrightarrow \text{Flutter UI} \longrightarrow \text{Feedback Loop}$$

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               FANSIVIBE TARGET DISCOVERY FLOW                           │
└────────────────────────────────────────────────────────────────────────────────────────┘
 [ Permitted Source ] (Offline Fixtures / Live Source via Protocol F)
         │
         ▼
 [ Raw Source Records ] (collection_runs, raw_source_records, payload_hash)
         │
         ▼
 [ Normalization & Identity ] (normalize_product, resolve_identity, products, product_source_map)
         │
         ├───► [ Observation History ] (product_observations)
         │             │
         │             ▼
         │      [ Trend Intelligence ] (D6 TrendCandidate, Growth & Velocity, FFO Validation)
         │             │
         ▼             ▼
 [ Shared Discovery Intelligence Layer ] (Candidate Generation, Hard Filters, Diversity)
         ▲
         │ (User Style DNA, Wardrobe Items, Feedback, Wear History)
         │
 [ For You Personalization & Complete Looks ] (Affinity Scoring, Wardrobe Complementarity)
         │
         ▼
 [ Grounded Explanation Engine ] (Audited Reasons: Palette, Fit, Silhouette, Wardrobe Match)
         │
         ▼
 [ Flutter Digital Atelier Client ] (DiscoverScreen, Trending Tab, For You Tab, 65/35 Cards)
         │
         ▼
 [ Interaction Telemetry & Feedback ] (Click, Save, Outbound Shop Tap → Learning Signals)
```

### Phase 1: Local Discovery Foundation & Catalog Ingestion (Offline-First)
- **Scope**:
  - Ingest bundled offline fashion product fixtures into PostgreSQL `products`, `product_source_map`, and `product_observations`.
  - Create a deterministic test catalog seeder (`backend/app/infrastructure/external/fashion_catalog_seed.py`) with 50 realistic Indian and global fashion items across Tops, Bottoms, Outerwear, Footwear, Accessories with valid GTINs, attributes, and INR prices.
  - Implement a CLI command: `python -m app.application.collection --source fashion_seed`.
- **Files**:
  - `backend/app/infrastructure/external/fashion_catalog_seed.py`
  - `backend/app/application/collection.py` (register seed source)
- **Prerequisites**: Existing Alembic head `0029` (tables already exist).
- **Acceptance Criteria**:
  - `products`, `product_source_map`, and `product_observations` tables have $\ge 50$ normalized rows.
  - Re-running the seeder is 100% idempotent (0 duplicate rows).
- **Required Tests**: Dedicated unit and integration tests verifying seed collection, deduplication, and observation recording.
- **Credentials**: None ($0, 100% offline).
- **Effort**: 1–2 days.
- **Risk**: Low. Stop condition: any schema migration attempt.

### Phase 2: Shared Discovery Intelligence & Candidate Generation
- **Scope**:
  - Implement `DiscoveryRepositorySQL` extending `app/domain/ports/repositories.py` to query `products` by category, brand, and attributes with pagination.
  - Build `GenerateDiscoveryCandidates` use case (`backend/app/application/discovery_candidates.py`): retrieves candidate products, applies hard filters (in-stock, price bounds, category exclusion).
  - Create shared scoring and ranking interface connecting user context to product candidates.
- **Files**:
  - `backend/app/domain/ports/repositories.py`
  - `backend/app/infrastructure/db/repositories.py`
  - `backend/app/application/discovery_candidates.py`
- **Prerequisites**: Phase 1 populated database.
- **Acceptance Criteria**:
  - Querying candidates by category returns valid `Product` domain entities.
  - Hard filters reject out-of-stock or invalid items deterministically.
- **Required Tests**: Unit tests covering candidate queries, filter boundaries, and empty results.
- **Credentials**: None.
- **Effort**: 2 days.
- **Risk**: Low.

### Phase 3: For You Personalization & Complete Looks Matching
- **Scope**:
  - Implement personalized product affinity scoring in `backend/app/domain/services/personalization.py`:
    - Style DNA affinity: matches product `attributes.style` with `user_state.style_profile.styleType`.
    - Wardrobe complementarity: checks whether a candidate product matches categories and colors of owned `wardrobe_items` using FFO pairing rules (`pairs_with`).
    - Feedback term: integrates user likes/dislikes from `feedback_events` (Phase 2 Step 1 precedent).
  - Implement Complete Looks matching: given a candidate top, retrieves complementary bottom and footwear from `products` or user wardrobe.
  - Create application use case `GetPersonalizedDiscoveryFeed`.
- **Files**:
  - `backend/app/domain/services/personalization.py`
  - `backend/app/application/discover_personalization.py`
- **Prerequisites**: Phase 2 candidate generation, existing `WardrobeItemRepositorySQL`.
- **Acceptance Criteria**:
  - Cold-start user receives catalog-ranked products with `personalized=false`.
  - User with wardrobe items receives products that complement their owned items with `personalized=true` and explicit wardrobe match IDs.
- **Required Tests**: Cold-start tests, wardrobe-complementarity tests, feedback-weight tests.
- **Credentials**: None.
- **Effort**: 3 days.
- **Risk**: Medium. Stop condition: ungrounded score fabrication.

### Phase 4: Grounded Explanation Engine & Unified API Endpoints
- **Scope**:
  - Implement `generate_discovery_explanation()`: generates audited, truthful explanation strings grounded in computed sub-scores (e.g. "Pairs with your Navy Chinos", "Matches your Minimalist preference", "Trending in Outerwear this week").
  - Upgrade `GET /v1/looks/for-you` (or expose `GET /v1/discovery/for-you`) to return typed `DiscoveryProductCard` schemas including price, currency, brand, image URL, match score, reasons, and wardrobe links.
  - Upgrade `GET /v1/trending` to connect to D6/D7 trend engine candidate output over `product_observations` with matched products.
- **Files**:
  - `backend/app/domain/services/discovery_explanations.py`
  - `backend/app/api/routers/looks.py` (or new `backend/app/api/routers/discovery.py`)
  - `backend/app/api/schemas/discovery.py`
- **Prerequisites**: Phase 3 personalization engine.
- **Acceptance Criteria**:
  - API response matches OpenAPI schema exactly.
  - Every reason string has a corresponding non-zero score term in the audit payload.
  - Empty reasons serialize cleanly without null errors.
- **Required Tests**: API integration tests covering 200, 401, 404, 422, explanation ground truth tests.
- **Credentials**: None.
- **Effort**: 2 days.
- **Risk**: Low.

### Phase 5: Flutter Digital Atelier Client Integration
- **Scope**:
  - Update `DiscoverClient` and `DiscoverRepository` in Flutter to consume the enriched discovery endpoints.
  - Bind `DiscoverScreen` tabs to live backend responses:
    - `Trending` tab displays real trends and matched products from `GET /v1/trending` or `GET /v1/trends/analysis`.
    - `For You` tab displays real personalized products from `GET /v1/looks/for-you` via `EstablishedUserForYouFeed`.
  - Replace hardcoded mock lists in `existing_user_for_you_widgets.dart` with backend data models.
  - Preserve 65% image / 35% content card proportions, Atelier rail, and Digital Atelier styling.
  - Maintain honest loading, error retry, and empty states.
- **Files**:
  - `newproject/flutter_application_1/lib/features/discover/data/discover_client.dart`
  - `newproject/flutter_application_1/lib/features/discover/data/discover_repository.dart`
  - `newproject/flutter_application_1/lib/features/discover/data/discover_models.dart`
  - `newproject/flutter_application_1/lib/features/discover/presentation/discover_screen.dart`
  - `newproject/flutter_application_1/lib/features/discover/presentation/widgets/existing_user_for_you_widgets.dart`
- **Prerequisites**: Phase 4 backend endpoints verified.
- **Acceptance Criteria**:
  - Launching Discover screen displays backend-loaded products with correct prices, titles, images, and match scores.
  - Switching between Trending and For You tabs loads respective backend data without layout overflow or test regression.
  - Card proportions strictly conform to 65% image / 35% content.
- **Required Tests**: Widget tests in `newproject/flutter_application_1/test/discover_screen_test.dart` and `test/for_you_test.dart`.
- **Credentials**: None.
- **Effort**: 3 days.
- **Risk**: Medium. Stop condition: UI redesign or breaking existing widget test baseline (1,340 passing tests).

### Phase 6: Interaction Telemetry & Discovery Feedback Loop
- **Scope**:
  - Add backend endpoint `POST /v1/discovery/events`: records `product_clicked`, `product_saved`, `look_expanded`, `affiliate_tapped`.
  - Wire Flutter `DiscoverScreen` and `LookCard` taps to fire-and-forget telemetry.
  - Connect product saves to `SavedLooks` (TRX-3) and `learning_signals` (`look_saved`).
  - Feed interaction history back into `personalization.py` scoring weights for subsequent sessions.
- **Files**:
  - `backend/app/api/routers/discovery.py`
  - `backend/app/application/discovery_events.py`
  - `newproject/flutter_application_1/lib/features/discover/presentation/widgets/discover_editorial_widgets.dart`
- **Prerequisites**: Phase 5 client integration.
- **Acceptance Criteria**:
  - Tapping "Save" or "Shop" emits an authenticated event recorded in PostgreSQL.
  - User's subsequent feed reflects positive bias toward saved brands/categories.
- **Required Tests**: Event ingestion tests, feedback adaptation regression tests.
- **Credentials**: None.
- **Effort**: 2 days.
- **Risk**: Low.

### Phase 7: Live External Provider Integration (Protocol F Gated)
- **Scope**:
  - Execute Protocol F for approved live providers (e.g. YouTube Data API v3, Flipkart Affiliate, Rainforest API, GDELT 24h rolling).
  - Implement authenticated live source adapter following `SourceAdapter` protocol.
  - Configure background collection worker (e.g. daily cron/task).
  - Validate provider data ingestion into `raw_source_records` and `products`.
- **Prerequisites**: Phases 1–6 complete; official credentials obtained per Protocol F.
- **Credentials**: Provider-specific (YouTube GCP API key, Affiliate tokens).
- **Effort**: 3–5 days per provider.
- **Risk**: High (rate limits, upstream changes). Fail-closed required.

---

## 6. API-Key Request Protocol Compliance

When initiating Phase 7 or connecting live third-party providers, the following protocol must be strictly observed:
1. **Stop Before Calling**: Never make outbound authenticated calls or write hardcoded keys into code or tests.
2. **Provider Identification**: Identify the exact provider, API name, and documentation link.
3. **Purpose Justification**: State the specific business requirement and functionality enabled.
4. **Official Setup Link**: Provide verified official registration URL.
5. **Cost & Quota Transparency**: Detail pricing tiers, rate limits, and attribution requirements.
6. **Environment Variable Specification**: State the exact environment variable name (e.g. `FANSIVIBE_YOUTUBE_API_KEY`).
7. **Zero Secrets in Chat**: The user must configure secrets in `.env` or local environment, never paste in conversation.
8. **Confirmation Gate**: Wait for explicit user confirmation that the credential is set.
9. **Non-Destructive Connectivity Smoke Test**: Execute a bounded, single-call connectivity test (max 1 request, timeout 10s) before enabling full ingestion.

---

## 7. Recommended Next Implementation Task

### Recommended Task: TASK DISCOVERY-02 — Local Fashion Product Foundation and Discovery Seeding

**Objective**:  
Build the local, credential-free Discovery foundation by creating a deterministic, high-quality fashion catalog seeder (`fashion_catalog_seed.py`) with 50 realistic Indian and global garments across Tops, Bottoms, Outerwear, Footwear, and Accessories, ingesting them through the existing `CollectSource` and `normalize_product` pipeline into PostgreSQL `products`, `product_source_map`, and `product_observations`.

**Why this is the highest priority**:
1. It unblocks all downstream intelligence, ranking, and UI presentation without requiring external credentials, API keys, or paid subscriptions.
2. It populates the existing, tested database tables (`products`, `product_observations`) that currently hold 0 rows.
3. It creates the concrete foundation for the thin end-to-end path while preserving all frozen boundaries and existing test baselines.
