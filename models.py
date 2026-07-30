import os
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Buyer')
    products = db.relationship('Product', backref='vendor', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_filename = db.Column(db.String(256), nullable=True)
    
    __table_args__ = (
        db.CheckConstraint(price > 0, name='check_positive_price'),
    )

class WalletConfig(db.Model):
    __tablename__ = 'wallet_config'
    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(10), unique=True, nullable=False)
    master_address = db.Column(db.String(256), nullable=False)
    platform_fee_percentage = db.Column(db.Float, default=0.05)

class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False, index=True)
    amount_crypto = db.Column(db.Float, nullable=False)
    buyer_provided_tx = db.Column(db.String(128), nullable=True)
    escrow_state = db.Column(db.String(32), nullable=False, default='Pending Payment', index=True)
    vendor_notified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    dispatched_at = db.Column(db.DateTime, nullable=True) # Starts the 14-day timer

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
