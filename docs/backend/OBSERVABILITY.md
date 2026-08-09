# Fansivibe — Observability (Logging & Tracing) Requirements

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Defines **basic observability**
> for Fansivibe: structured **logging and tracing** for request ID, user ID
> (where appropriate), use case, AI operation, model version, processing
> duration, database operation failures, external service failures, and
> background jobs — and the explicit **never-logged** list (passwords,
> authentication tokens, raw private images, unnecessary sensitive
> appearance data).
>
> **Status: architecture design only. Nothing is implemented.** No code,
> dependencies, or config are created. Verified: the current `backend/app`
> has **no logging at all** (no `logging`, `logger`, or `print` in app code);
> this doc defines the target. The live assistant contract
> (`POST /v1/assistant/chat`) is unchanged.

---

## 1. Purpose and scope

Observability gives operations the ability to **follow one request end-to-end**
and **diagnose failures** without ever capturing sensitive data. This document
specifies:

1. **What is logged** — the fields and the events.
2. **How it is structured** — log records + correlation (tracing).
3. **What is never logged** — the hard privacy/safety boundary.
4. **Where it applies** — per-layer responsibilities (API → application →
   domain → infrastructure) and the required events (request, use case, AI
   op, DB failure, external failure, background job).

It is consistent with the accepted **ERROR_HANDLING.md** logging policy
(ER-0…ER-3: allow-listed `details`, never stack/SQL/provider/token/user
content, level table) and the **AI_INTEGRATION_ARCHITECTURE.md** capability
logging attributes (model version, confidence, failure mode, duration).

**Key principles:**
- **Structured, not raw:** every log line is a JSON object with typed fields
  — machine-queryable, redactable, and greppable by request ID.
- **Correlation by request ID:** a single request carries one request ID
  through API → application → domain → infrastructure so every line is
  traceable (tracing = the request ID + span metadata; no separate tracing
  system required yet).
- **Privacy by default (MS10.3, ER-2):** user-identifying and appearance
  data is excluded unless explicitly listed; the never-logged list is
  absolute.

**Grounding rules:**
- **ER-0…ER-3 (`ERROR_HANDLING.md`):** allow-listed error details; no stack
  traces, SQL, provider names, tokens, or user content in logs; level table.
- **AI_INTEGRATION_ARCHITECTURE.md:** capability logging includes model
  version, input/output shapes (never content), confidence, failure mode,
  duration; `llm_backend.py` is the model-interaction seam.
- **AUTH_AUTHORIZATION_ARCHITECTURE.md:** token values never logged;
  user_id logged where appropriate (but appearance/image data is not).
- **BACKGROUND_JOB_ARCHITECTURE.md:** job status is row-derived; logs carry
  the job/run ID, never the payload.
- **MEDIA_UPLOAD_ARCHITECTURE.md:** no URLs, no image bytes, no public
  exposure in logs.
- **TRANSACTION_BOUNDARIES.md:** DB operation failures logged with the
  operation + constraint (safe), never the row content.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `backend/app` | Verified: no logging exists today (target defined here). |
| `ERROR_HANDLING.md` | ER-0…ER-3 logging policy, level table, never-log list. |
| `AI_INTEGRATION_ARCHITECTURE.md` | Capability logging attributes (model version, confidence, duration, failure mode). |
| `AUTH_AUTHORIZATION_ARCHITECTURE.md` | user_id logging; tokens never logged. |
| `BACKGROUND_JOB_ARCHITECTURE.md` | Job/run ID correlation; row-derived status. |
| `MEDIA_UPLOAD_ARCHITECTURE.md` | No URLs/images/bytes in logs. |
| `SECURITY_PRIVACY_DESIGN.md` | MS10.3 privacy/erasure applies to logs (retention). |

---

## 3. Log record (structure)

Every log line is a **structured record** with a fixed envelope:

| Field | Type | When | Notes |
| --- | --- | --- | --- |
| `ts` | ISO-8601 | always | event time |
| `level` | enum | always | `DEBUG/INFO/WARN/ERROR` |
| `request_id` | string (UUID) | request-scoped | correlation key |
| `span_id` | string | nested ops | sub-operation correlation (tracing) |
| `service` | string | always | `fansivibe-backend` |
| `use_case` | string | app/domain ops | e.g. `UC-22`, `analyze_face` |
| `user_id` | string (UUID) | where appropriate (§5) | redactable/opt-out |
| `job_id` / `run_id` | string | background jobs | correlates job lifecycle |
| `event` | string | always | e.g. `request.started`, `ai.called` |
| `status` | string | events | `started/succeeded/failed` |
| `duration_ms` | int | completed ops | timing |
| `detail` | object | per-event | **allow-listed** fields only |

