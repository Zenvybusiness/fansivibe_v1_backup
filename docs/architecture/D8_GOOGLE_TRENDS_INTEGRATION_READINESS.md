# D8 — Google Trends Provider Assessment & Integration Readiness

**Phase**: D8 (assessment / integration-readiness only)
**Date**: 2026-10-10
**Status**: COMPLETE — ASSESSMENT ONLY. No live collection, no migration applied,
no schema change, no code change, no secrets, no `DEMAND_SIGNAL_AVAILABLE` flip,
no authoritative-DB mutation, no D9.
**Access verdict**: **OWNER ACTION REQUIRED** (Google Trends API is an
application-gated *alpha*; the real contract, auth method, quotas and storage
terms are only available to accepted testers).
**Final decision**: **PASS WITH BLOCKERS** (blocked on alpha acceptance + verified
contract + storage/display terms before any live integration).

---

## A. Existing architecture and files inspected

The Discovery data platform already provides every seam a provider needs; D8
adds design only and reuses these abstractions.

| Concern | Existing artefact | Reuse verdict |
|---|---|---|
| Adapter contract | `backend/app/domain/ports/source_adapter.py` — `SourceAdapter` protocol, `RawSourceRecord`, `SourceBatch`, typed `SourceError` (`SourceAuthError`/`SourceRateLimitError`/`SourceTransientError`/`SourcePayloadError`) | **Reused unchanged.** Search-interest records fit `RawSourceRecord` (verbatim payload + optional provider id/timestamp). |
| Collection workflow | `backend/app/application/collection.py` — `CollectSource`, bounded paging, sanitized errors, truthful counters, DB failure → `failed` | **Loop shape reused; the product-specific `_process_record` is NOT.** It calls `normalize_product()`/`upsert_product()` and is product-listing only. |
| Run + raw storage | migration `0026_discovery_foundation.py` (`collection_runs`, `raw_source_records` with verbatim JSONB + `(source, payload_hash)` unique, `products`, `product_source_map`) | **Reused** (`collection_runs`, `raw_source_records` dedup/provenance). `products`/`product_source_map` are **not** applicable to concept-level signals. |
| Observation history | migration `0027_product_observations.py`, `ProductObservation` (`product_id` FK **NOT NULL**, `price`/`currency`/`availability`) | **Not reusable** for search interest (see §E/F). |
| Trend engine | `backend/app/domain/services/trends.py` — taxonomy (`direct_demand`/`supporting`/`catalog_operational`), `DEMAND_SIGNAL_AVAILABLE = False`, `compute_trend_candidates`, `to_ffo_trend` | **Reused**; a search-interest signal must enter as its own labelled kind, never as catalog growth. |
| Trend use case | `backend/app/application/trends.py` — `AnalyzeTrends`/`TrendConfig` | Reused unchanged. |
| Read API | `backend/app/api/routers/trend_analysis.py` + `schemas/trend_analysis.py` — `GET /v1/trends/analysis` | Reused unchanged; publication stays fail-closed. |
| Ports / SQL | `backend/app/domain/ports/repositories.py` (`DiscoveryRepository`, `TrendRepository`), `backend/app/infrastructure/db/repositories.py` | Reused; a new read/write seam would be added only when implementing (§G). |
| FFO schemas | `backend/app/data/ffo/schemas/trend.schema.json`, `trend_signal.schema.json`; validator `backend/app/data/ffo/validation.py` | Reused; signal must be expressible as a `trend_signal` with `provenance.source_type="INFERRED"`. |
| Provider matrix | `docs/architecture/TRENDING_PROVIDER_ACCESS_MATRIX.md` | Corrected URL (see §B). |
| Config convention | `backend/app/config/settings.py` — environment-driven `pydantic_settings`, credentials never in code | Adapter credentials would be new env vars only (never committed). |
| State / decisions | `CURRENT_STATE.md`, `DECISIONS.md` (`DEC-023`–`DEC-026`) | Updated with the D8 entry. |

**Smallest compatible integration path**: a Google Trends adapter emits raw
payloads through the existing `SourceAdapter`/`raw_source_records` machinery,
and a **dedicated search-interest observation writer** (not the product
path) persists normalized concept-level observations into a **new table**; the
D6 engine gains a distinct search-interest signal kind. Nothing existing is
replaced or duplicated.

