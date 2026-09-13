# Fansivibe Production Deployment Runbook (Phase 21.2)

Target architecture:

```
PostgreSQL 16
    ↓
FastAPI Docker container (`backend/Dockerfile` + `entrypoint.sh`)
    ↓
HTTPS reverse proxy / load balancer (NOT in this repo — §6)
    ↓
Flutter Android application (release-signed, §14)
```

> Truthfulness note: this repository contains NO production domain, TLS
> certificate, PostgreSQL server, Ollama server, keystore, or secret.
> Every section below is labeled **[REPO]** (doable in this codebase,
> done where stated) or **[INFRA]** (must be provisioned out-of-band in
> Phase 21.3+). Nothing here claims a deployment exists.

## 1. PostgreSQL provisioning — [INFRA]

- Provision PostgreSQL 16 (managed service preferred).
- Create one database + one least-privilege role for the API. The role
  needs DDL (Alembic migrations run at container startup) — or run
  migrations from a separate migrate job with an owner role and grant
  the runtime role DML only.
- Connection string shape:
  `postgresql+psycopg://<user>:<password>@<host>:5432/<database>`
- The service refuses production startup with the dev default URL or
  any URL containing the dev credential (`fansivibe_dev`) — enforced
  in `app/config/settings.py`, tested in
  `tests/test_production_hardening.py`.

## 2. Database backup / PITR — [INFRA, REQUIRED before real users]

- Enable automated daily base backups + WAL archiving (PITR) on the
  managed Postgres (or `pgBackRest`/`WAL-G` self-hosted).
- Practice a restore to a scratch instance before launch.
- Document retention (e.g. 7–30 days) and who can trigger a restore.

## 3. Secret injection — [INFRA + REPO template]

- Required secrets (see `backend/.env.example` for shapes only):
  `DATABASE_URL`, `FANSIVIBE_AUTH_SECRET` (random, ≥ 32 chars).
- Inject via the platform secret manager (never bake into the image,
  never commit `.env` — both `.gitignore` files deny-list it).
- `FANSIVIBE_ALLOW_DEV_TOKEN` must stay `false` (production validator
  rejects `true`); `FANSIVIBE_ENABLE_DOCS` should stay `false`.

## 4. Docker build — [REPO]

```bash
docker build -t fansivibe-api:<tag> backend/
```

- Base `python:3.12-slim-bookworm`, non-root `appuser` (uid 10001).
- Production image installs ONLY `requirements-prod.txt` (exact pins;
  `pytest` never ships). `requirements.txt` is the dev/test env.
- `HEALTHCHECK` hits `/health` (liveness).

## 5. Alembic migration — [REPO procedure, INFRA execution]

- `entrypoint.sh` runs `alembic upgrade head` BEFORE `exec uvicorn`
  (PID-1 intact, `set -e` fails fast — tested in
  `tests/test_docker_entrypoint.py`).
- Single head today: `0021` (asserted in
  `tests/test_production_hardening.py::TestMigrationReadiness`).
- Never edit historical migrations without a proven correctness
  defect; never run `downgrade` against production data (§16).

## 6. HTTPS / TLS termination — [INFRA]

- Terminate TLS at the reverse proxy (nginx / Caddy / cloud LB);
  the app container serves plain HTTP on `PORT` (default 8000) with
  `--proxy-headers` so `request.url` reflects the external scheme.
- Redirect HTTP→HTTPS and HSTS at the proxy. The Flutter production
  build refuses non-HTTPS base URLs (`AppConfig.validateOrThrow`).

## 7. DNS — [INFRA]

- No production hostname exists yet. When one is chosen, point an
  `A`/`AAAA` (or `CNAME`) record at the proxy/LB and pass the public
  origin to the backend (`FANSIVIBE_CORS_ORIGINS`) and to Flutter
  (`--dart-define=ASSISTANT_BASE_URL=https://<host>`).

## 8. Health / readiness checks — [REPO]

- Liveness: `GET /health` → `{"status":"ok"}` (Docker HEALTHCHECK).
- Readiness: `GET /ready` (alias `/health/ready`) → 200
  `{"status":"ready"}` when Postgres answers `SELECT 1`, else 503.
  Wire the LB/replica readiness gate to `/ready`, NOT `/health`.

## 9. Rate limiting — [REPO local + INFRA edge]

- [REPO] In-process sliding-window guard on `POST /v1/auth/register`
  and `POST /v1/auth/login` (`app/api/rate_limit.py`): per-IP budget,
  truthful `429 RATE_LIMITED` with a `retry_after` hint, env-tunable
  (`FANSIVIBE_RATE_LIMIT_*`), fail-open, bounded memory.
- [INFRA] This is single-process counting. Phase 21.3 must add edge
  enforcement (reverse-proxy/WAF limits, and Redis-backed counting if
  running >1 replica) for assistant/chat, analysis, and write-heavy
  routes.

