# NEXORA
Document management portfolio project; optional AI is future work. Current work: incremental enterprise development following the user’s 2026-10-07 request. The user explicitly authorized a baseline and small logical commits; push only if a remote is configured.
## Architecture
Modular monolith: apps/api (FastAPI, SQLAlchemy, Alembic), apps/web (Next.js/TypeScript), PostgreSQL, private local storage. No MCP, AI, workers or workflow engine in Iteration 1.
## Invariants
Backend owns authorization and lifecycle. Owner reads own documents; MANAGER reads department documents; ADMIN reads all. Other roles have owner access until assigned workflows exist. No client-controlled identity, role or status. Files are private; old versions immutable. Document numbering uses a database sequence; version allocation locks the document row. Audit is written transactionally.
Session cookie is HttpOnly; mutating requests require matching session CSRF token. Validate ACTIVE status on every request. Passwords use Argon2id. Secrets from environment only.
All user-visible frontend strings use RU/EN dictionaries, Russian default; preference persists in localStorage. Do not advertise planned features as implemented or claim production certification.
## Structure and commands
apps/api/app: config, models, auth, policy, storage, schemas, documents, main, seed.
apps/web/src: app pages, components, lib (API and localization).
Start: Copy-Item .env.example .env; docker compose up --build
API checks: cd apps/api; python -m pytest; python -m ruff check .; python -m mypy app
Web checks: cd apps/web; npm ci; npm run lint; npm run typecheck; npm run build
Migrations: docker compose exec api alembic upgrade head
Use typed schemas, small modules, explicit transactions, safe error codes. Update docs with implementation. Full workflow/approvals and notifications belong to Iteration 2. See docs/iterations.md and docs/security.md.

## Verified state
Iteration 1 implemented; 16 PostgreSQL/unit cases and 2 localization tests. See docs/verification.md for exact checks and limitations. Docker uses pinned requirements.lock and package-lock.json; web standalone runtime excludes dev tooling. Example .env uses default ports; prepared local .env uses 3300/8800/55432 because existing apps occupied defaults. Production setup and future workflows remain planned. Baseline is committed; see Git history.
