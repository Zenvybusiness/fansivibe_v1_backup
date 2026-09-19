# Fansivibe Real Trending Architecture and Source Decision

**Document Status**: ARCHITECTURAL AUDIT & DECISION SPECIFICATION  
**Milestone**: M13 P2  
**Implementation Status**: NOT IMPLEMENTED  
**Authoritative Finding**: Trending source: NOT AVAILABLE  

---

## 1. Executive Summary

This architecture decision document establishes the authoritative foundation for a future, real Trending capability in Fansivibe. It resolves the architectural gap identified in the Discover milestone audits: while Fansivibe successfully serves curated knowledge in **Explore** (`GET /v1/looks`) and owner-scoped personalization in **For You** (`GET /v1/looks/for-you`), and persisted personal garments in **Clothes** (`GET /v1/wardrobe/items`), there is currently **no legitimate real data source** for Trending in the Fansivibe platform.

### Authoritative Finding
```
Trending source: NOT AVAILABLE
```

Fansivibe operates under strict architectural and safety principles:
1. **No Fake Data / No Hallucinated Popularity**: Fabricated trend flags (`isTrending`), simulated popularity scores, and ungrounded mock catalogs are strictly banned in production.
2. **Fail-Closed Honesty**: When a data source does not exist, the platform must truthfully declare unavailability rather than silently falling back to mock fixtures or static lists posed as "popular".
3. **Data Privacy & Owner Isolation**: User wardrobes, private photos, wear logs, and personal calendar events are private assets (OW-1 tenant boundary). They cannot be casually exposed as public trends.

This document audits the entire Fansivibe repository, provides a semantic definition of Trending for fashion intelligence, evaluates the feasibility of seven candidate entity types, analyzes two architectural models (External Trend-Source Model vs. Fansivibe Behavioral Aggregation Model), drafts the prospective `GET /v1/trending` backend contract and database schema, specifies the Flutter fail-closed UI architecture, defines security and privacy boundaries, catalogs all pending product decisions, and establishes the blockers that must be cleared before implementation can safely begin.

---

## 2. Current-State Audit

A comprehensive inspection of the Fansivibe repository across backend, database, AI infrastructure, and Flutter client was conducted.

### 2.1 Discover Architecture
- **Presentation**: `DiscoverScreen` (`lib/features/discover/presentation/discover_screen.dart`) is a `StatefulWidget` presenting a horizontal tab selector (`_DiscoverTab.explore`, `_DiscoverTab.forYou`, `_DiscoverTab.clothes`). Each tab maintains an isolated, screen-local state bucket (`_items`, `_forYouItems`, `_clothesItems`). Tab state is ephemeral and dies with screen disposal to prevent cross-session leakage.
- **Backend Communication**: Delegated to `DiscoverRepositoryImpl` and `DiscoverClient`. It consumes `GET /v1/looks` (cursor-paginated catalog) and `GET /v1/looks/for-you` (boosted catalog).
- **Mock Isolation**: Dead mock lists (`DiscoverLookData.forYouMock`, `DiscoverLookData.trendingMock`) remain compiled in `discover_mock_data.dart` for legacy tests, but are completely disconnected from the active UI.

### 2.2 For You Architecture
- **Backend Implementation**: `GetForYouFeed` (`backend/app/application/discover.py`, registered at `GET /v1/looks/for-you`).
- **Signal Grounding**: Operates on exactly one proven, catalog-grounded signal: the caller's saved look codes (`saved_looks.look_id`). Saved catalog items receive a +0.03 score boost (capped at 1.0) and are re-sorted deterministically.
- **Cold Start**: If the caller has no saved looks, the feed returns the catalog order with `personalized: false`. It never poses static items as "trending" or "popular".

### 2.3 Looks / Knowledge Catalog
- **Source**: `CatalogKnowledgeSource` (`backend/app/infrastructure/external/knowledge.py`) backed by in-code seed `catalog.py` (K9.1).
- **Content**: Exactly 8 items:
  - 4 Hairstyles: `textured_quiff`, `classic_pompadour`, `side_part`, `brushed_up_undercut`.
  - 4 Grooming styles: `structured_goatee`, `classic_stubble`, `full_beard`, `goatee_with_mustache`.
- **Attributes**: `scoreSeed` (0.71 to 0.94), `reasons`, `stylingTips`, `maintenance`, `bestFor`.
- **Media**: Every `image_ref` is `None` in the database and catalog seed.
- **Filters**: Rows carry no occasion, style, or fit attributes. Any request to `/v1/looks?occasion=...` returns a truthful 422 `VALIDATION_ERROR` (DEC-014 P-3).

### 2.4 Wardrobe System
- **Persistence**: `wardrobe_items` table in PostgreSQL 18.6.
- **Attributes**: `id` (UUID), `user_id`, `name`, `category_id` (FK to `wardrobe_categories`: tops, bottoms, outerwear, footwear, accessories), `color_id` (FK to `colors`: 17 rows), `material_id` (FK to `materials`: 16 rows), `is_favorite`, `image_ref`.
- **Image Provenance**: `image_ref` stores an internal provenance pointer (`{"sourceRunId": "<uuid>"}`) linking the item to the Qwen vision analysis run that detected it. No binary image, URL, or public media asset is hosted or servable.
- **Isolation**: Strictly owner-scoped (`OW-1`). Querying another user's item returns 404 (never 403).

### 2.5 User Events
- **Persistence**: `user_events` table (M8-A).
- **Attributes**: `id`, `user_id`, `title`, `event_type_id` (FK to `event_types`: 8 rows), `event_date`, `event_time`, `location`, `notes`.
- **Usage**: Serves as a private user calendar for styling context. Seeds `preferred_occasions` and outfit derivation. Strictly private.

### 2.6 Feedback System
- **Persistence**: `feedback_events` table (M11).
- **Attributes**: `id`, `user_id`, `target_look_id`, `target_saved_look_id`, `rating`, `reason`, `idempotency_key`, `occurred_at`.
- **Scope**: Append-only log of raw user reactions. No cross-user aggregation pipeline exists.

### 2.7 Saved Looks
- **Persistence**: `saved_looks` table.
- **Attributes**: `id`, `user_id`, `look_id` (catalog code nullable), `title`, `source_context` (`hairstyle`, `grooming`, `outfit`, `daily`), `snapshot` (JSONB), `idempotency_key`, `source_run_id`.
- **Scope**: Current-state user bookmarks. Deletion is physical (`DELETE /v1/looks/saved/{id}`, DEC-013). Strictly private to each user.

