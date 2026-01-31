import asyncio
from django.core.management.base import BaseCommand
from scraper_module.scraper import XStakeScraper
from scraper_module.models import ScraperStatus
from asgiref.sync import sync_to_async

class Command(BaseCommand):
    help = 'Persistently monitors the main match list (gstake.net/line/201) and saves updates to the DB without closing the browser.'

    async def handle_async(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Starting persistent main list monitoring..."))
        
        # Initialize status
        status, _ = await sync_to_async(ScraperStatus.objects.get_or_create)(id=1)
        status.is_running = True
        status.logs = "🚀 Starting persistent main list monitoring...\n"
        await sync_to_async(status.save)()

        async def check_status():
            s = await sync_to_async(ScraperStatus.objects.get)(id=1)
            return s.is_running

        async def log_callback(msg):
            # Print to console
            self.stdout.write(msg)
            # Save to DB
            try:
                s = await sync_to_async(ScraperStatus.objects.get)(id=1)
                # Keep last 20000 chars to avoid DB bloat
                new_logs = s.logs + msg + "\n"
                if len(new_logs) > 20000:
                    new_logs = new_logs[-20000:]
                s.logs = new_logs
                await sync_to_async(s.save)()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Log error: {e}"))

        try:
            async with XStakeScraper() as scraper:
                if not await scraper.setup_driver():
                    self.stdout.write(self.style.ERROR("Failed to set up Playwright driver. Exiting."))
                    return
                
                # This method contains the infinite loop logic for persistent monitoring
                await scraper.monitor_main_list_persistent(
                    status_check_callback=check_status,
                    log_callback=log_callback
                )
        finally:
            status = await sync_to_async(ScraperStatus.objects.get)(id=1)
            status.is_running = False
            status.logs += "\n🛑 Monitor stopped."
            await sync_to_async(status.save)()

    def handle(self, *args, **options):
        asyncio.run(self.handle_async(*args, **options))
