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
: "${PIXELLE_API_PORT:=8888}"
: "${PIXELLE_API_BASE_URL:=http://localhost:${PIXELLE_API_PORT}/api}"
export PIXELLE_API_PORT PIXELLE_API_BASE_URL

if [[ -z "${PRODUCER_HEADLESS_SHELL_PATH:-}" ]]; then
    for browser_name in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge msedge; do
        if browser_path="$(command -v "$browser_name" 2>/dev/null)"; then
            export PRODUCER_HEADLESS_SHELL_PATH="$browser_path"
            break
        fi
    done
fi

if [[ -z "${PRODUCER_HEADLESS_SHELL_PATH:-}" ]]; then
    for browser_path in \
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
        "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
        if [[ -x "$browser_path" ]]; then
            export PRODUCER_HEADLESS_SHELL_PATH="$browser_path"
            break
        fi
    done
fi

if [[ -n "${PRODUCER_HEADLESS_SHELL_PATH:-}" ]]; then
    echo "Using browser: $PRODUCER_HEADLESS_SHELL_PATH"
fi

echo "Starting Pixelle-Video API..."
echo ""

uv run uvicorn api.app:app --host 127.0.0.1 --port "$PIXELLE_API_PORT" &
sleep 2

echo "Starting Pixelle-Video Web UI..."
echo ""

uv run streamlit run web/app.py
