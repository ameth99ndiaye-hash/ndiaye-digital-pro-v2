import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from functools import wraps
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 12,
)

DB = Path(os.getenv("DATABASE_PATH", "instance/ndiaye_digital.db"))
DB.parent.mkdir(parents=True, exist_ok=True)

@contextmanager
def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS merchants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT NOT NULL,
            owner_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            sku TEXT NOT NULL DEFAULT '',
            quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
            min_quantity INTEGER NOT NULL DEFAULT 0 CHECK(min_quantity >= 0),
            unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price >= 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(merchant_id, sku)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
            total REAL NOT NULL CHECK(total >= 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL CHECK(unit_price >= 0)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            movement_type TEXT NOT NULL CHECK(movement_type IN ('IN','OUT')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            note TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]

@app.context_processor
def inject_csrf():
    return {"csrf_token": csrf_token}

@app.before_request
def protect_posts():
    if request.method == "POST":
        sent = request.form.get("_csrf", "")
        expected = session.get("_csrf", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, description="Jeton de sécurité invalide. Recharge la page et réessaie.")

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "merchant_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def current_merchant():
    return int(session["merchant_id"])

@app.get("/")
def index():
    if session.get("merchant_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        shop = request.form.get("shop_name", "").strip()
        owner = request.form.get("owner_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not all([shop, owner, email, password]) or len(password) < 10:
            flash("Complète tous les champs. Le mot de passe doit contenir au moins 10 caractères.", "error")
            return render_template("register.html")
        try:
            with db() as con:
                cur = con.execute(
                    "INSERT INTO merchants(shop_name, owner_name, email, password_hash) VALUES(?,?,?,?)",
                    (shop, owner, email, generate_password_hash(password))
                )
                session.clear()
                session["merchant_id"] = cur.lastrowid
                session["shop_name"] = shop
                session.permanent = True
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("Cette adresse e-mail possède déjà un compte.", "error")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with db() as con:
            merchant = con.execute("SELECT * FROM merchants WHERE email=?", (email,)).fetchone()
        if merchant and check_password_hash(merchant["password_hash"], password):
            session.clear()
            session["merchant_id"] = merchant["id"]
            session["shop_name"] = merchant["shop_name"]
            session.permanent = True
            return redirect(url_for("dashboard"))
        flash("Identifiants incorrects.", "error")
    return render_template("login.html")

@app.get("/dashboard")
@login_required
def dashboard():
    mid = current_merchant()
    with db() as con:
        product_count = con.execute("SELECT COUNT(*) FROM products WHERE merchant_id=?", (mid,)).fetchone()[0]
        low_stock = con.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND quantity<=min_quantity", (mid,)).fetchone()[0]
        sales_total = con.execute("SELECT COALESCE(SUM(total),0) FROM sales WHERE merchant_id=? AND date(created_at)=date('now','localtime')", (mid,)).fetchone()[0]
        recent_sales = con.execute("SELECT id,total,created_at FROM sales WHERE merchant_id=? ORDER BY id DESC LIMIT 5", (mid,)).fetchall()
    return render_template("dashboard.html", shop_name=session.get("shop_name", "Ma boutique"),
                           product_count=product_count, low_stock=low_stock,
                           sales_total=sales_total, recent_sales=recent_sales)

@app.route("/products", methods=["GET", "POST"])
@login_required
def products():
    mid = current_merchant()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        sku = request.form.get("sku", "").strip()
        try:
            quantity = int(request.form.get("quantity", "0"))
            min_quantity = int(request.form.get("min_quantity", "0"))
            unit_price = float(request.form.get("unit_price", "0"))
            if not name or quantity < 0 or min_quantity < 0 or unit_price < 0:
                raise ValueError()
            with db() as con:
                con.execute("INSERT INTO products(merchant_id,name,sku,quantity,min_quantity,unit_price) VALUES(?,?,?,?,?,?)",
                            (mid,name,sku,quantity,min_quantity,unit_price))
            flash("Produit ajouté.", "success")
            return redirect(url_for("products"))
        except ValueError:
            flash("Vérifie les quantités et le prix saisis.", "error")
        except sqlite3.IntegrityError:
            flash("Ce code produit existe déjà dans ta boutique.", "error")
    with db() as con:
        rows = con.execute("SELECT * FROM products WHERE merchant_id=? ORDER BY name", (mid,)).fetchall()
    return render_template("products.html", products=rows)

@app.route("/stock/<int:product_id>", methods=["POST"])
@login_required
def stock_adjust(product_id):
    mid = current_merchant()
    try:
        quantity = int(request.form.get("quantity", "0"))
        movement_type = request.form.get("movement_type")
        note = request.form.get("note", "").strip()[:200]
        if quantity <= 0 or movement_type not in ("IN", "OUT"):
            raise ValueError()
        with db() as con:
            product = con.execute("SELECT id,quantity FROM products WHERE id=? AND merchant_id=?", (product_id,mid)).fetchone()
            if not product:
                abort(404)
            new_qty = product["quantity"] + quantity if movement_type == "IN" else product["quantity"] - quantity
            if new_qty < 0:
                flash("Stock insuffisant pour cette sortie.", "error")
                return redirect(url_for("products"))
            con.execute("UPDATE products SET quantity=? WHERE id=? AND merchant_id=?", (new_qty,product_id,mid))
            con.execute("INSERT INTO stock_movements(merchant_id,product_id,movement_type,quantity,note) VALUES(?,?,?,?,?)",
                        (mid,product_id,movement_type,quantity,note))
        flash("Mouvement de stock enregistré.", "success")
    except ValueError:
        flash("Quantité invalide.", "error")
    return redirect(url_for("products"))

@app.route("/sales", methods=["GET", "POST"])
@login_required
def sales():
    mid = current_merchant()
    if request.method == "POST":
        try:
            product_id = int(request.form.get("product_id", "0"))
            quantity = int(request.form.get("quantity", "0"))
            if quantity <= 0:
                raise ValueError()
            with db() as con:
                product = con.execute("SELECT * FROM products WHERE id=? AND merchant_id=?", (product_id,mid)).fetchone()
                if not product:
                    abort(404)
                if product["quantity"] < quantity:
                    flash("Stock insuffisant pour cette vente.", "error")
                    return redirect(url_for("sales"))
                total = round(product["unit_price"] * quantity, 2)
                cur = con.execute("INSERT INTO sales(merchant_id,total) VALUES(?,?)", (mid,total))
                con.execute("INSERT INTO sale_items(sale_id,product_id,quantity,unit_price) VALUES(?,?,?,?)",
                            (cur.lastrowid,product_id,quantity,product["unit_price"]))
                con.execute("UPDATE products SET quantity=quantity-? WHERE id=? AND merchant_id=?", (quantity,product_id,mid))
                con.execute("INSERT INTO stock_movements(merchant_id,product_id,movement_type,quantity,note) VALUES(?,?,?,?,?)",
                            (mid,product_id,"OUT",quantity,"Vente"))
            flash("Vente enregistrée et stock mis à jour.", "success")
            return redirect(url_for("sales"))
        except ValueError:
            flash("Choisis un produit et une quantité valide.", "error")
    with db() as con:
        products_list = con.execute("SELECT id,name,quantity,unit_price FROM products WHERE merchant_id=? AND quantity>0 ORDER BY name", (mid,)).fetchall()
        sales_list = con.execute("""SELECT s.id,s.total,s.created_at, GROUP_CONCAT(p.name || ' × ' || si.quantity, ', ') AS details
                                    FROM sales s JOIN sale_items si ON si.sale_id=s.id JOIN products p ON p.id=si.product_id
                                    WHERE s.merchant_id=? GROUP BY s.id ORDER BY s.id DESC LIMIT 50""", (mid,)).fetchall()
    return render_template("sales.html", products=products_list, sales=sales_list)

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.get("/health")
def health():
    return {"status":"ok","app":"NDIAYE DIGITAL PRO","phase":2}

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
