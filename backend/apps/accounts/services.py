"""Account transitions. User-row locks serialize credentials, revocation and erasure."""

import hashlib
import secrets
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from .errors import AccountError
from .models import (
    AuthEmailDelivery,
    AuthToken,
    DeletionRequest,
    PolicyAcceptance,
    Profile,
    User,
    UserSession,
)


def secret_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def queue_email(user, purpose):
    AuthEmailDelivery.objects.get_or_create(user=user, purpose=purpose, state="pending")


def register(*, email, password, display_name, accepted_policy_version):
    encoded_password = make_password(password)  # Pay hashing cost for duplicates too.
    try:
        with transaction.atomic():
            user = User.objects.create(email=email, password=encoded_password, role="candidate")
            Profile.objects.create(user=user, display_name=display_name)
            PolicyAcceptance.objects.create(user=user, policy_version=accepted_policy_version)
            queue_email(user, AuthToken.Purpose.VERIFY)
    except IntegrityError:
        # A duplicate address, including racing requests, has the same public response.
        if not User.objects.filter(email__iexact=email).exists():
            raise


def request_email(email, purpose):
    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(email__iexact=email, is_active=True, deletion_requested_at__isnull=True)
            .first()
        )
        if user and (
            (purpose == AuthToken.Purpose.VERIFY and not user.email_verified_at)
            or (purpose == AuthToken.Purpose.RESET and user.email_verified_at)
        ):
            queue_email(user, purpose)


