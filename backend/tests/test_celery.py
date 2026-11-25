import time

import pytest
from celery import Celery

from apps.common.tasks import infrastructure_probe
from config.celery import app


@pytest.mark.integration
def test_real_broker_worker_database_and_result_backend_round_trip():
    # An independent producer cannot accidentally execute eagerly in the pytest process.
    producer = Celery(
        "integration-probe", broker=app.conf.broker_url, backend=app.conf.result_backend
    )
    producer.conf.task_default_queue = app.conf.task_default_queue
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if producer.control.ping(timeout=1):
            break
        time.sleep(0.5)
    else:
        pytest.fail("No live Celery worker answered within 30 seconds.")
    result = producer.send_task(infrastructure_probe.name, args=[], kwargs={})
    try:
        assert result.get(timeout=20) == {"status": "ok"}
    finally:
        result.forget()
        producer.close()
