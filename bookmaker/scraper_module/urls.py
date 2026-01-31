from django.urls import path, include
from django.contrib import admin
from .models import ScraperStatus, CombinedScraperStatus
from .views import start_scraper, stop_scraper, get_scraperlogs
from . import views

urlpatterns = [
    # Fix these URLs to match what your JavaScript expects
    path('scraperstatus/control/start/', start_scraper, name='start_scraper'),
    path('scraperstatus/control/stop/', stop_scraper, name='stop_scraper'),
    path('scraperstatus/logs/', get_scraperlogs, name='get_scraperlogs'),

    # New API endpoints
    path('api/scraper-stats/', views.get_scraper_stats, name='scraper_stats'),
    path('api/recent-matches/', views.get_recent_matches, name='recent_matches'),
    path('api/live-scraper/<str:action>/', views.control_live_scraper, name='control_live_scraper'),
    path('api/live-scraper/logs/', views.get_live_scraper_logs, name='live_scraper_logs'),

    # Log management endpoints
    path('api/clear-logs/<str:log_type>/', views.clear_logs, name='clear_logs'),
    path('api/manage-logs/', views.manage_logs, name='manage_logs'),
]