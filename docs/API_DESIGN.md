# REST API design

Status updated 2026-11-26: health, authentication, owner profiles and current-data deletion are implemented, with development/testing OpenAPI/Swagger. Interview/resume/AI/learning/export/provider-consent endpoints below remain target contracts. A validated OpenAPI schema can be generated; no TypeScript client exists yet. Base path `/api/v1/`; JSON over HTTPS, UUID identifiers and UTC ISO-8601 timestamps. Session-cookie authentication is implemented. See [authentication scope](AUTHENTICATION.md) and [foundation history](PHASE_1_IMPLEMENTATION.md).

## Common contract

All endpoints require an authenticated, active, verified account unless marked public. Owners can access only their private records; foreign/missing IDs both return 404. Curator routes require scoped Django permissions; staff status alone does not grant private-content access. Standard permissions are described in [security](SECURITY.md).

Responses use resource objects, not a global success wrapper. Lists return `{ "results": [], "next": null, "previous": null }` with opaque cursor pagination, default 20/max 100; sort `(created_at DESC,id DESC)`. API allowlists filters and ordering fields. Decimal scores are JSON numbers, never NaN; absent/unscorable results are null. Unknown input fields are rejected to catch client errors. User-supplied strings are plain text, never trusted HTML.

Errors use `application/problem+json`:

```json
{
  "type": "urn:interview-platform:problem:state-conflict",
  "title": "The turn no longer accepts answers",
  "status": 409,
  "code": "TURN_STATE_CONFLICT",
  "detail": "Refresh the session before continuing.",
  "request_id": "req_opaque",
  "errors": {}
}
```

400 malformed/validation input; 401 unauthenticated (normalize DRF session behavior); 403 CSRF/permission/consent denial; 404 absent or foreign; 409 state conflict or idempotency key reuse with different payload; 412 stale `If-Match`; 413 size exceeded; 415 unsupported media; 429 rate/quota limit with `Retry-After`; 503 temporarily unavailable. A provider failure after acceptance appears as a failed job, not a changed original 202 response. Never leak parser traces, prompts or provider secrets.

`Idempotency-Key` is mandatory on asynchronous POST commands, answer submission and session state commands. Scope by owner+route for 24h. Same key and payload replays original status and resource/job ID; changed payload returns 409. Duplicate domain operations remain deduplicated beyond this window by unique operation keys. Set `If-Match: "<version>"` on session commands and mutable profile/task edits; missing header returns 428, stale header 412. POST resource creation does not require If-Match.

Asynchronous success returns 202 plus `Location: /api/v1/operations/{id}/` and `{ "operation_id": "...", "resource_id": "...", "status": "pending", "poll_after_ms": 1500 }`. A completed synchronous resource creation returns 201 with its Location. DELETE commands are idempotent; first erase request returns 202 and operation, repeated pending request returns the same operation, already purged authorized resource returns 204 where ownership can still be established by content-free tombstone. Otherwise missing/foreign returns 404.

## Authentication and account contracts

Implemented 2026-11-26 unless a row below explicitly says planned. [Authentication guide](AUTHENTICATION.md) gives payloads and PowerShell examples. All unsafe routes, including anonymous authentication, require CSRF. Responses contain no raw login bearer token: the server sets an HttpOnly session cookie. Common errors, cookie security and CSRF/If-Match parameters appear in generated OpenAPI. Current profiles use the requested field names below rather than earlier proposed aliases.

