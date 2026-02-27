import asyncio
from django.core.management.base import BaseCommand
from scraper_module.scraper import XStakeScraper
from scraper_module.models import CombinedScraperStatus
from asgiref.sync import sync_to_async

class Command(BaseCommand):
    help = 'Persistently monitors both upcoming and live matches, and starts individual live match scrapers.'

    async def handle_async(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Starting combined persistent monitoring..."))
        
        status, _ = await sync_to_async(CombinedScraperStatus.objects.get_or_create)(id=1)
        status.is_running = True
        status.logs = "🚀 Starting combined persistent monitoring...\n"
        await sync_to_async(status.save)()

        async def check_status():
            s = await sync_to_async(CombinedScraperStatus.objects.get)(id=1)
            return s.is_running

        def log_callback(msg, log_type='main'):
            self.stdout.write(msg)
            try:
                s = CombinedScraperStatus.objects.get(id=1)
                if log_type == 'live':
                    s.live_matches_log += msg + "\n"
                elif log_type == 'upcoming':
                    s.upcoming_matches_log += msg + "\n"
                else:
                    s.logs += msg + "\n"
                s.save()
            except Exception as e:
                print(f"Log error: {e}")

        try:
            async with XStakeScraper() as scraper:
                if not await scraper.setup_driver():
                    self.stdout.write(self.style.ERROR("Failed to set up Playwright driver. Exiting."))
                    return
                
                await scraper.monitor_live_and_upcoming_orchestrator(
                    status_check_callback=check_status,
                    log_callback=log_callback
                )
        finally:
            status = await sync_to_async(CombinedScraperStatus.objects.get)(id=1)
            status.is_running = False
            status.logs += "\n🛑 Combined Monitor stopped."
            await sync_to_async(status.save)()

    def handle(self, *args, **options):
        asyncio.run(self.handle_async(*args, **options))
