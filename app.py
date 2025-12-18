"""
Line Ranger ID Store - Flask Application
Main application file with routes and database models
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import json
import threading
import queue
import time
import requests
import re
from adb_handler import link_id, adb_handler, continue_phase2
from config import Config

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db = SQLAlchemy(app)

# Initialize login manager
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'กรุณาเข้าสู่ระบบก่อน'

# ============== DATABASE MODELS ==============

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    role = db.Column(db.String(20), default='user')  # user, admin
    orders = db.relationship('Order', backref='user', lazy=True)
    topups = db.relationship('TopUp', backref='user', lazy=True)
    
    @property
    def is_admin(self):
        return self.role == 'admin'

    def set_password(self, password):
        self.password = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    image_path = db.Column(db.String(500))
    # xml_file and is_sold are moved to ProductStock
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to stocks
    stocks = db.relationship('ProductStock', backref='product', lazy=True, cascade="all, delete-orphan")
    
    @property
    def stock_count(self):
        return ProductStock.query.filter_by(product_id=self.id, is_sold=False).count()
        
    @property
    def is_sold_out(self):
        return self.stock_count == 0

class ProductStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    xml_file = db.Column(db.String(500), nullable=False)
    is_sold = db.Column(db.Boolean, default=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False) # Keep link for metadata
    
    # Credentials (filled by user later)
    link_method = db.Column(db.String(20), nullable=True)
    customer_id = db.Column(db.String(200), nullable=True)
    customer_pass = db.Column(db.String(200), nullable=True)
    
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to the specific stock item purchased
    stock_item = db.relationship('ProductStock', backref='order', uselist=False, lazy=True)
    
    # Helper to get product details easily. 'product' backref is already defined in Product model (backref='product_orders'? No, backref='product' in OLD model, wait.)
    # In New Product model: stocks = ...
    # Old Product model: orders = db.relationship('Order', backref='product', lazy=True)
    # I removed 'orders' from Product model in New Code!
    # I should add it back or define it in Order.
    # New Code Order: no relationship defined to Product explicitly except via ForeignKey.
    # I should add:
    product = db.relationship('Product', backref='orders', lazy=True)


class TopUp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    # method = db.Column(db.String(50), nullable=False) -> Old one had default='tw_angpao'
    method = db.Column(db.String(50), default='tw_angpao') # Keep default
    # reference_code code? Old had reference_code. New Code had gift_link?
    # Old: reference_code = db.Column(db.String(100), unique=True, nullable=False)
    # New (Step 257): gift_link = db.Column(db.String(500), nullable=True)
    # Use the OLD TopUp definition or Upgrade it?
    # The new TopUp definition in Step 257 had `gift_link`.
    # But `topup_tw` function uses `reference_code`?
    # I should KEEP `reference_code` for TW integration.
    reference_code = db.Column(db.String(100), unique=True, nullable=True) # made nullable just in case
    gift_link = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default='pending') 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ============== HELPER FUNCTIONS ==============

def allowed_file(filename, types=None):
    if types is None:
        types = Config.ALLOWED_EXTENSIONS
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in types


def verify_tw_voucher(voucher_link, phone_number):
    """Verify and redeem TrueMoney Wallet Voucher using tw-voucher proxy API"""
    try:
        # 1. Validate phone number
        phone_number = str(phone_number).strip()
        if not phone_number or not phone_number.isdigit():
            return {'success': False, 'error': 'Invalid phone number'}
        
        # 2. Extract voucher code (must be 35 characters)
        voucher_link = str(voucher_link).strip()
        parts = voucher_link.split("v=")
        code_part = parts[1] if len(parts) > 1 else parts[0]
        
        # Extract alphanumeric code
        match = re.search(r'[0-9A-Za-z]+', code_part)
        if not match:
            return {'success': False, 'error': 'Invalid Voucher Link'}
        
        code = match.group(0)
        
        # Voucher code should be 35 characters
        if len(code) != 35:
            return {'success': False, 'error': f'Invalid voucher code length ({len(code)}/35)'}
        
        # 3. Call Proxy API (same as tw-voucher package)
        proxy_url = "https://truewalletproxy-755211536068837409.rcf2.deploys.app/api"
        
        payload = {
            "mobile": phone_number,
            "voucher": code
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "multilabxxxxxxxx"
        }
        
        response = requests.post(proxy_url, json=payload, headers=headers, timeout=15)
        
        try:
            data = response.json()
        except ValueError:
            print(f"Proxy API Error: Status {response.status_code}, Body: {response.text}")
            return {'success': False, 'error': f"API Error ({response.status_code}): {response.text[:100]}"}
        
        # 4. Process response
        if data.get('status', {}).get('code') == 'SUCCESS':
            ticket = data.get('data', {}).get('my_ticket', {})
            amount_str = ticket.get('amount_baht', '0')
            amount = float(str(amount_str).replace(',', ''))
            owner_name = data.get('data', {}).get('owner_profile', {}).get('full_name', 'Unknown')
            
            return {
                'success': True,
                'amount': amount,
                'owner_name': owner_name,
                'code': code
            }
        else:
            error_code = data.get('status', {}).get('code', 'UNKNOWN_ERROR')
            error_message = data.get('status', {}).get('message', error_code)
            return {'success': False, 'error': error_message}
            
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'Connection timeout'}
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {e}")
        return {'success': False, 'error': f'Connection error: {str(e)}'}
    except Exception as e:
        print(f"System Error: {e}")
        return {'success': False, 'error': str(e)}



# ============== QUEUE SYSTEM ==============

# Global Queue for ADB Tasks
job_queue = queue.Queue()
active_orders = set()
processing_lock = threading.Lock()

# Global Log Subscribers
log_subscribers = {}
subscribers_lock = threading.Lock()

def broadcast_log(order_id, message):
    with subscribers_lock:
        if order_id in log_subscribers:
            dead_queues = []
            for q in log_subscribers[order_id]:
                try:
                    q.put(message)
                except:
                    dead_queues.append(q)
            for dq in dead_queues:
                if dq in log_subscribers[order_id]:
                    log_subscribers[order_id].remove(dq)

def subscribe_log(order_id):
    q = queue.Queue()
    with subscribers_lock:
        if order_id not in log_subscribers:
            log_subscribers[order_id] = []
        log_subscribers[order_id].append(q)
    return q

def remove_subscription(order_id, q):
    with subscribers_lock:
        if order_id in log_subscribers:
            if q in log_subscribers[order_id]:
                log_subscribers[order_id].remove(q)
            if not log_subscribers[order_id]:
                del log_subscribers[order_id]

def worker_thread():
    """Background worker to process ADB tasks sequentially"""
    print("[Queue] Worker Thread Started")
    with app.app_context():
        while True:
            try:
                job = job_queue.get()
                order_id = job['order_id']
                job_type = job['type']
                
                print(f"[Queue] Processing job: {job_type} for Order {order_id}")
                
                # Check Queue Position
                q_size = job_queue.qsize()
                broadcast_log(order_id, f"STATUS:กำลังดำเนินการ (คิวรอ: {q_size})...")
                
                def worker_callback(msg):
                    broadcast_log(order_id, msg)
                
                if job_type == 'link_id':
                    # Retrieve latest order data
                    order = db.session.get(Order, order_id)
                    if not order:
                        broadcast_log(order_id, "ERROR:Order not found")
                    elif not order.stock_item:
                        broadcast_log(order_id, "ERROR:No stock item associated")
                    else:
                        xml_path = os.path.join(Config.PRODUCTS_FOLDER, order.stock_item.xml_file)
                        result = link_id(
                            source_xml_path=xml_path,
                            link_method=order.link_method,
                            customer_id=order.customer_id,
                            customer_pass=order.customer_pass,
                            automate=True,
                            callback=worker_callback
                        )
                        
                        if result.get('success'):
                            if result.get('verification_code'):
                                broadcast_log(order_id, f"VERIFICATION_CODE:{result['verification_code']}")
                            else:
                                broadcast_log(order_id, "SUCCESS:Automation Complete")
                            
                            # Update order status
                            order.status = 'processing'
                            db.session.commit()
                        else:
                            broadcast_log(order_id, f"ERROR:{result.get('error', 'Unknown Error')}")



                elif job_type == 'phase2':
                    result = continue_phase2(callback=worker_callback)
                    if result.get('success'):
                        broadcast_log(order_id, "SUCCESS:Phase 2 Complete")
                    else:
                        broadcast_log(order_id, f"ERROR:{result.get('error', 'Phase 2 Failed')}")
                
            except Exception as e:
                print(f"[Queue] Error: {e}")
                if 'order_id' in locals():
                    broadcast_log(order_id, f"ERROR:System Error {str(e)}")
            finally:
                if 'order_id' in locals():
                    with processing_lock:
                        active_orders.discard(order_id)
                job_queue.task_done()


# ============== PUBLIC ROUTES ==============

@app.route('/')
def home():
    # Show last 6 products
    products = Product.query.order_by(Product.created_at.desc()).limit(6).all()
    return render_template('index.html', products=products)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('เข้าสู่ระบบสำเร็จ!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'error')
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if password != confirm_password:
            flash('รหัสผ่านไม่ตรงกัน', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('ชื่อผู้ใช้นี้ถูกใช้แล้ว', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('อีเมลนี้ถูกใช้แล้ว', 'error')
            return render_template('register.html')
        
        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('ลงทะเบียนสำเร็จ! กรุณาเข้าสู่ระบบ', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ออกจากระบบสำเร็จ', 'success')
    return redirect(url_for('home'))


# ============== PRODUCT ROUTES ==============

@app.route('/products')
def products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('products.html', products=products)


@app.route('/product/<int:id>')
def product_detail(id):
    product = Product.query.get_or_404(id)
    return render_template('product_detail.html', product=product)


@app.route('/buy/<int:product_id>', methods=['POST'])
@login_required
def buy_product(product_id):
    """Purchase a product - assigns an available stock item"""
    product = Product.query.get_or_404(product_id)
    
    # 1. Find available stock
    # Locking rows is DB specific, here we just select first available
    stock_item = ProductStock.query.filter_by(product_id=product.id, is_sold=False).order_by(ProductStock.id.asc()).first()
    
    if not stock_item:
        if 'application/json' in request.accept_mimetypes:
            return jsonify({'success': False, 'message': 'สินค้าหมดสต็อก'})
        flash('สินค้าหมดสต็อก', 'error')
        return redirect(url_for('products'))
    
    # 2. Check Balance
    if current_user.balance < product.price:
        if 'application/json' in request.accept_mimetypes:
            return jsonify({'success': False, 'message': 'ยอดเงินไม่เพียงพอ'})
        flash('ยอดเงินไม่เพียงพอ กรุณาเติมเงิน', 'error')
        return redirect(url_for('topup_page'))

    # 3. Process Transaction
    try:
        # Deduct balance
        current_user.balance -= product.price
        
        # Create Order
        order = Order(
            user_id=current_user.id,
            product_id=product.id,
            status='pending'
        )
        db.session.add(order)
        db.session.flush() # Get order ID
        
        # Assign stock
        stock_item.is_sold = True
        stock_item.order_id = order.id
        
        db.session.commit()
        
        if 'application/json' in request.accept_mimetypes:
            return jsonify({'success': True, 'message': 'สั่งซื้อสำเร็จ!', 'order_id': order.id})
        
        flash('สั่งซื้อสำเร็จ!', 'success')
        return redirect(url_for('inventory'))
        
    except Exception as e:
        db.session.rollback()
        print(f"Error buying product: {e}")
        if 'application/json' in request.accept_mimetypes:
            return jsonify({'success': False, 'message': 'เกิดข้อผิดพลาดในการสั่งซื้อ'})
        flash('เกิดข้อผิดพลาดในการสั่งซื้อ', 'error')
        return redirect(url_for('product_detail', id=product_id))


# ============== USER ROUTES ==============

@app.route('/topup')
@login_required
def topup_page():
    topups = TopUp.query.filter_by(user_id=current_user.id).order_by(TopUp.created_at.desc()).all()
    return render_template('topup.html', topups=topups)

@app.route('/topup/tw', methods=['POST'])
@login_required
def topup_tw():
    voucher_link = request.form.get('voucher_link')
    if not voucher_link:
        flash('กรุณากรอกลิงค์อั่งเปา', 'error')
        return redirect(url_for('topup_page'))
    
    # Check if duplicate in DB
    # We need to extract code first or rely on verify logic
    # Let's verify first
    
    result = verify_tw_voucher(voucher_link, Config.TW_MERCHANT_PHONE)
    
    if result['success']:
        amount = result['amount']
        code = result['code']
        
        # Check duplicate code
        if TopUp.query.filter_by(reference_code=code).first():
             flash(f'ซองนี้ถูกใช้งานไปแล้ว (เติมได้ {amount} บาท)', 'warning')
             return redirect(url_for('topup_page'))
        
        # Success
        new_topup = TopUp(
            user_id=current_user.id,
            amount=amount,
            method='tw_angpao',
            reference_code=code,
            status='success'
        )
        current_user.balance += amount
        db.session.add(new_topup)
        db.session.commit()
        
        flash(f'เติมเงินสำเร็จ! +{amount} บาท', 'success')
    else:
        flash(f"เติมเงินไม่สำเร็จ: {result['error']}", 'error')
        
    return redirect(url_for('topup_page'))


@app.route('/inventory')
@login_required
def inventory():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('inventory.html', orders=orders)


@app.route('/api/order/<int:order_id>/download_xml')
@login_required
def download_xml(order_id):
    """Download XML file for an order"""
    order = Order.query.get_or_404(order_id)
    
    if order.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if not order.stock_item:
        return jsonify({'success': False, 'message': 'No file associated'}), 404
        
    xml_path = os.path.join(Config.PRODUCTS_FOLDER, order.stock_item.xml_file)
    
    if not os.path.exists(xml_path):
        return jsonify({'success': False, 'message': 'File not found on server'}), 404
    
    from flask import send_file
    return send_file(
        xml_path,
        as_attachment=True,
        download_name=f"{order.product.name}_ID.xml"
    )

@app.route('/api/order/<int:order_id>/link', methods=['POST'])
@login_required
def user_link_order(order_id):
    """User initiates link ID from inventory"""
    order = Order.query.get_or_404(order_id)
    
    if order.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    link_method = request.form.get('link_method')
    customer_id = request.form.get('customer_id')
    customer_pass = request.form.get('customer_pass')
    
    if not all([link_method, customer_id, customer_pass]):
        return jsonify({'success': False, 'message': 'กรุณากรอกข้อมูลให้ครบถ้วน'})
    
    order.link_method = link_method
    order.customer_id = customer_id
    order.customer_pass = customer_pass
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'บันทึกข้อมูลแล้ว รอแอดมินดำเนินการ'})



# ============== ADMIN ROUTES ==============

def admin_required(f):
    """Decorator that checks if user is admin"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    pending_count = Order.query.filter_by(status='pending').count()
    processing_count = Order.query.filter_by(status='processing').count()
    done_count = Order.query.filter_by(status='done').count()
    product_count = Product.query.count()
    
    return render_template('admin/dashboard.html', 
                         pending_count=pending_count,
                         processing_count=processing_count,
                         done_count=done_count,
                         product_count=product_count)