### 2.8 Wardrobe Wear Signals
- **Persistence**: `wardrobe_wear_events` (item-level history) and `wardrobe_wear_groups` (idempotency ledger) (DEC-011, DEC-012).
- **Scope**: Captured exclusively via "I wore this" on `WardrobeItemDetailsScreen`. Strictly private history. No cross-user aggregation.

### 2.9 Learning Signals
- **Persistence**: `learning_signals` table.
- **Seeded Codes**: 5 active codes (`look_saved`, `analysis_updated`, `outfit_selected`, `suggestion_opened`, `assistant_navigation`).
- **Usage**: Feeds `GET /v1/learning/summary` (`styleScore` formula, streak from `activity_days`, recents). Strictly private to the user.

### 2.10 Analytics
- **Implementation**: `AnalyticsService` (`lib/shared/analytics/analytics_service.dart`).
- **Nature**: An in-memory, non-blocking Dart event bus emitting 6 experiment events (`appearance_scan_started`, `appearance_scan_completed`, `recommendations_viewed`, `explanation_viewed`, `recommendation_selected`, `recommendation_saved`).
- **Network**: Dispatches events to local in-memory handlers only. No telemetry is transmitted to any analytics server, pipeline, or database.

### 2.11 Existing Recommendation Engines
- **Hairstyle / Grooming Engine**: Deterministic rules in `analysis_rules.py` matching face shape and skin tone to catalog attributes.
- **Outfit Candidate Generator**: Deterministic pairing in `outfits.py` requiring user's owned tops + bottoms, scored 0–100.
- **Today's Look Engine**: Derives daily ensemble in `today.py` from UserState + owned wardrobe + optional event.
- **Finding**: None of these engines model, compute, or output macro-level trend velocity.

### 2.12 Existing Backend Endpoints
- **Inventory**: All endpoints across auth, wardrobe, looks, today, analysis, feedback, learning, events, knowledge, and assistant are strictly user-scoped or static-catalog scoped. Zero endpoints serve trending data.

### 2.13 Existing Database Tables
- **Authoritative Database**: PostgreSQL 18.6, Alembic revision `0022`. Exactly 20 tables:
  `users`, `user_sessions`, `user_state`, `looks`, `run_types`, `signal_types`, `analysis_runs`, `saved_looks`, `learning_signals`, `feedback_events`, `activity_days`, `wardrobe_categories`, `colors`, `materials`, `wardrobe_items`, `wardrobe_wear_events`, `wardrobe_wear_groups`, `event_types`, `user_events`, `alembic_version`.
- **Finding**: Zero tables for trends, trend items, trend snapshots, or aggregate scores.

### 2.14 Scheduled / Background Jobs
- **Finding**: Zero background workers, schedulers, Celery queues, APScheduler instances, or cron definitions exist in the repository.

### 2.15 External Integrations / Providers
- **Local AI**: Local Ollama instance serving `qwen2.5vl:3b` for computer vision inference.
- **Third-Party APIs**: Zero external commercial fashion APIs, search APIs, trend providers, social media aggregators, or weather APIs are integrated or configured.

### 2.16 Image & Data Provenance
- **Images**: User-uploaded images for face and garment analysis are processed ephemerally in memory. Only metadata (`MediaRef` with SHA-256 and byte size) is persisted in `analysis_runs.input_media`. The backend does not host an image file system, S3 bucket, or CDN.

### 2.17 Existing Trend-Related Code & Banned Keys
- In `backend/app/application/discover.py` (lines 33-35) and `backend/app/api/schemas/discover.py` (lines 11-12), `isTrending` is explicitly designated as a **banned key** alongside fabricated tags to guarantee AI-0 honesty.
- In `backend/tests/test_m14_discover_api.py` and `backend/tests/test_m12_p1_for_you.py`, tests actively verify that `isTrending` is absent from all API responses.

### 2.18 System Data Classification Matrix

| Data Classification | Description in Fansivibe | Examples | Legitimate Global Trend Contributor? |
| :--- | :--- | :--- | :--- |
| **Data that exists** | Entities present in memory or runtime code | Static catalog (8 looks), vocabularies (17 colors, 16 materials, 5 categories), user records. | No. Static catalogs lack velocity; user data lacks aggregation. |
| **Data that is persisted** | Rows stored in PostgreSQL 18.6 | 20 tables, Alembic 0022. All user tables carry `user_id FK CASCADE`. | No. Every row is either system seed or user-private. |
| **Data that is user-private** | User-generated or user-identifying data | Wardrobe items, personal photos, wear logs, calendar events, saved looks, feedback ratings. | **STRICTLY NO**. Exposing private items violates privacy, OW-1 isolation, and security laws. |
| **Data legally/technically aggregatable** | Anonymized events with explicit user consent | Abstract counts of vocabulary codes (e.g. "navy blue tops"), provided $N \ge 50$ users participate. | **Technically possible in future**, but currently illegal/unsupported due to lack of consent terms and aggregation pipelines. |
| **Data that is insufficient** | Catalog or seed datasets with inadequate cardinality | 8 hairstyle/grooming looks, 0 product catalog items, 0 images. | **INSUFFICIENT**. Cannot back a real dynamic trending feed. |

---

## 3. What "Trending" Means for Fansivibe

To prevent ambiguity, "Trending" is defined semantically for the Fansivibe platform:

> **Trending** is a **macro-level, temporal velocity signal**: it quantifies entities (styles, garments, colors, silhouettes, grooming styles) that are experiencing statistically significant upward momentum in cultural adoption, search volume, or community engagement over a bounded rolling window (e.g. 7, 14, or 30 days) within a defined geographic or demographic cohort.

### Crucial Semantic Distinctions
- **Trending $\neq$ Popular**: "Popular" measures high cumulative volume over all time (e.g., a white cotton t-shirt or classic blue blazer is always popular, but rarely "trending"). Trending measures the *first derivative* (velocity / rate of change), highlighting emerging shifts.
- **Trending $\neq$ For You / Recommended**: "For You" is micro-level, personalized individual affinity based on personal Style DNA, face shape, skin tone, or owned wardrobe. Trending is macro-level, population-wide, and user-invariant within a geographic cohort.
- **Trending $\neq$ New / Fresh**: "New" measures publication or creation timestamp, irrespective of engagement. A new item with zero traction is not trending.
- **Trending $\neq$ Editorial / Curated**: "Curated" reflects the subjective aesthetic judgment of human fashion editors. Trending must be backed by quantifiable data velocity.

