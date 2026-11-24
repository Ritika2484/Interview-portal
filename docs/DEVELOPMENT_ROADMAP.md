# Development roadmap and risk register

Status: architecture review only. No phase below has been implemented. Deliver one safe vertical slice at a time; keep application and AI providers independently testable. Estimates assume one experienced full-time engineer with part-time frontend/design/security/domain review; they are effort ranges, not delivery commitments. Rough total is 18–28 engineering weeks plus review/procurement uncertainty.

## Phase plan

Each phase requires the automated and manual evidence in [testing strategy](TESTING_STRATEGY.md). Do not advance by marking checklist items complete without observed results.

| Phase | Estimated effort / prerequisites | Deliverables | Acceptance gate |
| --- | --- | --- | --- |
| 0. Architecture review | 1 week; current phase | These seven docs; decisions, data lifecycle, API/schema and budgets | Stakeholders review region/retention, initial rubric, corpus license, provider choice and budget; no feature implementation |
| 1. Foundation and identity | 2–3 weeks; phase 0 review | Django/DRF skeleton, custom user, React/TS shell, sessions/CSRF, verification/reset, profile, local Compose, migrations, OpenAPI, CI, fake providers, outbox/jobs, minimal privacy lifecycle | Clean-machine setup works; isolated PostgreSQL tests; auth/revocation/CSRF and cross-user tests pass; typed client builds; committed intent survives broker outage; secret scan clean |
| 2. Resume/JD analysis and gaps | 2–3 weeks; phase 1 | Secure upload/quarantine/parser, immutable versions, NLP taxonomy/evidence, configured LLM extraction, JD and gap reports, correction review UI | Malicious/oversized/encrypted input rejected safely; evidence spans round-trip; held-out extraction thresholds pass; user can inspect/correct; source deletion removes private derivatives; hosted consent enforced |
| 3. Grounded text interview MVP | 4–5 weeks; phases 1–2 | Curated corpus/rubric/resource administration, embeddings/retrieval, session state machine, text answers, basic bounded adaptive policy/follow-ups, structured evaluations and summary | All four interview categories work; 5–20-turn and follow-up caps hold; technical citations/abstentions valid; no answer leaks before completion; concurrency/retry tests pass; gold-set scoring and grounding gates pass; text SLO measured |
| 4. Voice turns and accessibility | 2–3 weeks; phase 3 | Recording consent, codec normalization, STT/revision review, explicit text submission, TTS caching/fallback, audio expiry | Supported browser/device flow works; mic denial/offline/TTS failure falls back to text; transcript edit is scored exactly; English STT benchmark and latency gates pass; raw audio purges on schedule |
| 5. Durable LangGraph orchestration | 2–3 weeks; phase 3, after phase 4 by default | Move existing services into planner/retriever/questioner/evaluator/coach graph, PostgreSQL checkpoints, execution leases/fencing, resume/cancel/version migration | Worker kill/replay gives one answer/evaluation/current turn; wait does not hold worker; graph bounded under injection; restore after crash works; outputs meet phase 3 quality baseline; no provider credentials in checkpoints |
| 6. Learning plans and progress | 2–3 weeks; phases 3 and 5 | Reviewed resource catalog, evidence-linked plans/tasks, comparable score history, filters and progress dashboard, export completeness | Plan tasks trace to gaps/evaluations; no fabricated URLs; charts match SQL fixtures and show sample sizes; incompatible rubrics separated; erased sources disappear from plans/analytics/export |
| 7. Production hardening and pilot | 3–4 weeks; phases 1–6 | Load/soak tests, security review, backup/PITR/restore drill, erasure ledger replay, incident runbooks, observability, budget caps, staging, release rollback and limited pilot | All launch gates below pass; owners assigned; pilot monthly spend forecast within approved cap; demonstrated recovery targets; no unresolved high/critical exploitable findings; sign-off on AI quality and limitations |

Phase 1 includes minimal export/delete plumbing; each subsequent phase extends the erasure/export graph when it adds private data. A phase cannot defer its privacy obligations until production hardening. Phase 3 uses deterministic service orchestration; LangGraph is introduced only after the domain contract is stable, avoiding simultaneous state-machine and framework risk.

## Review decisions with proposed defaults

| Decision | Proposed default | Why it matters |
| --- | --- | --- |
| Deployment region / user geography | Single region near initial learners, explicit subprocessor region review | Latency, data transfer, contracts |
| Hosted versus local LLM | Adapter supports both; select by quality/latency benchmark and disclosed data policy | Cost/privacy/hardware tradeoff; no automatic vendor fallback |
| Initial audience | English-speaking adults practicing individually | Keeps consent, speech tests and rubric validation bounded |
| Audio retention | Auto-delete within 24h; optional 30-day replay consent | Storage and privacy exposure |
| Budget | Pilot $250–460/month illustrative scenario | Actual provider/model rate and measured usage control feasibility |
| Initial knowledge corpus | Small licensed backend/system-design corpus, manually reviewed | Retrieval quality and redistribution rights |
| Assessment meaning | Formative coaching, versioned category rubrics | Avoid unsupported employability claims |
| Availability | Pilot single-region, limited redundancy; harden before general release | Explicit reliability/cost limits |

