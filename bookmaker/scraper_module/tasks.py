# tasks.py
import time
import threading
import logging
import asyncio
import os
from django.utils import timezone
from .models import ScraperStatus, CombinedScraperStatus, LiveScraperStatus  # Import models
from scraper_module.scraper import XStakeScraper  # Import your scraper class

# Get logger
logger = logging.getLogger(__name__)

# Global flags to control the scrapers
scraper_running = False
scraper_thread = None
scraper_instance = None

live_scraper_running = False
live_scraper_thread = None
live_scraper_instance = None


# ============== Helper Functions ==============
def write_to_log(message):
    """Safely write message to log file with proper encoding"""
    try:
        # Use UTF-8 encoding to support emojis
        with open('scraper.log', 'a', encoding='utf-8') as f:
            f.write(message + '\n')
    except Exception as e:
        # Fallback: write without emojis
        safe_message = message.encode('ascii', 'ignore').decode('ascii')
        with open('scraper.log', 'a', encoding='utf-8') as f:
            f.write(safe_message + '\n')
        print(f"Warning: Could not write emoji to log: {e}")


def write_live_log(message):
    """Write to live scraper log file"""
    try:
        with open('live_scraper.log', 'a', encoding='utf-8') as f:
            f.write(message + '\n')
    except Exception as e:
        safe_message = message.encode('ascii', 'ignore').decode('ascii')
        with open('live_scraper.log', 'a', encoding='utf-8') as f:
            f.write(safe_message + '\n')


def log_callback_to_file(msg):
    """Callback function to write scraper logs to file"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    write_to_log(f"[{timestamp}] {msg}")
    print(msg)  # Also print to console


def live_log_callback_to_file(msg):
    """Callback function to write live scraper logs to file"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    write_live_log(f"[{timestamp}] {msg}")
    print(f"Live Scraper: {msg}")  # Also print to console


async def async_log_callback(msg):
    """Async version of log callback for the main scraper"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] {msg}"
    # Update database log
    await asyncio.to_thread(update_main_scraper_log, log_message)
    # Run sync log function in thread
    await asyncio.to_thread(log_callback_to_file, log_message)


async def async_live_log_callback(msg):
    """Async version of log callback for the live scraper"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] {msg}"
    # Update database log
    await asyncio.to_thread(update_live_scraper_log, log_message)
    # Run sync log function in thread
    await asyncio.to_thread(live_log_callback_to_file, log_message)


# ============== Database Update Functions ==============
def update_main_scraper_log(message):
    """Update the main scraper log in the database"""
    try:
        scraper_status = ScraperStatus.get_instance()
        # Keep only last 2000 characters to prevent DB bloat
        if len(scraper_status.logs) > 2000:
            scraper_status.logs = scraper_status.logs[-2000:]
        scraper_status.logs += message + "\n"
        scraper_status.save()
    except Exception as e:
        print(f"Error updating main scraper log in DB: {e}")


def update_live_scraper_log(message):
    """Update the live scraper log in the database"""
    try:
        # Try to get or create LiveScraperStatus instance
        from .models import LiveScraperStatus
        live_status, created = LiveScraperStatus.objects.get_or_create(id=1)

        # Keep only last 2000 characters to prevent DB bloat
        if len(live_status.logs) > 2000:
            live_status.logs = live_status.logs[-2000:]
        live_status.logs += message + "\n"
        live_status.save()

        # Also update CombinedScraperStatus if it exists
        combined_status = CombinedScraperStatus.objects.first()
        if combined_status:
            if len(combined_status.live_matches_log) > 2000:
                combined_status.live_matches_log = combined_status.live_matches_log[-2000:]
            combined_status.live_matches_log += message + "\n"
            combined_status.save()

    except Exception as e:
        print(f"Error updating live scraper log in DB: {e}")


def update_combined_scraper_status(running=False):
    """Update the combined scraper status"""
    try:
        combined_status = CombinedScraperStatus.objects.first()
        if not combined_status:
            combined_status = CombinedScraperStatus.objects.create(
                is_running=running,
                last_run=timezone.now()
            )
        else:
            combined_status.is_running = running
            combined_status.last_run = timezone.now()
            combined_status.save()
    except Exception as e:
        print(f"Error updating combined scraper status: {e}")


