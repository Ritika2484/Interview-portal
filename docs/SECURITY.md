# Security, authorization and privacy

Status: requirements for implementation and release, not claims of current controls. Defaults are product proposals; deployment jurisdiction, contracts and legal obligations require review before public launch. This document does not assert regulatory certification.

## Threat model and trust boundaries

Protect credentials, resumes, job descriptions, voice recordings, transcripts, interview answers, feedback, learning history, provider secrets and operational budgets. Treat the browser, every uploaded file, retrieved document, model response and external provider as outside the trusted application boundary.

Primary threats: account takeover, enumeration, cross-user object access, malicious documents/archives, prompt injection, unauthorized retrieval, leaked signed URLs, XSS/CSRF, SSRF, supply-chain compromise, stolen provider credentials, resource exhaustion, task replay, and data retained after deletion. Controls apply to both synchronous API routes and asynchronous workers; moving work into a queue never bypasses ownership checks.

## Authentication

Use a custom Django User with case-insensitive unique email from the first migration. Verify email before accepting personal documents or running inference. Hash passwords with Django's Argon2id hasher configured first, with supported fallback hashers for upgrades. Passwords: 12–128 characters, Django common/similarity validators, paste and password managers allowed, no arbitrary periodic resets. Never log passwords or reset links.

Use database-backed Django sessions, Secure/HttpOnly/SameSite=Lax cookies scoped to host with no broad Domain. CSRF token is accessible to the client and sent in `X-CSRFToken`; validate trusted origins and CSRF on all unsafe methods, including login/logout/register/password reset. CORS off for same-origin deployment; never use credentialed wildcard origins. Set idle timeout 12 hours, absolute lifetime 7 days, and recent reauthentication <=10 minutes for exports, account deletion and logout-all. Session middleware must enforce these proposed limits explicitly; Django defaults alone do not implement every policy.

Rotate session ID on login, revoke current session on logout and all sessions on password reset/account deletion. Maintain user-session lookup for revocation. Verification/reset tokens are random, hashed at rest, single-use and purpose-scoped; verification expires in 24 hours, reset in 30 minutes. Generic registration/reset/resend responses reduce enumeration; normalize timing where practical. Reject login without verification using a generic safe error and a resend path. Apply IP/account rate limits without enabling permanent attacker-triggered account lockout.

Staff use separate protected admin access, mandatory MFA through a maintained integration or identity-aware proxy, no shared accounts, short sessions and recovery codes stored securely. User MFA and OAuth are future enhancements; staff MFA is a launch gate.

## Authorization matrix

| Capability | Anonymous | Verified learner | Curator | Operations administrator |
| --- | --- | --- | --- | --- |
| Register/login/reset | Public with CSRF/rate limits | Own account | Own account | Own account |
| Private profile/resume/JD/interview/media/plan | None | Own only | Own only | No content access by default |
| Read published reference excerpts | None | Through authorized use | Yes | Health/metadata only |
| Publish knowledge/rubrics/resources | None | None | Explicit model permissions | Only if separately granted curator role |
| Retry infrastructure jobs/inspect metrics | None | Own allowed operations | Own only | Scoped operational metadata |
| Export/delete personal data | None | Own + recent auth | Own + recent auth | Audited support workflow, no bulk content browsing |

Curator and ops are permission bundles, not automatic implications of `is_staff`. Disable broad Django admin registration for sensitive content. Emergency access requires time-limited elevated permission, reason, independent approval and audit; no standing all-resume access. Superuser credentials are break-glass only. Initial deployment has individual ownership, not organization tenants; organization membership must not later be inferred from email domain.

Scope every ORM read before serialization and every background job at execution and commit. Validate cross-resource ownership, nested routes, media purpose and source scope. UUIDs are not authorization. Signed storage URLs are issued only after authorization and expire within 60 seconds; do not log query strings. Strip cookies/auth headers on external calls. Cache keys include owner and content/model version; personalized results never enter global caches.

## Input, upload and browser controls