def deliver_email(delivery_id):
    """Bounded SMTP while holding the user lock prevents post-erasure dispatch.

    Raw secrets exist only in worker memory and the intended email. A failure issues
    a new token next time; delivery/commit cannot be exactly-once across SMTP and DB.
    """
    candidate = AuthEmailDelivery.objects.filter(pk=delivery_id).values("user_id").first()
    if not candidate:
        return False
    with transaction.atomic():
        user = (
            User.objects.select_for_update(skip_locked=True).filter(pk=candidate["user_id"]).first()
        )
        if not user:
            return False
        delivery = (
            AuthEmailDelivery.objects.select_for_update()
            .filter(pk=delivery_id, state="pending", next_attempt_at__lte=timezone.now())
            .first()
        )
        if not delivery:
            return False
        now = timezone.now()
        if (
            not user.is_active
            or user.deletion_requested_at
            or (delivery.purpose == AuthToken.Purpose.VERIFY and user.email_verified_at)
            or (delivery.purpose == AuthToken.Purpose.RESET and not user.email_verified_at)
        ):
            delivery.state = "canceled"
            delivery.completed_at = now
            delivery.save()
            return False
        AuthToken.objects.filter(
            user=user, purpose=delivery.purpose, consumed_at__isnull=True
        ).update(consumed_at=now)
        raw = secrets.token_urlsafe(32)
        ttl = (
            settings.AUTH_VERIFY_TOKEN_SECONDS
            if delivery.purpose == AuthToken.Purpose.VERIFY
            else settings.AUTH_RESET_TOKEN_SECONDS
        )
        token = AuthToken.objects.create(
            user=user,
            purpose=delivery.purpose,
            token_hash=secret_hash(raw),
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )
        action = (
            "verify-email" if delivery.purpose == AuthToken.Purpose.VERIFY else "reset-password"
        )
        delivery.attempts += 1
        try:
            sent = send_mail(
                "Verify your email" if action == "verify-email" else "Reset your password",
                (
                    f"Use this single-use token to {action}. "
                    f"It expires in {ttl // 60} minutes.\n\nToken: {raw}\n\n"
                    f"{settings.AUTH_PUBLIC_BASE_URL}/{action}#token={raw}\n\n"
                    "If you did not request this, ignore this message."
                ),
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            if sent != 1:
                raise OSError("Email was not accepted.")
        except (SMTPException, OSError):
            token.consumed_at = now
            token.save(update_fields=["consumed_at"])
            delivery.state = "failed" if delivery.attempts >= 5 else "pending"
            delivery.next_attempt_at = now + timedelta(seconds=min(300, 10 * 2**delivery.attempts))
        else:
            delivery.state = "sent"
        if delivery.state != "pending":
            delivery.completed_at = now
        delivery.save()
        return delivery.state == "sent"


def locked_token(raw, purpose):
    # Lock ordering is always User -> token, including resend, reset and deletion.
    token_hash = secret_hash(raw)
    candidate = (
        AuthToken.objects.filter(token_hash=token_hash, purpose=purpose).values("user_id").first()
    )
    if candidate:
        user = (
            User.objects.select_for_update()
            .filter(pk=candidate["user_id"], is_active=True, deletion_requested_at__isnull=True)
            .first()
        )
        if user:
            token = (
                AuthToken.objects.select_for_update()
                .filter(
                    user=user,
                    token_hash=token_hash,
                    purpose=purpose,
                    consumed_at__isnull=True,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if token:
                return user, token
    raise AccountError("Invalid or expired token.", "INVALID_TOKEN")


@transaction.atomic
def verify_email(raw):
    user, token = locked_token(raw, AuthToken.Purpose.VERIFY)
    if user.email_verified_at:
        raise AccountError("Invalid or expired token.", "INVALID_TOKEN")
    now = timezone.now()
    user.email_verified_at = now
    user.save(update_fields=["email_verified_at", "updated_at"])
    AuthToken.objects.filter(user=user, purpose=token.purpose, consumed_at__isnull=True).update(
        consumed_at=now
    )


def revoke_sessions(user):
    keys = list(UserSession.objects.filter(user=user).values_list("session_id", flat=True))
    Session.objects.filter(session_key__in=keys).delete()
    user.auth_version += 1
    user.save(update_fields=["auth_version", "updated_at"])


@transaction.atomic
def reset_password(raw, new_password):
    user, token = locked_token(raw, AuthToken.Purpose.RESET)
    validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    AuthToken.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=timezone.now())
    AuthEmailDelivery.objects.filter(user=user, state="pending").update(
        state="canceled", completed_at=timezone.now()
    )
    revoke_sessions(user)


@transaction.atomic
def sign_in(request, email, password):
    user = User.objects.select_for_update().filter(email__iexact=email).first()
    valid = user.check_password(password) if user else False
    if not user:
        make_password(password)  # Similar password-hasher cost for unknown addresses.
    if not (
        user
        and valid
        and user.is_active
        and user.email_verified_at
        and not user.deletion_requested_at
    ):
        raise AccountError(
            "Invalid credentials or account unavailable.", "INVALID_CREDENTIALS", 401
        )
    if user.role == "administrator" and not settings.AUTH_ADMIN_LOGIN_ENABLED:
        raise AccountError(
            "Invalid credentials or account unavailable.", "INVALID_CREDENTIALS", 401
        )
    raw_request = request._request
    raw_request.session.cycle_key()
    login(raw_request, user, backend="django.contrib.auth.backends.ModelBackend")
    now = timezone.now()
    raw_request.session["auth_version"] = user.auth_version
    raw_request.session["reauthenticated_at"] = now.timestamp()
    raw_request.session.set_expiry(settings.AUTH_SESSION_IDLE_SECONDS)
    raw_request.session.save()
    UserSession.objects.create(
        session_id=raw_request.session.session_key,
        user=user,
        auth_version=user.auth_version,
        created_at=now,
        last_seen_at=now,
        absolute_expires_at=now + timedelta(seconds=settings.AUTH_SESSION_ABSOLUTE_SECONDS),
    )
    Profile.objects.get_or_create(user=user)
    return user, now + timedelta(seconds=settings.AUTH_SESSION_IDLE_SECONDS)


def locked_session_user(request, recent=False):
    user = (
        User.objects.select_for_update()
        .filter(pk=request.user.pk, is_active=True, deletion_requested_at__isnull=True)
        .first()
    )
    if (
        not user
        or not user.email_verified_at
        or request.session.get("auth_version") != user.auth_version
        or not UserSession.objects.filter(
            user=user,
            session_id=request.session.session_key,
            absolute_expires_at__gt=timezone.now(),
            last_seen_at__gt=timezone.now() - timedelta(seconds=settings.AUTH_SESSION_IDLE_SECONDS),
        ).exists()
    ):
        raise AccountError("Authentication required.", "NOT_AUTHENTICATED", 401)
    if (
        recent
        and timezone.now().timestamp() - request.session.get("reauthenticated_at", 0)
        > settings.AUTH_REAUTH_SECONDS
    ):
        raise AccountError(
            "Reauthenticate with your password first.", "REAUTHENTICATION_REQUIRED", 403
        )
    return user


@transaction.atomic
def reauthenticate(request, password):
    user = locked_session_user(request)
    if not user.check_password(password):
        raise AccountError("Invalid credentials.", "INVALID_CREDENTIALS", 401)
    request.session["reauthenticated_at"] = timezone.now().timestamp()


@transaction.atomic
def logout_all(request):
    user = locked_session_user(request, recent=True)
    revoke_sessions(user)
    logout(request._request)


def get_profile(user):
    return Profile.objects.get_or_create(user=user)[0]


@transaction.atomic
def update_profile(request, data, expected_version):
    user = locked_session_user(request)
    profile = Profile.objects.select_for_update().get(user=user)
    if profile.version != expected_version:
        raise AccountError("Refresh the profile and retry.", "STALE_PROFILE", 412)
    for name, value in data.items():
        setattr(profile, name, value)
    profile.version += 1
    profile.save()
    return user, profile


@transaction.atomic
def delete_data(request, kind):
    user = locked_session_user(request, recent=True)
    now = timezone.now()
    receipt = secrets.token_urlsafe(32)
    deletion = DeletionRequest.objects.create(
        owner=user,
        kind=kind,
        receipt_hash=secret_hash(receipt),
        expires_at=now + timedelta(days=30),
    )
    revoke_sessions(user)
    AuthToken.objects.filter(user=user).delete()
    AuthEmailDelivery.objects.filter(user=user).delete()
    if kind == "account":
        # All current private models have explicit CASCADE/SET_NULL policies.
        user.deletion_requested_at = now
        user.is_active = False
        user.save(update_fields=["deletion_requested_at", "is_active", "updated_at"])
        user.delete()
    else:
        profile = Profile.objects.select_for_update().filter(user=user).first()
        version = profile.version + 1 if profile else 1
        Profile.objects.filter(user=user).delete()
        Profile.objects.create(user=user, version=version)
    logout(request._request)
    return deletion, receipt
