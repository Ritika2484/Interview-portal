from unittest.mock import MagicMock

import pytest
from django.db import OperationalError
from redis.exceptions import ConnectionError as RedisConnectionError


def test_liveness_has_no_external_dependencies(client):
    response = client.get("/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response["Cache-Control"] == "no-store"
    assert response["X-Request-ID"]


def test_liveness_rejects_mutation(client):
    assert client.post("/health/live/", {}).status_code == 405


@pytest.mark.parametrize("db_ok,redis_ok", [(True, True), (False, True), (True, False)])
def test_readiness_reports_minimal_status(client, monkeypatch, db_ok, redis_ok):
    database = MagicMock()
    cursor = database.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (db_ok, db_ok, db_ok)
    redis_factory = MagicMock()
    redis_factory.return_value.__enter__.return_value.ping.return_value = redis_ok
    monkeypatch.setattr("apps.common.health.connection", database)
    monkeypatch.setattr("apps.common.health.Redis.from_url", redis_factory)
    response = client.get("/health/ready/")
    assert response.status_code == (200 if db_ok and redis_ok else 503)
    assert response.json() == {"status": "ready" if db_ok and redis_ok else "not_ready"}
    assert response["Cache-Control"] == "no-store"


def test_readiness_redacts_infrastructure_errors(client, monkeypatch, caplog):
    database = MagicMock()
    database.cursor.side_effect = OperationalError("postgresql://secret:password@private-host/db")
    monkeypatch.setattr("apps.common.health.connection", database)
    monkeypatch.setattr(
        "apps.common.health.Redis.from_url",
        MagicMock(side_effect=RedisConnectionError("redis://secret:password@private-host")),
    )
    response = client.get("/health/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "password" not in response.content.decode()
    assert "password" not in caplog.text


@pytest.mark.django_db
def test_readiness_queries_real_pgvector_schema(client, monkeypatch):
    redis_factory = MagicMock()
    redis_factory.return_value.__enter__.return_value.ping.return_value = True
    monkeypatch.setattr("apps.common.health.Redis.from_url", redis_factory)
    assert client.get("/health/ready/").json() == {"status": "ready"}