## 10. Logs — [REPO format + INFRA sink]

- [REPO] API error logs are sanitized (`app/api/errors.py` scrubs DB
  passwords, Bearer tokens, JWTs, credential params) and carry
  `X-Request-Id` on every error path; 5xx responses include
  `request_id` for correlation. Authorization headers are never logged.
- [INFRA] Ship container stdout to a log aggregator and define
  retention + access controls in Phase 21.3.

## 11. Crash reporting — [REPO abstraction + INFRA provider]

- [REPO] Flutter `CrashReportingService` dispatches sanitized reports
  (`ErrorSanitizer` redacts tokens, passwords, image bytes, user data;
  bounded at 50 recent reports) to registered `CrashReportSink`s.
- [INFRA] No provider is wired in (no fake monitoring): add a
  `CrashReportSink` implementation (Sentry/Crashlytics/equivalent) and
  register it at startup in Phase 21.3.

## 12. Ollama / vision provisioning — [INFRA, CONDITIONAL]

- No production Ollama server exists. If scans are enabled, provision
  a host with a vision-capable model, set `FANSIVIBE_VISION_HOST`,
  `FANSIVIBE_VISION_MODEL`, `FANSIVIBE_VISION_TIMEOUT_S` — connection
  or model failures then surface as typed terminal failures (never
  fake analysis).
- If vision stays off, set `FANSIVIBE_DISABLE_VISION=true`: scans
  report `analyzer_unavailable` (degraded, honest). Never hardcode a
  production Ollama IP/domain in the repo.

## 13. Flutter production dart-defines — [REPO contract]

```bash
flutter build appbundle \
  --dart-define=PRODUCTION=true \
  --dart-define=ASSISTANT_BASE_URL=https://<your-backend-host>
```

- `PRODUCTION=true` without an `https://` non-localhost URL fails fast
  at startup (`AppConfig.validateOrThrow`, called in `main()`).
  No production domain is hardcoded or invented.
- Auth tokens persist in platform secure storage (Android Keystore /
  iOS Keychain) with a one-time migration from legacy preferences;
  tests/dev fall back transparently (`SecureTokenStorage`).

## 14. Android signing — [INFRA artifact + REPO strictness]

- `android/app/build.gradle.kts` REQUIRES `key.properties` for strict
  release builds (`REQUIRE_RELEASE_SIGNING=true`, `CI=true`, or
  `-PprodRelease` fail instead of silently using debug keys); local
  QA builds without it fall back to debug signing with a warning.
- Generate the keystore OUT-OF-BAND
  (`keytool -genkeypair ...`), copy `android/key.properties.example`
  to `android/key.properties` with real values, and NEVER commit
  `key.properties`, `*.jks`, `*.keystore`, or `*.p12` (deny-listed in
  every `.gitignore`).

## 15. Rollback procedure — [INFRA run]

1. LB: shift traffic back to the previous image tag (keep N-1 tagged).
2. API: `docker run` previous tag (migrations are forward-only — §16).
3. Flutter: staged rollout halt + promote previous AAB in Play Console.
4. Verify `/ready`, smoke tests (§17), error-rate dashboards.

## 16. Database rollback warning — [INFRA discipline]

- Alembic downgrades are NOT a production rollback tool: a downgrade
  can destroy data written by the newer schema. Roll the **code**
  back (§15) while leaving the schema at head unless a forward-fix
  migration is authored, reviewed, and first replayed on a
  backup-restored copy.

## 17. Smoke tests — [INFRA run, REPO contracts]

After every deploy, against the public base URL:

1. `GET /health` → 200 `{"status":"ok"}`.
2. `GET /ready` → 200 `{"status":"ready"}`.
3. `POST /v1/auth/register` WITHOUT `Idempotency-Key` → 422
   (contract, not rate limiting).
4. Register → login → `GET /v1/users/me` → 200; logout → 204;
   reused token → 401 with `WWW-Authenticate: Bearer`.
5. `POST /v1/auth/social` → 502 (honest stub — §backlog).
6. Rapid register/login burst past the configured budget → truthful
   429 with `retry_after`.
7. Flutter release build: cold start → login → token survives restart
   (secure storage) → 401 expiry routes to entry without loops.
8. If vision enabled: one scan end-to-end; if disabled: scan reports
   unavailable (never a fabricated result).

## Product backlog (NOT built in 21.2 — needs owner approval)

- Social login providers (Google/Apple verification) — backend and
  client are honest stubs (422-shape/502, `providerUnavailable`).
- Account deletion / erasure pipeline (O-6, API-12) — no route mounted.
- JWT refresh endpoint (tokens live 1h; clients re-login today).
- Distributed rate limiting + WAF (see §9).
- Monitoring/log/crash sinks (see §10–11).
- PostgreSQL backups/PITR drills (see §2).
