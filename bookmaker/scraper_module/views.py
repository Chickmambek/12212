# views.py - Updated with live scraper workflow
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from .tasks import *
import os
import json
from django.views.decorators.http import require_http_methods
from .models import ScraperStatus, LiveScraperStatus  # Import LiveScraperStatus model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from matches.models import Match, Team, Odds
from django.db.models import Count, Max, Min
import os
from django.conf import settings
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta


# ============== MAIN SCRAPER VIEWS (EXISTING) ==============

@csrf_exempt
@require_http_methods(["GET", "POST"])
def start_scraper(request):
    """Handle scraper start requests"""
    print(f"start_scraper endpoint called with method: {request.method}")

    try:
        # Get the scraper status instance
        scraper_status = ScraperStatus.get_instance()

        # Check if already running
        if scraper_status.is_running:
            return JsonResponse({
                'status': 'error',
                'message': 'Scraper is already running!',
                'is_running': True
            }, status=400)

        # IMPORTANT: Also check the global flag from tasks.py

        if scraper_running:
            return JsonResponse({
                'status': 'error',
                'message': 'Scraper is already running (task flag)!',
                'is_running': True
            }, status=400)

        # Call the task function
        result = start_scraping_task()
        print(f"Task started: {result}")

        response_data = {
            'status': 'ok',
            'message': 'Scraper started successfully',
            'is_running': True
        }

        return JsonResponse(response_data)

    except Exception as e:
        print(f"Error starting scraper: {str(e)}")
        import traceback
        traceback.print_exc()

        return JsonResponse({
            'status': 'error',
            'message': f'Failed to start scraper: {str(e)}',
            'is_running': False
        }, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def stop_scraper(request):
    """Handle scraper stop requests"""
    print(f"stop_scraper endpoint called with method: {request.method}")

    try:
        # Get the scraper status instance
        scraper_status = ScraperStatus.get_instance()

        # Check if already stopped
        if not scraper_status.is_running:
            return JsonResponse({
                'status': 'error',
                'message': 'Scraper is already stopped!',
                'is_running': False
            }, status=400)

        # Call the task function directly (no Celery)
        result = stop_scraping_task()
        print(f"Task stopped")

        response_data = {
            'status': 'ok',
            'message': 'Scraper stopped successfully',
            'is_running': False
        }

        return JsonResponse(response_data)

    except Exception as e:
        print(f"Error stopping scraper: {str(e)}")
        import traceback
        traceback.print_exc()

        return JsonResponse({
            'status': 'error',
            'message': f'Failed to stop scraper: {str(e)}',
            'is_running': scraper_status.is_running
        }, status=500)


@require_http_methods(["GET"])
def get_scraperlogs(request):
    """Get scraper logs and status"""
    print("get_scraperlogs endpoint called")
    try:
        # Get the scraper status instance
        scraper_status = ScraperStatus.get_instance()

        # Update logs from file with proper encoding
        try:
            if os.path.exists('scraper.log'):
                # Try UTF-8 first, then fallback to latin-1
                try:
                    with open('scraper.log', 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    with open('scraper.log', 'r', encoding='latin-1') as f:
                        lines = f.readlines()

                # Get last 200 lines
                scraper_status.logs = ''.join(lines[-200:]) if len(lines) > 200 else ''.join(lines)
            else:
                scraper_status.logs = "Log file not found. Scraper may not have run yet."
            scraper_status.save()
        except Exception as e:
            scraper_status.logs = f"Error reading logs: {str(e)}"
            scraper_status.save()

        # Check if log file exists for additional info
        log_file_exists = os.path.exists('scraper.log')

        return JsonResponse({
            'status': 'ok',
            'logs': scraper_status.logs,
            'is_running': scraper_status.is_running,
            'last_run': scraper_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if scraper_status.last_run else None,
            'log_file_exists': log_file_exists
        })
    except Exception as e:
        print(f"Error getting scraper logs: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'logs': f'Error reading logs: {str(e)}',
            'is_running': False,
            'last_run': None,
            'log_file_exists': False
        }, status=500)


# ============== LIVE SCRAPER VIEWS ==============
# ============== LIVE SCRAPER VIEWS ==============

@csrf_exempt
@require_http_methods(["GET", "POST"])
def start_live_scraper(request):
    """Start the live matches scraper"""
    print(f"start_live_scraper endpoint called with method: {request.method}")

    # For GET requests, return status info
    if request.method == 'GET':
        try:
            # Get the live scraper status instance
            live_status = LiveScraperStatus.get_instance()

            # Get global flag for backup

            global_is_running = live_scraper_running if 'live_scraper_running' in dir() else False

            # Use database status, fallback to global flag
            is_running_status = live_status.is_running or global_is_running

            return JsonResponse({
                'status': 'info',
                'endpoint': '/admin21/scraper_module/api/live-scraper/start/',
                'method': request.method,
                'allowed_methods': ['GET', 'POST'],
                'description': 'Start the live matches scraper',
                'current_status': {
                    'is_running': is_running_status,
                    'last_run': live_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if live_status.last_run else None,
                    'action': 'start',
                    'note': 'Use POST method to actually start the scraper'
                }
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error getting status: {str(e)}'
            }, status=500)

    # For POST requests, handle the actual start logic
    elif request.method == 'POST':
        try:
            # Get the live scraper status instance
            live_status = LiveScraperStatus.get_instance()

            print("Live scraper status POST : " + str(live_status))

            # Check if already running
            if live_status.is_running:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Live scraper is already running!',
                    'is_running': True
                }, status=400)

            # Check global flag

            if live_scraper_running:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Live scraper is already running (task flag)!',
                    'is_running': True
                }, status=400)

            # Start the live scraper
            result = start_live_scraping_task()
            print(f"Live task started: {result}")

            # Update status
            live_status.refresh_from_db()

            return JsonResponse({
                'status': 'ok',
                'message': 'Live scraper started successfully',
                'is_running': live_status.is_running,
                'last_run': live_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if live_status.last_run else None
            })

        except Exception as e:
            print(f"Error starting live scraper: {str(e)}")
            import traceback
            traceback.print_exc()

            return JsonResponse({
                'status': 'error',
                'message': f'Failed to start live scraper: {str(e)}',
                'is_running': False
            }, status=500)

    else:
        return JsonResponse({
            'status': 'error',
            'message': f'Method not allowed: {request.method}'
        }, status=405)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def stop_live_scraper(request):
    """Stop the live matches scraper"""
    print(f"stop_live_scraper endpoint called with method: {request.method}")

    # For GET requests, return status info
    if request.method == 'GET':
        try:
            # Get the live scraper status instance
            live_status = LiveScraperStatus.get_instance()

            # Get global flag for backup

            global_is_running = live_scraper_running if 'live_scraper_running' in dir() else False

            # Use database status, fallback to global flag
            is_running_status = live_status.is_running or global_is_running

            return JsonResponse({
                'status': 'info',
                'endpoint': '/admin21/scraper_module/api/live-scraper/stop/',
                'method': request.method,
                'allowed_methods': ['GET', 'POST'],
                'description': 'Stop the live matches scraper',
                'current_status': {
                    'is_running': is_running_status,
                    'last_run': live_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if live_status.last_run else None,
                    'action': 'stop',
                    'note': 'Use POST method to actually stop the scraper'
                }
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error getting status: {str(e)}'
            }, status=500)

    # For POST requests, handle the actual stop logic
    elif request.method == 'POST':
        try:
            # Get the live scraper status instance
            live_status = LiveScraperStatus.get_instance()

            # Check if already stopped
            if not live_status.is_running:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Live scraper is already stopped!',
                    'is_running': False
                }, status=400)

            # Stop the live scraper
            result = stop_live_scraping_task()
            print(f"Live task stopped: {result}")

            # Update status
            live_status.refresh_from_db()

            return JsonResponse({
                'status': 'ok',
                'message': 'Live scraper stopped successfully',
                'is_running': live_status.is_running,
                'last_run': live_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if live_status.last_run else None
            })

        except Exception as e:
            print(f"Error stopping live scraper: {str(e)}")
            import traceback
            traceback.print_exc()

            return JsonResponse({
                'status': 'error',
                'message': f'Failed to stop live scraper: {str(e)}',
                'is_running': live_status.is_running
            }, status=500)

    else:
        return JsonResponse({
            'status': 'error',
            'message': f'Method not allowed: {request.method}'
        }, status=405)

