# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

Only the latest release receives security updates.

## Reporting a Vulnerability

If you discover a security vulnerability, please report it privately by emailing the maintainer or opening a [GitHub Security Advisory](https://github.com/entcheneric/jellyfin-auto-groupings/security/advisories/new).

Please **do not** open a public issue for security vulnerabilities.

### What to include

- A description of the vulnerability
- Steps to reproduce
- Affected versions
- Any potential impact

You should receive a response within 48 hours. If the vulnerability is confirmed, we will work on a fix and release it as soon as possible.

## Security Considerations

### API Keys

- Jellyfin API keys, Trakt client IDs, and TMDb API keys are stored in `config/config.json`.
- These values can also be set via environment variables (`JELLYFIN_API_KEY`, `TRAKT_CLIENT_ID`, `TMDB_API_KEY`, `MAL_CLIENT_ID`), which take precedence over the config file.
- The `config/` directory is excluded from Docker builds via `.dockerignore`.

### App Password

- Set the `APP_PASSWORD` environment variable to enable HTTP Basic Auth for the web UI.
- When enabled, authentication is required for **all** requests except the main UI page
  (`GET /`) and `/static/` assets, enforced via a Flask `before_request` handler.
- The SPA stores the password in `sessionStorage` and sends it on subsequent API calls.
- When `APP_PASSWORD` is **not** set, the application has no built-in authentication.
  Only run it on trusted networks or behind a reverse proxy that enforces access control.

### CSRF Protection

- All state-changing requests (POST, PUT, DELETE, PATCH) require the `X-Requested-With: XMLHttpRequest` header.
- This prevents simple cross-site request forgery attacks.

### Filesystem Access

- The filesystem browser is restricted to whitelisted roots (home directory, `/media`, `/mnt`).
- Symlinks are excluded from the browser to prevent path traversal.

### Docker

- The Docker image runs as a non-root user (`appuser`, UID 1000).
- Health checks are configured to detect unresponsive containers.
