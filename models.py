import os
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

# ... [Previous User and Product models remain here] ...

class WalletConfig(db.Model):
    __tablename__ = 'wallet_config'
    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(10), unique=True, nullable=False) # e.g., 'BTC'
    master_address = db.Column(db.String(256), nullable=False)
    platform_fee_percentage = db.Column(db.Float, default=0.05) # 5% default commission

class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    amount_crypto = db.Column(db.Float, nullable=False)
    buyer_provided_tx = db.Column(db.String(128), nullable=True)
    # Strict state machine enforcement
    escrow_state = db.Column(db.String(32), nullable=False, default='Pending Payment')
    vendor_notified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint(
            escrow_state.in_(['Pending Payment', 'Paid & Awaiting Fulfillment', 'Dispatched / In Transit', 'Delivered & Released', 'Disputed']),
            name='check_valid_escrow_state'
        ),
    )

class Ledger(db.Model):
    __tablename__ = 'ledger'
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False, unique=True)
    gross_amount = db.Column(db.Float, nullable=False)
    platform_fee = db.Column(db.Float, nullable=False)
    net_payout = db.Column(db.Float, nullable=False)
    is_paid_out = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
