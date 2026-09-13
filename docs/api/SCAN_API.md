# Fansivibe — API Contract: Scan System

> **STEP 6 — API CONTRACT DESIGN.** Defines the **field-level API contract for
> the scan system** — the operations that create a scan, upload/associate the
> scan media, poll its processing status, retrieve its result, retry a failed
> processing, and the deletion story — for **only the scan types the finalized
> domain model supports** (outfit, face→hairstyle, grooming). It is the focused
> companion to `API_CONTRACT_RULES.md` (§12.11 analysis catalog, §8.3 async
> run object, §13 sketches) and `API_INVENTORY.md` (§5.12 analysis, §5.15
> media) and sits beside the sibling contract `APPEARANCE_API.md`, which owns
> the appearance-intelligence surface this doc overlaps (the hairstyle and
> grooming submissions are the *same endpoints*; this doc adds the scan-
> lifecycle operations and the outfit scan that APPEARANCE_API explicitly
> scopes out).
>
> **Status: contract design only. Scanning is NOT implemented.** No code, no
> `deps.py`, no routers, no SQL, no AI providers, no object storage, no Flutter
> changes, no dependencies. The live contract (`GET /health`,
> `POST /v1/assistant/chat`) is preserved unchanged. Scan endpoints are P2 and
> stay **unmounted** until the auth seam (D-AUTH-1), the media seal (MS10.3),
> and a real analysis pipeline land (API-12).
>
> **Source of truth:** the real Fansivibe repository and the accepted docs —
> STEP 2 `ACTION_API_INVENTORY.md` (actions 16/17/21/22/23/24), STEP 3
> `FANSIVIBE_DOMAIN_MODEL_V1.md` (E6 `AnalysisRun`),
> `DOMAIN_STATE_AND_HISTORY.md` (scans are immutable history), STEP 4
> `TABLE_DEFINITIONS.md` (`analysis_runs`, `run_types`) +
> `HISTORY_AND_VERSIONING.md` (§5.7 scans) + `TRANSACTION_BOUNDARIES.md`
> (TRX-1 media, TRX-5 run completion, TRX-6 projection, TRX-8 erasure) +
> `STORAGE_INVENTORY.md` (§1.2/§1.3 scan retention) + `SECURITY_PRIVACY_DESIGN.md`
> (scan media CRITICAL, auto-expire), STEP 5 `APPLICATION_USE_CASES.md`
> (UC-24…UC-27), `BACKGROUND_JOB_ARCHITECTURE.md` (§5 job lifecycle + retry),
> `AI_INTEGRATION_ARCHITECTURE.md` (FUTURE capability interfaces, §5.1/5.2/5.3,
> AI-0), `MEDIA_UPLOAD_ARCHITECTURE.md` (M16 sealed, PR-8/TRX-1),
> `ERROR_HANDLING.md` (12-category taxonomy), STEP 6 `API_CONTRACT_RULES.md`
> (catalog §12.11, async §8.3, error §9, idempotency §11) +
> `API_INVENTORY.md` (endpoints 36–40, 47/48), and `APPEARANCE_API.md`
> (the hairstyle/grooming contracts this doc shares).

---

## 1. Purpose and scope

This document defines, for every **required scan operation** and for each
**supported scan type**, the contract attributes the STEP 6 design task asks
for:

1. **method**
2. **path**
3. **request schema**
4. **response schema**
5. **authentication requirements**
6. **validation**
7. **errors**
8. **asynchronous behavior**

(plus security considerations, side effects, and domain entities, following
the same convention as the sibling contracts `APPEARANCE_API.md` and
`PROFILE_ONBOARDING_API.md`).

The task's operation list is covered operation by operation (§5):

- **create scan** — §5.1 (outfit), §5.2 (face→hairstyle), §5.3 (grooming)
- **upload / associate media** — §5.4
- **processing status** — §5.5
- **retrieve result** — §5.5 (the same polling read, `completed`)
- **retry failed processing** — §5.6
- **delete if supported** — §5.7 (and its answer: **runs are not deletable**)

It also selects the operation set: only the scan types the finalized domain
model actually supports are defined, and the operations the domain forbids
(a retry *endpoint*, a scan *DELETE*) are explicitly **not** invented (§3.2).

**The one binding design rule of this document — a scan is an immutable
historical record, and every client-visible operation is a lifecycle read or a
new submission.** There is no "scan" resource distinct from the `AnalysisRun`
row (`DOMAIN_STATE_AND_HISTORY.md` §1, §5.7: scans are EVENT/HISTORICAL_RECORD,
append-only, never overwritten; a re-scan is always a **new** run). Creating a
scan = inserting a run; processing = the run's state machine; a result = the
run's immutable `result` snapshot; retry = a new run; deletion is not a run
operation at all (it is retention and erasure, §5.7). Every endpoint below
traces 1:1 to the accepted inventory — **no invented endpoints**.

**What it does not do:** implement the scan module (M12) or media module (M16),
write AI providers, unseal M16 (MS10.3 gates it), modify Flutter, or change the
frozen assistant DTOs. The media endpoints (`POST /v1/media/uploads`,
`POST /v1/media/uploads/{upload_id}/complete`) are **referenced** (owned by
M16) and **not re-defined**. The profile projection written by face-scan
completion is owned by `PROFILE_ONBOARDING_API.md` / `APPEARANCE_API.md` and is
**referenced, not re-defined**.

### 1.1 Grounding facts (re-verified)

- **The scan IS the analysis run.** E6 `AnalysisRun` (`TABLE_DEFINITIONS.md`
  §5): `run_type` ∈ {`outfit`, `face`, `hairstyle`, `grooming`} (FK →
  `run_types`), `status` ∈ {`pending`, `completed`, `failed`} (CHECK),
  `engine_version`, `input_media` (`MediaRef`, never bytes — PR-8), `result`
  JSONB (immutable snapshot, NULL until completed), `created_at`,
  `completed_at`. Append-only (`INSERT`/`SELECT` only, PR-5); completion is
  write-once (TRX-5, PR-6).
- **Scan types actually supported by the domain model** (`run_types` seed,
  `POSTGRESQL_SCHEMA_V1_REVIEW.md` F6; `ACTION_API_INVENTORY.md`):
  - **outfit** — `POST /v1/analysis/outfit`, UC-24, endpoint 36 (action 16).
  - **face → hairstyle** — `POST /v1/analysis/hairstyle`, UC-25/26,
    endpoint 37 (action 21); the face analysis produces appearance attributes
    **and** hairstyle recommendations in one run.
  - **grooming** — `POST /v1/analysis/grooming`, UC-27, endpoint 38 (action
    23); option-based (no image), kept on the run model for uniformity (BJ-0).
  - **`face` run_type** is a **reserved** vocabulary code with **no endpoint**
    (`POSTGRESQL_SCHEMA_V1_REVIEW` F6; `APPEARANCE_API.md` §8.3) — face
    analysis mounts on run_type `hairstyle`. Additive, forward-looking.