The **envelope is always complete** (every request has a `request_id` even if
`user_id` is absent, e.g. unauthenticated assistant calls). Optional fields
are omitted (never empty strings) to keep records compact.

---

## 4. Required events (logging + tracing)

### 4.1 Request ID

- **Assigned at the API boundary** (middleware) on entry: `request_id` UUID.
  If the client supplies one (`X-Request-ID`), it is used (bounded format) —
  otherwise generated. Never trusted blindly (length/format enforced).
- Threaded **explicitly** through application → domain (DR-1/F-3: the ID is
  part of the call context, never global state). Every log line carries it.
- **Span IDs** mark sub-operations (e.g. DB query, AI call, job) so a request
  is a tree of spans — this is the "tracing"; no external tracing system is
  required until volume/UX justifies one.

### 4.2 User ID (where appropriate)

- Logged on **user-scoped** events (owner-scoped reads/writes, uploads,
  auth) — the `user_id` from the authenticated principal (OW-1).
- **Not logged** where it adds no diagnostic value (health checks,
  anonymous assistant calls).
- `user_id` is **not sensitive by itself** but is paired with the privacy
  rule: it may appear in logs, but **never with appearance/image data** in
  the same record (correlation must not enable profiling). Where both are
  needed, redact the appearance part.

### 4.3 Use case

- Each application use case (UC-1…UC-33) logs `use_case` + `status` +
  `duration_ms` at INFO on success, WARN on degraded (e.g. AI fallback to
  rules), ERROR on failure. This gives per-use-case latency/reliability
  without exposing content.
- The use-case name is a **stable enum string** (e.g. `assistant.chat`,
  `analysis.run.face`, `media.upload.complete`) — never free-form text.

### 4.4 AI operation

- Each capability call (via `infrastructure/external/ai.py`) logs an
  `ai.*` event: `ai.called`, `ai.succeeded`, `ai.failed` (AI-0 statuses).
- Fields: capability (e.g. `text_enrichment`), **model_version**,
  input/output **shape** (token counts, byte sizes — never content),
  confidence bucket when present, failure mode (`timeout/retry/garbage`),
  retry count, duration_ms.
- **Raw AI input/output is never logged** (ER-2; LLM provider content,
  images, prompts excluded). Only shapes + status + model version.

### 4.5 Model version

- Captured at the **AI capability seam** (AI doc §6 provenance) and logged on
  every `ai.*` event: the model/provider version that produced a result, so
  regression analysis can pin output to a version.
- Also recorded on **analysis runs** (TRX-5 result provenance) and surfaced
  in logs as `model_version` on `analysis.completed`/`job.completed` events.

### 4.6 Processing duration

- `duration_ms` on every completed operation: request end-to-end (middleware),
  use case, AI call, DB operation (when slow), job.
- **Slow-operation threshold logging:** DB ops / external calls exceeding a
  configurable threshold log at WARN with the operation name + duration —
  the earliest signal of regression.

### 4.7 Database operation failures

- On DB error: log the **operation name** (`users.create`,
  `wardrobe.item.update`), the **constraint/state** from the safe error code
  (`DATABASE_FAILURE`, `CONFLICT`), the request_id, duration.
- **Never log SQL text, bound parameters, row content, or data dumps**
  (ER-1). The structured `detail` carries only allow-listed codes.

### 4.8 External service failures

- On external failure (AI provider, object storage, knowledge source):
  log the **service category** (`ai`, `storage`, `knowledge`), the failure
  code (`AI_FAILURE`, `MEDIA_FAILURE`, `EXTERNAL_SERVICE_FAILURE`), status
  code where safe, retry count, duration.
- **Never log** provider URLs/keys, response bodies, or request payloads
  (ER-1/ER-2). `llm_backend.py` remains the only model-interaction seam, and
  it logs shapes only.

### 4.9 Background jobs

- Jobs (per BACKGROUND_JOB_ARCHITECTURE) log lifecycle events with
  `job_id`/`run_id`: `job.created`, `job.started`, `job.retry`,
  `job.completed`, `job.failed`.
- Fields: job type, row-derived status, attempt count, duration_ms, failure
  code. **Never the job payload** (image refs fine; image content never).
- A job failure always also produces an ERROR line with the **owning
  request_id** when the job was spawned from a request.

---

## 5. Logging levels

