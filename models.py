from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    price_btc = db.Column(db.Float, nullable=False)
    seller_name = db.Column(db.String(120), nullable=False)
    seller_payout_address = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), default="general")


class Order(db.Model):
    """
    One order = one address from the marketplace's single escrow wallet.

    The buyer sends BTC there themselves (no auto-pull, no browser
    extension -- they copy the address or scan the QR from their own
    wallet app). Funds sit in the marketplace wallet until an admin
    releases them to the seller, at which point the commission is kept
    automatically as leftover change on the payout transaction.

    Status lifecycle:
      awaiting_payment -> address shown, nothing received yet
      escrowed         -> payment seen with enough confirmations, held
      released         -> paid out to the seller (commission kept)
      refunded         -> paid back to the buyer instead
      disputed         -> flagged, frozen until an admin resolves it
    """

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)

    buyer_contact = db.Column(db.String(200), nullable=False)
    buyer_refund_address = db.Column(db.String(120), nullable=False)

    deposit_address = db.Column(db.String(120), nullable=False, unique=True)
    wallet_key_id = db.Column(db.Integer, nullable=False, unique=True)  # bitcoinlib key_id
    expected_amount_btc = db.Column(db.Float, nullable=False)
    received_amount_btc = db.Column(db.Float, default=0.0)

    status = db.Column(db.String(30), default="awaiting_payment")
    incoming_txid = db.Column(db.String(120))
    payout_txid = db.Column(db.String(120))
    commission_btc = db.Column(db.Float)
    dispute_note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    escrowed_at = db.Column(db.DateTime)
    released_at = db.Column(db.DateTime)

    product = db.relationship("Product")