---

## B. Official access findings (source URLs + verification date)

Verification date for all items: **2026-10-10**.

| Fact | Finding | Source |
|---|---|---|
| Product / access | "Get early access to the Google Trends API **alpha**" — "We're now accepting applications for alpha testers." Application-gated, limited set. | https://developers.google.com/search/apis/trends |
| Announcement | "Introducing the Google Trends API (alpha)" (July 2025). | https://developers.google.com/search/blog/2025/07/trends-api |
| Coverage | Rolling window of the **last 5 years**. | https://developers.google.com/search/apis/trends |
| Aggregation | **daily, weekly, monthly, yearly** intervals. | https://developers.google.com/search/apis/trends |
| Geography | Compare across **countries and sub-regions** ("sometimes more"). | https://developers.google.com/search/apis/trends |
| Scaling | "**consistently scaled** data" — **not** the UI's 0–100 scale: enables join/compare/merge of multiple requests, comparing dozens of terms (UI allows 8), and pulling only the last period instead of the whole period each request. | https://developers.google.com/search/apis/trends |
| UI semantics (contrast) | UI normalizes per request to the time+location, scaled 0–100; low-volume terms show as "0"; duplicate/short-lived/irregular searches filtered; statistical noise present on low-interest queries. | https://support.google.com/trends/answer/4365533 |
| Time zone | UI: ≥30-day ranges use UTC (daily/weekly/monthly); ≤7-day ranges use the browser's local time zone. | https://support.google.com/trends/answer/4365533 |
| Auth method | **Not published.** No public REST reference, no auth scheme, no base URL contract until alpha acceptance. | (docs absent pre-acceptance) |
| Rate limits / quotas | **Not published.** Gated per approved project. | — |
| Storage / display terms | **Not verified.** Alpha terms govern use; commercial status and historical-storage/display rights require confirmation during application review. | — |
| Deprecated path | `https://developers.google.com/trends` (cited by the M14 matrix) now returns **HTTP 404**; the live documentation is at `.../search/apis/trends`. | verified 2026-10-10 |

**Verified vs assumed.** Verified: alpha gating, 5-year window, interval set,
geo scope, "consistently scaled" claim, UI relative-scale semantics, stale URL.
**Assumed (NOT claimed)**: any absolute search volume, any auth scheme, any
quota, any right to store/display historically. These remain unverified until
alpha acceptance.

---

## C. Access status

**OWNER ACTION REQUIRED.**

- A path exists (public alpha application), so this is not `BLOCKED`.
- It is not `VERIFIED`: no accepted credentials exist and the actual API
  contract could not be observed, so access is **not** approved. Per D8, we do
  **not** claim approval, do **not** scrape, and do **not** call the provider.

---

## D. Actual signal semantics, timestamps, geography, limitations

- **What it measures**: a sample of Google **search interest** (relative),
  anonymized and aggregated — *never* sales, purchases, revenue, or absolute
  search volume.
- **Scale**: the alpha's "consistently scaled" values are **relative and
  provider-defined**. The *exact* scale definition is not public; it must be
  captured from the accepted contract before use. The UI's 0–100 scale is a
  different scale and must never be mixed with API values.
- **Timestamps**: interval-aggregated. UI uses UTC for ≥30-day ranges and local
  time for ≤7-day ranges; the API's definitive convention must be confirmed
  from the accepted contract. A result describes a **period**, not an instant.
- **Geography**: country and sub-region scopes; different geos are **not**
  comparable without documented normalization.
- **Limitations to preserve**: sampling; statistical noise on low-interest
  terms; filtered/low-volume terms can appear as "0" or be suppressed; a
  relative spike is **not** proof that a product is selling or that a garment is
  popular among all consumers. Search interest ≠ demand fulfilment.

---

## E. Proposed provider-neutral contract (design only)

Adapter `source_id = "google_trends"` implementing the existing
`SourceAdapter` protocol; it emits **verbatim raw payloads** and typed errors.
Normalization to the record below is deterministic and separate.

