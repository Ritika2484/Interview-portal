import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.sessions.models import Session
from django.db import models
from django.db.models.functions import Lower
from django.db.models.lookups import Exact
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Minimal identity schema established before any dependent migrations."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=254)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    role = models.CharField(
        max_length=20,
        default="candidate",
        choices=[("candidate", "Candidate"), ("administrator", "Administrator")],
    )
    auth_version = models.PositiveIntegerField(default=1)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
            models.CheckConstraint(
                condition=models.Q(auth_version__gte=1), name="accounts_auth_version_positive"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(role="candidate", is_staff=False, is_superuser=False)
                    | models.Q(role="administrator", is_staff=True)
                ),
                name="accounts_role_staff_consistent",
            ),
        ]

    def save(self, *args, **kwargs):
        self.email = UserManager().normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.pk)  # Avoid exposing email in generic logs/admin representations.


class PrivateRecord(models.Model):
    class Meta:
        abstract = True

    def __str__(self):
        return str(self.pk)


class Profile(PrivateRecord):
    user = models.OneToOneField(
        User, primary_key=True, on_delete=models.CASCADE, related_name="profile"
    )
    display_name = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    target_job_role = models.CharField(max_length=200, blank=True)
    experience_level = models.CharField(
        max_length=20,
        default="beginner",
        choices=[
            ("beginner", "Beginner"),
            ("intermediate", "Intermediate"),
            ("advanced", "Advanced"),
        ],
    )
    technical_skills = models.JSONField(default=list)
    interview_preferences = models.JSONField(default=dict)
    preparation_goals = models.JSONField(default=list)
    preferred_interview_language = models.CharField(max_length=16, default="en")
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="accounts_profile_version_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(experience_level__in=["beginner", "intermediate", "advanced"]),
                name="accounts_profile_experience_valid",
            ),
            *[
                models.CheckConstraint(
                    condition=Exact(
                        models.Func(
                            models.F(field),
                            function="jsonb_typeof",
                            output_field=models.CharField(),
                        ),
                        models.Value(kind),
                    ),
                    name=f"accounts_{field}_json_type",
                )
                for field, kind in [
                    ("technical_skills", "array"),
                    ("preparation_goals", "array"),
                    ("interview_preferences", "object"),
                ]
            ],
        ]


class PolicyAcceptance(PrivateRecord):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    policy_version = models.CharField(max_length=32)
    accepted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "policy_version"], name="accounts_policy_once")
        ]


class AuthToken(PrivateRecord):
    class Purpose(models.TextChoices):
        VERIFY = "verify_email", "Email verification"
        RESET = "reset_password", "Password reset"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_tokens")
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="accounts_token_expiry_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(purpose__in=["verify_email", "reset_password"]),
                name="accounts_token_purpose_valid",
            ),
        ]


class UserSession(PrivateRecord):
    session = models.OneToOneField(Session, primary_key=True, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tracked_sessions")
    auth_version = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    absolute_expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(absolute_expires_at__gt=models.F("created_at")),
                name="accounts_session_expiry_valid",
            )
        ]


class AuthEmailDelivery(PrivateRecord):
    """Durable intent only: no address, password, raw token or rendered email payload."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_deliveries")
    purpose = models.CharField(max_length=20, choices=AuthToken.Purpose.choices)
    state = models.CharField(
        max_length=16,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("sent", "Sent"),
            ("failed", "Failed"),
            ("canceled", "Canceled"),
        ],
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=["state", "next_attempt_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purpose__in=["verify_email", "reset_password"]),
                name="accounts_email_purpose_valid",
            ),
            models.UniqueConstraint(
                fields=["user", "purpose"],
                condition=models.Q(state="pending"),
                name="accounts_one_pending_email",
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=["pending", "sent", "failed", "canceled"]),
                name="accounts_email_state_valid",
            ),
        ]


class DeletionRequest(PrivateRecord):
    """Content-free completion receipt; account erasure leaves no account identifier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    kind = models.CharField(
        max_length=20, choices=[("account", "Account"), ("personal_data", "Personal data")]
    )
    receipt_hash = models.CharField(max_length=64, unique=True)
    state = models.CharField(max_length=16, default="completed")
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=["account", "personal_data"]),
                name="accounts_deletion_kind_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(state="completed"), name="accounts_deletion_state_valid"
            ),
        ]
