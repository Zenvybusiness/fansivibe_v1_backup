# M14 Trending Intelligence Report

**Milestone**: M14 — Trending Intelligence (foundation)
**Date**: 2026-09-23
**Status**: PARTIALLY READY (contracts + deterministic engine + test adapter live; real providers NOT CONNECTED)

Prior audits (`docs/architecture/TRENDING_PROVIDER_VALIDATION.md`,
`docs/architecture/TRENDING_PROVIDER_ACCESS_MATRIX.md`) were reused, not
redone. No scraping infrastructure created. No migration created. Frozen
AI/FFO pipeline untouched.

---

## 1. Provider access matrix

Authoritative detail lives in
`docs/architecture/TRENDING_PROVIDER_VALIDATION.md` §3–§4 and
`docs/architecture/TRENDING_PROVIDER_ACCESS_MATRIX.md`. Summary:

| Provider | Classification |
|---|---|
| YouTube Data API v3 (`regionCode=IN`, Cat. 26) | ACCESS REQUIRED (key not configured; free 10k units/day) |
| Google Trends (BigQuery public dataset, `geo=IN`) | ACCESS REQUIRED (GCP project not configured) |
| Google Trends (Alpha API) | DEFERRED (gated Alpha, not GA) |
| Flipkart Affiliate API | PARTNERSHIP REQUIRED (affiliate onboarding + token) |
| Amazon.in PA-API 5.0 | PARTNERSHIP REQUIRED (Associate + 3 qualifying sales/180d) |
| Cuelinks (link monetization only, no feed) | DEFERRED (no product data) |
| Rainforest API (Amazon.in fallback) | DEFERRED (paid SaaS, only if PA-API blocked) |
| Pinterest Trends | NOT SUITABLE (official API region enum excludes `IN`) |
| Instagram Graph API | NOT SUITABLE (30 hashtags/7d, no macro discovery) |
| Meta Content Library | NOT SUITABLE (non-commercial research only) |
| TikTok | NOT SUITABLE (banned in India, Sec. 69A IT Act) |
| Myntra | NOT SUITABLE (closed vendor-only API) |
| Heuritech / WGSN | COMMERCIAL REVIEW REQUIRED (€35k+/yr, roadmap only) |

Image rule (verified): hot-link provider CDN URLs only; never
download/self-host (Amazon PA-API §4(n), Flipkart mirroring ban).

## 2. Providers actually integrated

None as live connections. One deterministic **test adapter** is bundled
(`load_test_adapter` in `backend/app/trending/domain.py`) with fixed
`youtube_in` + `google_trends_in` signals and one `test_commerce`
product fixture. Every real provider is marked
`NOT CONNECTED — CREDENTIAL/ACCESS REQUIRED`. No fake live status.

## 3. Providers deferred

All of §1 except the test adapter: YouTube + Google Trends BQ +
Flipkart + Amazon PA-API await credentials (§11); everything
NOT SUITABLE stays out; enterprise forecasters stay roadmap-only.

## 4. Contracts created

- `TrendSignal` — source, source_identifier, observed_term, category,
  region, observed_at, growth/volume (nullable), metadata, provenance.
- `Trend` — trend_id, canonical_name, category, attributes, region,
  velocity, confidence, freshness_hours, supporting_signals, provenance.
- `ProductCandidate` — source, source_product_id, name, brand,
  category, price/currency, image_url, availability, product_url,
  affiliate_url (all nullable = unprovided, never fabricated),
  attributes, provenance, observed_at.
- Wire DTOs: `TrendingFeed`, `TrendItemSchema`, `TrendProductSchema`
  (camelCase); Flutter mirrors: `TrendingFeed`, `TrendingItem`,
  `TrendingProduct`, typed results/failures.

## 5. Files changed

- NEW `backend/app/trending/__init__.py`
- NEW `backend/app/trending/domain.py` (contracts, normalization,
  scoring, adapters, test adapter)
- NEW `backend/app/api/schemas/trending.py`
- NEW `backend/app/api/routers/trending.py`
- EDIT `backend/app/main.py` (router registration only)
- NEW `backend/tests/test_m14_trending.py` (11 tests)
- NEW `newproject/flutter_application_1/lib/features/trending/data/trending_models.dart`
- NEW `newproject/flutter_application_1/lib/features/trending/data/trending_client.dart`
- NEW `newproject/flutter_application_1/lib/features/trending/data/trending_repository.dart`
- NEW `newproject/flutter_application_1/test/trending_client_test.dart` (8 tests)
- NEW `docs/validation/M14_TRENDING_REPORT.md` (this file)

Deliberately NOT created: `trending/sources/*`, `trending/products/*`,
`trending/services/*`, `trending/workers/*` subpackages (no real
provider to adapt yet — one `domain.py` holds the contracts until a
credential lands); no Discover UI tab (backend contract first).

## 6. Database changes

NONE. M14 operates stateless/in-memory over the test adapter.
Persistence is deferred until a real provider is connected, at which
point the specified schema (`trend_sources`, `trend_entities`,
`trend_snapshots`, `trend_items`, `trend_products` — see provider
validation doc §14) can be proposed as migration 0023 with retention
(24h refresh, ≤30d cache per YouTube/PA-API terms), indexes, and
constraints. No table was created "because the diagram shows it".

## 7. API endpoints

