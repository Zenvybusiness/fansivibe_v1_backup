# Fansivibe — Background Job Architecture

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Determines **which Fansivibe
> operations are synchronous vs. asynchronous**, and defines the job
> lifecycle (creation, status, retry, timeout, failure, result persistence)
> for the operations that must go async — **without adding Celery, Redis,
> message queues, or other infrastructure unless the actual requirements
> justify them.**
>
> **Status: architecture design only. Nothing is implemented.** No code,
> files, directories, or dependencies are created; the live assistant
> contract (`POST /v1/assistant/chat`) is unchanged.
>
> **Grounding fact (BA-10 / no-premature-complexity):** today the backend is
> a **single synchronous FastAPI process** (one engine, rules-only, optional
> Ollama) with **no queues, no workers, no Redis, no Celery** (`requirements.txt`,
> `docker-compose.yml`). This design preserves that default and adds async
> **only where a real requirement exists** — slow image analysis. Everything
> else stays synchronous.

---

## 1. Purpose and scope

This document answers, for each candidate operation:

1. **SYNC / ASYNC / OPTIONAL ASYNC** — the classification and why.
2. **Job lifecycle** — creation, status, retry, timeout, failure, result
   persistence (for the ASYNC cases).

It also states the **infrastructure decision**: which async mechanism (if any)
is justified, and which are explicitly **rejected** as premature.

It does **not** implement jobs, queues, or workers.

**Grounding rules from accepted docs:**
- **API-40…43 (`API_LAYER_ARCHITECTURE.md`):** synchronous by default; slow
  analysis uses `202 + run_id` + polling (`pending → completed | failed`);
  no background jobs in routers (`infrastructure/jobs.py` + events).
- **TRX-5 (`TRANSACTION_BOUNDARIES.md`):** analysis runs are write-once —
  a single guarded completion sets `status='completed'`, `result`,
  `completed_at`; blob upload is outside the transaction.
- **AI_INTEGRATION_ARCHITECTURE.md:** capability timeouts (20–30s for vision),
  retries (1), graceful degradation; AI never inside a DB transaction.
- **BA-10 / PR-12:** no premature complexity; only real needs get machinery.
- **§5 `TRANSACTION_BOUNDARIES.md`:** external effects after commit;
  retention/pruning jobs run in their own transactions.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| Current `backend/` (requirements, docker-compose, main.py) | Proven: no async infra today; single sync process; Ollama only. |
| `APPLICATION_USE_CASES.md` | UC-24/25/26/27 (analysis), UC-16/17 (daily outfit), UC-21 (event), UC-28/29 (outfit), UC-15/30 (save). |
| `API_LAYER_ARCHITECTURE.md` | §15 async (API-40…44): 202 + run_id polling, sync-by-default. |
| `TRANSACTION_BOUNDARIES.md` | TRX-5 write-once completion; §4/§5 single-row vs non-transactional. |
| `AI_INTEGRATION_ARCHITECTURE.md` | Capability timeouts/retries/degrade; async analysis run model. |
| `ERROR_HANDLING.md` | `PROCESSING_FAILURE` (run `failed` + error code), `MEDIA_FAILURE`, `AI_FAILURE`. |
| `KNOWLEDGE_ARCHITECTURE.md` | Knowledge retrieval is fast (cached) — no async. |

---

## 3. The decision framework

**BJ-0 (async only for real latency/IO needs):** an operation goes ASYNC only
if it has **at least one** of:

1. **Long, blocking work** the client cannot wait for within the API timeout
   (e.g. vision analysis on a large image: 20–30s capability timeouts).
2. **External side effects that must not block the request** (blob cleanup
   after delete, webhook entitlement, retention) — post-commit work, §5 of
   TRANSACTION_BOUNDARIES.
3. **Heavy repeated IO** that would starve the sync pool (batch processing).

Operations with none of these stay **SYNC**. This keeps the default simple:
one process, synchronous use cases, `infrastructure/jobs.py` for the few
deferred tasks.

---

## 4. Operation classification

### 4.1 `face analysis` — **ASYNC**

- **Why:** vision capability, 30s timeout (AI doc §5.1), large image upload,
  produces a persisted `AnalysisRun` (TRX-5).
- **Pattern:** `POST /analysis/face` → `202 + run_id` → poll
  `GET /analysis/runs/{run_id}`.

### 4.2 `outfit image analysis` — **ASYNC**

- **Why:** vision capability, 30s timeout (§5.3), image upload, persisted
  run + `result` (UC-24, TRX-5).
- **Pattern:** `POST /analysis/outfit` → `202 + run_id` → poll; on completion
  the run carries sections/items/scores + confidence.

### 4.3 `wardrobe image processing` — **OPTIONAL ASYNC**

