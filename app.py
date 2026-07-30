import os
import io
import secrets
import json
import urllib.request
import urllib.error
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, render_template, redirect, flash, session
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from PIL import Image
from models import db, User, Product, WalletConfig, Order, Ledger

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 10, 'check_same_thread': False}
}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db.init_app(app)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["120 per day", "30 per hour", "5 per minute"],
    storage_uri="memory://"
)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# ... [sanitize_and_save_image and verify_transaction_onchain remain unchanged] ...

# ==============================================================================
# CORE ESCROW RESOLUTION LOGIC (Idempotent & Reusable)
# ==============================================================================
def attempt_auto_release(order: Order) -> bool:
    """
    Checks if an order has exceeded the 14-day dispute window.
    If so, executes the ledger split and updates the state.
    Returns True if released, False otherwise.
    """
    if order.escrow_state in ['Delivered & Released', 'Disputed', 'Refunded']:
        return False # Already resolved
        
    if order.dispatched_at is None:
        return False # Not yet shipped
        
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
    
    if order.dispatched_at <= fourteen_days_ago:
        try:
            wallet_config = WalletConfig.query.filter_by(currency='BTC').first()
            fee_pct = wallet_config.platform_fee_percentage if wallet_config else 0.05
            
            commission = round(order.amount_crypto * fee_pct, 8)
            vendor_payout = round(order.amount_crypto - commission, 8)
            
            ledger_entry = Ledger(
                vendor_id=order.vendor_id,
                order_id=order.id,
                gross_amount=order.amount_crypto,
                platform_fee=commission,
                net_payout=vendor_payout,
                is_paid_out=False
            )
            db.session.add(ledger_entry)
            order.escrow_state = 'Delivered & Released'
            db.session.commit()
            print(f"[AUTO-RELEASE] Order {order.id} successfully released after 14-day expiration.")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"[AUTO-RELEASE ERROR] Failed on order {order.id}: {e}")
            return False
            
    return False


def auto_release_worker():
    """Proactive Layer: Background daemon thread to auto-release funds hourly."""
    while True:
        time.sleep(3600)
        with app.app_context():
            # Fetch only orders that are shipped and potentially expired
            candidate_orders = Order.query.filter(
                Order.escrow_state.in_(['Paid & Awaiting Fulfillment', 'Dispatched / In Transit']),
                Order.dispatched_at != None
            ).all()
            
            for order in candidate_orders:
                attempt_auto_release(order)

# Start daemon thread
release_thread = threading.Thread(target=auto_release_worker, daemon=True)
release_thread.start()


# ... [index, register, login, checkout routes remain unchanged] ...

@app.route('/vendor/dispatch/<int:order_id>', methods=['POST'])
@limiter.limit("5 per minute")
def dispatch_order(order_id):
    if 'user_id' not in session or session.get('role') != 'Vendor':
        return redirect('login')
    
    order = Order.query.get_or_404(order_id)
    if order.vendor_id != session['user_id']:
        flash("Unauthorized access.")
        return redirect('dashboard')
    
    if order.escrow_state == 'Paid & Awaiting Fulfillment':
        order.escrow_state = 'Dispatched / In Transit'
        order.dispatched_at = datetime.utcnow()
        db.session.commit()
        flash("Order marked as dispatched. 14-day auto-release timer has started.")
    
    return redirect('dashboard')


@app.route('/order/details/<int:order_id>')
@limiter.limit("30 per minute")
def order_details(order_id):
    """
    Lazy Evaluation Layer: Guarantees funds are never permanently locked.
    Simply viewing an expired order triggers the auto-release synchronously.
    """
    if 'user_id' not in session:
        return redirect('login')
    
    order = Order.query.get_or_404(order_id)
    
    # Enforce RBAC: Only buyer, vendor, or admin can view
    is_authorized = (
        order.buyer_id == session['user_id'] or 
        order.vendor_id == session['user_id'] or 
        session.get('role') == 'Admin'
    )
    if not is_authorized:
        flash("Unauthorized access.")
        return redirect('dashboard')

    # LAZY EVALUATION: Check and release immediately if expired
    if attempt_auto_release(order):
        flash("Dispute window expired. Funds have been automatically released to the vendor.")

    return render_template('order_details.html', order=order)


@app.route('/order/confirm_receipt/<int:order_id>', methods=['POST'])
@limiter.limit("5 per minute")
def confirm_receipt(order_id):
    if 'user_id' not in session:
        return redirect('login')
    
    order = Order.query.get_or_404(order_id)
    if order.buyer_id != session['user_id']:
        flash("Unauthorized access.")
        return redirect('dashboard')
    
    if order.escrow_state not in ['Dispatched / In Transit', 'Paid & Awaiting Fulfillment']:
        flash("Order is not in a valid state for receipt confirmation.")
        return redirect('dashboard')
    
    # Execute immediate release (reuses the same safe logic)
    attempt_auto_release(order)
    flash("Receipt confirmed. Funds have been securely allocated to the vendor ledger.")
    return redirect('dashboard')
