import os
import json
import csv
import io
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from datetime import datetime, time, timedelta

# --- KONFIGURASI ---
app = Flask(__name__)
app.secret_key = 'kunci_rahasia_elok_alfa_sangat_aman'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///elokpos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'static/uploads'
PROOF_FOLDER = 'static/uploads/proofs'
EXPENSE_FOLDER = 'static/uploads/expenses'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROOF_FOLDER'] = PROOF_FOLDER
app.config['EXPENSE_FOLDER'] = EXPENSE_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROOF_FOLDER, exist_ok=True)
os.makedirs(EXPENSE_FOLDER, exist_ok=True)

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
    variant = db.Column(db.String(50), nullable=True) 
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    stock = db.Column(db.Integer, default=0)
    cost_price = db.Column(db.Integer, nullable=False)
    sell_price = db.Column(db.Integer, nullable=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    no_faktur = db.Column(db.String(50), unique=True, nullable=False)
    tanggal = db.Column(db.DateTime, default=datetime.now)
    customer_name = db.Column(db.String(100), default='Umum') 
    
    # --- UPGRADE: DISKON & CATATAN ---
    discount = db.Column(db.Integer, default=0)
    note = db.Column(db.String(200), nullable=True)
    
    total_bayar = db.Column(db.Integer, nullable=False) # Total Akhir (Setelah Diskon)
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

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tanggal = db.Column(db.DateTime, default=datetime.now)
    kategori = db.Column(db.String(50), nullable=False)
    deskripsi = db.Column(db.String(200), nullable=False) 
    jumlah = db.Column(db.Integer, nullable=False)
    bukti_foto = db.Column(db.String(255), nullable=True)

# --- SECURITY & HELPER ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.context_processor
def inject_store_info():
    try: return dict(info=StoreInfo.query.first())
    except: return dict(info=None)

# --- ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id; session['username'] = user.username
            flash('Login berhasil!', 'success'); return redirect(url_for('index'))
        else: flash('Username/Password salah!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); flash('Logout berhasil.', 'success'); return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    today = datetime.now().date()
    start = datetime.combine(today, time.min); end = datetime.combine(today, time.max)
    omset = db.session.query(func.sum(Transaction.total_bayar)).filter(Transaction.tanggal >= start, Transaction.tanggal <= end).scalar() or 0
    expense = db.session.query(func.sum(Expense.jumlah)).filter(Expense.tanggal >= start, Expense.tanggal <= end).scalar() or 0
    
    chart_lbl = []; chart_dat = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        s = datetime.combine(d, time.min); e = datetime.combine(d, time.max)
        val = db.session.query(func.sum(Transaction.total_bayar)).filter(Transaction.tanggal >= s, Transaction.tanggal <= e).scalar() or 0
        chart_lbl.append(d.strftime("%a %d")); chart_dat.append(val)

    return render_template('layout.html', content_only=True, omset=omset, expense=expense, profit=omset-expense, 
                           trx_count=Transaction.query.filter(Transaction.tanggal >= start, Transaction.tanggal <= end).count(),
                           low_stock=Product.query.filter(Product.stock < 5).count(), total_products=Product.query.count(),
                           chart_labels=json.dumps(chart_lbl), chart_data=json.dumps(chart_dat))

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def settings():
    info = StoreInfo.query.first()
    if request.method == 'POST':
        file = request.files.get('logo'); fname = None
        if file and allowed_file(file.filename):
            fname = secure_filename(file.filename); file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        if info is None: db.session.add(StoreInfo(nama_toko=request.form['nama_toko'], alamat=request.form['alamat'], telepon=request.form['telepon'], logo_filename=fname))
        else:
            info.nama_toko = request.form['nama_toko']; info.alamat = request.form['alamat']; info.telepon = request.form['telepon']
            if fname: info.logo_filename = fname
        db.session.commit(); flash('Disimpan!', 'success'); return redirect(url_for('settings'))
    return render_template('settings.html')

@app.route('/admin/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST': db.session.add(Category(name=request.form['name'])); db.session.commit(); flash('Kategori ditambah!', 'success'); return redirect(url_for('categories'))
    return render_template('categories.html', categories=Category.query.all())

@app.route('/admin/categories/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_category(id):
    cat = Category.query.get_or_404(id)
    if request.method == 'POST': cat.name = request.form['name']; db.session.commit(); return redirect(url_for('categories'))
    return render_template('edit_category.html', cat=cat)

@app.route('/admin/categories/delete/<int:id>')
@login_required
def delete_category(id):
    if Product.query.filter_by(category_id=id).first(): flash('Gagal! Ada produk.', 'error')
    else: db.session.delete(Category.query.get_or_404(id)); db.session.commit(); flash('Dihapus!', 'warning')
    return redirect(url_for('categories'))

@app.route('/admin/products')
@login_required
def products():
    f = request.args.get('filter')
    prods = Product.query.filter(Product.stock < 5).all() if f == 'low' else Product.query.all()
    return render_template('products.html', products=prods, filter_type=f)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        db.session.add(Product(code=request.form['code'], name=request.form['name'], variant=request.form['variant'], category_id=request.form['category_id'], cost_price=request.form['cost_price'], sell_price=request.form['sell_price'], stock=request.form['stock']))
        db.session.commit(); flash('Produk ditambah!', 'success'); return redirect(url_for('products'))
    return render_template('product_form.html', categories=Category.query.all(), action="Tambah")

@app.route('/admin/products/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    p = Product.query.get_or_404(id)
    if request.method == 'POST':
        p.code=request.form['code']; p.name=request.form['name']; p.variant=request.form['variant']; p.category_id=request.form['category_id']; p.cost_price=request.form['cost_price']; p.sell_price=request.form['sell_price']; p.stock=request.form['stock']
        db.session.commit(); flash('Produk diupdate!', 'success'); return redirect(url_for('products'))
    return render_template('product_form.html', categories=Category.query.all(), product=p, action="Edit")

@app.route('/admin/products/delete/<int:id>')
@login_required
def delete_product(id): db.session.delete(Product.query.get_or_404(id)); db.session.commit(); flash('Dihapus!', 'warning'); return redirect(url_for('products'))

@app.route('/admin/expenses', methods=['GET', 'POST'])
@login_required
def expenses():
    if request.method == 'POST':
        tgl = datetime.strptime(request.form['tanggal'], '%Y-%m-%d') if request.form['tanggal'] else datetime.now()
        file = request.files.get('bukti_foto'); fn = None
        if file and allowed_file(file.filename):
            fn = f"EXP_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file.filename.rsplit('.',1)[1].lower()}"; file.save(os.path.join(app.config['EXPENSE_FOLDER'], fn))
        db.session.add(Expense(deskripsi=request.form['deskripsi'], jumlah=int(request.form['jumlah']), kategori=request.form['kategori'], tanggal=tgl, bukti_foto=fn))
        db.session.commit(); flash('Tercatat!', 'success'); return redirect(url_for('expenses'))
    return render_template('expenses.html', expenses=Expense.query.order_by(Expense.tanggal.desc()).all(), total=db.session.query(func.sum(Expense.jumlah)).scalar() or 0)

@app.route('/admin/expenses/delete/<int:id>')
@login_required
def delete_expense(id):
    e = Expense.query.get_or_404(id)
    if e.bukti_foto: 
        try: os.remove(os.path.join(app.config['EXPENSE_FOLDER'], e.bukti_foto))
        except: pass
    db.session.delete(e); db.session.commit(); flash('Dihapus!', 'warning'); return redirect(url_for('expenses'))

@app.route('/kasir')
@login_required
def kasir(): return render_template('kasir.html', products=Product.query.filter(Product.stock > 0).all())

@app.route('/kasir/proses_bayar', methods=['POST'])
@login_required
def proses_bayar():
    try:
        keranjang = json.loads(request.form['keranjang'])
        total_bayar = int(request.form['total_bayar'])
        # UPGRADE: Terima Diskon & Note
        discount = int(request.form.get('discount', 0))
        note = request.form.get('note', '')
        
        payment_method = request.form['payment_method']
        customer = request.form.get('customer_name', '').strip() or 'Umum'
        
        if payment_method == 'Transfer': uang = total_bayar; kembalian = 0
        else: uang = int(request.form['uang_diterima']); kembalian = int(request.form['kembalian'])

        fn = None
        if payment_method == 'Transfer':
            f = request.files.get('proof_image')
            if f and allowed_file(f.filename):
                fn = f"PROOF_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{f.filename.rsplit('.',1)[1].lower()}"; f.save(os.path.join(app.config['PROOF_FOLDER'], fn))
            else: return json.dumps({'status': 'error', 'message': 'Upload bukti!'}), 400

        no = "TRX-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        trx = Transaction(no_faktur=no, tanggal=datetime.now(), customer_name=customer, total_bayar=total_bayar, 
                          uang_diterima=uang, kembalian=kembalian, payment_method=payment_method, proof_image=fn,
                          discount=discount, note=note) # Simpan Diskon & Note
        db.session.add(trx); db.session.flush()

        for i in keranjang:
            p = Product.query.get(i['id'])
            if p:
                if p.stock < int(i['qty']): return json.dumps({'status': 'error', 'message': f'Stok {p.name} kurang!'}), 400
                p.stock -= int(i['qty'])
                nm = p.name + (f" ({p.variant})" if p.variant else "")
                db.session.add(TransactionDetail(transaction_id=trx.id, product_name=nm, qty=int(i['qty']), price=int(i['price']), subtotal=int(i['qty'])*int(i['price'])))
        
        db.session.commit(); return json.dumps({'status': 'success', 'no_faktur': no})
    except Exception as e: db.session.rollback(); return json.dumps({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/history')
@login_required
def history(): return render_template('history.html', transaksi=Transaction.query.order_by(Transaction.tanggal.desc()).all())

@app.route('/admin/history/delete/<int:id>')
@login_required
def delete_history(id):
    t = Transaction.query.get_or_404(id)
    try:
        if t.proof_image: 
            try: os.remove(os.path.join(app.config['PROOF_FOLDER'], t.proof_image))
            except: pass
        for d in t.details: db.session.delete(d)
        db.session.delete(t); db.session.commit(); flash('Dihapus!', 'warning')
    except Exception as e: db.session.rollback(); flash(f'Gagal: {str(e)}', 'error')
    return redirect(url_for('history'))

@app.route('/admin/history/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_history(id):
    t = Transaction.query.get_or_404(id)
    if request.method == 'POST':
        t.tanggal = datetime.strptime(request.form['tanggal'], '%Y-%m-%dT%H:%M')
        t.uang_diterima = int(request.form['uang_diterima'])
        t.kembalian = t.uang_diterima - t.total_bayar
        db.session.commit(); flash('Updated!', 'success'); return redirect(url_for('history'))
    return render_template('edit_history.html', trx=t)

@app.route('/admin/export/transactions')
@login_required
def export_transactions():
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(['No Faktur', 'Tanggal', 'Jam', 'Pelanggan', 'Metode', 'Diskon', 'Total Bayar', 'Catatan', 'Detail'])
    for t in Transaction.query.order_by(Transaction.tanggal.desc()).all():
        dt = t.tanggal + timedelta(hours=7)
        items = "; ".join([f"{d.product_name} ({d.qty})" for d in t.details])
        w.writerow([t.no_faktur, dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M'), t.customer_name, t.payment_method, t.discount, t.total_bayar, t.note, items])
    out.seek(0)
    return Response(out, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=Laporan_WIB.csv"})

@app.route('/struk/<no_faktur>')
@login_required
def struk(no_faktur): return render_template('invoice.html', trx=Transaction.query.filter_by(no_faktur=no_faktur).first_or_404())

with app.app_context():
    try: db.create_all()
    except OperationalError: pass
    try:
        if not User.query.first():
            db.session.add(User(username='admin', password=generate_password_hash('admin123', method='pbkdf2:sha256'), role='admin')); db.session.commit()
    except (IntegrityError, OperationalError): db.session.rollback()

if __name__ == '__main__': app.run(debug=True, host='0.0.0.0')