- **No scan endpoint is live.** All four analysis operations (36–38/39–40)
  are **P2** and **async** (`202 + run_id` → poll, API-41/42). Every analysis
  provider is **FUTURE** (`AI_INTEGRATION_ARCHITECTURE.md` §5.1/§5.2/§5.3) —
  AI-0 honesty: no capability pretends to exist.
- **Media is a reference, never bytes.** Scan evidence lives in object storage
  (`users/{user_id}/scans/{run_id}/input.{ext}`) behind a `MediaRef`
  (`input_media`); the inline `multipart/form-data` `image` part is the
  accepted transport for the analysis submissions (API-36, upload-then-insert
  TRX-1); the separate M16 signed-URL flow is **sealed** until MS10.3 (API-12).
- **Retention is the deletion story.** Raw scan media auto-expires unless the
  user saves it (`STORAGE_INVENTORY.md` §1.2 face — auto-expire after analysis
  unless saved; §1.3 outfit — e.g. 30 days unless attached to a saved look).
  This is a background retention job (`SECURITY_PRIVACY_DESIGN.md` §4.3), not
  a user-facing DELETE endpoint.
- **Retry is automatic, then a new submission.** Transient failures (timeout,
  5xx, network) get **1 automatic retry** in the in-process job runner;
  non-transient failures (no face, no clothing, invalid inputs) are **never**
  retried; a job that fails twice is `failed` permanently
  (`BACKGROUND_JOB_ARCHITECTURE.md` §5.3). A user-initiated retry is a **new
  submission** (a new run), never a mutation of the failed one.
- **Delete is not supported for runs.** `analysis_runs` is append-only
  (PR-5/PR-6); a run is removed **only** by account erasure (TRX-8). There is
  **no** `DELETE /v1/analysis/runs/{run_id}`.
