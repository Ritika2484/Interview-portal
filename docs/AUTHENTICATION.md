# Phase 2: authentication and user management

Implemented 2026-11-26. This milestone follows the user's current Phase 2 request; the original architecture roadmap's resume/JD milestone is still future work. No AI features were added.

## Design and migration decisions

Keep the initial UUID/email custom User and its case-insensitive uniqueness constraint. Migration `accounts.0002_authemaildelivery_authtoken_deletionrequest_and_more` adds roles and revocation version plus Profile, PolicyAcceptance, AuthToken, UserSession, AuthEmailDelivery and DeletionRequest. Existing UUIDs, emails and password hashes are preserved. Existing staff/superusers become administrators; profiles are backfilled in batches. Legacy Django sessions are intentionally deleted to require a fresh login with revocation tracking. This is a data migration, not a replacement of the original user model or initial migration. Upgrade tests exercise an existing staff/candidate database.

Use the documented session alternative to JWT: database-backed opaque cookies, HttpOnly/SameSite=Lax, Secure in production. No bearer credentials go into localStorage or JSON login responses. Login rotates session and CSRF secrets. Each session has a server-side owner, auth version, last activity and immutable absolute expiry. Idle expiry is 12 hours; absolute expiry is seven days. Logout deletes the current session; logout-all, reset, role changes and erasure revoke all tracked sessions and advance the account auth version. Session checks also run on read requests. A revoked in-flight mutation rechecks the locked user/session before writing. A response already read cannot be recalled.

Passwords use the existing Argon2 configuration; password validators and the 12–128-character API bounds apply to registration/reset. Tests use a fast hasher except for an explicit real Argon2 test. Login accepts normalized email only after verification and checks account activation/deletion state. Wrong passwords, unknown addresses, unverified accounts and inactive accounts return the same credential error. Registration and recovery return generic 202 messages; duplicate registration never replaces an existing password/profile. Hashing cost is paid for duplicate registration and unknown login. These controls reduce timing differences; they do not claim perfectly constant response times.

