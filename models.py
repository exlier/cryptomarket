import os
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

# ... [User, Product, WalletConfig, Ledger models remain unchanged] ...

class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    amount_crypto = db.Column(db.Float, nullable=False)
    buyer_provided_tx = db.Column(db.String(128), nullable=True)
    escrow_state = db.Column(db.String(32), nullable=False, default='Pending Payment')
    vendor_notified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # NEW: Tracks when the vendor marks the item as shipped, starting the 14-day auto-release clock
    dispatched_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            escrow_state.in_(['Pending Payment', 'Paid & Awaiting Fulfillment', 'Dispatched / In Transit', 'Delivered & Released', 'Disputed']),
            name='check_valid_escrow_state'
        ),
    )
