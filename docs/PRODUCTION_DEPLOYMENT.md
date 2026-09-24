# Fansivibe Production Deployment Runbook (Phase 3AL)

Target deployment topology:

```
PostgreSQL 16 (Managed DB with PITR)
    ↓
Ollama Host (Local / GPU Instance: qwen2.5vl:3b)
    ↓
FastAPI Docker Container (`backend/Dockerfile` + `entrypoint.sh`)
    ↓
HTTPS Reverse Proxy / Load Balancer (Nginx / Caddy / Cloud LB with TLS Termination)
    ↓
Flutter Client (Android Release-Signed / iOS / Web)
```

> Truthfulness note: this repository contains NO production domain, TLS certificate, PostgreSQL server, Ollama server, keystore, or secret. Every section below is labeled **[REPO]** (implemented in this codebase) or **[INFRA]** (must be provisioned out-of-band).

---

## 1. Environment Configuration & Canonical Variables — [REPO + INFRA]

The backend configuration is managed by the leaf settings module (`backend/app/config/settings.py`) backed by Pydantic `BaseSettings`. Canonical naming scheme and legacy aliases:

| Canonical Variable | Alias / Fallback | Default | Description |
|---|---|---|---|
| `FANSIVIBE_ENV` | `ENVIRONMENT` | `development` | Environment mode (`development`, `test`, `staging`, `production`). In `production`, strict invariants are enforced. |
| `DATABASE_URL` | — | `postgresql+psycopg://...` | Connection string for Postgres. Production rejects `fansivibe_dev` default credentials. |
| `DATABASE_POOL_SIZE` | — | `5` | SQLAlchemy connection pool size. |
| `DATABASE_POOL_TIMEOUT_S` | — | `30.0` | Connection checkout timeout from pool. |
| `FANSIVIBE_AUTH_SECRET` | — | `dev-only-...` | JWT signing secret. Production rejects dev default and requires >= 32 characters. |
| `FANSIVIBE_ALLOW_DEV_TOKEN` | — | `false` | Must stay `false` in production (enforced by validator). |
| `FANSIVIBE_OLLAMA_BASE_URL` | `FANSIVIBE_OLLAMA_HOST` | `http://localhost:11434` | Ollama HTTP host endpoint. |
| `FANSIVIBE_OLLAMA_MODEL` | `FANSIVIBE_REASONING_MODEL` | `qwen2.5vl:3b` | Frozen reasoning model name. |
| `FANSIVIBE_OLLAMA_TIMEOUT` | `FANSIVIBE_REASONING_TIMEOUT_S`| `60.0` | Ollama inference timeout (seconds). |
| `FANSIVIBE_OLLAMA_CONNECT_TIMEOUT`| — | `5.0` | Ollama TCP connect timeout (seconds). |
| `FANSIVIBE_REASONING_TEMPERATURE`| — | `0.0` | Model decoding temperature (0.0 for benchmark determinism). |
| `FANSIVIBE_REASONING_MAX_RETRIES`| — | `1` | Max transport retries for transient HTTP/socket failures. |
| `FANSIVIBE_REASONING_CONCURRENCY_LIMIT`| — | `2` | Max concurrent Ollama inference requests per backend instance. |
| `FANSIVIBE_REASONING_KEEP_ALIVE` | — | `15m` | Ollama VRAM keep-alive parameter (`15m` or `-1` for indefinite). |
| `FANSIVIBE_RATE_LIMIT_REASONING_PER_MINUTE`| — | `30` | Sliding-window per-IP reasoning request limit. |
| `FANSIVIBE_DISABLE_REASONING` | — | `false` | Typed kill-switch. When `true`, `/v1/reasoning` returns 503 and `/ready` reports reasoning as disabled. |
| `FANSIVIBE_LOG_LEVEL` | — | `INFO` | Root logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `FANSIVIBE_CORS_ORIGINS` | — | `[]` | Allowed browser origins (comma-separated or JSON list). Production forbids `*` with credentials. |