| Method / route | Request | Success / permission |
| --- | --- | --- |
| GET `/auth/csrf/` | none | 200 `{csrf_token}` plus CSRF cookie; public, no cache |
| POST `/auth/register/` | email, password, display_name, accepted_policy_version | 202 generic message; public; creates unverified candidate; durable email intent; unverified accounts cannot log in |
| POST `/auth/verify-email/` | token | 200 `{verified:true}`; public, single-use hashed token |
| POST `/auth/resend-verification/` | email | 202 generic message; public |
| POST `/auth/login/` | email, password | 200 `{user:{id,email,display_name},session_expires_at}`; public + CSRF; session cookie rotated |
| POST `/auth/logout/` | none | 204; revoke current session |
| POST `/auth/logout-all/` | none | 204; recent password reauthentication |
| POST `/auth/password-reset/` | email | 202 generic message; public, enumeration resistant |
| POST `/auth/password-reset/confirm/` | token, new_password | 204; public; revoke existing sessions |
| POST `/auth/reauthenticate/` | password | 204; refresh server-side recent-auth marker |
| GET `/me/` | none | 200 User + nested Profile + ETag; optional provider consent remains future |
| PATCH `/me/` | display_name, timezone, target_job_role, experience_level, technical_skills, interview_preferences, preparation_goals, preferred_interview_language | 200 User with nested versioned Profile; CSRF + If-Match |
| POST `/me/consents/` | purpose, granted:boolean, policy_version | Planned; registration currently records policy acceptance only |
| POST `/me/exports/` | none | Planned; no export endpoint yet |
| DELETE `/me/` | `{confirmation:"delete-account"}` | 202 already-completed current-data erasure receipt; recent auth; revoke sessions |
| DELETE `/me/personal-data/` | `{confirmation:"delete-personal-data"}` | 202 completed receipt; clears profile/token/email artifacts, keeps login identity/policy acceptance, revokes sessions |
| GET `/privacy-requests/{id}/` | X-Deletion-Receipt header | 200 content-free status; missing/wrong/expired proof returns 404; hashed receipt expires in 30 days |
| GET `/admin/account-stats/` | none | Administrator-only aggregate count; production access disabled pending staff MFA |

All unsafe cookie-based requests, including public login/register/reset, require a valid CSRF token and origin validation. Registration does not log in. Password length 12–128 plus Django validators; email max 254 characters, display_name max 100, IANA timezone validated. Email changes and external OAuth are deferred; no hidden email change in PATCH `/me/`.

Current privacy commands perform small synchronous database erasures and return a terminal receipt (id, kind, state, timestamps, receipt and status_url); they do not return a generic operation_id. Other async/idempotency contracts remain future domain design. GET /me/ returns id/email/role/email_verified_at plus nested profile and an ETag. JWT refresh is unnecessary: idle session renewal is bounded by seven-day absolute expiry. Logout is CSRF-protected and idempotent even for an anonymous client. See the authentication guide for profile bounds and rate limits.

## Resumes, job descriptions and gaps

| Method / route | Request / behavior | Success |
| --- | --- | --- |
| GET/POST `/resumes/` | list; POST multipart `file`, `label` | 200 list / 202 resume+version ingestion operation |
| GET/DELETE `/resumes/{id}/` | retrieve summary/current version; erase source and derivatives | 200 / 202 |
| POST `/resumes/{id}/versions/` | multipart file; append immutable version | 202 ingestion operation |
| GET `/resumes/{id}/versions/{version_id}/` | extraction status and safe extracted text for owner | 200 |
| GET `/resumes/{id}/versions/{version_id}/analyses/` | successful/failed analysis metadata | 200 list |
| POST `/resumes/{id}/versions/{version_id}/analyses/` | `{}`; retry/new analysis explicitly | 202 |
| GET `/resume-analyses/{id}/` | structured observations, evidence spans, caveats | 200 |
| POST `/resume-analyses/{id}/corrections/` | skill_id, evidence_text, asserted_level_optional | 202 revised analysis; user-confirmed provenance |
| GET/POST `/job-descriptions/` | list; POST `{label,title,text,company?}` | 200 / 202 version+analysis operation |
| GET/DELETE `/job-descriptions/{id}/` | retrieve / erase | 200 / 202 |
| POST `/job-descriptions/{id}/versions/` | `{title,text,company?}` | 202 append+analyze |
| GET `/job-descriptions/{id}/versions/{version_id}/` | version metadata/text/analysis IDs | 200 |
| GET `/job-analyses/{id}/` | normalized requirements and evidence | 200 |
| POST `/job-descriptions/{id}/versions/{version_id}/analyses/` | `{}`; explicit retry/new revision | 202 |
| GET/POST `/gap-analyses/` | list; POST resume_analysis_id, job_analysis_id | 200 / 202 |
| GET `/gap-analyses/{id}/` | coverage, skill states/evidence and algorithm version | 200 |
| GET `/skills/?query=` | normalized skill taxonomy; query max 100 chars | 200 paginated list |

PDF/DOCX only, max 10 MiB, max 50 pages, bounded extracted text 200,000 characters; detect file type and ZIP inflation independent of extension. Ingestion operation includes scan, extraction and first analysis stages; status detail reports each. Invalid or encrypted documents fail asynchronously with safe actionable error codes. No download until scan succeeds. JD text 100–50,000 characters; label/title max 200. A version may be processing; analysis creation against incomplete extraction returns 409.

