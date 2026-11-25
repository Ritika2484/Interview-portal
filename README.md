# AI Interview Preparation Platform

**Status: backend foundation and Phase 2 authentication/user management implemented; AI and interview features remain planned.**

A modular Django REST Framework backend for a future interview preparation platform. The eventual product includes resume/JD analysis, personalized text/voice interviews, grounded feedback, learning plans and analytics. This repository currently provides infrastructure and secure account APIs; those interview/AI workflows remain planned.

## Implemented foundation

- Ten Django apps: `accounts`, `resumes`, `jobs`, `interviews`, `feedback`, `knowledge`, `learning`, `analytics`, `ai_services`, `common`.
- Development, testing and fail-closed production settings with environment-based configuration.
- UUID email-based custom User with case-insensitive database uniqueness, established before dependent migrations.
- PostgreSQL and a migration enabling pgvector; Redis cache/broker/results; a Celery infrastructure probe task.
- JSON logging with request IDs, session/CSRF/CORS defaults, health checks and OpenAPI/Swagger.
- Non-root multi-stage Dockerfile, local Compose stack, pinned dependencies, Ruff, Pytest, pre-commit and GitHub Actions.

Phase 2 adds registration/login, email verification, password recovery, tracked server-side sessions, owner-scoped profiles, candidate/administrator roles and account/personal-data deletion. Authentication emails use a durable PostgreSQL intent queue processed by Celery; no raw tokens enter the broker or database. See [authentication implementation and manual API guide](docs/AUTHENTICATION.md).

AI, interview/upload APIs, frontend, generic domain jobs/outbox and data export remain future work. The authentication milestone follows the user's current Phase 2 sequence; the original roadmap's resume/JD phase is still future. The original broader foundation milestone still has pending frontend/export work. [Phase 1 verification](docs/PHASE_1_IMPLEMENTATION.md) remains a historical record.

## Repository layout

```text
backend/
  manage.py
  config/                  # URLs, Celery, WSGI/ASGI, settings/
  apps/                    # ten independently registered domain modules
  tests/                   # security, schema, database, HTTP and worker checks
  Dockerfile               # development and production targets
requirements/              # exact runtime and development dependency closures
scripts/                   # safe local environment setup, native tests, hook checks
.github/workflows/ci.yml
compose.yaml
docs/
```

## Prerequisites

Use Windows PowerShell from the repository root. Install Git, Python 3.12 or 3.14 and Docker Desktop with Linux containers and Compose **2.24+**. Start Docker Desktop; `docker version` must show both client and server. Host verification used Python 3.14.8; Docker pins Python 3.14.10. CI targets Python 3.12 and 3.14. Run Redis and Celery in Linux containers for normal Windows development; native Windows Celery is not a supported production configuration.