No request for credentials, purchases, deployments or feature implementation is part of the current documentation task. Resolve review decisions in an architecture revision before beginning phase 1.

## Dependency order and release scope

Identity/ownership -> durable jobs -> ingestion/evidence -> licensed knowledge/rubrics -> reliable text interviews/evaluation -> optional voice -> durable graph -> learning/analytics -> hardening. Curation is available before RAG release; no placeholder citations or synthetic benchmark scores in user-facing claims. Use feature flags for voice, hosted inference and graph rollout. Migrate one workflow at a time with shadow evaluation on synthetic/consented data; avoid running two live orchestrators against one session.

Initial release excludes code execution, live video, facial/emotional analysis, employer rankings, external calendar/email agents, payments, multi-organization sharing, fine-tuning, full-duplex realtime audio, multilingual scoring and mobile clients. System-design answers are text/voice explanations; diagrams or whiteboards require a later explicit scope.

## Risk register

| Risk | Likelihood / impact | Mitigation and observable trigger | Accountable role |
| --- | --- | --- | --- |
| Hallucinated facts or citations | High / high | Authorized curated retrieval, quote validation, abstention; stop release if grounding gates fail | AI/domain lead |
| Biased or inconsistent scores | High / high | Anchored rubrics, blinded human comparisons, paraphrase/accent tests, no protected-trait scoring; block regression beyond stated threshold | AI/domain lead |
| Prompt injection through resume/corpus | High / high | Untrusted-context boundary, no open tools, ACL filters, adversarial suite; any unauthorized disclosure blocks release | Security/backend lead |
| Cross-user data leakage | Medium / critical | Scoped selectors, composite ownership rules, cache isolation, API+worker tests; one leak is a release blocker | Backend lead |
| Retry/checkpoint race duplicates turns | High / high | Database state machine, unique operation keys, leases/fencing, fault injection; duplicate domain effect blocks graph rollout | Backend lead |
| Provider downtime, 429s, model retirement | High / medium | Bounded retries, queue status, curated question/text fallback, adapter contract tests, model availability checks; alert error >5%/10min | Platform lead |
| Inference bill spikes | High / high | Atomic reservations, per-user caps, global hard stop, bounded context/graph; alert 80%, block at 100% budget | Platform/product owner |
| Slow CPU speech or inference | High / medium | Benchmark actual hardware, limited queue concurrency, text fallback; queue age >60s prompts capacity review | Platform lead |
| Noisy/accented speech transcription errors | High / high | User correction before scoring, subgroup benchmark, engine confidence caveats; WER/quality gates block unsupported claims | AI/frontend lead |
| Malicious PDF/DOCX/audio | Medium / critical | Quarantine, malware scan, no-network sandbox, decode limits and patched binaries; fail closed on scanner outage | Security/backend lead |
| Deletion misses vectors/checkpoints/backups | Medium / high | Erasure manifest, dependent artifact inventory, restore-time ledger replay, recurring sweeps; overdue purge alert | Privacy/platform owner |
| pgvector filter recall/capacity | Medium / medium | Scoped exact baseline, ANN-vs-exact benchmark, iterative scan/fallback; recall <0.90 or latency breach triggers tuning | Backend/AI lead |
| Corpus or voice/model license conflict | Medium / high | Track license/version/source, review redistribution and GPL obligations before enabling; missing approval blocks artifact | Product/legal reviewer |
| Version incompatibility / dependency CVE | Medium / high | Locked packages/model hashes, SBOM/scanning, staging upgrade/rollback tests; exploitable high/critical blocks release | Platform lead |
| Over-engineered scope / delayed MVP | High / medium | Text vertical slice first, bounded graph later, no microservices, per-phase gates; phase overrun prompts scope review | Engineering owner |
| Analytics misleads progress | Medium / high | Match rubric/difficulty, disclose counts/confidence, no trend under 3 samples; fixture/review mismatch blocks dashboard | Product/AI lead |
| Insufficient recovery on low-cost hosting | Medium / high | Cost reliability separately, measured restore drills, managed PITR before production; missed RPO/RTO blocks public launch | Platform lead |

Roles may be held by the same engineer initially, but a named person and independent security/domain reviewer must be assigned before launch. Review risks each phase and after incidents/provider changes.

## Production acceptance

An adult pilot learner can register/verify, manage their profile, upload and review a resume, analyze a JD, inspect evidence-backed gaps, complete a personalized interview in any supported category, optionally record/correct voice answers, receive grounded feedback, follow an evidence-linked learning plan, and view comparable progress. They can export/delete their data; another learner cannot access it through API, storage, retrieval, tasks or caches.

Release additionally requires documented SLO evidence, successful upgrade/rollback and restore+erasure drills, monitored budget caps, approved corpus/model licenses and provider data terms, accessibility checks, staff MFA, and benchmark reports with failure cases. The product must explain uncertain/incomplete scores and transcript limitations. See [testing strategy](TESTING_STRATEGY.md) for measurable thresholds and [architecture](ARCHITECTURE.md#operational-cost-model) for cost sensitivity.
