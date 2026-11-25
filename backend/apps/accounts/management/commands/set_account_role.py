from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.services import revoke_sessions


class Command(BaseCommand):
    help = "Trusted operator only: change a verified account's role and revoke its sessions."

    def add_arguments(self, parser):
        parser.add_argument("user_id")
        parser.add_argument("role", choices=["candidate", "administrator"])

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = User.objects.select_for_update().get(
                pk=options["user_id"], is_active=True, email_verified_at__isnull=False
            )
        except (User.DoesNotExist, ValueError, ValidationError) as error:
            raise CommandError("A verified, active account UUID is required.") from error
        user.role = options["role"]
        user.is_staff = user.role == "administrator"
        # This command never grants superuser; demotion removes it.
        if not user.is_staff:
            user.is_superuser = False
        user.save(update_fields=["role", "is_staff", "is_superuser", "updated_at"])
        revoke_sessions(user)
        self.stdout.write("Account role updated; sessions revoked.")
