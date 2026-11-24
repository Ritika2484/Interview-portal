# AI Interview Preparation Platform

**Status: architecture proposal for review; no application features implemented.**

This project proposes a production-inspired interview practice platform built with Django REST Framework, React/TypeScript, PostgreSQL/pgvector, configurable language models, retrieval-augmented generation (RAG), speech processing, and bounded LangGraph workflows. It is a coaching product; scores are formative feedback, not hiring decisions or verified measures of employability.

## Repository inspection

Inspected `C:\interview-plat` on 2026-11-24, including hidden entries and a recursive listing. The workspace was empty: no source code, dependency manifests, migrations, documentation, AGENTS.md, or Git repository were present. These documents establish a greenfield design. No framework scaffolding, dependencies, infrastructure, or database objects have been created.

## Proposed scope

- Email authentication, account recovery, profiles, and privacy controls.
- PDF/DOCX resume ingestion, evidence-backed analysis, job-description analysis, and skill gaps.
- Personalized technical, behavioral, HR, and system-design practice.
- Adaptive questions and bounded follow-ups with text and turn-based voice answers.
- RAG-grounded technical evaluation; rubric-based behavioral coaching with explicit uncertainty.
- Learning plans, performance history, and comparable progress metrics.

Start with a **modular monolith**: one backend codebase, one relational database, and the same backend image running API and worker processes. React is a separate build deployed behind the same public origin. Background workers are process roles, not microservices.

## Design documents

| Document | Purpose |
| --- | --- |
| [Architecture](docs/ARCHITECTURE.md) | Modules, AI/speech workflows, dependencies, infrastructure, sizing and costs |
| [Database design](docs/DATABASE_DESIGN.md) | Tables, relationships, ownership, constraints, vector indexes and lifecycle |
| [API design](docs/API_DESIGN.md) | Versioned contracts, authentication, asynchronous jobs, examples and errors |
| [Development roadmap](docs/DEVELOPMENT_ROADMAP.md) | Ordered phases, dependencies, review gates, risks and acceptance criteria |
| [Security](docs/SECURITY.md) | Threat model, permissions, consent, retention and operational controls |
| [Testing strategy](docs/TESTING_STRATEGY.md) | Automated verification, AI benchmarks, performance targets and release gates |

## Starting assumptions and decisions

English-first, adult individual learners, one deployment region, no organization tenancy or billing in the initial release. Plan for 100 monthly active learners and 1,000 completed sessions/month; validate with load tests before promising capacity. An interview is bounded to 5–20 questions, up to two follow-ups per primary question within that total, and a 60-minute maximum duration.

Use same-origin server-side session authentication with CSRF protection. Prefer open-source PostgreSQL, pgvector, Valkey, Celery, sentence-transformers and faster-whisper where operationally practical. Hosted inference is optional and explicitly disclosed. Model weights and voice licenses need separate review. Provider choice must not alter public API schemas or silently move personal data between vendors.

The first usable milestone is a secure **text interview vertical slice** with resume/JD analysis and grounded evaluations. Voice, LangGraph orchestration, and richer analytics follow in gated phases. No Kubernetes, service mesh, dedicated vector database, multi-agent service fleet, code execution sandbox, live video, emotion detection, or full-duplex voice is planned initially.

## Implementation and review

There are no runnable setup commands yet. After design review, phase 1 will add the backend/frontend skeleton, lockfiles, local Compose stack, CI, migrations and environment examples. Never commit real credentials or personal resumes.

Review priorities are deployment region and retention policy, expected concurrency, corpus licensing, rubric validity, hosted versus local inference, and the monthly budget. Proposed defaults and measurable gates are documented so implementation can proceed after review without inventing core contracts.

Planning estimates and external references were checked on 2026-11-24. Prices are USD planning figures, not vendor quotes; see [cost assumptions](docs/ARCHITECTURE.md#operational-cost-model).
