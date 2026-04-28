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

echo "Starting Pixelle-Video Web UI..."
echo ""

# Start Streamlit
uv run streamlit run web/app.py