---

## 4. Supported Entity Types

We systematically evaluate whether each fashion entity type can legitimately appear in a Fansivibe Trending feed today:

| Entity Type | Currently Available? | Current Source | Persisted Where? | Globally Aggregatable? | Provenance | Freshness | Ranking Inputs | Blockers |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Outfits** | **NO** | User-owned generator (`POST /v1/outfits/generate`) or static assistant mock cards (`REFINED_OFFICE`). | `saved_looks.snapshot` (private user JSONB). | **NO** (Contains private wardrobe UUIDs). | Generated per request from personal wardrobe. | Ephemeral / Static. | N/A | No public outfit entity; no universal outfit schema; exposing user outfits violates privacy. |
| **Garments** | **NO** | Private `wardrobe_items` or empty `ITEM_REFERENCES` (`GET /v1/knowledge/items`). | `wardrobe_items` (user-scoped). | **NO** (Private garments). | User photo scan or manual entry. | Static user inventory. | N/A | No product catalog; no global SKU/brand normalization; no public images; strictly private. |
| **Colors** | **POTENTIALLY** (Abstract only) | `colors` table (17 system codes: black, white, navy, charcoal, beige, etc.). | `colors` table (Alembic 0005 seed). | **YES** (Abstract counts across wears/saves, if privacy-safe). | System vocabulary. | Static vocabulary. | Wear frequency velocity, save velocity, or external color trend index. | Needs aggregation pipeline, minimum user threshold ($N \ge 50$), and UI rendering format (color trend cards vs look cards). |
| **Patterns** | **NO** | Ephemeral label from Qwen garment vision adapter. | None (ephemeral result / item title). | **NO** | Vision inference string. | Static. | N/A | No pattern vocabulary table; no database index; no collection pipeline. |
| **Styles / Vibes** | **POTENTIALLY** (Abstract only) | `StyleVibe` client enum (6 options: Minimalist, Bold, Classic, Trendy, Natural, Edgy). | `user_state.style_profile` JSONB. | **YES** (Aggregate distribution shifts). | User onboarding preference. | Static / Slow drift. | Profile selection frequency. | Too coarse-grained to populate a visual look card feed alone. |
| **Hairstyles** | **POTENTIALLY** (Limited) | `catalog.HAIRSTYLE_LOOKS` (4 looks: textured quiff, classic pompadour, side part, brushed up undercut). | `looks` table (code PK). | **YES** (Internal save counts or external search velocity). | Curated knowledge v1.1. | Static (no updates since seed). | Save velocity, or external search trend volume. | Only 4 hairstyle rows exist in Fansivibe; no images (`image_ref` is null); sample size too small for internal ranking. |
| **Grooming Styles**| **POTENTIALLY** (Limited) | `catalog.GROOMING_LOOKS` (4 looks: structured goatee, classic stubble, full beard, goatee with mustache). | `looks` table (code PK). | **YES** (Internal save counts or external index). | Curated knowledge v1.1. | Static. | Save velocity, or external grooming trend volume. | Only 4 grooming rows exist; no images; cannot form a dynamic feed. |

### Verdict on Entity Feasibility
- **Visual Look / Outfit Cards**: Cannot trend using internal data today. Outfits in Fansivibe are strictly composed of private wardrobe item UUIDs, and the static catalog contains only 8 text-only looks. Visual look trending requires an **External Trend-Source** with licensed product/style imagery.
- **Abstract Style / Color Trends**: Could trend in a future milestone via internal behavioral aggregation once user volume reaches statistical significance, but cannot be rendered as look cards today.

---

## 5. Current Real Data Sources

### Real Source Audit
```
Trending source: NOT AVAILABLE
```
- **Configuration & Environment**: Inspected `backend/app/config/settings.py`. Only database connection, Ollama vision URL, and authentication secrets are defined. Zero API keys, webhooks, or endpoints for external fashion, trend, search, or social feeds exist.
- **Dependencies**: Inspected backend `pyproject.toml` and Flutter `pubspec.yaml`. No external fashion SDKs, scrapers, or social media clients exist.
- **Pipelines**: Zero data ingestion pipelines or background ETL jobs exist in the codebase.

### Theoretical External Provider Candidates
The following third-party providers are evaluated purely as **architectural candidates** for future integration. None are currently approved, contracted, or available in the repository:

| Candidate Provider | API Availability | Licensing / Terms | Freshness | Coverage (Geo / Entity) | Image Availability | Attribution Requirements | Estimated Costs / Limits | Failure Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Google Trends API** (Enterprise BigQuery) | Official via GCP BigQuery; unofficial via scrapers (pytrends). | Enterprise commercial terms via GCP. Scraping violates ToS. | Real-time to 24h. | Global + Regional. Search terms / topics only. | **ZERO**. Text keywords only. | Mandatory citation of Google Trends. | Free/cheap for scraping (brittle); high for BigQuery enterprise. | Fail closed with cached snapshot fallback. |
| **Fashion E-Commerce Aggregators** (ShopStyle / Rakuten / Lyst) | Partner / Affiliate REST APIs. | Affiliate developer license; commercial affiliate terms. | Daily catalog updates with popularity ranks. | US, UK, EU, CA. Retail garments, outfits, brands, prices. | **HIGH**. High-resolution licensed product photography. | Mandatory brand display, retailer name, and outbound link. | Revenue-share / affiliate model, or monthly API licensing fees. | Circuit-breaker to previous snapshot; fail closed on 48h stale. |
| **Trend Intelligence Platforms** (Heuritech / Trendalytics / WGSN) | Enterprise B2B REST APIs. | Proprietary enterprise contracts ($$$$). | Weekly / Monthly trend curve metrics. | Global runway, social media, e-commerce trend curves. | Runway / Social imagery (licensing varies). | Strict copyright & proprietary source attribution. | Enterprise SaaS subscription (significant annual cost). | Batch ETL; snapshot fallback. |
| **Social Media Visual Feeds** (Pinterest / Instagram / TikTok) | Restricted Graph / Partner APIs. | Heavy API gating; commercial display requires formal partnership. | Real-time engagement velocity. | Global social trends, creator outfits, hashtags. | High visual quality, but complex user rights/copyright. | Mandatory creator handle, platform logo, and deep link. | Strict rate limits; developer approval hurdles. | Fail closed; high API volatility. |

