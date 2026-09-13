#!/usr/bin/env bash
set -e

echo "==> Running Alembic migrations to head..."
alembic upgrade head

echo "==> Starting Fansivibe backend service..."
# 21.2 — concurrency strategy: the container stays single-worker by
# default (safe on small instances; scale horizontally with replicas
# behind the reverse proxy / load balancer). Set UVICORN_WORKERS>1
# only on larger instances. Non-numeric values fail safe to 1.
WORKERS="${UVICORN_WORKERS:-1}"
if ! [[ "$WORKERS" =~ ^[0-9]+$ ]] || [ "$WORKERS" -lt 1 ]; then
  echo "==> WARNING: invalid UVICORN_WORKERS='$WORKERS'; falling back to 1."
  WORKERS=1
fi

echo "==> Starting Fansivibe backend service (workers=$WORKERS)..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "$WORKERS" --proxy-headers "$@"
