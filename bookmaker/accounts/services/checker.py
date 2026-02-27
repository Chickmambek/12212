import requests
from decimal import Decimal
from accounts.models import CryptoTransaction
from django.utils import timezone

ETHERSCAN_API_KEY = "MF8ISXZNE6W2HI4EB7N2JGUFHV5JVE9RVR"

API = {
    "BTC": "https://blockchain.info/rawaddr/",
    "ETH": "https://api.etherscan.io/v2/api?chainid=1&action=balance&apikey=" + ETHERSCAN_API_KEY + "&address=",
    "USDT": (
        "https://api.etherscan.io/v2/api?chainid=1&action=tokenbalance"
        f"&contractaddress=0xdAC17F958D2ee523a2206206994597C13D831ec7"
        f"&apikey={ETHERSCAN_API_KEY}&address="
    ),
    "LTC": "https://chain.so/api/v2/get_address_balance/LTC/"
}


def check_deposits():
    """
    Returns a list of changes detected in pending transactions.
    Each item is a string message for logging.
    """
    pending = CryptoTransaction.objects.filter(status="pending")
    changes = []

    for tx in pending:
        crypto = tx.crypto_type
        addr = tx.deposit_address
        expected = Decimal(tx.amount)

        try:
            if crypto == "BTC":
                data = requests.get(API["BTC"] + addr).json()
                received = Decimal(data["final_balance"]) / Decimal(1e8)
            elif crypto == "ETH":
                url = API["ETH"] + addr
                data = requests.get(url).json()
                received = Decimal(data["result"]) / Decimal(1e18)
            elif crypto == "USDT":
                url = API["USDT"] + addr
                data = requests.get(url).json()
                received = Decimal(data["result"]) / Decimal(1e6)
            elif crypto == "LTC":
                data = requests.get(API["LTC"] + addr).json()
                received = Decimal(data["data"]["confirmed_balance"])
            else:
                continue

            # Check payment logic
            msg = None
            if received == expected:
                tx.status = "confirmed"
                tx.user.profile.balance += expected
                tx.user.profile.save()
                tx.save()
                msg = f"✔ [{timezone.now()}] Deposit Confirmed → {tx.user} | Crypto={crypto} | Amount={expected} | New Balance={tx.user.profile.balance}"
            elif received < expected and received > 0:
                tx.status = "underpaid"
                tx.confirmations = 1
                tx.save()
                msg = f"⚠ [{timezone.now()}] Underpaid Deposit → {tx.user} | Crypto={crypto} | Received={received} / Expected={expected}"
            elif received > expected:
                tx.status = "overpaid"
                tx.confirmations = 1
                tx.user.profile.balance += received
                tx.user.profile.save()
                tx.save()
                msg = f"💰 [{timezone.now()}] Overpayment Detected → {tx.user} | Crypto={crypto} | Received={received} | New Balance={tx.user.profile.balance}"

            if msg:
                changes.append(msg)

        except Exception as e:
            changes.append(f"❌ [{timezone.now()}] Error checking tx_id={tx.id} | User={tx.user} | Crypto={crypto} | Error: {e}")

    return changes
