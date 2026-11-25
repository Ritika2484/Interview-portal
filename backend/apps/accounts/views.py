import re

from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import ValidationError as DjangoValidationError
from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .authentication import IsAdministrator
from .errors import AccountError
from .models import AuthToken, DeletionRequest, User
from .serializers import (
    AccountSerializer,
    AdminStatusSerializer,
    CSRFSerializer,
    DeletionInputSerializer,
    DeletionOutputSerializer,
    DeletionStatusSerializer,
    EmailSerializer,
    LoginOutputSerializer,
    LoginSerializer,
    MessageSerializer,
    PasswordInput,
    ProblemSerializer,
    ProfileInputSerializer,
    RegisterSerializer,
    ResetSerializer,
    StrictSerializer,
    TokenSerializer,
    VerifyOutputSerializer,
)
from .throttling import AuthRateThrottle


def account_schema(*, responses, parameters=None, **kwargs):
    success = responses if isinstance(responses, dict) else {200: responses}
    return extend_schema(
        responses={
            **{status: ProblemSerializer for status in (400, 401, 403, 404, 412, 428, 429, 503)},
            **success,
        },
        parameters=[
            OpenApiParameter(
                "X-CSRFToken",
                str,
                OpenApiParameter.HEADER,
                description=(
                    "Required for unsafe requests, including anonymous authentication. "
                    "Fetch via GET /auth/csrf/; refresh after login."
                ),
            ),
            *(parameters or []),
        ],
        **kwargs,
    )


