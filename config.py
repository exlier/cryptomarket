import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
    # If DATABASE_URL isn't set, app.py points this at an absolute path
    # inside the Flask instance folder once the app is created.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Bitcoin network: "testnet" (free, fake coins, use this while building)
    # or "bitcoin" (mainnet, real money -- only switch once you've tested
    # the ENTIRE order lifecycle on testnet: pay in, escrow, release, and
    # a dispute/refund).
    BTC_NETWORK = os.environ.get("BTC_NETWORK", "testnet")

    # The marketplace's ONE escrow wallet, as an extended PRIVATE key
    # (tprv on testnet / xprv on mainnet). This wallet holds every buyer's
    # payment until it's released to a seller or refunded, so:
    #   - it must only ever live in your .env file (which must be in
    #     .gitignore) or your host's secret manager, never in source code
    #   - back up the seed/xprv somewhere safe and offline -- if it's
    #     lost, every escrowed coin is gone with it
    #   - generate it once with init_wallet.py, then never regenerate it
    #     (regenerating = losing access to every address already in use)
    ESCROW_XPRV = os.environ.get("ESCROW_XPRV", "")

    WALLET_NAME = os.environ.get("WALLET_NAME", "marketplace_escrow")

    # Percentage the marketplace keeps from every completed order.
    # Taken automatically as the "change" left over when funds are
    # forwarded to the seller -- see wallet.py release_to_seller().
    COMMISSION_PERCENT = float(os.environ.get("COMMISSION_PERCENT", "2.5"))

    # Confirmations required before a payment counts as "escrowed" rather
    # than still-reversible. Keep at 1+ always; use 2-3 on mainnet for
    # larger amounts.
    REQUIRED_CONFIRMATIONS = int(os.environ.get("REQUIRED_CONFIRMATIONS", "1"))
