# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Build stage — install dependencies into a virtual environment
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt requirements-dev.txt pyproject.toml README.md ./
COPY *.py ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# ---------------------------------------------------------------------------
# Final stage — copy only what is needed to run the application
# ---------------------------------------------------------------------------
FROM python:3.12-slim

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
      org.opencontainers.image.description="Create virtual Jellyfin libraries by grouping media via symlinks, filtered by genre, actor, studio, IMDb list, or Trakt list." \
      org.opencontainers.image.url="https://github.com/entcheneric/jellyfin-groupings" \
      org.opencontainers.image.source="https://github.com/entcheneric/jellyfin-groupings" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.authors="entcheneric" \
      net.unraid.docker.managed="dockerman" \
      net.unraid.docker.webui="http://[IP]:[PORT:5000]/" \
      net.unraid.docker.icon="https://raw.githubusercontent.com/entcheneric/jellyfin-groupings/main/unraid/jellyfin-groupings-icon.png"

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/')" || exit 1

USER appuser

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
