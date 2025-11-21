import os
import json
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from datetime import datetime, time

# --- KONFIGURASI ---
app = Flask(__name__)
app.secret_key = 'kunci_rahasia_elok_alfa_sangat_aman'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///elokpos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'static/uploads'
PROOF_FOLDER = 'static/uploads/proofs'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROOF_FOLDER'] = PROOF_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROOF_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

db = SQLAlchemy(app)

# --- MODEL DATABASE ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='admin')

class StoreInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama_toko = db.Column(db.String(100), nullable=False)
    alamat = db.Column(db.Text, nullable=True)
    telepon = db.Column(db.String(20), nullable=True)
    logo_filename = db.Column(db.String(100), nullable=True)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    stock = db.Column(db.Integer, default=0)
    cost_price = db.Column(db.Integer, nullable=False)
    sell_price = db.Column(db.Integer, nullable=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    no_faktur = db.Column(db.String(50), unique=True, nullable=False)
    tanggal = db.Column(db.DateTime, default=datetime.now)
    customer_name = db.Column(db.String(100), default='Umum') 
    total_bayar = db.Column(db.Integer, nullable=False)
    uang_diterima = db.Column(db.Integer, nullable=False)
    kembalian = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(20), default='Cash')
    proof_image = db.Column(db.String(255), nullable=True)
    details = db.relationship('TransactionDetail', backref='transaction', lazy=True)

class TransactionDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Integer, nullable=False)

# --- SECURITY & HELPER ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.context_processor
def inject_store_info():
    # Tambahkan try-except untuk mencegah error saat tabel belum siap
    try:
        return dict(info=StoreInfo.query.first())
    except:
        return dict(info=None)