- `GET /v1/trending?region=IN&limit=20` → `TrendingFeed`
  (region, generatedAt, isStale, items). Auth required (401 otherwise).
- `GET /v1/trending/{trend_id}` → `TrendItemSchema` (200) / 404.
- Both read-only, no DB, fail-closed. Provider internals not exposed
  (only source-name provenance chips). Clients cannot bypass backend
  validation (auth + bounds `limit 1..50` server-side).

## 8. Flutter changes

Data layer only, mirroring the Discover client/repository pattern:
`TrendingClient` (http, session Bearer, never throws, no mock
fallback) + `TrendingRepository`/`TrendingRepositoryImpl` (verbatim
passthrough). No screen/tab added (per M14 Phase 9: no large UI before
the backend contract is validated; UI Change Safety Rule honored).
No direct provider integration in Flutter (credentials can never reach
the client — there are none to leak).

## 9. Tests added

- Backend `test_m14_trending.py` (11): equivalent/distinct
  normalization, fresh-vs-stale, multi-vs-single source, missing
  metrics stay missing, provenance, dedup without name-merge,
  single-source never ranks, API 401/shape/no-fabrication/detail/404.
- Flutter `trending_client_test.dart` (8): wire-shape parsing with
  nulls-stay-null, malformed-type failure path, feed 200/query-params/
  401/malformed-200, detail 200/404, repository passthrough.

## 10. Final test results

- Backend: **918 passed, 537 skipped, 0 failed** (baseline 907 + 11 new).
- `flutter analyze lib test`: **0 issues**.
- Flutter: **1021 passed, 0 failed** (baseline 1013 + 8 new).
- AI/FFO frozen pipeline: untouched (no files under `app/ai/` modified).
- Auth/isolation/mock-real separation: preserved (endpoints reuse
  `get_current_user_id`; test adapter isolated from prod paths).

## 11. External credentials still required

YouTube Data API v3 key; GCP project for Trends BigQuery; Flipkart
affiliate id/token; Amazon Associate tag + PA-API keys (needs 3 sales).

## 12. Commercial/legal verification still required

Affiliate program acceptances (Flipkart, Amazon.in) with attribution +
disclosure strings in UI; 24h price/stock refresh job before serving
real products; confirm BigQuery commercial ToS for the GCP project.

## 13. Remaining M14 work

1. Owner provisions credentials (§11) → real adapters behind
   `TrendSource`/`ProductSource` interfaces (fail-closed per-source).
2. Migration 0023 (only then) + daily batch worker (02:00 IST) with
   staleness flags.
3. Discover 4th tab (65/35 cards, fail-closed states) + "Style With My
   Wardrobe" bridge → existing outfit engine via its public contract
   (no duplicated generation logic; contract only in this milestone).
4. Real-device + camera validation (unchanged: NOT TESTED).

## 14. Recommended next milestone

M14 P2 (provider connection): connect YouTube v3 + Google Trends BQ
first (trend signals), then Flipkart Affiliate (products). Keep the
test adapter until live provenance is verified end-to-end.

---

## M14.1 Provider Access Check (2026-09-23)

```
M14.1 BLOCKED — CREDENTIALS REQUIRED
```

- Provider: none selected (selection requires verified credentials).
- Credential status: MISSING for all four candidates — no YouTube,
  Google/GCP, Flipkart, or Amazon keys in process env, `.env*` files,
  or `app/config` (key names checked, values never read/printed).
- API status: NOT TESTED (no credential to test with; no live calls made).
- Adapter: not implemented (per stop conditions — no fake credentials,
  no fake live-provider behavior).
- Tests: none added (M14 suite unchanged: backend 918, Flutter 1021).
- Live smoke: NOT TESTED.
- Commercial verification: PENDING for all candidates.
- Remaining limitations: M14 test adapter remains the only signal
  source; `GET /v1/trending` serves deterministic fixtures honestly.

### M14.1 Step 1 re-check — YouTube Data API v3 (2026-09-23, after owner configured credential)

```
YouTube Data API v3:
Credential present: NO (not detectable)
Valid: NOT VERIFIED
Reachable: NOT VERIFIED
Commercial/usage access: NOT VERIFIED
Region: PENDING
Live call: NOT TESTED
```

- Searched (names only, values never read/printed): process env
  (full listing), User/Machine-target env, `backend/.env` (absent),
  `backend/.env.staging` key names (no YouTube/Google keys),
  `app/config` + `app/trending` code (no key fields), recent-file sweep.
- No live call attempted: nothing to authenticate with, and probing
  without a key cannot verify the owner's configured credential.
- No code, test, migration, or UI changes made in this run.
- Exact next step: owner confirms WHERE the key was placed (env var
  name, file path, or secret manager) or re-exports it into this
  shell's environment then re-runs Step 1; only then can validity,
  reachability, and region be TESTED with a single 1-unit read-only
  `videos.list?chart=mostPopular&regionCode=IN` call.

---

```
M14 STATUS: PARTIALLY READY

REAL PROVIDERS: none connected (test adapter only)

CREDENTIALS REQUIRED: YouTube v3 key; GCP/Trends BQ; Flipkart affiliate;
  Amazon PA-API (Associate + 3 sales)

DATABASE: NONE

BACKEND: PASS (918/918 runnable, 0 failures)

FLUTTER: PASS (1021/1021, analyze 0 issues)

REGRESSION: PASS (no baseline failures; FFO/auth/isolation intact)
```