Gap response fragment:

```json
{
  "id": "b205c4ea-bd79-44fa-bb18-ac0d68908e19",
  "coverage": 62.5,
  "algorithm_version": "weighted-evidence-v1",
  "items": [{
    "skill_id": "8c3b287d-dcc7-4814-b38c-c76d4066a457",
    "state": "not_evidenced",
    "priority": "required",
    "evidence": [],
    "explanation": "This resume does not provide evidence of this skill."
  }]
}
```

## Interview contracts and state

| Method / route | Request / behavior | Success |
| --- | --- | --- |
| GET/POST `/interviews/` | list; create configuration below | 200 / 201 draft session |
| GET `/interviews/{id}/` | state, version, counts, current_turn, allowed_actions, operation IDs, expires_at | 200 + ETag |
| POST `/interviews/{id}/start/` | `{}`; freeze blueprint and input versions | 202 prepare operation; If-Match |
| GET `/interviews/{id}/turns/` | authorized question history and own answers | 200 list; grading/reference fields hidden until completed |
| POST `/interviews/{id}/turns/{turn_id}/answers/` | `{text}` OR `{transcript_revision_id}` | 202 accepted immutable answer + evaluation operation; If-Match on session |
| POST `/interviews/{id}/turns/{turn_id}/skip/` | `{reason?}` max 200 chars | 202 next-step operation; If-Match |
| POST `/interviews/{id}/complete/` | `{}`; end early with coverage caveat | 202 summary operation; If-Match |
| POST `/interviews/{id}/cancel/` | `{}` | 202 cancel operation; If-Match |
| GET `/interviews/{id}/summary/` | completed summary, score dimensions, uncertainty and evidence | 200; 409 until completed |
| DELETE `/interviews/{id}/` | purge session/answers/audio/checkpoints/derivatives | 202 |
| GET `/evaluations/{id}/` | authorized evaluation with rubric and citations | 200 only after session completed; otherwise 409 |
| POST `/evaluations/{id}/revisions/` | `{reason}` max 500 chars; new evaluation, not overwritten | 202; completed session only, quota-limited |

Create request:

```json
{
  "resume_analysis_id": null,
  "job_analysis_id": null,
  "gap_analysis_id": null,
  "target_role": "Backend engineer",
  "seniority": "intermediate",
  "track_mix": {"technical": 0.5, "behavioral": 0.2, "hr": 0.1, "system_design": 0.2},
  "modality": "text",
  "question_count": 10,
  "duration_minutes": 30,
  "locale": "en"
}
```

Track keys are fixed; nonnegative proportions sum to 1 with at least one positive entry. Question count 5–20 includes follow-ups. Duration 10–60 minutes. Analysis inputs are optional for generic practice; when supplied must be ready and owned. If a gap is supplied its resume/JD references must match any explicit references. Target role max 200. Question retrieval never accepts a client-supplied corpus scope.

Answer text 1–20,000 characters; exactly one of text or transcript_revision_id. Resolve canonical text server-side; ignore client scores, difficulty and timing claims. Answer submission schedules evaluation and then advancement as one logical operation chain. Polling returns resource/session IDs and current session version; the client refreshes the session before the next command. No separate client "generate next" call, which would race with automatic advancement.

