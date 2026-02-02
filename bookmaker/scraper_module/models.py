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


# models.py - Add this if not already present

class LiveScraperStatus(models.Model):
    """Model to track the live scraper status"""
    is_running = models.BooleanField(default=False)
    last_run = models.DateTimeField(auto_now=True)
    logs = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Live Scraper Status (Running: {self.is_running}, Last Run: {self.last_run})"

    def update_logs(self):
        """Update logs from the live_scraper.log file"""
        try:
            if os.path.exists('live_scraper.log'):
                with open('live_scraper.log', 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    self.logs = ''.join(lines[-200:]) if len(lines) > 200 else ''.join(lines)
            else:
                self.logs = "Log file not found. Live scraper may not have run yet."
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
        verbose_name_plural = "Live Scraper Status"


# Update CombinedScraperStatus model to include live status
class CombinedScraperStatus(models.Model):
    is_running = models.BooleanField(default=False)
    last_run = models.DateTimeField(auto_now=True)
    logs = models.TextField(blank=True, default="")
    live_matches_log = models.TextField(blank=True, default="")
    upcoming_matches_log = models.TextField(blank=True, default="")

    # Add these fields to track individual scraper statuses
    main_scraper_running = models.BooleanField(default=False)
    live_scraper_running = models.BooleanField(default=False)

    def update_statuses(self):
        """Update status from individual scraper models"""
        main_status = ScraperStatus.get_instance()
        live_status = LiveScraperStatus.get_instance()

        self.main_scraper_running = main_status.is_running
        self.live_scraper_running = live_status.is_running
        self.is_running = main_status.is_running or live_status.is_running
        self.save()

    def __str__(self):
        return f"Combined: Main={self.main_scraper_running}, Live={self.live_scraper_running}"

    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance"""
        instance, created = cls.objects.get_or_create(id=1)
        return instance

    class Meta:
        verbose_name_plural = "Combined Scraper Status"