Compose pins PostgreSQL 17/pgvector 0.8.7 and Redis 7.4.12. Django 5.2.19 LTS, DRF 3.18.1, Celery 5.7.0 and psycopg 3.3.9 are principal resolved versions. Runtime and development dependency closures have exact pins; refresh them together with tests and security review. Package hashes and image digests are not locked yet. Release references: [Django](https://www.djangoproject.com/download/), [DRF](https://www.django-rest-framework.org/community/release-notes/), [Celery](https://docs.celeryq.dev/en/stable/getting-started/introduction.html).

## Run with Docker Compose

```powershell
Set-Location C:\interview-plat
python scripts/initialize_env.py
docker compose config --quiet
docker compose up --build --wait --wait-timeout 240 api worker
```

The initializer generates local credentials from `.env.example`, never prints them, and refuses to overwrite `.env`. If the file exists, review/use it and skip initialization. `.env` is ignored by Git and excluded from image builds. These credentials are for local development only.

Compose waits for database/Redis health and runs the one-off `migrate` service before API/worker startup. Both processes use the same backend codebase/image. Host ports bind only to loopback; named database/Redis volumes survive normal shutdown.

```powershell
Invoke-RestMethod http://localhost:8000/health/live/
Invoke-RestMethod http://localhost:8000/health/ready/
Start-Process http://localhost:8000/api/v1/docs/
docker compose ps -a
docker compose logs --tail 100 api worker migrate
```

Expected responses: `{"status":"alive"}` and `{"status":"ready"}`. Swagger and `/api/v1/schema/` are development/testing-only; Swagger assets are packaged locally with drf-spectacular-sidecar. Production disables API docs and Django admin until proper staff MFA/access controls exist.

```powershell
docker compose exec api python manage.py check
docker compose exec api python manage.py showmigrations
docker compose exec api python manage.py makemigrations --check --dry-run
docker compose exec api python manage.py shell -c "from apps.common.tasks import infrastructure_probe; print(infrastructure_probe.delay().get(timeout=20))"
# Uses default POSTGRES_USER/POSTGRES_DB names; adjust if you changed them:
docker compose exec db psql -U interview -d interview_platform -c "SELECT extname, extversion FROM pg_extension;"

# Full suite, including real worker round trip; keep the worker running:
docker compose --profile test run --rm test python -m pytest
# Default test command excludes worker integration and prints coverage:
docker compose --profile test run --rm test

# Stop while retaining development data:
docker compose down
```

The worker now also processes authentication email intents and retention cleanup. Compose starts a singleton `beat` scheduler and local Mailpit with the worker. View verification/reset emails at `http://localhost:8025`; SMTP is loopback-only on host port 1025. Mailpit is a development inbox and never relays mail externally. Account links contain tokens for a future frontend; until then use the API guide to submit the token. No public task-dispatch endpoint exists. Future billable/domain jobs still require the generic outbox/deduplication layer.

## Native API and tooling on Windows

Keep PostgreSQL/pgvector and Redis in Compose and run Django/tooling in a virtual environment. Do not simultaneously run the native and container API on port 8000.

```powershell
Set-Location C:\interview-plat
python scripts/initialize_env.py  # Skip if .env already exists.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/dev.txt
.\.venv\Scripts\python.exe -m pip check
docker compose up -d --wait db redis mailpit
.\.venv\Scripts\python.exe backend/manage.py migrate --noinput
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe scripts/run_tests.py -m "not integration"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe backend/manage.py runserver 127.0.0.1:8000
```

Development automatically reads root `.env` without overriding shell variables. Testing and production settings do not automatically read it. `scripts/run_tests.py` explicitly loads local infrastructure URLs and selects testing settings; CI injects URLs directly. Pytest creates/destroys a separate `test_<database-name>` PostgreSQL database and needs permission to create test databases. No SQLite fallback exists. Never point local/test configuration at a production database.

For all native tests with a Linux worker, start `docker compose up --build --wait worker` in another terminal, then run `.\.venv\Scripts\python.exe scripts/run_tests.py`. To export OpenAPI:

```powershell
New-Item -ItemType Directory -Force reports | Out-Null
.\.venv\Scripts\python.exe backend/manage.py spectacular --file reports/openapi.yaml --validate --fail-on-warn
```

Local pre-commit hooks use the active Python environment. Activate the venv, or prepend it to this terminal's PATH without changing execution policy:

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv\Scripts') + ';' + $env:PATH
python -m pre_commit install
python -m pre_commit run --all-files
# Also check new files before staging:
$files = git ls-files --cached --others --exclude-standard
python -m pre_commit run --files $files
```

Hooks check Ruff lint/format, conflict markers and accidentally selected `.env` files. This is not a comprehensive secret scanner. Hook installation is a developer action; CI checks independently. Tests do not run on every commit.

## Configuration and production boundaries

| Variable | Purpose |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.development`, `.testing` or `.production` |
| `DJANGO_SECRET_KEY` | Required; independent secret per deployment |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts without schemes; explicit production hosts required |
| `DATABASE_URL` | PostgreSQL DSN; Compose overrides it using `POSTGRES_*` and container hostname |
| `REDIS_URL` | Cache/readiness, local Redis DB 0 |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Broker/results, local Redis DBs 1/2 |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Explicit frontend origins; empty for same-origin production |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Exact trusted unsafe-request origins; does not replace CSRF tokens |
| `DJANGO_ENABLE_API_DOCS` | Development switch; production always disables docs |
| `DJANGO_LOG_LEVEL` | Structured log threshold, default INFO |
| `POSTGRES_PORT`, `REDIS_PORT`, `API_PORT` | Published loopback ports; also update native DSNs if changed |
| `DATABASE_SSLMODE`, `PGSSLROOTCERT` | Production database certificate verification and CA path |
| `DJANGO_TRUST_PROXY_SSL_HEADER` | False by default; enable only behind a trusted header-sanitizing TLS proxy |

Production requires verified database TLS (`verify-full` default), `rediss://` with certificate validation, a strong secret, explicit allowed hosts and HTTPS configured origins. DEBUG is always off. Secure session/CSRF cookies, HTTPS redirect, HSTS and a restrictive API CSP are enabled. Do not expose development's unauthenticated Redis, superuser database role or `runserver` publicly. Compose explicitly selects development settings; changing only `.env` does not make it a production deployment.

Authentication additionally requires a configured production SMTP host, a real `DEFAULT_FROM_EMAIL`, and an HTTPS `AUTH_PUBLIC_BASE_URL`. SMTP uses STARTTLS, server-side credentials and a five-second timeout. Administrator API login remains disabled in production until staff MFA/access controls are added; candidate authentication is available. Registration always creates a candidate, and profile inputs cannot change roles or verification flags. The upgrade preserves existing users/password hashes, backfills profiles and staff roles, and forces fresh login by clearing legacy untracked sessions. Do not edit or replace the initial user migration.

The production Docker target uses Gunicorn and a non-root user. A future release pipeline must inject secrets, run `python manage.py check --deploy --fail-level WARNING`, collect static assets with `python manage.py collectstatic --noinput`, apply controlled migrations, and provision TLS, least-privilege roles, backups and monitoring. The migration role needs extension-creation permission or a DBA must preinstall vector; production runtime workers must not be superusers. No production deployment exists.

Liveness touches no infrastructure. Readiness checks PostgreSQL, vector and core account/session tables plus the configured cache Redis connection. It does not certify every future migration, broker URL or worker; use the separate probe and monitoring. Health checks never invoke AI providers.

Logs retain fixed events, request IDs, status, method, route name, duration and exception type. They omit bodies, credentials, raw URLs/query strings, SQL and exception messages/tracebacks. Third-party messages become `library_event`; their logger names remain available for diagnostics. Any future detailed diagnostic channel must preserve privacy.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Docker command missing / no engine | Install/start Docker Desktop and reopen PowerShell; a stale `docker-desktop` WSL distribution alone is insufficient |
| `DisallowedHost` | Add the exact hostname to `DJANGO_ALLOWED_HOSTS`; recreate containers after environment changes |
| Readiness 503 | Inspect `docker compose ps -a` and migrate/API logs; verify database/vector migration and Redis |
| Vector extension unavailable | Use the pgvector image, not plain PostgreSQL; verify extension support and migration privileges |
| Database auth fails after `.env` edits | Existing volume retains original credentials; deliberately update the role or restore prior credentials. Container recreation does not reset the database |
| Native tests cannot authenticate | Use `scripts/run_tests.py`; plain Pytest does not automatically load `.env` |
| Port already in use | Adjust published ports and native DSNs, or stop the other local process |
| `db` / `redis` unresolved on Windows | Container hostnames only work inside Compose; native URLs use `127.0.0.1` |
| CORS / CSRF rejection | Configure exact scheme/host/port, send session credentials and CSRF token; keep CSRF enabled |
| Probe timeout | Confirm worker consumes `default`, URLs match API, and worker can reach PostgreSQL |
| Hook cannot import Ruff | Activate/prepend `.venv\Scripts` to PATH and install development requirements |
| Production static errors | Run collectstatic with production settings before serving |
| Stale test database | Confirm it is disposable, then use `--reuse-db` or deliberately resolve that test database; never reset the primary DB |

Normal shutdown is `docker compose down`. `docker compose down --volumes` **deletes all local database/Redis data** and is only for an intentional disposable reset, not routine troubleshooting.

If port 8000 is occupied, set `API_PORT=8001` in the root `.env` and recreate the API container:

```powershell
docker compose up --wait --wait-timeout 240 api worker
if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed; inspect its output before continuing.' }
Invoke-RestMethod http://127.0.0.1:8001/health/ready/
Start-Process http://127.0.0.1:8001/api/v1/docs/
```

`API_PORT` changes only the host mapping; Django and its container health check continue using port 8000 inside the container. An API-only port change does not require changes to database/Redis URLs, migrations, volumes or dependencies. Run tests after startup succeeds rather than continuing past a failed Compose command.

## Verification and documentation

Phase 2 verification on 2026-11-26: **91 tests passed both natively and in the pinned Linux Compose stack**, including existing tests, account flows, CSRF, expiry/revocation, rate limits, owner permissions, privilege escalation, deletion, concurrent token use and migration upgrade. Django checks, migration drift, OpenAPI validation and Ruff passed. The live Mailpit/worker email flow and authenticated HTTP lifecycle were also exercised. See [authentication evidence and manual testing](docs/AUTHENTICATION.md).

On 2026-11-25, migrations, Django checks, migration-drift checks, OpenAPI validation, Ruff, pre-commit and all **36 tests passed**. Real HTTP health/schema/Swagger and a Celery round trip were verified. Local temporary services were PostgreSQL 18.7/pgvector 0.8.1 and Redis 8.4.2; the Windows diagnostic worker used the solo pool. The exact Compose PostgreSQL 17/pgvector 0.8.7, Redis 7.4.12 and Linux prefork combination remains a CI/manual gate. Compose configuration validated, but image builds/startup and GitHub-hosted CI were not executed locally. See the [full verification report](docs/PHASE_1_IMPLEMENTATION.md).

Update 2026-11-26: the user's Docker output confirms the pinned images built, migrations completed and all 36 tests passed in the Linux Compose test container. The host port-8000 conflict was resolved by setting local `.env` to `API_PORT=8001`. The stack was then restarted successfully: API and worker are healthy, HTTP liveness/readiness return alive/ready, and Swagger returns 200 at `http://127.0.0.1:8001/api/v1/docs/`. GitHub-hosted CI remains unexecuted.

| Document | Purpose |
| --- | --- |
| [Architecture](docs/ARCHITECTURE.md) | Module boundaries, AI design, infrastructure and illustrative cost model |
| [Database design](docs/DATABASE_DESIGN.md) | Proposed domain schema; User and vector migration currently implemented |
| [API design](docs/API_DESIGN.md) | Planned product APIs; current surface is health/development docs |
| [Development roadmap](docs/DEVELOPMENT_ROADMAP.md) | Phases, dependencies, risks and gates |
| [Security](docs/SECURITY.md) | Target security/privacy requirements and implementation boundaries |
| [Testing strategy](docs/TESTING_STRATEGY.md) | Phase-specific acceptance strategy |
| [Authentication](docs/AUTHENTICATION.md) | Phase 2 decisions, API examples, email delivery, migrations and verification |

Initial inspection on 2026-11-24 found an empty workspace without Git. Documentation was subsequently committed before implementation began. This work has not pushed, merged or deployed any changes.
