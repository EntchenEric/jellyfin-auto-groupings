FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Copy application files
COPY . .

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

CMD ["python", "app.py"]