@require_http_methods(["GET"])
def get_live_scraper_logs(request):
    """Get live scraper logs and status"""
    print("get_live_scraper_logs endpoint called")

    try:
        # Get the live scraper status instance
        live_status = LiveScraperStatus.get_instance()

        # Update logs from file with proper encoding
        try:
            if os.path.exists('live_scraper.log'):
                # Try UTF-8 first, then fallback to latin-1
                try:
                    with open('live_scraper.log', 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    with open('live_scraper.log', 'r', encoding='latin-1') as f:
                        lines = f.readlines()

                # Get last 200 lines
                live_status.logs = ''.join(lines[-200:]) if len(lines) > 200 else ''.join(lines)
            else:
                live_status.logs = "Live scraper log file not found. Scraper may not have run yet."
            live_status.save()
        except Exception as e:
            live_status.logs = f"Error reading live logs: {str(e)}"
            live_status.save()

        # Check if log file exists
        log_file_exists = os.path.exists('live_scraper.log')

        # Get global flag for backup

        global_is_running = live_scraper_running if 'live_scraper_running' in dir() else False

        # Use database status, fallback to global flag
        is_running_status = live_status.is_running or global_is_running

        return JsonResponse({
            'status': 'ok',
            'logs': live_status.logs,
            'is_running': is_running_status,
            'last_run': live_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if live_status.last_run else None,
            'log_file_exists': log_file_exists
        })

    except Exception as e:
        print(f"Error getting live scraper logs: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'logs': f'Error reading live logs: {str(e)}',
            'is_running': False,
            'last_run': None,
            'log_file_exists': False
        }, status=500)


