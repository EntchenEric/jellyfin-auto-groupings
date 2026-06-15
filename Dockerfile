# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Build stage — install dependencies into a virtual environment
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Only copy what pip needs — .py source files are not required to
# resolve dependencies.  The final layer copies everything anyway.
COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn && \
    # Verify key dependencies are importable
    python -c "import flask; import requests; import apscheduler"

# ---------------------------------------------------------------------------
# Final stage — copy only what is needed to run the application
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# Ensure Python logs are unbuffered for timely container log output
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application files (respects .dockerignore)
COPY . .

# Create a non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# ------------------------------------------------------------------
# Unraid Community Applications labels
# ------------------------------------------------------------------
LABEL org.opencontainers.image.title="Jellyfin Groupings" \
      org.opencontainers.image.description="Create virtual Jellyfin libraries by grouping media via symlinks, filtered by genre, actor, studio, year, or external lists (IMDb, Trakt, TMDb, Letterboxd, AniList, MyAnimeList)." \
      org.opencontainers.image.url="https://github.com/entcheneric/jellyfin-auto-groupings" \
      org.opencontainers.image.source="https://github.com/entcheneric/jellyfin-auto-groupings" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.authors="entcheneric" \
      net.unraid.docker.managed="dockerman" \
      net.unraid.docker.webui="http://[IP]:[PORT:5000]/" \
      net.unraid.docker.icon="https://raw.githubusercontent.com/entcheneric/jellyfin-auto-groupings/main/unraid/jellyfin-groupings-icon.png"

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:5000/api/health', timeout=3).raise_for_status()" || exit 1

USER appuser

# ------------------------------------------------------------------
# Gunicorn configuration — timeout is configurable via GUNICORN_TIMEOUT
# (default 120s) for deployments with slow API responses or large libraries.
# Worker count is configurable via GUNICORN_WORKERS (default 2) for
# multi-core hosts.
# ------------------------------------------------------------------
ENV GUNICORN_TIMEOUT=120
ENV GUNICORN_WORKERS=2

# shell entrypoint expands $GUNICORN_TIMEOUT and $GUNICORN_WORKERS at
# container start so environment variables can be overridden without
# rebuilding the image.
ENTRYPOINT ["/bin/sh", "-c", "exec gunicorn --bind 0.0.0.0:5000 --workers ${GUNICORN_WORKERS} --timeout ${GUNICORN_TIMEOUT} --preload --access-logfile - --error-logfile - app:app"]