| Level | Use |
| --- | --- |
| `DEBUG` | development/tracing of request flow; disabled in prod by default |
| `INFO` | request start/end, use-case success, job lifecycle, AI success |
| `WARN` | degraded paths (AI→rules fallback, slow DB/external op, first retry) |
| `ERROR` | use-case/job/external failure; unhandled exception with request_id |
| (no FATAL) | process-level failures surface via deployment, not app logs |

---

## 6. Never logged (absolute boundary)

**ER-4 — the never-log list (privacy + safety, MS10.3):**

1. **Passwords** — any credential, hash, or derived secret.
2. **Authentication tokens** — access tokens, refresh tokens, signed URL
   query strings (AUTH doc; MEDIA doc).
3. **Raw private images** — image bytes, file contents, object keys in
   queryable form that expose user content (only sanitized refs/IDs).
4. **Unnecessary sensitive appearance data** — face metrics, analysis
   details, appearance judgments, scan content. The rule: **log the event and
   the outcome, never the substance.** If an analysis fails, log
   `ai.failed failure=timeout`, not why the image was rejected visually.
5. **Also excluded by ER-0…ER-3:** stack traces, raw SQL/params, provider
   keys/URLs, LLM prompts/outputs, client IP bodies of user text.

**Enforcement:** the structured `detail` object is **allow-list only** — any
field not on the allowed set is dropped by the logging layer (not by
convention). This makes the boundary structural, not aspirational.

---

## 7. Current state and sequencing

- **Today:** no logging in `backend/app`; the assistant is a single sync
  request. 
- **M1–M2:** M2 ships the typed error + logging **configuration** (per
  ERROR_HANDLING) — the structured envelope, levels, never-log list, and
  request_id middleware. Assistant keeps its contract; 19 tests stay green.
- **M3+:** use-case/AI/job events are added as each module lands (M4 P0
  slice, M12 analysis, M16 media) — always through the same structured
  logging layer.
- **No external tracing system** (OTel/Jaeger/etc.) is introduced now (BJ-1
  philosophy: request-ID correlation suffices); revisit only on measured
  need.

---

## 8. Report, assumptions, constraints

**What changed (this step):** added `OBSERVABILITY.md` — the logging/tracing
requirements. Nothing implemented.

**Skills used:** repository analysis (verified no logging exists in
`backend/app`; grounded in ERROR_HANDLING ER-0…3, AI capability logging,
AUTH/MEDIA/JOB docs) — architecture documentation only.

**Files changed:** `docs/backend/OBSERVABILITY.md` (new).

**Validation run:**
- Every required logging subject is defined: request ID (§4.1), user ID
  where appropriate (§4.2), use case (§4.3), AI operation (§4.4), model
  version (§4.5), processing duration (§4.6), DB operation failures (§4.7),
  external service failures (§4.8), background jobs (§4.9).
- The never-logged list matches the task exactly (passwords, auth tokens,
  raw private images, unnecessary sensitive appearance data) plus the
  existing ER-0…ER-3 exclusions — enforced via allow-listed `detail`.
- Consistent with ERROR_HANDLING.md (ER-0…3, levels), AI doc (model version/
  shapes), AUTH doc (tokens never), MEDIA doc (no URLs/bytes), JOB doc
  (row-derived status, no payloads), MS10.3 (retention/erasure applies).
- `git status --short`: only this new doc + `CURRENT_STATE.md` update; no
  code, directories, or files created. No pytest run needed (no code change).

**Remaining issues / follow-ups:**
- Structured logging **configuration** is implemented at M2 (typed error
  contract + logging setup per ERROR_HANDLING); events per module at M4+.
- No decision on a logging **transport/aggregation** (console → JSON →
  external sink) — not needed until deployment; the record format here is
  transport-agnostic.
- Retention of logs must respect MS10.3 erasure (a user erasure request
  should trigger log redaction where user_id appears) — deferred to the
  erasure implementation.
- No `DECISIONS.md` entry added (documentation only).

**Assumptions recorded:**
- Request ID correlation is sufficient "tracing" at this stage; no external
  tracing system.
- Logs are structured JSON records; the envelope is complete (request_id
  always present, optional fields omitted).
- user_id is loggable when paired only with non-sensitive diagnostics; never
  with appearance/image data in the same record.

**Constraints honored:** ER-0…ER-3 (allow-listed detail, no stack/SQL/token/
content), AI doc (shapes not content, model version), AUTH doc (no tokens),
MEDIA doc (no URLs/bytes), JOB doc (no payloads), MS10.3 (privacy, erasure),
the Scope rule (this document only), and no implementation (observability
NOT created).