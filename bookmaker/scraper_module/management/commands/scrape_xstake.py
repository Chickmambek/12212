# scraper/management/commands/scrape_xstake.py
import os
import sys
import django
import asyncio
from django.core.management.base import BaseCommand

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bookmaker.settings')
django.setup()

from ...scraper import XStakeScraper


class Command(BaseCommand):
    help = 'Scrape football matches and odds from xstake.bet'

    def add_arguments(self, parser):
        parser.add_argument(
            '--url',
            type=str,
            default='https://gh7.bet/line/201',
            help='URL to scrape (default: https://gh7.bet/line/201)'
        )
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Run continuous scraping every 5 seconds'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Interval in seconds for continuous scraping (default: 5)'
        )
        parser.add_argument(
            '--match-interval',
            type=int,
            default=1,
            help='Interval in seconds between match processing (default: 1)'
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting xstake.bet scraper...')

        scraper = XStakeScraper()
        if options['url']:
            scraper.base_url = options['url']

        if options['continuous']:
            self.stdout.write(
                self.style.SUCCESS(f'Starting continuous scraping every {options["interval"]} seconds')
            )
            # Run continuous scraping
            asyncio.run(scraper.continuous_scraping(
                interval_seconds=options['interval'],
                match_interval_seconds=options['match_interval']
            ))
        else:
            # Run single scraping
            success = asyncio.run(scraper.scrape_matches())

            if success:
                self.stdout.write(
                    self.style.SUCCESS('Successfully scraped and saved matches and odds!')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Scraping failed! Check logs for details.')
                )