- **Why:** image processing (metadata extraction, thumbnail, palette via
  `ImageAnalysisProvider`, 20s) is slower than a normal write but faster than
  full analysis. Default **ASYNC** when M16/MS10.3 media lands; a small image
  could stay sync.
- **Decision:** **ASYNC by default** (media-gated, P2), with the same run/
  job pattern. Until M16 exists: **N/A** (no image path).

### 4.4 `recommendation generation` — **SYNC**

- **Why:** today it is **deterministic rules** (engine tools) — instant; even
  with AI-driven candidates it is bounded (≤30s, degrade-to-rules, additive).
  No client-facing reason to defer.
- **Decision:** **SYNC** (always). If an AI-driven provider later exceeds the
  timeout, revisit per BJ-0 — but the rules path guarantees sync success.

### 4.5 `generated images` — **ASYNC**

- **Why:** image generation (AI image synthesis, FUTURE) is the slowest
  operation (multi-second to minutes); must not block a request.
- **Decision:** **ASYNC** (FUTURE capability, AI-0 honesty — not implemented;
  defined now so the pattern is ready). `POST /images/generate` → `202` +
  job/run → poll.

### 4.6 `daily outfit generation` — **SYNC**

- **Why:** rules-based derivation (UC-16) is instant; optional weather hint
  is fast and degrade-safe (non-authoritative). The today's-look is a derived
  value object, not a persisted run (TRX-2/4).
- **Decision:** **SYNC**.

### 4.7 `event recommendations` — **SYNC**

- **Why:** event→outfit generation (UC-21) delegates to the same
  recommendation generation (SYNC, §4.4); it reads event + wardrobe + profile
  (fast) and produces a regenerable recommendation (TRX-7).
- **Decision:** **SYNC**.

### 4.8 `large media processing` — **ASYNC**

- **Why:** large blobs (high-res photos, multiple images) involve object
  storage + image processing beyond request timeouts; upload itself is
  upload-then-insert (TRX-1) with async orphan sweep.
- **Decision:** **ASYNC** (M16-gated, P2) — media processing pipeline runs as
  a job after the blob is referenced.

### 4.9 Summary table

| Operation | Class | Reason | Persisted result |
| --- | --- | --- | --- |
| face analysis | **ASYNC** | 30s vision, run + TRX-5 | `analysis_runs` |
| outfit image analysis | **ASYNC** | 30s vision, run + TRX-5 | `analysis_runs` |
| wardrobe image processing | **OPTIONAL ASYNC** (ASYNC w/ M16) | media-gated; small sync | `wardrobe_items` media ref + image tasks |
| recommendation generation | **SYNC** | rules-instant; AI additive/degrade | none (regenerable) |
| generated images | **ASYNC** | slowest, FUTURE | media refs + job |
| daily outfit generation | **SYNC** | rules-instant, derived | none (or today_look_records P1) |
| event recommendations | **SYNC** | delegates to SYNC generation | none (TRX-7) |
| large media processing | **ASYNC** | blob + image work beyond timeout | media refs |

---

## 5. Job lifecycle (for ASYNC operations)

A Fanvivibe **job** is a unit of deferred work. For analysis it is the
`AnalysisRun` row itself (TRX-5); for media/generated images it is a
**job row** in the media/analysis tables (or a `jobs` row where needed).
The lifecycle is identical.

### 5.1 Job creation

- The `POST` validates input, uploads the blob **before** the row insert
  (TRX-1), then creates the run/job row in **`pending`** and returns
  `202 + { "run_id": ... }` (API-41).
- **No queue** is needed for creation: the row is the record of the job;
  `infrastructure/jobs.py` (in-process) picks up `pending` rows.

### 5.2 Job status

- States: `pending → completed | failed` (write-once, TRX-5).
- Client polls `GET /analysis/runs/{run_id}` (or the job status endpoint);
  `completed` carries the `result` (immutable), `failed` carries
  `error.code` (`PROCESSING_FAILURE`/`MEDIA_FAILURE`/`AI_FAILURE`).
- Status is **derived from the row**, never from in-memory state — restarts
  and multi-worker deploys remain correct.

### 5.3 Retry

- **Retry scope:** only **transient** failures (timeout, 5xx, network) get
  **1 retry** (AI doc §5; capability retries). Non-transient failures
  (invalid image, face not detected, validation) are **never** retried.
- Retry is **automatic** (the in-process job runner retries once) or
  client-initiated (re-`POST`) — both safe because TRX-5 write-once prevents
  double-completion.
- **No retry storms:** a job that fails twice is marked `failed` permanently.

### 5.4 Timeout