- **Face scans write the current projection; outfit and grooming do not.**
  Face-scan completion applies appearance attributes to
  `user_state.style_profile` in a **separate transaction** (TRX-6, latest-wins,
  `source_run_id` provenance); outfit and grooming scans write history only
  (a style is accepted later via the saved-look surface, M7). Runs are never
  touched by acceptance (`APPEARANCE_API.md` §4.4).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `ACTION_API_INVENTORY.md` | Actions 16 (scan outfit), 21 (hairstyle), 23 (grooming), 17/22/24 (save from scan) → the future endpoints + error conditions + AUTH. |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` / `DOMAIN_STATE_AND_HISTORY.md` | E6 `AnalysisRun`; scans = EVENT/HISTORICAL_RECORD, append-only, never overwritten, re-scan = new run (§5.7). |
| `TABLE_DEFINITIONS.md` | `analysis_runs` (run_type/status/engine_version/input_media/result/created_at/completed_at), `run_types` vocab. |
| `HISTORY_AND_VERSIONING.md` | §5.7 scans: no overwrite, exact reproducibility from `input_media` + `result` + `engine_version`. |
| `TRANSACTION_BOUNDARIES.md` | TRX-1 upload-then-insert; TRX-5 write-once run completion; TRX-6 profile projection update; TRX-8 erasure. |
| `STORAGE_INVENTORY.md` / `SECURITY_PRIVACY_DESIGN.md` | §1.2/§1.3 scan retention (auto-expire unless saved); scan media CRITICAL-sensitivity, private by default. |
| `APPLICATION_USE_CASES.md` | UC-24 `AnalyzeOutfit`, UC-25 `AnalyzeAppearance`, UC-26 `GenerateHairstyleRecommendations`, UC-27 `GenerateGroomingRecommendations` (M12, P2). |
| `BACKGROUND_JOB_ARCHITECTURE.md` | Job lifecycle §5: creation (blob before row, TRX-1), status (pending→completed\|failed), **retry §5.3**, timeout, failure, result persistence. |
| `AI_INTEGRATION_ARCHITECTURE.md` | `OutfitAnalysisProvider`/`FaceAnalysisProvider`/`HairAnalysisProvider` FUTURE; 30s timeouts; 1 retry; `CapabilityResult` envelope; AI-0/AI-5/AI-6. |
| `MEDIA_UPLOAD_ARCHITECTURE.md` | M16 flow (upload auth → object storage → complete → `MediaRef`); sealed until MS10.3; PR-8; TRX-1. |
| `API_CONTRACT_RULES.md` | Catalog §12.11 (methods/paths/auth/UC/errors), §8.3 async run object, §13 sketches, §9 error contract, §11 no-idempotency for analysis. |
| `API_INVENTORY.md` | Endpoints 36–40 (§5.12), 47/48 (§5.15 media, sealed); related domain entities per endpoint. |
| `APPEARANCE_API.md` | The shared hairstyle/grooming submission contracts, `AnalysisRun` DTO (§4.3), run-type/status vocabulary — referenced and kept identical. |
| `PROFILE_ONBOARDING_API.md` / `AUTH_API.md` | P-2 `PATCH /users/me` (`sourceRunId` rules) and the profile read/write surface — referenced for the face-scan projection. |
| `ERROR_HANDLING.md` | 12-category taxonomy: VALIDATION_ERROR (422), AUTHENTICATION_ERROR (401), NOT_FOUND (404), MEDIA_FAILURE (413/422), EXTERNAL_SERVICE_FAILURE (503), PROCESSING_FAILURE (run `failed`), RATE_LIMITED (429). |

---

## 3. Operation selection (define only the required operations)

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| S-1 | **Create outfit scan** | **Required** — `POST /v1/analysis/outfit` | UC-24, endpoint 36, action 16. Outfit image → detected items, sections, scores. §5.1. |
| S-2 | **Create face → hairstyle scan** | **Required** — `POST /v1/analysis/hairstyle` | UC-25/26, endpoint 37, action 21. Face image → appearance attributes (TRX-6 projection) + hairstyle recommendations. §5.2. |
| S-3 | **Create grooming scan** | **Required** — `POST /v1/analysis/grooming` | UC-27, endpoint 38, action 23. Grooming options → recommendations; no projection change. §5.3. |
| S-4 | **Upload / associate scan media** | **Required** — inline multipart part (API-36) + M16 flow **referenced** | The scan's evidence is a `MediaRef` (PR-8); the `image` part travels inline on S-1/S-2; the separate signed-URL flow (endpoints 47/48, purpose `scan`) is owned by M16 and sealed until MS10.3. §5.4. |
| S-5 | **Processing status (poll)** | **Required** — `GET /v1/analysis/runs/{run_id}` | Endpoint 39, polling read; status derived from the row (BJ §5.2). §5.5. |
| S-6 | **Retrieve result** | **Required** — `GET /v1/analysis/runs/{run_id}` (`completed`) | The same read; completed carries the immutable `result` + `engine_version`. §5.5. |
| S-7 | **Retry failed processing** | **Pattern, no endpoint** | Automatic 1x transient retry (BJ §5.3) + client re-submission (new run). A retry *endpoint* would mutate append-only history — explicitly NOT defined. §5.6. |
| S-8 | **Delete scan** | **NOT supported for runs** — no DELETE endpoint | `analysis_runs` is append-only (PR-5/6); runs die only by erasure (TRX-8); raw scan media auto-expires unless saved (retention job). §5.7. |
| S-9 | **List scan history** | **Required (supporting)** — `GET /v1/analysis/runs` | Endpoint 40, the scan-history read (`?run_type=` filter per scan type). §5.8. |
| — | **`face` run_type endpoint** | **NOT defined now** | Reserved vocabulary code; face analysis mounts on `/v1/analysis/hairstyle` (§3.1). |
| — | **Cancel a scan** | **NOT defined** | The run machine has no cancellation; TRX-5 write-once (a pending run finishes or fails). |

### 3.1 Scan types supported by the domain model

The `run_types` vocabulary has four codes (`outfit`, `face`, `hairstyle`,
`grooming`), but **three scan types have live product features today**
(`ACTION_API_INVENTORY.md` actions 16/21/23; `FEATURE_INVENTORY.md` features
Outfit Scan, Hairstyle, Grooming):

| Scan type | `run_type` | Endpoint | Input | Produces | Projection |
| --- | --- | --- | --- | --- | --- |
| **Outfit scan** | `outfit` | `POST /v1/analysis/outfit` | outfit image | detected items, sections, scores | none (history only) |
| **Face → hairstyle scan** | `hairstyle` | `POST /v1/analysis/hairstyle` | face image (image pass) or empty body (profile-only pass over `style_profile` by `user_id`, Phase 28) | face attributes + hairstyle recommendations | writes `styleProfile` (TRX-6) |
| **Grooming scan** | `grooming` | `POST /v1/analysis/grooming` | empty JSON `{}` (profile-only pass over `style_profile` by `user_id`, Phase 28) | grooming recommendations | none unless a style is explicitly saved |

The `face` code is **reserved, forward-looking** (a dedicated face-only
analysis, e.g. an onboarding scan producing only `FaceProfile`) — it is seeded
in `run_types` but has **no endpoint today** (`APPEARANCE_API.md` §8.3). It is
additive if a real feature mounts it; the contract never invents it now.

### 3.2 Operations explicitly NOT defined (and why)

- **`POST /v1/analysis/runs/{run_id}/retry` — NOT defined.** A run is an
  immutable EVENT/HISTORICAL_RECORD (PR-5); retrying in place would overwrite
  history. Retry is the automatic 1x job retry plus a **new submission**,
  both of which already exist (§5.6). A retry endpoint is an invented API.
- **`DELETE /v1/analysis/runs/{run_id}` — NOT defined.** Same append-only
  invariant (PR-5/PR-6); a run is removed only by account erasure (TRX-8).
  Scan *media* is covered by retention (auto-expire unless saved), not by a
  user-facing delete (§5.7).
- **`POST /v1/analysis/cancel` / cancel state — NOT defined.** The run status
  machine is `pending → completed | failed` (CHECK constraint, TRX-5); there
  is no cancellation, matching `APPEARANCE_API.md` §4.3.
- **A dedicated "scan" resource family — NOT defined.** `/scans/*` does not
  exist; the scan is the `AnalysisRun` under `/analysis/*`. No invented
  parallel resource.

---

## 4. Shared semantics (apply to every operation below)

### 4.1 Base URL, headers, format

- All endpoints under `/v1` (API-1); JSON bodies `application/json;
  charset=UTF-8`; keys camelCase; timestamps ISO-8601 UTC (API-19). Image
  submissions use `multipart/form-data` with the `image` part (API-36) — binary
  is never base64'd into JSON.
- Protected endpoints send `Authorization: Bearer <token>` (API-5). Missing /
  invalid / expired / revoked → `401 AUTHENTICATION_ERROR` +
  `WWW-Authenticate: Bearer` (API-7, ERROR_HANDLING §5.2).
- **No `Idempotency-Key`** on scan submissions — **each call creates a new
  run** (`API_CONTRACT_RULES.md` §11: analysis is never idempotent). Reads,
  polls, and the M16 media steps follow their own rules (media is covered by
  its own contract).
- Every response echoes `X-Request-Id` (OBSERVABILITY §4.1).

### 4.2 The scan lifecycle and the run status machine

Image analysis is the **only async surface** in the API (sync-by-default,
API-40). Every scan **submission** returns `202 Accepted` immediately:

```json
{ "run_id": "7a2b3c…" }
```

The client polls `GET /v1/analysis/runs/{run_id}` (S-5) until
`status ∈ { completed, failed }`, then reads the result (S-6). Completion is
**write-once** (TRX-5): the guarded `UPDATE … WHERE status='pending'` flips the
run once; a completed run is immutable and never overwritten (PR-6). A `failed`
run carries the typed error in `error` and **no** `result` — the failure is
itself part of history (reproducible). Scanning is **not idempotent**: a
retried submission creates a second run, which is by design (each attempt is a
distinct historical record, §5.6).

**The task's four lifecycle states, and how they map to the wire:**

The task asks the contract to express `CREATED`, `PROCESSING`, `COMPLETED`,
`FAILED`. The finalized domain model exposes these as a **client-visible scan
lifecycle**; the wire `status` field keeps the accepted **three-value run
vocabulary** (`pending | completed | failed`) so this contract stays identical
to `APPEARANCE_API.md` §4.3 and the `analysis_runs` CHECK constraint:

| Scan lifecycle (task vocabulary) | Wire `AnalysisRun.status` | When |
| --- | --- | --- |
| **CREATED** | `pending` | the run row exists; the job is queued, not yet started |
| **PROCESSING** | `pending` | the job is in flight (status is row-derived — `BACKGROUND_JOB_ARCHITECTURE.md` §5.2; no stored in-flight flag) |
| **COMPLETED** | `completed` | `result` + `engine_version` written **once** (TRX-5); immutable |
| **FAILED** | `failed` | typed `error`; no `result`; immutable; not retried in place |

**CREATED and PROCESSING intentionally both surface as `pending`.** The domain
deliberately does not store a separate "processing" state (BJ §5.2: status is
derived from the row so restarts and multi-worker deploys stay correct; the
schema CHECK forbids a fourth value). A client that wants to show
created-vs-processing locally may infer it from time since submission, but the
wire contract does not distinguish them. `pending → completed | failed` is the
only transition (TRX-5); there is no cancellation and no re-run of an existing
run — **regenerate = a new submission** (§5.6).

### 4.3 Scan DTO (the run)

```
AnalysisRun {
  run_id*,          // UUID; the historical record's identity
  run_type*,        // "outfit" | "hairstyle" | "grooming" (the scan types; "face" reserved)
  status*,          // "pending" | "completed" | "failed"
  created_at*,      // ISO-8601 UTC
  completed_at?,    // present when completed | failed
  engine_version?,  // provenance — present when completed (PR-6)
  input_media?,     // MediaRef to the source scan image (when media attached)
  result?,          // immutable typed snapshot — present ONLY when completed
  error?            // frozen error body — present ONLY when failed
}
```

`status` transitions: `pending → completed | failed` (TRX-5). `result` shapes
are the per-scan-type typed snapshots (§5.1–5.3), mirroring the real mock data
(`outfit_scan_mock_data.dart`, `hairstyle_mock_data.dart`,
`grooming_mock_data.dart`).

### 4.4 Media association (upload / associate)

Scan evidence is a `MediaRef` (`input_media`), never the bytes (PR-8). There
are two accepted mechanisms (§5.4); both end in the run carrying a `MediaRef`:

1. **Inline multipart part (primary, per the catalog):** the scan submission
   (S-1/S-2) carries the `image` part in `multipart/form-data`; the backend
   performs **upload-then-insert** (TRX-1) — blob → object storage (M16
   adapter) → `MediaRef` written on `analysis_runs.input_media` before/with
   the run row. `API_CONTRACT_RULES.md` §12.11, `API_LAYER_ARCHITECTURE.md`
   API-36/API-37.
2. **Separate M16 flow (referenced, sealed):** `POST /v1/media/uploads`
   (purpose `scan`) → signed PUT URL → Flutter PUTs bytes → `POST
   /v1/media/uploads/{upload_id}/complete` → `MediaRef`
   (`MEDIA_UPLOAD_ARCHITECTURE.md` §3/§4, endpoints 47/48). Gated until
   MS10.3 lifts (API-12). **Referenced, not re-defined.**

Object keys are owner-scoped: `users/{user_id}/scans/{run_id}/input.{ext}`
(`MEDIA_STORAGE_DESIGN.md` §6.2/6.3). Scan blobs are **private by default** and
auto-expire unless saved (§5.7).

### 4.5 Error body (frozen, API-28)

```
{ "error": { "code": "<one of the 12>", "message": "<safe client message>", "details": {...} } }
```

`details` is allow-listed only (ER-1): field errors + allowed values (422),
`maxBytes` (413), `run_id` (own run only), `request_id` (500). **Never** the
user's scan image, run `result` content, prompts, provider/model names, or
analysis internals (C-7/C-8, ER-0/ER-2, AI-0).

### 4.6 Auth, ownership, privacy

| Requirement | Endpoints |
| --- | --- |
| **Auth** (Bearer → `user_id`) | `POST /v1/analysis/outfit`, `POST /v1/analysis/hairstyle`, `POST /v1/analysis/grooming`, `GET /v1/analysis/runs/{run_id}`, `GET /v1/analysis/runs`, and (when unsealed) the M16 media endpoints. |
| **Public** | none in this surface. |

Authorization is **owner-only (OW-1)** with **404-not-403** (API-10): every
run is scoped to the caller's `user_id`, and a `run_id` that is not yours (or
that never existed) returns `404`, never `403` and never an existence hint.
Face and outfit scan media are **CRITICAL-sensitivity** appearance data
(`SECURITY_PRIVACY_DESIGN.md` §3): HTTPS only, owner-only, never cached on
shared storage, **image bytes never logged and never echoed in responses or
errors** — only the `MediaRef` travels (MS10.3, ER-4).

---

## 5. Operation contracts

### 5.1 S-1 — Create outfit scan (`AnalyzeOutfit`, UC-24)

- **Method / path:** `POST /v1/analysis/outfit` (endpoint 36, action 16)
- **Asynchronous behavior:** **async** — `202 Accepted` + `run_id`; poll S-5
  until `completed | failed`. Each submission is a new run (never idempotent).
- **Request schema** (`multipart/form-data`):

```
image:           <file>        // required; outfit photo; the evidence (MediaRef after M16)
…typed fields…                  // optional typed context per catalog §12.11 ("image + typed fields");
                                //   exact keys finalized at implementation (open decision §8)
```

- **Response schema:** `202 Accepted` — `AsyncAccepted { run_id* }` (bare, no
  envelope). Completed run `result` (run_type `outfit`), mirroring
  `OutfitAnalysisData` (`outfit_scan_mock_data.dart`):

```
AnalysisRun.result (run_type "outfit") {
  title: string,                    // e.g. "Modern Minimalist Look"
  sections: [{ id, label, description, score?, detail? }],   // silhouette, balance, fit, …
  detectedItems: [{ name, category, color, material? }],     // clothing detected in the photo
  confidence?: { value: 0..1, scope: "outfit" }              // FUTURE; absent today (AI-0)
}
```

- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1); outfit media is private.
- **Validation:**
  - Image required; content-type/size checked pre-run → **413/422
    MEDIA_FAILURE** (`details.maxBytes`).
  - No clothing detected / poor image → **422 VALIDATION_ERROR** (UC-24
    `InvalidInputError`).
  - `run_type` produced = `outfit`.
- **Errors:** `202`; `401`; `404` (account gone); `413/422 MEDIA_FAILURE`;
  `422 VALIDATION_ERROR` (no clothing, missing image); `503
  EXTERNAL_SERVICE_FAILURE` (provider — submission); on the poll, the run may
  be `status=failed` with `error.code = PROCESSING_FAILURE` (details.run_id).
  `429 RATE_LIMITED`.
- **Security considerations:** outfit media is CRITICAL appearance data —
  bytes flow only into the pipeline, stored as `MediaRef`, never logged, never
  echoed (MS10.3, ER-4); provider/model internals never surface (C-8, AI-0);
  404-not-403 on owned ids.
- **Side effects:**
  - **History:** blob → object storage (TRX-1), then an `analysis_runs` row
    (run_type `outfit`, status `pending`); on completion writes the immutable
    `result` + `engine_version` once (TRX-5).
  - **No projection change:** outfit analysis is history only; "Generate Look"
    from the result is the saved-look surface (M7, endpoint 23, referenced).
  - **Failure:** a failed run writes no `result` and no projection change;
    orphan blobs are swept by the async cleanup job (TRX-1 §5).
- **Domain entities involved:** E6 `AnalysisRun`; `MediaRef` (input evidence);
  value objects: `OutfitAnalysisData`, `DetectedClothingItem`,
  `AnalysisSection`, Confidence (FUTURE).

---

### 5.2 S-2 — Create face → hairstyle scan (`AnalyzeAppearance` UC-25 / `GenerateHairstyleRecommendations` UC-26)

- **Method / path:** `POST /v1/analysis/hairstyle` (endpoint 37, action 21)
- **Asynchronous behavior:** **async** — `202 Accepted` + `run_id`; poll S-5.
  Each submission is a new run.
- **Request schema** (`multipart/form-data`, Phase 28: no face-profile reference — identical to `APPEARANCE_API.md`
  §5.1):

```
image:            <file>          // optional; face photo for the image pass (MediaRef after M16)
                                 // absent = profile-only pass over the authenticated user's stored style_profile (by user_id)
```

  - With an image: the run does UC-25 (face analysis → appearance attributes)
    then UC-26 (hairstyle recommendations) — one run, one result.
  - Without an image (profile-only, empty body): recommendation
    pass over the already-stored current profile (no new face attributes).
- **Response schema:** `202 Accepted` — `AsyncAccepted { run_id* }`. Completed
  run `result` (run_type `hairstyle`), mirroring `HairstyleAnalysisResult`
  (`hairstyle_mock_data.dart`):

```
AnalysisRun.result (run_type "hairstyle") {
  appearance?: {                       // UC-25 — face attributes
    faceShape?, skinTone?, bodyType?,  // analysis-derived codes
    styleType?,                        // suggested vibe (recommendation, not acceptance)
    confidence?: { value: 0..1, scope: "face" },   // FUTURE; absent today (AI-0)
    sourceRunId                        // = this run_id (provenance)
  },
  recommendations: {                   // UC-26 — hairstyle recommendations
    top: HairstyleRecommendation,      // { id, name, description, matchScore, reasons[],
    alternatives: HairstyleRecommendation[],   //   stylingTips, maintenance, bestFor }
  }
}
```

  The *current* face profile (after acceptance) is **not** this `result` — it
  is `ProfileView.styleProfile` via `GET /v1/users/me` (§4.4 of
  `APPEARANCE_API.md`). `HairstyleRecommendation` mirrors
  `hairstyle_mock_data.dart:64-102`.
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1); face media is private.
- **Validation:**
  - Profile-only pass (no image) resolves the authenticated user's stored
    `style_profile` by `user_id`; missing face data → **422
    INSUFFICIENT_USER_DATA**. Image
    content-type/size checked pre-run → **413/422 MEDIA_FAILURE**.
  - No face detected / poor image → **422 VALIDATION_ERROR** (UC-25).
  - `run_type` produced = `hairstyle` (the endpoint's run_types code); a
    dedicated `face`-only run is reserved, not mounted (§3.1).
- **Errors:** `202`; `401`; `404`; `413/422 MEDIA_FAILURE`; `422
  VALIDATION_ERROR` (no face, invalid input, missing image); `503
  EXTERNAL_SERVICE_FAILURE`; on the poll, the run may be `status=failed` with
  `error.code = PROCESSING_FAILURE` (details.run_id); `429 RATE_LIMITED`.
- **Security considerations:** face media is CRITICAL — uploaded as bytes only
  into the pipeline, stored as `MediaRef` (never the bytes in PG, PR-8), never
  logged, never echoed (MS10.3, ER-4). Analysis-derived attributes are **never
  client-authored truth** — they arrive inside the immutable run and reach the
  profile only via the guarded completion (C-16/BAR-0).
- **Side effects:**
  - **History:** blob → object storage (TRX-1), then an `analysis_runs` row
    (run_type `hairstyle`); on completion writes the immutable `result` +
    `engine_version` once (TRX-5).
  - **Projection:** the completed face analysis **applies** the attributes to
    `user_state.style_profile` (latest-wins, TRX-6) and emits an
    `analysis_updated`/`style_updated` learning signal — the run is untouched
    (`APPEARANCE_API.md` §4.4 guarantee 3). A later user override goes through
    `PATCH /v1/users/me` (`sourceRunId` required for derived fields,
    `PROFILE_ONBOARDING_API.md` §5.2).
  - **Failure:** a failed run writes no `result` and no projection change.
- **Domain entities involved:** E6 `AnalysisRun`; E1.1
  `UserState.styleProfile` (FaceProfile projection + `sourceRunId`, written by
  TRX-6); E5 `Look` (hairstyle catalog, read-only); E7 `LearningSignal`
  (`analysis_updated`); `MediaRef`; value objects: FaceProfile,
  HairstyleRecommendation, Confidence (FUTURE).

---

### 5.3 S-3 — Create grooming scan (`GenerateGroomingRecommendations`, UC-27)

- **Method / path:** `POST /v1/analysis/grooming` (endpoint 38, action 23)
- **Asynchronous behavior:** **async** — `202 Accepted` + `run_id`; poll S-5.
  Stays on the run model for uniformity (BJ-0); each submission is a new run.
  No image — no media step.
- **Request schema** (`application/json`) — identical to `APPEARANCE_API.md`
  §5.2:

```
{
  "options": {                    // required; user preference — GroomingOption vocab ids (not free text)
    "faceShape":  "oval",         // from the grooming input vocabulary
    "beardStyle": "full_beard",
    "density":    "medium",
    "color":      "dark_brown"
  }
}
```

  The options mirror the user's picks in the grooming flow
  (`grooming_mock_data.dart:16` — face shape, beard style, density, color).
- **Response schema:** `202 Accepted` — `AsyncAccepted { run_id* }`. Completed
  run `result` (run_type `grooming`), mirroring `GroomingAnalysisResult`
  (`grooming_mock_data.dart:223`):

```
AnalysisRun.result (run_type "grooming") {
  recommendations: {                   // grooming recommendation rules
    top: GroomingRecommendation,       // { id, name, description, matchScore, reasons[],
    alternatives: GroomingRecommendation[],  //   beardLength, cheekLine, eyewearFrame,
                                            //   eyewearRecommendation, stylingTips, maintenance, bestFor }
  }
}
```

- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1).
- **Validation:**
  - Every option must be a **valid `GroomingOption` vocab code** (K9.1);
    unknown/absent code → **422** with allowed values in `details`.
  - `options` object required; missing → **422**.
- **Errors:** `202`; `401`; `404`; `422 VALIDATION_ERROR` (invalid option
  codes); `503 EXTERNAL_SERVICE_FAILURE`; on poll `status=failed` →
  `PROCESSING_FAILURE` (details.run_id); `429 RATE_LIMITED`.
- **Security considerations:** grooming options are low-sensitivity user
  preference (vocab ids only — no free text, no injection surface); results are
  regenerable recommendations, never stored truth (BAR-0). Same owner-only /
  404-not-403 / C-8 posture as S-1.
- **Side effects:**
  - **History:** inserts an `analysis_runs` row (run_type `grooming`), writes
    the immutable result once on completion (TRX-5).
  - **No projection change by default:** grooming recommendations do **not**
    update the current profile (UC-27); if the user later "saves a style", that
    is a saved-look write (M7), not a profile edit.
  - **Failure:** no result, no side effects beyond the failed run row.
- **Domain entities involved:** E6 `AnalysisRun`; E5 `Look` (grooming catalog,
  read-only); E1.1 `UserState` (read: FaceProfile grooming inputs); value
  objects: GroomingRecommendation, GroomingOption (vocab ref).

---

### 5.4 S-4 — Upload / associate scan media

The scan's media is the run's `input_media` `MediaRef` (§4.4). Two mechanisms;
both end with the run carrying a `MediaRef` (never bytes, PR-8):

**a) Inline (primary — part of S-1/S-2).** The scan submission carries the
`image` part in `multipart/form-data`; the backend performs **upload-then-
insert** (TRX-1): blob → object storage (`users/{user_id}/scans/{run_id}/`),
then the run row references it via `input_media`. Validation is pre-upload
(`413/422 MEDIA_FAILURE`, API-38); bytes never base64'd (API-36).

**b) Separate M16 flow (referenced — owned by M16, sealed until MS10.3).**

- **Method / path:** `POST /v1/media/uploads` (endpoint 47) —
  `UploadRequest { purpose: "scan", filename, size, contentType }` →
  `201 { upload_id, signedPutUrl, expiresAt }`; then Flutter PUTs the bytes
  directly to object storage; then
- **Method / path:** `POST /v1/media/uploads/{upload_id}/complete` (endpoint
  48) → `MediaRef` (TRX-1 insert; HEAD size/type verification).
- **Asynchronous behavior:** the upload itself is client-direct; `/complete`
  is sync; any follow-on media processing is a job (M16).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1) — the signed URL is scoped to the single owner + declared key.
- **Validation:** purpose ∈ allowed set (`scan` is allowed); declared size ≤
  limit (e.g. 15–20 MB vision input) and MIME in allow-list
  (`image/jpeg`, `image/png`, `image/webp`) at both authorization and
  `/complete` (mismatch → **422/413 MEDIA_FAILURE**).
- **Errors:** `201`/`200`; `401`; `404`; `413/422 MEDIA_FAILURE`; `503
  EXTERNAL_SERVICE_FAILURE`.
- **Security considerations:** scan blobs are private by default (MS10.3); the
  signed URL is short-lived, owner-scoped, never stored long-term
  (`MEDIA_UPLOAD_ARCHITECTURE.md` §4.8/4.9). Orphan blobs (uploaded, never
  completed, or a failed scan) are swept by the async cleanup job.
- **Side effects:** blob in object storage; `/complete` inserts the `MediaRef`;
  an abandoned upload is orphan-swept. No run mutation — the run's `input_media`
  references the `MediaRef`.
- **Domain entities involved:** `MediaRef` (value/JSONB); E6 `AnalysisRun`
  (referencing it); M16 media module (owned).
- **Gating:** M16 is **sealed** — neither endpoint is mounted until MS10.3
  lifts (API-12); until then the inline `image` part on S-1/S-2 is the scan
  media path (once the analysis endpoints mount).

---

### 5.5 S-5 / S-6 — Processing status and result (`GetAnalysisRun`)

- **Method / path:** `GET /v1/analysis/runs/{run_id}` (endpoint 39, actions
  16/21/23 poll)
- **Asynchronous behavior:** **sync** — it is the *polling read* for the async
  submissions above. The same read serves both **processing status** (S-5) and
  **result retrieval** (S-6): the client polls until `status ∈ { completed,
  failed }`; a `completed` response carries the immutable `result` +
  `engine_version`.
- **Request schema:** none (`run_id` UUID in path).
- **Response schema:** `200 OK` — `AnalysisRun` (bare, no envelope; §4.3):

```
{
  "run_id": "7a2b…", "run_type": "outfit",
  "status": "completed",
  "created_at": "2026-08-10T12:00:00Z",
  "completed_at": "2026-08-10T12:00:05Z",
  "engine_version": "2026.08.1",
  "input_media": { "key": "users/u1/scans/7a2b…/input.jpg", "mediaType": "image/jpeg" },
  "result": { /* immutable typed snapshot — only when completed */ }
}
```

  While `pending` (CREATED/PROCESSING): only `run_id`, `run_type`, `status`,
  `created_at`. When `failed`: `status`, `created_at`, `completed_at`, and
  `error` (the frozen error body); **no** `result` (a failed run has no output
  and still is history, §5.6).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  — the run must belong to the caller; another user's (or a non-existent)
  `run_id` → **404** (404-not-403, API-10).
- **Validation:** `run_id` must be a valid UUID; malformed → **422**.
- **Errors:** `200`; `401`; `404 NOT_FOUND` (not yours / never existed);
  `422 VALIDATION_ERROR` (bad UUID).
- **Security considerations:** the `result` is the user's own scan history —
  owner-only, never logged; no other user's run is ever reachable. Response
  never exposes analysis internals beyond the typed snapshot (C-8).
- **Side effects:** none — a pure read of the immutable history.
- **Domain entities involved:** E6 `AnalysisRun`.

---

### 5.6 S-7 — Retry failed processing

Retry is covered by two existing mechanisms; **there is no retry endpoint**
(§3.2).

**a) Server-side automatic retry (transient only).** The in-process job runner
retries **once** on transient failures (timeout, 5xx, network) for the scan
capabilities (`BACKGROUND_JOB_ARCHITECTURE.md` §5.3;
`AI_INTEGRATION_ARCHITECTURE.md` §5.1/5.2/5.3: "1 retry on timeout/5xx").
Non-transient failures — **no face detected** (S-2), **no clothing detected**
(S-1), invalid grooming options (S-3) — are **never** retried (don't reprocess
a bad image). A job that fails twice is marked `failed` permanently. TRX-5's
write-once guard makes the retry safe (no double-completion).

**b) Client-initiated retry = a new submission.** The user-facing "Retry" on a
`failed` run is a **fresh `POST`** to the same scan endpoint (S-1/S-2/S-3),
creating a **new run** — never a mutation of the failed one:

```
retry: POST /v1/analysis/outfit (same image)   → 202 { run_id: new }   → poll S-5
failed run stays failed:  analysis_runs row (status=failed, error, no result) — immutable history
```

- **Method / path:** none invented — reuse the scan-creation `POST` for the
  scan type. No `POST /v1/analysis/runs/{run_id}/retry` exists: retrying in
  place would overwrite append-only history (PR-5/PR-6), and the failed run is
  intentionally kept as an auditable record of the failed attempt
  (`APPEARANCE_API.md` §4.4 guarantee 5).
- **What the client sees:** on `status=failed` the run carries the typed
  `error`; the UI shows a retry action that re-submits the scan inputs. The
  new run is a distinct historical record (analysis is never idempotent, §11).
- **Side effects:** the automatic retry re-runs the job against the **same**
  run (no new row); the client retry inserts a **new** `analysis_runs` row.
  Both honor TRX-5.
- **Domain entities involved:** E6 `AnalysisRun`.

---

### 5.7 S-8 — Delete scan (if supported)

**Runs are not deletable by the user.** This is a deliberate domain decision,
not a missing endpoint:

- **`DELETE /v1/analysis/runs/{run_id}` is NOT defined.** `analysis_runs` is
  append-only (`INSERT`/`SELECT` only, PR-5); completed and failed runs are
  immutable (PR-6); re-scanning creates new runs (§5.7 of
  `HISTORY_AND_VERSIONING.md`). A run row is removed **only** by account
  erasure (`DELETE /v1/users/me`, TRX-8 — owned by `AUTH_API.md`, referenced),
  which also deletes the scan blobs (async object-storage sweep,
  `SECURITY_PRIVACY_DESIGN.md` §5.2).
- **Scan media has a lifecycle, not a delete call.** Raw scan blobs
  **auto-expire unless the user saves them** — face scans expire after
  analysis unless saved; outfit scans e.g. after 30 days unless attached to a
  saved look (`STORAGE_INVENTORY.md` §1.2/§1.3; `MEDIA_STORAGE_DESIGN.md`
  §1.6). This is a **background retention job**, never a user-facing DELETE,
  and it never removes a saved look's snapshot (`HISTORY_AND_VERSIONING.md`
  §5.7: retention prunes only under rules).
- **M16 media deletion** (`DELETE /v1/media/…`) is part of the sealed media
  surface (logical tombstone + async byte sweep, `MEDIA_UPLOAD_ARCHITECTURE.md`
  §4.7) — referenced, gated until MS10.3.

**Answer to the task's "delete if supported":** individual scan deletion is
**not supported** (append-only history + erasure-only removal); unsaved scan
media auto-expires by retention. No DELETE endpoint is defined for scans.

---

### 5.8 S-9 — Scan history (`ListAnalysisRuns`)

- **Method / path:** `GET /v1/analysis/runs` (endpoint 40, scan history)
- **Asynchronous behavior:** **sync.**
- **Request schema:** query params `?run_type=&sort=created_at&page=&page_size=`
  (`run_type` optional — filter to a single scan type; sort only by
  `created_at`; pagination API-20/22).
- **Response schema:** `200 OK` — `ListEnvelope`:

```
{ "items": [ AnalysisRun… ], "page": 1, "page_size": 20, "total": 37 }
```

  List rows may be summary (no `result`) to keep the history read light;
  detail comes from S-5/S-6.
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  — only the caller's own runs (OW-1).
- **Validation:** `run_type` must be a valid run_types code → else **422**;
  `page`/`page_size` bounds `[1,100]` (API-22); unknown sort key → **422**.
- **Errors:** `200`; `401`; `404` (account gone); `422 VALIDATION_ERROR`;
  `429 RATE_LIMITED`.
- **Security considerations:** history is the user's own scan record —
  owner-only; pagination never leaks other users' rows; no content beyond the
  typed DTO.
- **Side effects:** none — pure read.
- **Domain entities involved:** E6 `AnalysisRun`.

---

### 5.9 The scan flow (a sequence of the above — no new endpoint)

```
S-1/S-2 submit image (multipart) ──202 {run_id}──►  S-5 poll ──► completed
    │ (blob → object storage TRX-1; run pending)      │          │ result snapshot (immutable, engine_version)
    │                                                  │          ▼
    │                                        S-6 result  ◄── S-9 history list (all scans, ?run_type=)
    ▼                                          + current profile only for face: TRX-6 → styleProfile