# --- ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Login berhasil!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Username atau Password salah!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    today = datetime.now().date()
    start_of_day = datetime.combine(today, time.min)
    end_of_day = datetime.combine(today, time.max)
    omset_today = db.session.query(func.sum(Transaction.total_bayar)).filter(Transaction.tanggal >= start_of_day).filter(Transaction.tanggal <= end_of_day).scalar() or 0
    trx_count = Transaction.query.filter(Transaction.tanggal >= start_of_day).filter(Transaction.tanggal <= end_of_day).count()
    low_stock = Product.query.filter(Product.stock < 5).count()
    total_products = Product.query.count()
    return render_template('layout.html', content_only=True, omset=omset_today, trx_count=trx_count, low_stock=low_stock, total_products=total_products)

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def settings():
    info = StoreInfo.query.first()
    if request.method == 'POST':
        nama_toko = request.form['nama_toko']
        alamat = request.form['alamat']
        telepon = request.form['telepon']
        file = request.files.get('logo')
        filename = info.logo_filename if info else None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        if info is None:
            db.session.add(StoreInfo(nama_toko=nama_toko, alamat=alamat, telepon=telepon, logo_filename=filename))
        else:
            info.nama_toko = nama_toko; info.alamat = alamat; info.telepon = telepon
            if filename: info.logo_filename = filename
        db.session.commit()
        flash('Pengaturan disimpan!', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html')

@app.route('/admin/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        db.session.add(Category(name=request.form['name']))
        db.session.commit()
        flash('Kategori ditambah!', 'success')
        return redirect(url_for('categories'))
    return render_template('categories.html', categories=Category.query.all())

@app.route('/admin/categories/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_category(id):
    cat = Category.query.get_or_404(id)
    if request.method == 'POST':
        cat.name = request.form['name']
        db.session.commit()
        return redirect(url_for('categories'))
    return render_template('edit_category.html', cat=cat)

@app.route('/admin/categories/delete/<int:id>')
@login_required
def delete_category(id):
    if Product.query.filter_by(category_id=id).first():
        flash('Gagal! Ada produk di kategori ini.', 'error')
    else:
        db.session.delete(Category.query.get_or_404(id))
        db.session.commit()
        flash('Kategori dihapus!', 'warning')
    return redirect(url_for('categories'))

@app.route('/admin/products')
@login_required
def products():
    return render_template('products.html', products=Product.query.all())

@app.route('/admin/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        db.session.add(Product(code=request.form['code'], name=request.form['name'], category_id=request.form['category_id'], cost_price=request.form['cost_price'], sell_price=request.form['sell_price'], stock=request.form['stock']))
        db.session.commit()
        flash('Produk ditambah!', 'success')
        return redirect(url_for('products'))
    return render_template('product_form.html', categories=Category.query.all(), action="Tambah")

@app.route('/admin/products/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    prod = Product.query.get_or_404(id)
    if request.method == 'POST':
        prod.code=request.form['code']; prod.name=request.form['name']; prod.category_id=request.form['category_id']
        prod.cost_price=request.form['cost_price']; prod.sell_price=request.form['sell_price']; prod.stock=request.form['stock']
        db.session.commit()
        flash('Produk diupdate!', 'success')
        return redirect(url_for('products'))
    return render_template('product_form.html', categories=Category.query.all(), product=prod, action="Edit")

@app.route('/admin/products/delete/<int:id>')
@login_required
def delete_product(id):
    db.session.delete(Product.query.get_or_404(id))
    db.session.commit()
    flash('Produk dihapus!', 'warning')
    return redirect(url_for('products'))

@app.route('/kasir')
@login_required
def kasir():
    products = Product.query.filter(Product.stock > 0).all()
    return render_template('kasir.html', products=products)

@app.route('/kasir/proses_bayar', methods=['POST'])
@login_required
def proses_bayar():
    try:
        keranjang = json.loads(request.form['keranjang'])
        total_bayar = int(request.form['total_bayar'])
        payment_method = request.form['payment_method']
        customer_name = request.form.get('customer_name', '').strip() or 'Umum'

        if payment_method == 'Transfer':
            uang_diterima = total_bayar
            kembalian = 0
        else:
            uang_diterima = int(request.form['uang_diterima'])
            kembalian = int(request.form['kembalian'])

        proof_filename = None
        if payment_method == 'Transfer':
            file = request.files.get('proof_image')
            if file and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                proof_filename = f"PROOF_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
                file.save(os.path.join(app.config['PROOF_FOLDER'], proof_filename))
            else:
                return json.dumps({'status': 'error', 'message': 'Wajib upload bukti transfer!'}), 400

        no_faktur = "TRX-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        new_trx = Transaction(
            no_faktur=no_faktur,
            tanggal=datetime.now(),
            customer_name=customer_name,
            total_bayar=total_bayar,
            uang_diterima=uang_diterima,
            kembalian=kembalian,
            payment_method=payment_method,
            proof_image=proof_filename
        )
        db.session.add(new_trx)
        db.session.flush()

        for item in keranjang:
            product = Product.query.get(item['id'])
            if product:
                if product.stock < int(item['qty']):
                    return json.dumps({'status': 'error', 'message': f'Stok {product.name} kurang!'}), 400
                product.stock -= int(item['qty'])
                db.session.add(TransactionDetail(transaction_id=new_trx.id, product_name=product.name, qty=int(item['qty']), price=int(item['price']), subtotal=int(item['qty']) * int(item['price'])))
        
        db.session.commit()
        return json.dumps({'status': 'success', 'no_faktur': no_faktur})

    except Exception as e:
        db.session.rollback()
        return json.dumps({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/history')
@login_required
def history():
    transaksi = Transaction.query.order_by(Transaction.tanggal.desc()).all()
    return render_template('history.html', transaksi=transaksi)

@app.route('/admin/history/delete/<int:id>')
@login_required
def delete_history(id):
    trx = Transaction.query.get_or_404(id)
    try:
        for detail in trx.details:
            product = Product.query.filter_by(name=detail.product_name).first()
            if product: product.stock += detail.qty
        if trx.proof_image:
            try: os.remove(os.path.join(app.config['PROOF_FOLDER'], trx.proof_image))
            except: pass
        for detail in trx.details: db.session.delete(detail)
        db.session.delete(trx)
        db.session.commit()
        flash('Transaksi dihapus.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal: {str(e)}', 'error')
    return redirect(url_for('history'))

@app.route('/admin/history/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_history(id):
    trx = Transaction.query.get_or_404(id)
    if request.method == 'POST':
        trx.tanggal = datetime.strptime(request.form['tanggal'], '%Y-%m-%dT%H:%M')
        trx.uang_diterima = int(request.form['uang_diterima'])
        trx.kembalian = trx.uang_diterima - trx.total_bayar
        db.session.commit()
        flash('Data diupdate!', 'success')
        return redirect(url_for('history'))
    return render_template('edit_history.html', trx=trx)

@app.route('/struk/<no_faktur>')
@login_required
def struk(no_faktur):
    trx = Transaction.query.filter_by(no_faktur=no_faktur).first_or_404()
    return render_template('invoice.html', trx=trx)

# --- INISIALISASI DB (DIPINDAH KELUAR MAIN) ---
# Ini akan dijalankan otomatis oleh Gunicorn saat aplikasi start
with app.app_context():
    db.create_all()
    if not User.query.first():
        print("--- Membuat User Admin Default ---")
        hashed_pw = generate_password_hash('admin123', method='pbkdf2:sha256')
        db.session.add(User(username='admin', password=hashed_pw, role='admin'))
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')