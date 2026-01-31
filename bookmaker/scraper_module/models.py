from django.db import models
import os


class ScraperStatus(models.Model):
    is_running = models.BooleanField(default=False)
    last_run = models.DateTimeField(auto_now=True)
    logs = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Scraper Status (Running: {self.is_running})"

    def update_logs(self):
        """Update logs from the scraper.log file"""
        try:
            if os.path.exists('scraper.log'):
                with open('scraper.log', 'r') as f:
                    # Get last 200 lines
                    lines = f.readlines()
                    self.logs = ''.join(lines[-200:]) if len(lines) > 200 else ''.join(lines)
            else:
                self.logs = "Log file not found. Scraper may not have run yet."
            self.save()
            return self.logs
        except Exception as e:
            self.logs = f"Error reading logs: {str(e)}"
            self.save()
            return self.logs

    def get_status(self):
        """Get current status with logs"""
        self.update_logs()
        return {
            'is_running': self.is_running,
            'last_run': self.last_run,
            'logs': self.logs
        }

    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance"""
        instance, created = cls.objects.get_or_create(id=1)
        return instance

    class Meta:
        verbose_name_plural = "Scraper Status"


class CombinedScraperStatus(models.Model):
    is_running = models.BooleanField(default=False)
    last_run = models.DateTimeField(auto_now=True)
    logs = models.TextField(blank=True, default="")
    live_matches_log = models.TextField(blank=True, default="")
    upcoming_matches_log = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Combined Scraper Status (Running: {self.is_running})"

    class Meta:
        verbose_name_plural = "Combined Scraper Status"