S-3 grooming (options JSON) ──202 {run_id}──► S-5 poll ──► recommendations only (no projection)
S-7 retry failed: auto 1x (transient) → still failed?  client re-POST → NEW run (failed run stays history)
S-8 delete: runs append-only (no DELETE); unsaved scan media auto-expires (retention job); erasure only (TRX-8)
```

---

## 6. Validation reference (shared)

| Field | Rules | Source |
| --- | --- | --- |
| `run_type` | ∈ run_types vocab {`outfit`,`face`,`hairstyle`,`grooming`}; scan endpoints produce `outfit`/`hairstyle`/`grooming` | `analysis_runs.run_type` FK, TABLE_DEFINITIONS |
| `status` | `pending → completed | failed`; write-once guard | TRX-5, CHECK constraint |
| `image` | required for S-1; optional for S-2 (absent = profile-only pass over `style_profile` by `user_id`, Phase 28); face/clothing detectable; size/content-type | API-16, UC-24/25 |
| `options.*` | valid `GroomingOption` vocab codes | K9.1 vocab (VALUE_OBJECTS row 8 family) |
| `run_id` | UUID; owned (404-not-403) | path param, OW-1 |
| media `purpose` | ∈ allowed set (`scan` allowed); declared size ≤ limit; MIME ∈ allow-list | MEDIA_UPLOAD §4.1–4.4 |
| `page`/`page_size` | `[1,100]` | API-22 |
| derived codes (`faceShape`/`skinTone`/`bodyType`) | vocab-validated (K9.1); codes finalized at §8 | API-14 |

All validation is **server-side** (Flutter never enforces security) and returns
the **safe client message**, never internals (ER-2).

---

## 7. Error reference for this surface

| `error.code` | HTTP | When | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | bad image / no face / no clothing (S-1/S-2); invalid grooming option (S-3); bad UUID/filter (S-5/S-9) | field errors + allowed values in `details` |
| `MEDIA_FAILURE` | 413/422 | image too large / unsupported content-type (S-1/S-2, S-4) | `details.maxBytes`; pre-run check |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | run not owned / never existed; account gone | 404-not-403, no existence leak |
| `EXTERNAL_SERVICE_FAILURE` | 502/503 | AI provider/submission failure; object storage | C-8: no provider internals |
| `PROCESSING_FAILURE` | 500 (sync) / run `failed` | analysis pipeline failure (after the 1 automatic retry) | `details.run_id`; the run is a historical failure |
| `RATE_LIMITED` | 429 | any endpoint | + `Retry-After` |

---

## 8. Open decisions (carried forward, unchanged where already recorded)

1. **D-AUTH-1 — auth provider** — unchanged; gates mounting the whole M12
   scan surface (endpoints stay unmounted until the seam lands, API-12).
2. **MS10.3 — media seal** — face/outfit image submission (`multipart` →
   `MediaRef`, and the M16 upload flow) depends on M16 unsealing; until then
   the scan endpoints are not mounted (API-12, same rule as the sealed
   modules). No fake 200 before either gate lifts.
3. **`face` run_type** — a dedicated face-only scan (run_type `face`, e.g. an
   onboarding scan producing only `FaceProfile`) has **no endpoint today**;
   the catalog mounts face analysis on `/v1/analysis/hairstyle` (run_type
   `hairstyle`). The vocabulary code is reserved, additive.
4. **Outfit "typed fields"** — `API_CONTRACT_RULES.md` §12.11 lists the outfit
   submission as `image + typed fields`; the exact optional context keys are
   finalized at M2/P2 implementation (no field is added to this contract).
5. **Auto-accept on completion** — face-scan completion applies attributes to
   the current projection at completion (per inventory 37, TRX-6). If the
   product instead wants an explicit "Save / Apply" acceptance step, it is
   additive as a `PATCH /v1/users/me` call after the run; the run remains the
   history either way.
6. **Analysis-derived vocab codes** — `faceShape`/`skinTone`/`bodyType` value
   codes are finalized with the knowledge layer (K9.1); until then the
   contract pins them to runs and rejects free text.
7. **CREATED-vs-PROCESSING on the wire** — both map to `pending` (§4.2); if a
   future product need requires distinguishing queued-from-running on the wire,
   that is a schema/contract change to be decided — not made here (PR-12).
8. **Scan retention windows** — exact auto-expire windows (face: "after
   analysis unless saved"; outfit: "e.g. 30 days") are config-driven and
   finalized with the retention job at M12/M16.
9. All other open decisions from `API_CONTRACT_RULES.md` §16,
   `APPEARANCE_API.md` §8, and `PROFILE_ONBOARDING_API.md` §8 remain open and
   are unaffected.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/SCAN_API.md` — the field-level
