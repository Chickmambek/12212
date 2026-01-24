#!/usr/bin/env python3
"""
BIP-39 Seed Phrase Generator, Validator, and Balance Checker
This script generates BIP-39 seed phrases, validates them, and checks for wallet balances
"""

import hashlib
import hmac
import requests
import time
from typing import List, Tuple, Optional
import unicodedata

class BIP39Generator:
    def __init__(self):
        print("Initializing BIP-39 Generator...")
        self.wordlist = self.load_wordlist()
        print(f"✓ Loaded {len(self.wordlist)} words from BIP-39 wordlist")

    def load_wordlist(self) -> List[str]:
        """Load the BIP-39 English wordlist from GitHub"""
        print("Loading BIP-39 wordlist from GitHub...")
        url = "https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            words = response.text.strip().split('\n')
            print(f"Successfully loaded {len(words)} words")
            return words
        except Exception as e:
            print(f"Error loading wordlist: {e}")
            print("Using fallback local wordlist...")
            # Fallback to a minimal wordlist if GitHub fails
            return [
                "abandon", "ability", "able", "about", "above", "absent", "absorb", "abstract",
                "absurd", "abuse", "access", "accident", "account", "accuse", "achieve", "acid"
            ]

    def generate_entropy(self, bits: int = 128) -> bytes:
        """Generate cryptographically secure entropy"""
        print(f"\nGenerating {bits} bits of entropy...")
        import secrets
        entropy = secrets.token_bytes(bits // 8)
        print(f"Entropy bytes: {entropy.hex()}")
        return entropy

    def calculate_checksum(self, entropy: bytes) -> int:
        """Calculate checksum for BIP-39"""
        print("Calculating checksum...")
        # Calculate SHA256 hash of entropy
        hash_bytes = hashlib.sha256(entropy).digest()
        print(f"SHA256 hash: {hash_bytes.hex()}")

        # Number of checksum bits = entropy length / 32
        checksum_length = len(entropy) * 8 // 32
        print(f"Checksum length: {checksum_length} bits")

        # Get first checksum_length bits from hash
        hash_int = int.from_bytes(hash_bytes, 'big')
        checksum = hash_int >> (256 - checksum_length)
        print(f"Checksum (binary): {checksum:0{checksum_length}b}")

        return checksum

    def entropy_to_mnemonic(self, entropy: bytes) -> List[str]:
        """Convert entropy to BIP-39 mnemonic words"""
        print("\nConverting entropy to mnemonic...")

        # Calculate checksum
        checksum = self.calculate_checksum(entropy)

        # Combine entropy and checksum
        entropy_bits = int.from_bytes(entropy, 'big')
        entropy_bits <<= len(entropy) * 8 // 32  # Shift left to make room for checksum
        combined_bits = entropy_bits | checksum

        # Number of bits in combined value
        total_bits = len(entropy) * 8 + len(entropy) * 8 // 32
        print(f"Total bits (entropy + checksum): {total_bits}")

        # Split into 11-bit chunks
        words = []
        mask = (1 << 11) - 1

        for i in range(total_bits // 11):
            index = (combined_bits >> (total_bits - (i + 1) * 11)) & mask
            words.append(self.wordlist[index])

        print(f"Generated {len(words)}-word mnemonic")
        return words

    def generate_mnemonic(self, word_count: int = 12) -> List[str]:
        """Generate a complete BIP-39 mnemonic"""
        print(f"\n{'='*50}")
        print(f"Generating {word_count}-word mnemonic...")

        # Map word count to entropy bits
        bits_map = {
            12: 128,  # 128 bits entropy + 4 bits checksum
            15: 160,  # 160 bits entropy + 5 bits checksum
            18: 192,  # 192 bits entropy + 6 bits checksum
            21: 224,  # 224 bits entropy + 7 bits checksum
            24: 256   # 256 bits entropy + 8 bits checksum
        }

        if word_count not in bits_map:
            print(f"Invalid word count: {word_count}. Using 12 words.")
            word_count = 12

        entropy_bits = bits_map[word_count]
        entropy = self.generate_entropy(entropy_bits)
        mnemonic = self.entropy_to_mnemonic(entropy)

        print(f"\nGenerated mnemonic: {' '.join(mnemonic)}")
        print(f"Mnemonic length: {len(mnemonic)} words")
        return mnemonic

    def normalize_string(self, text: str) -> str:
        """Normalize string to NFKD format as per BIP-39"""
        return unicodedata.normalize('NFKD', text)

    def mnemonic_to_seed(self, mnemonic: List[str], passphrase: str = "") -> bytes:
        """Convert mnemonic to seed using PBKDF2"""
        print(f"\nConverting mnemonic to seed...")
        print(f"Passphrase: '{passphrase}'")

        # Normalize inputs
        mnemonic_normalized = self.normalize_string(' '.join(mnemonic)).encode('utf-8')
        passphrase_normalized = self.normalize_string('mnemonic' + passphrase).encode('utf-8')

        print(f"Using PBKDF2 with HMAC-SHA512, 2048 iterations...")
        seed = hashlib.pbkdf2_hmac(
            'sha512',
            mnemonic_normalized,
            passphrase_normalized,
            2048
        )

        print(f"Seed generated: {seed[:16].hex()}... (first 16 bytes)")
        return seed

    def validate_mnemonic(self, mnemonic: List[str]) -> bool:
        """Validate if a mnemonic is valid according to BIP-39"""
        print(f"\nValidating mnemonic...")

        # Check if all words are in the wordlist
        for i, word in enumerate(mnemonic):
            if word not in self.wordlist:
                print(f"✗ Word '{word}' at position {i+1} not in wordlist")
                return False

        print("✓ All words are in the BIP-39 wordlist")

        # Convert mnemonic back to entropy
        word_count = len(mnemonic)
        bits_map = {
            12: 128, 15: 160, 18: 192, 21: 224, 24: 256
        }

        if word_count not in bits_map:
            print(f"✗ Invalid word count: {word_count}")
            return False

        entropy_bits = bits_map[word_count]

        # Convert words to indices
        indices = [self.wordlist.index(word) for word in mnemonic]
        print(f"Word indices: {indices}")

        # Reconstruct combined bits
        combined_bits = 0
        for index in indices:
            combined_bits = (combined_bits << 11) | index

        # Split into entropy and checksum
        checksum_length = word_count * 11 - entropy_bits
        entropy_int = combined_bits >> checksum_length
        checksum = combined_bits & ((1 << checksum_length) - 1)

        print(f"Reconstructed entropy bits: {entropy_int:0{entropy_bits}b}")
        print(f"Reconstructed checksum: {checksum:0{checksum_length}b}")

        # Calculate expected checksum
        entropy_bytes = entropy_int.to_bytes(entropy_bits // 8, 'big')
        expected_checksum = self.calculate_checksum(entropy_bytes)

        print(f"Expected checksum: {expected_checksum:0{checksum_length}b}")

        if checksum == expected_checksum:
            print("✓ Mnemonic checksum is valid!")
            return True
        else:
            print("✗ Mnemonic checksum is invalid")
            return False

class BlockchainChecker:
    def __init__(self):
        print("\nInitializing Blockchain Checker...")

    def check_address_balance(self, address: str, cryptocurrency: str = "bitcoin") -> dict:
        """Check balance for a cryptocurrency address"""
        print(f"\nChecking balance for {cryptocurrency.upper()} address: {address}")

        apis = {
            "bitcoin": [
                f"https://blockchain.info/rawaddr/{address}",
                f"https://api.blockcypher.com/v1/btc/main/addrs/{address}/balance"
            ],
            "ethereum": [
                f"https://api.etherscan.io/api?module=account&action=balance&address={address}",
                f"https://api.blockcypher.com/v1/eth/main/addrs/{address}/balance"
            ],
            "litecoin": [
                f"https://api.blockcypher.com/v1/ltc/main/addrs/{address}/balance"
            ]
        }

        if cryptocurrency not in apis:
            print(f"Unsupported cryptocurrency: {cryptocurrency}")
            return {"error": "Unsupported cryptocurrency"}

        for api_url in apis[cryptocurrency]:
            try:
                print(f"Trying API: {api_url}")
                response = requests.get(api_url, timeout=10)

                if response.status_code == 200:
                    data = response.json()

                    if "blockchain.info" in api_url:
                        balance_satoshi = data.get("final_balance", 0)
                        balance_btc = balance_satoshi / 100000000
                        return {
                            "balance_satoshi": balance_satoshi,
                            "balance": balance_btc,
                            "unit": "BTC",
                            "tx_count": data.get("n_tx", 0)
                        }
                    elif "etherscan.io" in api_url:
                        if data.get("status") == "1":
                            balance_wei = int(data.get("result", 0))
                            balance_eth = balance_wei / 10**18
                            return {
                                "balance_wei": balance_wei,
                                "balance": balance_eth,
                                "unit": "ETH",
                                "source": "etherscan"
                            }
                    elif "blockcypher.com" in api_url:
                        balance_satoshi = data.get("balance", 0)
                        if cryptocurrency == "bitcoin":
                            balance_btc = balance_satoshi / 10**8
                            return {
                                "balance_satoshi": balance_satoshi,
                                "balance": balance_btc,
                                "unit": "BTC",
                                "source": "blockcypher"
                            }
                        elif cryptocurrency == "ethereum":
                            balance_eth = balance_satoshi / 10**18
                            return {
                                "balance_wei": balance_satoshi,
                                "balance": balance_eth,
                                "unit": "ETH",
                                "source": "blockcypher"
                            }

            except Exception as e:
                print(f"API error: {e}")
                continue

        print("All API calls failed")
        return {"error": "Failed to fetch balance"}

def main():
    print("="*60)
    print("BIP-39 SEED PHRASE GENERATOR & VALIDATOR")
    print("="*60)

    # Initialize generator
    generator = BIP39Generator()

    # Generate multiple mnemonics
    num_mnemonics = 3
    print(f"\nGenerating {num_mnemonics} seed phrases...")

    all_mnemonics = []
    for i in range(num_mnemonics):
        print(f"\n{'='*50}")
        print(f"SEED PHRASE #{i+1}")
        print('='*50)

        # Generate mnemonic
        mnemonic = generator.generate_mnemonic(12)

        # Validate the generated mnemonic
        print(f"\nValidating seed phrase #{i+1}...")
        is_valid = generator.validate_mnemonic(mnemonic)

        if is_valid:
            print(f"✓ Seed phrase #{i+1} is VALID")

            # Convert to seed (for demonstration)
            seed = generator.mnemonic_to_seed(mnemonic, "")

            # Store valid mnemonic
            all_mnemonics.append({
                'mnemonic': mnemonic,
                'seed': seed[:16].hex(),  # Store first 16 bytes only for display
                'valid': True
            })
        else:
            print(f"✗ Seed phrase #{i+1} is INVALID")
            all_mnemonics.append({
                'mnemonic': mnemonic,
                'valid': False
            })

        # Add delay to avoid rate limiting
        if i < num_mnemonics - 1:
            print("\nWaiting 1 second before next generation...")
            time.sleep(1)

    # Display summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for i, mnemonic_data in enumerate(all_mnemonics):
        print(f"\nSeed phrase #{i+1}:")
        print(f"  Words: {' '.join(mnemonic_data['mnemonic'])}")
        print(f"  Status: {'VALID' if mnemonic_data['valid'] else 'INVALID'}")
        if mnemonic_data.get('seed'):
            print(f"  Seed (first 16 bytes): {mnemonic_data['seed']}...")

    # Note about blockchain checking
    print("\n" + "="*60)
    print("BLOCKCHAIN CHECKING NOTE")
    print("="*60)
    print("""
    To actually check balances, you would need to:
    1. Convert the seed to a master private key
    2. Derive HD wallet addresses (BIP-32/BIP-44)
    3. Check those addresses on blockchain explorers

    However, note:
    - Checking random seed phrases for balances is extremely unlikely to yield results
    - The probability of finding a seed phrase with funds is astronomically small
    - This script demonstrates the process but won't find any funds

    For educational purposes only!
    """)

    # Optional: Check a specific address (for demonstration)
    print("\n" + "="*60)
    print("DEMONSTRATION: CHECKING SAMPLE ADDRESS")
    print("="*60)

    checker = BlockchainChecker()

    # Check some sample addresses
    sample_addresses = [
        ("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "bitcoin"),  # Bitcoin genesis address
        ("0x742d35Cc6634C0532925a3b844Bc9eE43a419026", "ethereum")  # Sample ETH address
    ]

    for address, crypto in sample_addresses:
        balance_info = checker.check_address_balance(address, crypto)
        print(f"\n{crypto.upper()} Address: {address}")

        if 'error' in balance_info:
            print(f"  Error: {balance_info['error']}")
        else:
            print(f"  Balance: {balance_info['balance']} {balance_info['unit']}")
            if 'tx_count' in balance_info:
                print(f"  Transaction Count: {balance_info['tx_count']}")

    print("\n" + "="*60)
    print("SCRIPT COMPLETE")
    print("="*60)
    print("\nRemember: Never share your seed phrases with anyone!")
    print("Store them securely and never enter them into untrusted software.")

if __name__ == "__main__":
    # Install required packages if not present
    try:
        import requests
    except ImportError:
        print("Installing required packages...")
        import subprocess
        subprocess.check_call(["pip", "install", "requests"])
        import requests

    main()