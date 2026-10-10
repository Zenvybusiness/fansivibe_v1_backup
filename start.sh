#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"

echo "=== Fansivibe startup ==="

echo "[1/4] Starting PostgreSQL..."
docker start fansivibe-postgres18 >/dev/null 2>&1 || true

echo "[2/4] Waiting for PostgreSQL..."
until docker exec fansivibe-postgres18 pg_isready -U fansivibe -d fansivibe >/dev/null 2>&1; do
    sleep 1
done

echo "[3/4] Applying database migrations..."
cd "$BACKEND"
.venv/bin/alembic upgrade head

echo "[4/4] Checking Ollama..."
if ! systemctl is-active --quiet ollama; then
    echo "Starting Ollama..."
    sudo systemctl start ollama
fi

if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null; then
    echo "ERROR: Ollama is not responding."
    exit 1
fi

if ! curl -sf http://127.0.0.1:11434/api/tags | grep -q 'qwen3-vl:4b-instruct'; then
    echo "ERROR: qwen3-vl:4b-instruct is not installed."
    exit 1
fi

echo
echo "=== Starting FastAPI ==="
set -a
source "$BACKEND/.env"
set +a

TAILSCALE_IP="$(tailscale ip -4)"
exec "$BACKEND/.venv/bin/uvicorn" app.main:app --host "$TAILSCALE_IP" --port 8000
