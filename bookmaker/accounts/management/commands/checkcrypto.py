from django.core.management.base import BaseCommand
from accounts.services.checker import check_deposits
import time


class Command(BaseCommand):
    help = "Checks blockchain deposits continuously with live logging"

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=1,
            help='Seconds between checks'
        )

    def handle(self, *args, **options):
        interval = options['interval']
        print(f"⚡ Starting continuous deposit checker (interval: {interval}s). Press CTRL+C to stop.\n")

        try:
            while True:
                changes = check_deposits()
                for msg in changes:
                    print(msg)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n🛑 Checker stopped by user.")