---

## 6. External Trend-Source Model (Model A)

Model A ingests pre-computed, licensed fashion trend data from a verified third-party commercial partner.

```
┌─────────────────────────┐      Daily Batch ETL       ┌────────────────────────┐
│ Verified Trend Provider │ ─────────────────────────> │ Fansivibe Backend Ingest│
│ (e.g. Fashion Affiliate)│      (03:00 UTC)           │ - Schema Normalization │
└─────────────────────────┘                            │ - Entity Deduplication │
                                                       └───────────┬────────────┘
                                                                   │
                                                                   v
                                                       ┌────────────────────────┐
                                                       │ PostgreSQL 18.6 DB     │
                                                       │ - trend_snapshots      │
                                                       │ - trend_items          │
                                                       └───────────┬────────────┘
                                                                   │
                                                                   v
                                                       ┌────────────────────────┐
                                                       │ GET /v1/trending       │
                                                       │ - Cursor Pagination    │
                                                       │ - Provenance Metadata  │
                                                       └────────────────────────┘
```

### Specifications
1. **Source**: Verified, contracted fashion API provider delivering curated looks, garment metadata, and licensed CDN image URLs.
2. **Input Entities**: Curated trend items carrying title, description, category, high-resolution image URL, trend rank, and provenance.
3. **Collection Frequency**: Automated daily batch ETL scheduled at 03:00 UTC.
4. **Time Window**: Rolling 7-day or 14-day popularity window calculated by provider.
5. **Freshness Requirement**: Snapshots must be updated at least once every 24 hours. A snapshot older than 48 hours is marked stale.
6. **Normalization**: Provider categories are mapped strictly into Fansivibe’s controlled vocabularies (`wardrobe_categories`, `colors`, `materials`). Images must be served over secure HTTPS with verified aspect ratios complying with the Fansivibe 65/35 card rule.
7. **Deduplication**: Ingested items are deduplicated across `(source_provider, external_id)` and payload content hash.
8. **Ranking & Decay**: Base rank is provided by external velocity, adjusted by an exponential decay formula:
   $$S(t) = S_{\text{external}} \cdot e^{-\lambda \cdot \Delta t}$$
   where $\Delta t$ is days since publication, and $\lambda = \frac{\ln(2)}{7}$ (7-day half-life).
9. **Minimum Confidence**: Items must meet an external confidence score $\ge 0.70$ and verified commercial availability.
10. **Provenance**: Every record must persist: `source_name`, `external_id`, `license_type`, `attribution_text`, `attribution_url`, and `ingested_at`.
11. **Stale-Source Behavior**: If the provider is unreachable or the latest snapshot is $> 48$ hours old, the API returns the last valid snapshot with `isStale: true` and `staleReason: "provider_unreachable"`. If $> 7$ days old, the endpoint returns HTTP 503 `SERVICE_UNAVAILABLE`.
12. **Cold Start**: When a new category is introduced, the provider’s baseline popularity index is served with `coldStart: true`.
13. **Abuse & Manipulation Protection**: Completely immune to internal user bot manipulation, as ranking data is generated externally. Guarded against external spam via strict ingestion schema validation and domain allow-listing for media assets.

---

## 7. Fansivibe Behavioral Aggregation Model (Model B)

Model B derives macro-trends exclusively from the anonymized, aggregated behavior of real Fansivibe users.

```
┌────────────────────────────────────────────────────────────────────────┐
│ Fansivibe User Actions (Owner-Scoped, Private)                         │
│ - POST /v1/looks/saved      -> look_saved learning signal              │
│ - POST /v1/wardrobe/wears   -> wardrobe_wear_events (color/category)   │
│ - POST /v1/feedback         -> feedback_events (positive ratings)      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    │ Anonymized Event Stream (Hourly)
                                    v
┌────────────────────────────────────────────────────────────────────────┐
│ Behavioral Aggregation Engine                                          │
│ - K-Anonymity Guard: Reject any bucket with < 50 unique users          │
│ - Anti-Sybil Cap: Max 1 vote per user per entity per 14-day window     │
│ - Account Age Filter: Exclude accounts < 72 hours old                  │
│ - Rolling 14-day Exponential Decay Calculation                         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    v
┌────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL 18.6 DB (trend_snapshots, trend_items)                      │
│ - Abstract Vocabulary Codes ONLY (looks.code, colors.code)             │
│ - ZERO User Images / ZERO Private UUIDs                                │
└────────────────────────────────────────────────────────────────────────┘
```

### Specifications
1. **Events Used**: Aggregates strictly non-sensitive, abstract system-level actions:
   - `look_saved` learning signals (`looks.code` targets only).
   - `wardrobe_wear_events` (aggregating `colors.code`, `materials.code`, and `wardrobe_categories.code` of worn garments).
   - `feedback_events` (positive rating counts on system looks).
   - Private wardrobe item names, private images, and personal calendar notes are **never** read.
2. **Aggregation Window**: Rolling 14-day sliding window.
3. **Minimum Sample Size & Anti-Sybil Rules (Crucial Safety Constraint)**:
   - **K-Anonymity Threshold**: An entity **CANNOT** appear in trending unless at least $N \ge 50$ distinct authenticated user accounts (`COUNT(DISTINCT user_id) >= 50`) interacted with it in the window.
   - **User Weight Cap**: Each distinct user can contribute at most a weight of $1.0$ per entity per window, regardless of repeat actions. A single user wearing or saving an item 100 times produces exactly $1.0$ aggregate count.
   - **Account Age Threshold**: User accounts created $< 72$ hours ago are excluded from trend aggregation to prevent ephemeral bot swarms.
4. **Decay & Velocity Ranking**:
   Velocity is calculated by comparing momentum across two consecutive 7-day sub-windows:
   $$V = \frac{Count_{t-7 \to t} - Count_{t-14 \to t-7}}{\max(Count_{t-14 \to t-7}, 10)}$$