---

## 2. Ollama / Model Lifecycle Management — [REPO + INFRA]

The model lifecycle is managed via `OllamaLifecycleManager` (`backend/app/ai/lifecycle.py`):

1. **Startup Probe**:
   - On backend startup (`lifespan`), the backend issues a non-blocking `check_availability(timeout_s=2.0)` to Ollama `/api/tags`.
   - Verifies Ollama is listening and `qwen2.5vl:3b` exists in the local model library.
   - If Ollama is offline or the model is missing at startup, the service logs a structured warning and continues running. Core services (auth, database, wardrobe, knowledge reads) remain 100% available.

2. **Model Warmup & Keep-Alive Pinning**:
   - If the model is detected at startup, the manager triggers a background asynchronous warmup (`warmup()`).
   - Issues a minimal ping with `keep_alive: "15m"` to load model weights into GPU VRAM / system memory.
   - Eliminates cold-start latency spikes for user queries (cold start ~15s drops to warm latency ~1-2s).
   - In production with dedicated GPU, set `FANSIVIBE_REASONING_KEEP_ALIVE=-1` to permanently pin model weights in VRAM.

3. **Adapter Keep-Alive Transmission**:
   - `OllamaFashionReasoner` forwards `keep_alive` in all chat payloads (`backend/app/ai/ollama_reasoner.py`), ensuring the model stays warm during active usage.

---

## 3. Health & Readiness Architecture — [REPO]

1. **Liveness Probe (`GET /health`)**:
   - Lightweight: returns `{"status":"ok"}` immediately.
   - Zero database, FFO, or Ollama I/O.
   - Intended for container orchestrator liveness checks (Docker `HEALTHCHECK`, Kubernetes `livenessProbe`).

2. **Readiness Probe (`GET /ready` & `GET /health/ready`)**:
   - Standard mode (`GET /ready`): validates PostgreSQL connectivity (`SELECT 1`).
     - Returns 200 `{"status": "ready", "database": "connected"}` or 503 `{"status": "not_ready", "database": "disconnected"}`.
   - Detailed mode (`GET /ready?detailed=true`):
     - Validates Database (`SELECT 1`).
     - Validates FFO Corpus integrity (memoized static index and digest verification).
     - Validates Ollama Reasoning subsystem (or reports `"disabled"` when `FANSIVIBE_DISABLE_REASONING=true`).
     - Returns:
       ```json
       {
         "status": "ready",
         "database": "connected",
         "checks": {
           "database": "ok",
           "ffo_corpus": "ok",
           "reasoning": "ok",
           "reasoning_model": "qwen2.5vl:3b"
         }
       }
       ```
   - If database or corpus check fails, responds with HTTP 503. If reasoning is offline while core DB is healthy, responds with HTTP 200 `{"status": "ready_degraded"}` so non-AI traffic is not blocked.

---

## 4. Cascading Timeout Hierarchy — [REPO + INFRA]

To prevent orphaned backend processes, socket hangs, and premature client cancellations, timeouts strictly adhere to a cascading budget hierarchy:

```
[Layer 1] Ollama LLM Inference:       60.0s (connect: 5.0s, read: 55.0s)
            ↓
[Layer 2] Backend Handler Deadline:    65.0s (FastAPI usecase deadline -> 504 TIMEOUT)
            ↓
[Layer 3] Flutter Client Timeout:      75.0s (AppConfig.reasoningTimeout -> truthful retry UI)
            ↓
[Layer 4] Reverse Proxy Gateway (LB):  90.0s - 120.0s (proxy_read_timeout / gateway deadline)
            ↓
[Database] Pool Checkout Timeout:      30.0s (DATABASE_POOL_TIMEOUT_S)
```

