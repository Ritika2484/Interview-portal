from datetime import timedelta

from celery import shared_task
from django.contrib.sessions.models import Session
from django.utils import timezone

from .models import AuthEmailDelivery, AuthToken, DeletionRequest
from .services import deliver_email


@shared_task(ignore_result=True)
def process_auth_emails():
    # Durable records survive broker outages; concurrent schedulers are safe via user locks.
    ids = list(
        AuthEmailDelivery.objects.filter(state="pending", next_attempt_at__lte=timezone.now())
        .order_by("created_at")
        .values_list("pk", flat=True)[:50]
    )
    for delivery_id in ids:
        deliver_email(delivery_id)


@shared_task(ignore_result=True)
def prune_auth_records():
    now = timezone.now()
    for model, query in [
        (AuthToken, AuthToken.objects.filter(expires_at__lt=now - timedelta(days=1))),
        (
            AuthEmailDelivery,
            AuthEmailDelivery.objects.exclude(state="pending").filter(
                completed_at__lt=now - timedelta(days=7)
            ),
        ),
        (DeletionRequest, DeletionRequest.objects.filter(expires_at__lte=now)),
        (Session, Session.objects.filter(expire_date__lte=now)),
    ]:
        model.objects.filter(pk__in=list(query.values_list("pk", flat=True)[:500])).delete()