5. **Deduplication**: Events are grouped strictly by canonical system vocabulary identifiers (e.g. `textured_quiff`, `color:navy`, `category:outerwear`).
6. **Privacy Boundaries**:
   - Zero user UUIDs or personal IDs leave the aggregation pipeline.
   - Differential privacy noise is added to counts if the user cohort is small.
   - User photos are **never** aggregated or displayed. Trending cards must reuse official system catalog imagery or vector icons.
7. **Cold Start & Insufficient Data**:
   - If the total active user base or qualifying interactions fall below the $N \ge 50$ threshold, the engine declares `insufficient_data = true`.
   - The API truthfully returns HTTP 200 with an empty list (`items: []`) and `reason: "insufficient_community_signals"`, or HTTP 503 `SOURCE_UNAVAILABLE`. It **never** invents popularity scores or fabricates mock community data.

### Comparative Tradeoff Matrix

| Evaluation Dimension | Model A: External Trend-Source | Model B: Fansivibe Behavioral Aggregation |
| :--- | :--- | :--- |
| **Visual Appeal & Imagery** | **High**: Rich, professionally licensed photography. | **Low / Abstract**: Limited to 8 static looks or color swatches. Zero user photos allowed. |
| **Cold-Start Viability** | **Immediate**: Works from Day 1 regardless of user base size. | **Blocked**: Requires thousands of active daily users before $N \ge 50$ threshold is reached. |
| **Authenticity to Fansivibe** | **Low**: Reflects broader commercial / industry trends. | **100% Authentic**: Reflects actual Fansivibe community styling choices. |
| **Licensing & Cost** | **High**: Requires third-party contract, ongoing API fees, affiliate agreements. | **Zero External Cost**: Uses internal PostgreSQL event data. |
| **Technical Complexity** | **Moderate**: Batch ETL job, error handling, rate limits. | **High**: Stream aggregation, Sybil-defense, k-anonymity pipelines, privacy compliance. |
| **Manipulation Vulnerability** | **Immune**: Internal users cannot game third-party data. | **Vulnerable**: Requires robust bot/Sybil defenses and user weight caps. |

---

## 8. Proposed Backend API Contract (DRAFT ONLY)

```http
GET /v1/trending?entity_type={entity_type}&cursor={cursor}&limit={limit}
```

### Query Parameters
- `entity_type` (string, optional): Filter by entity type. Allowed values: `look`, `color`, `style`. Default: returns all supported entities.
- `cursor` (string, optional): Base64 opaque cursor string issued by a previous page.
- `limit` (integer, optional): Items per page. Min: 1, Max: 50, Default: 20.

### Headers
- `Authorization`: `Bearer <token>` (Required. Follows standard Fansivibe auth).

---

### Response Shapes

#### 1. Success Response (HTTP 200 OK)
```json
{
  "items": [
    {
      "id": "tr_look_9842",
      "entityType": "look",
      "entityCode": "textured_quiff",
      "title": "Textured Modern Quiff",
      "description": "High-volume textured styling experiencing rapid adoption across metropolitan centers.",
      "imageUrl": "https://cdn.fansivibe.com/curated/looks/textured_quiff_v1.webp",
      "rank": 1,
      "velocityScore": 94,
      "trendDirection": "up",
      "provenance": {
        "sourceName": "FashionMetrics International",
        "attributionText": "Curated via FashionMetrics Weekly Index",
        "attributionUrl": "https://fashionmetrics.example.com/trends/9842",
        "licenseType": "commercial_licensed"
      },
      "attributes": {
        "category": "hairstyle",
        "dominantColor": "charcoal",
        "seasonalAffinity": "autumn"
      }
    },
    {
      "id": "tr_color_012",
      "entityType": "color",
      "entityCode": "navy",
      "title": "Deep Monochrome Navy",
      "description": "Monochromatic dark blue tailoring showing +38% increase in seasonal wear logs.",
      "imageUrl": null,
      "rank": 2,
      "velocityScore": 88,
      "trendDirection": "up",
      "provenance": {
        "sourceName": "Fansivibe Community Aggregation",
        "attributionText": "Aggregated from 1,240 verified community wear logs",
        "attributionUrl": null,
        "licenseType": "internal_aggregate"
      },
      "attributes": {
        "colorHex": "#1B2A4A",
        "sampleSize": 1240
      }
    }
  ],
  "nextCursor": "ODg6dHJfY29sb3JfMDEy",
  "hasMore": false,
  "generatedAt": "2026-09-18T03:00:00Z",
  "freshness": {
    "snapshotId": "f7d3a2b1-4c5e-4a6f-9b2d-1e8c7a6b5c4d",
    "snapshotAgeSeconds": 3600,
    "isStale": false,
    "staleReason": null
  },
  "sourceMetadata": {
    "modelType": "external_partner",
    "providerName": "FashionMetrics International",
    "totalEntitiesTracked": 150
  }
}
```

#### 2. Source Unavailable Response (HTTP 503 Service Unavailable)
Returned when no trend source is configured, external providers are down past tolerance, or community volume is below the statistical privacy threshold.
```json
{
  "error": {
    "code": "TRENDING_SOURCE_UNAVAILABLE",
    "message": "Trending intelligence is currently unavailable. Fansivibe only displays verified trend signals.",
    "details": {
      "reason": "no_active_provider_configured",
      "retryAfterSeconds": 3600
    }
  }
}
```

#### 3. Stale Response (HTTP 200 OK with Stale Flag)
Returned when snapshot is $> 24$ hours old but within the 7-day grace window.
```json
{
  "items": [...],
  "nextCursor": null,
  "hasMore": false,
  "generatedAt": "2026-09-15T03:00:00Z",
  "freshness": {
    "snapshotId": "a1b2c3d4-0000-1111-2222-333344445555",
    "snapshotAgeSeconds": 259200,
    "isStale": true,
    "staleReason": "provider_refresh_delayed"
  },
  "sourceMetadata": {
    "modelType": "external_partner",
    "providerName": "FashionMetrics International",
    "totalEntitiesTracked": 150
  }
}
```

