from django.contrib import admin, messages
from .models import Wallet, CryptoTransaction, WalletIndex
from django.utils import timezone
from django.db import transaction


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('currency', 'address', 'label', 'created_at')
    search_fields = ('currency', 'address', 'label')


@admin.register(WalletIndex)
class WalletIndexAdmin(admin.ModelAdmin):
    list_display = ('currency', 'last_index')
    readonly_fields = ('currency', 'last_index')

    def has_add_permission(self, request):
        return False  # Prevent manual creation to avoid messing up the sequence


@admin.register(CryptoTransaction)
class CryptoTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'crypto_type', 'amount', 'deposit_address',
        'status', 'confirmations', 'tx_hash', 'created_at'
    )
    list_filter = ('status', 'crypto_type', 'created_at')
    search_fields = ('user__username', 'deposit_address', 'crypto_type')

    actions = ['approve_transactions', 'reject_transactions']

    def approve_transactions(self, request, queryset):
        pending = queryset.filter(status=CryptoTransaction.STATUS_PENDING)
        approved_count = 0

        for tx in pending:
            tx.status = CryptoTransaction.STATUS_CONFIRMED
            tx.user.profile.balance += tx.amount
            tx.user.profile.save()
            tx.save()
            approved_count += 1

        self.message_user(request, f"Approved {approved_count} deposits.")

    approve_transactions.short_description = "Force Approve (manual credit)"

    def reject_transactions(self, request, queryset):
        updated = queryset.filter(status=CryptoTransaction.STATUS_PENDING).update(
            status=CryptoTransaction.STATUS_UNDERPAID
        )
        self.message_user(request, f"Rejected {updated} transactions.")

    reject_transactions.short_description = "Mark as rejected / underpaid"
