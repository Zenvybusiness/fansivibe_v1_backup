"""P0-1 — Docker database migration startup (production-safe).

Verifies the production container ensures the database reaches Alembic head
before serving traffic:

- backend/entrypoint.sh runs `alembic upgrade head` before uvicorn
- the final process uses `exec` (proper PID 1 signal handling)
- migration failure aborts startup (set -e, no swallowed errors)
- backend/Dockerfile wires the entrypoint (ENTRYPOINT, COPY, chmod +x)
  and does not start uvicorn directly without migrations.

DB-free: pure file-content assertions, runs everywhere.
"""

from __future__ import annotations

import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ENTRYPOINT = BACKEND / "entrypoint.sh"
DOCKERFILE = BACKEND / "Dockerfile"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_entrypoint_exists():
    assert ENTRYPOINT.is_file(), "backend/entrypoint.sh must exist"


def test_entrypoint_runs_migrations_before_api():
    text = _read(ENTRYPOINT)
    assert "alembic upgrade head" in text
    mig_pos = text.index("alembic upgrade head")
    uv_pos = text.index("uvicorn")
    assert mig_pos < uv_pos, "migrations must run before uvicorn starts"


def test_entrypoint_uses_exec_for_uvicorn():
    text = _read(ENTRYPOINT)
    assert re.search(r"^exec\s+uvicorn\b", text, re.MULTILINE), (
        "final uvicorn process must use exec for PID 1 signal handling"
    )


def test_entrypoint_fails_fast_on_migration_error():
    text = _read(ENTRYPOINT)
    # set -e (or -eu/-euo pipefail) preserves non-zero exit when
    # `alembic upgrade head` fails, so the API never starts on a stale DB.
    assert re.search(r"^set\s+-e", text, re.MULTILINE), (
        "entrypoint must fail fast (set -e) when migrations fail"
    )
    # Migration failures must not be silently ignored.
    assert "|| true" not in text
    assert "|| :" not in text
    assert "or true" not in text.lower()


def test_dockerfile_wires_entrypoint():
    text = _read(DOCKERFILE)
    assert 'ENTRYPOINT ["/app/entrypoint.sh"]' in text
    assert "COPY entrypoint.sh" in text or "COPY ./entrypoint.sh" in text
    assert "chmod +x" in text and "entrypoint.sh" in text


def test_dockerfile_does_not_bypass_migrations():
    text = _read(DOCKERFILE)
    # The container must not start uvicorn directly as its main command
    # without going through the migration entrypoint.
    assert 'ENTRYPOINT ["/app/entrypoint.sh"]' in text
    assert not re.search(r'^CMD\s+\["uvicorn"', text, re.MULTILINE), (
        "Dockerfile must not CMD uvicorn directly; migrations run via ENTRYPOINT"
    )
