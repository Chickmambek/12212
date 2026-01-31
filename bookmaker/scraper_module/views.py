from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from .tasks import start_scraping_task, stop_scraping_task
import os
import json
from django.views.decorators.http import require_http_methods
from .models import ScraperStatus  # Import the model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from matches.models import Match, Team, Odds
from django.db.models import Count, Max, Min
import os
from django.conf import settings
import json
from datetime import datetime, timedelta


# views.py - update start_scraper view
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
        from .tasks import scraper_running
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


@require_http_methods(["GET"])
def get_scraper_stats(request):
    """Get scraper statistics"""
    try:
        # Get total matches
        total_matches = Match.objects.count()

        # Get last updated match
        last_match = Match.objects.order_by('-scraped_at').first()
        last_updated = last_match.scraped_at if last_match else None

        # Get matches added today
        today = datetime.now().date()
        today_matches = Match.objects.filter(
            scraped_at__date=today
        ).count()

        # Calculate scraping speed (matches per hour)
        hour_ago = datetime.now() - timedelta(hours=1)
        recent_matches = Match.objects.filter(
            scraped_at__gte=hour_ago
        ).count()
        scraping_speed = f"{recent_matches}/hour"

        # Get database info (simplified)
        db_records = {
            'matches': total_matches,
            'teams': Team.objects.count(),
            'odds': Odds.objects.count(),
        }

        # Estimate database size (this is a rough estimate)
        db_size_kb = (total_matches * 2) + (Team.objects.count() * 1)  # Rough KB estimate

        return JsonResponse({
            'status': 'ok',
            'total_matches': total_matches,
            'last_updated': last_updated.isoformat() if last_updated else None,
            'today_matches': today_matches,
            'scraping_speed': scraping_speed,
            'db_size': f"{db_size_kb} KB",
            'db_records': db_records,
            'avg_speed': f"{today_matches // 24 if today_matches > 24 else 1}/hour"
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


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


@csrf_exempt
@require_http_methods(["POST"])
def control_live_scraper(request, action):
    """Control the live matches scraper"""
    try:
        from .tasks import start_live_scraping_task, stop_live_scraping_task

        if action == 'start':
            result = start_live_scraping_task()
            return JsonResponse({
                'status': 'ok',
                'message': 'Live scraper started successfully',
                'is_running': True
            })
        elif action == 'stop':
            result = stop_live_scraping_task()
            return JsonResponse({
                'status': 'ok',
                'message': 'Live scraper stopped successfully',
                'is_running': False
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


@require_http_methods(["GET"])
def get_live_scraper_logs(request):
    """Get live scraper logs"""
    try:
        log_file = 'live_scraper.log'
        logs = ""

        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    logs = ''.join(lines[-200:]) if len(lines) > 200 else ''.join(lines)
            except UnicodeDecodeError:
                with open(log_file, 'r', encoding='latin-1') as f:
                    lines = f.readlines()
                    logs = ''.join(lines[-200:]) if len(lines) > 200 else ''.join(lines)
        else:
            logs = "Live scraper log file not found. Scraper may not have run yet."

        # Get live scraper status
        from .tasks import live_scraper_running

        return JsonResponse({
            'status': 'ok',
            'logs': logs,
            'is_running': live_scraper_running if 'live_scraper_running' in locals() else False
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
def clear_logs(request, log_type):
    """Clear log files based on type: main, live, or all"""
    print("clearing_logs")
    try:
        if log_type == 'main':
            log_file = 'scraper.log'
            if os.path.exists(log_file):
                # Instead of deleting, we can truncate or create empty file
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n")
                message = 'Main logs cleared successfully'
            else:
                message = 'Main log file not found'

        elif log_type == 'live':
            log_file = 'live_scraper.log'
            if os.path.exists(log_file):
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n")
                message = 'Live logs cleared successfully'
            else:
                message = 'Live log file not found'

        elif log_type == 'all':
            # Clear main logs
            if os.path.exists('scraper.log'):
                with open('scraper.log', 'w', encoding='utf-8') as f:
                    f.write(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n")

            # Clear live logs
            if os.path.exists('live_scraper.log'):
                with open('live_scraper.log', 'w', encoding='utf-8') as f:
                    f.write(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by user\n")

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


# Alternative: Create a separate log management view
@csrf_exempt
def manage_logs(request):
    """Manage log files with different actions"""
    import time

    if request.method == 'POST':
        action = request.POST.get('action', '')
        log_type = request.POST.get('type', 'all')

        try:
            if action == 'clear':
                if log_type == 'main' or log_type == 'all':
                    if os.path.exists('scraper.log'):
                        with open('scraper.log', 'w', encoding='utf-8') as f:
                            f.write(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared\n")

                if log_type == 'live' or log_type == 'all':
                    if os.path.exists('live_scraper.log'):
                        with open('live_scraper.log', 'w', encoding='utf-8') as f:
                            f.write(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared\n")

                return JsonResponse({
                    'status': 'ok',
                    'message': f'{log_type.capitalize()} logs cleared successfully'
                })

            elif action == 'download':
                # Download log file
                log_file = 'scraper.log' if log_type == 'main' else 'live_scraper.log'
                if os.path.exists(log_file):
                    from django.http import FileResponse
                    response = FileResponse(open(log_file, 'rb'))
                    response['Content-Disposition'] = f'attachment; filename="{log_file}"'
                    return response
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Log file not found: {log_file}'
                    }, status=404)

            elif action == 'view':
                # View log file content
                log_file = 'scraper.log' if log_type == 'main' else 'live_scraper.log'
                content = ''
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                return JsonResponse({
                    'status': 'ok',
                    'content': content,
                    'size': len(content)
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