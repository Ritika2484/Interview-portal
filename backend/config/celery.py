import os

from celery import Celery
from celery.signals import setup_logging
from django.conf import settings
from django.utils.log import configure_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("interview_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def configure_worker_logging(**kwargs):
    """Keep worker and API JSON logging consistent; do not let Celery replace it."""
    configure_logging(settings.LOGGING_CONFIG, settings.LOGGING)
