from django.core.management.base import BaseCommand
from scraper_module.models import ScraperStatus
import os


class Command(BaseCommand):
    help = 'Initialize the scraper database and log file'

    def handle(self, *args, **options):
        # Create or get ScraperStatus instance
        status, created = ScraperStatus.objects.get_or_create(id=1)
        if created:
            self.stdout.write(self.style.SUCCESS('Created ScraperStatus instance'))
        else:
            self.stdout.write(self.style.WARNING('ScraperStatus instance already exists'))

        # Create log file if it doesn't exist
        if not os.path.exists('scraper.log'):
            with open('scraper.log', 'w') as f:
                f.write("Scraper log initialized\n")
            self.stdout.write(self.style.SUCCESS('Created scraper.log file'))
        else:
            self.stdout.write(self.style.WARNING('scraper.log already exists'))

        # Update logs in database
        status.update_logs()
        self.stdout.write(self.style.SUCCESS('Updated logs in database'))

        self.stdout.write(self.style.SUCCESS(
            f'Scraper status: {"Running" if status.is_running else "Stopped"}'
        ))