@require_http_methods(["GET"])
def get_live_scraper_status(request):
    """Get live scraper status without logs"""
    print("get_live_scraper_status endpoint called")

    try:
        # Get the live scraper status instance
        live_status = LiveScraperStatus.get_instance()

        # Get global flag for backup

        global_is_running = live_scraper_running if 'live_scraper_running' in dir() else False

        # Use database status, fallback to global flag
        is_running_status = live_status.is_running or global_is_running

        # Check if log file exists
        log_file_exists = os.path.exists('live_scraper.log')

        # Get log file size if exists
        log_file_size = 0
        if log_file_exists:
            log_file_size = os.path.getsize('live_scraper.log')

        return JsonResponse({
            'status': 'ok',
            'is_running': is_running_status,
            'last_run': live_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if live_status.last_run else None,
            'log_file_exists': log_file_exists,
            'log_file_size_kb': round(log_file_size / 1024, 2) if log_file_exists else 0
        })

    except Exception as e:
        print(f"Error getting live scraper status: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'is_running': False,
            'last_run': None
        }, status=500)


# ============== COMBINED SCRAPER VIEWS ==============

@require_http_methods(["GET"])
def get_scraper_stats(request):
    """Get comprehensive statistics for both scrapers"""
    try:
        # Get scraper statuses
        main_status = ScraperStatus.get_instance()
        live_status = LiveScraperStatus.get_instance()

        # Calculate time ranges
        now = datetime.now()
        today_start = datetime.combine(now.date(), datetime.min.time())

        # Functionally identical to timedelta(hours=1) and timedelta(days=1)
        hour_ago = now - relativedelta(hours=1)
        day_ago = now - relativedelta(days=1)

        # Database statistics
        total_matches = Match.objects.count()
        live_matches = Match.objects.filter(status='live').count()
        upcoming_matches = Match.objects.filter(status='upcoming').count()
        finished_matches = Match.objects.filter(status='finished').count()

        # Get last updated match
        last_match = Match.objects.order_by('-scraped_at').first()
        last_updated = last_match.scraped_at if last_match else None

        # Count matches by time periods
        today_matches = Match.objects.filter(
            scraped_at__gte=today_start
        ).count()

        recent_matches = Match.objects.filter(
            scraped_at__gte=hour_ago
        ).count()

        daily_matches = Match.objects.filter(
            scraped_at__gte=day_ago
        ).count()

        # Calculate scraping speed
        scraping_speed = f"{recent_matches}/hour"
        avg_daily_speed = f"{daily_matches // 24 if daily_matches > 24 else 1}/hour"

        # Database records count
        db_records = {
            'matches': total_matches,
            'teams': Team.objects.count(),
            'odds': Odds.objects.count(),
            'live_matches': live_matches,
            'upcoming_matches': upcoming_matches,
            'finished_matches': finished_matches,
        }

        # Log file statistics
        log_stats = {
            'main_scraper': {
                'exists': os.path.exists('scraper.log'),
                'size_kb': 0,
                'modified': None
            },
            'live_scraper': {
                'exists': os.path.exists('live_scraper.log'),
                'size_kb': 0,
                'modified': None
            }
        }

        # Get log file details
        for scraper, log_file in [('main_scraper', 'scraper.log'),
                                  ('live_scraper', 'live_scraper.log')]:
            if os.path.exists(log_file):
                size = os.path.getsize(log_file)
                log_stats[scraper]['size_kb'] = round(size / 1024, 2)
                mtime = os.path.getmtime(log_file)
                log_stats[scraper]['modified'] = datetime.fromtimestamp(mtime).isoformat()

        # System information
        system_info = {
            'current_time': now.isoformat(),
            'today': today_start.isoformat(),
            'uptime_hours': None  # You could add system uptime here
        }

        response_data = {
            'status': 'ok',
            'system': system_info,
            'database': {
                'total_records': total_matches,
                'last_updated': last_updated.isoformat() if last_updated else None,
                'today_new': today_matches,
                'recent_hour': recent_matches,
                'last_24h': daily_matches,
                'scraping_speed': scraping_speed,
                'avg_daily_speed': avg_daily_speed,
                'records': db_records,
                'match_status': {
                    'live': live_matches,
                    'upcoming': upcoming_matches,
                    'finished': finished_matches
                }
            },
            'scrapers': {
                'main': {
                    'is_running': main_status.is_running,
                    'last_run': main_status.last_run.isoformat() if main_status.last_run else None,
                    'status': main_status.status,
                    'log': log_stats['main_scraper']
                },
                'live': {
                    'is_running': live_status.is_running,
                    'last_run': live_status.last_run.isoformat() if live_status.last_run else None,
                    'status': live_status.status,
                    'log': log_stats['live_scraper']
                }
            }
        }

        return JsonResponse(response_data, json_dumps_params={'indent': 2})

    except Exception as e:
        import traceback
        error_details = {
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }
        return JsonResponse(error_details, status=500, json_dumps_params={'indent': 2})

