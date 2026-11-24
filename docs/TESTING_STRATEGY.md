# Testing strategy and acceptance evidence

Status: future implementation requirements. No application exists and no runtime tests have been executed. Current verification covers document completeness, links and consistency only. Quality targets below are proposed gates, not measured performance.

## Test layers and tools

Use pytest/pytest-django for services, ORM invariants, selectors, API and workers; run database-dependent tests against real PostgreSQL with the actual pgvector extension, never SQLite substitutes. Use deterministic provider fakes for normal CI, including malformed responses, latency, cost usage and failures. Contract-test each enabled adapter separately against its provider sandbox or explicit-budget live run. Mocking all provider behavior cannot certify real model quality.

Frontend: TypeScript strict checks, Vitest/Testing Library for meaningful interactions and Playwright for browser journeys. Validate OpenAPI request/response schemas and generate/compile the TypeScript client in CI. Check worker imports/module boundaries, migrations, Ruff/mypy, secret/dependency/container scans and an SBOM. Prefer tests of permissions, state and user outcomes over assertions tied to internal implementation.

Maintain synthetic fixtures with seeded taxonomy, corpus, resumes/JDs, rubrics and scores. No production data in tests. Keep deterministic seeds where supported, but do not assume an LLM will be byte-for-byte deterministic. Store benchmark dataset version, split, model/provider revision, prompt/rubric/schema versions, retrieval parameters and cost/latency with every AI report.

## Acceptance by phase

| Phase | Required automated verification | Required manual/evidence gate |
| --- | --- | --- |
| 0. Design | Seven requested files exist; relative links resolve; endpoint/table/phase terminology consistent | Architecture, privacy defaults, budget assumptions and open decisions reviewable; no feature files created |
| 1. Foundation | Empty-database and upgrade migrations; auth/CSRF/verification/reset; session rotation/revocation; cross-owner profile/jobs; transactional outbox with broker failure; OpenAPI/client compile | Clean-machine local boot from future README; password-manager flow; no secrets committed; auth accessibility |
| 2. Ingestion/NLP | MIME/size/page/archive/timeout tests, scanner fail-closed, parser no-network, evidence spans, immutability, correction provenance, resume/JD cross-owner gaps, deletion/export | Held-out extraction/gap gates below; owner can understand/correct observations; malformed/scanned PDF errors actionable |
| 3. Text interviews/RAG | All categories, budgets, adaptive boundaries, answer/skip/end races, deduplication, ACL retrieval, citation quote checks, abstention, feedback visibility, curation permissions | Human-rated evaluation benchmark; real-provider adapter test; full text journey; question relevance/coverage and performance targets |
| 4. Voice | Codec/duration limits, STT result/revision separation, explicit submission, consent denial/revocation, TTS cache ownership, audio expiry, media URL expiry | Chrome/Edge/Firefox desktop plus Android Chrome/iOS Safari supported-format checks; mic denial and keyboard/text fallback; WER and latency reports |
| 5. Graph | Kill/restart each node boundary; duplicate delivery; lease expiry and stale fencing; cancel/delete race; checkpoint restoration; step/token limits; backward-compatible graph state migration | Resume an interrupted interview with no duplicate turn/result; no waiting worker; compare graph quality/cost with phase 3 baseline |
| 6. Learning/analytics | Resource catalog validation, evidence links, task transitions, aggregate-vs-raw SQL fixtures, version/difficulty cohort filters, minimum sample size, derivative deletion/export | Plans actionable with realistic time; charts readable and uncertainty visible; no fabricated resources or readiness claims |
| 7. Release | Load/soak, security suite, restore/PITR/erasure ledger replay, deploy/rollback, budget exhaustion, provider outage and dependency scans | Independent security/domain review; named incident/privacy owners; measured recovery; limited pilot sign-off with known limitations |

Every gate failure becomes a tracked defect or explicitly narrowed supported scope; do not silently lower a metric after seeing the held-out set. Expand fixtures when a defect escapes.

## Core invariants and integration scenarios