@app.route('/admin/orders')
@app.route('/admin/orders/<status>')
@login_required
@admin_required
def admin_orders(status='pending'):
    if status not in ['pending', 'processing', 'done']:
        status = 'pending'
    
    orders = Order.query.filter_by(status=status).order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', orders=orders, current_status=status)


@app.route('/admin/order/<int:order_id>/update', methods=['POST'])
@login_required
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    
    if new_status in ['pending', 'processing', 'done']:
        order.status = new_status
        db.session.commit()
        flash(f'อัพเดทสถานะออเดอร์ #{order_id} สำเร็จ', 'success')
    else:
        flash('สถานะไม่ถูกต้อง', 'error')
    
    return redirect(url_for('admin_orders', status=new_status))


@app.route('/admin/order/<int:order_id>/link', methods=['POST'])
@login_required
@admin_required
def link_order_id(order_id):
    """Link ID for an order using ADB with full automation"""
    order = Order.query.get_or_404(order_id)
    product = order.product
    
    # Get product XML path
    xml_path = os.path.join(Config.PRODUCTS_FOLDER, product.xml_file)
    
    if not os.path.exists(xml_path):
        return jsonify({
            'success': False,
            'message': f'ไม่พบไฟล์ XML ของสินค้า: {product.xml_file}'
        })
    
    # Import and run ADB handler with FULL automation
    try:
        from adb_handler import link_id
        
        # ส่ง credentials ไปด้วยเพื่อให้ automation ทำงาน
        result = link_id(
            source_xml_path=xml_path,
            link_method=order.link_method,      # 'google' or 'line'
            customer_id=order.customer_id,       # Email/LINE ID
            customer_pass=order.customer_pass,   # Password
            automate=True                        # เปิด automation
        )
        
        if result['success']:
            # Update order status to processing
            order.status = 'processing'
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': result.get('message', f'Link ID สำเร็จ! ({order.link_method.upper()} Login)'),
                'verification_code': result.get('automation', {}).get('verification_code'),
                'order_info': {
                    'link_method': order.link_method,
                    'customer_id': order.customer_id
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': result.get('error', 'เกิดข้อผิดพลาด')
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'เกิดข้อผิดพลาด: {str(e)}'
        })


