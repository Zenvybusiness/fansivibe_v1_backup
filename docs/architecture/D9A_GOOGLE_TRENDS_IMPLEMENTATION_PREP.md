# D9A — Google Trends Integration Preparation (Access Pending)

**Phase**: D9A (preparation report only)
**Date**: 2026-10-10
**Status**: PREPARATION COMPLETE — no network calls, no scraping, no invented
endpoints/schemas, no credentials, no migrations, no production-code change, no
`DEMAND_SIGNAL_AVAILABLE` flip, no frozen/FFO/benchmark change, no DB change.
**Inputs read**: `docs/architecture/D8_GOOGLE_TRENDS_INTEGRATION_READINESS.md`,
`docs/architecture/TRENDING_PROVIDER_ACCESS_MATRIX.md`, and the D2–D7 source
adapter / collection / observation / trend-analysis / FFO-validation contracts.

**Key planning insight**: most of the work is **contract-independent** and can be
built and tested offline now against a synthetic fake adapter. Only the concrete
HTTP adapter and authentication are blocked on Google's alpha contract and terms.

---

## 1. Implementation checklist

Legend: **[NOW]** buildable offline today · **[GATED]** blocked on the verified
Google contract / terms.

### 1.1 Configuration — `app/config/settings.py`
- [NOW] Add `google_trends_enabled: bool = False` (default off; nothing runs
  unless explicitly enabled).
- [GATED] Credential field shape (see §3.1): token / API key / service-account
  path — depends on the auth mechanism. Never committed; env/secret-manager only.
- [NOW] Query-set + geo + interval + window configuration keys (term/topic list,
  geo scope, aggregation interval) — these are our inputs, independent of the
  transport contract.

### 1.2 Adapter — `app/infrastructure/external/google_trends_source.py` [GATED]
- Implements `SourceAdapter`, `source_id="google_trends"`.
- `fetch_batch(continuation, limit) -> SourceBatch[RawSourceRecord]`; verbatim
  payload only.
- Typed-error mapping: 401/403 → `SourceAuthError`; 429 →
  `SourceRateLimitError(retry_after_s=...)`; timeout/5xx →
  `SourceTransientError`; structurally-invalid payload → `SourcePayloadError`.
- `source_record_id` from any provider identity; `source_timestamp` from the
  observation period.
- Bounded paging with an opaque continuation cursor.
- Blocked items: base URL, method, auth header/param, request schema, response
  schema, pagination model, provider error codes, quota behavior, value scale.

### 1.3 Normalization — `app/domain/services/search_interest.py` (new, pure)
- Mirror the `normalize_product` pattern: `normalize_search_interest(raw) ->
  SearchInterestResult` with `ok` / `errors` / `missing` / `status` / `observation`.
- Validate: `metric`; non-empty `query_kind`/`query_key`; `geo_scope` +
  `geo_scope_type`; `aggregation_interval` enum; tz-aware UTC
  `period_start < period_end`; finite numeric `value`; mandatory `value_scale`;
  `value_status='present'` ⇔ `value is not None`; missing/suppressed never zeroed.
- Deterministic, no clock, no network.
- [GATED] field-name/semantics mapping from the provider; [NOW] the contract and
  its validation rules.

### 1.4 Collection workflow — `app/application/search_interest_collection.py` (new)
- Mirror `CollectSource`: bounded loop, truthful counters
  (fetched/inserted/skipped/failed), sanitized fixed error strings, DB failure →
  run `failed`, per-record failure → run `completed`.
- Reuse `start_run` / `insert_raw_if_absent` / `mark_raw` / `finish_run`.
- [NOW] Works against a fake adapter; [GATED] real adapter wiring.

### 1.5 Persistence seam
- [NOW] New port `SearchInterestRepository` (recommended) rather than
  overloading `DiscoveryRepository.upsert_product` — keeps the product vs
  concept seams separate. Methods: `insert_observation(...)` (idempotent on the
  natural key + unique raw id), `observations_in_window(...)`.
- [NOW] ORM `SearchInterestObservation` + `SearchInterestRepositorySQL`.

### 1.6 Migration `0028_search_interest_observations.py` [NOW, not applied]
- Additive table per D8 §G; `down_revision="0027"`.
- Rollback: `downgrade()` drops only the table.
- **Not created in D9A**; the file itself is written only in the implementation
  phase (D9B), and applied only on the disposable test DB.

### 1.7 D6 engine — `app/domain/services/trends.py`
- [NOW] Add an additive `SEARCH_INTEREST` signal kind + a
  `SearchInterestEvidence` input dataclass alongside `ObservationEvidence`.
- [NOW] Keep `catalog_operational` growth and search-interest strictly separate;
  never relabel one as the other. Search interest is **not** sales.
- [NOW] Keep `DEMAND_SIGNAL_AVAILABLE=False`; search-interest evidence alone must
  not make a candidate publishable.
- [GATED] Whether search interest is sufficient to publish, and under what
  normalization, after real-observation review.