API contract for the scan system, covering **only the scan types the domain
model supports** (outfit, face→hairstyle, grooming; `face` reserved). It
defines every task operation — **create scan** (`POST /v1/analysis/outfit`,
`/hairstyle`, `/grooming`), **upload/associate media** (inline multipart part +
the referenced M16 flow), **processing status** and **retrieve result**
(`GET /v1/analysis/runs/{run_id}`), **retry failed processing** (automatic 1x +
client re-submission; no retry endpoint), and **delete** (runs are append-only
— no DELETE; media auto-expires; erasure only) — plus the supporting
**history** read (`GET /v1/analysis/runs`). The async lifecycle expresses the
task's four states — **CREATED / PROCESSING / COMPLETED / FAILED** — and maps
them honestly to the frozen three-value wire status (§4.2). Nothing is
implemented.

**Skills used:** repository + documentation analysis (`analysis_runs`/
`run_types` tables, TRX-1/5/6/8, UC-24…27, BACKGROUND_JOB retry §5.3,
AI_INTEGRATION_ARCHITECTURE FUTURE capability interfaces,
MEDIA_UPLOAD_ARCHITECTURE sealed M16, STORAGE_INVENTORY §1.2/1.3 retention,
API_CONTRACT_RULES §12.11/§8.3/§13, API_INVENTORY endpoints 36–40/47/48,
ERROR_HANDLING taxonomy, live `outfit_scan_mock_data.dart` /
`hairstyle_mock_data.dart` / `grooming_mock_data.dart` scan shapes, and the
sibling contract `APPEARANCE_API.md`) — documentation only.