**Normalized search-interest observation (concept-level):**

| Field | Meaning | Rules |
|---|---|---|
| `source` | provider id | `"google_trends"` |
| `metric` | metric name | `"search_interest"` only — never `"volume"`/`"sales"` |
| `query_kind` | input class | `"search_term"` \| `"topic"` (Google entity MID) |
| `query_key` | canonical grouping key | normalized term or topic MID; groups comparable series |
| `query_display` | verbatim provider label | provider's returned name/type |
| `geo_scope` / `geo_scope_type` | geography | `country` \| `region` \| `worldwide` |
| `aggregation_interval` | bucket size | `daily` \| `weekly` \| `monthly` \| `yearly` |
| `period_start` / `period_end` | observation period (UTC) | `period_end > period_start` |
| `value` | provider-reported value | numeric; **NULL unless present** |
| `value_scale` | scale identifier | e.g. `google_trends_alpha_consistent_v1`; required |
| `is_relative` | relative vs absolute | always `true` |
| `value_status` | availability | `present` \| `missing` \| `suppressed` \| `invalid` |
| `source_timestamp` | provider period/data time | NULL when unprovided |
| `observed_at` | collection time | DB `now()` |
| `query_config_version` | our request/query-map version | diffable when queries change |
| `payload_hash` | dedup/provenance | from the raw record |

**Rules encoded by the contract**: missing/suppressed/invalid are never `0`;
no field can be read as absolute volume; scale is mandatory; the same query
definition + geo + interval + period is the observation identity.

---

## F. Compatibility assessment with D2–D7

| Layer | Compatibility |
|---|---|
| `SourceAdapter` / `RawSourceRecord` / typed errors | **Compatible unchanged** — provider payloads and failures map 1:1. |
| `collection_runs` + `raw_source_records` (verbatim, `(source,payload_hash)` unique) | **Compatible** — reuse for provenance and duplicate-payload protection. |
| D3 `CollectSource` record path | **Not compatible as-is**: it is product-listing specific (`normalize_product` → `upsert_product`, requires `source_product_id`). Needs a parallel search-interest writer. Reusing it would force concept-level signals through product semantics. |
| `products` / `product_source_map` | **Not applicable** — a search concept is not a purchasable product listing. |
| `product_observations` | **Cannot represent search interest safely**: `product_id` is a non-null FK and the metric columns are `price`/`currency`/`availability`. Forcing a concept signal in would corrupt meaning (a query has no product and no price). |
| D6 engine | **Compatible with one additive change**: a distinct `search_interest` signal kind, kept separate from `catalog_operational` growth. Catalog growth must never be relabelled as search interest and vice versa. Search interest is *not* sales. |
| D7 API + FFO validation | **Compatible** — new evidence flows through the same fail-closed projection; publication remains gated by `DEMAND_SIGNAL_AVAILABLE` and confidence/stage rules. |
| Different scales / geos / intervals | **Must not be merged** without a documented normalization method (not designed here; required before any cross-series comparison). |

---

## G. Proposed migration (NOT applied in D8)

**Required.** The current schema cannot represent search-interest observations
without corrupting semantics, so a new additive table is the smallest justified
change.

Proposed head `0028` (down `0027`) — `search_interest_observations`:

- `id` UUID PK.
- `collection_run_id` UUID → `collection_runs` (SET NULL).
- `raw_source_record_id` UUID → `raw_source_records` (SET NULL), **unique**.
- `source`, `metric` (`'search_interest'`), `query_kind`, `query_key`,
  `query_display`.
- `geo_scope`, `geo_scope_type`.
- `aggregation_interval`.
- `period_start`, `period_end` (`period_end > period_start`).
- `value` NUMERIC NULL, `value_scale` TEXT NOT NULL, `is_relative` BOOL NOT NULL
  DEFAULT true, `value_status` CHECK.
- `source_timestamp` NULL, `observed_at` NOT NULL DEFAULT `now()`.
- `query_config_version` TEXT NOT NULL.
- `payload_hash` TEXT.
- `created_at`.
- CHECKs: `value_status='present'` ⇔ `value IS NOT NULL`; interval/geo enums;
  non-negative period bounds.