- Per-operation timeouts from the AI doc: face/hair/outfit **30s**,
  image analysis **20s**, generation per capability. A job exceeding the
  capability timeout (including 1 retry) → `failed` with `AI_FAILURE`/`PROCESSING_FAILURE`.
- The HTTP request never waits for the job; polling is bounded client-side.

### 5.5 Failure

- Failure sets `status='failed'` (write-once guard: only a `pending` row can
  transition) + `error.code` + optional `error.message` (safe, allow-listed —
  ERROR_HANDLING ER-1).
- **Orphan blobs** (upload succeeded, job failed) are swept by the async
  cleanup job (TRX-1 §5).
- **Failure is honest (AI-0):** no fabricated partial results; the run stays
  `failed` until re-submitted.

### 5.6 Result persistence

- `completed` → `result` is written **once** with the run (TRX-5: `WHERE
  status='pending'`), carrying `engine_version`/`model_version` for
  provenance (AI doc §6).
- Results are **immutable after completion** (append-only grants, PR-6).
- Non-analysis jobs (media, generated images) persist **media refs** on the
  owning row (M16/MS10.3) — never image bytes in PG (PR-8).

---

## 6. Infrastructure decision (BJ-0 applied)

| Mechanism | Adopted? | Rationale |
| --- | --- | --- |
| **In-process async runner** (`infrastructure/jobs.py`, asyncio/background task) | **YES** (default) | Only async need is deferred work + polling; a single FastAPI process can run `pending` jobs in background tasks. Zero new infra. |
| DB row = job record | **YES** | `analysis_runs` already is the job (TRX-5); status derived from the row survives restarts. |
| Celery | **NO** | Adds workers/broker; no requirement yet (analysis is low-volume, in-process suffices). Revisit only if throughput demands multi-worker. |
| Redis / message queues | **NO** | No fan-out, no cross-service pub/sub, no real-time need. Polling on the run row is sufficient. |
| Dedicated worker process | **NO** (deferred) | Only if jobs outgrow the request process (FUTURE decision, gated on measured need). |

**BJ-1 (defer, don't build):** all async today is served by the in-process
runner + DB-row job records. Queues/Celery/Redis are **explicitly rejected**
until a measured requirement exists (throughput, retry durability beyond
process lifetime, or multi-instance deployment) — consistent with BA-10 and
§9 migration (no new deps until real need).

---

## 7. Report, assumptions, constraints

**What changed (this step):** added `BACKGROUND_JOB_ARCHITECTURE.md` — the
sync/async classification and job lifecycle design. No implementation.

**Skills used:** repository analysis (current backend deps/compose confirm no
queues; accepted async patterns API-40…44, TRX-5, capability timeouts) —
architecture documentation only.

**Files changed:** `docs/backend/BACKGROUND_JOB_ARCHITECTURE.md` (new).

**Validation run:**
- Every operation classified against real latency/IO needs (vision timeouts,
  blob IO, rules-instant work) using BJ-0; no operation is async without a
  documented reason.
- Job lifecycle maps to accepted docs: TRX-5 (write-once), API-41 (202 +
  run_id), ERROR_HANDLING (failed + error.code), AI doc (timeouts/retries).
- Infrastructure decision grounded in the current repo (no Celery/Redis/queue
  exists; only FastAPI + Ollama) and explicitly rejected under BJ-1 until a
  measured need — honoring "do not introduce Celery, Redis, queues unless
  required."
- `git status --short`: only this new doc + `CURRENT_STATE.md` update; no
  code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- The in-process runner details (asyncio task lifecycle, restart-safe pickup)
  are implemented at M4/P2 with the analysis module (M12) and media (M16).
- `generated images` is a FUTURE capability (AI-0): classified now, gated on
  the product actually adding image generation.
- No `DECISIONS.md` entry needed: no accepted architectural decision made
  (documentation only); open items remain in `BACKEND_ARCHITECTURE_RULES.md`
  §8/§10.

**Assumptions recorded:**
- "ASYNC" = client receives `202 + run_id` and polls the row (API-41);
  "OPTIONAL ASYNC" = async by default but a fast path may stay sync.
- Today only face/outfit analysis are real ASYNC candidates; the rest of the
  ASYNC set is gated on M16 media or FUTURE capabilities and marked as such.
- Job status is always derived from the DB row (never in-memory), so the
  in-process runner can be replaced later without changing the contract.

**Constraints honored:** BA-10/PR-12 (no premature complexity; no queue infra
without a measured need), API-40…44 (sync-by-default, 202+run_id, jobs out of
routers), TRX-1/5 (upload-then-insert, write-once completion), PR-8 (no image
bytes in PG), ERROR_HANDLING (safe failure codes), the UI Change Safety Rule
(no Flutter modified), and the Scope rule (this document only).