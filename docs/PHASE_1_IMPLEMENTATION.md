# Phase 1 backend foundation: implementation and verification

Date: 2026-11-25. Scope follows the user's backend infrastructure request. No AI features, domain workflows, pushes, merges or deployments were performed.

## Implemented behavior

The modular monolith now has ten installed Django applications, shared API/worker configuration, separate development/testing/production settings, PostgreSQL/pgvector migrations, Redis caching and Celery transport/results, health checks, OpenAPI/Swagger, minimized structured logs, a multi-stage Dockerfile and local Compose stack. Ruff, Pytest, pre-commit and GitHub Actions configuration are present. Runtime and development dependency closures are pinned to exact versions.

`accounts` supplies only a minimal UUID/email custom User and manager, so later applications do not depend on Django's default integer/username user. PostgreSQL enforces case-insensitive email uniqueness even when model save logic is bypassed. No learner-facing account endpoint or profile model exists yet. Other domain apps intentionally contain no feature models. `knowledge.0001_enable_vector` uses pgvector's `VectorExtension` migration operation; it does not create embeddings or call a model.

Production settings fail on absent/weak secrets, wildcard/empty hosts, non-HTTPS configured origins, non-PostgreSQL databases, insecure Redis transport or disabled certificate verification. Session/CSRF cookies are secure, DRF routes default to authenticated, and admin/docs are unavailable in production. Admin is development-only and has no private domain models registered. These are foundation controls, not a claim that the full security/privacy design has been implemented.

`/health/live/` is independent of external services. `/health/ready/` checks database connectivity, vector availability, core tables and cache Redis, returning only ready/not_ready. It does not prove worker/broker health or that every future schema migration is current. `common.infrastructure_probe` separately verifies actual broker dispatch, worker execution, a database query and result-backend retrieval. There is no public task-dispatch API.

## Decisions relative to original architecture

- Redis replaces the initial Valkey proposal, as requested.
- `feedback` corresponds to planned evaluation concerns; `ai_services` corresponds to the planned AI adapter boundary. Neither implements AI behavior.
- Separate skills/workflows/media/audit modules are deferred until those features are introduced. Common infrastructure does not pretend to implement durable user jobs or an outbox.
- Python 3.12 and 3.14 are CI targets. Native verification used 3.14.8; the Docker runtime pins the newer 3.14.10 patch. Django remains on the 5.2 LTS series.
- The user's current request completes the **backend infrastructure subset** of the original Phase 1. Authentication/verification/reset/profile workflows, frontend, generated TypeScript client, durable outbox and export/deletion plumbing remain pending. The broader roadmap phase is not marked fully complete.

## Commands executed and observed results

Commands below are grouped by purpose. Local verification injected disposable infrastructure URLs with ports 54329/6389; these are distinct from normal README development ports. Production configuration checks used independently generated, temporary test secrets and certificate-enforcing example URLs without contacting a live production system. No real secret values are included here.

