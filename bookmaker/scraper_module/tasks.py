# tasks.py
import time
import threading
import logging
import asyncio
import os
from django.utils import timezone
from .models import ScraperStatus
from scraper_module.scraper import XStakeScraper  # Import your scraper class

# Get logger
logger = logging.getLogger(__name__)

# Global flag to control the scraper
scraper_running = False
scraper_thread = None
scraper_instance = None  # Store the scraper instance


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


def log_callback_to_file(msg):
    """Callback function to write scraper logs to file"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    write_to_log(f"[{timestamp}] {msg}")
    print(msg)  # Also print to console


async def async_log_callback(msg):
    """Async version of log callback for the scraper"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] {msg}"
    # Run sync log function in thread
    await asyncio.to_thread(log_callback_to_file, log_message)


def start_scraping_task():
    """Start the actual scraper task"""
    global scraper_running, scraper_thread, scraper_instance

    print("STARTING: Scraper is starting up...")
    logger.info("STARTING: Scraper is starting up...")

    # Update the model
    scraper_status = ScraperStatus.get_instance()
    scraper_status.is_running = True
    scraper_status.save()

    # Write to log file with proper encoding
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    write_to_log(f"[{timestamp}] 🚀 STARTING: Scraper is starting up...")

    # Start the scraping loop in a separate thread
    if not scraper_running:
        scraper_running = True
        scraper_thread = threading.Thread(target=run_scraper_async, daemon=True)
        scraper_thread.start()

    return "Scraper started successfully"


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
        write_to_log(f"[{timestamp}] 🔄 RUNNING: Starting monitor_main_list_persistent...")

        loop.run_until_complete(
            scraper_instance.monitor_main_list_persistent(
                status_check_callback=status_check_callback,
                log_callback=async_log_callback
            )
        )

    except Exception as e:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        write_to_log(f"[{timestamp}] ❌ ERROR in scraper thread: {e}")
        import traceback
        write_to_log(f"[{timestamp}] Traceback: {traceback.format_exc()}")
    finally:
        if scraper_instance:
            loop.run_until_complete(scraper_instance.cleanup())
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        write_to_log(f"[{timestamp}] 🛑 Scraper thread ended")


def stop_scraping_task():
    """Stop the scraping task"""
    global scraper_running, scraper_thread, scraper_instance

    print("STOPPING: Scraper is stopping...")
    logger.info("STOPPING: Scraper is stopping...")

    # Update the model
    scraper_status = ScraperStatus.get_instance()
    scraper_status.is_running = False
    scraper_status.save()

    # Write to log file with proper encoding
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    write_to_log(f"[{timestamp}] 🛑 STOPPING: Scraper is stopping...")

    # Stop the scraper loop
    scraper_running = False

    # Wait for thread to finish (with timeout)
    if scraper_thread and scraper_thread.is_alive():
        scraper_thread.join(timeout=10)  # Wait up to 10 seconds

    # Force cleanup if needed
    if scraper_instance:
        try:
            import asyncio as async_module
            loop = async_module.new_event_loop()
            async_module.set_event_loop(loop)
            loop.run_until_complete(scraper_instance.cleanup())
        except:
            pass

    return "Scraper stopped successfully"


# tasks.py - add cleanup function
def cleanup_scraper():
    """Force cleanup of scraper resources"""
    global scraper_running, scraper_thread, scraper_instance

    scraper_running = False

    # Update status
    status = ScraperStatus.get_instance()
    status.is_running = False
    status.save()

    # Force cleanup if scraper instance exists
    if scraper_instance:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scraper_instance.cleanup())
            scraper_instance = None
        except:
            pass

    write_to_log(f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S')}] 🧹 Cleanup completed")


# Live scraper globals
live_scraper_running = False
live_scraper_thread = None
live_scraper_instance = None


def write_live_log(message):
    """Write to live scraper log"""
    try:
        with open('live_scraper.log', 'a', encoding='utf-8') as f:
            f.write(message + '\n')
    except Exception as e:
        with open('live_scraper.log', 'a', encoding='latin-1') as f:
            f.write(message.encode('ascii', 'ignore').decode('ascii') + '\n')


def start_live_scraping_task():
    """Start the live matches scraper"""
    global live_scraper_running, live_scraper_thread

    print("STARTING: Live scraper is starting up...")
    write_live_log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 STARTING: Live Matches Scraper is starting up...")

    # Update the model if you have one for live scraper
    # For now, just set the global flag

    if live_scraper_running:
        return "Live scraper is already running"

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

        # Define log callback
        async def live_log_callback(msg):
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            log_message = f"[{timestamp}] {msg}"
            await asyncio.to_thread(write_live_log, log_message)

        # Define status check callback
        async def live_status_check_callback():
            return live_scraper_running

        # Run the live scraper
        write_live_log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🔥 RUNNING: Starting live matches monitoring...")

        loop.run_until_complete(
            live_scraper_instance.monitor_live_page_persistent(
                status_check_callback=live_status_check_callback,
                log_callback=live_log_callback
            )
        )

    except Exception as e:
        write_live_log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ ERROR in live scraper: {e}")
        import traceback
        write_live_log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Traceback: {traceback.format_exc()}")
    finally:
        # Cleanup
        if live_scraper_instance:
            try:
                loop.run_until_complete(live_scraper_instance.cleanup())
            except:
                pass

        write_live_log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🛑 Live scraper thread ended")
        live_scraper_running = False


def stop_live_scraping_task():
    """Stop the live matches scraper"""
    global live_scraper_running, live_scraper_thread, live_scraper_instance

    print("STOPPING: Live scraper is stopping...")
    write_live_log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🛑 STOPPING: Live Matches Scraper is stopping...")

    if not live_scraper_running:
        return "Live scraper is already stopped"

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
        except:
            pass

    write_live_log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ Live scraper stopped completely")

    return "Live scraper stopped successfully"