Rules:
- The inner timeout (Ollama) expires *before* the backend handler deadline.
- The backend handler deadline expires *before* the client timeout.
- The client timeout expires *before* the reverse proxy drops the connection.
- Transport retries inside the adapter are bounded (`max_retries: 1`), and only trigger on retryable transport disconnects—never on model validation failures.

---

## 5. Resource Limits & Concurrency Protection — [REPO]

1. **Request Body Size & Length Bounds** (`backend/app/api/schemas/reasoning.py`):
   - `query`: `min_length=1`, `max_length=500` characters.
   - `context` string fields: `max_length=100` characters each.
   - `wardrobe_refs`: max 20 IDs.
   - `max_conclusions`: bounded between 1 and 5.

2. **In-Process Concurrency Limiter** (`backend/app/api/rate_limit.py`):
   - Concurrency semaphore (`ConcurrencyLimiter`) bounds simultaneous Ollama inference requests per container instance (default: 2).
   - If all slots are busy and a 1.0s acquire timeout expires, the request is rejected immediately with HTTP 429 `RATE_LIMITED` and `details: {"retry_after": 5}`.
   - Ollama is **never invoked** prior to concurrency admission, protecting GPU VRAM from out-of-memory crashes.

3. **Per-IP Rate Limiting**:
   - In-process sliding-window rate limit on `POST /v1/reasoning` (default: 30 requests/minute per IP).
   - Exceeding the rate limit returns HTTP 429 with truthful `retry_after`.
   - *Architecture note*: This is single-process memory tracking. In multi-replica deployments with >1 backend container, edge enforcement (Cloudflare / Nginx WAF / Redis-backed limiter) should be provisioned.

---

## 6. Input Handling & Contract Integrity — [REPO]

- User queries are **never silently rewritten or mutated**. Fashion terminology, casing, punctuation, and FFO references are preserved exactly as submitted.
- Input validation:
  - If a query contains unpermitted ASCII control characters (e.g. `\x00`–`\x1F` outside standard whitespace `\n`, `\r`, `\t`), the API rejects the request with HTTP 422 `VALIDATION_ERROR`.
  - Empty or whitespace-only queries are rejected with HTTP 422.

---

## 7. Logging & Observability — [REPO]

1. **Correlation IDs (`X-Request-Id`)**:
   - `security_and_correlation_headers` middleware extracts incoming `X-Request-Id` or generates a UUID.
   - Attached to request state, passed to error bodies, and returned on every response header.

2. **Structured Reasoning Telemetry**:
   - On completion of every query, a structured log entry is emitted:
     ```
     Reasoning query completed [req_id=...] query_len=14 intent=explain conclusions=3 confidence=high latency_ms=1240.5
     ```
   - **Privacy Redaction Guarantee**:
     - Query text is NOT logged (only `query_len`).
     - Raw Ollama model output is NEVER logged.
     - User images, base64 strings, and biometric data are NEVER logged.
     - Passwords, Bearer tokens, and database credentials are automatically scrubbed via regex sanitization.

---

## 8. Security & Headers — [REPO]

1. **Security Headers Middleware**:
   Applied to all responses:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` (scoped to API responses)
   - In production (`is_production=True`): `Strict-Transport-Security: max-age=31536000; includeSubDomains`

2. **CORS Restrictions**:
   - Configured via `FANSIVIBE_CORS_ORIGINS`.
   - In production, wildcard `*` origins combined with `allow_credentials=True` are rejected at startup by settings validation.

---

## 9. Retry Behavior & Policy — [REPO]

Reasoning requests are expensive. The client and backend strictly follow these retry policies:

- **HTTP 422 (Contract / Validation Error)**: NEVER retry automatically.
- **HTTP 502 (Malformed Model Output)**: NEVER retry automatically. Surface failure with manual retry button.
- **HTTP 429 (Rate Limited / Concurrency Full)**: Respect `retry_after` hint; client waits before retrying.
- **HTTP 503 (AI Unavailable / Degraded)**: Surface retryable error to user with retry option.
- **HTTP 504 (Timeout)**: Surface timeout message and allow explicit user retry.
- **Network / Socket Error**: Surface network failure and allow explicit user retry.

---

## 10. Flutter Production Configuration — [REPO]

Compile-time parameters for release builds:

```bash
flutter build appbundle \
  --dart-define=PRODUCTION=true \
  --dart-define=ASSISTANT_BASE_URL=https://<your-backend-host> \
  --dart-define=REASONING_TIMEOUT_S=75
