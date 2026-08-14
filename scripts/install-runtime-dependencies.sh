#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
bridge_root="$repo_root/tools/hyperframes_bridge"

for required_path in \
  "$repo_root/uv.lock" \
  "$bridge_root/package-lock.json" \
  "$bridge_root/browser_integrity.json"; do
  if [ ! -f "$required_path" ]; then
    echo "Required lock file not found: $required_path" >&2
    exit 1
  fi
done

for command_name in uv node npm; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 1
  fi
done

node_version=$(node --version)
node_major=$(printf '%s' "$node_version" | sed -n 's/^v\([0-9][0-9]*\)\.\([0-9][0-9]*\)\..*/\1/p')
node_minor=$(printf '%s' "$node_version" | sed -n 's/^v\([0-9][0-9]*\)\.\([0-9][0-9]*\)\..*/\2/p')
if [ -z "$node_major" ] || [ -z "$node_minor" ]; then
  echo "Unable to determine Node.js version: $node_version" >&2
  exit 1
fi
if [ "$node_major" -lt 22 ] || { [ "$node_major" -eq 22 ] && [ "$node_minor" -lt 12 ]; }; then
  echo "Node.js 22.12.0 or newer is required; found $node_version" >&2
  exit 1
fi

export PUPPETEER_CACHE_DIR="$bridge_root/.cache/puppeteer"
export PUPPETEER_SKIP_DOWNLOAD=true
export PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD=true
export PIXELLE_REQUIRE_PINNED_BROWSER=true
unset PUPPETEER_EXECUTABLE_PATH PRODUCER_HEADLESS_SHELL_PATH

cd "$repo_root"
uv sync --frozen
npm ci --omit=dev --prefix "$bridge_root"
(
  cd "$bridge_root"
  npm run browser:install
  npm run runtime:verify
)

printf '[OK] Runtime dependencies installed and HyperFrames bridge verified.\n'
