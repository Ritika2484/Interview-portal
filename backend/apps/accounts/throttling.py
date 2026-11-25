import hashlib
import hmac

from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError
from rest_framework.exceptions import Throttled
from rest_framework.throttling import BaseThrottle

from .errors import AccountError

WINDOW_SCRIPT = """
local wait = 0
for i,key in ipairs(KEYS) do
  if tonumber(redis.call('GET',key) or '0') >= tonumber(ARGV[(i-1)*2+1]) then
    wait = math.max(wait, redis.call('TTL',key), 1)
  end
end
if wait > 0 then return wait end
for i,key in ipairs(KEYS) do
  if redis.call('INCR',key) == 1 then redis.call('EXPIRE',key,ARGV[(i-1)*2+2]) end
end
return 0
"""


class AuthRateThrottle(BaseThrottle):
    """Atomic shared limits; HMAC keys conceal addresses/IPs; Redis outage fails closed."""

    def allow_request(self, request, view):
        scope = getattr(view, "rate_scope", "authenticated")
        limits = settings.AUTH_RATE_LIMITS[scope]
        identities = [("ip", request.META.get("REMOTE_ADDR", "unknown"), limits[0])]
        if scope in {"login", "register", "email"}:
            email = request.data.get("email", "")
            identity = email.strip().lower()[:254] if isinstance(email, str) else "invalid"
            identities.append(("account", identity, limits[1]))
        elif request.user.is_authenticated:
            identities.append(("user", str(request.user.pk), limits[1]))
        keys, args = [], []
        for kind, identity, limit in identities:
            digest = hmac.new(
                settings.SECRET_KEY.encode(), identity.encode(), hashlib.sha256
            ).hexdigest()
            keys.append(f"{settings.AUTH_RATE_PREFIX}:{scope}:{kind}:{digest}")
            args.extend(limit)
        try:
            with Redis.from_url(
                settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
            ) as client:
                wait = int(client.eval(WINDOW_SCRIPT, len(keys), *keys, *args))
        except (RedisError, OSError, ValueError) as error:
            raise AccountError(
                "Authentication is temporarily unavailable.", "AUTH_UNAVAILABLE", 503
            ) from error
        if wait:
            raise Throttled(wait=wait)
        return True