#### 4. Honest Empty Response (HTTP 200 OK)
Returned when the source is operational, but zero items meet the velocity or quality threshold for the requested filter.
```json
{
  "items": [],
  "nextCursor": null,
  "hasMore": false,
  "generatedAt": "2026-09-18T03:00:00Z",
  "freshness": {
    "snapshotId": "f7d3a2b1-4c5e-4a6f-9b2d-1e8c7a6b5c4d",
    "snapshotAgeSeconds": 3600,
    "isStale": false,
    "staleReason": null
  },
  "sourceMetadata": {
    "modelType": "fansivibe_behavioral",
    "providerName": "Community Aggregation",
    "totalEntitiesTracked": 0
  }
}
```

#### 5. Validation Error (HTTP 422 Validation Error)
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid query parameters.",
    "details": {
      "fieldErrors": [
        {
          "field": "entity_type",
          "error": "unsupported entity type 'footwear'; allowed: ['look', 'color', 'style']"
        }
      ]
    }
  }
}
```

---

## 9. Proposed Database Schema (DRAFT ONLY — NO MIGRATION)

The proposed schema introduces two essential tables to support deterministic, snapshot-isolated trend serving. It deliberately avoids modifying any existing production tables or creating migrations.

```
┌────────────────────────────────────────────────────────┐
│ trend_snapshots (Table)                                │
│ ───────────────────────────────────────────────────────│
│ id (UUID, PK)                                          │
│ model_type (TEXT: 'external_partner', 'behavioral')    │
│ provider_name (TEXT)                                   │
│ window_start (TIMESTAMPTZ)                             │
│ window_end (TIMESTAMPTZ)                               │
│ generated_at (TIMESTAMPTZ)                             │
│ expires_at (TIMESTAMPTZ)                               │
│ status (TEXT: 'active', 'superseded', 'failed')        │
│ metadata (JSONB)                                       │
└──────────────────────────┬─────────────────────────────┘
                           │ 1
                           │
                           │ N
                           v
┌────────────────────────────────────────────────────────┐
│ trend_items (Table)                                    │
│ ───────────────────────────────────────────────────────│
│ id (UUID, PK)                                          │
│ snapshot_id (UUID, FK -> trend_snapshots.id CASCADE)   │
│ rank (INTEGER, NOT NULL)                               │
│ entity_type (TEXT: 'look', 'color', 'style')           │
│ entity_code (TEXT, NULLABLE)                           │
│ title (TEXT, NOT NULL)                                 │
│ description (TEXT, NOT NULL)                           │
│ image_url (TEXT, NULLABLE)                             │
│ velocity_score (INTEGER, 0-100)                        │
│ trend_direction (TEXT: 'up', 'stable', 'down')         │
│ provenance (JSONB, NOT NULL)                           │
│ attributes (JSONB, NOT NULL)                           │
│ UNIQUE (snapshot_id, rank)                             │
│ UNIQUE (snapshot_id, entity_type, entity_code)         │
└────────────────────────────────────────────────────────┘
```

### Table Justifications

#### Table 1: `trend_snapshots`
- **Purpose**: Defines an immutable, versioned calculation run. Ensures cursor pagination is deterministic: when a user pages through a feed, all pages read from the same `snapshot_id`, even if a background job generates a new snapshot concurrently.
- **Required?**: **YES**. Without snapshots, real-time recalculations cause pagination drift, duplicate items, and skipping.
- **Columns**:
  - `id`: `UUID PRIMARY KEY DEFAULT gen_random_uuid()`
  - `model_type`: `TEXT NOT NULL CHECK (model_type IN ('external_partner', 'behavioral'))`
  - `provider_name`: `TEXT NOT NULL`
  - `window_start`: `TIMESTAMPTZ NOT NULL`
  - `window_end`: `TIMESTAMPTZ NOT NULL`
  - `generated_at`: `TIMESTAMPTZ NOT NULL DEFAULT NOW()`
  - `expires_at`: `TIMESTAMPTZ NOT NULL`
  - `status`: `TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'failed'))`
  - `metadata`: `JSONB NOT NULL DEFAULT '{}'::jsonb`
- **Mutability**: Immutable after completion, except `status` updating from `'active'` to `'superseded'`.
- **Indexes**:
  - `ix_trend_snapshots_status_generated_at` on `(status, generated_at DESC)`

#### Table 2: `trend_items`
- **Purpose**: Holds individual ranked trend items for each snapshot.
- **Required?**: **YES**. Stores the normalized, denormalized presentation data served to clients.
- **Columns**:
  - `id`: `UUID PRIMARY KEY DEFAULT gen_random_uuid()`
  - `snapshot_id`: `UUID NOT NULL REFERENCES trend_snapshots(id) ON DELETE CASCADE`
  - `rank`: `INTEGER NOT NULL CHECK (rank >= 1)`
  - `entity_type`: `TEXT NOT NULL CHECK (entity_type IN ('look', 'color', 'style'))`
  - `entity_code`: `TEXT NULL` (Links to `looks.code` or `colors.code` when applicable)
  - `title`: `TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200)`
  - `description`: `TEXT NOT NULL`
  - `image_url`: `TEXT NULL` (HTTPS CDN link with verified licensing)
  - `velocity_score`: `INTEGER NOT NULL CHECK (velocity_score BETWEEN 0 AND 100)`
  - `trend_direction`: `TEXT NOT NULL CHECK (trend_direction IN ('up', 'stable', 'down'))`
  - `provenance`: `JSONB NOT NULL` (stores source name, attribution, license)
  - `attributes`: `JSONB NOT NULL DEFAULT '{}'::jsonb`
- **Mutability**: Strictly immutable.
- **Constraints & Indexes**:
  - `UNIQUE (snapshot_id, rank)`
  - `UNIQUE (snapshot_id, entity_type, entity_code)`
  - `Index ("ix_trend_items_snapshot_entity_rank", "snapshot_id", "entity_type", "rank")`

#### Unjustified Tables (Rejected)
- `trend_sources`: **REJECTED**. Unnecessary table bloat. Source configurations (API keys, endpoints) belong in environment-driven `Settings` (`pydantic_settings`), not database tables.
- `trend_scores`: **REJECTED**. Normalized intermediate math tables add complexity. Final velocity scores belong directly on `trend_items`.

---

## 10. Flutter Architecture

Trending must integrate into the existing Discover architecture cleanly without disturbing Explore, For You, or Clothes.

```
DiscoverScreen (StatefulWidget)
  │
  ├── Tab Selector: [ Explore | For You | Clothes | Trending ]
  │
  ├── State Buckets (Isolated, Screen-Local):
  │     ├── Explore:  _items, _loading, _failure, _cursor, _hasMore
  │     ├── For You:  _forYouItems, _forYouLoading, _forYouFailure, _forYouPersonalized
  │     ├── Clothes:  _clothesItems, _clothesLoading, _clothesFailed
  │     └── Trending: _trendingItems, _trendingLoading, _trendingFailure, 
  │                   _trendingUnavailableReason, _trendingStale
  │
  └── Presentation:
        ├── Loading:     SkeletonShimmerGrid
        ├── Success:     FansiMasonryGrid -> TrendingCard (65% visual / 35% content)
        ├── Unavailable: Truthful Unavailable View (No Mock Fallback!)
        ├── Stale:       TrendingCard Grid with "Updated X days ago" notice
        ├── Empty:       Truthful Empty View
        └── Error:       Error Card with Retry
