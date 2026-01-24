from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes, Bip39Languages

mnemonic = "witch collapse practice feed shame open despair creek road again ice least"
seed_bytes = Bip39SeedGenerator(mnemonic, Bip39Languages.ENGLISH).Generate()

print("Testing BTC...")
try:
    bip44_mst_key = Bip44.FromSeed(seed_bytes, Bip44Coins.BITCOIN)
    print("Success BTC FromSeed")
    bip44_addr_key = bip44_mst_key.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    print(f"Address: {bip44_addr_key.PublicKey().ToAddress()}")
except Exception as e:
    print(f"Error BTC: {e}")

print("\nTesting ETH...")
try:
    bip44_mst_key = Bip44.FromSeed(seed_bytes, Bip44Coins.ETHEREUM)
    print("Success ETH FromSeed")
    bip44_addr_key = bip44_mst_key.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    print(f"Address: {bip44_addr_key.PublicKey().ToAddress()}")
except Exception as e:
    print(f"Error ETH: {e}")