1. Two users attempt every private endpoint, nested reference, operation, cache hit, media download, citation and export. Foreign IDs return 404 and never start billable work. Curator/ops users receive no implicit private access. Also test worker execution after ownership/consent changes.
2. Simultaneous answers, answer-versus-skip, answer-versus-complete and duplicate task delivery produce one submitted answer, one current evaluation and at most one next turn. Reused idempotency key with a changed request returns 409; stale ETag returns 412 without mutation.
3. Crash before/after domain commit, outbox publication, provider response, evaluation commit and checkpoint save. Broker loss leaves persisted work recoverable. Replays cannot duplicate domain effects; duplicate external billing is recorded/capped rather than assumed impossible.
4. Exhaust provider rate limit, schema repair budget, session budget, user quota and global spend ceiling. Verify atomic reservations under concurrency, release/reconciliation of abandoned reservations, useful retry state and no extra hidden calls.
5. Delete source/account while STT/LLM is running. Result commit is fenced, storage/vector/checkpoint/trace/cached artifacts are purged, learning/analytics invalidated, exports updated and restored backups reapply erasure before service resumes.
6. Low-recall retrieval and absent evidence yield null/provisional factual scores, never a confidently invented reference. Adversarial private/shared documents cannot change ACLs, tools or system instructions.
7. Difficulty changes only within defined boundaries after two qualifying primary scores; skipped/provisional answers do not change difficulty. Follow-ups stay under two per primary and count toward total question budget. Time expiry allows accepted work to settle but never accepts a late answer.

## AI, NLP and retrieval evaluation

Create a versioned gold dataset before tuning: minimum 100 synthetic/consented resumes, 50 JDs, 100 technical retrieval queries, 200 question/answer pairs distributed across all four tracks and difficulty bands, plus 50 adversarial/insufficient-evidence cases. Assign splits at source/person/template level, not chunk level, to avoid leakage: 60% development, 20% validation, 20% frozen test. Expand frozen sets if category counts are too small for confidence; report uncertainty/sample size rather than overclaiming. Two domain reviewers independently score at least 50 answers, adjudicating disagreements to form anchors.

| Area | Proposed acceptance threshold | Measurement / caveat |
| --- | --- | --- |
| Skill extraction | micro precision >=0.90, recall >=0.80 | Evidence-span-supported skill labels on held-out resumes; report category breakdown |
| JD required/preferred classification | macro F1 >=0.85 | Reviewer-labeled requirements, not model-generated truth |
| Gap computation | 100% match deterministic labeled fixtures | Explicit required/preferred/partial weights and missing-evidence semantics |
| Retrieval | Recall@6 >=0.90; MRR@6 >=0.75 | On answerable held-out questions, authorized corpus only; compare ANN against exact baseline |
| Retrieval authorization | Zero unauthorized chunks | Synthetic multi-owner/cross-scope canaries, all retrieval modes |
| Structured output | >=99% valid after bounded repair; 100% invalid outputs withheld | Include model error/timeout cases separately, no parsing unsafe text into state |
| Citation integrity | 100% IDs/quotes/offsets valid | Deterministic validators; human checks separately assess support |
| Grounding | >=95% factual feedback claims supported; unsupported high-impact claims <=1% | Blinded claim-level human review with denominator and confidence interval |
| Abstention | >=90% recall on insufficient-evidence cases; false abstention <=10% on answerable cases | Keep sufficient/insufficient subsets reported separately |
| Scoring agreement | Mean absolute error <=0.6 on 0–4 dimensions; weighted kappa >=0.65 | Compare to adjudicated anchors; also report human-human agreement |
| Repeated runs | Median overall-score range <=10/100 over three runs | Fixed inputs/versions; disclose outliers and per-track distribution |
| Question quality | >=90% relevant and seniority-appropriate; duplicate intent <=5% | Human labeled session samples; system-design tradeoffs and behavioral relevance included |
| Plan quality | 100% resources from approved catalog; >=90% tasks actionable and evidence-linked | Human rubric, practical exercises, time fit |

Evaluate score robustness to paraphrases, formatting, verbosity, explicit prompt injection and transcript spelling errors. Conduct matched-answer tests varying names/pronouns/accent-derived transcription artifacts; average dimension-score difference <=0.2/4 for semantically equivalent answers is an initial regression threshold, not proof of fairness. Small subgroups require more data before claims. Exclude protected traits from evaluation inputs when irrelevant. Score transcript content only, not audio/accent/emotion.

Prompt/model/embedding/rubric changes require re-running affected frozen benchmarks and an explicit regression comparison. Embedding migration must meet recall and tenant-isolation thresholds before switching. Rebaseline scores only with a justified new rubric version; preserve old history labels. Do not train/tune on frozen tests or use a single model as both generator and unquestioned grading oracle.

## Speech and accessibility

Build an English benchmark of at least 120 consented/synthetic clips, 10 speakers where consented human audio is used, covering distinct accents, microphones, quiet/noisy environments, silence and technical terms. Separate tuning and held-out speakers. Target median WER <=15% for clean clips and <=25% for noisy clips; report speaker/condition distributions, technical-term errors and failures rather than only averages. Synthetic voices alone cannot establish performance across real accents.

