#!/usr/bin/env bash
# start.sh
# Used as the Render start command when you want to auto-seed on every deploy.
# Render sets DATABASE_URL automatically when linked to a Render Postgres instance.
#
# Usage: bash start.sh
# Or set as Start Command in Render: bash start.sh

set -e

if [ -f "profiles_seed.json" ]; then
    echo "[start] Seeding database..."
    python seed.py profiles_seed.json
else
    echo "[start] No profiles_seed.json found — skipping seed."
fi

echo "[start] Starting server..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
