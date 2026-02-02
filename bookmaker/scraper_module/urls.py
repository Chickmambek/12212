# urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Main scraper URLs (existing)
    path('scraperstatus/control/start/', views.start_scraper, name='start_scraper'),
    path('scraperstatus/control/stop/', views.stop_scraper, name='stop_scraper'),
    path('scraperstatus/logs/', views.get_scraperlogs, name='get_scraperlogs'),

    # Live scraper URLs - SEPARATE ENDPOINTS
    path('api/live-scraper/start/', views.start_live_scraper, name='start_live_scraper'),
    path('api/live-scraper/stop/', views.stop_live_scraper, name='stop_live_scraper'),

    # Other live scraper URLs
    path('api/live-scraper/logs/', views.get_live_scraper_logs, name='live_scraper_logs'),
    path('api/live-scraper/status/', views.get_live_scraper_status, name='live_scraper_status'),

    # Combined URLs
    path('api/scraper-stats/', views.get_scraper_stats, name='scraper_stats'),
    path('api/scrapers/control/<str:action>/', views.control_all_scrapers, name='control_all_scrapers'),

    # Other URLs
    path('api/recent-matches/', views.get_recent_matches, name='recent_matches'),
    path('api/clear-logs/<str:log_type>/', views.clear_logs, name='clear_logs'),
    path('api/manage-logs/', views.manage_logs, name='manage_logs'),
]