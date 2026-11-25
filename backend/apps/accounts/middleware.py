from datetime import timedelta

from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone

from .models import UserSession


class AccountSessionMiddleware:
    """Idle/absolute expiry and revocation checks for API sessions, including read requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/v1/") and request.user.is_authenticated:
            now = timezone.now()
            tracked = UserSession.objects.filter(
                session_id=request.session.session_key, user=request.user
            ).first()
            if (
                not tracked
                or not request.user.is_active
                or not request.user.email_verified_at
                or request.user.deletion_requested_at
                or tracked.auth_version != request.user.auth_version
                or tracked.absolute_expires_at <= now
                or tracked.last_seen_at + timedelta(seconds=settings.AUTH_SESSION_IDLE_SECONDS)
                <= now
            ):
                logout(request)
            else:
                UserSession.objects.filter(pk=tracked.pk).update(last_seen_at=now)
                request.session.set_expiry(
                    min(
                        settings.AUTH_SESSION_IDLE_SECONDS,
                        max(1, int((tracked.absolute_expires_at - now).total_seconds())),
                    )
                )
        return self.get_response(request)
