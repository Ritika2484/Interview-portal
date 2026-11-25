from django.core.management.base import BaseCommand

from apps.accounts.tasks import process_auth_emails


class Command(BaseCommand):
    help = "Process one bounded batch of durable authentication email intents (no secrets printed)."

    def handle(self, *args, **options):
        process_auth_emails.run()
        self.stdout.write("Authentication email batch processed.")
