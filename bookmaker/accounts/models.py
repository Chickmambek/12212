from django.db import models
from django.contrib.auth.models import User
import pycountry
from django.conf import settings


class Profile(models.Model):
    # Get all countries
    COUNTRIES = [(country.alpha_2, country.name) for country in pycountry.countries]

    # Get all currencies
    CURRENCIES = [
        (currency.alpha_3, f"{currency.alpha_3} - {currency.name}") for currency in pycountry.currencies
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=200)
    country = models.CharField(max_length=2, choices=COUNTRIES)
    currency = models.CharField(max_length=3, choices=CURRENCIES)
    promo_code = models.CharField(max_length=100, blank=True, null=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return self.user.username

    def add_balance(self, amount):
        if amount > 0:
            self.balance += amount
            self.save()


User = settings.AUTH_USER_MODEL


class Wallet(models.Model):
    """
    Store site-controlled deposit addresses (public addresses only).
    One row per currency (BTC, ETH, USDT, ...).
    """
    CURRENCY_CHOICES = [
        ('BTC', 'Bitcoin'),
        ('ETH', 'Ethereum'),
        ('USDT', 'Tether (ERC20/TRC20)'),
        ('LTC', 'Litecoin'),
    ]

    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, unique=True)
    address = models.CharField(max_length=255)
    label = models.CharField(max_length=100, blank=True, help_text="Optional note (eg. Hot wallet)")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.currency} — {self.address}"


class WalletIndex(models.Model):
    """
    Tracks the last used HD wallet index for each cryptocurrency to prevent address reuse
    and race conditions.
    """
    currency = models.CharField(max_length=10, unique=True)
    last_index = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.currency} - Index: {self.last_index}"


class CryptoTransaction(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_UNDERPAID = 'underpaid'
    STATUS_OVERPAID = 'overpaid'
    STATUS_CANCELED = 'canceled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_UNDERPAID, 'Underpaid'),
        (STATUS_OVERPAID, 'Overpaid'),
        (STATUS_CANCELED, 'Canceled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    crypto_type = models.CharField(max_length=10)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    deposit_address = models.CharField(max_length=255)
    qr_path = models.CharField(max_length=500, blank=True, null=True)
    tx_hash = models.CharField(max_length=255, blank=True, null=True)
    confirmations = models.IntegerField(default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    # =================================================================
    # ✅ CHANGE: Added field to store the HD wallet address index
    # This prevents address reuse.
    # =================================================================
    address_index = models.PositiveIntegerField(null=True, blank=True, db_index=True)
