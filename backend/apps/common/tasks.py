from celery import shared_task
from django.db import connection


@shared_task(name="common.infrastructure_probe", ignore_result=False)
def infrastructure_probe():
    """Ops-only round-trip probe, with no user payload and no public dispatch API."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return {"status": "ok"}