Resume limits: PDF/DOCX, 10 MiB, 50 pages, 200,000 extracted characters. Audio: allowed codecs only, 20 MiB, five decoded minutes per turn. Enforce at proxy, stream reader, parser and decoded-content layers. Sniff MIME/signature, validate archive structure/compression ratio, reject macros, encrypted files, malformed containers and extension/content mismatch. DOCX extraction ignores external relationships and embedded objects. Resume names are display metadata only; generate random storage keys and normalize download names.

Uploads start in private quarantine. Malware scan fails closed: unavailable scanner leaves pending/retryable, not clean. Run parsers, FFmpeg and scanners with no outbound network, restricted filesystem, CPU/memory/time limits, non-root identity and read-only root. Do not execute embedded scripts, resume code samples or uploaded binaries. Reject scanned-image resumes with an OCR-not-supported explanation initially. Decompression/time limit tests are release gates.

Use parameterized ORM/SQL, serializer allowlists and bounded filters. Never `eval` model outputs or deserialize arbitrary pickle/checkpoint objects. Render plain text or sanitized restricted Markdown; disable raw HTML and script URLs. Set CSP (restrict scripts/connect/media origins), HSTS after HTTPS validation, `X-Content-Type-Options: nosniff`, restrictive `Referrer-Policy`, clickjacking protection and microphone Permissions-Policy for self. Microphone access is requested only after user action. Keep file downloads `Content-Disposition: attachment` where appropriate. Avoid storing personal content in browser analytics, service-worker caches and session replay tooling.

## AI and agent controls

- Treat documents and retrieved text as untrusted quoted evidence, not instructions. Delimit context and keep system policy separate. Injection detection is advisory; tool restrictions and access control are the enforcement boundary.
- Retrieval filters owner/scope before sending context to a model. Shared corpus publication requires curator review and license metadata. Do not index users' answers into a shared corpus.
- Allowlist tools to typed domain services; no arbitrary SQL, shell, web browsing, filesystem reads, email, code execution, or generated URL fetching. Model-generated IDs are validated against the operation's authorized input set.
- Enforce Pydantic schemas, bounded strings/scores, citation offsets, reference ownership, graph transition rules and step/token/spend budgets. Unsupported facts trigger abstention/provisional evaluation. Do not expose hidden prompts, private rubrics during an interview, internal traces or chain-of-thought.
- Redact contact details and unnecessary identifiers before hosted calls. Redaction reduces disclosure but does not guarantee de-identification; resumes and answers can remain identifiable.
- Provider endpoints and region are deployment allowlists. Never accept arbitrary user-supplied base URLs. Hosted fallback is prohibited unless the consent/data-processing policy permits that exact provider class and region.
- Keep provider keys in secret storage, rotate them, scope projects, configure vendor spend limits and reconcile metered usage. Use per-attempt accounting and atomic budget reservations; client-side caps are insufficient.
- Pin prompt/schema/model/rubric versions, run regression evaluations before changes, and review dependency/model licenses and downloads. No training or fine-tuning on personal data without a separate future opt-in policy.

## Consent and data minimization

Show a clear notice before uploading a resume and before recording audio. Recording consent is separate from optional storage of audio. Hosted inference requires disclosure of categories sent, provider/subprocessor, purpose, region and retention terms; if declined, offer local/text capability where available or explain the unavailable feature. Browser/device TTS may involve an OS vendor and requires a separate disclosure.

Default to retaining transcript/corrected answers rather than raw audio. Do not collect government IDs, birth dates, demographic attributes or unrelated employment data. Exclude protected traits from prompts/scoring; do not infer emotion, health, honesty, personality or employability from voice. Allow user review of extracted skills and transcripts. User consent revocation blocks new dependent calls and cancels queued work; already transmitted provider data follows the agreed provider policy, which must be explained honestly.

No production data in development/test. Synthetic fixtures and separately consented benchmark recordings only. Do not send sensitive payloads to optional tracing SaaS by default. Providers must be reviewed for contractual data use, retention, deletion mechanisms and regional processing; do not claim zero retention without a verified agreement.