@require_http_methods(["GET"])
def get_recent_matches(request):
    """Get recently scraped matches"""
    try:
        matches = Match.objects.order_by('-scraped_at')[:10]

        matches_data = []
        for match in matches:
            matches_data.append({
                'id': match.id,
                'home_team': match.home_team.name if match.home_team else 'N/A',
                'away_team': match.away_team.name if match.away_team else 'N/A',
                'league': match.league,
                'match_date': match.match_date.isoformat() if match.match_date else None,
                'home_odds': float(match.home_odds) if match.home_odds else None,
                'draw_odds': float(match.draw_odds) if match.draw_odds else None,
                'away_odds': float(match.away_odds) if match.away_odds else None,
                'status': match.status,
                'scraped_at': match.scraped_at.isoformat() if match.scraped_at else None,
            })

        return JsonResponse({
            'status': 'ok',
            'matches': matches_data,
            'count': len(matches_data)
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


# ============== LOG MANAGEMENT VIEWS ==============

@csrf_exempt
def clear_logs(request, log_type):
    """Clear log files based on type: main, live, or all"""
    print(f"clear_logs endpoint called with type: {log_type}")

    try:
        if log_type == 'main':
            # Clear main scraper log file
            if os.path.exists('scraper.log'):
                with open('scraper.log', 'w', encoding='utf-8') as f:
                    f.write(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n")
                message = 'Main logs cleared successfully'
            else:
                message = 'Main log file not found'

            # Also clear database logs
            scraper_status = ScraperStatus.get_instance()
            scraper_status.logs = f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n"
            scraper_status.save()

        elif log_type == 'live':
            # Clear live scraper log file
            if os.path.exists('live_scraper.log'):
                with open('live_scraper.log', 'w', encoding='utf-8') as f:
                    f.write(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n")
                message = 'Live logs cleared successfully'
            else:
                message = 'Live log file not found'

            # Also clear database logs
            live_status = LiveScraperStatus.get_instance()
            live_status.logs = f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n"
            live_status.save()

        elif log_type == 'all':
            # Clear all log files
            for log_file in ['scraper.log', 'live_scraper.log']:
                if os.path.exists(log_file):
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n")

            # Clear database logs for both
            scraper_status = ScraperStatus.get_instance()
            scraper_status.logs = f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n"
            scraper_status.save()

            live_status = LiveScraperStatus.get_instance()
            live_status.logs = f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n"
            live_status.save()

            message = 'All logs cleared successfully'

        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Invalid log type: {log_type}'
            }, status=400)

        return JsonResponse({
            'status': 'ok',
            'message': message
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
def manage_logs(request):
    """Manage log files with different actions"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action', '')
            log_type = data.get('type', 'all')

            if action == 'clear':
                # Call the clear_logs function with the appropriate type
                if log_type == 'all':
                    return clear_logs(request, 'all')
                elif log_type == 'main':
                    return clear_logs(request, 'main')
                elif log_type == 'live':
                    return clear_logs(request, 'live')
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Invalid log type: {log_type}'
                    }, status=400)

            elif action == 'download':
                # Prepare log file for download
                if log_type == 'main':
                    log_file = 'scraper.log'
                    filename = f'scraper_log_{timezone.now().strftime("%Y%m%d_%H%M%S")}.txt'
                elif log_type == 'live':
                    log_file = 'live_scraper.log'
                    filename = f'live_scraper_log_{timezone.now().strftime("%Y%m%d_%H%M%S")}.txt'
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Invalid log type for download: {log_type}'
                    }, status=400)

                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    from django.http import HttpResponse
                    response = HttpResponse(content, content_type='text/plain')
                    response['Content-Disposition'] = f'attachment; filename="{filename}"'
                    return response
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Log file not found: {log_file}'
                    }, status=404)

            elif action == 'view':
                # View log file content (truncated)
                if log_type == 'main':
                    log_file = 'scraper.log'
                elif log_type == 'live':
                    log_file = 'live_scraper.log'
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Invalid log type for view: {log_type}'
                    }, status=400)

                content = ''
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        content = ''.join(lines[-100:])  # Last 100 lines only

                return JsonResponse({
                    'status': 'ok',
                    'content': content,
                    'size': len(content),
                    'filename': log_file
                })

            else:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Invalid action: {action}'
                }, status=400)

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    }, status=400)


# ============== BOTH SCRAPERS CONTROL ==============

@csrf_exempt
@require_http_methods(["POST"])
def control_all_scrapers(request, action):
    """Control both scrapers at once (start/stop all)"""
    print(f"control_all_scrapers endpoint called with action: {action}")

    try:
        if action == 'start':
            # Start main scraper
            main_result = start_scraping_task()

            # Start live scraper

            live_result = start_live_scraping_task()

            # Get statuses
            main_status = ScraperStatus.get_instance()
            live_status = LiveScraperStatus.get_instance()

            return JsonResponse({
                'status': 'ok',
                'message': 'All scrapers started successfully',
                'main_scraper': {
                    'is_running': main_status.is_running,
                    'last_run': main_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if main_status.last_run else None
                },
                'live_scraper': {
                    'is_running': live_status.is_running,
                    'last_run': live_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if live_status.last_run else None
                }
            })

        elif action == 'stop':
            # Stop main scraper
            main_result = stop_scraping_task()

            # Stop live scraper

            live_result = stop_live_scraping_task()

            # Get statuses
            main_status = ScraperStatus.get_instance()
            live_status = LiveScraperStatus.get_instance()

            return JsonResponse({
                'status': 'ok',
                'message': 'All scrapers stopped successfully',
                'main_scraper': {
                    'is_running': main_status.is_running,
                    'last_run': main_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if main_status.last_run else None
                },
                'live_scraper': {
                    'is_running': live_status.is_running,
                    'last_run': live_status.last_run.strftime('%Y-%m-%d %H:%M:%S') if live_status.last_run else None
                }
            })

        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Invalid action: {action}'
            }, status=400)

    except Exception as e:
        print(f"Error controlling all scrapers: {str(e)}")
        import traceback
        traceback.print_exc()

        return JsonResponse({
            'status': 'error',
            'message': f'Failed to control all scrapers: {str(e)}'
        }, status=500)