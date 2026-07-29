import os
import io
import secrets
from flask import Flask, request, render_template, redirect, flash, session
from werkzeug.utils import secure_filename
from PIL import Image
from models import db, User, Product

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db.init_app(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def sanitize_and_save_image(file_stream) -> str:
    """Zero-dependency, cryptographically secure image sanitization."""
    if not file_stream or not file_stream.filename:
        raise ValueError("No file provided in request.")
    
    # 1. Extension Filter & Traversal Protection
    original_filename = secure_filename(file_stream.filename)
    if not original_filename:
        raise ValueError("Invalid filename after sanitization.")
    
    ext = original_filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Invalid file type. Only PNG, JPG, and JPEG are permitted.")
    
    file_content = file_stream.read()
    if len(file_content) == 0:
        raise ValueError("Uploaded file is empty.")
    
    # 2. Magic Bytes Validation (Prevents renamed script attacks)
    if ext in ('jpg', 'jpeg'):
        if not file_content.startswith(b'\xff\xd8\xff'):
            raise ValueError("File content does not match JPEG magic bytes.")
    elif ext == 'png':
        if not file_content.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError("File content does not match PNG magic bytes.")
    
    # 3. Pixel Sanitation (Destroys EXIF, XMP, and hidden payloads)
    try:
        img = Image.open(io.BytesIO(file_content))
        img.verify() # Verify it is a valid image structure
        
        # Re-open after verify() consumes the stream
        img = Image.open(io.BytesIO(file_content))
        
        # Rebuild image from raw pixels only. This strips ALL metadata and appended code.
        clean_img = Image.frombytes(img.mode, img.size, img.tobytes())
        
        # Generate cryptographically secure random filename
        secure_name = f"{secrets.token_hex(16)}.{ext}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        
        # Save as fresh, immutable file
        clean_img.save(output_path, format=clean_img.format)
        
        # Return strict relative path for database storage
        return os.path.join('static', 'uploads', secure_name).replace('\\', '/')
        
    except Exception as e:
        raise ValueError(f"Image processing failed: {str(e)}")


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


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session or session.get('role') != 'Vendor':
        return redirect('login')
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        file = request.files.get('image')
        
        image_path = None
        if file and file.filename != '':
            try:
                image_path = sanitize_and_save_image(file)
            except ValueError as e:
                flash(str(e))
                return redirect('dashboard')
        
        new_product = Product(
            vendor_id=session['user_id'],
            name=name,
            description=description,
            price=float(price),
            image_filename=image_path
        )
        db.session.add(new_product)
        db.session.commit()
        flash("Product uploaded securely.")
        return redirect('dashboard')
    
    user_products = Product.query.filter_by(vendor_id=session['user_id']).all()
    return render_template('vendor_dashboard.html', products=user_products)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('index')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Note: For production, run via gunicorn bound to the unix socket:
    # gunicorn --bind unix:/tmp/marketplace.sock app:app
    app.run(host='127.0.0.1', port=5000)
