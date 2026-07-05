# Fernway Market -- Bitcoin escrow marketplace (Flask)

A working prototype of a marketplace where buyers and sellers connect,
buyers pay in bitcoin, and the marketplace holds funds in escrow until
the buyer confirms the goods arrived -- then the marketplace forwards
payment to the seller, automatically keeping a commission. No signup
cost, no paid services: SQLite, bitcoinlib, and free public block
explorer APIs.

## How the money actually moves

1. Buyer clicks "buy" and gets a **unique bitcoin address for that
   order only**, plus a QR code and the exact amount to send.
2. Buyer sends BTC to it **themselves**, from their own wallet app --
   nothing is ever pulled automatically, and there's no browser
   extension involved.
3. The app watches that address (via a free public block explorer API)
   and marks the order "escrowed" once payment arrives with enough
   confirmations.
4. When the buyer confirms delivery (currently: an admin clicks
   "release" -- see Limitations), the app signs and broadcasts a
   payout transaction straight from that order's escrowed coins to the
   seller's address.
5. The marketplace's cut is simply the **change** left over on that
   payout transaction -- it lands back in the marketplace wallet
   automatically. No separate step, no float required.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Generate the marketplace's ONE escrow wallet key (do this once, ever)
python init_wallet.py --network testnet

# Copy the printed ESCROW_XPRV into a real .env file
cp .env.example .env
# then edit .env and paste in the key

python app.py
# visit http://localhost:5000
```

Get free testnet coins from a faucet (search "bitcoin testnet faucet")
to actually test a payment going through before you ever touch mainnet
or real money.

## Files

| File | Purpose |
|---|---|
| `app.py` | Routes: browse, checkout, order status, admin actions |
| `wallet.py` | The escrow wallet: address generation, payment checks, payouts |
| `models.py` | `Product` and `Order` database tables |
| `config.py` | Settings, loaded from `.env` |
| `init_wallet.py` | One-time script to generate the escrow wallet key |
| `templates/`, `static/` | UI |

## Security model -- read this before using real money

- **The private key in `.env` controls every coin ever escrowed.**
  Anyone who obtains it can drain the wallet. Keep `.env` out of git
  (already in `.gitignore`), don't paste it into chat tools or
  screenshots, and back it up offline somewhere separate from your
  server.
- **This demo's `/admin` routes have no login.** Right now anyone who
  finds the URL can release or refund any order. Add real
  authentication (e.g. `Flask-Login` with a proper password hash, or
  put the whole `/admin` path behind your hosting provider's access
  control) before this goes anywhere public.
- **Start on testnet.** `BTC_NETWORK=testnet` uses coins with no real
  value. Run through a full order -- pay in, escrow, release, and a
  refund -- before ever switching to `bitcoin` (mainnet).
- **Bitcoin transactions are irreversible.** There's no chargeback. The
  whole point of the escrow step is to give you a manual checkpoint
  before money leaves buyer or marketplace control -- don't automate
  the release step without a real "buyer confirmed" signal.

## Regulatory note

Holding customer funds and taking a cut as a paid intermediary is
custodial money transmission / virtual asset service provision in most
countries, which typically requires registration or licensing (FinCEN
MSB + state money transmitter licenses in the US, FIU-IND registration
in India, similar regimes elsewhere) and AML/KYC obligations once
you're handling real money. This is worth checking into properly
before launching with real funds -- the technical build here doesn't
substitute for that.

## What's still missing for a real launch

- Real user accounts and authentication (buyers, sellers, and admin)
- A genuine "buyer confirms delivery" flow instead of an admin button
  (e.g. an auto-release timer after N days, with the dispute button as
  the buyer's way to pause it)
- Seller-side dashboard (list items, see incoming orders)
- Email/notification on status changes
- Rate limiting and input validation on the public routes
- HTTPS in front of this (never run real payments over plain HTTP)
