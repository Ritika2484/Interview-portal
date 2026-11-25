import uuid

import pytest


@pytest.fixture(autouse=True)
def isolated_auth_rate_keys(settings):
    # No FLUSHDB: never discard another process's cache/broker data during tests.
    settings.AUTH_RATE_PREFIX = f"test-auth:{uuid.uuid4().hex}"
