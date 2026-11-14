# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS runtime

ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid "$APP_GID" app \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --create-home --shell /usr/sbin/nologin app

COPY --from=builder --chown=$APP_UID:$APP_GID /app /app

# Camoufox keeps its browser, GeoIP database and fingerprint model under
# $XDG_CACHE_HOME/camoufox; outside $HOME, which is a tmpfs at runtime.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/opt/cache

# Headless fallback for blocked pages: Camoufox (pinned build) plus Firefox's system
# libraries. The build ships ~2 GB of fonts, which its fingerprints need. Camoufox writes a
# per-OS fontconfig file into its cache dir on first launch; generating it here lets the
# root filesystem stay read-only.
RUN playwright install-deps firefox \
    && camoufox set official/stable/158.0.1-beta.41 \
    && camoufox fetch \
    && python -c "from wheel_n_deal.browser import CAMOUFOX_OPTIONS as o; from camoufox.utils import launch_options; launch_options(os=o['os'], headless=True)" \
    && chmod -R a+rX /opt/cache \
    && rm -rf /var/lib/apt/lists/* /tmp/*

USER app
WORKDIR /app

# The app touches /data/heartbeat every 30s (config data_dir must be /data).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
    CMD python -c "import os, sys, time; sys.exit(time.time() - os.path.getmtime('/data/heartbeat') > 180)"

CMD ["wheel-n-deal", "--config", "/config/config.yaml"]