This design uses [Django database sessions](https://docs.djangoproject.com/en/5.2/topics/http/sessions/) and explicit CSRF protection around all unsafe account routes, including anonymous login/register/reset. DRF session authentication alone is insufficient for anonymous login CSRF, as described in its [authentication documentation](https://www.django-rest-framework.org/api-guide/authentication/). CSRF is refreshed after login; CORS remains an explicit allowlist. Authentication responses use no-store; error bodies are structured problems with safe details. Application logging omits bodies, cookies, email addresses, raw tokens and exception text.

## Roles and permissions

`candidate` is the only public registration role. `administrator` is provisioned by a trusted operator, never by registration/profile input. Database checks enforce candidate => no staff/superuser flags and administrator => staff. Unknown/read-only fields such as role, user_id, email, groups, is_staff and verification flags are rejected. Administrator is not automatically a Django superuser and has no blanket access to candidate profiles. Current administrative API access provides only aggregate active-account counts.

Production keeps Django admin disabled and blocks administrator API login/access until staff MFA/access controls exist. Candidate production login is supported with the required TLS/SMTP configuration. Development/testing permits administrator API verification. To change a verified active account's role locally:

```powershell
docker compose exec api python manage.py set_account_role <account-uuid> administrator
```

This revokes existing sessions. Demotion uses `candidate` and removes staff/superuser flags. The command does not grant superuser; restrict shell/database access independently. No public role-management endpoint exists.

## Current API

All routes below have prefix `/api/v1/`. Swagger documents payloads, error responses, session cookies and the CSRF header. Use a cookie-aware client; bootstrap CSRF before every unsafe operation in manual testing so login rotation is handled correctly.

| Method / route | Contract |
| --- | --- |
| GET `auth/csrf/` | Public `{csrf_token, policy_version}` plus CSRF cookie, no-store |
| POST `auth/register/` | email, password, display_name, accepted_policy_version; generic 202; persists unverified candidate and email intent |
| POST `auth/verify-email/` | token; 200 `{verified:true}`; single-use, no automatic login |
| POST `auth/resend-verification/` | email; generic 202; only eligible unverified accounts get an email |
| POST `auth/login/` | email/password; 200 `{user, session_expires_at}` plus session/rotated CSRF cookie; generic 401 on credential failure |
| POST `auth/password-reset/` | email; generic 202; eligible verified active accounts only |
| POST `auth/password-reset/confirm/` | token/new_password; 204; validates password, consumes all account tokens and revokes sessions; login again |
| POST `auth/logout/` | `{}`; CSRF-protected, idempotent 204, including an already anonymous client |
| POST `auth/reauthenticate/` | password; 204; refreshes the recent-password marker |
| POST `auth/logout-all/` | `{}`; recent authentication required; 204; current client is logged out too |
| GET `me/` | Verified current owner only; User and nested Profile; ETag is quoted profile version |
| PATCH `me/` | Flat profile fields; CSRF + `If-Match` required; 200 with updated ETag; 428 missing/412 stale precondition |
| DELETE `me/` | `{confirmation:"delete-account"}` + recent authentication; 202 completed erasure receipt |
| DELETE `me/personal-data/` | `{confirmation:"delete-personal-data"}` + recent authentication; reset profile/private account artifacts while retaining login identity; revokes sessions |
| GET `privacy-requests/{id}/` | `X-Deletion-Receipt` bearer proof; no normal session needed; only content-free status; wrong/missing/expired proof =>404 |
| GET `admin/account-stats/` | Verified administrator only, enabled in development/testing; aggregate count only |

Profile fields: display_name, timezone (IANA name), target_job_role, experience_level (beginner/intermediate/advanced), technical_skills (up to 50 distinct strings, 64 chars each), preparation_goals (up to 20 strings, 300 chars each), preferred_interview_language (a bounded language-tag preference), and interview_preferences. Preferences accept only categories (technical/behavioral/hr/system_design), modality (text/voice), question_count (5–20) and duration_minutes (10–60). Language/voice preferences do not mean those interview features are implemented. Email/roles/ownership are never profile edits. JSON array/object types, experience values, positive versions, role consistency, token purpose/expiry and pending-email uniqueness are database constrained.

Sensitive commands require password authentication within the last ten minutes; a successful login qualifies. Later use the reauthentication endpoint. Privacy commands are small synchronous database erasures in this phase: a 202 response already has state `completed`, plus `id`, `receipt` and `status_url`. They do not masquerade as queued generic domain operations. The receipt is returned once, hashed at rest, expires in 30 days and must not be put in URLs or logs. Losing it does not undo deletion.

## Email delivery and rate limits

Verification tokens have 256 bits of randomness and expire in 24 hours; reset tokens expire in 30 minutes. Only SHA-256 token hashes are stored. Tokens are purpose-scoped, invalidated by replacement, checked for active account/expiry, and consumed under user/token row locks; concurrent use succeeds once. A reset revokes all outstanding account tokens. Weak reset passwords do not consume a still-valid token.

HTTP requests commit PostgreSQL email intents, not raw email bodies or token-bearing Celery messages. A singleton Celery beat scheduler dispatches a poll every ten seconds. The worker locks the account, generates a fresh token in memory, stores its hash and sends SMTP. This bounded mail transaction holds the user lock during SMTP to serialize against deletion; it is not the pattern for future long-running AI calls. SMTP timeout is five seconds. Failed sends revoke the issued token and back off, at most five attempts. Pending records survive broker failure; a manual batch command is also available:

```powershell
docker compose exec api python manage.py process_account_emails
```

SMTP acceptance and database commit cannot be atomic. A crash can produce duplicate mail or an unusable link; use resend/recovery. No exactly-once delivery claim is made. Already delivered emails cannot be recalled. Future frontend links use a token fragment rather than a token query string; the frontend pages are not built yet, so manual clients submit the token in the email body to the API.

Compose starts Mailpit v1.34.0 at `http://127.0.0.1:8025`, SMTP on loopback host 1025, with no external relay and no persistent inbox volume. The local inbox retains up to 100 messages/one hour; it contains authentication secrets and is development-only. Host ports can be overridden with MAILPIT_WEB_PORT/MAILPIT_SMTP_PORT. Container SMTP remains mailpit:1025. Native Django uses EMAIL_HOST/EMAIL_PORT. Production requires configured STARTTLS SMTP, DEFAULT_FROM_EMAIL and an HTTPS AUTH_PUBLIC_BASE_URL; SMTP credentials remain server-side environment secrets. Mailpit is not a production mail provider.

Limits use one atomic Redis Lua operation across independently keyed IP/account or IP/user buckets. Keys are HMACs, not raw emails/IPs. Defaults: login 5/minute/account and 30/minute/IP; registration 3/hour/address and 20/hour/IP; resend/reset share 3/hour/address and 20/hour/IP; token/CSRF routes 60/minute/IP; reauthentication 5/minute/user; other account operations 120/minute/user and 300/minute/IP. Fixed windows do not become permanent account lockouts. Rate-limited responses are 429 with Retry-After. Redis failure returns 503 rather than disabling protection. Remote address is server-provided; X-Forwarded-For is ignored. Configure trusted ingress address handling before production. Edge rate limits remain an additional deployment control.

## Deletion and retention boundaries

Account erasure locks the owner, revokes tracked sessions, deletes tokens/email intents, and hard-deletes the User and cascaded Profile, policy acceptance and group/permission associations. A random completion receipt remains with owner NULL and no email, user UUID or copied profile. Personal-data erasure instead resets every profile field, removes tokens/pending/delivered email intent records, revokes sessions, and retains email/password/role/verification plus policy acceptance to keep the account usable. The response and guide explicitly distinguish that retained identity from complete account erasure.

Current feature apps do not yet hold resumes, interviews, vector chunks, media or learning history. When those models arrive, their erasure handlers must be added before release; this phase does not claim to purge nonexistent future storage. Requests already transmitting email may finish before erasure takes the lock; delivered messages follow recipient/provider retention. HMAC abuse-prevention counters expire within an hour; no profile or token payload is cached. Restore-time erasure-ledger replay and managed backup expiry remain production work, not an assertion that historical backups are erased now.

Hourly cleanup prunes tokens expired more than a day ago, terminal email-intent metadata older than seven days, expired 30-day receipts, and expired Django sessions, in bounded batches. There is no infinite raw-token log/archive. Monitor pending/failed email intents and run one beat scheduler; local worker startup depends on beat/Mailpit so standard Compose instructions include delivery.

## Manual API testing with Windows PowerShell

Start/rebuild with `docker compose up --build --wait --wait-timeout 240 api worker`. Use the API_PORT from local `.env` (this workspace uses 8001). Do not discard database volumes to apply the migration. Swagger is `/api/v1/docs/`; inbox is port 8025.

```powershell
$base = 'http://127.0.0.1:8001/api/v1'
$web = New-Object Microsoft.PowerShell.Commands.WebRequestSession
function Get-AccountCsrf {
    (Invoke-RestMethod "$base/auth/csrf/" -WebSession $web).csrf_token
}
function Send-AccountPost($path, $body) {
    $headers = @{ 'X-CSRFToken' = (Get-AccountCsrf) }
    Invoke-RestMethod "$base/$path/" -Method Post -WebSession $web `
        -Headers $headers -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 5)
}
$email = Read-Host 'Your test email'
$securePassword = Read-Host 'Password (12-128 characters)' -AsSecureString
$password = [System.Net.NetworkCredential]::new('', $securePassword).Password
$policy = (Invoke-RestMethod "$base/auth/csrf/" -WebSession $web).policy_version
Send-AccountPost 'auth/register' @{
    email=$email; password=$password; display_name='Test candidate'; accepted_policy_version=$policy
}
# Wait up to a polling interval, then read the verification token in Mailpit.
Start-Process 'http://127.0.0.1:8025'
$verification = Read-Host 'Verification token from the email'
Send-AccountPost 'auth/verify-email' @{ token=$verification }
Send-AccountPost 'auth/login' @{ email=$email; password=$password }
Invoke-RestMethod "$base/me/" -WebSession $web
```

For profile PATCH, obtain both the current profile version and a fresh CSRF token. PATCH uses **flat** profile inputs; the response nests them under `profile`:

```powershell
$me = Invoke-RestMethod "$base/me/" -WebSession $web
$headers = @{ 'X-CSRFToken'=(Get-AccountCsrf); 'If-Match'=('"{0}"' -f $me.profile.version) }
$profileUpdate = @{
    target_job_role='Backend engineer'; experience_level='intermediate'
    technical_skills=@('Django','PostgreSQL'); preparation_goals=@('Practice system design')
    preferred_interview_language='en'
    interview_preferences=@{ categories=@('technical','system_design'); modality='text'; question_count=10 }
}
Invoke-RestMethod "$base/me/" -Method Patch -WebSession $web -Headers $headers `
    -ContentType 'application/json' -Body ($profileUpdate | ConvertTo-Json -Depth 5)

Send-AccountPost 'auth/password-reset' @{ email=$email }
$resetToken = Read-Host 'Reset token from the new Mailpit email'
$secureNewPassword = Read-Host 'New password' -AsSecureString
$newPassword = [System.Net.NetworkCredential]::new('', $secureNewPassword).Password
Send-AccountPost 'auth/password-reset/confirm' @{ token=$resetToken; new_password=$newPassword }
# The old cookie now gets 401. Login again with the new password.
Send-AccountPost 'auth/login' @{ email=$email; password=$newPassword }
Send-AccountPost 'auth/reauthenticate' @{ password=$newPassword }

# This intentionally deletes the current test account and its personal data.
$receipt = Invoke-RestMethod "$base/me/" -Method Delete -WebSession $web `
    -Headers @{ 'X-CSRFToken'=(Get-AccountCsrf) } -ContentType 'application/json' `
    -Body (@{confirmation='delete-account'} | ConvertTo-Json)
Invoke-RestMethod ("http://127.0.0.1:8001" + $receipt.status_url) `
    -Headers @{ 'X-Deletion-Receipt'=$receipt.receipt }
