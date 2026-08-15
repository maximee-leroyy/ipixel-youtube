# syntax=docker/dockerfile:1
#
# Image linux/amd64 + linux/arm64 (Pi 5), publiée sur
#   ghcr.io/maximee-leroyy/ipixel-youtube
#   nerdctl pull ghcr.io/maximee-leroyy/ipixel-youtube:latest
#
# BlueZ tourne dans le container (ou on réutilise celui du Pi via D-Bus).

ARG PYTHON_VERSION=3.13.7

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock README.md ./

# Dépendances seulement : le wheel hatch force-include youtube.png (absent du repo).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY assets ./assets

FROM python:${PYTHON_VERSION}-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libdbus-1-3 \
        dbus \
        bluez \
        rfkill \
    && rm -f /usr/share/dbus-1/system-services/org.bluez.service \
             /etc/dbus-1/system-services/org.bluez.service \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/assets /app/assets
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
COPY container/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    YOUTUBE_COOKIES=/app/cookies.txt

LABEL org.opencontainers.image.title="ipixel-youtube" \
      org.opencontainers.image.description="Live YouTube subscriber counter for iPixel Color 32×32" \
      org.opencontainers.image.source="https://github.com/maximee-leroyy/ipixel-youtube" \
      org.opencontainers.image.url="https://github.com/maximee-leroyy/ipixel-youtube" \
      org.opencontainers.image.licenses="MIT"

ENTRYPOINT ["/entrypoint.sh"]
