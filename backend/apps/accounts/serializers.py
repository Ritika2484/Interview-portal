from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Profile, User


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {name: "Unknown or read-only field." for name in sorted(unknown)}
            )
        return super().to_internal_value(data)


class EmailSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        return value.strip().lower()


class PasswordInput(StrictSerializer):
    password = serializers.CharField(
        min_length=1, max_length=128, trim_whitespace=False, write_only=True
    )


class LoginSerializer(EmailSerializer, PasswordInput):
    pass


class RegisterSerializer(LoginSerializer):
    display_name = serializers.CharField(max_length=100)
    accepted_policy_version = serializers.CharField(max_length=32)

    def validate_accepted_policy_version(self, value):
        if value != settings.AUTH_POLICY_VERSION:
            raise serializers.ValidationError("Accept the current policy version.")
        return value

    def validate(self, attrs):
        try:
            validate_password(attrs["password"], User(email=attrs["email"]))
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages}) from error
        return attrs


class TokenSerializer(StrictSerializer):
    token = serializers.RegexField(r"^[A-Za-z0-9_-]{43}$", write_only=True, max_length=43)


class ResetSerializer(TokenSerializer):
    new_password = serializers.CharField(
        min_length=12, max_length=128, trim_whitespace=False, write_only=True
    )


class PreferencesSerializer(StrictSerializer):
    categories = serializers.ListField(
        child=serializers.ChoiceField(choices=["technical", "behavioral", "hr", "system_design"]),
        max_length=4,
        required=False,
    )
    modality = serializers.ChoiceField(choices=["text", "voice"], required=False)
    question_count = serializers.IntegerField(min_value=5, max_value=20, required=False)
    duration_minutes = serializers.IntegerField(min_value=10, max_value=60, required=False)


class ProfileInputSerializer(StrictSerializer):
    display_name = serializers.CharField(max_length=100, allow_blank=True, required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    target_job_role = serializers.CharField(max_length=200, allow_blank=True, required=False)
    experience_level = serializers.ChoiceField(
        choices=["beginner", "intermediate", "advanced"], required=False
    )
    technical_skills = serializers.ListField(
        child=serializers.CharField(max_length=64), max_length=50, required=False
    )
    interview_preferences = PreferencesSerializer(required=False)
    preparation_goals = serializers.ListField(
        child=serializers.CharField(max_length=300), max_length=20, required=False
    )
    preferred_interview_language = serializers.RegexField(
        r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$", max_length=16, required=False
    )

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise serializers.ValidationError("Use a valid IANA timezone.") from error
        return value

    def validate_technical_skills(self, values):
        if len({value.casefold() for value in values}) != len(values):
            raise serializers.ValidationError("Duplicate skills are not allowed.")
        return values


class ProfileOutputSerializer(serializers.ModelSerializer):
    technical_skills = serializers.ListField(
        child=serializers.CharField(max_length=64), max_length=50, read_only=True
    )
    preparation_goals = serializers.ListField(
        child=serializers.CharField(max_length=300), max_length=20, read_only=True
    )
    interview_preferences = PreferencesSerializer(read_only=True)

    class Meta:
        model = Profile
        fields = [
            "display_name",
            "timezone",
            "target_job_role",
            "experience_level",
            "technical_skills",
            "interview_preferences",
            "preparation_goals",
            "preferred_interview_language",
            "version",
            "updated_at",
        ]
        read_only_fields = fields


class AccountSerializer(serializers.ModelSerializer):
    profile = ProfileOutputSerializer()

    class Meta:
        model = User
        fields = ["id", "email", "role", "email_verified_at", "profile"]
        read_only_fields = fields


class LoginOutputSerializer(serializers.Serializer):
    user = AccountSerializer()
    session_expires_at = serializers.DateTimeField()


class MessageSerializer(serializers.Serializer):
    message = serializers.CharField()


class CSRFSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()
    policy_version = serializers.CharField()


class VerifyOutputSerializer(serializers.Serializer):
    verified = serializers.BooleanField()


class DeletionInputSerializer(StrictSerializer):
    confirmation = serializers.CharField(max_length=32)


class DeletionStatusSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["account", "personal_data"])
    state = serializers.CharField()
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField()


class DeletionOutputSerializer(DeletionStatusSerializer):
    receipt = serializers.CharField()
    status_url = serializers.CharField()


class AdminStatusSerializer(serializers.Serializer):
    active_accounts = serializers.IntegerField()


class ProblemSerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    status = serializers.IntegerField()
    code = serializers.CharField()
    detail = serializers.CharField()
    request_id = serializers.UUIDField(allow_null=True)
    errors = serializers.JSONField()