**Files changed:** `docs/api/SCAN_API.md` (new); `CURRENT_STATE.md` (status).

**Validation run:**
- **Every defined operation traces 1:1 to the accepted inventory** — S-1→UC-24
  / endpoint 36, S-2→UC-25/26 / 37, S-3→UC-27 / 38, S-5/S-6→39, S-9→40,
  S-4→47/48 (referenced, sealed). Paths/methods/auth/UC/errors identical to
  `API_CONTRACT_RULES.md` §12.11 and `API_INVENTORY.md` §5.12/§5.15; the async
  `202 + run_id` + poll pattern matches §8.3 and API-41/42; the hairstyle/
  grooming request and result shapes are **identical** to the sibling
  `APPEARANCE_API.md` §5.1/§5.2 — no field renamed, removed, or retyped (API-2).
- **Wire shapes match the accepted sketches** — `AnalysisRun`, `AsyncAccepted`,
  and `ListEnvelope` are identical to §8.3/§13; result snapshots mirror the
  real mock shapes (`OutfitAnalysisData`, `HairstyleAnalysisResult`,
  `GroomingAnalysisResult`). The task's four lifecycle states are documented
  and mapped to the frozen three-value `status` (§4.2) rather than inventing a
  fourth wire value the schema forbids.
- **The immutable-history rule is structurally enforced** — scans are
  `analysis_runs` EVENT/HISTORICAL_RECORD (append-only, PR-5); write-once
  completion (TRX-5); retry = new submission, never a mutation of a failed run;
  **no DELETE run endpoint** (§5.7) and **no retry endpoint** (§5.6) exist —
  both would violate PR-5/PR-6 and are explicitly documented as not defined
  (§3.2). No invented endpoints.
