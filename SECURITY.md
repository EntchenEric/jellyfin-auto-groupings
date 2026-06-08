# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | ✅ Yes             |
| < 1.x   | ❌ No              |

We recommend always running the latest published Docker image or building from the latest `main` commit.

## Reporting a Vulnerability

If you discover a security vulnerability in Jellyfin Groupings, please report it by opening a [GitHub Security Advisory](https://github.com/entcheneric/jellyfin-auto-groupings/security/advisories/new).

Do **not** open a public issue for security vulnerabilities.

We aim to acknowledge reports within 48 hours and will work on a fix as quickly as possible.

## Best Practices for Deployments

1. **Use environment variables for secrets** — API keys, passwords, and tokens set via `JELLYFIN_API_KEY`, `APP_PASSWORD`, etc. are preferred over storing them in `config.json`.
2. **Enable authentication** — Set `APP_PASSWORD` to enable HTTP Basic Auth for the web UI.
3. **Restrict network access** — Do not expose the web UI (port 5000) to the public internet without a VPN or reverse proxy with authentication.
4. **Run as non-root** — The Docker container runs as `appuser` (UID 1000) by default. Avoid running as root.
5. **Keep dependencies updated** — Regularly rebuild the Docker image to pick up the latest security patches.