```

- In production (`PRODUCTION=true`), `AppConfig.validateOrThrow()` refuses to start if `ASSISTANT_BASE_URL` is missing, contains `localhost`, or uses cleartext HTTP (`http://`).
- `KnowledgeClient` uses `AppConfig.reasoningTimeout` (75s) and transmits `X-Request-Id` correlation headers on every reasoning request.
- Handles HTTP 429 by displaying truthful `retry_after` cooldown hints.

---

## 11. Post-Deployment Smoke Tests — [INFRA Runbook]

After deploying to staging/production, execute these verification steps:

1. **Liveness Probe**:
   `GET /health` → 200 `{"status":"ok"}` (< 5ms).
2. **Readiness Probe**:
   `GET /ready` → 200 `{"status":"ready", "database":"connected"}`.
   `GET /ready?detailed=true` → 200 with checks for `database`, `ffo_corpus`, and `reasoning`.
3. **Security Headers**:
   `curl -I https://<host>/health` verifies `X-Content-Type-Options`, `X-Frame-Options`, and `X-Request-Id`.
4. **Live Reasoning Smoke Category Checks** (`POST /v1/reasoning`):
   - Category 1 (Normal fashion query): `"what is denim"` → 200 OK with admitted conclusions.
   - Category 2 (Comparison query): `"cotton vs linen"` → 200 OK.
   - Category 3 (Supported styling query): `"white sneakers"` → 200 OK.
   - Category 4 (Insufficient evidence query): `"kimono sizing"` → 502 fail-closed contract response.
   - Category 5 (Unsupported info query): `"current price of white sneakers"` → 502 fail-closed contract response.
5. **Rate Limit / Concurrency Verification**:
   - Send burst requests to verify 429 `RATE_LIMITED` with `Retry-After: 5` when concurrency limit is saturated.

---

## 12. Troubleshooting & Operational Recovery

| Symptom | Probable Cause | Action |
|---|---|---|
| `/ready` returns 503 `database: disconnected` | Postgres unreachable or connection pool exhausted | Check Postgres host, credentials in `DATABASE_URL`, and pool size (`DATABASE_POOL_SIZE`). |
| `/ready` reports `reasoning: unavailable` | Ollama service is stopped or unreachable | Check if Ollama process is running at `FANSIVIBE_OLLAMA_BASE_URL`. |
| `/ready` reports `reasoning: model_missing` | Required model not pulled into Ollama | Run `ollama pull qwen2.5vl:3b` on the Ollama host. |
| Reasoning queries return 504 `TIMEOUT` | Model inference taking > 60s (CPU inference or heavy GPU contention) | Verify GPU acceleration in Ollama (`ollama ps`), increase `FANSIVIBE_OLLAMA_TIMEOUT` and Flutter timeout. |
| Reasoning queries return 429 `RATE_LIMITED` | Concurrency limit (2) saturated or IP rate limit exceeded | Increase `FANSIVIBE_REASONING_CONCURRENCY_LIMIT` if GPU VRAM allows, or scale backend replicas. |
| Cold queries take ~15s, warm queries take ~1.5s | Ollama unloaded model from VRAM | Set `FANSIVIBE_REASONING_KEEP_ALIVE=-1` or `"30m"` to prevent unloading. |
| Scans or reasoning disabled intentionally | Maintenance or degraded operation | Set `FANSIVIBE_DISABLE_REASONING=true`. API returns 503 AI_FAILURE and `/ready` reports `"reasoning": "disabled"`. |