- **Auth/authorization/errors consistent** — all scan endpoints auth +
  owner-only (OW-1, 404-not-403); frozen 12-category errors; 401 +
  `WWW-Authenticate`, 429 + `Retry-After`; scan submissions never idempotent
  (§11), reads/polls naturally idempotent.
- **`git status --short`:** `docs/api/` holds API_CONTRACT_RULES.md,
  API_INVENTORY.md, AUTH_API.md, PROFILE_ONBOARDING_API.md, APPEARANCE_API.md,
  SCAN_API.md (untracked) + `CURRENT_STATE.md`; no code, directories, or files
  created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- The M12 scan endpoints are **not mounted** until D-AUTH-1 + the media/
  analysis pipeline exist; before MS10.3 lifts, no scan-image upload path exists
  (API-12 — no fake 200).
- `face` run_type endpoint, outfit "typed fields", auto-accept vs explicit
  save, analysis-derived vocab codes, and the CREATED-vs-PROCESSING wire
  question are decided at M2/P2 implementation (§8.3–8.7).
- Scan retention windows are config-driven and finalized with the retention
  job (§8.8).
- Other open decisions unchanged: auth provider (D-AUTH-1), User fields,
  Today'sLookRecord (P1), RecommendationHistory (P3), conversation retention,
  K9.1 knowledge shape, media-privacy (MS10.3), feedback design.

**Assumptions recorded:**
- A "scan" is the `AnalysisRun` row; there is no separate scan resource and no
  `/scans/*` path (§3.2).
- CREATED and PROCESSING are both `pending` on the wire (§4.2); the client may
  infer phase locally but the contract does not distinguish them.
- Scan media is stored as a `MediaRef` (PR-8); raw scan blobs auto-expire
  unless saved (retention job, §5.7).
- Retry is the automatic 1x transient retry plus client re-submission; failed
  runs are immutable history (auditable), never mutated (§5.6).
- Face scans are the only scans that write the current projection (TRX-6);
  outfit and grooming scans write history only until a style is explicitly
  accepted via the saved-look surface.

**Constraints honored:** no implementation (scanning NOT created, no AI
providers, no object storage, no media), the live assistant contract untouched
(F-5), no invented APIs (retry/delete/cancel/face explicitly excluded and
documented), the run status machine and request/result shapes kept identical to
the accepted contract and sibling docs, scope limited to
`docs/api/SCAN_API.md` + `CURRENT_STATE.md`.
