"""
Run this ONCE to create the marketplace's single escrow wallet key.

    python init_wallet.py --network testnet

Copy the printed key into your .env file as ESCROW_XPRV. Then also write
it down somewhere offline (paper, password manager, hardware backup) --
if your .env / database is ever lost and you have no other copy of this
key, every coin sitting in escrow becomes permanently unrecoverable.

Do NOT run this more than once for the same live marketplace. Every time
you run it you get a brand new, unrelated wallet -- running it again
after you're already using one in production would orphan any escrowed
funds under the old key.
"""

import argparse
from bitcoinlib.keys import HDKey


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", default="testnet", choices=["testnet", "bitcoin"])
    args = parser.parse_args()

    key = HDKey(network=args.network, witness_type="segwit")

    print("=" * 70)
    print("MARKETPLACE ESCROW WALLET -- GENERATED ONCE")
    print("=" * 70)
    print()
    print(f"Network: {args.network}")
    print()
    print("Put this in your .env file:")
    print(f"ESCROW_XPRV={key.wif_private()}")
    print(f"BTC_NETWORK={args.network}")
    print()
    print("Back this key up offline too. Anyone who obtains it can move")
    print("every coin ever escrowed by the marketplace.")
    print("=" * 70)


if __name__ == "__main__":
    main()
