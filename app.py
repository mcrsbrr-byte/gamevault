import os
import sqlite3
import json
import hashlib
import smtplib
import datetime
import re
import csv
import io
import time
import uuid
import random
import string
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import (Flask, session, request, redirect, url_for,
                   render_template, jsonify, send_file, flash, g, abort, make_response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'gamevault-secret-2024-xk9q')

# ─── Config ────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DB_PATH      = os.path.join(BASE_DIR, 'gamevault.db')
UPLOAD_COVER = os.path.join(BASE_DIR, 'static', 'uploads', 'covers')
UPLOAD_FILES = os.path.join(BASE_DIR, 'static', 'uploads', 'files')
UPLOAD_AVATARS = os.path.join(BASE_DIR, 'static', 'uploads', 'avatars')
UPLOAD_BANNERS = os.path.join(BASE_DIR, 'static', 'uploads', 'banners')
ADMIN_EMAIL  = 'mcr.sbrr@gmail.com'
SMTP_HOST    = 'smtp.gmail.com'
SMTP_PORT    = 587
SMTP_USER    = 'mcr.sbrr@gmail.com'
SMTP_PASS    = os.environ.get('SMTP_PASS', '')  # Set via env or .env

ALLOWED_IMG  = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_GAME = {'iso', 'rom', 'pkg', 'cia', 'xbla', 'zip', 'rar', '7z', 'bin', 'cue', 'nds', 'gba', 'gcm', 'wbfs'}

# Rate limiting store (in-memory)
_rate_store = {}

for d in [UPLOAD_COVER, UPLOAD_FILES, UPLOAD_AVATARS, UPLOAD_BANNERS]:
    os.makedirs(d, exist_ok=True)


