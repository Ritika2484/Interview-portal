from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission


class VerifiedSessionAuthentication(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"

    def authenticate(self, request):
        result = super().authenticate(request)
        if result and (not result[0].email_verified_at or result[0].deletion_requested_at):
            raise AuthenticationFailed("Authentication required.")
        return result


class IsAdministrator(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated
            and request.user.email_verified_at
            and request.user.role == "administrator"
            and request.user.is_staff
        )