## Retention and deletion

Proposed defaults, configurable centrally and visible in product policy:

| Data | Default retention | Required handling |
| --- | --- | --- |
| Rejected/quarantined files | <=24 hours after failure | Purge file and parser intermediates; safe failure metadata only |
| Raw user audio and normalized intermediates | Delete within 24h after transcription | Optional explicit retention up to 30 days for replay; no indefinite retention |
| Generated question audio | <=7 days cache | Owner-scoped, purge with source question/session |
| Resumes/JDs/extracted analyses/private vectors | Until user deletes or account inactive 12 months | Notify 30 days before inactivity purge; deleting source cascades private derivatives |
| Answers/transcripts/evaluations/learning history | Until deletion or same inactivity policy | Include checkpoints, excerpts, caches and analytics in deletion |
| Operational job payloads/results and AI attempt diagnostics | 30 days after terminal state | Preserve only minimized provenance needed by retained reports; aggregate content-free cost statistics may remain |
| Idempotency replay metadata | 24 hours | No raw sensitive response copies |
| Privacy export artifact | <=24 hours | Authenticated, short-lived download, auto-delete |
| Security audit metadata | 90 days | Minimize/pseudonymize subjects, restricted access |
| Encrypted backups | Rolling 30 days | Expiry enforced; restored data remains blocked until erasure replay |

Retain minimized model/prompt/schema/rubric version, usage totals and reference IDs for as long as a dependent analysis or evaluation exists, so operational cleanup does not break provenance foreign keys. Remove detailed diagnostics after 30 days; private provenance is still purged with its source/account. Prompt templates are versioned code assets, not retained copies of private input prompts.

On deletion request: revoke sessions or block affected resources immediately, fence/cancel queued and running jobs, and record an erasure manifest. Within seven days purge live database content, objects and versions, private chunks/vectors, graph checkpoints, caches, exports, evaluation excerpts and learning/analytics derivatives. Resumes/JDs used by active sessions invalidate/cancel those sessions. Dependent reports are invalidated/purged, not left as copies of erased content. Account exports include original documents, structured analyses, answers, scores, plans and consent history in portable JSON plus files; exclude secrets and others' corpus content.

Backup copies expire within 30 days; user-facing policy distinguishes immediate loss of access, live purge deadline and backup expiry. Minimal erasure receipts contain random subject reference, request time and completion state, never deleted content. Maintain an erasure ledger outside ordinary restore rollback scope so restoration can reapply deletions before serving traffic. Provider deletion is requested where supported/contracted; expose any unavoidable vendor retention period. Alert on overdue erasure and verify object-version cleanup. Revocation/deletion racing with inference must prevent committing the returned result.

## Operational security and incident response

TLS for external traffic and database/broker connections where supported; encryption at rest for database, objects and backups using managed keys. Separate production/staging accounts, databases, buckets and credentials. Private network for data services, no public broker or admin DB port. Least-privilege runtime DB role; separate migration role and restricted checkpoint schema access. Secrets never in images, frontend bundles, repository, errors or logs. Secret scanning and dependency/container scanning run in CI; lockfiles, model hashes and an SBOM record supply chain inputs.

Use structured audit events for auth, consent, access elevation, publication, export/deletion, operational overrides and budget changes. Redact request bodies by default. Alerts go to operators through an established incident channel configured at deployment; this design does not send messages. Incident procedure: triage -> contain/revoke keys/sessions -> preserve minimal evidence -> assess affected users/data -> recover and replay deletion ledger -> communicate according to applicable obligations -> post-incident fixes and regression tests. Assign named incident and privacy owners before launch.

Security gate: no unresolved critical/high exploitable findings; cross-owner denial tests for every route/worker; staff MFA; restore+erasure drill; verified provider contracts/consent; rate/budget enforcement; malware fail-closed; and tested secret rotation. Full test mapping is in [testing strategy](TESTING_STRATEGY.md).