```

### Component Structure
1. **Model Layer**: `TrendingFeedPage`, `TrendingItemData`, `TrendingProvenance`, `TrendingFreshness` in `lib/features/discover/data/trending_models.dart`.
2. **Client Layer**: `TrendingClient` in `lib/features/discover/data/trending_client.dart` calling `GET /v1/trending`. Parses typed responses; fails closed with typed failures; **zero mock fallback**.
3. **Repository Layer**: `TrendingRepository` interface and `TrendingRepositoryImpl` in `lib/features/discover/data/trending_repository.dart`.
4. **UI Integration**:
   - Add `_DiscoverTab.trending` to `_DiscoverTab` enum.
   - Screen-local state bucket in `_DiscoverScreenState`:
     ```dart
     bool _trendingLoading = false;
     bool _trendingLoaded = false;
     TrendingFailure? _trendingFailure;
     String? _trendingUnavailableReason;
     List<TrendingItemData> _trendingItems = [];
     String? _trendingCursor;
     bool _trendingHasMore = false;
     bool _trendingIsStale = false;
     ```
   - Lazy-load on first tab visit:
     ```dart
     if (tab == _DiscoverTab.trending && !_trendingLoaded) _refreshTrending();
     ```
   - Card Proportion Compliance: Every trending card must use `FansiHeroCard` maintaining approximately **65% visual area / 35% content area**, strictly adhering to repo design rules.

---

## 11. Failure / Empty / Unavailable Behavior

The platform enforces strict truthfulness across all failure modes:

| Scenario | Backend HTTP Status | Backend Response Code | Flutter UI State | Rendered Copy & User Guidance |
| :--- | :--- | :--- | :--- | :--- |
| **No Source Configured** | `503 Service Unavailable` | `TRENDING_SOURCE_UNAVAILABLE` | **Unavailable View** | *"Trending is currently unavailable. Fansivibe only displays verified trend signals."* (Honest state. Zero mock fallback). |
| **External API Outage** | `503 Service Unavailable` | `EXTERNAL_SERVICE_TIMEOUT` | **Unavailable View** | *"Trend data source is temporarily unreachable. Please check back later."* + Retry button. |
| **Below Privacy Threshold** ($N < 50$ users) | `200 OK` | `items: []` | **Empty View** | *"Trending needs more community activity to appear. Keep exploring and saving styles!"* |
| **Filter Yields Zero Results** | `200 OK` | `items: []` | **Empty View** | *"No trending items in this category right now."* |
| **Stale Snapshot** ($24\text{h} < \text{Age} < 7\text{d}$) | `200 OK` | `isStale: true` | **Success with Stale Notice** | Shows trending cards, with a subtle header: *"Updated 3 days ago"*. |
| **Expired Snapshot** ($\text{Age} \ge 7\text{d}$) | `503 Service Unavailable` | `TRENDING_DATA_EXPIRED` | **Unavailable View** | *"Trend data has expired and is pending refresh. Check back soon."* |
| **Network Failure** | Client Transport Error | N/A | **Error View** | *"Couldn't load trending styles. Please check your internet connection."* + Retry button. |
| **Unauthorized** | `401 Unauthorized` | `AUTHENTICATION_ERROR` | **Session Ejection** | `AuthSession.notifyUnauthorized()` routes user to login. |

---

## 12. Security and Data Integrity

1. **Authentication & Authorization**:
   - `GET /v1/trending` requires a valid Bearer JWT.
   - All trend read operations are read-only.
   - Background ingestion and snapshot creation run under an internal worker service role; no public or user endpoint can write or trigger trend snapshots.
2. **Anti-Sybil & Manipulation Defenses**:
   - **Threshold Enforcement**: A minimum of 50 unique user IDs (`COUNT(DISTINCT user_id) >= 50`) is mandatory before any behavioral signal can register.
   - **Vote Capping**: Any single user account is hard-capped at 1.0 influence weight per rolling 14-day window.
   - **Account Age Guard**: Accounts younger than 72 hours are excluded from aggregation.
   - **Self-Promotion Block**: Users cannot upvote or trend their own private wardrobe items; only canonical, system-owned vocabulary identifiers can be aggregated.
3. **Data Integrity & Auditability**:
   - Snapshots are write-once, immutable records with cryptographic content verification.
   - External URLs must be validated against a strict HTTPS domain allow-list to prevent malicious link injection.

---

## 13. Privacy Boundaries

Fansivibe processes intimate personal styling and appearance data. The trending feature must adhere to uncompromising privacy standards:

1. **Zero Private Image Exposure**: User face scans, outfit analysis photos, and garment photos are private and ephemeral. **No user photo may EVER appear in a public or trending feed** without explicit, signed commercial model releases.
2. **Zero Wardrobe Leakage**: Private item names (e.g. "Gift from Mom", "Vintage leather jacket"), purchase prices, and wardrobe item UUIDs are private. They must never be aggregated or revealed.
3. **Location & Calendar Protection**: User event locations, dates, and calendar notes are strictly isolated and never correlated into geographical trends.
4. **GDPR / CCPA Right to Erasure**:
   - When a user deletes their account (`DELETE /v1/users/me`), all their rows in `users`, `user_state`, `wardrobe_items`, `saved_looks`, `analysis_runs`, and `user_events` are immediately erased via `CASCADE`.
   - Any historical aggregate counts in past snapshots are fully anonymous k-anonymized integers that cannot be reverse-engineered to identify the user.

---

## 14. Product Decisions Required

The following fundamental product decisions require explicit stakeholder approval before any engineering implementation begins:

1. **Core Product Strategy**: Should Fansivibe Trending represent **macro fashion industry trends** (curated external provider) or **internal Fansivibe community trends** (behavioral aggregation)?
2. **Entity Scope**: Which entities should trend? Full fashion look cards only, or also standalone color trends, hairstyle trends, and grooming trends?
3. **Commercial & Licensing Budget**: Is the organization prepared to license commercial fashion trend feeds (e.g. ShopStyle, Heuritech, or Lyst) and fund CDN infrastructure for look photography?
4. **Geographic Specificity**: Should trends be global, country-specific (e.g. US vs UK vs India), or climate/metropolitan specific?
5. **Community Consent**: Should Fansivibe's Terms of Service and Privacy Policy be updated to explicitly include opt-in anonymized behavioral aggregation for community trends?
6. **Commercial Monetization**: Should trending garment cards feature affiliate outbound purchasing links, or remain purely stylistic inspiration?
7. **Snapshot Cadence & Archival**: How frequently should trend snapshots be calculated (daily vs weekly), and how long should historical snapshots be retained in the database (30 days vs 1 year)?

---

## 15. Implementation Blockers

Engineering implementation cannot proceed due to the following concrete blockers:

1. **BLOCKER 1: No Approved External Trend Provider**: No commercial API contract, credentials, licensing agreement, or SDK exists in the repository.
2. **BLOCKER 2: Insufficient Community Scale for Behavioral Model**: The active user base and interaction volume are currently below the statistically sound $N \ge 50$ unique-user minimum threshold required to prevent Sybil attacks and protect privacy.
3. **BLOCKER 3: No Public Image Hosting / CDN Infrastructure**: Fansivibe currently stores zero image binaries. Displaying visual trending look cards requires CDN hosting, storage buckets, and licensed image assets.
4. **BLOCKER 4: Unresolved Product Decisions**: The product owner decisions listed in Section 14 have not been finalized.
5. **BLOCKER 5: Database Migration Prohibited**: Adding trend tables requires Alembic migration 0023, which is prohibited until the schema and provider strategy are approved.

---

## 16. Recommended Next Engineering Phase

When product approval is granted, engineering should execute in the following sequential phases:

1. **Phase 1: Product Decision Freeze**: Project owners resolve the 7 questions in Section 14, selecting either Model A (External Provider) or Model B (Behavioral Aggregation).
2. **Phase 2: Provider Procurement / CDN Setup** (if Model A): Establish API credentials, test provider endpoints in sandbox, and configure image caching/CDN.
3. **Phase 3: Database Foundation**: Author Alembic migration 0023 introducing `trend_snapshots` and `trend_items` tables with complete indexes and cascade rules.
4. **Phase 4: Ingestion Pipeline**: Implement scheduled daily worker (FastAPI background task or standalone container) to ingest, normalize, and score trend records.
5. **Phase 5: Backend Endpoint Delivery**: Implement `GET /v1/trending` with cursor pagination, error boundaries, and fail-closed unavailable responses.
6. **Phase 6: Flutter Discover Integration**: Add fourth `Trending` tab to `DiscoverScreen`, build `TrendingClient` and `TrendingRepository`, implement `FansiHeroCard` grid with 65/35 visual ratio, and implement honest unavailable/empty UI states.

---

## Final Status & Audit Confirmation

```
IMPLEMENTATION STATUS: NOT IMPLEMENTED
```

### Pre-Implementation Checklist (What Must Be Provided Before Implementation):
1. Written product approval of either Model A (External) or Model B (Internal).
2. Approved API credentials and licensing agreement for an external trend provider (if Model A).
3. CDN and image storage infrastructure specification for trend imagery.
4. Signed Terms of Service update regarding anonymized data aggregation (if Model B).
5. Formal approval to author Alembic migration 0023.

---

### Audit Report Summary
- **Files Inspected**:
  - `CURRENT_STATE.md`
  - `DECISIONS.md`
  - `docs/ARCHITECTURE.md`
  - `docs/PRODUCT_BLUEPRINT.md`
  - `backend/app/config/settings.py`
  - `backend/app/data/catalog.py`
  - `backend/app/infrastructure/db/models.py`
  - `backend/app/infrastructure/external/knowledge.py`
  - `backend/app/application/discover.py`
  - `backend/app/api/routers/looks.py`
  - `backend/app/api/schemas/discover.py`
  - `newproject/flutter_application_1/lib/features/discover/presentation/discover_screen.dart`
  - `newproject/flutter_application_1/lib/features/discover/presentation/widgets/discover_widgets.dart`
  - `newproject/flutter_application_1/lib/features/discover/data/discover_client.dart`
  - `newproject/flutter_application_1/lib/features/discover/data/discover_mock_data.dart`
  - `newproject/flutter_application_1/lib/shared/analytics/analytics_service.dart`
- **Relevant Existing Endpoints**:
  - `GET /v1/looks` (Explore: static knowledge catalog)
  - `GET /v1/looks/for-you` (For You: saved-look boosted catalog)
  - `GET /v1/wardrobe/items` (Clothes: owner's wardrobe)
  - `GET /v1/looks/{look_id}` (Look Detail)
  - `POST /v1/looks/saved` (Save look)
- **Relevant DB Tables**:
  - `looks` (8 seeded hairstyle/grooming looks)
  - `saved_looks` (user bookmarks)
  - `wardrobe_items` (user garments)
  - `wardrobe_wear_events` (wear actions)
  - `learning_signals` (learning history)
  - `feedback_events` (ratings)
  - `colors`, `materials`, `wardrobe_categories` (vocabularies)
- **Relevant Existing Providers**:
  - `CatalogKnowledgeSource` (in-memory 8-look catalog)
  - `OllamaVisionAppearanceAdapter` / `OllamaVisionGarmentAdapter` (local Qwen 2.5-VL:3B)
- **Existing Trend-Related Code**:
  - Dead mock lists in `discover_mock_data.dart` (`trendingMock`, `isTrending`)
  - Explicitly banned key `isTrending` in `backend/app/application/discover.py` and `backend/app/api/schemas/discover.py`
- **Git Status**: Clean working tree with respect to this task; prior user modifications preserved; zero git reset or discard executed.
- **Safety Confirmation**: Zero destructive database operations, zero mock data introduced, zero migrations created, zero production code modified.
