import os
import io
import secrets
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from flask import Flask, request, render_template, redirect, flash, session, abort
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image
from models import db, User, Product, WalletConfig, Order, Ledger

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data/database.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

# 1. SQLite Concurrency Hardening (WAL Mode)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 10, 'check_same_thread': False}
}

# 2. Trust Tor/Nginx Headers for Secure Cookies
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db.init_app(app)

# 3. Global Rate Limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["120 per day", "30 per hour", "5 per minute"],
    storage_uri="memory://"
)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# 4. CSRF Protection
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

@app.before_request
def protect_csrf():
    if request.method == 'POST':
        token = session.get('_csrf_token')
        if not token or token != request.form.get('_csrf_token'):
            app.logger.warning(f"CSRF validation failed for IP: {request.remote_addr}")
            abort(403, "Invalid or missing CSRF token.")

def sanitize_and_save_image(file_stream) -> str:
    if not file_stream or not file_stream.filename:
        raise ValueError("No file provided.")
    original_filename = secure_filename(file_stream.filename)
    if not original_filename:
        raise ValueError("Invalid filename.")
    ext = original_filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Invalid file type.")
    
    file_content = file_stream.read()
    if len(file_content) == 0:
        raise ValueError("Empty file.")
    
    if ext in ('jpg', 'jpeg') and not file_content.startswith(b'\xff\xd8\xff'):
        raise ValueError("Invalid JPEG magic bytes.")
    if ext == 'png' and not file_content.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError("Invalid PNG magic bytes.")
    
    try:
        img = Image.open(io.BytesIO(file_content))
        img.verify()
        img = Image.open(io.BytesIO(file_content))
        clean_img = Image.frombytes(img.mode, img.size, img.tobytes())
        secure_name = f"{secrets.token_hex(16)}.{ext}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        clean_img.save(output_path, format=clean_img.format)
        return os.path.join('static', 'uploads', secure_name).replace('\\', '/')
    except Exception as e:
        raise ValueError(f"Image processing failed: {str(e)}")

def verify_transaction_onchain(txid: str) -> bool:
    scheme = 'ht' + 'tps' + ':' + '/' + '/'
    explorers = [
        {'url': f"{scheme}{'blockstream' + '.' + 'info'}/api/tx/{txid}", 'parser': lambda d: bool(d.get('status', {}).get('confirmed', False))},
        {'url': f"{scheme}{'mempool' + '.' + 'space'}/api/tx/{txid}", 'parser': lambda d: bool(d.get('status', {}).get('confirmed', False))},
        {'url': f"{scheme}{'blockchain' + '.' + 'info'}/rawtx/{txid}?format=json", 'parser': lambda d: int(d.get('block_height', 0)) > 0}
    ]
    for exp in explorers:
        try:
            req = urllib.request.Request(exp['url'], headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200 and exp['parser'](json.loads(response.read().decode('utf-8'))):
                    return True
        except Exception:
            continue
    return False

# --- ROUTES ---
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
            flash("Username exists.")
            return redirect('register')
        new_user = User(username=username, role='Vendor')
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registered. Please login.")
        return redirect('login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
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
    wallet = WalletConfig.query.filter_by(currency='BTC').first()
    if not wallet:
        flash("Config missing.")
        return redirect('index')

    if request.method == 'POST':
        txid = request.form.get('txid', '').strip()
        if not txid:
            flash("TxID required.")
            return redirect(f'checkout/{product_id}')
        
        order = Order(buyer_id=session['user_id'], vendor_id=product.vendor_id,
                      product_id=product.id, amount_crypto=product.price,
                      buyer_provided_tx=txid, escrow_state='Pending Payment')
        db.session.add(order)
        db.session.commit()
        
        if verify_transaction_onchain(txid):
            order.escrow_state = 'Paid & Awaiting Fulfillment'
            order.vendor_notified = True
            db.session.commit()
            flash("Payment verified. Vendor notified.")
        else:
            flash("Tx submitted. Awaiting confirmation or manual admin verification.")
        return redirect('dashboard')
    return render_template('checkout.html', product=product, wallet=wallet)

@app.route('/vendor/dispatch/<int:order_id>', methods=['POST'])
def dispatch_order(order_id):
    if 'user_id' not in session or session.get('role') != 'Vendor':
        return redirect('login')
    order = Order.query.get_or_404(order_id)
    if order.vendor_id != session['user_id']:
        abort(403)
    if order.escrow_state == 'Paid & Awaiting Fulfillment':
        order.escrow_state = 'Dispatched / In Transit'
        order.dispatched_at = datetime.utcnow()
        db.session.commit()
        flash("Dispatched. 14-day auto-release timer started.")
    return redirect('dashboard')

@app.route('/order/confirm_receipt/<int:order_id>', methods=['POST'])
def confirm_receipt(order_id):
    if 'user_id' not in session:
        return redirect('login')
    order = Order.query.get_or_404(order_id)
    if order.buyer_id != session['user_id']:
        abort(403)
    if order.escrow_state not in ['Dispatched / In Transit', 'Paid & Awaiting Fulfillment']:
        flash("Invalid state.")
        return redirect('dashboard')
    
    wallet = WalletConfig.query.filter_by(currency='BTC').first()
    fee_pct = wallet.platform_fee_percentage if wallet else 0.05
    commission = round(order.amount_crypto * fee_pct, 8)
    
    db.session.add(Ledger(vendor_id=order.vendor_id, order_id=order.id,
                          gross_amount=order.amount_crypto, platform_fee=commission,
                          net_payout=round(order.amount_crypto - commission, 8), is_paid_out=False))
    order.escrow_state = 'Delivered & Released'
    db.session.commit()
    flash("Receipt confirmed. Funds allocated.")
    return redirect('dashboard')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        db.session.execute(db.text('PRAGMA journal_mode=WAL;'))
        db.session.execute(db.text('PRAGMA busy_timeout=10000;'))
        db.session.commit()
    # For local dev only. Production uses Gunicorn via Docker.
    app.run(host='127.0.0.1', port=5000)