| Commands / checks | Result |
| --- | --- |
| Repository inventory, `rg`, `git status`, existing documentation reads | Existing repository contained committed design documents; no backend code or manifests |
| `python --version`, `py -0p`, executable/runtime discovery, PyPI version queries | Python 3.14.8 available; no usable Docker engine/Windows CLI; a residual Docker Desktop WSL distribution exists |
| `python -m venv .venv`; venv `pip install` for selected runtime/dev packages | Successful; resolved dependency closures recorded in requirements files |
| Venv `python -m pip check` | No broken requirements |
| `python scripts/initialize_env.py` | Created ignored local `.env` with generated credentials; no values printed |
| `python backend/manage.py makemigrations accounts --settings=config.settings.testing` | Generated custom User initial migration; initial database-history warning before test services were available |
| `python backend/manage.py migrate --noinput --settings=config.settings.testing` | All migrations applied successfully against real PostgreSQL, including vector extension |
| `python backend/manage.py check --settings=config.settings.testing` | No issues |
| `python backend/manage.py makemigrations --check --dry-run --settings=config.settings.testing` | No changes detected |
| Production `python backend/manage.py check --deploy --fail-level WARNING` | No issues, exit 0 |
| Production `python backend/manage.py collectstatic --noinput --verbosity 0` | Successful, exit 0; generated files ignored by Git |
| `python backend/manage.py spectacular --file reports/openapi.yaml --validate --fail-on-warn --settings=config.settings.testing` | Successful OpenAPI 3.0.3 schema generation/validation |
| `python -m ruff check .`; `python -m ruff format --check .` | Passed; generated files were formatted before final checks |
| `python -m pre_commit run --files <tracked-and-new-repository-files>` with venv on PATH | All three hooks passed; hook installation itself is left as a documented developer command |
| `python -m pytest --cov --cov-report=term-missing --junitxml=reports/pytest.xml` | **36 passed**; includes actual database and actual worker integration |
| Independent `python -m pytest -m integration` | Passed real broker/worker/database/result-backend round trip |
| Official Compose CLI v2.40.3, `.tools/docker-compose config --quiet` | Valid configuration; downloaded binary SHA-256 matched its published checksum |
| Native Django `runserver 127.0.0.1:8011 --noreload` plus PowerShell HTTP requests | Liveness 200/alive; readiness 200/ready; schema 3.0.3; Swagger 200 |
| `git diff --check` and documentation link/fence checks | Passed at final review |

Earlier verification exposed and corrected a test-fixture cleanup error and a producer queue mismatch. The final worker test uses an independent, non-eager producer on the configured queue and passes. Pre-commit initially resolved the global Python instead of the venv; final verification prepended the venv to PATH, as documented in README.

Tests cover health success/degradation/redaction, request-ID validation, schema validation/local Swagger assets, real pgvector distance operations, migration completeness, custom user constraints/password handling, database sessions, CSRF rejection, CORS allowlists, private API defaults, production settings/deploy guards, restrictive API CSP, and real Celery transport/results. Parent-process coverage was 85%; worker and production-settings subprocess execution are not included in that percentage. Coverage is descriptive, not a release gate.

## Verification environment and limits

Because a Docker engine was unavailable, real local services ran in an isolated temporary Alpine root inside the existing WSL distribution, with loopback-only listeners. Its signed repository packages supplied **PostgreSQL 18.7, pgvector 0.8.1 and Redis 8.4.2**. Tests used a UTF-8 database. The diagnostic Celery worker ran on Windows with the solo pool. These temporary services are stopped after verification; no system-wide PostgreSQL/Redis installation was made. Ignored local tools, venv, generated static assets and reports remain development artifacts, not application source or deployment state.

The exact Compose stack instead pins **PostgreSQL 17/pgvector 0.8.7, Redis 7.4.12 and a Linux prefork worker**. Its configuration validates, but image builds and container startup could not run locally. GitHub CI contains a Python 3.12/3.14 database/worker matrix and a separate complete Compose build/start/test job; those hosted workflows have not run because nothing was pushed. Native Python 3.12, production TLS certificate negotiation, load/soak behavior, backups/recovery, staff MFA and production operations remain unverified. Package hashes/image digests and comprehensive secret/dependency vulnerability scanning remain future hardening work.

## Follow-up verification: 2026-11-26

The user's Docker output confirms successful builds of the pinned images, completed migrations and **36 passing tests in the Linux Compose container**, including the real Celery integration test. Initial API startup failed because host port 8000 was already occupied; it was a host binding conflict, not an image build, migration or test failure.

Local `.env` was changed from `API_PORT=8000` to `API_PORT=8001` after verifying that 8001 was available. Using the host Docker CLI, `docker compose up --wait --wait-timeout 240 api worker` then completed successfully with both API and worker healthy. HTTP checks at `127.0.0.1:8001` returned `{"status":"alive"}`, `{"status":"ready"}` and Swagger status 200. Internal container port 8000, dependencies, database data and the process already using host port 8000 were left unchanged. The local stack remains running for the user. This resolves the earlier local Compose build/startup verification gap; GitHub-hosted CI and production operations remain unverified.

