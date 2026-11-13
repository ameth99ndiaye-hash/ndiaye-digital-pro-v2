import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "CHANGE-ME-before-deployment")

# Phase 1 starter: local SQLite for safe development only.
# Production multi-tenant deployment will move authentication/data to Supabase
# with PostgreSQL Row Level Security (RLS).
import sqlite3
from pathlib import Path
DB = Path("instance/ndiaye_digital.db")
DB.parent.mkdir(exist_ok=True)

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

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

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "merchant_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

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
        if not all([shop, owner, email, password]) or len(password) < 8:
            flash("Complète tous les champs. Le mot de passe doit contenir au moins 8 caractères.", "error")
            return render_template("register.html")
        try:
            with db() as con:
                cur = con.execute(
                    "INSERT INTO merchants(shop_name, owner_name, email, password_hash) VALUES(?,?,?,?)",
                    (shop, owner, email, generate_password_hash(password))
                )
                session["merchant_id"] = cur.lastrowid
                session["shop_name"] = shop
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
            session["merchant_id"] = merchant["id"]
            session["shop_name"] = merchant["shop_name"]
            return redirect(url_for("dashboard"))
        flash("Identifiants incorrects.", "error")
    return render_template("login.html")

@app.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", shop_name=session.get("shop_name", "Ma boutique"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.get("/health")
def health():
    return {"status": "ok", "app": "NDIAYE DIGITAL PRO", "phase": 1}

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
