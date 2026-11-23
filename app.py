import os
import secrets
import sqlite3
import time
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from supabase_client import check_supabase_connection
from supabase_auth import (
    merchant_counts, merchant_for_user, refresh_auth_session,
    sign_in, sign_up, supabase_auth_enabled, list_products, create_product,
    adjust_stock, list_stock_movements, create_sale, list_sales,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
)

BASE_DIR = Path(__file__).resolve().parent
DB = BASE_DIR / "instance" / "ndiaye_digital.db"
DB.parent.mkdir(parents=True, exist_ok=True)


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS merchants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_name TEXT NOT NULL,
                owner_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        # Jetons Supabase stockés côté serveur : jamais dans le cookie du navigateur.
        con.execute(
            """CREATE TABLE IF NOT EXISTS auth_sessions (
                sid TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at REAL NOT NULL,
                merchant_id TEXT NOT NULL,
                shop_name TEXT NOT NULL,
                email TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )


def save_auth_session(auth_session, merchant, email):
    sid = secrets.token_urlsafe(32)
    expires_at = getattr(auth_session, "expires_at", None) or (time.time() + int(getattr(auth_session, "expires_in", 3600)))
    with db() as con:
        con.execute(
            """INSERT INTO auth_sessions
            (sid, access_token, refresh_token, expires_at, merchant_id, shop_name, email)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sid, auth_session.access_token, auth_session.refresh_token,
             float(expires_at), str(merchant["id"]), merchant["shop_name"], email),
        )
    session.clear()
    session["auth_sid"] = sid
    session["merchant_id"] = str(merchant["id"])
    session["shop_name"] = merchant["shop_name"]
    session["email"] = email
    session.permanent = True


def load_auth_session():
    sid = session.get("auth_sid")
    if not sid:
        return None
    with db() as con:
        row = con.execute("SELECT * FROM auth_sessions WHERE sid = ?", (sid,)).fetchone()
    if not row:
        session.clear()
        return None

    if float(row["expires_at"]) <= time.time() + 60:
        try:
            refreshed = refresh_auth_session(row["refresh_token"])
            expires_at = getattr(refreshed, "expires_at", None) or (time.time() + int(getattr(refreshed, "expires_in", 3600)))
            with db() as con:
                con.execute(
                    """UPDATE auth_sessions SET access_token=?, refresh_token=?, expires_at=?,
                    updated_at=CURRENT_TIMESTAMP WHERE sid=?""",
                    (refreshed.access_token, refreshed.refresh_token, float(expires_at), sid),
                )
            row = dict(row)
            row["access_token"] = refreshed.access_token
            row["refresh_token"] = refreshed.refresh_token
            row["expires_at"] = expires_at
        except Exception:
            with db() as con:
                con.execute("DELETE FROM auth_sessions WHERE sid=?", (sid,))
            session.clear()
            return None
    return row


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "merchant_id" not in session:
            return redirect(url_for("login"))
        if supabase_auth_enabled():
            g.auth_record = load_auth_session()
            if not g.auth_record:
                return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


init_db()


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

        if supabase_auth_enabled():
            try:
                _, user, auth_session = sign_up(email, password, shop, owner)
                if not user:
                    flash("Inscription non finalisée. Vérifie ta boîte e-mail si une confirmation est demandée.", "success")
                    return redirect(url_for("login"))
                if not auth_session:
                    flash("Compte créé. Confirme ton adresse e-mail, puis connecte-toi.", "success")
                    return redirect(url_for("login"))
                from supabase_client import create_supabase_client
                client = create_supabase_client(access_token=auth_session.access_token)
                merchant = merchant_for_user(client, user, auth_session.access_token)
                save_auth_session(auth_session, merchant, email)
                return redirect(url_for("dashboard"))
            except Exception:
                app.logger.exception("Supabase registration failed")
                flash("Impossible de créer le compte. Vérifie l'e-mail, le mot de passe et la confirmation e-mail Supabase.", "error")
                return render_template("register.html")

        try:
            with db() as con:
                cur = con.execute(
                    "INSERT INTO merchants(shop_name, owner_name, email, password_hash) VALUES(?,?,?,?)",
                    (shop, owner, email, generate_password_hash(password)),
                )
                session.clear()
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
        if supabase_auth_enabled():
            try:
                _, user, auth_session = sign_in(email, password)
                if not user or not auth_session:
                    flash("Connexion impossible. Vérifie ton e-mail et ton mot de passe.", "error")
                    return render_template("login.html")
                from supabase_client import create_supabase_client
                client = create_supabase_client(access_token=auth_session.access_token)
                merchant = merchant_for_user(client, user, auth_session.access_token)
                save_auth_session(auth_session, merchant, email)
                return redirect(url_for("dashboard"))
            except Exception:
                app.logger.exception("Supabase login failed")
                flash("Identifiants incorrects ou e-mail non confirmé.", "error")
                return render_template("login.html")

        with db() as con:
            merchant = con.execute("SELECT * FROM merchants WHERE email = ?", (email,)).fetchone()
        if merchant and check_password_hash(merchant["password_hash"], password):
            session.clear()
            session["merchant_id"] = merchant["id"]
            session["shop_name"] = merchant["shop_name"]
            return redirect(url_for("dashboard"))
        flash("Identifiants incorrects.", "error")
    return render_template("login.html")


@app.get("/dashboard")
@login_required
def dashboard():
    counts = {"products": 0, "sales": 0}
    if supabase_auth_enabled():
        try:
            counts = merchant_counts(g.auth_record["access_token"], session["merchant_id"])
        except Exception:
            app.logger.exception("Could not load Supabase dashboard counts")
            flash("Certaines données ne sont pas disponibles pour le moment.", "error")
    return render_template(
        "dashboard.html",
        shop_name=session.get("shop_name", "Ma boutique"),
        counts=counts,
    )


@app.get("/logout")
def logout():
    sid = session.get("auth_sid")
    if sid:
        with db() as con:
            con.execute("DELETE FROM auth_sessions WHERE sid=?", (sid,))
    session.clear()
    return redirect(url_for("index"))


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "NDIAYE DIGITAL PRO",
        "phase": 2,
        "auth_mode": "supabase" if supabase_auth_enabled() else "local_sqlite",
        "supabase": check_supabase_connection(),
    }


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=debug)