@method_decorator(csrf_protect, name="dispatch")
class AccountAPIView(APIView):
    throttle_classes = [AuthRateThrottle]
    rate_scope = "authenticated"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def parse(self, serializer_class, request):
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class PublicAccountAPIView(AccountAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    rate_scope = "token"


class CSRFView(PublicAccountAPIView):
    @account_schema(responses=CSRFSerializer, auth=[], tags=["Authentication"])
    def get(self, request):
        return Response(
            {
                "csrf_token": get_token(request._request),
                "policy_version": settings.AUTH_POLICY_VERSION,
            }
        )


class RegisterView(PublicAccountAPIView):
    rate_scope = "register"

    @account_schema(
        request=RegisterSerializer,
        responses={202: MessageSerializer},
        auth=[],
        tags=["Authentication"],
    )
    def post(self, request):
        services.register(**self.parse(RegisterSerializer, request))
        return Response(
            {"message": "If registration can proceed, verification instructions will be sent."},
            status=202,
        )


class LoginView(PublicAccountAPIView):
    rate_scope = "login"

    @account_schema(
        request=LoginSerializer,
        responses={200: LoginOutputSerializer},
        auth=[],
        tags=["Authentication"],
    )
    def post(self, request):
        user, expires = services.sign_in(request, **self.parse(LoginSerializer, request))
        return Response({"user": AccountSerializer(user).data, "session_expires_at": expires})


class VerifyEmailView(PublicAccountAPIView):
    @account_schema(
        request=TokenSerializer, responses=VerifyOutputSerializer, auth=[], tags=["Authentication"]
    )
    def post(self, request):
        services.verify_email(self.parse(TokenSerializer, request)["token"])
        return Response({"verified": True})


class RequestEmailView(PublicAccountAPIView):
    rate_scope = "email"
    purpose = AuthToken.Purpose.VERIFY

    @account_schema(
        request=EmailSerializer,
        responses={202: MessageSerializer},
        auth=[],
        tags=["Authentication"],
    )
    def post(self, request):
        services.request_email(self.parse(EmailSerializer, request)["email"], self.purpose)
        return Response(
            {"message": "If the account is eligible, instructions will be sent."}, status=202
        )


class ForgotPasswordView(RequestEmailView):
    purpose = AuthToken.Purpose.RESET


class ResetPasswordView(PublicAccountAPIView):
    @account_schema(
        request=ResetSerializer, responses={204: None}, auth=[], tags=["Authentication"]
    )
    def post(self, request):
        data = self.parse(ResetSerializer, request)
        try:
            services.reset_password(data["token"], data["new_password"])
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": error.messages}) from error
        logout(request._request)
        return Response(status=204)


class LogoutView(PublicAccountAPIView):
    @account_schema(
        request=StrictSerializer, responses={204: None}, auth=[], tags=["Authentication"]
    )
    def post(self, request):
        self.parse(StrictSerializer, request)
        logout(request._request)
        return Response(status=204)


class LogoutAllView(AccountAPIView):
    @account_schema(request=StrictSerializer, responses={204: None}, tags=["Authentication"])
    def post(self, request):
        self.parse(StrictSerializer, request)
        services.logout_all(request)
        return Response(status=204)


class ReauthenticateView(AccountAPIView):
    rate_scope = "reauthenticate"

    @account_schema(request=PasswordInput, responses={204: None}, tags=["Authentication"])
    def post(self, request):
        services.reauthenticate(request, self.parse(PasswordInput, request)["password"])
        return Response(status=204)


def deletion_response(deletion, receipt):
    url = reverse("accounts:privacy-request", kwargs={"pk": deletion.pk})
    response = Response(
        {**DeletionStatusSerializer(deletion).data, "receipt": receipt, "status_url": url},
        status=202,
    )
    response["Location"] = url
    return response


class MeView(AccountAPIView):
    @account_schema(responses=AccountSerializer, tags=["Account"])
    def get(self, request):
        profile = services.get_profile(request.user)
        response = Response(AccountSerializer(request.user).data)
        response["ETag"] = f'"{profile.version}"'
        return response

    @account_schema(
        request=ProfileInputSerializer,
        responses=AccountSerializer,
        parameters=[
            OpenApiParameter(
                "If-Match",
                str,
                OpenApiParameter.HEADER,
                required=True,
                description='Quoted profile version from GET /me/, e.g. "1".',
            )
        ],
        tags=["Account"],
    )
    def patch(self, request):
        data = self.parse(ProfileInputSerializer, request)
        supplied = request.headers.get("If-Match")
        if supplied is None:
            raise AccountError("Provide the current profile ETag.", "PRECONDITION_REQUIRED", 428)
        match = re.fullmatch(r'"([1-9][0-9]{0,9})"', supplied)
        if not match:
            raise AccountError("Use a quoted profile version.", "INVALID_ETAG")
        user, profile = services.update_profile(request, data, int(match[1]))
        response = Response(AccountSerializer(user).data)
        response["ETag"] = f'"{profile.version}"'
        return response

    @account_schema(
        request=DeletionInputSerializer, responses={202: DeletionOutputSerializer}, tags=["Privacy"]
    )
    def delete(self, request):
        data = self.parse(DeletionInputSerializer, request)
        if data["confirmation"] != "delete-account":
            raise AccountError(
                "Provide explicit account deletion confirmation.", "CONFIRMATION_REQUIRED"
            )
        return deletion_response(*services.delete_data(request, "account"))


class PersonalDataView(AccountAPIView):
    @account_schema(
        request=DeletionInputSerializer, responses={202: DeletionOutputSerializer}, tags=["Privacy"]
    )
    def delete(self, request):
        data = self.parse(DeletionInputSerializer, request)
        if data["confirmation"] != "delete-personal-data":
            raise AccountError(
                "Provide explicit personal-data deletion confirmation.", "CONFIRMATION_REQUIRED"
            )
        return deletion_response(*services.delete_data(request, "personal_data"))


class PrivacyRequestView(PublicAccountAPIView):
    @account_schema(
        responses=DeletionStatusSerializer,
        parameters=[
            OpenApiParameter("X-Deletion-Receipt", str, OpenApiParameter.HEADER, required=True)
        ],
        auth=[],
        tags=["Privacy"],
    )
    def get(self, request, pk):
        receipt = request.headers.get("X-Deletion-Receipt", "")
        deletion = DeletionRequest.objects.filter(
            pk=pk, receipt_hash=services.secret_hash(receipt[:128]), expires_at__gt=timezone.now()
        ).first()
        if not deletion:
            raise AccountError("Resource not found.", "NOT_FOUND", 404)
        return Response(DeletionStatusSerializer(deletion).data)


class AdminAccountStatsView(AccountAPIView):
    permission_classes = [IsAdministrator]

    @account_schema(responses=AdminStatusSerializer, tags=["Administration"])
    def get(self, request):
        if not settings.AUTH_ADMIN_LOGIN_ENABLED:
            raise AccountError("Administrator access is unavailable.", "PERMISSION_DENIED", 403)
        return Response({"active_accounts": User.objects.filter(is_active=True).count()})