## Container verification checklist

1. Follow the [PowerShell setup](../README.md#run-with-docker-compose) on Docker Desktop with a running Linux engine.
2. Run `docker compose up --build --wait --wait-timeout 240 api worker`; verify db/redis/API/worker are healthy and migrate exited 0.
3. Confirm liveness/readiness responses, inspect Swagger, and generate the schema with `--validate --fail-on-warn`.
4. Query `pg_extension`, inspect `showmigrations`, and run the infrastructure probe; expect `{'status': 'ok'}`.
5. Run `docker compose --profile test run --rm test python -m pytest`; expect all 36 tests to pass against the pinned services.
6. Stop Redis temporarily; readiness should return 503 while liveness remains 200. Start Redis again and verify readiness recovers. Repeat with database only in a disposable local stack.
7. Restart API/worker and confirm migrations/data persist. Use ordinary `docker compose down` to retain volumes.
8. After an approved future push, inspect both CI jobs, including image build and Linux worker results. No push, merge or deployment is authorized by this verification checklist.

## Source file inventory

The exact newly created source paths are listed below. Existing README and six design documents were updated to distinguish implemented infrastructure from planned product features. `.env`, `.venv`, `.tools`, `.runtime`, `reports` and collected static assets are ignored local artifacts.

New source/documentation files: 75.

```text
.dockerignore
.env.example
.gitattributes
.github/workflows/ci.yml
.gitignore
.pre-commit-config.yaml
backend/Dockerfile
backend/apps/__init__.py
backend/apps/accounts/__init__.py
backend/apps/accounts/apps.py
backend/apps/accounts/managers.py
backend/apps/accounts/migrations/0001_initial.py
backend/apps/accounts/migrations/__init__.py
backend/apps/accounts/models.py
backend/apps/ai_services/__init__.py
backend/apps/ai_services/apps.py
backend/apps/ai_services/models.py
backend/apps/analytics/__init__.py
backend/apps/analytics/apps.py
backend/apps/analytics/models.py
backend/apps/common/__init__.py
backend/apps/common/apps.py
backend/apps/common/health.py
backend/apps/common/logging.py
backend/apps/common/middleware.py
backend/apps/common/models.py
backend/apps/common/pagination.py
backend/apps/common/tasks.py
backend/apps/feedback/__init__.py
backend/apps/feedback/apps.py
backend/apps/feedback/models.py
backend/apps/interviews/__init__.py
backend/apps/interviews/apps.py
backend/apps/interviews/models.py
backend/apps/jobs/__init__.py
backend/apps/jobs/apps.py
backend/apps/jobs/models.py
backend/apps/knowledge/__init__.py
backend/apps/knowledge/apps.py
backend/apps/knowledge/migrations/0001_enable_vector.py
backend/apps/knowledge/migrations/__init__.py
backend/apps/knowledge/models.py
backend/apps/learning/__init__.py
backend/apps/learning/apps.py
backend/apps/learning/models.py
backend/apps/resumes/__init__.py
backend/apps/resumes/apps.py
backend/apps/resumes/models.py
backend/config/__init__.py
backend/config/asgi.py
backend/config/celery.py
backend/config/settings/__init__.py
backend/config/settings/base.py
backend/config/settings/development.py
backend/config/settings/production.py
backend/config/settings/testing.py
backend/config/urls.py
backend/config/wsgi.py
backend/manage.py
backend/tests/__init__.py
backend/tests/test_accounts.py
backend/tests/test_celery.py
backend/tests/test_database.py
backend/tests/test_health.py
backend/tests/test_logging.py
backend/tests/test_schema.py
backend/tests/test_security.py
compose.yaml
docs/PHASE_1_IMPLEMENTATION.md
pyproject.toml
requirements/base.txt
requirements/dev.txt
scripts/check_repository.py
scripts/initialize_env.py
scripts/run_tests.py
```
