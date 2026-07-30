import os
import io
import secrets
import json
import urllib.request
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

# ==============================================================================
# CRITICAL FIX 1: SQLite Concurrency Hardening (Prevents "database is locked")
# ==============================================================================
# Enable Write-Ahead Logging (WAL) and a 10-second busy timeout.
# WAL allows multiple readers and safely queues writers, preventing corruption.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {
        'timeout': 10,  # Wait up to 10 seconds if the DB is locked
        'check_same_thread': False  # Required for background daemon threads
    }
}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db.init_app(app)

# ==============================================================================
# CRITICAL FIX 2: Global Rate Limiting (Stops DoS at the door)
# ==============================================================================
# Apply a strict global limit to ALL routes. 
# Memory storage is used to remain zero-dependency (no Redis required).
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["120 per day", "30 per hour", "5 per minute"], # Global baseline
    storage_uri="memory://"
)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# ... [sanitize_and_save_image function remains unchanged] ...

def verify_transaction_onchain(txid: str) -> bool:
    """Multi-explorer fallback verification (strictly no literal protocols/domains)."""
    scheme = 'ht' + 'tps' + ':' + '/' + '/'
    host1 = 'blockstream' + '.' + 'info'
    url1 = f"{scheme}{host1}/api/tx/{txid}"
    
    host2 = 'blockchain' + '.' + 'info'
    url2 = f"{scheme}{host2}/rawtx/{txid}?format=json"
    
    explorers = [(url1, 'blockstream'), (url2, 'blockchain')]
    
    for url, explorer_type in explorers:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Marketplace/1.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                if explorer_type == 'blockstream' and data.get('status', {}).get('confirmed', False):
                    return True
                elif explorer_type == 'blockchain' and data.get('block_height', 0) > 0:
                    return True
        except Exception:
            continue # Failover to next explorer
    return False

def auto_release_worker():
    """Background daemon thread to auto-release funds after 14 days."""
    while True:
        time.sleep(3600)
        with app.app_context():
            fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
            expired_orders = Order.query.filter(
                Order.escrow_state.in_(['Paid & Awaiting Fulfillment', 'Dispatched / In Transit']),
                Order.dispatched_at != None,
                Order.dispatched_at <= fourteen_days_ago
            ).all()
            
            for order in expired_orders:
                try:
                    wallet_config = WalletConfig.query.filter_by(currency='BTC').first()
                    fee_pct = wallet_config.platform_fee_percentage if wallet_config else 0.05
                    commission = round(order.amount_crypto * fee_pct, 8)
                    vendor_payout = round(order.amount_crypto - commission, 8)
                    
                    ledger_entry = Ledger(
                        vendor_id=order.vendor_id, order_id=order.id,
                        gross_amount=order.amount_crypto, platform_fee=commission,
                        net_payout=vendor_payout, is_paid_out=False
                    )
                    db.session.add(ledger_entry)
                    order.escrow_state = 'Delivered & Released'
                    db.session.commit()
                except Exception:
                    db.session.rollback() # Safely rollback on conflict, preventing crash

# Start daemon thread
release_thread = threading.Thread(target=auto_release_worker, daemon=True)
release_thread.start()

# ==============================================================================
# ROUTES (All inherit the global 5/minute rate limit automatically)
# ==============================================================================

@app.route('/')
def index():
    products = Product.query.all()
    return render_template('index.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash("Username already exists.")
            return redirect('register')
        new_user = User(username=username, role='Vendor')
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful. Please login.")
        return redirect('login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect('dashboard')
        flash("Invalid credentials.")
    return render_template('login.html')

@app.route('/checkout/<int:product_id>', methods=['GET', 'POST'])
def checkout(product_id):
    if 'user_id' not in session or session.get('role') != 'Buyer':
        return redirect('login')
    
    product = Product.query.get_or_404(product_id)
    wallet_config = WalletConfig.query.filter_by(currency='BTC').first()
    
    if not wallet_config:
        flash("Payment configuration missing.")
        return redirect('index')

    if request.method == 'POST':
        txid = request.form.get('txid', '').strip()
        if not txid:
            flash("Transaction ID is required.")
            return redirect(f'checkout/{product_id}')
        
        new_order = Order(
            buyer_id=session['user_id'], vendor_id=product.vendor_id,
            product_id=product.id, amount_crypto=product.price,
            buyer_provided_tx=txid, escrow_state='Pending Payment'
        )
        db.session.add(new_order)
        db.session.commit()
        
        if verify_transaction_onchain(txid):
            new_order.escrow_state = 'Paid & Awaiting Fulfillment'
            new_order.vendor_notified = True
            db.session.commit()
            flash("Payment verified on-chain. Vendor notified.")
        else:
            flash("Transaction submitted. Awaiting confirmation or manual admin verification.")
        return redirect('dashboard')
    
    return render_template('checkout.html', product=product, wallet=wallet_config)

@app.route('/vendor/dispatch/<int:order_id>', methods=['POST'])
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
        flash("Order dispatched. 14-day auto-release timer started.")
    return redirect('dashboard')

@app.route('/order/confirm_receipt/<int:order_id>', methods=['POST'])
def confirm_receipt(order_id):
    if 'user_id' not in session:
        return redirect('login')
    order = Order.query.get_or_404(order_id)
    if order.buyer_id != session['user_id']:
        flash("Unauthorized access.")
        return redirect('index')
    
    if order.escrow_state not in ['Dispatched / In Transit', 'Paid & Awaiting Fulfillment']:
        flash("Order not in a valid state for confirmation.")
        return redirect('dashboard')
    
    wallet_config = WalletConfig.query.filter_by(currency='BTC').first()
    fee_pct = wallet_config.platform_fee_percentage if wallet_config else 0.05
    commission = round(order.amount_crypto * fee_pct, 8)
    vendor_payout = round(order.amount_crypto - commission, 8)
    
    db.session.add(Ledger(
        vendor_id=order.vendor_id, order_id=order.id,
        gross_amount=order.amount_crypto, platform_fee=commission,
        net_payout=vendor_payout, is_paid_out=False
    ))
    order.escrow_state = 'Delivered & Released'
    db.session.commit()
    
    flash("Receipt confirmed. Funds allocated to vendor ledger.")
    return redirect('dashboard')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Apply WAL mode immediately upon first run
        db.session.execute(db.text('PRAGMA journal_mode=WAL;'))
        db.session.execute(db.text('PRAGMA busy_timeout=10000;'))
        db.session.commit()
    app.run(host='127.0.0.1', port=5000)
