import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db


def test_custom_user_email_password_and_uuid():
    user = get_user_model().objects.create_user("  Learner@EXAMPLE.com  ", "a-strong-test-password")
    assert user.email == "learner@example.com"
    assert isinstance(user.pk, uuid.UUID)
    assert user.check_password("a-strong-test-password")
    assert user.email_verified_at is None
    assert not user.is_staff
    assert not user.is_superuser


def test_email_case_insensitive_constraint_blocks_bypassed_model_save():
    user_model = get_user_model()
    user_model.objects.create_user("learner@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        user_model.objects.bulk_create([user_model(email="LEARNER@example.com")])


def test_manager_rejects_missing_email_and_invalid_superuser():
    manager = get_user_model().objects
    with pytest.raises(ValueError, match="email"):
        manager.create_user("")
    with pytest.raises(ValueError, match="is_staff"):
        manager.create_superuser("ops@example.com", "strong-test-password", is_staff=False)
    with pytest.raises(ValueError, match="password"):
        manager.create_superuser("ops@example.com")


def test_createsuperuser_manager():
    user = get_user_model().objects.create_superuser("Ops@EXAMPLE.com", "strong-test-password")
    assert user.is_staff and user.is_superuser and user.is_active
    assert user.email == "ops@example.com"


def test_database_session_can_be_created_and_revoked(client):
    user = get_user_model().objects.create_user("learner@example.com", "strong-test-password")
    client.force_login(user)
    from django.contrib.sessions.models import Session

    session_key = client.session.session_key
    assert Session.objects.filter(session_key=session_key).exists()
    client.logout()
    assert not Session.objects.filter(session_key=session_key).exists()
