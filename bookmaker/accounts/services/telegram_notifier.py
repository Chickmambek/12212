import requests
import logging
from django.conf import settings
import threading
import socket

logger = logging.getLogger('accounts')

def send_telegram_message(message):
    """
    Sends a message to the configured Telegram chat.
    Runs in a separate thread to avoid blocking the main request.
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.warning("Telegram bot token or chat ID not configured.")
        return

    def _send():
        try:
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=5)
            if response.status_code != 200:
                logger.error(f"Failed to send Telegram message: {response.text}")
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")

    threading.Thread(target=_send).start()

def notify_new_user(user, profile):
    msg = (
        f"<b>👤 New User Registered</b>\n\n"
        f"<b>Username:</b> {user.username}\n"
        f"<b>Email:</b> {user.email}\n"
        f"<b>Name:</b> {profile.full_name}\n"
        f"<b>Country:</b> {profile.country}\n"
        f"<b>Currency:</b> {profile.currency}\n"
        f"<b>Promo:</b> {profile.promo_code or 'None'}"
    )
    send_telegram_message(msg)

def notify_deposit_request(tx):
    msg = (
        f"<b>💸 New Deposit Request</b>\n\n"
        f"<b>User:</b> {tx.user.username}\n"
        f"<b>Amount:</b> {tx.amount} {tx.crypto_type}\n"
        f"<b>Address:</b> <code>{tx.deposit_address}</code>\n"
        f"<b>ID:</b> #{tx.id}"
    )
    send_telegram_message(msg)

def notify_deposit_confirmed(tx):
    msg = (
        f"<b>✅ Deposit Confirmed</b>\n\n"
        f"<b>User:</b> {tx.user.username}\n"
        f"<b>Amount:</b> {tx.amount} {tx.crypto_type}\n"
        f"<b>New Balance:</b> {tx.user.profile.balance} {tx.user.profile.currency}\n"
        f"<b>ID:</b> #{tx.id}"
    )
    send_telegram_message(msg)

def notify_site_visit(request):
    """
    Notifies Telegram when a user visits the site.
    Includes IP address and User Agent.
    """
    try:
        # Get IP Address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')

        # Get User Agent
        user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
        
        # Get User info if logged in
        user_info = "Guest"
        if request.user.is_authenticated:
            user_info = f"{request.user.username} (ID: {request.user.id})"

        # Get Location (basic geo-ip lookup could be added here, but keeping it simple for now)
        # For now, just IP and UA
        
        msg = (
            f"<b>👀 New Site Visit</b>\n\n"
            f"<b>User:</b> {user_info}\n"
            f"<b>IP:</b> {ip}\n"
            f"<b>Path:</b> {request.path}\n"
            f"<b>User Agent:</b> {user_agent[:100]}..." # Truncate UA to avoid huge messages
        )
        send_telegram_message(msg)
        
    except Exception as e:
        logger.error(f"Error notifying site visit: {e}")
