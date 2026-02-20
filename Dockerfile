FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY index.html .

# ------------------------------------------------------------------
# Unraid Community Applications labels
# These are read by the Unraid CA plugin to auto-populate the
# container template and show the app in the Unraid app directory.
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

# config.json and the groupings output dir are mounted at runtime.
# See docker-compose.yml or the Unraid template for example mounts.
CMD ["python", "app.py"]