# ============== Main Scraper Functions ==============
def start_scraping_task():
    """Start the main scraper task"""
    global scraper_running, scraper_thread, scraper_instance

    print("STARTING: Main scraper is starting up...")
    logger.info("STARTING: Main scraper is starting up...")

    # Update the database
    scraper_status = ScraperStatus.get_instance()
    scraper_status.is_running = True
    scraper_status.last_run = timezone.now()
    scraper_status.save()

    # Update combined status
    update_combined_scraper_status(running=True)

    # Write to log file
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] 🚀 STARTING: Main scraper is starting up..."
    write_to_log(log_message)
    update_main_scraper_log(log_message)

    # Start the scraping loop in a separate thread
    if not scraper_running:
        scraper_running = True
        scraper_thread = threading.Thread(target=run_scraper_async, daemon=True)
        scraper_thread.start()

    return "Main scraper started successfully"


def run_scraper_async():
    """Run the async scraper in a separate thread"""
    global scraper_running, scraper_instance

    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Create scraper instance
        scraper_instance = XStakeScraper()

        # Define status check callback
        async def status_check_callback():
            return scraper_running  # Check the global flag

        # Run the scraper
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] 🔄 RUNNING: Starting monitor_main_list_persistent..."
        write_to_log(log_message)
        update_main_scraper_log(log_message)

        loop.run_until_complete(
            scraper_instance.monitor_main_list_persistent(
                status_check_callback=status_check_callback,
                log_callback=async_log_callback
            )
        )

    except Exception as e:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        error_message = f"[{timestamp}] ❌ ERROR in main scraper thread: {e}"
        write_to_log(error_message)
        update_main_scraper_log(error_message)

        import traceback
        traceback_msg = f"[{timestamp}] Traceback: {traceback.format_exc()}"
        write_to_log(traceback_msg)
        update_main_scraper_log(traceback_msg[:500])  # Limit traceback in DB
    finally:
        if scraper_instance:
            loop.run_until_complete(scraper_instance.cleanup())

        # Update status in database
        scraper_status = ScraperStatus.get_instance()
        scraper_status.is_running = False
        scraper_status.save()

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        end_message = f"[{timestamp}] 🛑 Main scraper thread ended"
        write_to_log(end_message)
        update_main_scraper_log(end_message)

        # Update global flag
        scraper_running = False


def stop_scraping_task():
    """Stop the main scraping task"""
    global scraper_running, scraper_thread, scraper_instance

    print("STOPPING: Main scraper is stopping...")
    logger.info("STOPPING: Main scraper is stopping...")

    # Update the database
    scraper_status = ScraperStatus.get_instance()
    scraper_status.is_running = False
    scraper_status.save()

    # Write to log file
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] 🛑 STOPPING: Main scraper is stopping..."
    write_to_log(log_message)
    update_main_scraper_log(log_message)

    # Stop the scraper loop
    scraper_running = False

    # Wait for thread to finish (with timeout)
    if scraper_thread and scraper_thread.is_alive():
        scraper_thread.join(timeout=10)  # Wait up to 10 seconds

    # Force cleanup if needed
    if scraper_instance:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scraper_instance.cleanup())
        except Exception as e:
            print(f"Error during cleanup: {e}")

    return "Main scraper stopped successfully"


# ============== Live Scraper Functions ==============
def start_live_scraping_task():
    """Start the live matches scraper"""
    global live_scraper_running, live_scraper_thread

    print("STARTING: Live scraper is starting up...")

    # Check if already running
    if live_scraper_running:
        return "Live scraper is already running"

    # Update database status
    try:
        from .models import LiveScraperStatus
        live_status, created = LiveScraperStatus.objects.get_or_create(id=1)
        live_status.is_running = True
        live_status.last_run = timezone.now()
        live_status.save()
    except Exception as e:
        print(f"Error updating live scraper status: {e}")

    # Update combined status
    update_combined_scraper_status(running=True)

    # Write to log
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] 🚀 STARTING: Live Matches Scraper is starting up..."
    write_live_log(log_message)
    update_live_scraper_log(log_message)

    # Start the thread
    live_scraper_running = True
    live_scraper_thread = threading.Thread(target=run_live_scraper, daemon=True, name="LiveScraperThread")
    live_scraper_thread.start()

    return "Live scraper started successfully"