Session progression and concurrency rules are in [database design](DATABASE_DESIGN.md#transactions-and-state-transitions). A second answer to a turn with a different idempotency key returns 409. A stale ETag returns 412 before mutation. Do not allow skip/complete to race past an accepted answer; complete returns 409 while evaluation is pending, or the user can cancel. Server expiry settles accepted work then completes without generating additional turns.

## Voice, media and citations

| Method / route | Request / behavior | Success |
| --- | --- | --- |
| POST `/interviews/{id}/turns/{turn_id}/transcriptions/` | multipart audio file + consent policy version | 202 scan/decode/STT operation |
| GET `/transcriptions/{id}/` | status, raw transcript, segments and latest revision | 200 |
| POST `/transcriptions/{id}/revisions/` | `{text}`; corrected draft, 1–20,000 chars | 201 immutable revision |
| POST `/interviews/{id}/turns/{turn_id}/speech/` | `{voice,locale}` from server allowlist | 202 TTS operation or 200 cached artifact |
| GET `/media/{id}/download/` | authorized clean media only | 200 `{url,expires_at}`; signed URL TTL <=60 seconds, no-store |
| DELETE `/media/{id}/` | erase optional audio; transcript stays unless session erased | 202; invalidates dependent cached playback |
| GET `/citations/{id}/` | retained authorized evidence excerpt + title, version, location, source URL | 200; linked evaluation visible; 410 if source removed |

Voice accepts WebM/Opus or MP4/AAC, maximum 20 MiB and five decoded minutes per turn. Multipart upload uses application proxy initially; enforce streaming limits before buffering. A successful STT operation does not submit an answer. User selects a reviewed revision through the normal answer contract. Voice attempts attach only to an awaiting turn and never advance it automatically. Citation endpoints expose excerpts within permitted rights, not arbitrary full source downloads. Private-source deletion returns a content-free tombstone rather than leaked historical text.

## Learning, analytics and operations

| Method / route | Request / behavior | Success |
| --- | --- | --- |
| GET/POST `/learning-plans/` | list; POST `{session_id? ,gap_analysis_id?,weekly_minutes}` with at least one source | 200 / 202 plan proposal; minutes 30–1200 |
| GET `/learning-plans/{id}/` | tasks, source evidence, reviewed resources and revision | 200 |
| PATCH `/learning-plans/{id}/` | status active/archived | 200; If-Match |
| PATCH `/learning-tasks/{id}/` | status, due_date_optional | 200; If-Match; completion time server-generated |
| DELETE `/learning-plans/{id}/` | erase plan/tasks | 202 |
| GET `/analytics/overview/?from=&to=` | ISO dates; max range 366 days | 200 counts, breakdown, freshness and methodology |
| GET `/analytics/progress/?skill_id=&track=&rubric_version=&difficulty=` | same date bounds, comparable cohort filters | 200 points, sample sizes and exclusions |
| GET `/operations/{id}/` | status, stage, progress 0–100 or null, resource_id, result_url, safe error, retryable | 200 owner only; no model prompt or internal checkpoint |
| POST `/operations/{id}/retry/` | `{}`; failed retryable operation only | 202 same logical operation/new attempt; enforce total budget |
| POST `/operations/{id}/cancel/` | `{}`; cooperative cancellation | 202; completed =>409; committed domain work is not rolled back |

Full-session answer processing is a composite operation: do not expose partial evaluation payloads through generic result URLs before session completion. Deletion operations are not user-cancelable once accepted and continue after logout; their failures are retried operationally until resolved. The cancel endpoint returns 409 `OPERATION_NOT_CANCELABLE` for erasure work. Signed deletion receipts provide only status, never deleted data. Privacy export download artifacts expire within 24h and require recent authentication.

Curator contracts: GET/POST `/admin/knowledge-sources/` (metadata + licensed text); POST `/admin/knowledge-sources/{id}/versions/`; POST `/admin/knowledge-source-versions/{id}/publish/`; DELETE `/admin/knowledge-sources/{id}/`; GET/POST `/admin/learning-resources/`; PATCH `/admin/learning-resources/{id}/`; GET/POST `/admin/rubric-versions/`; POST `/admin/rubric-versions/{id}/publish/`. Writes are audited, curator permission required, use idempotency keys; publishing/ingestion returns 202 and immutable versions. No route accepts arbitrary fetch URLs or executable templates. These curation APIs are release prerequisites for managed content, implemented in phase 3.

Unauthenticated internal health routes: `/health/live/` returns 200 if process alive; `/health/ready/` reports only ready/not-ready and checks DB/required configuration. Detailed dependency status and `/metrics/` are private-network/ops authenticated. Readiness does not call external models on every probe.

## Quotas and compatibility

Initial configurable defaults: login 5 attempts/minute per account+IP with progressive delays; reset/resend 3/hour per account+IP; reads 120/minute/user; writes 30/minute/user; uploads 10/hour/user; one active session/user; two pending expensive operations/user; 20 sessions/user/day; 60 audio minutes/user/day. Apply edge IP limits and distributed application limits. Limits return stable error codes and reset metadata; administrator overrides are audited. Spend limits are an additional hard server-side guard, independent of request count.

Additive nullable output fields are compatible; removing fields, changing enum semantics, score meaning or authentication requires a documented migration/deprecation or new API version. Validate request/response examples and permission behavior against OpenAPI in CI. Locale expansion, streaming transport, organization tenancy, billing, OAuth/mobile tokens and public integrations require explicit future contracts.
