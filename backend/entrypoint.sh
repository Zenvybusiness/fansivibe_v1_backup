#!/usr/bin/env bash
set -e

echo "==> Running Alembic migrations to head..."
alembic upgrade head

echo "==> Starting Fansivibe backend service..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers "$@"
