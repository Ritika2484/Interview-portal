import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.hashers import identify_hasher
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.test import APIClient

from apps.accounts.models import (
    AuthEmailDelivery,
    AuthToken,
    DeletionRequest,
    PolicyAcceptance,
    Profile,
    User,
    UserSession,
)
from apps.accounts.services import deliver_email, secret_hash
from apps.accounts.tasks import process_auth_emails, prune_auth_records

pytestmark = pytest.mark.django_db
PASSWORD = "Original-secure-Passphrase-91!"
NEW_PASSWORD = "Replacement-secure-Passphrase-37!"


def csrf(client):
    response = client.get("/api/v1/auth/csrf/")
    assert response.status_code == 200, response.content
    return response.json()["csrf_token"]


def post(client, path, data=None):
    return client.post(f"/api/v1/{path}/", data or {}, format="json", HTTP_X_CSRFTOKEN=csrf(client))


def delete(client, path, confirmation):
    return client.delete(
        f"/api/v1/{path}/",
        {"confirmation": confirmation},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
    )


@pytest.fixture
def api():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def candidate():
    return User.objects.create_user(
        "candidate@example.com", PASSWORD, email_verified_at=timezone.now()
    )


def login(client, user):
    response = post(client, "auth/login", {"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.content
    return response


def issue_token(user, purpose, *, expired=False):
    raw = secrets.token_urlsafe(32)
    now = timezone.now()
    token = AuthToken.objects.create(
        user=user,
        purpose=purpose,
        token_hash=secret_hash(raw),
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(seconds=1) if expired else now + timedelta(minutes=30),
    )
    return raw, token


def test_registration_hashes_password_forces_candidate_and_queues_email(api):
    response = post(
        api,
        "auth/register",
        {
            "email": "New@EXAMPLE.com",
            "password": PASSWORD,
            "display_name": "Learner",
            "accepted_policy_version": settings.AUTH_POLICY_VERSION,
        },
    )
    assert response.status_code == 202
    assert api.get("/api/v1/me/").status_code == 401
    user = User.objects.get(email="new@example.com")
    assert user.check_password(PASSWORD)
    assert user.password != PASSWORD
    assert user.role == "candidate" and not user.is_staff and not user.email_verified_at
    assert user.profile.display_name == "Learner"
    assert PolicyAcceptance.objects.filter(user=user).count() == 1
    assert (
        AuthEmailDelivery.objects.filter(user=user, purpose="verify_email", state="pending").count()
        == 1
    )
    assert not AuthToken.objects.filter(user=user).exists()
    assert "token" not in response.json()


def test_registration_duplicate_is_generic_and_does_not_replace_credentials(api, candidate):
    data = {
        "email": candidate.email.upper(),
        "password": NEW_PASSWORD,
        "display_name": "Attacker",
        "accepted_policy_version": settings.AUTH_POLICY_VERSION,
    }
    known = post(api, "auth/register", data)
    fresh = post(api, "auth/register", {**data, "email": "new@example.com"})
    assert known.status_code == fresh.status_code == 202
    assert known.json() == fresh.json()
    candidate.refresh_from_db()
    assert candidate.check_password(PASSWORD)
    assert User.objects.count() == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "administrator"),
        ("is_staff", True),
        ("is_superuser", True),
        ("email_verified_at", "2026-01-01"),
    ],
)
def test_registration_rejects_privilege_fields(api, field, value):
    response = post(
        api,
        "auth/register",
        {
            "email": "new@example.com",
            "password": PASSWORD,
            "display_name": "Learner",
            "accepted_policy_version": settings.AUTH_POLICY_VERSION,
            field: value,
        },
    )
    assert response.status_code == 400
    assert not User.objects.exists()


