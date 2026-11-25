import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_upgrade_preserves_existing_user_identity_and_maps_staff_roles():
    before = [("accounts", "0001_initial"), ("sessions", "0001_initial")]
    after = [("accounts", "0002_authemaildelivery_authtoken_deletionrequest_and_more")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old_apps = executor.loader.project_state(before).apps
    old_user = old_apps.get_model("accounts", "User")
    old_session = old_apps.get_model("sessions", "Session")
    staff = old_user.objects.create(
        email="upgrade-staff@example.com", password="existing-encoded-hash", is_staff=True
    )
    ordinary = old_user.objects.create(
        email="upgrade-user@example.com", password="existing-other-hash"
    )
    old_session.objects.create(
        session_key="legacy-session",
        session_data="legacy-encoded-data",
        expire_date="2030-01-01T00:00:00Z",
    )
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        new_apps = executor.loader.project_state(after).apps
        migrated_user = new_apps.get_model("accounts", "User")
        assert migrated_user.objects.get(pk=staff.pk).role == "administrator"
        assert migrated_user.objects.get(pk=staff.pk).password == "existing-encoded-hash"
        assert migrated_user.objects.get(pk=ordinary.pk).role == "candidate"
        assert (
            not new_apps.get_model("sessions", "Session")
            .objects.filter(session_key="legacy-session")
            .exists()
        )
    finally:
        MigrationExecutor(connection).migrate(after)
