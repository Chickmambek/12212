import logging
import asyncio
from django_q.tasks import async_task, schedule
from django.utils import timezone
from .models import Match
from .services.settlement import settle_bets_for_match
from scraper_module.scraper import XStakeScraper
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

def schedule_bet_settlement():
    """
    Schedules the tasks.
    """
    # 1. Main Scraper (Leagues & Matches) - Runs every 5 minutes
    schedule('matches.tasks.scrape_leagues_task',
             schedule_type='I',
             minutes=5,
             repeats=-1)

    # 2. Detail Scraper (Odds & Updates) - Runs every 2 minutes
    schedule('matches.tasks.scrape_match_details_task',
             schedule_type='I',
             minutes=2,
             repeats=-1)

    # 3. Settlement - Runs every 1 minute
    schedule('matches.tasks.settle_finished_matches_task',
             schedule_type='I',
             minutes=1,
             repeats=-1)
             
    # 4. Live Match Monitor - Runs every 1 minute
    schedule('matches.tasks.monitor_live_matches_task',
             schedule_type='I',
             minutes=1,
             repeats=-1)

def scrape_leagues_task():
    """
    Task 1: Scrapes the main page to get leagues and match lists.
    Does NOT go into match details.
    """
    print("\n" + "="*60)
    print(f"🔄 [{timezone.now().strftime('%H:%M:%S')}] Task 1: Scraping Leagues & Matches")
    print("="*60)
    
    scraper = XStakeScraper()
    try:
        # Run only the main list scraping
        asyncio.run(scraper.scrape_main_list_only())
        print("✅ League scraping completed.")
    except Exception as e:
        print(f"❌ League scraping failed: {e}")

def scrape_match_details_task():
    """
    Task 2: Iterates through existing matches in DB and updates them.
    Prioritizes Live and Upcoming matches.
    """
    print("\n" + "="*60)
    print(f"🔄 [{timezone.now().strftime('%H:%M:%S')}] Task 2: Updating Match Details")
    print("="*60)
    
    # Get matches that need updating: Live matches + Upcoming in next 24h
    matches_to_update = Match.objects.filter(
        status__in=[Match.STATUS_LIVE, Match.STATUS_UPCOMING],
        match_date__lte=timezone.now() + timezone.timedelta(hours=24),
        match_url__isnull=False
    ).order_by('match_date')
    
    print(f"🎯 Found {matches_to_update.count()} matches to update.")
    
    if matches_to_update.exists():
        scraper = XStakeScraper()
        try:
            asyncio.run(scraper.update_specific_matches(matches_to_update))
            print("✅ Match details update completed.")
        except Exception as e:
            print(f"❌ Match details update failed: {e}")
    else:
        print("   No matches need updating.")

def monitor_live_matches_task():
    """
    Task 4: Checks live matches for score updates and finished status.
    """
    print("\n" + "="*60)
    print(f"🔴 [{timezone.now().strftime('%H:%M:%S')}] Task 4: Monitoring Live Matches")
    print("="*60)
    
    # Find matches that are currently live or should be live (started recently)
    live_matches = Match.objects.filter(
        match_date__lte=timezone.now(),
        status__in=[Match.STATUS_UPCOMING, Match.STATUS_LIVE],
        match_url__isnull=False
    )
    
    if live_matches.exists():
        print(f"🎯 Found {live_matches.count()} potential live matches.")
        scraper = XStakeScraper()
        try:
            asyncio.run(scraper.update_live_matches(live_matches))
            print("✅ Live monitoring completed.")
        except Exception as e:
            print(f"❌ Live monitoring failed: {e}")
    else:
        print("   No live matches to monitor.")

def settle_finished_matches_task():
    """
    Task 3: Settles bets for finished matches.
    """
    print("\n" + "="*60)
    print(f"⚖️  [{timezone.now().strftime('%H:%M:%S')}] Task 3: Settling Bets")
    print("="*60)
    
    finished_matches = Match.objects.filter(status=Match.STATUS_FINISHED)
    count = 0
    for match in finished_matches:
        if match.bets.filter(status='pending').exists():
            print(f"   Settling bets for match: {match}")
            settle_bets_for_match(match)
            count += 1
            
    print(f"🏁 Settlement complete. Processed {count} matches.")
