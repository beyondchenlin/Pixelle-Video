#!/bin/bash
# Start Pixelle-Video Web UI

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PIXELLE_VIDEO_ROOT="$SCRIPT_DIR"
export PIXELLE_VIDEO_RUNTIME_ROOT="$SCRIPT_DIR/_runtime"
export TMP="$PIXELLE_VIDEO_RUNTIME_ROOT/tmp"
export TEMP="$PIXELLE_VIDEO_RUNTIME_ROOT/tmp"
export TMPDIR="$PIXELLE_VIDEO_RUNTIME_ROOT/tmp"
export UV_CACHE_DIR="$PIXELLE_VIDEO_RUNTIME_ROOT/uv-cache"
export RUFF_CACHE_DIR="$PIXELLE_VIDEO_RUNTIME_ROOT/ruff-cache"

mkdir -p "$PIXELLE_VIDEO_RUNTIME_ROOT" "$TMP" "$UV_CACHE_DIR" "$RUFF_CACHE_DIR"
: "${PIXELLE_API_PORT:=8001}"
: "${PIXELLE_API_BASE_URL:=http://localhost:${PIXELLE_API_PORT}/api}"
export PIXELLE_API_PORT PIXELLE_API_BASE_URL

echo "Starting Pixelle-Video API..."
echo ""

uv run uvicorn api.app:app --host 127.0.0.1 --port "$PIXELLE_API_PORT" &
sleep 2

echo "Starting Pixelle-Video Web UI..."
echo ""

uv run streamlit run web/app.py