Remove-Variable password,newPassword,verification,resetToken,securePassword,secureNewPassword
```

The helper refreshes CSRF before each unsafe request; login rotates it. To test logout-all, use two independent WebRequestSession objects, log in both, then POST logout-all from one and verify the other gets 401. Submit a consumed/expired token again: expect 400 INVALID_TOKEN. Send role/is_staff in registration or PATCH: expect 400. Omit If-Match:428; reuse an old profile version:412. Five failed logins followed by another attempt:429. Keep test credentials/tokens out of saved command bodies, screenshots and logs; the examples read secrets into memory rather than literals in command history.

## Verification evidence

All **91 tests passed natively and in the pinned Linux Compose stack** (PostgreSQL 17/pgvector 0.8.7, Redis 7.4.12, Python 3.14.10). This includes the original suite plus real Argon2, registration, verification/reset expiry/single-use/purpose, CSRF/origin checks, shared throttles/Redis failure, session rotation/expiry/revocation, ownership, profile validation/ETags, role escalation, complete/personal erasure, receipt access/cleanup, concurrent token consumption, migration upgrade and the real Celery round trip. User migration, Django checks, drift checks, OpenAPI validation and Ruff pass. Local test XML/schema artifacts are under ignored `reports/`; the CI workflow runs the expanded suite without paid providers.

The live cookie/CSRF API flow was exercised against Mailpit and the worker: registration -> delivered verification token -> verification -> login -> profile PATCH -> delivered reset token -> reset/session invalidation -> new login -> account erasure -> receipt status. Synthetic accounts and their inbox messages were removed. GitHub-hosted CI, external production SMTP, TLS ingress, MFA, load/soak, backups and frontend integration remain unverified. No changes were pushed, merged or deployed publicly.