### 1.8 D7 API — `app/api/routers/trend_analysis.py` + `schemas/trend_analysis.py`
- [NOW] The `evidenceType` field already exists (top-level and per-candidate);
  add passthrough for a search-interest evidence type when present.
- [NOW] Preserve fail-closed FFO validation (`app/data/ffo/validation.py`)
  unchanged; `publishedCandidates` stays empty while demand is unavailable.
- No new endpoint; M14 and Flutter untouched.

### 1.9 Registry / CLI — `app/application/collection.py`
- [NOW] Keep `google_trends` **absent** from `_source_registry()` → refused
  (exit 2) until authorized.
- [GATED] Add the adapter to the registry only when enabled **and** credentials
  are configured; publication stays gated regardless.

---

## 2. Dependency map

```
                   [BLOCKED: Google alpha contract + storage/display terms]
                                   │
        ┌──────────────────────────┼───────────────────────────┐
        ▼                          ▼                           ▼
  auth mechanism            endpoint + request          response schema /
  (config fields)           params (term/topic,         value scale / error
        │                   geo, interval, window)      codes / pagination
        └──────────────┬───────────┴───────────────┬─────────────┘
                       ▼                            ▼
              concrete adapter  ◄──────────  parser + typed-error mapping
                       │
                       ▼
                raw_source_records  ──(existing D2/D3, reused)──► dedup
                       │
                       ▼
        ┌───────────────────────────────────────────────────────┐
        │  [NOW] CAN BE BUILT + TESTED WITHOUT THE CONTRACT      │
        │                                                        │
        │  query-set config ─► normalization (pure) ─► obs model │
        │                                    │                   │
        │                                    ▼                   │
        │              migration 0028 + ORM + SearchInterestRepo │
        │                                    │                   │
        │              collection workflow + CLI (fake adapter)  │
        │                                    │                   │
        │              D6 SEARCH_INTEREST kind + evidence        │
        │                                    │                   │
        │              D7 evidenceType passthrough (fail-closed) │
        └───────────────────────────────────────────────────────┘
                                   │
                                   ▼
              [GATED] enable adapter + review publication rules
                      against real observations before DEMAND flip
```

**Reuse (unchanged)**: `SourceAdapter`/`RawSourceRecord`/`SourceBatch`/typed
errors; `collection_runs`; `raw_source_records` verbatim + `(source,payload_hash)`
unique; `TrendRepository` window read; D7 router/schemas; FFO `validation.py`.
**New (concept-level)**: `search_interest.py` normalization; `SearchInterestRepository`
port + SQL; `SearchInterestObservation` ORM; migration `0028`;
`search_interest_collection.py`; D6 `SEARCH_INTEREST` kind.
**Not reused**: `products`/`product_source_map` (not applicable);
`product_observations` (semantic mismatch — see D8 §F); `CollectSource._process_record`.

---

## 3. Decisions that cannot be finalized until Google's contract/terms exist

1. **Authentication mechanism** → shape of the credential setting(s).
2. **Base URL, method, and request parameters** (term vs topic, geo codes,
   interval, time range).
3. **Response schema** (value field, scale field, period fields, geo, entity
   id/type, error objects).
4. **Pagination / continuation model**.
5. **Rate limits / quotas** and the exact 429/`retry_after` semantics.
6. **The definition and identifier of `value_scale`** ("consistently scaled" is
   not a published numeric definition).
7. **Timestamp convention**: UTC vs local, period boundary (inclusive/exclusive),
   and whether a `source_timestamp` is provided per point or only per response.
