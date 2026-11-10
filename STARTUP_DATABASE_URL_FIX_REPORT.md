# Fansivibe Startup Failure: Database URL & Dialect Driver Fix Report

## 1. Exact Root Cause

The startup failure (`sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:driver`) stemmed from a three-part configuration flaw:

1. **Premature Migration Execution in `start.sh`:**
   `start.sh` executed `.venv/bin/alembic upgrade head` at step `[3/4]` before sourcing `backend/.env` (which occurred at line 40). Because the shell environment did not export `DATABASE_URL`, Alembic started with `os.getenv("DATABASE_URL")` evaluated as `None`.
2. **Template Priority Fallback in `backend/alembic/env.py`:**
   In `alembic/env.py`, `runtime_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or DATABASE_URL` evaluated `config.get_main_option("sqlalchemy.url")` ahead of the application's authoritative `DATABASE_URL` imported from `app.infrastructure.db.session`.
3. **Unresolved Placeholder in `backend/alembic.ini`:**
   `alembic.ini` retained the generic template line `sqlalchemy.url = driver://user:pass@localhost/dbname`. When `os.getenv("DATABASE_URL")` was unset, Alembic adopted this truthy string, which SQLAlchemy attempted to load as the `driver` dialect, crashing before any network or connection attempt.

---

## 2. Exact Files Modified

1. **`backend/alembic.ini`**
   - Cleared the template placeholder on line 89 (`sqlalchemy.url = `) and added explanatory commentary that URLs are resolved dynamically.
2. **`backend/alembic/env.py`**
   - Implemented `_is_placeholder(url)` to detect and reject placeholders (`driver://`, `user:pass@localhost/dbname`, empty strings).
   - Implemented `_resolve_database_url()` establishing authoritative resolution:
     1. Environment variable `DATABASE_URL` (if non-placeholder).
     2. Caller-specified `config.get_main_option("sqlalchemy.url")` (if explicitly set, e.g., in test runners, and non-placeholder).
     3. Application authoritative `DATABASE_URL` from `app.infrastructure.db.session`.
     4. Raises a descriptive `ValueError` if no valid URL is configured or if an unresolved placeholder is encountered.
3. **`backend/app/config/settings.py`**
   - Added `@field_validator("database_url", mode="before")` to `Settings`, ensuring empty strings and unresolved placeholder schemes (`driver://`, `user:pass@localhost/dbname`) fail validation immediately.
4. **`start.sh`**
   - Relocated sourcing of `$BACKEND/.env` to the top of the script (immediately after `BACKEND="$ROOT/backend"`), ensuring that Docker checks, Alembic migrations, and Uvicorn share the exact same authoritative environment.
5. **`backend/tests/test_settings.py`**
   - Added unit test suite `TestDatabaseUrlSettings` (5 test cases) covering default validity, empty string rejection, whitespace rejection, driver placeholder rejection, and template placeholder rejection.

---

## 3. Before/After Configuration Behavior (Secrets Redacted)

### Before
- **`start.sh`:** Sourced `.env` at line 40; Alembic executed at line 19 without `DATABASE_URL` in environment.
- **`backend/alembic.ini`:** `sqlalchemy.url = driver://user:pass@localhost/dbname`
- **`backend/alembic/env.py`:** Evaluated `config.get_main_option("sqlalchemy.url")` before `DATABASE_URL` from session/settings without placeholder filtering.
- **Result:** URL evaluated to `driver://user:pass@localhost/dbname`, causing `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:driver`.

### After
- **`start.sh`:** Sources `$BACKEND/.env` before step `[1/4]`; exports authoritative environment to all subshells.
- **`backend/alembic.ini`:** `sqlalchemy.url = ` (blank, dynamic resolution).
- **`backend/alembic/env.py`:** Detects placeholders; rejects `driver://` and template strings; falls back to authoritative `DATABASE_URL` from application settings; validates URL before engine initialization.
- **`backend/app/config/settings.py`:** Validates `database_url` field, rejecting placeholders early at configuration construction.
- **Result:**
  - Sanitized URL Scheme: `postgresql+psycopg`
  - Host: `localhost:5432`
  - Target Database: `fansivibe`
  - Engine construction succeeds: `Engine(postgresql+psycopg://fansivibe:***@localhost:5432/fansivibe)`
  - Alembic commands execute cleanly against PostgreSQL.

---