- **Unique** `(source, metric, query_kind, query_key, geo_scope,
  aggregation_interval, period_start, period_end)` — repeated collection cannot
  inflate a series.
- Indexes: `(query_key, geo_scope, period_start)`, `(source, observed_at)`.

**Rollback**: purely additive; `downgrade()` drops the table and nothing else
references it (no existing table gains a column). Safe.

**Not applied**: in D8 the authoritative DB stays at head `0026` and the test DB
at `0027`; no `0028` file is created.

---

## H. Testing and safety plan

**Tests completed in D8** (no new code, so these are existing suites re-run to
prove no regression / frozen integrity):

- D2–D7 phase suites + M14 trending/discover + `test_production_soak.py`
  (frozen-artifact hashes incl. FFO corpus digest) → **203 passed**.
- FFO benchmark / retrieval / semantic / ref-selector → **67 passed**.
- Read-only DB checks: authoritative `fansivibe` = head `0026`, no
  `product_observations`, 0 discovery rows; `fansivibe_test` = head `0027`.

**Tests planned (to implement only with the adapter, offline/synthetic):**

1. Adapter contract + configuration validation.
2. Authentication/authorization failures → `SourceAuthError`.
3. Rate limit / retry / timeout / outage → `SourceRateLimitError`
   (`retry_after_s`) / `SourceTransientError`.
4. Malformed responses and schema changes → `SourcePayloadError`.
5. Timestamp/timezone correctness (UTC period bounds; long vs short range).
6. Geographic and aggregation consistency (reject mixed geo/interval merges).
7. Duplicate payloads + idempotent collection (raw `payload_hash` unique +
   observation natural key).
8. Missing / suppressed / invalid observations never zero.
9. Relative-value guard: no absolute-volume claim; `value_scale` required.
10. Fixture isolation (synthetic fixtures flagged, never presented as real).
11. Preservation of D6/D7 insufficient-evidence + publication protections.
12. Safe logging: no credentials / request details.

All offline tests use **synthetic fixtures labelled synthetic**; no live provider
call is made until access is authorized and the owner approves the test.

---

## I. Secrets, database, frozen-file, and FFO integrity

- **Secrets**: none added, requested, logged, or committed. No credential
  literals in the working tree.
- **Database**: authoritative `fansivibe` untouched (head `0026`, no
  `product_observations`, 0 discovery rows); only `fansivibe_test` was used by
  the re-run tests (head `0027`). No migration applied.
- **Frozen files / FFO corpus**: unchanged; `test_production_soak.py`
  frozen-artifact hashes (including the FFO corpus digest) pass.
- **Publication switch**: `DEMAND_SIGNAL_AVAILABLE` remains `False`;
  `publishedCandidates` remains empty by design.

---

## J. Exact owner actions required before live integration

1. **Apply** for the Google Trends API alpha at
   https://developers.google.com/search/apis/trends (use-case + feedback
   commitment), or confirm whether acceptance already exists.
2. After acceptance, **capture the real contract**: auth scheme, base URL,
   request/response schema, quotas, rate limits, error semantics, versioning,
   and the exact value-scale definition. Store it internally (no secrets in the
   repo).
3. Confirm **in writing** whether **historical storage** and **display to app
   users** are permitted under the alpha terms (this gates all persistence).
4. Provide credentials via **environment/secret manager only**.
5. Only then implement (new phase): the adapter, the `0028` migration + ORM +
   repository seam, the search-interest observation writer, the D6 signal-kind
   addition, and the offline test suite above.
6. Separately, **re-review D6/D7 publication rules against real observations**
   before flipping `DEMAND_SIGNAL_AVAILABLE` — search interest is evidence of
   interest, never proof of sales.

Until steps 1–3 are satisfied: no live collection, no schema change, no
publication.

---

## K. Final decision

**PASS WITH BLOCKERS.**

The assessment is complete and the minimal compatible integration design is
ready and consistent with D2–D7. Live integration is blocked on
(i) alpha acceptance, (ii) the verified API contract, and (iii) confirmed
storage/display terms. No code, migration, secret, or database change was made.
D9 is not started.