8. **Geographic code format** (ISO codes vs Google's own) and sub-region
   granularity/coverage.
9. **Storage / display rights** under the alpha terms — whether historical
   retention and end-user display are permitted at all (gates persistence).
10. **Topic vs search-term support** and the form of topic/entity identifiers.
11. **`query_key` canonicalization rules** (how a term/topic becomes a groupable
    key; how aliases/renames are handled).
12. **Suppression signalling**: whether the provider marks suppressed/missing
    points explicitly or simply omits them (affects `value_status`).

---

## 4. Offline synthetic tests (defined; to be implemented in D9B)

All tests use a **`FakeGoogleTrendsAdapter`** and synthetic fixtures that are
clearly labelled synthetic — never recorded real responses, never presented as
real evidence. Tests are network-free.

**Timestamp handling**
- tz-aware UTC `period_start`/`period_end` accepted; naive datetimes rejected.
- `period_end <= period_start` rejected.
- `source_timestamp` (provider period time) and `observed_at` (collection time)
  remain distinct; missing `source_timestamp` → NULL, never fabricated.
- Long-range vs short-range convention does not silently switch scale/semantics.

**Geography**
- Valid `geo_scope` + `geo_scope_type` accepted; unknown/malformed rejected.
- Mixed-geo comparison rejected (no merge of differing scopes without a
  documented normalization).
- Sub-region scope recorded verbatim; each series kept separate.

**Missing values**
- Missing / suppressed / invalid → `value IS NULL` with the matching
  `value_status`; **never** coerced to `0`.
- `value_status='present'` ⇔ `value is not None` (CHECK enforced).
- A provider-reported "0" relative value is preserved as a point, not treated as
  absolute zero demand.

**Duplicate observations**
- Identical repeated payload → raw dedup (`skipped`), no second observation.
- Same natural key re-observed → no duplicate row.
- A changed value in a new period → a new observation (append-only history).
- Idempotent re-run of the same collection adds nothing.

**Relative-scale semantics**
- `value_scale` mandatory; a record without it is rejected.
- No code path emits "volume"/absolute-search claims; the metric is always
  `search_interest`.
- Different `value_scale` / interval / geo values are never combined.

**D6/D7 publication safeguards**
- With `DEMAND_SIGNAL_AVAILABLE=False`, analysis still returns
  `insufficient_evidence` and `publishedCandidates` stays empty even with
  synthetic search-interest rows present.
- A search-interest-only candidate is not publishable until rules are reviewed.
- Catalog growth is never relabelled as search interest (and vice versa).
- Fixture/synthetic candidates remain `fixtureDerived` / unpublished.
- FFO projection remains fail-closed (`validation.py` unchanged; schema-invalid
  → excluded with reason).

**Collection + error safety**
- Adapter returning a batch for a different source → `SourcePayloadError`.
- Non-terminating page cursor bounded by `max_records`/`max_pages`.
- Typed-error mapping (auth/rate-limit/transient/payload).
- Sanitized run error strings contain no credentials, tokens, or raw payloads.
- DB failure → run `failed`; per-record failure → run `completed`.

---

## 5. Proposed implementation sequence

- **D9B — contract-independent build (offline, `DEMAND_SIGNAL_AVAILABLE=False`)**:
  `search_interest.py` normalization; migration `0028` + `SearchInterestObservation`
  ORM; `SearchInterestRepository` port + SQL; `search_interest_collection.py` +
  CLI wiring kept refused; D6 `SEARCH_INTEREST` kind/evidence; D7 `evidenceType`
  passthrough; the full synthetic test suite above. Migration applied only on the
  disposable test DB; `google_trends` remains out of the registry.
- **D9C — contract-bound wiring (after alpha acceptance + terms)**:
  concrete HTTP adapter, auth, config fields, contract mapping, registry enable
  behind the enabled-flag + configured credentials. Publication still off.
- **D9D — publication review**: review D6/D7 rules against real observations,
  then decide whether/when to flip `DEMAND_SIGNAL_AVAILABLE`.

No phase starts until the owner approves and the prerequisite access/terms exist.

---

## 6. Unresolved questions

- Does the alpha expose topics (entity MIDs) as well as terms, and in what form?
- Is the "consistently scaled" value bounded/absolute-ish or an unbounded index?
- Are suppressed/low-volume points marked or omitted?
- What are the storage and end-user-display rights, and any attribution
  requirement?
- Is per-point `source_timestamp` provided, and in which time zone?
- Are sub-region geos available for India (`IN`)?
- Is there a documented normalization to compare across geos/intervals, or must
  Fansivibe define and document its own (owner decision)?

---

## 7. Owner actions

1. Apply for the Google Trends API alpha (or confirm acceptance).
2. After acceptance, capture the real contract (auth, base URL, request/response
   schemas, quotas, rate limits, value scale, timestamp/geo conventions).
3. Confirm **in writing** historical-storage and user-display rights under the
   alpha terms.
4. Provide credentials via environment/secret manager only (never the repo).
5. Approve the D9B/D9C/D9D split, and approve starting D9B (offline,
   publication still disabled).

---

## 8. Changes made in D9A

**None to code or the database.** This document is the only new artefact;
`CURRENT_STATE.md` gains a short D9A entry. No migration, no ORM change, no
production code, no credentials, no network call, no `DEMAND_SIGNAL_AVAILABLE`
flip, no frozen/FFO/benchmark change. `DECISIONS.md` unchanged (nothing accepted
yet).

---

## 9. D9B implementation note (added after D9B)

D9B implemented the contract-independent foundation with two deliberate
deviations from the §5 plan, both to reduce risk and duplication:

- The collection workflow lives in `app/application/collection.py`
  (`CollectSearchInterest`), **not** a new
  `search_interest_collection.py`, so it reuses the existing run +
  verbatim-raw bookkeeping and the shared sanitized-error helper without a
  duplicate framework. There is still no CLI/registry wiring.
- The D6 `SEARCH_INTEREST` signal kind was **not** added. D9B stores
  search-interest evidence in its own table and leaves D6/D7 unchanged
  (`DEMAND_SIGNAL_AVAILABLE=False`, `publishedCandidates` empty). Wiring search
  interest into D6 is deferred to D9C/D9D, when real observations and their
  publication rules can be reviewed.

Everything else matches the plan: pure `search_interest.py` normalization,
migration `0028` + `SearchInterestObservation` ORM, `SearchInterestRepository`
port + SQL, the synthetic adapter, and the offline test suite; `0028` was
applied only on the disposable test DB. See `DEC-027` and the D9B entry in
`CURRENT_STATE.md`.
