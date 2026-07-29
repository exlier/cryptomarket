# Fernway Market -- Secure Bitcoin Escrow Marketplace (Flask)

A hardened, self-contained prototype of a multi-vendor marketplace where buyers and sellers connect, buyers pay in bitcoin, and the marketplace holds funds in escrow until the buyer confirms the goods arrived. 

Built under strict architectural constraints: **Zero JavaScript, no external dependencies, pure server-side rendering, and localized deployment.** Uses SQLite, Pillow for pixel-level image sanitization, and free public block explorer APIs.

## How the money actually moves

1. Buyer clicks "buy" and is directed to a secure checkout page displaying the marketplace's master wallet address and a locally hosted QR code.
2. Buyer sends the exact BTC amount **themselves**, from their own wallet app -- nothing is ever pulled automatically, and there's no browser extension involved.
3. Buyer pastes their Transaction ID (TxID) into a secure HTML form. The Python backend verifies the transaction on-chain using a free public block explorer via direct IP routing (bypassing domain name restrictions).
4. Once confirmed, the order state updates to "Paid & Awaiting Fulfillment", triggering a dashboard notification for the vendor to ship the item.
5. When the buyer confirms delivery via a secure POST form, the backend executes an immutable ledger split: calculating the platform commission (e.g., 5%), logging the net vendor payout, and updating the escrow state to "Delivered & Released".

## Setup

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies (Flask, SQLAlchemy, Pillow, Gunicorn, etc.)
pip install -r requirements.txt

# 3. Initialize the local SQLite database
python3 -c "from app import app, db; app.app_context().push(); db.create_all()"

# 4. Configure Nginx (Production)
# Copy the provided nginx.conf to /etc/nginx/sites-available/
# Ensure the unix socket path matches: unix:/tmp/marketplace.sock
sudo systemctl restart nginx

# 5. Run the application via Gunicorn (Production)
gunicorn --bind unix:/tmp/marketplace.sock --workers 2 app:app

# For local development testing only:
# python3 app.py
# visit 127.0.0.1:5000
```

Get free testnet coins from a faucet (search "bitcoin testnet faucet") to actually test a payment going through before you ever touch mainnet or real money.

## Files

| File | Purpose |
|---|---|
| `app.py` | Core routes, session management, image sanitization logic, and escrow state machine |
| `models.py` | SQLAlchemy tables: `User`, `Product`, `Order`, `Ledger`, `WalletConfig` |
| `nginx.conf` | Hardened reverse-proxy configuration with strict CSP and static cache bypass |
| `templates/` | Pure HTML/Jinja2 templates (Zero JavaScript, strict relative paths) |
| `static/` | Localized assets only (`style.css`, sanitized `uploads/`, local `qrs/`) |

## Security model -- read this before using real money

- **Zero JavaScript & Strict Paths**: The codebase contains no client-side scripts, no external CDNs, and no full domain names. All links, form actions, and asset sources use strict relative paths to prevent external leakage.
- **Pixel-Level Image Sanitization**: All uploaded images are validated via magic bytes and rebuilt from raw pixels using Pillow. This mathematically destroys all EXIF metadata, steganography, and hidden polyglot payloads.
- **Hardened Nginx Configuration**: Enforces a strict Content-Security-Policy (CSP), hides server tokens, and limits payload sizes to 2MB to prevent resource exhaustion.
- **No External Dependencies**: Block verification uses dynamic protocol construction and direct IP routing to query public explorers. This prevents DNS hijacking, domain takedowns, or reliance on paid API keys.
- **The private key controls all funds**: If using a master wallet, anyone who obtains the seed or private key can drain the wallet. Keep secrets out of git, do not paste them into chat tools, and back them up offline.

## Regulatory note

Holding customer funds and taking a cut as a paid intermediary is custodial money transmission / virtual asset service provision in most countries, which typically requires registration or licensing (FinCEN MSB + state money transmitter licenses in the US, FIU-IND registration in India, similar regimes elsewhere) and AML/KYC obligations once you're handling real money. This is worth checking into properly before launching with real funds -- the technical build here doesn't substitute for that.

## What's still missing for a real launch

- Automated dispute resolution timers (currently relies on manual buyer confirmation or admin intervention).
- Advanced analytics and reporting dashboards for platform growth metrics.
- Bulk CSV product upload parsing for vendors (currently limited to single-file form uploads).
- Production-grade HTTPS/TLS termination (currently configured for local Port 80 testing; never run real payments over plain HTTP).
- Comprehensive rate limiting and advanced input validation on all public-facing routes.