---

## 13. Cloud Deployment Preparation (Phase 4B)

Provider-neutral. No cloud provider is specified in this repo; the compose
topology runs on any host with Docker + NVIDIA GPU for the Ollama node.

### 13.1 Topology & Ollama placement

`Flutter → HTTPS → nginx (80/443, canary split) → FastAPI primary/canary → Postgres 16 → Ollama (dedicated GPU node, `qwen2.5vl:3b`)`.
Ollama is NOT published: no `ports:` on `ollama-prod`, reachable only over
`fansivibe-prod-network` as `http://ollama-prod:11434`. Point
`FANSIVIBE_OLLAMA_BASE_URL` and `FANSIVIBE_VISION_HOST` at that internal name
(never localhost, never public). GPU floor: 4 GB VRAM resident for
`qwen2.5vl:3b` Q4 (`ollama ps` must list it; digest `fb90415c…`).

### 13.2 Secrets (all out-of-band, never committed)

- Create `backend/.env.production` ONLY on the deploy host (or inject via
  the platform secret manager: env vars, Docker secrets, or mounted volume).
  Template: `backend/.env.production.example` (placeholders only).
- Postgres password: prefer `POSTGRES_PASSWORD_FILE: /run/secrets/db_password`
  (already wired) over env. JWT secret: ≥32 chars random, platform-managed.
- Verified: no secrets in `Dockerfile`/images (source + requirements only,
  non-root `appuser`), no secrets in Flutter source (dart-define defaults are
  `dev`/localhost and prod builds fail fast without explicit values), no
  secrets in logs (`errors.scrub_message` redacts URLs/tokens) or error
  responses (frozen 12-category contract carries no payload data).
- Residual: `.env.staging` on local disk holds dev-format values and is
  git-ignored — rotate iff ever copied off-disk.

### 13.3 TLS / domain (owner decision required)

1. Owner provides domain + DNS A record → set `server_name` in
   `deploy/nginx/production.conf` (currently `fansivibe.com` placeholders).
2. Provision certs into `deploy/tls/` as `fullchain.pem` + `privkey.pem`
   (Let's Encrypt/certbot or platform ACM — never commit `privkey.pem`).
3. HTTP→HTTPS 301, HSTS preload, and TLSv1.2+ cipher floor are already
   configured. CORS origins must be replaced with the real `https://` app
   origin. TLS is NOT complete until a real cert + domain serve traffic.

### 13.4 Database

- Startup runs `alembic upgrade head` (forward-only, non-destructive; all 21
  revisions ship `downgrade()` for per-step retreat). Rehearsed on a
  disposable DB in Phase 4A (clean through `0022` head). Pool defaults
  10/20/30s; append `?sslmode=require` to `DATABASE_URL` for managed Postgres.
- Backup: `pg_dump -Fc fansivibe_prod` on schedule; restore rehearsal:
  `pg_restore -d <fresh_db>` then `alembic current` must print the head.
- App rollback: redeploy prior image tag (migrations are additive; a
  retreating migration needs explicit `alembic downgrade -<n>` approval).

### 13.5 Observability & security posture

- Prometheus scrapes both backends internally (`deploy/prometheus/`
  `prometheus.yml`); port 9090 is NOT published; nginx restricts `/metrics`
  to private ranges. Docs endpoints 404 in prod; 2 MB body cap; vision
  uploads JPEG/PNG/WebP ≤20 MB; rate + concurrency limits per §5.
- PII/vision: image bytes are ephemeral (base64 in-flight only, never
  logged/persisted); metrics carry counts and latencies, never prompts,
  outputs, images, or tokens. No debug mode, no SSRF (Ollama host is
  operator-configured, never user-supplied).

### 13.6 Minimum owner decisions before first cloud deploy

1. Cloud/GPU host + domain name. 2. Secret injection mechanism.
3. Managed vs self-hosted Postgres (backup owner). 4. Cert provisioning path.
