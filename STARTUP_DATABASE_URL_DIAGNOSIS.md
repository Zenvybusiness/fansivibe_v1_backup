# Fansivibe Startup Failure: Database URL & Dialect Driver Diagnosis

## 1. Executive Summary

During execution of `./start.sh`, startup halted at step `[3/4] Applying database migrations...` with the following exception:

```text
sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:driver
```

This read-only diagnosis traces the root cause of why Alembic received an invalid database URL containing the placeholder scheme `driver://` instead of the configured PostgreSQL connection string.

---

## 2. Root Cause Analysis

The failure is caused by a compound interaction between three components:

1. **Premature Migration Execution in `start.sh` (Line 18–19 vs. Line 39–41):**
   In `start.sh`, Alembic is invoked at step `[3/4]` (`cd "$BACKEND" && .venv/bin/alembic upgrade head`) **before** the backend environment file is loaded. Sourcing of `backend/.env` occurs at line 40 under `=== Starting FastAPI ===`. Consequently, when Alembic executes, `DATABASE_URL` is absent from the shell environment.

2. **Template Precedence Bug in `backend/alembic/env.py` (Lines 17–19):**
   Commit `79298c36` introduced the following fallback chain:
   ```python
   runtime_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or DATABASE_URL
   config.set_main_option("sqlalchemy.url", runtime_url)
   ```
   When `os.getenv("DATABASE_URL")` is unset, Python evaluates `config.get_main_option("sqlalchemy.url")`. Because `backend/alembic.ini` defines `sqlalchemy.url = driver://user:pass@localhost/dbname`, `config.get_main_option("sqlalchemy.url")` evaluates to a non-empty string (`"driver://..."`), which is truthy.
   Therefore, Python short-circuits and never evaluates `DATABASE_URL` (the authoritative configuration imported from `app.infrastructure.db.session`).

3. **Active Placeholder in `backend/alembic.ini` (Line 89):**
   `backend/alembic.ini` line 89 contains the unescaped template placeholder:
   ```ini
   sqlalchemy.url = driver://user:pass@localhost/dbname
   ```
   This placeholder is interpreted by SQLAlchemy as dialect `driver`, triggering `sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:driver` during engine construction.

---

## 3. Detailed Inspection of Configuration Sources

### 3.1 `start.sh`
- **Location:** `start.sh`
- **Behavior:**
  - Lines 9–15: Starts Docker container `fansivibe-postgres18` and verifies readiness with `pg_isready`.
  - Lines 17–19: Changes directory to `$BACKEND` and executes `.venv/bin/alembic upgrade head`.
  - Lines 39–41: Sources `$BACKEND/.env` (`set -a; source "$BACKEND/.env"; set +a`).
- **Finding:** Environment variables from `$BACKEND/.env` are not loaded into the process when migrations are executed at line 19.

### 3.2 `backend/alembic.ini`
- **Location:** `backend/alembic.ini`
- **Line 89:**
  ```ini
  sqlalchemy.url = driver://user:pass@localhost/dbname
  ```
- **Finding:** A generic template placeholder is present. When parsed by Alembic's `Config`, it populates option `sqlalchemy.url` with the string `"driver://user:pass@localhost/dbname"`.

### 3.3 `backend/alembic/env.py`
- **Location:** `backend/alembic/env.py`
- **Lines 8–9:**
  ```python
  from app.infrastructure.db.session import DATABASE_URL, Base
  from app.infrastructure.db import models  # noqa
  ```
- **Lines 17–19:**
  ```python
  # Override the URL with the runtime value from the environment if provided.
  runtime_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or DATABASE_URL
  config.set_main_option("sqlalchemy.url", runtime_url)
  ```
- **Finding:** The fallback priority improperly allows the placeholder template from `alembic.ini` to take precedence over the application's authoritative `DATABASE_URL` from `app.infrastructure.db.session`. Furthermore, no validation exists to detect or reject placeholder schemes (`driver://`).

### 3.4 Environment Files (`.env`)
- **Root `.env`:** Not present (`ls: cannot access '.env': No such file or directory`).
- **`backend/.env`:** Present (`-rw------- 1 tony tony 388`).
- **Sanitized `backend/.env` configuration:**
  - Scheme: `postgresql+psycopg`
  - Host: `localhost`
  - Port: `5432`
  - Database: `fansivibe`
  - Credentials: Confirmed present and redacted.

### 3.5 Application Database Configuration (`session.py` & `settings.py`)
- **`backend/app/infrastructure/db/session.py`:**
  - Lines 20–21:
    ```python
    _settings = get_settings()
    DATABASE_URL = _settings.database_url
    ```
- **`backend/app/config/settings.py`:**
  - Lines 20–22:
    ```python
    _DEFAULT_DATABASE_URL = (
        "postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe"
    )
    ```
  - Line 34:
    ```python
    database_url: str = Field(default=_DEFAULT_DATABASE_URL)
    ```
  - Pydantic Settings reads from `os.environ` or falls back to `_DEFAULT_DATABASE_URL`.
  - Both default and configured URLs target PostgreSQL using the `postgresql+psycopg` dialect driver.

---

## 4. Installed Driver & Environment Verification

- **Virtual Environment:** `backend/.venv` (Python 3.12.3)
- **Installed PostgreSQL Packages:**
  - `psycopg` version 3.3.4
  - `psycopg-binary` version 3.3.4
  - `SQLAlchemy` version 2.0.52
- **Driver Verification:**
  - Dialect `postgresql.psycopg` loads successfully via `sqlalchemy.dialects.registry.load("postgresql.psycopg")`.
  - PostgreSQL driver: `<class 'sqlalchemy.dialects.postgresql.psycopg.PGDialect_psycopg'>`.

---

## 5. PostgreSQL Instance & Migration State

- **Docker Container:** `fansivibe-postgres18` is running and healthy (`pg_isready` reports accepting connections).
- **Target Database:** `fansivibe`
- **Current Database Revision:** `0032` (verified via `SELECT version_num FROM alembic_version;`).
- **Repository Migration Head:** `0036` (`0036_media_upload_lease_token.py`).
- **Revision Discrepancy:** The database is at revision `0032` while the repository head is `0036`.
  In accordance with safety constraints and project debt item DEBT-01, migrations must not be executed automatically on the shared development database.

---

## 6. Diagnosis Checklist Answers

| Diagnosis Question | Finding |
|---|---|
| **Which variable or configuration entry supplies Alembic's URL?** | `backend/alembic.ini` line 89 (`sqlalchemy.url = driver://...`), which erroneously intercepts the resolution in `alembic/env.py` line 18 before `DATABASE_URL` is reached. |
| **Whether `.env` is loaded before Alembic starts?** | No. In `start.sh`, `.env` is sourced at line 40, while Alembic is called at line 19. |
| **Whether `start.sh` changes directory or environment unexpectedly?** | `start.sh` changes to `backend`, but fails to export `.env` variables before running migrations. |
| **Whether Alembic overrides an environment-derived URL?** | If `DATABASE_URL` is in `os.environ`, it was honored; but if unset, `alembic.ini`'s template URL overrides `app.infrastructure.db.session.DATABASE_URL`. |
| **Whether a template value from `alembic.ini` is taking precedence?** | Yes. `config.get_main_option("sqlalchemy.url")` took precedence over `DATABASE_URL`. |
| **Whether the URL is being overwritten by an empty or incorrectly named variable?** | No; the variable name `DATABASE_URL` is correct, but it was unset in the subshell during step `[3/4]`. |
