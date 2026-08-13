# Pixelle-Video Docker Image

FROM node:24.12.0-bookworm-slim AS hyperframes-runtime

WORKDIR /bridge
COPY tools/hyperframes_bridge/package.json tools/hyperframes_bridge/package-lock.json ./
ENV PUPPETEER_CACHE_DIR="/bridge/.cache/puppeteer" \
    PUPPETEER_SKIP_DOWNLOAD="true" \
    PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD="true"
RUN set -eu; \
    for attempt in 1 2 3; do \
        if npm ci --omit=dev; then exit 0; fi; \
        if [ "$attempt" -eq 3 ]; then exit 1; fi; \
        sleep $((attempt * 5)); \
    done
COPY tools/hyperframes_bridge/src ./src
RUN set -eu; \
    for attempt in 1 2 3; do \
        if node ./node_modules/puppeteer/lib/puppeteer/node/cli.js browsers install chrome; then exit 0; fi; \
        if [ "$attempt" -eq 3 ]; then exit 1; fi; \
        sleep $((attempt * 5)); \
    done
RUN node --input-type=module -e "const bridge = await import('./src/render.mjs'); await bridge.resolveBrowserExecutable()"

FROM ghcr.io/astral-sh/uv:0.10.7 AS uv-runtime
FROM python:3.11-slim

COPY --from=uv-runtime /uv /uvx /bin/
COPY --from=hyperframes-runtime /usr/local/bin/node /usr/local/bin/node

# Build arguments for mirror configuration
# USE_CN_MIRROR: whether to use China mirrors (true/false)
ARG USE_CN_MIRROR=false
ARG PIXELLE_UID=1000
ARG PIXELLE_GID=1000

# Set working directory
WORKDIR /app

# Replace apt sources with China mirrors if needed
# Debian 12 uses DEB822 format in /etc/apt/sources.list.d/debian.sources
RUN if [ "$USE_CN_MIRROR" = "true" ]; then \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    fi

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    printf '%s\n' \
        'Acquire::Retries "5";' \
        'Acquire::http::Timeout "60";' \
        'Acquire::https::Timeout "60";' \
        > /etc/apt/apt.conf.d/80-pixelle-network

# Install system dependencies
# - curl: for health checks and downloads
# - ffmpeg: for video/audio processing
# - fonts-noto-cjk: for CJK character support
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN uv --version

# Copy dependency files and source code for building
# Note: pixelle_video is needed for hatchling to build the package
COPY pyproject.toml uv.lock README.md ./
COPY pixelle_video ./pixelle_video
ENV PLAYWRIGHT_BROWSERS_PATH="/app/tools/playwright" \
    PUPPETEER_CACHE_DIR="/app/tools/hyperframes_bridge/.cache/puppeteer"

# Create virtual environment and install dependencies
# Use -i flag to specify mirror when USE_CN_MIRROR=true
RUN export UV_HTTP_TIMEOUT=300 && \
    if [ "$USE_CN_MIRROR" = "true" ]; then \
        uv sync --frozen --no-dev --index-url https://pypi.tuna.tsinghua.edu.cn/simple; \
    else \
        uv sync --frozen --no-dev; \
    fi && \
    uv run playwright install --with-deps chromium

COPY --from=hyperframes-runtime /bridge ./tools/hyperframes_bridge

# Copy rest of application code
COPY api ./api
COPY web ./web
COPY bgm ./bgm
COPY templates ./templates
COPY workflows ./workflows
COPY resources ./resources
COPY docs/images ./docs/images
COPY docs/FAQ*.md ./docs/

ENV PIXELLE_VIDEO_ROOT="/app" \
    PIXELLE_VIDEO_RUNTIME_ROOT="/app/_runtime" \
    TMP="/app/_runtime/tmp" \
    TEMP="/app/_runtime/tmp" \
    TMPDIR="/app/_runtime/tmp" \
    UV_CACHE_DIR="/app/_runtime/uv-cache" \
    RUFF_CACHE_DIR="/app/_runtime/ruff-cache"

# Create persistent output/data directories and runtime workspace.
RUN mkdir -p \
    /app/output \
    /app/data \
    "$TMP" \
    "$UV_CACHE_DIR" \
    "$RUFF_CACHE_DIR" && \
    groupadd --gid "$PIXELLE_GID" pixelle && \
    useradd --uid "$PIXELLE_UID" --gid "$PIXELLE_GID" --create-home pixelle && \
    chown -R pixelle:pixelle /app

USER pixelle

RUN cd tools/hyperframes_bridge && \
    node --input-type=module -e "const bridge = await import('./src/render.mjs'); await bridge.resolveBrowserExecutable()"

# Expose ports
# 8000: API service
# 8501: Web UI service
EXPOSE 8000 8501

# Default command (can be overridden in docker-compose)
CMD ["uv", "run", "python", "api/app.py"]