STT must reject undecodable/silent input safely; user correction overrides the scored text exactly. Original transcript remains provenance until its retention/deletion deadline. Verify hallucinated speech on silence does not auto-submit. TTS question text remains visible and accessible, autoplay is user-controlled, and audio unavailable/expired can fall back to text.

Target WCAG 2.2 AA through automated axe checks plus manual keyboard/screen-reader review of key journeys: labeled form errors, focus on question changes, status announcements without excessive polling chatter, pause controls, contrast and charts with equivalent tabular/text summaries. Automated accessibility checks alone do not certify conformance. Test denied microphone, missing MediaRecorder codec, navigation during upload, reconnect, session expiration and duplicate click behavior.

## Performance, reliability and cost targets

Test on documented pilot hardware/data size with warm and cold models distinguished: 100 users, 1,000 sessions, 10,000 answers, 100,000 shared chunks plus multiple private collections. Load profile: 20 active sessions, five concurrent inference jobs (local speech concurrency separately capped), API read burst 20 requests/second. Use a 30-minute steady run and four-hour soak; size-up testing follows measured failures.

| Metric | Initial target | Measurement boundary |
| --- | --- | --- |
| Read API latency | p95 <=300 ms | Excludes file transfer/provider computation; includes DB serialization |
| Async command acceptance | p95 <=500 ms | Validation + transaction + durable job intent; does not wait for broker/provider |
| Authorized retrieval | p95 <=300 ms | Query embedding measured separately; scoped DB full-text/vector retrieval |
| Next question ready | p95 <=10 seconds | Accepted start/advancement to visible persisted question, including queue wait |
| Evaluation + next-step completion | p95 <=20 seconds | Answer acceptance through ready next question or summary |
| STT | p95 <=30 seconds for 60-second audio | Upload completed to reviewable transcript, including queue/decode; hardware-specific |
| TTS | p95 <=5 seconds for 30-second question audio | Request accepted to playable output, uncached; text always immediate |
| Interactive queue age | p95 <=5 seconds; alert >60 seconds | Enqueue commit to worker start; report provider throttling separately |
| Pilot API availability | 99% monthly objective | Measured uptime excluding declared maintenance; not a contractual SLA |
| Production availability | 99.5% monthly objective | Only after redundant API/database failover design is tested |
| Recovery | Pilot RPO <=24h/RTO <=8h; production <=1h/4h | Timed restore drill with object consistency and erasure replay |
| Cost | Within approved monthly budget; hard stop at configured ceiling | Actual billed input/output/reasoning/audio and all attempts; estimate versus invoice reconciliation |

Track p50/p95/p99, error rate, queue age, memory/CPU, connections, query plans, provider throttles and cost/session. Provider-backed SLOs are provisional until measured on selected models and quotas. If latency fails, bound concurrency, reduce context/steps, change the approved model or add capacity; never conceal queue time from metrics. Validate input/audio limits under parallel uploads and verify memory remains bounded.

## Security and operational verification

Automated checks include CSRF, origin/CORS, cookie flags, session fixation/revocation, token reuse/expiry, auth enumeration, rate limits, SQL injection, stored XSS/Markdown links, SSRF endpoint restriction, malicious filenames/archives, decompression bombs, parser egress denial, media signature spoofing and prompt-injection canaries. Confirm all private responses and signed URL responses use appropriate no-store controls. Run authenticated dynamic scanning in staging with synthetic content. Independent review tests authorization and AI tool boundaries, not only dependency CVEs.

Operational drills: kill worker mid-call, flush disposable broker in staging, make scanner unavailable, break provider connectivity, exhaust DB pool, simulate storage deletion failure, rotate secrets, restore DB+objects, apply erasure ledger and roll back an app release with the current expanded schema. Test no external notification/inference is sent from restored staging data. Record timings, recovery actions and defects. Run restore/deletion drills before launch and at least quarterly thereafter.

## CI and release evidence

Every PR: lint/type checks, relevant unit/integration/permission tests, frontend build, OpenAPI compatibility, migrations and security scans. Nightly: broader concurrency/fault suites, browser journeys and bounded AI regression subset. Before phase/release gates: full affected AI benchmark, real configured-adapter contracts, load/soak, privacy sweep and manual accessibility/security/domain review. Avoid paying for live model calls on every trivial docs/UI change.

Release evidence contains commit/image ID, dependency/model hashes, schema migration path, test reports, AI dataset/version and reviewers, latency/cost distributions, security findings, restore timings, deletion verification and known limitations. Block release on ownership leaks, silent data loss, invalid scoring evidence, missing consent/erasure, duplicate state transitions or unresolved exploitable high/critical findings. Coverage is a diagnostic, not the acceptance criterion; all identified security and transaction invariants need explicit tests.