# ============== ADMIN PRODUCT MANAGEMENT ==============

@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin/products.html', products=products)


@app.route('/admin/product/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        
        # Image
        image = request.files.get('image')
        image_filename = None
        if image and image.filename:
            filename = secure_filename(image.filename)
            # Add timestamp
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            image.save(os.path.join(Config.UPLOAD_FOLDER, filename))
            image_filename = filename
            
        # Create Product
        new_product = Product(
            name=name,
            description=description,
            price=price,
            image_path=image_filename
        )
        db.session.add(new_product)
        db.session.flush() # get ID
        
        # Process XML Files (Multiple)
        xml_files = request.files.getlist('xml_files[]')
        
        count = 0
        for xml_file in xml_files:
            if xml_file and xml_file.filename:
                # Format: GUESTv3_{Product}_{Index}.xml or similar
                original_name = secure_filename(xml_file.filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                saved_filename = f"{timestamp}_{count}_{original_name}"
                
                xml_path = os.path.join(Config.PRODUCTS_FOLDER, saved_filename)
                xml_file.save(xml_path)
                
                # Create Stock Item
                stock = ProductStock(
                    product_id=new_product.id,
                    xml_file=saved_filename,
                    is_sold=False
                )
                db.session.add(stock)
                count += 1
        
        db.session.commit()
        flash(f'เพิ่มสินค้าเรียบร้อย ({count} ไอดี)', 'success')
        return redirect(url_for('admin_products'))
        
    return render_template('admin/add_product.html')


@app.route('/admin/product/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.price = float(request.form.get('price'))
        
        # New Image
        image = request.files.get('image')
        if image and image.filename:
            # Delete old image if exists
            if product.image_path:
                try:
                    os.remove(os.path.join(Config.UPLOAD_FOLDER, product.image_path))
                except:
                    pass
            
            filename = secure_filename(image.filename)
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            image.save(os.path.join(Config.UPLOAD_FOLDER, filename))
            product.image_path = filename
            
        # Add MORE XML Files
        new_xml_files = request.files.getlist('xml_files[]')
        count = 0
        for xml_file in new_xml_files:
            if xml_file and xml_file.filename:
                original_name = secure_filename(xml_file.filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                saved_filename = f"{timestamp}_add_{count}_{original_name}"
                
                xml_path = os.path.join(Config.PRODUCTS_FOLDER, saved_filename)
                xml_file.save(xml_path)
                
                stock = ProductStock(
                    product_id=product.id,
                    xml_file=saved_filename,
                    is_sold=False
                )
                db.session.add(stock)
                count += 1
                
        db.session.commit()
        flash(f'แก้ไขสินค้าเรียบร้อย (เพิ่ม {count} ไอดี)', 'success')
        return redirect(url_for('admin_products'))
        
    return render_template('admin/edit_product.html', product=product)


@app.route('/admin/product/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    
    # Delete image
    if product.image_path:
        try:
            os.remove(os.path.join(Config.UPLOAD_FOLDER, product.image_path))
        except:
            pass
            
    # Delete XML files (Stocks)
    for stock in product.stocks:
        try:
            os.remove(os.path.join(Config.PRODUCTS_FOLDER, stock.xml_file))
        except:
            pass
            
    db.session.delete(product)
    db.session.commit()
    
    flash('ลบสินค้าสำเร็จ!', 'success')
    return redirect(url_for('admin_products'))


@app.route('/admin/stock/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_stock_item(id):
    stock = ProductStock.query.get_or_404(id)
    
    # Only allow deleting unsold stock
    if stock.is_sold:
        return jsonify({'success': False, 'message': 'ไม่สามารถลบสินค้าที่ขายแล้วได้'})
        
    try:
        # Delete file
        os.remove(os.path.join(Config.PRODUCTS_FOLDER, stock.xml_file))
    except Exception as e:
        print(f"Error deleting stock file: {e}")
        
    db.session.delete(stock)
    db.session.commit()
    
    return jsonify({'success': True})


# ============== API ENDPOINTS ==============

@app.route('/api/order/<int:order_id>')
@login_required
@admin_required
def get_order_details(order_id):
    order = Order.query.get_or_404(order_id)
    return jsonify({
        'id': order.id,
        'product_name': order.product.name,
        'customer': order.user.username,
        'link_method': order.link_method,
        'customer_id': order.customer_id,
        'customer_pass': order.customer_pass,
        'status': order.status,
        'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })


from adb_handler import continue_phase2 # Added import

@app.route('/api/stream_automation/<int:order_id>')
@login_required
def stream_automation(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    # Determine if we should queue a new job
    # We only queue if it's not currently active to prevent duplicates on refresh
    queued_now = False
    with processing_lock:
        if order_id not in active_orders:
            job = {
                'type': 'link_id',
                'order_id': order_id,
                'params': {} 
            }
            job_queue.put(job)
            active_orders.add(order_id)
            queued_now = True

    def generate():
        q = subscribe_log(order_id)
        
        # Initial status
        if queued_now:
            q_size = job_queue.qsize()
            if q_size > 1: # Someone else is being processed (since we are in queue) or just added
                # Actually qsize includes us. If qsize=1, it means we are next (or current if worker picks up fast)
                # Let's say: "อยู่ในคิวลำดับที่..." is hard to protect accurately without complex logic
                # Just say "Queued"
                q.put(f"STATUS:เข้าคิวตรวจสอบ... (ลำดับรอ: {q_size})")
            else:
                 q.put("STATUS:กำลังเริ่มทำงาน...")
        else:
             # Already active, just listening
             q.put("STATUS:กำลังเชื่อมต่อกับงานเดิม...")

        try:
            while True:
                msg = q.get()
                yield f"data: {msg}\n\n"
                
                # Close stream conditions
                if msg.startswith("SUCCESS") or "ERROR" in msg:
                    # Give client a moment to process before cutting stream? 
                    # SSE clients usually don't close unless server closes or JS calls close()
                    # We can break here to close request
                    pass 
        finally:
            remove_subscription(order_id, q)
            
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/stream_phase2/<int:order_id>')
@login_required
def stream_phase2(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    queued_now = False
    with processing_lock:
        if order_id not in active_orders:
            job = {
                'type': 'phase2',
                'order_id': order_id
            }
            job_queue.put(job)
            active_orders.add(order_id)
            queued_now = True

    def generate():
        q = subscribe_log(order_id)
        
        if queued_now:
            q.put(f"STATUS:เข้าคิว Phase 2... (ลำดับรอ: {job_queue.qsize()})")
        
        try:
            while True:
                msg = q.get()
                yield f"data: {msg}\n\n"
        finally:
            remove_subscription(order_id, q)
            
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# ============== DATABASE INITIALIZATION ==============

def init_db():
    """Initialize database and create admin user if not exists"""
    with app.app_context():
        db.create_all()
        
        # Create admin user if not exists
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@lineranger.store', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Admin user created: admin / admin123')


if __name__ == '__main__':
    # Create folders if not exist
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(Config.PRODUCTS_FOLDER, exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Start Worker Thread
    threading.Thread(target=worker_thread, daemon=True).start()

    
    # Run app
    app.run(debug=True, port=5000)