def run_live_scraper():
    """Run the live scraper in a separate thread"""
    global live_scraper_running, live_scraper_instance

    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Create scraper instance
        live_scraper_instance = XStakeScraper()

        # Define status check callback
        async def live_status_check_callback():
            return live_scraper_running

        # Run the live scraper
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] 🔥 RUNNING: Starting live matches monitoring..."
        write_live_log(log_message)
        update_live_scraper_log(log_message)

        loop.run_until_complete(
            live_scraper_instance.monitor_live_page_persistent(
                status_check_callback=live_status_check_callback,
                log_callback=async_live_log_callback
            )
        )

    except Exception as e:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        error_message = f"[{timestamp}] ❌ ERROR in live scraper: {e}"
        write_live_log(error_message)
        update_live_scraper_log(error_message)

        import traceback
        traceback_msg = f"[{timestamp}] Traceback: {traceback.format_exc()}"
        write_live_log(traceback_msg)
        update_live_scraper_log(traceback_msg[:500])  # Limit traceback in DB
    finally:
        # Cleanup
        if live_scraper_instance:
            try:
                loop.run_until_complete(live_scraper_instance.cleanup())
            except Exception as e:
                error_msg = f"Error during live scraper cleanup: {e}"
                write_live_log(error_msg)
                update_live_scraper_log(error_msg)

        # Update database status
        try:
            from .models import LiveScraperStatus
            live_status = LiveScraperStatus.objects.get(id=1)
            live_status.is_running = False
            live_status.save()
        except Exception as e:
            print(f"Error updating live scraper status on stop: {e}")

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        end_message = f"[{timestamp}] 🛑 Live scraper thread ended"
        write_live_log(end_message)
        update_live_scraper_log(end_message)

        # Update global flag
        live_scraper_running = False


def stop_live_scraping_task():
    """Stop the live matches scraper"""
    global live_scraper_running, live_scraper_thread, live_scraper_instance

    print("STOPPING: Live scraper is stopping...")

    if not live_scraper_running:
        return "Live scraper is already stopped"

    # Update database status
    try:
        from .models import LiveScraperStatus
        live_status = LiveScraperStatus.objects.get(id=1)
        live_status.is_running = False
        live_status.save()
    except Exception as e:
        print(f"Error updating live scraper status on stop: {e}")

    # Write to log
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] 🛑 STOPPING: Live Matches Scraper is stopping..."
    write_live_log(log_message)
    update_live_scraper_log(log_message)

    # Stop the scraper
    live_scraper_running = False

    # Wait for thread to finish
    if live_scraper_thread and live_scraper_thread.is_alive():
        live_scraper_thread.join(timeout=10)

    # Force cleanup if needed
    if live_scraper_instance:
        try:
            temp_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(temp_loop)
            temp_loop.run_until_complete(live_scraper_instance.cleanup())
        except Exception as e:
            error_msg = f"Error during live scraper forced cleanup: {e}"
            write_live_log(error_msg)
            update_live_scraper_log(error_msg)

    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    end_message = f"[{timestamp}] ✅ Live scraper stopped completely"
    write_live_log(end_message)
    update_live_scraper_log(end_message)

    return "Live scraper stopped successfully"


# ============== Combined Functions ==============
def cleanup_scraper():
    """Force cleanup of all scraper resources"""
    global scraper_running, scraper_thread, scraper_instance
    global live_scraper_running, live_scraper_thread, live_scraper_instance

    # Stop main scraper
    scraper_running = False
    if scraper_thread and scraper_thread.is_alive():
        scraper_thread.join(timeout=5)

    # Stop live scraper
    live_scraper_running = False
    if live_scraper_thread and live_scraper_thread.is_alive():
        live_scraper_thread.join(timeout=5)

    # Update statuses in database
    scraper_status = ScraperStatus.get_instance()
    scraper_status.is_running = False
    scraper_status.save()

    try:
        from .models import LiveScraperStatus
        live_status = LiveScraperStatus.objects.get(id=1)
        live_status.is_running = False
        live_status.save()
    except:
        pass

    # Update combined status
    update_combined_scraper_status(running=False)

    # Force cleanup of instances
    if scraper_instance:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scraper_instance.cleanup())
            scraper_instance = None
        except:
            pass

    if live_scraper_instance:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(live_scraper_instance.cleanup())
            live_scraper_instance = None
        except:
            pass

    timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    write_to_log(f"[{timestamp}] 🧹 Cleanup completed for all scrapers")
    write_live_log(f"[{timestamp}] 🧹 Cleanup completed for all scrapers")