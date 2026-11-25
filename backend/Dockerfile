# Runtime and development share the same supported Python release.
FROM python:3.14.10-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY requirements/ /app/requirements/
RUN pip install --no-cache-dir -r requirements/base.txt
COPY --chown=app:app backend/ /app/backend/
WORKDIR /app/backend

FROM base AS development
ENV DJANGO_SETTINGS_MODULE=config.settings.development
USER root
RUN pip install --no-cache-dir -r /app/requirements/dev.txt
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS production
USER app
EXPOSE 8000
# Collectstatic and migrations are explicit release jobs, not worker startup side effects.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "/dev/null", "--error-logfile", "-", "--capture-output"]

