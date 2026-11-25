import logging

from django.conf import settings
from django.db import DatabaseError, connection
from drf_spectacular.utils import extend_schema
from redis import Redis
from redis.exceptions import RedisError
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["alive", "ready", "not_ready"])


class PublicHealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []
    http_method_names = ["get", "head", "options"]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class LivenessView(PublicHealthView):
    @extend_schema(responses={200: HealthSerializer}, auth=[], tags=["Health"])
    def get(self, request):
        # No DB, broker or external provider access here.
        return Response({"status": "alive"})


class ReadinessView(PublicHealthView):
    @extend_schema(
        responses={200: HealthSerializer, 503: HealthSerializer}, auth=[], tags=["Health"]
    )
    def get(self, request):
        ready = True
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector'), "
                    "to_regclass('accounts_user') IS NOT NULL, "
                    "to_regclass('django_session') IS NOT NULL"
                )
                ready = all(cursor.fetchone())
        except DatabaseError:
            ready = False
            logger.warning("dependency_unavailable", extra={"dependency": "database"})
        try:
            with Redis.from_url(
                settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
            ) as redis_client:
                ready = bool(redis_client.ping()) and ready
        except (RedisError, OSError, ValueError):
            ready = False
            logger.warning("dependency_unavailable", extra={"dependency": "redis"})
        return Response({"status": "ready" if ready else "not_ready"}, status=200 if ready else 503)