## 4. PostgreSQL Driver Detected

- **Installed in `backend/.venv`:** `psycopg` 3.3.4, `psycopg-binary` 3.3.4, `SQLAlchemy` 2.0.52.
- **Dialect Class Loaded:** `<class 'sqlalchemy.dialects.postgresql.psycopg.PGDialect_psycopg'>`.
- **Verdict:** Driver is correctly installed, loaded, and supported without package installations or upgrades.

---

## 5. Environment-Loading Behavior

- **Root `.env`:** Confirmed absent.
- **`backend/.env`:** Confirmed present and sourced at startup by `start.sh`.
- **Subshell Export:** `set -a; source "$BACKEND/.env"; set +a` exports all variables into the process tree prior to database readiness checks and migration execution.

---

## 6. SQLAlchemy Engine Construction Result

- Engine successfully constructed via `create_engine(DATABASE_URL)` in `app.infrastructure.db.session`.
- Connection pool parameters preserved:
  - `pool_size`: 5
  - `max_overflow`: 10
  - `pool_timeout`: 30.0s
  - `pool_recycle`: 1800s
  - `pool_pre_ping`: True

---

## 7. PostgreSQL Connectivity Result

- Direct connectivity verified via `engine.connect()`:
  - Query executed: `SELECT 1`
  - Result: `1` (Success)
- Docker container `fansivibe-postgres18` confirmed healthy and accepting connections.

---

## 8. Current Database Alembic Revision & Repository Head

- **Current Database Revision (`fansivibe`):** `0032` (verified via `SELECT version_num FROM alembic_version;` and `alembic current`).
- **Current Test Database Revision (`fansivibe_test`):** `0032`.
- **Repository Migration Head:** `0036` (`0036_media_upload_lease_token.py`).
- **Discrepancy:** The database is at `0032`, while repository head is `0036`.
  In accordance with safety constraints and project technical debt DEBT-01, **no migrations were executed against the shared development database**.

---

## 9. Tests Executed and Actual Results

1. **`backend/tests/test_settings.py`:**
   - 17 passed in 0.81s (12 existing tests + 5 new database URL validation tests).
2. **`backend/tests/test_docker_entrypoint.py`:**
   - 8 passed in 0.74s.
3. **`backend/tests/test_production_hardening.py`:**
   - 34 passed in 0.99s.
4. **`backend/tests/test_storage_config.py`:**
   - 16 passed in 0.78s.
5. **`backend/tests/test_p1_1_outfit_swap.py`:**
   - 21 passed in 0.93s.
6. **`backend/tests/test_db_session.py`:**
   - 24 skipped cleanly (safe guard when `FANSIVIBE_TEST_DATABASE_URL` is unset).
7. **Alembic CLI Diagnostics:**
   - `.venv/bin/alembic current` executed cleanly, reporting `0032`.
   - `.venv/bin/alembic heads` executed cleanly, reporting `0036 (head)`.
   - Negative test with `DATABASE_URL="driver://test"` verified immediate fail-closed `ValidationError`.
   - Negative test with `DATABASE_URL=""` verified immediate fail-closed `ValidationError`.
8. **Static Verification:**
   - `python3 -m py_compile` 100% clean across all modified files.
   - `git diff --check` 100% clean (zero whitespace errors).

---

## 10. Database State & Migration Invariants

- **Were migrations executed?** No. `alembic upgrade head` was intentionally not executed on the shared database `fansivibe`.
- **Did database data or migration state change?** No. `fansivibe` and `fansivibe_test` remain strictly at revision `0032`.
- **Git State:** All pre-existing untracked and uncommitted files from previous milestones strictly preserved. Zero commits or pushes performed.

---

## 11. Remaining Risks

1. **Database Revision Discrepancy (DEBT-01):**
   The shared development database `fansivibe` is at revision `0032`, while the codebase contains migrations up to `0036` (`0033_media_upload_idempotency`, `0034_media_upload_completion`, `0035_media_upload_lease`, `0036_media_upload_lease_token`).
   Because `start.sh` executes `.venv/bin/alembic upgrade head`, running `start.sh` directly will apply migrations 0033–0036 to `fansivibe`. Upgrading `fansivibe` from 0032 to 0036 should only be executed once migration impact is explicitly reviewed and authorized.

---

## 12. Final Decision

**CONFIGURATION FIXED, DATABASE MIGRATION STILL PENDING**