# ─── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        avatar TEXT DEFAULT '',
        is_admin INTEGER DEFAULT 0,
        points INTEGER DEFAULT 0,
        newsletter INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        last_login TEXT
    );

    CREATE TABLE IF NOT EXISTS consoles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        banner TEXT DEFAULT '',
        icon TEXT DEFAULT '',
        sort_order INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        console_id INTEGER NOT NULL,
        category_id INTEGER,
        cover TEXT DEFAULT '',
        images TEXT DEFAULT '[]',
        description TEXT DEFAULT '',
        price REAL DEFAULT 9.90,
        original_price REAL DEFAULT 0,
        file_path TEXT DEFAULT '',
        file_format TEXT DEFAULT 'ISO',
        file_size TEXT DEFAULT '',
        language TEXT DEFAULT 'PT-BR',
        region TEXT DEFAULT 'NTSC',
        compatibility TEXT DEFAULT '',
        rating REAL DEFAULT 0,
        rating_count INTEGER DEFAULT 0,
        sales_count INTEGER DEFAULT 0,
        download_count INTEGER DEFAULT 0,
        is_featured INTEGER DEFAULT 0,
        is_new INTEGER DEFAULT 1,
        is_free INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        stock INTEGER DEFAULT 9999,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(console_id) REFERENCES consoles(id),
        FOREIGN KEY(category_id) REFERENCES categories(id)
    );

    CREATE TABLE IF NOT EXISTS bundles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        price REAL NOT NULL,
        cover TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS bundle_games (
        bundle_id INTEGER,
        game_id INTEGER,
        PRIMARY KEY(bundle_id, game_id),
        FOREIGN KEY(bundle_id) REFERENCES bundles(id),
        FOREIGN KEY(game_id) REFERENCES games(id)
    );

    CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        discount_type TEXT DEFAULT 'percent',
        discount_value REAL NOT NULL,
        min_value REAL DEFAULT 0,
        max_uses INTEGER DEFAULT 100,
        used_count INTEGER DEFAULT 0,
        expires_at TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        transaction_id TEXT UNIQUE NOT NULL,
        total REAL NOT NULL,
        coupon_id INTEGER,
        discount_amount REAL DEFAULT 0,
        payment_method TEXT DEFAULT 'pix',
        payment_status TEXT DEFAULT 'pending',
        payment_id TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        paid_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        game_id INTEGER,
        bundle_id INTEGER,
        title TEXT NOT NULL,
        price REAL NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id)
    );

    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        rating INTEGER NOT NULL,
        comment TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(game_id) REFERENCES games(id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        UNIQUE(game_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS wishlist (
        user_id INTEGER,
        game_id INTEGER,
        PRIMARY KEY(user_id, game_id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(game_id) REFERENCES games(id)
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        type TEXT DEFAULT 'info',
        read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS newsletter (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS banners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        subtitle TEXT DEFAULT '',
        image TEXT DEFAULT '',
        link TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS site_settings (
        key TEXT PRIMARY KEY,
        value TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS emulators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        banner TEXT DEFAULT '',
        description TEXT DEFAULT '',
        sort_order INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1
    );

    CREATE INDEX IF NOT EXISTS idx_games_console ON games(console_id);
    CREATE INDEX IF NOT EXISTS idx_games_category ON games(category_id);
    CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
    CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
    CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
    """)
    db.commit()
    return db


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[áàãâä]', 'a', text)
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[íìîï]', 'i', text)
    text = re.sub(r'[óòõôö]', 'o', text)
    text = re.sub(r'[úùûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text


def allowed_img(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMG

def allowed_game(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_GAME

def save_image(file, folder, max_size=(800, 600)):
    if not file or not allowed_img(file.filename):
        return None
    ext = file.filename.rsplit('.', 1)[1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(folder, fname)
    try:
        img = Image.open(file)
        img.thumbnail(max_size, Image.LANCZOS)
        img.save(path, optimize=True, quality=85)
    except Exception:
        file.seek(0)
        file.save(path)
    return fname


# ─── Auth helpers ──────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        db = get_db()
        user = db.execute("SELECT is_admin FROM users WHERE id=?", (session['user_id'],)).fetchone()
        if not user or not user['is_admin']:
            abort(403)
        return f(*args, **kwargs)
    return decorated

def current_user():
    if 'user_id' not in session:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()

def rate_limit(key, limit=5, window=60):
    now = time.time()
    if key not in _rate_store:
        _rate_store[key] = []
    _rate_store[key] = [t for t in _rate_store[key] if now - t < window]
    if len(_rate_store[key]) >= limit:
        return False
    _rate_store[key].append(now)
    return True


# ─── Email ─────────────────────────────────────────────────────────────────────
def send_email(to, subject, body_html, body_text=''):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f'GameVault <{SMTP_USER}>'
        msg['To'] = to
        if body_text:
            msg.attach(MIMEText(body_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.ehlo()
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, to, msg.as_string())
        return True
    except Exception as e:
        app.logger.error(f"Email error: {e}")
        return False


# ─── Helpers for templates ─────────────────────────────────────────────────────
def get_setting(key, default=''):
    try:
        db = get_db()
        row = db.execute("SELECT value FROM site_settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default
    except:
        return default

def save_setting(key, value):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO site_settings(key,value) VALUES(?,?)", (key, value))
    db.commit()

@app.context_processor
def inject_globals():
    db = get_db()
    consoles  = db.execute("SELECT * FROM consoles WHERE active=1 ORDER BY sort_order").fetchall()
    emulators = db.execute("SELECT * FROM emulators WHERE active=1 ORDER BY sort_order").fetchall()
    user = current_user()
    notif_count = 0
    cart = session.get('cart', [])
    if user:
        notif_count = db.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0",
            (user['id'],)
        ).fetchone()[0]
    # Site settings
    whatsapp_number = get_setting('whatsapp_number', '5500000000000')
    whatsapp_active = get_setting('whatsapp_active', '1')
    return dict(
        consoles=consoles,
        emulators=emulators,
        current_user=user,
        notif_count=notif_count,
        cart_count=len(cart),
        now=datetime.datetime.now(),
        whatsapp_number=whatsapp_number,
        whatsapp_active=whatsapp_active,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    db = get_db()
    featured   = db.execute("SELECT g.*, c.name as console_name, c.slug as console_slug FROM games g JOIN consoles c ON g.console_id=c.id WHERE g.is_featured=1 AND g.is_active=1 ORDER BY g.sales_count DESC LIMIT 8").fetchall()
    bestsellers= db.execute("SELECT g.*, c.name as console_name, c.slug as console_slug FROM games g JOIN consoles c ON g.console_id=c.id WHERE g.is_active=1 ORDER BY g.sales_count DESC LIMIT 12").fetchall()
    newest     = db.execute("SELECT g.*, c.name as console_name, c.slug as console_slug FROM games g JOIN consoles c ON g.console_id=c.id WHERE g.is_active=1 ORDER BY g.created_at DESC LIMIT 12").fetchall()
    free_games = db.execute("SELECT g.*, c.name as console_name, c.slug as console_slug FROM games g JOIN consoles c ON g.console_id=c.id WHERE g.is_free=1 AND g.is_active=1 LIMIT 6").fetchall()
    banners    = db.execute("SELECT * FROM banners WHERE active=1 ORDER BY sort_order").fetchall()
    bundles    = db.execute("SELECT * FROM bundles WHERE active=1 LIMIT 4").fetchall()
    stats = {
        'games': db.execute("SELECT COUNT(*) FROM games WHERE is_active=1").fetchone()[0],
        'users': db.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0],
        'orders': db.execute("SELECT COUNT(*) FROM orders WHERE payment_status='approved'").fetchone()[0],
    }
    return render_template('index.html',
        featured=featured, bestsellers=bestsellers, newest=newest,
        free_games=free_games, banners=banners, bundles=bundles, stats=stats)


@app.route('/consoles')
def consoles_page():
    db = get_db()
    consoles = db.execute("""
        SELECT c.*, COUNT(g.id) as game_count
        FROM consoles c LEFT JOIN games g ON g.console_id=c.id AND g.is_active=1
        WHERE c.active=1 GROUP BY c.id ORDER BY c.sort_order
    """).fetchall()
    return render_template('consoles.html', consoles=consoles)


@app.route('/console/<slug>')
def console_page(slug):
    db = get_db()
    console = db.execute("SELECT * FROM consoles WHERE slug=? AND active=1", (slug,)).fetchone()
    if not console:
        abort(404)
    categories = db.execute("""
        SELECT cat.* FROM categories cat
        JOIN games g ON g.category_id=cat.id
        WHERE g.console_id=? AND g.is_active=1
        GROUP BY cat.id
    """, (console['id'],)).fetchall()
    cat_filter  = request.args.get('cat', '')
    sort        = request.args.get('sort', 'bestseller')
    search      = request.args.get('q', '')
    page        = max(1, int(request.args.get('page', 1)))
    per_page    = 24

    q = "SELECT g.*, c2.name as console_name FROM games g JOIN consoles c2 ON g.console_id=c2.id WHERE g.console_id=? AND g.is_active=1"
    params = [console['id']]
    if cat_filter:
        q += " AND g.category_id=(SELECT id FROM categories WHERE slug=?)"
        params.append(cat_filter)
    if search:
        q += " AND g.title LIKE ?"
        params.append(f'%{search}%')
    sort_map = {'bestseller':'g.sales_count DESC','newest':'g.created_at DESC','az':'g.title ASC','price_asc':'g.price ASC','price_desc':'g.price DESC'}
    q += f" ORDER BY {sort_map.get(sort,'g.sales_count DESC')}"
    all_games = db.execute(q, params).fetchall()
    total = len(all_games)
    games = all_games[(page-1)*per_page:page*per_page]
    pages = (total + per_page - 1) // per_page
    return render_template('console.html',
        console=console, games=games, categories=categories,
        cat_filter=cat_filter, sort=sort, search=search,
        page=page, pages=pages, total=total)



@app.route('/emuladores')
def emulators_page():
    db = get_db()
    emulators = db.execute("SELECT * FROM emulators WHERE active=1 ORDER BY sort_order").fetchall()
    return render_template('emulators.html', emulators=emulators)


@app.route('/emulador/<slug>')
def emulator_page(slug):
    db = get_db()
    emulator = db.execute("SELECT * FROM emulators WHERE slug=? AND active=1", (slug,)).fetchone()
    if not emulator:
        abort(404)
    return render_template('emulator_detail.html', emulator=emulator)


@app.route('/jogo/<slug>')
def game_detail(slug):
    db = get_db()
    game = db.execute("""
        SELECT g.*, c.name as console_name, c.slug as console_slug, cat.name as category_name
        FROM games g JOIN consoles c ON g.console_id=c.id
        LEFT JOIN categories cat ON g.category_id=cat.id
        WHERE g.slug=? AND g.is_active=1
    """, (slug,)).fetchone()
    if not game:
        abort(404)
    reviews = db.execute("""
        SELECT r.*, u.name as user_name, u.avatar FROM reviews r
        JOIN users u ON r.user_id=u.id
        WHERE r.game_id=? ORDER BY r.created_at DESC
    """, (game['id'],)).fetchall()
    related = db.execute("""
        SELECT g.*, c.name as console_name FROM games g JOIN consoles c ON g.console_id=c.id
        WHERE g.console_id=? AND g.id!=? AND g.is_active=1 ORDER BY RANDOM() LIMIT 6
    """, (game['console_id'], game['id'])).fetchall()
    images = json.loads(game['images']) if game['images'] else []
    in_wishlist = False
    user_review = None
    user = current_user()
    if user:
        wl = db.execute("SELECT 1 FROM wishlist WHERE user_id=? AND game_id=?", (user['id'], game['id'])).fetchone()
        in_wishlist = bool(wl)
        user_review = db.execute("SELECT * FROM reviews WHERE user_id=? AND game_id=?", (user['id'], game['id'])).fetchone()
    purchased = False
    if user:
        p = db.execute("""
            SELECT 1 FROM order_items oi JOIN orders o ON oi.order_id=o.id
            WHERE o.user_id=? AND oi.game_id=? AND o.payment_status='approved'
        """, (user['id'], game['id'])).fetchone()
        purchased = bool(p)
    return render_template('game_detail.html',
        game=game, reviews=reviews, related=related,
        images=images, in_wishlist=in_wishlist,
        user_review=user_review, purchased=purchased)


@app.route('/buscar')
def search():
    db = get_db()
    q = request.args.get('q', '').strip()
    console_slug = request.args.get('console', '')
    cat_slug     = request.args.get('cat', '')
    sort         = request.args.get('sort', 'bestseller')
    page         = max(1, int(request.args.get('page', 1)))
    per_page     = 24
    query = "SELECT g.*, c.name as console_name, c.slug as console_slug FROM games g JOIN consoles c ON g.console_id=c.id WHERE g.is_active=1"
    params = []
    if q:
        query += " AND g.title LIKE ?"
        params.append(f'%{q}%')
    if console_slug:
        query += " AND c.slug=?"
        params.append(console_slug)
    if cat_slug:
        query += " AND g.category_id=(SELECT id FROM categories WHERE slug=?)"
        params.append(cat_slug)
    sort_map = {'bestseller':'g.sales_count DESC','newest':'g.created_at DESC','az':'g.title ASC','price_asc':'g.price ASC'}
    query += f" ORDER BY {sort_map.get(sort,'g.sales_count DESC')}"
    all_games = db.execute(query, params).fetchall()
    total = len(all_games)
    games = all_games[(page-1)*per_page:page*per_page]
    pages = (total+per_page-1)//per_page
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template('search.html',
        games=games, q=q, total=total, page=page, pages=pages,
        console_slug=console_slug, cat_slug=cat_slug, sort=sort,
        categories=categories)


@app.route('/jogos')
def all_games():
    return redirect(url_for('search'))


@app.route('/mais-vendidos')
def bestsellers():
    db = get_db()
    games = db.execute("""
        SELECT g.*, c.name as console_name, c.slug as console_slug FROM games g
        JOIN consoles c ON g.console_id=c.id
        WHERE g.is_active=1 ORDER BY g.sales_count DESC LIMIT 50
    """).fetchall()
    return render_template('listing.html', games=games, title='🏆 Mais Vendidos', subtitle='Os jogos mais amados da comunidade')


@app.route('/novidades')
def novidades():
    db = get_db()
    games = db.execute("""
        SELECT g.*, c.name as console_name, c.slug as console_slug FROM games g
        JOIN consoles c ON g.console_id=c.id
        WHERE g.is_active=1 ORDER BY g.created_at DESC LIMIT 50
    """).fetchall()
    return render_template('listing.html', games=games, title='🆕 Novidades', subtitle='Recém adicionados ao catálogo')


@app.route('/gratuitos')
def free_games():
    db = get_db()
    games = db.execute("""
        SELECT g.*, c.name as console_name, c.slug as console_slug FROM games g
        JOIN consoles c ON g.console_id=c.id
        WHERE g.is_free=1 AND g.is_active=1 ORDER BY g.title
    """).fetchall()
    return render_template('listing.html', games=games, title='🎁 Jogos Gratuitos', subtitle='Download sem custo')


@app.route('/bundle/<int:bid>')
def bundle_detail(bid):
    db = get_db()
    bundle = db.execute("SELECT * FROM bundles WHERE id=? AND active=1", (bid,)).fetchone()
    if not bundle:
        abort(404)
    games = db.execute("""
        SELECT g.*, c.name as console_name FROM games g JOIN consoles c ON g.console_id=c.id
        JOIN bundle_games bg ON bg.game_id=g.id WHERE bg.bundle_id=?
    """, (bid,)).fetchall()
    return render_template('bundle_detail.html', bundle=bundle, games=games)


# ══════════════════════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email','').lower().strip()
        password = request.form.get('password','')
        ip = request.remote_addr
        key = f"login_{ip}"
        if not rate_limit(key, limit=10, window=60):
            flash('Muitas tentativas. Aguarde 1 minuto.', 'error')
            return render_template('auth/login.html')
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.permanent = True
            session['user_id'] = user['id']
            db.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user['id'],))
            db.commit()
            nxt = request.args.get('next', url_for('index'))
            return redirect(nxt)
        flash('Email ou senha incorretos.', 'error')
    return render_template('auth/login.html')


@app.route('/registro', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name  = request.form.get('name','').strip()
        email = request.form.get('email','').lower().strip()
        pwd   = request.form.get('password','')
        pwd2  = request.form.get('password2','')
        newsletter = 1 if request.form.get('newsletter') else 0
        if not name or not email or not pwd:
            flash('Preencha todos os campos.', 'error')
            return render_template('auth/register.html')
        if pwd != pwd2:
            flash('Senhas não conferem.', 'error')
            return render_template('auth/register.html')
        if len(pwd) < 6:
            flash('Senha mínima: 6 caracteres.', 'error')
            return render_template('auth/register.html')
        db = get_db()
        if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            flash('Este e-mail já está cadastrado.', 'error')
            return render_template('auth/register.html')
        ph = generate_password_hash(pwd)
        db.execute("INSERT INTO users(name,email,password_hash,newsletter) VALUES(?,?,?,?)", (name,email,ph,newsletter))
        uid = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()['id']
        # Welcome notification
        db.execute("INSERT INTO notifications(user_id,title,message,type) VALUES(?,?,?,?)",
            (uid, '🎮 Bem-vindo ao GameVault!', f'Olá {name}! Sua conta foi criada. Explore nosso catálogo!', 'success'))
        db.commit()
        # Welcome email (async-style, best effort)
        send_email(email, '🎮 Bem-vindo ao GameVault!',
            f'<h2>Olá {name}!</h2><p>Sua conta no <b>GameVault</b> foi criada com sucesso!</p>'
            f'<p>Explore centenas de jogos clássicos em <a href="/">GameVault</a>.</p>')
        # Notify admin
        send_email(ADMIN_EMAIL, f'[GameVault] Novo usuário: {name}',
            f'<p>Novo cadastro: <b>{name}</b> ({email})</p>')
        session['user_id'] = uid
        flash('Conta criada com sucesso! Bem-vindo ao GameVault!', 'success')
        return redirect(url_for('index'))
    return render_template('auth/register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ══════════════════════════════════════════════════════════════════════════════
#  CART & CHECKOUT
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/carrinho')
def cart():
    db = get_db()
    cart_items = session.get('cart', [])
    games = []
    total = 0
    for item in cart_items:
        if item.get('type') == 'game':
            g2 = db.execute("SELECT g.*, c.name as console_name FROM games g JOIN consoles c ON g.console_id=c.id WHERE g.id=?", (item['id'],)).fetchone()
            if g2:
                games.append({'item': dict(g2), 'type': 'game'})
                total += g2['price']
        elif item.get('type') == 'bundle':
            b = db.execute("SELECT * FROM bundles WHERE id=?", (item['id'],)).fetchone()
            if b:
                games.append({'item': dict(b), 'type': 'bundle'})
                total += b['price']
    return render_template('cart.html', cart_games=games, total=total)


@app.route('/carrinho/add', methods=['POST'])
def cart_add():
    data = request.get_json() or {}
    item_id   = int(data.get('id', 0))
    item_type = data.get('type', 'game')
    cart = session.get('cart', [])
    for c in cart:
        if c['id'] == item_id and c['type'] == item_type:
            return jsonify({'status':'already', 'count': len(cart)})
    cart.append({'id': item_id, 'type': item_type})
    session['cart'] = cart
    session.modified = True
    return jsonify({'status':'ok', 'count': len(cart)})


@app.route('/carrinho/remove', methods=['POST'])
def cart_remove():
    data    = request.get_json() or {}
    item_id = int(data.get('id', 0))
    item_type = data.get('type', 'game')
    cart = session.get('cart', [])
    cart = [c for c in cart if not (c['id']==item_id and c['type']==item_type)]
    session['cart'] = cart
    session.modified = True
    return jsonify({'status':'ok', 'count': len(cart)})


@app.route('/checkout', methods=['GET','POST'])
@login_required
def checkout():
    db   = get_db()
    user = current_user()
    cart = session.get('cart', [])
    if not cart:
        return redirect(url_for('cart'))

    items = []
    total = 0
    for c in cart:
        if c['type'] == 'game':
            g2 = db.execute("SELECT * FROM games WHERE id=? AND is_active=1", (c['id'],)).fetchone()
            if g2:
                items.append({'obj': g2, 'type': 'game', 'title': g2['title'], 'price': g2['price']})
                total += g2['price']
        elif c['type'] == 'bundle':
            b = db.execute("SELECT * FROM bundles WHERE id=? AND active=1", (c['id'],)).fetchone()
            if b:
                items.append({'obj': b, 'type': 'bundle', 'title': b['name'], 'price': b['price']})
                total += b['price']

    coupon_code    = request.form.get('coupon_code','').strip().upper()
    discount       = 0
    coupon_obj     = None
    coupon_error   = ''
    if coupon_code:
        coupon_obj = db.execute("""
            SELECT * FROM coupons WHERE code=? AND active=1
            AND (expires_at IS NULL OR expires_at > datetime('now'))
            AND used_count < max_uses
        """, (coupon_code,)).fetchone()
        if coupon_obj:
            if total < coupon_obj['min_value']:
                coupon_error = f"Valor mínimo: R$ {coupon_obj['min_value']:.2f}"
                coupon_obj = None
            else:
                if coupon_obj['discount_type'] == 'percent':
                    discount = round(total * coupon_obj['discount_value'] / 100, 2)
                else:
                    discount = min(coupon_obj['discount_value'], total)
        else:
            coupon_error = 'Cupom inválido ou expirado.'

    final_total = max(0, total - discount)

    if request.method == 'POST' and request.form.get('action') == 'pay':
        pay_method = request.form.get('payment_method', 'pix')
        txn = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        coupon_id = coupon_obj['id'] if coupon_obj else None
        db.execute("""
            INSERT INTO orders(user_id,transaction_id,total,coupon_id,discount_amount,payment_method,payment_status)
            VALUES(?,?,?,?,?,?,'pending')
        """, (user['id'], txn, final_total, coupon_id, discount, pay_method))
        order_id = db.execute("SELECT id FROM orders WHERE transaction_id=?", (txn,)).fetchone()['id']
        for it in items:
            gid = it['obj']['id'] if it['type']=='game' else None
            bid = it['obj']['id'] if it['type']=='bundle' else None
            db.execute("INSERT INTO order_items(order_id,game_id,bundle_id,title,price) VALUES(?,?,?,?,?)",
                (order_id, gid, bid, it['title'], it['price']))
        if coupon_obj:
            db.execute("UPDATE coupons SET used_count=used_count+1 WHERE id=?", (coupon_obj['id'],))
        db.commit()
        session['pending_order'] = txn
        return redirect(url_for('payment_page', txn=txn))

    return render_template('checkout.html', items=items, total=total,
        discount=discount, final_total=final_total,
        coupon_code=coupon_code, coupon_error=coupon_error, coupon_obj=coupon_obj)


@app.route('/pagamento/<txn>')
@login_required
def payment_page(txn):
    db = get_db()
    user = current_user()
    order = db.execute("SELECT * FROM orders WHERE transaction_id=? AND user_id=?", (txn, user['id'])).fetchone()
    if not order:
        abort(404)
    return render_template('payment.html', order=order)


@app.route('/pagamento/<txn>/confirmar', methods=['POST'])
@login_required
def payment_confirm(txn):
    """Cliente avisa que pagou — fica aguardando confirmacao manual do admin"""
    db   = get_db()
    user = current_user()
    order = db.execute("SELECT * FROM orders WHERE transaction_id=? AND user_id=?", (txn, user['id'])).fetchone()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    db.execute("UPDATE orders SET payment_status='waiting' WHERE id=?", (order['id'],))
    db.execute("INSERT INTO notifications(user_id,title,message,type) VALUES(?,?,?,?)",
        (user['id'], '⏳ Pagamento em análise!',
         f'Recebemos seu aviso do pedido #{txn[:8]}. Confirmaremos o PIX em breve e liberaremos seu acesso!', 'info'))
    db.commit()
    items = db.execute("SELECT * FROM order_items WHERE order_id=?", (order['id'],)).fetchall()
    items_str = ', '.join([it['title'] for it in items])
    send_email(ADMIN_EMAIL,
        f'[GameVault] ⚠️ PIX aguardando confirmação — R$ {order["total"]:.2f}',
        f'<h2>Novo pagamento para confirmar!</h2>'
        f'<p><b>Cliente:</b> {user["name"]} ({user["email"]})</p>'
        f'<p><b>Pedido:</b> #{txn}</p>'
        f'<p><b>Total:</b> R$ {order["total"]:.2f}</p>'
        f'<p><b>Jogos:</b> {items_str}</p>'
        f'<p>Verifique o PIX recebido e acesse o painel admin para aprovar o pedido.</p>'
        f'<p><a href="https://gamevaultstore.up.railway.app/admin/pedidos" style="background:#f5c518;color:#000;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold">✅ Ir para Painel Admin</a></p>')
    session.pop('cart', None)
    session.pop('pending_order', None)
    return jsonify({'status': 'waiting'})


@app.route('/admin/aprovar/<txn>', methods=['POST'])
@admin_required
def admin_approve_order(txn):
    """Admin aprova o pedido manualmente"""
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE transaction_id=?", (txn,)).fetchone()
    if not order:
        flash('Pedido não encontrado.', 'error')
        return redirect(url_for('admin_orders'))
    db.execute("UPDATE orders SET payment_status='approved', paid_at=datetime('now') WHERE id=?", (order['id'],))
    items = db.execute("SELECT * FROM order_items WHERE order_id=?", (order['id'],)).fetchall()
    for it in items:
        if it['game_id']:
            db.execute("UPDATE games SET sales_count=sales_count+1, download_count=download_count+1 WHERE id=?", (it['game_id'],))
    pts = int(order['total'])
    db.execute("UPDATE users SET points=points+? WHERE id=?", (pts, order['user_id']))
    db.execute("INSERT INTO notifications(user_id,title,message,type) VALUES(?,?,?,?)",
        (order['user_id'], '✅ Pagamento confirmado!',
         f'Seu pedido #{txn[:8]} foi aprovado! Acesse Meus Jogos para baixar.', 'success'))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE id=?", (order['user_id'],)).fetchone()
    items_str = ', '.join([it['title'] for it in items])
    send_email(user['email'], '✅ Pagamento confirmado — GameVault',
        f'<h2>Pagamento confirmado!</h2>'
        f'<p>Olá {user["name"]}! Seu pedido <b>#{txn[:8]}</b> foi aprovado.</p>'
        f'<p><b>Jogos:</b> {items_str}</p>'
        f'<p>Acesse sua conta para baixar os jogos.</p>'
        f'<p><a href="https://gamevaultstore.up.railway.app/minha-conta" style="background:#f5c518;color:#000;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold">📥 Baixar Jogos</a></p>')
    flash(f'Pedido #{txn[:8]} aprovado e cliente notificado!', 'success')
    return redirect(url_for('admin_orders'))


@app.route('/pagamento-aguardando')
@login_required
def payment_waiting():
    return render_template('payment_waiting.html')


# ══════════════════════════════════════════════════════════════════════════════
#  USER ACCOUNT
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/minha-conta')
@login_required
def my_account():
    db   = get_db()
    user = current_user()
    orders = db.execute("""
        SELECT o.*, COUNT(oi.id) as item_count FROM orders o
        LEFT JOIN order_items oi ON oi.order_id=o.id
        WHERE o.user_id=? GROUP BY o.id ORDER BY o.created_at DESC LIMIT 10
    """, (user['id'],)).fetchall()
    # Purchased games
    games = db.execute("""
        SELECT g.*, c.name as console_name, c.slug as console_slug, oi.id as oi_id
        FROM order_items oi JOIN orders o ON oi.order_id=o.id
        JOIN games g ON oi.game_id=g.id JOIN consoles c ON g.console_id=c.id
        WHERE o.user_id=? AND o.payment_status='approved' AND oi.game_id IS NOT NULL
        ORDER BY o.paid_at DESC
    """, (user['id'],)).fetchall()
    wishlist = db.execute("""
        SELECT g.*, c.name as console_name, c.slug as console_slug FROM wishlist w
        JOIN games g ON w.game_id=g.id JOIN consoles c ON g.console_id=c.id
        WHERE w.user_id=? ORDER BY g.title
    """, (user['id'],)).fetchall()
    notifications = db.execute("""
        SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 20
    """, (user['id'],)).fetchall()
    db.execute("UPDATE notifications SET read=1 WHERE user_id=?", (user['id'],))
    db.commit()
    return render_template('account/dashboard.html',
        user=user, orders=orders, games=games,
        wishlist=wishlist, notifications=notifications)


@app.route('/minha-conta/pedido/<int:oid>')
@login_required
def order_detail(oid):
    db = get_db()
    user = current_user()
    order = db.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (oid, user['id'])).fetchone()
    if not order:
        abort(404)
    items = db.execute("""
        SELECT oi.*, g.slug as game_slug, g.cover as game_cover FROM order_items oi
        LEFT JOIN games g ON oi.game_id=g.id WHERE oi.order_id=?
    """, (oid,)).fetchall()
    return render_template('account/order_detail.html', order=order, items=items)


@app.route('/minha-conta/editar', methods=['GET','POST'])
@login_required
def edit_profile():
    db   = get_db()
    user = current_user()
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        pwd  = request.form.get('password','')
        pwd2 = request.form.get('password2','')
        newsletter = 1 if request.form.get('newsletter') else 0
        avatar_file = request.files.get('avatar')
        avatar = user['avatar']
        if avatar_file and avatar_file.filename:
            fname = save_image(avatar_file, UPLOAD_AVATARS, (200,200))
            if fname:
                avatar = fname
        updates = ['name=?','newsletter=?','avatar=?']
        vals = [name, newsletter, avatar]
        if pwd:
            if pwd != pwd2:
                flash('Senhas não conferem.','error')
                return render_template('account/edit_profile.html', user=user)
            if len(pwd) < 6:
                flash('Senha mínima: 6 caracteres.','error')
                return render_template('account/edit_profile.html', user=user)
            updates.append('password_hash=?')
            vals.append(generate_password_hash(pwd))
        vals.append(user['id'])
        db.execute(f"UPDATE users SET {','.join(updates)} WHERE id=?", vals)
        db.commit()
        flash('Perfil atualizado!','success')
        return redirect(url_for('my_account'))
    return render_template('account/edit_profile.html', user=user)


@app.route('/baixar/<int:game_id>')
@login_required
def download_game(game_id):
    db   = get_db()
    user = current_user()
    purchased = db.execute("""
        SELECT 1 FROM order_items oi JOIN orders o ON oi.order_id=o.id
        WHERE o.user_id=? AND oi.game_id=? AND o.payment_status='approved'
    """, (user['id'], game_id)).fetchone()
    game = db.execute("SELECT * FROM games WHERE id=? AND (is_free=1 OR ?)", (game_id, bool(purchased))).fetchone()
    if not game:
        flash('Você não tem acesso a este arquivo.','error')
        return redirect(url_for('my_account'))
    if not game['file_path']:
        flash('Arquivo ainda não disponível.','error')
        return redirect(url_for('my_account'))
    file_path = os.path.join(UPLOAD_FILES, game['file_path'])
    if not os.path.exists(file_path):
        flash('Arquivo não encontrado no servidor.','error')
        return redirect(url_for('my_account'))
    db.execute("UPDATE games SET download_count=download_count+1 WHERE id=?", (game_id,))
    db.commit()
    return send_file(file_path, as_attachment=True, download_name=game['file_path'])


@app.route('/wishlist/toggle', methods=['POST'])
@login_required
def wishlist_toggle():
    db      = get_db()
    user    = current_user()
    game_id = int(request.get_json().get('game_id', 0))
    existing = db.execute("SELECT 1 FROM wishlist WHERE user_id=? AND game_id=?", (user['id'], game_id)).fetchone()
    if existing:
        db.execute("DELETE FROM wishlist WHERE user_id=? AND game_id=?", (user['id'], game_id))
        db.commit()
        return jsonify({'status': 'removed'})
    else:
        db.execute("INSERT INTO wishlist(user_id,game_id) VALUES(?,?)", (user['id'], game_id))
        db.commit()
        return jsonify({'status': 'added'})


@app.route('/review', methods=['POST'])
@login_required
def add_review():
    db      = get_db()
    user    = current_user()
    game_id = int(request.form.get('game_id', 0))
    rating  = int(request.form.get('rating', 5))
    comment = request.form.get('comment','').strip()
    purchased = db.execute("""
        SELECT 1 FROM order_items oi JOIN orders o ON oi.order_id=o.id
        WHERE o.user_id=? AND oi.game_id=? AND o.payment_status='approved'
    """, (user['id'], game_id)).fetchone()
    game = db.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not purchased and not game['is_free']:
        flash('Você precisa comprar o jogo para avaliar.','error')
        return redirect(url_for('game_detail', slug=game['slug']))
    try:
        db.execute("INSERT INTO reviews(game_id,user_id,rating,comment) VALUES(?,?,?,?)",
            (game_id, user['id'], rating, comment))
        avg = db.execute("SELECT AVG(rating), COUNT(*) FROM reviews WHERE game_id=?", (game_id,)).fetchone()
        db.execute("UPDATE games SET rating=?, rating_count=? WHERE id=?", (round(avg[0],1), avg[1], game_id))
        db.commit()
        flash('Avaliação enviada!','success')
    except:
        flash('Você já avaliou este jogo.','error')
    return redirect(url_for('game_detail', slug=game['slug']))


# ══════════════════════════════════════════════════════════════════════════════
#  NEWSLETTER
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/newsletter', methods=['POST'])
def newsletter_subscribe():
    email = request.form.get('email','').lower().strip()
    if not email or '@' not in email:
        return jsonify({'error': 'Email inválido'}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO newsletter(email) VALUES(?)", (email,))
        db.commit()
        send_email(email, '📧 Inscrição confirmada — GameVault',
            '<h2>Você está na nossa lista!</h2><p>Fique de olho: você receberá novidades, promoções e lançamentos em primeira mão.</p>')
        return jsonify({'status': 'ok'})
    except:
        return jsonify({'status': 'already'})


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin')
@admin_required
def admin_index():
    db = get_db()
    stats = {
        'total_games':   db.execute("SELECT COUNT(*) FROM games").fetchone()[0],
        'total_users':   db.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0],
        'total_orders':  db.execute("SELECT COUNT(*) FROM orders WHERE payment_status='approved'").fetchone()[0],
        'total_revenue': db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE payment_status='approved'").fetchone()[0],
        'pending_orders':db.execute("SELECT COUNT(*) FROM orders WHERE payment_status='pending'").fetchone()[0],
    }
    # Sales chart data (last 30 days)
    chart_data = db.execute("""
        SELECT DATE(paid_at) as day, COUNT(*) as cnt, SUM(total) as rev
        FROM orders WHERE payment_status='approved' AND paid_at >= DATE('now','-30 days')
        GROUP BY DATE(paid_at) ORDER BY day
    """).fetchall()
    recent_orders = db.execute("""
        SELECT o.*, u.name as user_name, u.email as user_email FROM orders o
        JOIN users u ON o.user_id=u.id ORDER BY o.created_at DESC LIMIT 15
    """).fetchall()
    top_games = db.execute("""
        SELECT g.title, g.sales_count, c.name as console_name FROM games g
        JOIN consoles c ON g.console_id=c.id ORDER BY g.sales_count DESC LIMIT 10
    """).fetchall()
    return render_template('admin/index.html',
        stats=stats, chart_data=list(chart_data),
        recent_orders=recent_orders, top_games=top_games)


@app.route('/admin/jogos')
@admin_required
def admin_games():
    db = get_db()
    q  = request.args.get('q','')
    console_id = request.args.get('console','')
    page = max(1, int(request.args.get('page',1)))
    per_page = 30
    query = "SELECT g.*, c.name as console_name FROM games g JOIN consoles c ON g.console_id=c.id WHERE 1=1"
    params = []
    if q:
        query += " AND g.title LIKE ?"
        params.append(f'%{q}%')
    if console_id:
        query += " AND g.console_id=?"
        params.append(console_id)
    query += " ORDER BY g.title"
    all_games = db.execute(query, params).fetchall()
    total = len(all_games)
    games = all_games[(page-1)*per_page:page*per_page]
    consoles = db.execute("SELECT * FROM consoles ORDER BY name").fetchall()
    return render_template('admin/games.html', games=games, consoles=consoles,
        q=q, console_id=console_id, page=page,
        pages=(total+per_page-1)//per_page, total=total)


@app.route('/admin/jogos/novo', methods=['GET','POST'])
@admin_required
def admin_game_new():
    db = get_db()
    consoles   = db.execute("SELECT * FROM consoles ORDER BY name").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    if request.method == 'POST':
        title       = request.form.get('title','').strip()
        console_id  = int(request.form.get('console_id',0))
        category_id = request.form.get('category_id') or None
        price       = float(request.form.get('price',9.90))
        orig_price  = float(request.form.get('original_price',0))
        fmt         = request.form.get('file_format','ISO')
        size        = request.form.get('file_size','')
        lang        = request.form.get('language','PT-BR')
        region      = request.form.get('region','NTSC')
        compat      = request.form.get('compatibility','')
        desc        = request.form.get('description','')
        is_free     = 1 if request.form.get('is_free') else 0
        is_featured = 1 if request.form.get('is_featured') else 0
        # Cover
        cover_file = request.files.get('cover')
        cover = save_image(cover_file, UPLOAD_COVER, (400,560)) or ''
        # Game file
        game_file = request.files.get('game_file')
        game_fname = ''
        if game_file and game_file.filename and allowed_game(game_file.filename):
            game_fname = secure_filename(f"{uuid.uuid4().hex}_{game_file.filename}")
            game_file.save(os.path.join(UPLOAD_FILES, game_fname))
        # Extra images
        extras = []
        for f in request.files.getlist('images'):
            if f and f.filename:
                fn = save_image(f, UPLOAD_COVER, (800,600))
                if fn: extras.append(fn)
        sl = slugify(title)
        # ensure unique slug
        existing = db.execute("SELECT id FROM games WHERE slug=?", (sl,)).fetchone()
        if existing:
            sl = sl + '-' + uuid.uuid4().hex[:4]
        db.execute("""
            INSERT INTO games(title,slug,console_id,category_id,price,original_price,
            file_format,file_size,language,region,compatibility,description,cover,images,
            file_path,is_free,is_featured,is_new)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        """, (title, sl, console_id, category_id, price, orig_price,
              fmt, size, lang, region, compat, desc, cover, json.dumps(extras),
              game_fname, is_free, is_featured))
        gid = db.execute("SELECT id FROM games WHERE slug=?", (sl,)).fetchone()['id']
        db.commit()
        # Notify all users about new game
        users = db.execute("SELECT id FROM users WHERE is_admin=0").fetchall()
        for u in users:
            db.execute("INSERT INTO notifications(user_id,title,message,type) VALUES(?,?,?,?)",
                (u['id'], '🆕 Novo jogo disponível!', f'"{title}" acabou de ser adicionado ao catálogo!', 'info'))
        db.commit()
        flash(f'Jogo "{title}" adicionado!','success')
        return redirect(url_for('admin_games'))
    return render_template('admin/game_form.html', game=None, consoles=consoles, categories=categories)


@app.route('/admin/jogos/<int:gid>/editar', methods=['GET','POST'])
@admin_required
def admin_game_edit(gid):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id=?", (gid,)).fetchone()
    if not game:
        abort(404)
    consoles   = db.execute("SELECT * FROM consoles ORDER BY name").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    if request.method == 'POST':
        title       = request.form.get('title','').strip()
        console_id  = int(request.form.get('console_id',0))
        category_id = request.form.get('category_id') or None
        price       = float(request.form.get('price',9.90))
        orig_price  = float(request.form.get('original_price',0))
        fmt         = request.form.get('file_format','ISO')
        size        = request.form.get('file_size','')
        lang        = request.form.get('language','PT-BR')
        region      = request.form.get('region','NTSC')
        compat      = request.form.get('compatibility','')
        desc        = request.form.get('description','')
        is_free     = 1 if request.form.get('is_free') else 0
        is_featured = 1 if request.form.get('is_featured') else 0
        is_active   = 1 if request.form.get('is_active') else 0
        cover = game['cover']
        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            fn = save_image(cover_file, UPLOAD_COVER, (400,560))
            if fn: cover = fn
        game_fname = game['file_path']
        game_file = request.files.get('game_file')
        if game_file and game_file.filename and allowed_game(game_file.filename):
            game_fname = secure_filename(f"{uuid.uuid4().hex}_{game_file.filename}")
            game_file.save(os.path.join(UPLOAD_FILES, game_fname))
        images = json.loads(game['images']) if game['images'] else []
        for f in request.files.getlist('images'):
            if f and f.filename:
                fn = save_image(f, UPLOAD_COVER, (800,600))
                if fn: images.append(fn)
        db.execute("""
            UPDATE games SET title=?,console_id=?,category_id=?,price=?,original_price=?,
            file_format=?,file_size=?,language=?,region=?,compatibility=?,description=?,
            cover=?,images=?,file_path=?,is_free=?,is_featured=?,is_active=? WHERE id=?
        """, (title,console_id,category_id,price,orig_price,fmt,size,lang,region,compat,
              desc,cover,json.dumps(images),game_fname,is_free,is_featured,is_active,gid))
        db.commit()
        flash('Jogo atualizado!','success')
        return redirect(url_for('admin_games'))
    images = json.loads(game['images']) if game['images'] else []
    return render_template('admin/game_form.html', game=game, consoles=consoles,
        categories=categories, images=images)


@app.route('/admin/jogos/<int:gid>/deletar', methods=['POST'])
@admin_required
def admin_game_delete(gid):
    db = get_db()
    db.execute("UPDATE games SET is_active=0 WHERE id=?", (gid,))
    db.commit()
    flash('Jogo desativado.','success')
    return redirect(url_for('admin_games'))


@app.route('/admin/consoles', methods=['GET','POST'])
@admin_required
def admin_consoles():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name','').strip()
            sl   = slugify(name)
            banner_file = request.files.get('banner')
            banner = save_image(banner_file, UPLOAD_BANNERS, (1200,400)) or ''
            db.execute("INSERT OR IGNORE INTO consoles(name,slug,banner) VALUES(?,?,?)", (name, sl, banner))
            db.commit()
            flash(f'Console "{name}" adicionado!','success')
        elif action == 'edit':
            cid  = int(request.form.get('cid',0))
            name = request.form.get('name','').strip()
            sort = int(request.form.get('sort_order',0))
            active = 1 if request.form.get('active') else 0
            banner_file = request.files.get('banner')
            c = db.execute("SELECT * FROM consoles WHERE id=?", (cid,)).fetchone()
            banner = c['banner'] if c else ''
            if banner_file and banner_file.filename:
                fn = save_image(banner_file, UPLOAD_BANNERS, (1200,400))
                if fn: banner = fn
            db.execute("UPDATE consoles SET name=?,sort_order=?,active=?,banner=? WHERE id=?",
                (name, sort, active, banner, cid))
            db.commit()
            flash('Console atualizado!','success')
    consoles = db.execute("""
        SELECT c.*, COUNT(g.id) as game_count FROM consoles c
        LEFT JOIN games g ON g.console_id=c.id AND g.is_active=1
        GROUP BY c.id ORDER BY c.sort_order
    """).fetchall()
    return render_template('admin/consoles.html', consoles=consoles)


@app.route('/admin/cupons', methods=['GET','POST'])
@admin_required
def admin_coupons():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            code  = request.form.get('code','').strip().upper()
            dtype = request.form.get('discount_type','percent')
            dval  = float(request.form.get('discount_value',10))
            min_v = float(request.form.get('min_value',0))
            max_u = int(request.form.get('max_uses',100))
            exp   = request.form.get('expires_at') or None
            try:
                db.execute("INSERT INTO coupons(code,discount_type,discount_value,min_value,max_uses,expires_at) VALUES(?,?,?,?,?,?)",
                    (code,dtype,dval,min_v,max_u,exp))
                db.commit()
                flash(f'Cupom {code} criado!','success')
            except:
                flash('Código já existe.','error')
        elif action == 'toggle':
            cid = int(request.form.get('cid',0))
            db.execute("UPDATE coupons SET active=1-active WHERE id=?", (cid,))
            db.commit()
    coupons = db.execute("SELECT * FROM coupons ORDER BY created_at DESC").fetchall()
    return render_template('admin/coupons.html', coupons=coupons)


@app.route('/admin/usuarios')
@admin_required
def admin_users():
    db = get_db()
    q  = request.args.get('q','')
    query = "SELECT * FROM users WHERE 1=1"
    params = []
    if q:
        query += " AND (name LIKE ? OR email LIKE ?)"
        params.extend([f'%{q}%', f'%{q}%'])
    query += " ORDER BY created_at DESC"
    users = db.execute(query, params).fetchall()
    return render_template('admin/users.html', users=users, q=q)


@app.route('/admin/pedidos')
@admin_required
def admin_orders():
    db     = get_db()
    status = request.args.get('status','')
    page   = max(1, int(request.args.get('page',1)))
    per_page = 30
    q = "SELECT o.*, u.name as user_name FROM orders o JOIN users u ON o.user_id=u.id WHERE 1=1"
    params = []
    if status:
        q += " AND o.payment_status=?"
        params.append(status)
    q += " ORDER BY o.created_at DESC"
    all_orders = db.execute(q, params).fetchall()
    total = len(all_orders)
    orders = all_orders[(page-1)*per_page:page*per_page]
    return render_template('admin/orders.html', orders=orders, status=status,
        page=page, pages=(total+per_page-1)//per_page, total=total)


@app.route('/admin/banners', methods=['GET','POST'])
@admin_required
def admin_banners():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            title    = request.form.get('title','')
            subtitle = request.form.get('subtitle','')
            link     = request.form.get('link','')
            sort     = int(request.form.get('sort_order',0))
            img_file = request.files.get('image')
            img = save_image(img_file, UPLOAD_BANNERS, (1200,450)) or ''
            db.execute("INSERT INTO banners(title,subtitle,image,link,sort_order) VALUES(?,?,?,?,?)",
                (title,subtitle,img,link,sort))
            db.commit()
            flash('Banner adicionado!','success')
        elif action == 'delete':
            bid = int(request.form.get('bid',0))
            db.execute("DELETE FROM banners WHERE id=?", (bid,))
            db.commit()
    banners = db.execute("SELECT * FROM banners ORDER BY sort_order").fetchall()
    return render_template('admin/banners.html', banners=banners)


@app.route('/admin/configuracoes', methods=['GET','POST'])
@admin_required
def admin_settings():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'whatsapp':
            number = request.form.get('whatsapp_number','').strip().replace(' ','').replace('-','').replace('(','').replace(')','')
            active = '1' if request.form.get('whatsapp_active') else '0'
            save_setting('whatsapp_number', number)
            save_setting('whatsapp_active', active)
            flash('WhatsApp atualizado!', 'success')
        elif action == 'email_blast':
            subject  = request.form.get('subject','').strip()
            body     = request.form.get('body','').strip()
            target   = request.form.get('target', 'all')
            if not subject or not body:
                flash('Preencha assunto e mensagem.', 'error')
            else:
                # Get emails
                if target == 'newsletter':
                    emails_rows = db.execute("SELECT email FROM newsletter").fetchall()
                elif target == 'users':
                    emails_rows = db.execute("SELECT email FROM users WHERE is_admin=0 AND newsletter=1").fetchall()
                else:
                    # Both
                    emails_rows = db.execute("SELECT email FROM users WHERE is_admin=0").fetchall()
                    nl = db.execute("SELECT email FROM newsletter").fetchall()
                    all_emails = list(set([r['email'] for r in emails_rows] + [r['email'] for r in nl]))
                    emails_rows = [{'email': e} for e in all_emails]

                sent = 0
                failed = 0
                html_body = f"""
                <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a0a0f;color:#e8e8f0;padding:2rem;border-radius:12px">
                  <div style="text-align:center;margin-bottom:1.5rem">
                    <h1 style="font-size:1.5rem;color:#f5c518">🎮 GameVault</h1>
                  </div>
                  <h2 style="color:#f5c518;margin-bottom:1rem">{subject}</h2>
                  <div style="color:#a0a0b8;line-height:1.8;white-space:pre-line">{body}</div>
                  <hr style="border-color:#2a2a3a;margin:1.5rem 0">
                  <p style="font-size:0.8rem;color:#606078;text-align:center">
                    GameVault — <a href="https://gamevaultstore.up.railway.app" style="color:#f5c518">gamevaultstore.up.railway.app</a>
                  </p>
                </div>"""
                for row in emails_rows:
                    ok = send_email(row['email'], f'[GameVault] {subject}', html_body)
                    if ok: sent += 1
                    else: failed += 1
                flash(f'✅ Email enviado para {sent} destinatários! {f"({failed} falhas)" if failed else ""}', 'success')
    settings = {
        'whatsapp_number': get_setting('whatsapp_number', '5500000000000'),
        'whatsapp_active': get_setting('whatsapp_active', '1'),
    }
    # Count targets
    total_users = db.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0]
    newsletter_count = db.execute("SELECT COUNT(*) FROM newsletter").fetchone()[0]
    return render_template('admin/settings.html', settings=settings,
        total_users=total_users, newsletter_count=newsletter_count)


@app.route('/admin/notificar', methods=['GET','POST'])
@admin_required
def admin_notify():
    db = get_db()
    if request.method == 'POST':
        title   = request.form.get('title','')
        message = request.form.get('message','')
        send_mail = request.form.get('send_email')
        users = db.execute("SELECT * FROM users WHERE is_admin=0").fetchall()
        for u in users:
            db.execute("INSERT INTO notifications(user_id,title,message,type) VALUES(?,?,?,?)",
                (u['id'], title, message, 'promo'))
            if send_mail:
                send_email(u['email'], f'[GameVault] {title}',
                    f'<h2>{title}</h2><p>{message}</p>')
        db.commit()
        flash(f'Notificação enviada para {len(users)} usuários!','success')
    return render_template('admin/notify.html')


@app.route('/admin/relatorio')
@admin_required
def admin_report():
    db = get_db()
    orders = db.execute("""
        SELECT o.transaction_id, o.created_at, o.paid_at, o.total, o.payment_method,
               o.payment_status, u.name as user_name, u.email as user_email
        FROM orders o JOIN users u ON o.user_id=u.id
        ORDER BY o.created_at DESC
    """).fetchall()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(['Pedido','Data','Pago em','Total','Método','Status','Cliente','Email'])
    for o in orders:
        w.writerow([o['transaction_id'], o['created_at'], o['paid_at'] or '',
                    f"R$ {o['total']:.2f}", o['payment_method'], o['payment_status'],
                    o['user_name'], o['user_email']])
    output = make_response(si.getvalue())
    output.headers['Content-Disposition'] = 'attachment; filename=gamevault_pedidos.csv'
    output.headers['Content-type'] = 'text/csv; charset=utf-8-sig'
    return output


@app.route('/admin/emuladores', methods=['GET','POST'])
@admin_required
def admin_emulators():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name','').strip()
            desc = request.form.get('description','').strip()
            sl   = slugify(name)
            banner_file = request.files.get('banner')
            banner = save_image(banner_file, UPLOAD_BANNERS, (1200,400)) or ''
            try:
                db.execute("INSERT INTO emulators(name,slug,banner,description) VALUES(?,?,?,?)", (name,sl,banner,desc))
                db.commit()
                flash(f'Emulador "{name}" adicionado!','success')
            except:
                flash('Emulador já existe.','error')
        elif action == 'edit':
            eid    = int(request.form.get('eid',0))
            name   = request.form.get('name','').strip()
            desc   = request.form.get('description','').strip()
            sort   = int(request.form.get('sort_order',0))
            active = 1 if request.form.get('active') else 0
            banner_file = request.files.get('banner')
            e = db.execute("SELECT * FROM emulators WHERE id=?", (eid,)).fetchone()
            banner = e['banner'] if e else ''
            if banner_file and banner_file.filename:
                fn = save_image(banner_file, UPLOAD_BANNERS, (1200,400))
                if fn: banner = fn
            db.execute("UPDATE emulators SET name=?,description=?,sort_order=?,active=?,banner=? WHERE id=?",
                (name,desc,sort,active,banner,eid))
            db.commit()
            flash('Emulador atualizado!','success')
        elif action == 'delete':
            eid = int(request.form.get('eid',0))
            db.execute("DELETE FROM emulators WHERE id=?", (eid,))
            db.commit()
            flash('Emulador removido!','success')
    emulators = db.execute("SELECT * FROM emulators ORDER BY sort_order").fetchall()
    return render_template('admin/emulators.html', emulators=emulators)


@app.route('/admin/categorias', methods=['GET','POST'])
@admin_required
def admin_categories():
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        sl   = slugify(name)
        try:
            db.execute("INSERT INTO categories(name,slug) VALUES(?,?)", (name,sl))
            db.commit()
            flash(f'Categoria "{name}" criada!','success')
        except:
            flash('Categoria já existe.','error')
    cats = db.execute("SELECT cat.*, COUNT(g.id) as game_count FROM categories cat LEFT JOIN games g ON g.category_id=cat.id GROUP BY cat.id ORDER BY cat.name").fetchall()
    return render_template('admin/categories.html', categories=cats)


@app.route('/admin/bundles', methods=['GET','POST'])
@admin_required
def admin_bundles():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action','')
        if action == 'add':
            name  = request.form.get('name','')
            desc  = request.form.get('description','')
            price = float(request.form.get('price',29.90))
            game_ids = request.form.getlist('game_ids')
            cover_file = request.files.get('cover')
            cover = save_image(cover_file, UPLOAD_COVER, (400,300)) or ''
            db.execute("INSERT INTO bundles(name,description,price,cover) VALUES(?,?,?,?)", (name,desc,price,cover))
            bid = db.execute("SELECT id FROM bundles ORDER BY id DESC LIMIT 1").fetchone()['id']
            for gid in game_ids:
                db.execute("INSERT OR IGNORE INTO bundle_games(bundle_id,game_id) VALUES(?,?)", (bid,int(gid)))
            db.commit()
            flash('Bundle criado!','success')
        elif action == 'toggle':
            bid = int(request.form.get('bid',0))
            db.execute("UPDATE bundles SET active=1-active WHERE id=?", (bid,))
            db.commit()
    bundles = db.execute("SELECT b.*, COUNT(bg.game_id) as game_count FROM bundles b LEFT JOIN bundle_games bg ON bg.bundle_id=b.id GROUP BY b.id ORDER BY b.created_at DESC").fetchall()
    games = db.execute("SELECT id, title, console_id FROM games WHERE is_active=1 ORDER BY title").fetchall()
    return render_template('admin/bundles.html', bundles=bundles, games=games)


# ─── API endpoints ──────────────────────────────────────────────────────────
@app.route('/api/coupon/check', methods=['POST'])
def api_coupon_check():
    db   = get_db()
    code = (request.get_json() or {}).get('code','').strip().upper()
    total = float((request.get_json() or {}).get('total', 0))
    coupon = db.execute("""
        SELECT * FROM coupons WHERE code=? AND active=1
        AND (expires_at IS NULL OR expires_at > datetime('now'))
        AND used_count < max_uses
    """, (code,)).fetchone()
    if not coupon:
        return jsonify({'valid': False, 'message': 'Cupom inválido ou expirado.'})
    if total < coupon['min_value']:
        return jsonify({'valid': False, 'message': f"Valor mínimo: R$ {coupon['min_value']:.2f}"})
    if coupon['discount_type'] == 'percent':
        disc = round(total * coupon['discount_value'] / 100, 2)
        msg  = f"-{coupon['discount_value']}%"
    else:
        disc = min(coupon['discount_value'], total)
        msg  = f"-R$ {coupon['discount_value']:.2f}"
    return jsonify({'valid': True, 'discount': disc, 'message': msg, 'code': code})


@app.route('/api/notifications')
@login_required
def api_notifications():
    db   = get_db()
    user = current_user()
    notifs = db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (user['id'],)).fetchall()
    count  = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0", (user['id'],)).fetchone()[0]
    return jsonify({'notifications': [dict(n) for n in notifs], 'count': count})


# ─── Errors ──────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


# ─── Sitemap ─────────────────────────────────────────────────────────────────
@app.route('/sitemap.xml')
def sitemap():
    db = get_db()
    games   = db.execute("SELECT slug, created_at FROM games WHERE is_active=1").fetchall()
    consoles= db.execute("SELECT slug FROM consoles WHERE active=1").fetchall()
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    base = request.host_url.rstrip('/')
    for url in ['/', '/consoles', '/emuladores', '/mais-vendidos', '/novidades', '/gratuitos']:
        xml.append(f'<url><loc>{base}{url}</loc></url>')
    for c in consoles:
        xml.append(f'<url><loc>{base}/console/{c["slug"]}</loc></url>')
    for g in games:
        xml.append(f'<url><loc>{base}/jogo/{g["slug"]}</loc><lastmod>{g["created_at"][:10]}</lastmod></url>')
    xml.append('</urlset>')
    r = make_response('\n'.join(xml))
    r.headers['Content-Type'] = 'application/xml'
    return r


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("Inicializando banco de dados...")
    db = init_db()

    # ─── Seed initial data ───────────────────────────────────────────────────
    # Admin user
    existing_admin = db.execute("SELECT id FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone()
    if not existing_admin:
        ph = generate_password_hash('Admin@GameVault2024!')
        db.execute("INSERT INTO users(name,email,password_hash,is_admin) VALUES(?,?,?,1)",
            ('Administrador', ADMIN_EMAIL, ph))
        db.commit()
        print(f"✅ Admin criado: {ADMIN_EMAIL} / Admin@GameVault2024!")

    # Consoles
    consoles_data = [
        ('PlayStation 2',  'playstation-2',  1),
        ('PlayStation 3',  'playstation-3',  2),
        ('PlayStation Portable', 'psp',      3),
        ('Nintendo 3DS',   'nintendo-3ds',   4),
        ('Nintendo Wii',   'nintendo-wii',   5),
        ('Xbox',           'xbox',           6),
        ('Xbox 360',       'xbox-360',       7),
    ]
    for name, slug, order in consoles_data:
        db.execute("INSERT OR IGNORE INTO consoles(name,slug,sort_order) VALUES(?,?,?)", (name,slug,order))
    db.commit()

    # Categories
    cats = ['Ação','Aventura','RPG','Corrida','Esportes','Luta','Terror','FPS','Plataforma','Puzzle','Estratégia','Simulação']
    for cat in cats:
        db.execute("INSERT OR IGNORE INTO categories(name,slug) VALUES(?,?)", (cat, slugify(cat)))
    db.commit()

    # Seed games
    def get_cid(slug):
        r = db.execute("SELECT id FROM consoles WHERE slug=?", (slug,)).fetchone()
        return r['id'] if r else None

    def get_cat(name):
        r = db.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
        return r['id'] if r else None

    def add_game(title, console_slug, cat_name, price=9.90, orig=0, fmt='ISO', size='', lang='PT-BR', region='NTSC', featured=0):
        cid = get_cid(console_slug)
        cat = get_cat(cat_name)
        if not cid:
            return
        sl = slugify(title)
        existing = db.execute("SELECT id FROM games WHERE slug=? AND console_id=?", (sl, cid)).fetchone()
        if existing:
            return
        # ensure unique slug globally
        base_sl = sl
        suffix = 1
        while db.execute("SELECT id FROM games WHERE slug=?", (sl,)).fetchone():
            sl = base_sl + '-' + console_slug[:3] + (str(suffix) if suffix > 1 else '')
            suffix += 1
        try:
            db.execute("""
                INSERT INTO games(title,slug,console_id,category_id,price,original_price,
                file_format,file_size,language,region,is_featured,sales_count)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """, (title, sl, cid, cat, price, orig, fmt, size, lang, region, featured, random.randint(0,500)))
        except Exception:
            pass

    # ── Xbox 360 games ──────────────────────────────────────────────────────
    xbox360_games = [
        ("Grand Theft Auto V","Ação",14.90,9.90,"NTSC",1),
        ("Red Dead Redemption","Ação",14.90,9.90,"NTSC",1),
        ("The Elder Scrolls V: Skyrim","RPG",12.90,9.90,"NTSC",1),
        ("Fallout 3","RPG",9.90,0,"NTSC",0),
        ("Fallout: New Vegas","RPG",9.90,0,"NTSC",0),
        ("The Witcher 2: Assassins of Kings","RPG",12.90,9.90,"NTSC",0),
        ("Mass Effect","RPG",9.90,0,"NTSC",0),
        ("Mass Effect 2","RPG",9.90,0,"NTSC",1),
        ("Mass Effect 3","RPG",9.90,0,"NTSC",0),
        ("Halo 3","FPS",12.90,9.90,"NTSC",1),
        ("Halo 3: ODST","FPS",9.90,0,"NTSC",0),
        ("Halo: Reach","FPS",12.90,9.90,"NTSC",1),
        ("Halo 4","FPS",12.90,9.90,"NTSC",0),
        ("Gears of War","Ação",9.90,0,"NTSC",1),
        ("Gears of War 2","Ação",9.90,0,"NTSC",0),
        ("Gears of War 3","Ação",12.90,9.90,"NTSC",1),
        ("Call of Duty 4: Modern Warfare","FPS",9.90,0,"NTSC",0),
        ("Call of Duty: World at War","FPS",9.90,0,"NTSC",0),
        ("Call of Duty: Modern Warfare 2","FPS",14.90,9.90,"NTSC",1),
        ("Call of Duty: Black Ops","FPS",12.90,9.90,"NTSC",1),
        ("Call of Duty: Modern Warfare 3","FPS",12.90,9.90,"NTSC",0),
        ("Call of Duty: Black Ops II","FPS",12.90,9.90,"NTSC",1),
        ("Battlefield 3","FPS",9.90,0,"NTSC",0),
        ("Battlefield: Bad Company 2","FPS",9.90,0,"NTSC",0),
        ("Far Cry 3","Ação",12.90,9.90,"NTSC",1),
        ("Assassin's Creed","Ação",9.90,0,"NTSC",0),
        ("Assassin's Creed II","Ação",9.90,0,"NTSC",0),
        ("Assassin's Creed Brotherhood","Ação",9.90,0,"NTSC",0),
        ("Assassin's Creed Revelations","Ação",9.90,0,"NTSC",0),
        ("Assassin's Creed III","Ação",9.90,0,"NTSC",0),
        ("Batman: Arkham Asylum","Ação",9.90,0,"NTSC",0),
        ("Batman: Arkham City","Ação",12.90,9.90,"NTSC",1),
        ("BioShock","Ação",9.90,0,"NTSC",0),
        ("BioShock 2","Ação",9.90,0,"NTSC",0),
        ("BioShock Infinite","Ação",12.90,9.90,"NTSC",1),
        ("Minecraft: Xbox 360 Edition","Aventura",9.90,0,"NTSC",0),
        ("Portal 2","Puzzle",9.90,0,"NTSC",1),
        ("Left 4 Dead","FPS",9.90,0,"NTSC",0),
        ("Left 4 Dead 2","FPS",9.90,0,"NTSC",0),
        ("Dead Space","Terror",9.90,0,"NTSC",0),
        ("Dead Space 2","Terror",9.90,0,"NTSC",0),
        ("Resident Evil 5","Terror",9.90,0,"NTSC",0),
        ("Resident Evil 6","Terror",9.90,0,"NTSC",0),
        ("Dark Souls","RPG",12.90,9.90,"NTSC",1),
        ("Dark Souls II","RPG",12.90,9.90,"NTSC",0),
        ("Dragon Age: Origins","RPG",9.90,0,"NTSC",0),
        ("Final Fantasy XIII","RPG",9.90,0,"NTSC",0),
        ("Final Fantasy XIII-2","RPG",9.90,0,"NTSC",0),
        ("Lost Odyssey","RPG",9.90,0,"NTSC",0),
        ("Forza Motorsport 3","Corrida",9.90,0,"NTSC",0),
        ("Forza Motorsport 4","Corrida",9.90,0,"NTSC",0),
        ("Forza Horizon","Corrida",12.90,9.90,"NTSC",1),
        ("Need for Speed Most Wanted (2012)","Corrida",9.90,0,"NTSC",0),
        ("Need for Speed Hot Pursuit","Corrida",9.90,0,"NTSC",0),
        ("Burnout Paradise","Corrida",9.90,0,"NTSC",0),
        ("FIFA 14","Esportes",9.90,0,"NTSC",0),
        ("Pro Evolution Soccer 2013","Esportes",9.90,0,"NTSC",0),
        ("NBA 2K13","Esportes",9.90,0,"NTSC",0),
        ("Mortal Kombat (2011)","Luta",9.90,0,"NTSC",0),
        ("Street Fighter IV","Luta",9.90,0,"NTSC",0),
        ("Tekken 6","Luta",9.90,0,"NTSC",0),
        ("Saints Row: The Third","Ação",9.90,0,"NTSC",0),
        ("Sleeping Dogs","Ação",9.90,0,"NTSC",0),
        ("L.A. Noire","Ação",9.90,0,"NTSC",0),
        ("Max Payne 3","Ação",9.90,0,"NTSC",0),
        ("Metal Gear Rising: Revengeance","Ação",9.90,0,"NTSC",0),
        ("Hitman: Absolution","Ação",9.90,0,"NTSC",0),
        ("Dead Rising","Ação",9.90,0,"NTSC",0),
        ("Dead Rising 2","Ação",9.90,0,"NTSC",0),
        ("Fable II","RPG",9.90,0,"NTSC",0),
        ("Fable III","RPG",9.90,0,"NTSC",0),
        ("Bayonetta","Ação",9.90,0,"NTSC",0),
        ("Devil May Cry 4","Ação",9.90,0,"NTSC",0),
        ("Prototype","Ação",9.90,0,"NTSC",0),
        ("Prototype 2","Ação",9.90,0,"NTSC",0),
        ("Saints Row 2","Ação",9.90,0,"NTSC",0),
        ("The Orange Box","FPS",9.90,0,"NTSC",0),
        ("Skate 3","Esportes",9.90,0,"NTSC",0),
        ("Castle Crashers","Ação",9.90,0,"NTSC",0),
        ("Limbo","Puzzle",9.90,0,"NTSC",0),
        ("Spec Ops: The Line","Ação",9.90,0,"NTSC",0),
        ("Guitar Hero III: Legends of Rock","Simulação",9.90,0,"NTSC",0),
        ("Rock Band 3","Simulação",9.90,0,"NTSC",0),
        ("Tales of Vesperia","RPG",9.90,0,"NTSC",0),
        ("Dragon Age II","RPG",9.90,0,"NTSC",0),
        ("The Last Remnant","RPG",9.90,0,"NTSC",0),
        ("WWE 2K14","Luta",9.90,0,"NTSC",0),
        ("Soulcalibur IV","Luta",9.90,0,"NTSC",0),
    ]
    for title, cat, orig, price, region, feat in xbox360_games:
        add_game(title, 'xbox-360', cat, price, orig, 'ISO', '8.5 GB', 'PT-BR', region, feat)

    # ── PlayStation 3 ──────────────────────────────────────────────────────
    ps3_games = [
        ("The Last of Us","Ação",14.90,9.90,"NTSC",1),
        ("Grand Theft Auto V","Ação",14.90,9.90,"NTSC",1),
        ("Uncharted 2: Among Thieves","Ação",12.90,9.90,"NTSC",1),
        ("Uncharted 3: Drake's Deception","Ação",12.90,9.90,"NTSC",1),
        ("Uncharted: Drake's Fortune","Ação",9.90,0,"NTSC",0),
        ("God of War III","Ação",12.90,9.90,"NTSC",1),
        ("God of War: Ascension","Ação",9.90,0,"NTSC",0),
        ("Metal Gear Solid 4: Guns of the Patriots","Ação",12.90,9.90,"NTSC",1),
        ("Heavy Rain","Aventura",12.90,9.90,"NTSC",1),
        ("Beyond: Two Souls","Aventura",12.90,9.90,"NTSC",0),
        ("LittleBigPlanet","Plataforma",9.90,0,"NTSC",0),
        ("LittleBigPlanet 2","Plataforma",9.90,0,"NTSC",0),
        ("Gran Turismo 5","Corrida",9.90,0,"NTSC",1),
        ("Gran Turismo 6","Corrida",9.90,0,"NTSC",0),
        ("Killzone 2","FPS",9.90,0,"NTSC",0),
        ("Killzone 3","FPS",9.90,0,"NTSC",0),
        ("Infamous","Ação",9.90,0,"NTSC",0),
        ("Infamous 2","Ação",9.90,0,"NTSC",1),
        ("Batman: Arkham Asylum","Ação",9.90,0,"NTSC",0),
        ("Batman: Arkham City","Ação",12.90,9.90,"NTSC",0),
        ("Batman: Arkham Origins","Ação",9.90,0,"NTSC",0),
        ("Assassin's Creed IV: Black Flag","Ação",12.90,9.90,"NTSC",1),
        ("Call of Duty: Black Ops","FPS",9.90,0,"NTSC",0),
        ("Call of Duty: Black Ops II","FPS",12.90,9.90,"NTSC",1),
        ("Battlefield 3","FPS",9.90,0,"NTSC",0),
        ("Battlefield 4","FPS",9.90,0,"NTSC",0),
        ("Far Cry 3","Ação",12.90,9.90,"NTSC",1),
        ("Far Cry 4","Ação",12.90,9.90,"NTSC",0),
        ("BioShock Infinite","Ação",12.90,9.90,"NTSC",1),
        ("Dead Space","Terror",9.90,0,"NTSC",0),
        ("Dead Space 2","Terror",9.90,0,"NTSC",0),
        ("Dead Space 3","Terror",9.90,0,"NTSC",0),
        ("Resident Evil 5","Terror",9.90,0,"NTSC",0),
        ("Resident Evil 6","Terror",9.90,0,"NTSC",0),
        ("Dark Souls","RPG",12.90,9.90,"NTSC",1),
        ("Dark Souls II","RPG",12.90,9.90,"NTSC",0),
        ("Demon's Souls","RPG",12.90,9.90,"NTSC",1),
        ("The Elder Scrolls V: Skyrim","RPG",12.90,9.90,"NTSC",1),
        ("Fallout 3","RPG",9.90,0,"NTSC",0),
        ("Fallout: New Vegas","RPG",9.90,0,"NTSC",0),
        ("Mass Effect 2","RPG",9.90,0,"NTSC",0),
        ("Mass Effect 3","RPG",9.90,0,"NTSC",0),
        ("Final Fantasy XIII","RPG",9.90,0,"NTSC",0),
        ("Persona 5","RPG",14.90,9.90,"NTSC",1),
        ("Ni no Kuni: Wrath of the White Witch","RPG",12.90,9.90,"NTSC",1),
        ("Kingdom Hearts HD 1.5 Remix","RPG",12.90,9.90,"NTSC",0),
        ("GTA IV","Ação",9.90,0,"NTSC",0),
        ("Red Dead Redemption","Ação",14.90,9.90,"NTSC",1),
        ("Portal 2","Puzzle",9.90,0,"NTSC",1),
        ("Minecraft: PlayStation 3 Edition","Aventura",9.90,0,"NTSC",0),
        ("Tomb Raider (2013)","Ação",12.90,9.90,"NTSC",0),
        ("Sleeping Dogs","Ação",9.90,0,"NTSC",0),
        ("L.A. Noire","Ação",9.90,0,"NTSC",0),
        ("Max Payne 3","Ação",9.90,0,"NTSC",0),
        ("Saints Row IV","Ação",9.90,0,"NTSC",0),
        ("Skate 3","Esportes",9.90,0,"NTSC",0),
        ("FIFA 14","Esportes",9.90,0,"NTSC",0),
        ("Mortal Kombat (2011)","Luta",9.90,0,"NTSC",0),
        ("Street Fighter IV","Luta",9.90,0,"NTSC",0),
        ("Tekken 6","Luta",9.90,0,"NTSC",0),
        ("Bayonetta","Ação",9.90,0,"NTSC",0),
        ("Devil May Cry 4","Ação",9.90,0,"NTSC",0),
        ("Dragon Age: Origins","RPG",9.90,0,"NTSC",0),
        ("Resistance: Fall of Man","FPS",9.90,0,"NTSC",0),
        ("The Walking Dead: Season One","Aventura",9.90,0,"NTSC",0),
        ("Journey","Aventura",9.90,0,"NTSC",0),
        ("Limbo","Puzzle",9.90,0,"NTSC",0),
        ("Castle Crashers","Ação",9.90,0,"NTSC",0),
        ("Tales of Xillia","RPG",9.90,0,"NTSC",0),
        ("Darksiders","Ação",9.90,0,"NTSC",0),
        ("Darksiders II","Ação",9.90,0,"NTSC",0),
        ("The Orange Box","FPS",9.90,0,"NTSC",0),
        ("DmC: Devil May Cry","Ação",9.90,0,"NTSC",0),
        ("Crysis 2","FPS",9.90,0,"NTSC",0),
        ("Crysis 3","FPS",9.90,0,"NTSC",0),
    ]
    for title, cat, orig, price, region, feat in ps3_games:
        add_game(title, 'playstation-3', cat, price, orig, 'PKG', '18 GB', 'PT-BR', region, feat)

    # ── Nintendo Wii ────────────────────────────────────────────────────────
    wii_games = [
        ("Wii Sports","Esportes",9.90,0,"NTSC",1),
        ("Wii Sports Resort","Esportes",9.90,0,"NTSC",0),
        ("Mario Kart Wii","Corrida",12.90,9.90,"NTSC",1),
        ("Super Smash Bros. Brawl","Luta",12.90,9.90,"NTSC",1),
        ("Super Mario Galaxy","Plataforma",12.90,9.90,"NTSC",1),
        ("Super Mario Galaxy 2","Plataforma",12.90,9.90,"NTSC",1),
        ("New Super Mario Bros. Wii","Plataforma",9.90,0,"NTSC",0),
        ("The Legend of Zelda: Twilight Princess","Aventura",12.90,9.90,"NTSC",1),
        ("The Legend of Zelda: Skyward Sword","Aventura",12.90,9.90,"NTSC",1),
        ("Donkey Kong Country Returns","Plataforma",9.90,0,"NTSC",0),
        ("Kirby's Return to Dream Land","Plataforma",9.90,0,"NTSC",0),
        ("Mario Party 8","Simulação",9.90,0,"NTSC",0),
        ("Mario Party 9","Simulação",9.90,0,"NTSC",0),
        ("Animal Crossing: City Folk","Simulação",9.90,0,"NTSC",0),
        ("Metroid Prime 3: Corruption","Ação",9.90,0,"NTSC",0),
        ("Metroid Prime Trilogy","Ação",12.90,9.90,"NTSC",0),
        ("Kirby's Epic Yarn","Plataforma",9.90,0,"NTSC",0),
        ("Sonic Colors","Plataforma",9.90,0,"NTSC",0),
        ("Sonic Unleashed","Plataforma",9.90,0,"NTSC",0),
        ("Resident Evil 4: Wii Edition","Terror",9.90,0,"NTSC",1),
        ("Resident Evil: The Umbrella Chronicles","Terror",9.90,0,"NTSC",0),
        ("Call of Duty: Black Ops","FPS",9.90,0,"NTSC",0),
        ("GoldenEye 007","FPS",9.90,0,"NTSC",0),
        ("No More Heroes","Ação",9.90,0,"NTSC",0),
        ("No More Heroes 2: Desperate Struggle","Ação",9.90,0,"NTSC",0),
        ("The Last Story","RPG",9.90,0,"NTSC",1),
        ("Xenoblade Chronicles","RPG",12.90,9.90,"NTSC",1),
        ("Monster Hunter Tri","Ação",9.90,0,"NTSC",0),
        ("Dragon Ball Z: Budokai Tenkaichi 3","Luta",12.90,9.90,"NTSC",1),
        ("Naruto: Clash of Ninja Revolution","Luta",9.90,0,"NTSC",0),
        ("Punch-Out!!","Luta",9.90,0,"NTSC",0),
        ("Guitar Hero III: Legends of Rock","Simulação",9.90,0,"NTSC",0),
        ("Guitar Hero World Tour","Simulação",9.90,0,"NTSC",0),
        ("Rock Band","Simulação",9.90,0,"NTSC",0),
        ("Just Dance","Simulação",9.90,0,"NTSC",0),
        ("Just Dance 2","Simulação",9.90,0,"NTSC",0),
        ("Just Dance 3","Simulação",9.90,0,"NTSC",0),
        ("Wii Fit Plus","Esportes",9.90,0,"NTSC",0),
        ("Epic Mickey","Aventura",9.90,0,"NTSC",0),
        ("Lego Star Wars: The Complete Saga","Ação",9.90,0,"NTSC",0),
        ("Lego Batman: The Videogame","Ação",9.90,0,"NTSC",0),
        ("Lego Indiana Jones: The Original Adventures","Ação",9.90,0,"NTSC",0),
        ("Okami","Aventura",9.90,0,"NTSC",0),
        ("Little King's Story","Estratégia",9.90,0,"NTSC",0),
        ("MadWorld","Ação",9.90,0,"NTSC",0),
        ("Pandora's Tower","RPG",9.90,0,"NTSC",0),
        ("Muramasa: The Demon Blade","Ação",9.90,0,"NTSC",0),
        ("Rhythm Heaven Fever","Simulação",9.90,0,"NTSC",0),
        ("Tatsunoko vs. Capcom","Luta",9.90,0,"NTSC",0),
        ("Need for Speed: Carbon","Corrida",9.90,0,"NTSC",0),
        ("Mario & Sonic at the Olympic Games","Esportes",9.90,0,"NTSC",0),
        ("Super Paper Mario","RPG",9.90,0,"NTSC",0),
        ("Wario Land: Shake It!","Plataforma",9.90,0,"NTSC",0),
        ("Rayman Raving Rabbids","Ação",9.90,0,"NTSC",0),
        ("Pokémon Battle Revolution","Luta",9.90,0,"NTSC",0),
        ("SpongeBob's Boating Bash","Corrida",9.90,0,"NTSC",0),
    ]
    for title, cat, orig, price, region, feat in wii_games:
        add_game(title, 'nintendo-wii', cat, price, orig, 'WBFS', '4.3 GB', 'PT-BR', region, feat)

    # ── Xbox (original) ─────────────────────────────────────────────────────
    xbox_games = [
        ("Halo: Combat Evolved","FPS",12.90,9.90,"NTSC",1),
        ("Halo 2","FPS",12.90,9.90,"NTSC",1),
        ("Fable","RPG",9.90,0,"NTSC",0),
        ("Fable: The Lost Chapters","RPG",9.90,0,"NTSC",1),
        ("Star Wars: Knights of the Old Republic","RPG",12.90,9.90,"NTSC",1),
        ("Star Wars Knights of the Old Republic II: The Sith Lords","RPG",12.90,9.90,"NTSC",0),
        ("The Elder Scrolls III: Morrowind","RPG",9.90,0,"NTSC",0),
        ("Grand Theft Auto: San Andreas","Ação",12.90,9.90,"NTSC",1),
        ("Grand Theft Auto: Vice City","Ação",9.90,0,"NTSC",0),
        ("Grand Theft Auto III","Ação",9.90,0,"NTSC",0),
        ("Bully","Aventura",9.90,0,"NTSC",0),
        ("Ninja Gaiden","Ação",9.90,0,"NTSC",1),
        ("Ninja Gaiden Black","Ação",12.90,9.90,"NTSC",1),
        ("Forza Motorsport","Corrida",9.90,0,"NTSC",0),
        ("Burnout 3: Takedown","Corrida",9.90,0,"NTSC",1),
        ("Burnout Revenge","Corrida",9.90,0,"NTSC",0),
        ("Need for Speed Underground","Corrida",9.90,0,"NTSC",0),
        ("Need for Speed Underground 2","Corrida",9.90,0,"NTSC",0),
        ("Need for Speed Most Wanted","Corrida",12.90,9.90,"NTSC",1),
        ("Tom Clancy's Splinter Cell: Chaos Theory","Ação",9.90,0,"NTSC",1),
        ("Chronicles of Riddick: Escape from Butcher Bay","Ação",9.90,0,"NTSC",0),
        ("Max Payne","Ação",9.90,0,"NTSC",0),
        ("Max Payne 2: The Fall of Max Payne","Ação",9.90,0,"NTSC",0),
        ("The Warriors","Ação",9.90,0,"NTSC",0),
        ("Manhunt","Ação",9.90,0,"NTSC",0),
        ("Scarface: The World Is Yours","Ação",9.90,0,"NTSC",0),
        ("Spider-Man 2","Ação",9.90,0,"NTSC",0),
        ("Prince of Persia: The Sands of Time","Ação",9.90,0,"NTSC",0),
        ("Prince of Persia: Warrior Within","Ação",9.90,0,"NTSC",0),
        ("Resident Evil 4","Terror",12.90,9.90,"NTSC",1),
        ("Silent Hill 2","Terror",9.90,0,"NTSC",1),
        ("Mortal Kombat: Deception","Luta",9.90,0,"NTSC",0),
        ("Soulcalibur II","Luta",9.90,0,"NTSC",0),
        ("Dead or Alive 3","Luta",9.90,0,"NTSC",0),
        ("Jade Empire","RPG",9.90,0,"NTSC",0),
        ("Psychonauts","Plataforma",9.90,0,"NTSC",0),
        ("Conker: Live & Reloaded","Ação",9.90,0,"NTSC",0),
        ("Doom 3","FPS",9.90,0,"NTSC",0),
        ("Half-Life 2","FPS",9.90,0,"NTSC",0),
        ("Far Cry Instincts","FPS",9.90,0,"NTSC",0),
        ("Jet Set Radio Future","Ação",9.90,0,"NTSC",0),
        ("Panzer Dragoon Orta","Ação",9.90,0,"NTSC",0),
        ("Crimson Skies: High Road to Revenge","Ação",9.90,0,"NTSC",0),
        ("Destroy All Humans!","Ação",9.90,0,"NTSC",0),
        ("Tony Hawk's Underground","Esportes",9.90,0,"NTSC",0),
        ("SSX 3","Esportes",9.90,0,"NTSC",0),
        ("FIFA 07","Esportes",9.90,0,"NTSC",0),
        ("WWE Raw 2","Luta",9.90,0,"NTSC",0),
        ("Otogi: Myth of Demons","Ação",9.90,0,"NTSC",0),
        ("Lego Star Wars: The Video Game","Ação",9.90,0,"NTSC",0),
        ("Guitar Hero II","Simulação",9.90,0,"NTSC",0),
        ("Marvel: Ultimate Alliance","Ação",9.90,0,"NTSC",0),
        ("Project Gotham Racing","Corrida",9.90,0,"NTSC",0),
        ("Midnight Club 3: DUB Edition","Corrida",9.90,0,"NTSC",0),
        ("Voodoo Vince","Plataforma",9.90,0,"NTSC",0),
    ]
    for title, cat, orig, price, region, feat in xbox_games:
        add_game(title, 'xbox', cat, price, orig, 'ISO', '6 GB', 'PT-BR', region, feat)

    # ── PlayStation 2 ───────────────────────────────────────────────────────
    ps2_games = [
        ("Grand Theft Auto: San Andreas","Ação",14.90,9.90,"NTSC",1),
        ("Grand Theft Auto: Vice City","Ação",9.90,0,"NTSC",1),
        ("Grand Theft Auto III","Ação",9.90,0,"NTSC",0),
        ("God of War","Ação",12.90,9.90,"NTSC",1),
        ("God of War II","Ação",12.90,9.90,"NTSC",1),
        ("Shadow of the Colossus","Aventura",12.90,9.90,"NTSC",1),
        ("Resident Evil 4","Terror",12.90,9.90,"NTSC",1),
        ("Devil May Cry","Ação",9.90,0,"NTSC",0),
        ("Devil May Cry 3: Dante's Awakening","Ação",12.90,9.90,"NTSC",1),
        ("Metal Gear Solid 2: Sons of Liberty","Ação",12.90,9.90,"NTSC",1),
        ("Metal Gear Solid 3: Snake Eater","Ação",12.90,9.90,"NTSC",1),
        ("Kingdom Hearts","RPG",12.90,9.90,"NTSC",1),
        ("Kingdom Hearts II","RPG",14.90,9.90,"NTSC",1),
        ("Final Fantasy X","RPG",12.90,9.90,"NTSC",1),
        ("Final Fantasy XII","RPG",12.90,9.90,"NTSC",0),
        ("Dragon Ball Z: Budokai Tenkaichi 3","Luta",12.90,9.90,"NTSC",1),
        ("Dragon Ball Z: Budokai 3","Luta",9.90,0,"NTSC",0),
        ("Dragon Ball Z: Budokai","Luta",9.90,0,"NTSC",0),
        ("Naruto: Ultimate Ninja 5","Luta",9.90,0,"NTSC",0),
        ("Tekken 5","Luta",12.90,9.90,"NTSC",1),
        ("Soulcalibur III","Luta",9.90,0,"NTSC",0),
        ("Mortal Kombat: Armageddon","Luta",9.90,0,"NTSC",0),
        ("Need for Speed Underground","Corrida",9.90,0,"NTSC",0),
        ("Need for Speed Underground 2","Corrida",9.90,0,"NTSC",0),
        ("Need for Speed Most Wanted","Corrida",12.90,9.90,"NTSC",1),
        ("Burnout 3: Takedown","Corrida",9.90,0,"NTSC",1),
        ("Gran Turismo 4","Corrida",12.90,9.90,"NTSC",1),
        ("Tony Hawk's Pro Skater 3","Esportes",9.90,0,"NTSC",0),
        ("Bully","Aventura",9.90,0,"NTSC",0),
        ("Okami","Aventura",9.90,0,"NTSC",1),
        ("The Warriors","Ação",9.90,0,"NTSC",0),
        ("Spider-Man 2","Ação",9.90,0,"NTSC",0),
        ("Prince of Persia: The Sands of Time","Ação",9.90,0,"NTSC",0),
        ("Prince of Persia: Warrior Within","Ação",9.90,0,"NTSC",0),
        ("Ratchet & Clank","Plataforma",9.90,0,"NTSC",1),
        ("Jak and Daxter: The Precursor Legacy","Plataforma",9.90,0,"NTSC",0),
        ("Jak II","Plataforma",9.90,0,"NTSC",0),
        ("Sly Cooper and the Thievius Raccoonus","Plataforma",9.90,0,"NTSC",0),
        ("Crash Twinsanity","Plataforma",9.90,0,"NTSC",0),
        ("Crash Nitro Kart","Corrida",9.90,0,"NTSC",0),
        ("FIFA 14","Esportes",9.90,0,"NTSC",0),
        ("Pro Evolution Soccer 6","Esportes",9.90,0,"NTSC",0),
        ("WWE SmackDown! Here Comes the Pain","Luta",9.90,0,"NTSC",0),
        ("Def Jam: Fight for NY","Luta",9.90,0,"NTSC",0),
        ("Manhunt","Ação",9.90,0,"NTSC",0),
        ("Scarface: The World Is Yours","Ação",9.90,0,"NTSC",0),
        ("Hitman: Blood Money","Ação",9.90,0,"NTSC",0),
        ("Silent Hill 2","Terror",9.90,0,"NTSC",1),
        ("Silent Hill 3","Terror",9.90,0,"NTSC",0),
        ("Fatal Frame II: Crimson Butterfly","Terror",9.90,0,"NTSC",0),
        ("Ico","Aventura",9.90,0,"NTSC",0),
        ("Persona 4","RPG",12.90,9.90,"NTSC",1),
        ("Persona 3 FES","RPG",12.90,9.90,"NTSC",1),
        ("Shin Megami Tensei: Nocturne","RPG",9.90,0,"NTSC",0),
        ("Dark Cloud","RPG",9.90,0,"NTSC",0),
        ("Dark Chronicle","RPG",9.90,0,"NTSC",0),
        ("Rogue Galaxy","RPG",9.90,0,"NTSC",0),
        ("Black","FPS",9.90,0,"NTSC",0),
        ("Destroy All Humans!","Ação",9.90,0,"NTSC",0),
        ("Lego Star Wars: The Video Game","Ação",9.90,0,"NTSC",0),
        ("Lego Batman: The Videogame","Ação",9.90,0,"NTSC",0),
        ("TimeSplitters 2","FPS",9.90,0,"NTSC",0),
        ("Ace Combat 5: The Unsung War","Ação",9.90,0,"NTSC",0),
        ("Max Payne","Ação",9.90,0,"NTSC",0),
        ("Max Payne 2: The Fall of Max Payne","Ação",9.90,0,"NTSC",0),
        ("Katamari Damacy","Puzzle",9.90,0,"NTSC",0),
        ("Viewtiful Joe","Ação",9.90,0,"NTSC",0),
        ("Haunting Ground","Terror",9.90,0,"NTSC",0),
        ("Resident Evil Code: Veronica X","Terror",9.90,0,"NTSC",0),
        ("SSX 3","Esportes",9.90,0,"NTSC",0),
        ("Wipeout Fusion","Corrida",9.90,0,"NTSC",0),
        ("Jak 3","Plataforma",9.90,0,"NTSC",0),
        ("Sly 2: Band of Thieves","Plataforma",9.90,0,"NTSC",0),
        ("Crash Tag Team Racing","Corrida",9.90,0,"NTSC",0),
        ("Batman Begins","Ação",9.90,0,"NTSC",0),
        ("Tom Clancy's Splinter Cell: Chaos Theory","Ação",9.90,0,"NTSC",0),
    ]
    for title, cat, orig, price, region, feat in ps2_games:
        add_game(title, 'playstation-2', cat, price, orig, 'ISO', '4.3 GB', 'PT-BR', region, feat)

    # ── PSP ─────────────────────────────────────────────────────────────────
    psp_games = [
        ("God of War: Chains of Olympus","Ação",9.90,0,"NTSC",1),
        ("God of War: Ghost of Sparta","Ação",9.90,0,"NTSC",1),
        ("Grand Theft Auto: Liberty City Stories","Ação",9.90,0,"NTSC",1),
        ("Grand Theft Auto: Vice City Stories","Ação",9.90,0,"NTSC",1),
        ("Grand Theft Auto: Chinatown Wars","Ação",9.90,0,"NTSC",0),
        ("Crisis Core: Final Fantasy VII","RPG",12.90,9.90,"NTSC",1),
        ("Final Fantasy Tactics: The War of the Lions","RPG",9.90,0,"NTSC",1),
        ("Kingdom Hearts Birth by Sleep","RPG",12.90,9.90,"NTSC",1),
        ("Metal Gear Solid: Peace Walker","Ação",12.90,9.90,"NTSC",1),
        ("Metal Gear Solid: Portable Ops","Ação",9.90,0,"NTSC",0),
        ("Monster Hunter Freedom Unite","Ação",12.90,9.90,"NTSC",1),
        ("Monster Hunter Freedom 2","Ação",9.90,0,"NTSC",0),
        ("Monster Hunter Portable 3rd","Ação",12.90,9.90,"NTSC",1),
        ("Dissidia Final Fantasy","Luta",9.90,0,"NTSC",0),
        ("Dissidia 012 Final Fantasy","Luta",9.90,0,"NTSC",0),
        ("Naruto Shippuden: Ultimate Ninja Impact","Luta",9.90,0,"NTSC",0),
        ("Dragon Ball Z: Shin Budokai","Luta",9.90,0,"NTSC",0),
        ("Dragon Ball Z: Shin Budokai 2","Luta",9.90,0,"NTSC",0),
        ("Tekken: Dark Resurrection","Luta",9.90,0,"NTSC",1),
        ("Soulcalibur: Broken Destiny","Luta",9.90,0,"NTSC",0),
        ("Street Fighter Alpha 3 MAX","Luta",9.90,0,"NTSC",0),
        ("Mortal Kombat: Unchained","Luta",9.90,0,"NTSC",0),
        ("Gran Turismo PSP","Corrida",9.90,0,"NTSC",1),
        ("Need for Speed: Most Wanted 5-1-0","Corrida",9.90,0,"NTSC",0),
        ("Burnout Legends","Corrida",9.90,0,"NTSC",0),
        ("Midnight Club 3: DUB Edition","Corrida",9.90,0,"NTSC",0),
        ("Tekken 6","Luta",9.90,0,"NTSC",0),
        ("Persona 3 Portable","RPG",12.90,9.90,"NTSC",1),
        ("Ys Seven","RPG",9.90,0,"NTSC",0),
        ("Valkyria Chronicles II","RPG",9.90,0,"NTSC",0),
        ("Disgaea: Afternoon of Darkness","RPG",9.90,0,"NTSC",0),
        ("Tactics Ogre: Let Us Cling Together","RPG",9.90,0,"NTSC",0),
        ("Final Fantasy I","RPG",9.90,0,"NTSC",0),
        ("Final Fantasy II","RPG",9.90,0,"NTSC",0),
        ("Silent Hill: Origins","Terror",9.90,0,"NTSC",0),
        ("Silent Hill: Shattered Memories","Terror",9.90,0,"NTSC",0),
        ("LocoRoco","Puzzle",9.90,0,"NTSC",0),
        ("LocoRoco 2","Puzzle",9.90,0,"NTSC",0),
        ("Patapon","Estratégia",9.90,0,"NTSC",0),
        ("Patapon 2","Estratégia",9.90,0,"NTSC",0),
        ("Patapon 3","Estratégia",9.90,0,"NTSC",0),
        ("Killzone: Liberation","FPS",9.90,0,"NTSC",0),
        ("Resistance: Retribution","FPS",9.90,0,"NTSC",0),
        ("LittleBigPlanet PSP","Plataforma",9.90,0,"NTSC",0),
        ("Bully: Anniversary Edition","Aventura",9.90,0,"NTSC",0),
        ("Daxter","Plataforma",9.90,0,"NTSC",0),
        ("Ratchet & Clank: Size Matters","Plataforma",9.90,0,"NTSC",0),
        ("The Warriors","Ação",9.90,0,"NTSC",0),
        ("Ace Combat X: Skies of Deception","Ação",9.90,0,"NTSC",0),
        ("Ridge Racer","Corrida",9.90,0,"NTSC",0),
        ("Wipeout Pure","Corrida",9.90,0,"NTSC",0),
        ("Manhunt 2","Ação",9.90,0,"NTSC",0),
        ("Lego Star Wars II: The Original Trilogy","Ação",9.90,0,"NTSC",0),
        ("Sonic Rivals","Plataforma",9.90,0,"NTSC",0),
        ("Crash Tag Team Racing","Corrida",9.90,0,"NTSC",0),
        ("Crash of the Titans","Ação",9.90,0,"NTSC",0),
        ("Lego Batman: The Videogame","Ação",9.90,0,"NTSC",0),
        ("Spider-Man 2","Ação",9.90,0,"NTSC",0),
        ("The 3rd Birthday","RPG",9.90,0,"NTSC",0),
        ("Star Ocean: Second Evolution","RPG",9.90,0,"NTSC",0),
        ("Jeanne d'Arc","RPG",9.90,0,"NTSC",0),
        ("Tales of the World: Radiant Mythology","RPG",9.90,0,"NTSC",0),
        ("Syphon Filter: Dark Mirror","Ação",9.90,0,"NTSC",0),
        ("Syphon Filter: Logan's Shadow","Ação",9.90,0,"NTSC",0),
    ]
    for title, cat, orig, price, region, feat in psp_games:
        add_game(title, 'psp', cat, price, orig, 'ISO', '1.5 GB', 'PT-BR', region, feat)

    # ── Nintendo 3DS (NDS) ──────────────────────────────────────────────────
    nds_games = [
        ("Mario Kart 7","Corrida",9.90,0,"NTSC",1),
        ("Super Mario 3D Land","Plataforma",9.90,0,"NTSC",1),
        ("The Legend of Zelda: Ocarina of Time 3D","Aventura",12.90,9.90,"NTSC",1),
        ("The Legend of Zelda: A Link Between Worlds","Aventura",12.90,9.90,"NTSC",1),
        ("The Legend of Zelda: Majora's Mask 3D","Aventura",12.90,9.90,"NTSC",1),
        ("Super Smash Bros. for Nintendo 3DS","Luta",12.90,9.90,"NTSC",1),
        ("Pokémon X","RPG",9.90,0,"NTSC",1),
        ("Pokémon Y","RPG",9.90,0,"NTSC",0),
        ("Pokémon Omega Ruby","RPG",9.90,0,"NTSC",1),
        ("Pokémon Alpha Sapphire","RPG",9.90,0,"NTSC",0),
        ("Pokémon Sun","RPG",9.90,0,"NTSC",1),
        ("Pokémon Moon","RPG",9.90,0,"NTSC",0),
        ("Pokémon Ultra Sun","RPG",9.90,0,"NTSC",0),
        ("Pokémon Ultra Moon","RPG",9.90,0,"NTSC",0),
        ("Animal Crossing: New Leaf","Simulação",9.90,0,"NTSC",1),
        ("Fire Emblem Awakening","RPG",12.90,9.90,"NTSC",1),
        ("Fire Emblem Fates","RPG",12.90,9.90,"NTSC",1),
        ("Luigi's Mansion: Dark Moon","Aventura",9.90,0,"NTSC",1),
        ("New Super Mario Bros. 2","Plataforma",9.90,0,"NTSC",0),
        ("Mario & Luigi: Dream Team","RPG",9.90,0,"NTSC",0),
        ("Mario & Luigi: Bowser's Inside Story + Bowser Jr.'s Journey","RPG",9.90,0,"NTSC",0),
        ("Kirby: Triple Deluxe","Plataforma",9.90,0,"NTSC",0),
        ("Kirby: Planet Robobot","Plataforma",9.90,0,"NTSC",0),
        ("Donkey Kong Country Returns 3D","Plataforma",9.90,0,"NTSC",0),
        ("Star Fox 64 3D","Ação",9.90,0,"NTSC",0),
        ("Kid Icarus: Uprising","Ação",9.90,0,"NTSC",1),
        ("Monster Hunter 4 Ultimate","Ação",12.90,9.90,"NTSC",1),
        ("Monster Hunter Generations","Ação",12.90,9.90,"NTSC",1),
        ("Dragon Quest VII: Fragments of the Forgotten Past","RPG",9.90,0,"NTSC",0),
        ("Dragon Quest VIII: Journey of the Cursed King","RPG",9.90,0,"NTSC",1),
        ("Bravely Default","RPG",9.90,0,"NTSC",1),
        ("Bravely Second: End Layer","RPG",9.90,0,"NTSC",0),
        ("Shin Megami Tensei IV","RPG",9.90,0,"NTSC",0),
        ("Persona Q: Shadow of the Labyrinth","RPG",9.90,0,"NTSC",0),
        ("Persona Q2: New Cinema Labyrinth","RPG",9.90,0,"NTSC",0),
        ("Phoenix Wright: Ace Attorney Trilogy","Aventura",9.90,0,"NTSC",0),
        ("Professor Layton and the Miracle Mask","Puzzle",9.90,0,"NTSC",0),
        ("Resident Evil Revelations","Terror",9.90,0,"NTSC",0),
        ("Castlevania: Lords of Shadow – Mirror of Fate","Ação",9.90,0,"NTSC",0),
        ("Metal Gear Solid: Snake Eater 3D","Ação",9.90,0,"NTSC",0),
        ("Sonic Generations","Plataforma",9.90,0,"NTSC",0),
        ("Sonic Lost World","Plataforma",9.90,0,"NTSC",0),
        ("Shovel Knight","Plataforma",9.90,0,"NTSC",0),
        ("Minecraft: New Nintendo 3DS Edition","Aventura",9.90,0,"NTSC",0),
        ("Terraria","Aventura",9.90,0,"NTSC",0),
        ("Tomodachi Life","Simulação",9.90,0,"NTSC",0),
        ("Mario Party: Island Tour","Simulação",9.90,0,"NTSC",0),
        ("Rune Factory 4","RPG",9.90,0,"NTSC",0),
        ("Fantasy Life","RPG",9.90,0,"NTSC",0),
        ("Yo-kai Watch","RPG",9.90,0,"NTSC",0),
        ("Yo-kai Watch 2","RPG",9.90,0,"NTSC",0),
        ("Harvest Moon: A New Beginning","Simulação",9.90,0,"NTSC",0),
        ("Hatsune Miku: Project Mirai DX","Simulação",9.90,0,"NTSC",0),
        ("Super Street Fighter IV: 3D Edition","Luta",9.90,0,"NTSC",0),
        ("Dead or Alive: Dimensions","Luta",9.90,0,"NTSC",0),
        ("Pokémon Mystery Dungeon: Gates to Infinity","RPG",9.90,0,"NTSC",0),
        ("Pokémon Super Mystery Dungeon","RPG",9.90,0,"NTSC",0),
        ("Project X Zone","RPG",9.90,0,"NTSC",0),
        ("Project X Zone 2","RPG",9.90,0,"NTSC",0),
        ("Theatrhythm Final Fantasy","Simulação",9.90,0,"NTSC",0),
        ("Theatrhythm Final Fantasy: Curtain Call","Simulação",9.90,0,"NTSC",0),
        ("WarioWare Gold","Simulação",9.90,0,"NTSC",0),
        ("Rhythm Heaven Megamix","Simulação",9.90,0,"NTSC",0),
        ("Miitopia","RPG",9.90,0,"NTSC",0),
        ("Poochy & Yoshi's Woolly World","Plataforma",9.90,0,"NTSC",0),
        ("Lego Marvel Super Heroes","Ação",9.90,0,"NTSC",0),
        ("Lego Star Wars: The Force Awakens","Ação",9.90,0,"NTSC",0),
        ("Monster Hunter Stories","RPG",9.90,0,"NTSC",0),
        ("Shin Megami Tensei IV: Apocalypse","RPG",9.90,0,"NTSC",0),
        ("Fire Emblem Echoes: Shadows of Valentia","RPG",9.90,0,"NTSC",0),
    ]
    for title, cat, orig, price, region, feat in nds_games:
        add_game(title, 'nintendo-3ds', cat, price, orig, 'CIA', '3 GB', 'PT-BR', region, feat)

    db.commit()

    # Coupons padrão
    coupons = [
        ('GAMER10', 'percent', 10, 0, 999, None),
        ('PRIMEIRACOMPRA', 'percent', 15, 0, 1, None),
        ('PACK5', 'fixed', 5.00, 20, 999, None),
    ]
    for code, dtype, dval, min_v, max_u, exp in coupons:
        db.execute("INSERT OR IGNORE INTO coupons(code,discount_type,discount_value,min_value,max_uses,expires_at) VALUES(?,?,?,?,?,?)",
            (code, dtype, dval, min_v, max_u, exp))

    # Banners
    banners = [
        ('🎮 Bem-vindo ao GameVault', 'Os melhores jogos clássicos em formato digital', '', '/', 0),
        ('🔥 Promoção da Semana', 'Jogos de PS2 a partir de R$ 7,90', '', '/console/playstation-2', 1),
        ('🆕 Novos Jogos Adicionados', 'Confira as últimas adições ao catálogo', '', '/novidades', 2),
    ]
    for title, sub, img, link, order in banners:
        db.execute("INSERT OR IGNORE INTO banners(title,subtitle,image,link,sort_order) VALUES(?,?,?,?,?)",
            (title, sub, img, link, order))

    # Bundle
    db.execute("INSERT OR IGNORE INTO bundles(id,name,description,price,active) VALUES(1,'Pack PS2 Clássicos','5 jogos mais vendidos do PS2',29.90,1)")

    db.commit()
    print(f"✅ Banco de dados inicializado com sucesso!")
    total_games = db.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    print(f"✅ {total_games} jogos cadastrados")
    db.close()

    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