@pytest.mark.parametrize(
    "extra",
    [{"password": "short"}, {"password": "1" * 129}, {"accepted_policy_version": "obsolete"}],
)
def test_registration_rejects_invalid_password_or_policy(api, extra):
    response = post(
        api,
        "auth/register",
        {
            "email": "new@example.com",
            "password": PASSWORD,
            "display_name": "Learner",
            "accepted_policy_version": settings.AUTH_POLICY_VERSION,
            **extra,
        },
    )
    assert response.status_code == 400


def test_real_argon2_hashing_is_configured(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
    user = User.objects.create_user("hash@example.com", PASSWORD)
    assert identify_hasher(user.password).algorithm == "argon2"
    assert user.check_password(PASSWORD)


def test_email_delivery_stores_only_hash_and_verification_is_single_use(api, mailoutbox):
    user = User.objects.create_user("unverified@example.com", PASSWORD)
    delivery = AuthEmailDelivery.objects.create(user=user, purpose="verify_email")
    assert deliver_email(delivery.pk)
    raw = re.search(r"Token: ([A-Za-z0-9_-]+)", mailoutbox[0].body).group(1)
    token = AuthToken.objects.get(user=user)
    assert token.token_hash == secret_hash(raw)
    assert token.expires_at - token.created_at == timedelta(hours=24)
    assert raw not in str(token.__dict__)
    assert raw not in str(AuthEmailDelivery.objects.get(pk=delivery.pk).__dict__)
    assert post(api, "auth/verify-email", {"token": raw}).status_code == 200
    assert post(api, "auth/verify-email", {"token": raw}).status_code == 400
    user.refresh_from_db()
    assert user.email_verified_at
    login(api, user)


@pytest.mark.parametrize(
    "purpose,path",
    [("verify_email", "auth/verify-email"), ("reset_password", "auth/password-reset/confirm")],
)
def test_expired_tokens_are_rejected(api, candidate, purpose, path):
    raw, token = issue_token(candidate, purpose, expired=True)
    response = post(
        api,
        path,
        {"token": raw, **({"new_password": NEW_PASSWORD} if purpose == "reset_password" else {})},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_TOKEN"
    token.refresh_from_db()
    assert token.consumed_at is None


def test_wrong_purpose_unknown_and_disabled_user_tokens_fail(api, candidate):
    raw, _ = issue_token(candidate, "reset_password")
    assert post(api, "auth/verify-email", {"token": raw}).status_code == 400
    assert post(api, "auth/verify-email", {"token": secrets.token_urlsafe(32)}).status_code == 400
    candidate.is_active = False
    candidate.save()
    assert (
        post(
            api, "auth/password-reset/confirm", {"token": raw, "new_password": NEW_PASSWORD}
        ).status_code
        == 400
    )


def test_resend_invalidates_previous_token_and_does_not_duplicate_pending_job(
    api, candidate, mailoutbox
):
    candidate.email_verified_at = None
    candidate.save()
    raw, token = issue_token(candidate, "verify_email")
    for _ in range(2):
        assert post(api, "auth/resend-verification", {"email": candidate.email}).status_code == 202
    assert AuthEmailDelivery.objects.filter(state="pending").count() == 1
    process_auth_emails.run()
    token.refresh_from_db()
    assert token.consumed_at
    assert post(api, "auth/verify-email", {"token": raw}).status_code == 400
    assert len(mailoutbox) == 1


def test_email_failure_revokes_unsent_token_and_retries_without_secret_payload(
    candidate, mailoutbox
):
    delivery = AuthEmailDelivery.objects.create(user=candidate, purpose="reset_password")
    with patch("apps.accounts.services.send_mail", side_effect=OSError("secret-smtp-password")):
        assert not deliver_email(delivery.pk)
    delivery.refresh_from_db()
    assert delivery.state == "pending" and delivery.attempts == 1
    assert AuthToken.objects.get(user=candidate).consumed_at
    assert "secret" not in str(delivery.__dict__)
    delivery.next_attempt_at = timezone.now()
    delivery.save()
    assert deliver_email(delivery.pk)
    assert len(mailoutbox) == 1
    latest = AuthToken.objects.filter(user=candidate).latest("created_at")
    assert latest.expires_at - latest.created_at == timedelta(minutes=30)


def test_login_is_case_insensitive_tracks_session_and_hides_secrets(api, candidate):
    response = post(api, "auth/login", {"email": candidate.email.upper(), "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "candidate"
    assert "password" not in response.content.decode()
    cookie = api.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    assert UserSession.objects.filter(session_id=cookie.value, user=candidate).exists()
    tracked = UserSession.objects.get(session_id=cookie.value)
    assert tracked.absolute_expires_at - tracked.created_at == timedelta(days=7)
    assert api.get("/api/v1/me/").status_code == 200


def test_invalid_unknown_unverified_and_inactive_credentials_are_indistinguishable(api, candidate):
    wrong = post(api, "auth/login", {"email": candidate.email, "password": "wrong"})
    unknown = post(api, "auth/login", {"email": "unknown@example.com", "password": PASSWORD})
    candidate.email_verified_at = None
    candidate.save()
    unverified = post(api, "auth/login", {"email": candidate.email, "password": PASSWORD})
    candidate.email_verified_at = timezone.now()
    candidate.is_active = False
    candidate.save()
    inactive = post(api, "auth/login", {"email": candidate.email, "password": PASSWORD})
    for response in (wrong, unknown, unverified, inactive):
        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_CREDENTIALS"
        assert response.json()["detail"] == wrong.json()["detail"]
    assert not UserSession.objects.exists()


def test_login_rotates_session_and_csrf(api, candidate):
    before_csrf = csrf(api)
    login(api, candidate)
    previous_session = api.cookies[settings.SESSION_COOKIE_NAME].value
    response = api.post("/api/v1/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=before_csrf)
    assert response.status_code == 403
    login(api, candidate)
    assert api.cookies[settings.SESSION_COOKIE_NAME].value != previous_session
    assert not Session.objects.filter(session_key=previous_session).exists()


@pytest.mark.parametrize(
    "path,data",
    [
        ("auth/register", {"email": "new@example.com"}),
        ("auth/login", {"email": "new@example.com", "password": PASSWORD}),
        ("auth/password-reset", {"email": "new@example.com"}),
        ("auth/verify-email", {"token": "a" * 43}),
        ("auth/logout", {}),
    ],
)
def test_anonymous_unsafe_routes_require_csrf(api, path, data):
    response = api.post(f"/api/v1/{path}/", data, format="json")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"
    assert response["Cache-Control"] == "no-store"


def test_cross_origin_login_is_rejected(api, candidate):
    response = api.post(
        "/api/v1/auth/login/",
        {"email": candidate.email, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(api),
        HTTP_ORIGIN="https://attacker.example",
    )
    assert response.status_code == 403


def test_login_throttling_account_and_ip_are_not_spoofed(api, candidate):
    for _ in range(5):
        assert (
            post(api, "auth/login", {"email": candidate.email, "password": "wrong"}).status_code
            == 401
        )
    response = api.post(
        "/api/v1/auth/login/",
        {"email": candidate.email, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(api),
        HTTP_X_FORWARDED_FOR="192.0.2.99",
    )
    assert response.status_code == 429
    assert int(response["Retry-After"]) > 0


def test_authentication_fails_closed_when_rate_limit_store_is_down(api, candidate):
    token = csrf(api)
    with patch(
        "apps.accounts.throttling.Redis.from_url",
        side_effect=RedisConnectionError("redis://secret"),
    ):
        response = api.post(
            "/api/v1/auth/login/",
            {"email": candidate.email, "password": PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
    assert response.status_code == 503
    assert "secret" not in response.content.decode()


def test_logout_and_logout_all_revoke_other_clients(api, candidate):
    other = APIClient(enforce_csrf_checks=True)
    login(api, candidate)
    login(other, candidate)
    assert post(api, "auth/logout").status_code == 204
    assert api.get("/api/v1/me/").status_code == 401
    assert other.get("/api/v1/me/").status_code == 200
    login(api, candidate)
    assert post(api, "auth/logout-all").status_code == 204
    assert other.get("/api/v1/me/").status_code == 401
    assert not UserSession.objects.filter(user=candidate).exists()


@pytest.mark.parametrize("expired", ["idle", "absolute", "epoch", "untracked"])
def test_session_expiry_and_revocation(api, candidate, expired):
    login(api, candidate)
    tracked = UserSession.objects.get(user=candidate)
    if expired == "idle":
        UserSession.objects.filter(pk=tracked.pk).update(
            last_seen_at=timezone.now() - timedelta(hours=13)
        )
    elif expired == "absolute":
        UserSession.objects.filter(pk=tracked.pk).update(
            created_at=timezone.now() - timedelta(days=8),
            absolute_expires_at=timezone.now() - timedelta(seconds=1),
        )
    elif expired == "epoch":
        User.objects.filter(pk=candidate.pk).update(auth_version=2)
    else:
        tracked.delete()
    assert api.get("/api/v1/me/").status_code == 401


def test_password_reset_request_is_generic_and_reset_revokes_every_session(api, candidate):
    known = post(api, "auth/password-reset", {"email": candidate.email})
    unknown = post(api, "auth/password-reset", {"email": "unknown@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    other = APIClient(enforce_csrf_checks=True)
    login(api, candidate)
    login(other, candidate)
    raw, token = issue_token(candidate, "reset_password")
    assert (
        post(
            api, "auth/password-reset/confirm", {"token": raw, "new_password": NEW_PASSWORD}
        ).status_code
        == 204
    )
    candidate.refresh_from_db()
    assert candidate.check_password(NEW_PASSWORD)
    assert other.get("/api/v1/me/").status_code == 401
    assert api.get("/api/v1/me/").status_code == 401
    assert not Session.objects.filter(
        session_key__in=UserSession.objects.filter(user=candidate).values("session_id")
    ).exists()
    assert (
        post(
            api, "auth/password-reset/confirm", {"token": raw, "new_password": PASSWORD}
        ).status_code
        == 400
    )
    assert (
        post(api, "auth/login", {"email": candidate.email, "password": PASSWORD}).status_code == 401
    )
    assert (
        post(api, "auth/login", {"email": candidate.email, "password": NEW_PASSWORD}).status_code
        == 200
    )


def test_weak_reset_password_does_not_consume_valid_token(api, candidate):
    raw, token = issue_token(candidate, "reset_password")
    assert (
        post(
            api, "auth/password-reset/confirm", {"token": raw, "new_password": "123456789012"}
        ).status_code
        == 400
    )
    token.refresh_from_db()
    assert token.consumed_at is None


def test_reauthentication_required_for_sensitive_operations(api, candidate):
    login(api, candidate)
    session = api.session
    session["reauthenticated_at"] = (timezone.now() - timedelta(minutes=11)).timestamp()
    session.save()
    assert post(api, "auth/logout-all").status_code == 403
    assert delete(api, "me", "delete-account").status_code == 403
    assert post(api, "auth/reauthenticate", {"password": "wrong"}).status_code == 401
    assert post(api, "auth/reauthenticate", {"password": PASSWORD}).status_code == 204
    assert post(api, "auth/logout-all").status_code == 204


def test_profiles_are_owner_scoped_versioned_and_bounded(api, candidate):
    other = User.objects.create_user(
        "other@example.com", PASSWORD, email_verified_at=timezone.now()
    )
    Profile.objects.create(user=other, display_name="Other private name")
    login(api, candidate)
    response = api.get(f"/api/v1/me/?user_id={other.pk}")
    assert response.json()["id"] == str(candidate.pk)
    data = {
        "target_job_role": "Backend engineer",
        "experience_level": "intermediate",
        "technical_skills": ["Django", "PostgreSQL"],
        "interview_preferences": {
            "categories": ["technical"],
            "modality": "text",
            "question_count": 10,
            "duration_minutes": 30,
        },
        "preparation_goals": ["Practice system design"],
        "preferred_interview_language": "en",
        "timezone": "Asia/Calcutta",
    }
    assert (
        api.patch("/api/v1/me/", data, format="json", HTTP_X_CSRFTOKEN=csrf(api)).status_code == 428
    )
    updated = api.patch(
        "/api/v1/me/",
        data,
        format="json",
        HTTP_X_CSRFTOKEN=csrf(api),
        HTTP_IF_MATCH=response["ETag"],
    )
    assert updated.status_code == 200, updated.content
    assert updated.json()["profile"]["target_job_role"] == data["target_job_role"]
    assert updated["ETag"] != response["ETag"]
    assert (
        api.patch(
            "/api/v1/me/",
            data,
            format="json",
            HTTP_X_CSRFTOKEN=csrf(api),
            HTTP_IF_MATCH=response["ETag"],
        ).status_code
        == 412
    )
    assert other.profile.display_name == "Other private name"
    assert api.get(f"/api/v1/users/{other.pk}/").status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        {"role": "administrator"},
        {"is_staff": True},
        {"user_id": "another"},
        {"email": "takeover@example.com"},
        {"technical_skills": ["Django", "django"]},
        {"technical_skills": ["x"] * 51},
        {"interview_preferences": {"system_prompt": "evil"}},
        {"timezone": "Not/AZone"},
    ],
)
def test_profile_rejects_escalation_and_invalid_inputs(api, candidate, data):
    login(api, candidate)
    response = api.patch(
        "/api/v1/me/", data, format="json", HTTP_X_CSRFTOKEN=csrf(api), HTTP_IF_MATCH='"1"'
    )
    assert response.status_code == 400
    candidate.refresh_from_db()
    assert candidate.role == "candidate" and not candidate.is_staff


def test_admin_role_is_server_provisioned_and_permissions_are_scoped(api, candidate, settings):
    login(api, candidate)
    assert api.get("/api/v1/admin/account-stats/").status_code == 403
    call_command("set_account_role", str(candidate.pk), "administrator")
    assert api.get("/api/v1/me/").status_code == 401
    candidate.refresh_from_db()
    assert candidate.role == "administrator" and candidate.is_staff and not candidate.is_superuser
    login(api, candidate)
    assert api.get("/api/v1/admin/account-stats/").status_code == 200
    settings.AUTH_ADMIN_LOGIN_ENABLED = False
    assert api.get("/api/v1/admin/account-stats/").status_code == 403
    assert (
        post(api, "auth/login", {"email": candidate.email, "password": PASSWORD}).status_code == 401
    )


def test_database_rejects_inconsistent_roles_and_wrong_json_types(candidate):
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=candidate.pk).update(role="administrator", is_staff=False)
    with pytest.raises(IntegrityError), transaction.atomic():
        Profile.objects.create(user=candidate, technical_skills={"invalid": "object"})


def test_account_deletion_purges_private_rows_and_has_content_free_receipt(api, candidate):
    user_id = candidate.pk
    other = APIClient(enforce_csrf_checks=True)
    login(api, candidate)
    login(other, candidate)
    old_keys = list(UserSession.objects.filter(user=candidate).values_list("session_id", flat=True))
    raw, token = issue_token(candidate, "reset_password")
    AuthEmailDelivery.objects.create(user=candidate, purpose="reset_password")
    PolicyAcceptance.objects.create(user=candidate, policy_version=settings.AUTH_POLICY_VERSION)
    assert delete(api, "me", "wrong").status_code == 400
    response = delete(api, "me", "delete-account")
    assert response.status_code == 202
    assert not User.objects.filter(pk=user_id).exists()
    assert not Profile.objects.filter(user_id=user_id).exists()
    assert not AuthToken.objects.filter(user_id=user_id).exists()
    assert not AuthEmailDelivery.objects.filter(user_id=user_id).exists()
    assert not PolicyAcceptance.objects.filter(user_id=user_id).exists()
    assert not Session.objects.filter(session_key__in=old_keys).exists()
    assert other.get("/api/v1/me/").status_code == 401
    body = response.json()
    receipt = DeletionRequest.objects.get(pk=body["id"])
    assert receipt.owner_id is None
    assert secret_hash(body["receipt"]) == receipt.receipt_hash
    assert api.get(body["status_url"]).status_code == 404
    status = api.get(body["status_url"], HTTP_X_DELETION_RECEIPT=body["receipt"])
    assert status.status_code == 200
    assert "email" not in status.content.decode() and str(user_id) not in status.content.decode()
    assert (
        post(
            api, "auth/password-reset/confirm", {"token": raw, "new_password": NEW_PASSWORD}
        ).status_code
        == 400
    )


def test_personal_data_deletion_keeps_identity_but_clears_profile_and_sessions(api, candidate):
    login(api, candidate)
    Profile.objects.filter(user=candidate).update(
        display_name="Private", technical_skills=["Django"], preparation_goals=["Private goal"]
    )
    response = delete(api, "me/personal-data", "delete-personal-data")
    assert response.status_code == 202
    candidate.refresh_from_db()
    assert candidate.check_password(PASSWORD) and candidate.email_verified_at
    assert candidate.profile.display_name == "" and candidate.profile.technical_skills == []
    assert api.get("/api/v1/me/").status_code == 401
    login(api, candidate)


def test_unauthorized_and_deleted_receipt_access(api):
    assert api.get("/api/v1/me/").status_code == 401
    assert delete(api, "me", "delete-account").status_code == 401
    assert api.get("/api/v1/admin/account-stats/").status_code == 401


def test_pruning_expired_tokens_receipts_and_delivered_intents(candidate):
    now = timezone.now()
    raw, token = issue_token(candidate, "reset_password", expired=True)
    AuthToken.objects.filter(pk=token.pk).update(
        created_at=now - timedelta(days=3), expires_at=now - timedelta(days=2)
    )
    expired = DeletionRequest.objects.create(
        owner=candidate,
        kind="personal_data",
        receipt_hash=secret_hash(raw),
        expires_at=now - timedelta(seconds=1),
    )
    AuthEmailDelivery.objects.create(
        user=candidate, purpose="reset_password", state="sent", completed_at=now - timedelta(days=8)
    )
    prune_auth_records.run()
    assert not AuthToken.objects.filter(pk=token.pk).exists()
    assert not DeletionRequest.objects.filter(pk=expired.pk).exists()
    assert not AuthEmailDelivery.objects.exists()


def test_auth_logs_do_not_capture_password_email_token_or_receipt(api, candidate, caplog):
    raw, _ = issue_token(candidate, "reset_password")
    post(api, "auth/login", {"email": candidate.email, "password": "Secret-failed-password"})
    post(api, "auth/password-reset/confirm", {"token": raw, "new_password": NEW_PASSWORD})
    for secret in (candidate.email, raw, NEW_PASSWORD, "Secret-failed-password"):
        assert secret not in caplog.text


@pytest.mark.django_db(transaction=True)
def test_concurrent_token_consumption_succeeds_exactly_once():
    user = User.objects.create_user("race@example.com", PASSWORD)
    raw, token = issue_token(user, "verify_email")

    def consume():
        close_old_connections()
        try:
            client = APIClient(enforce_csrf_checks=True)
            return post(client, "auth/verify-email", {"token": raw}).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: consume(), range(2))) == [200, 400]
