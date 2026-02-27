import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import CryptoTransaction
from django.conf import settings


class Command(BaseCommand):
    help = "Deletes pending crypto transactions older than 20 minutes."

    def handle(self, *args, **kwargs):
        expiration_time = timezone.now() - timedelta(minutes=20)

        expired = CryptoTransaction.objects.filter(
            status='pending',
            created_at__lt=expiration_time
        )

        count = expired.count()

        for tx in expired:
            # Delete the QR file
            file_path = os.path.join(settings.MEDIA_ROOT, tx.qr_path)
            if os.path.exists(file_path):
                os.remove(file_path)

            # Delete DB record
            tx.delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {count} expired transactions."))
