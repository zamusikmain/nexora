# Development and production deployment

Local reviewed stack: UI http://localhost:3300, API http://localhost:8800, PostgreSQL 127.0.0.1:55432. Existing `.env` uses those ports; do not overwrite it. Start the development stack with real antivirus:

```powershell
docker compose -f compose.yaml -f compose.security.yaml up -d --build
```

ClamAV initializes signatures before API starts. Plain `compose.yaml` uses an explicit development-only scanner bypass. UI upload status identifies that mode. Demo seed is allowed only in development and never overwrites existing passwords.

Production overlay (configuration/build verified, real HTTPS deployment NOT VERIFIED):

```powershell
docker compose -f compose.yaml -f compose.security.yaml -f compose.production.yaml config --quiet
docker compose -f compose.yaml -f compose.security.yaml -f compose.production.yaml up -d --build
```

Before the second command provide a real HTTPS WEB_ORIGIN, private DB credentials and HTTPS reverse proxy in your deployment environment. The reverse proxy must set X-Forwarded-For and be added to `TRUSTED_PROXIES` (for example `web,10.0.0.10`) for per-client login throttling. Do not use the local demo `.env` for production. Production API disables OpenAPI/debug docs, demo seed/password and scanner bypass. Separate `migrate` service must succeed before API starts. Prepare the initial administrator through an approved operator provisioning process; signup/invitation/OIDC setup is not implemented. Scan legacy versions before production cutover; see security.md.

API image has runtime/development/production targets. Only the development target migrates and seeds on startup; runtime/production images start uvicorn only, so a bare production image never runs Alembic under the runtime connection. Production excludes tests/pytest/httpx/mypy/ruff and runs uid10001; development includes verification tools. Frontend uses standalone runtime under the node user. Both graphs are lockfile-backed. Web/API/DB/ClamAV have health checks, persistent DB/private-file/signature volumes and loopback host port bindings. No external tunnel or public deployment was created. Avoid `down -v`; it destroys volumes.

These deployment controls do not complete pilot readiness: MFA/SSO, granular ACL, organization boundaries, verified reverse-proxy forwarding for rate limiting, least-privilege DB roles, TLS/secrets management, background jobs, observability/alerting and scale verification remain required for the intended enterprise scope.

Least-privilege PostgreSQL cutover is prepared and isolated-tested, but NOT applied to the existing stack. See `database-roles.md` for the explicit opt-in `compose.roles.yaml`, secrets, provisioning, rollback and verification. Existing startup commands above still use the administrator connection until approved cutover. Never enable the roles overlay before provisioning. Append it after the security/production overlays; it removes Alembic from API startup and uses a migrations-only service.
