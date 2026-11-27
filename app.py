import os
import secrets
import sqlite3
import time
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.security import check_password_hash, generate_password_hash

from supabase_client import check_supabase_connection
from merchant_auth import (
    merchant_counts, merchant_for_user, refresh_auth_session,
    sign_in, sign_up, supabase_auth_enabled, list_products, create_product,
    adjust_stock, list_stock_movements, create_sale, list_sales,
)

load_dotenv()

app = Flask(__name__)
app.config["WTF_CSRF_ENABLED"] = os.getenv("WTF_CSRF_ENABLED", "1") == "1"
csrf = CSRFProtect(app)
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


@app.get("/sw.js")
def service_worker():
    response = app.send_static_file("sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/offline")
def offline_page():
    return app.send_static_file("offline.html")


@app.context_processor
def inject_admin_email():
    return {"config_admin_email": os.getenv("ADMIN_EMAIL", "").strip().lower()}


@app.get("/")
def index():
    if session.get("merchant_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Public self-registration is deliberately disabled.
    # Only the administrator will be allowed to create merchant accounts.
    flash("Les inscriptions publiques sont fermées. Contacte l’administrateur pour obtenir un compte.", "error")
    return redirect(url_for("login"))


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        expected = os.getenv("ADMIN_EMAIL", "").strip().lower()
        current = session.get("email", "").strip().lower()
        if not expected or current != expected or not session.get("auth_sid"):
            flash("Accès réservé à l’administrateur.", "error")
            return redirect(url_for("login"))
        g.auth_record = load_auth_session()
        if not g.auth_record:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/admin", methods=["GET", "POST"], endpoint="admin_panel")
@admin_required
def admin():
    temporary_credentials = None
    secret_ready = bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip())
    if request.method == "POST":
        shop = request.form.get("shop_name", "").strip()
        owner = request.form.get("owner_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        if not secret_ready:
            flash("Configuration incomplète : la clé secrète Supabase doit être ajoutée dans les variables privées de Render.", "error")
        elif not all([shop, owner, email]) or email == os.getenv("ADMIN_EMAIL", "").strip().lower():
            flash("Vérifie les champs et utilise une adresse différente de celle de l’administrateur.", "error")
        else:
            try:
                from supabase_client import create_supabase_admin_client
                admin_client = create_supabase_admin_client()
                temporary_password = secrets.token_urlsafe(15)
                created = admin_client.auth.admin.create_user({
                    "email": email,
                    "password": temporary_password,
                    "email_confirm": True,
                    "user_metadata": {"shop_name": shop, "owner_name": owner},
                })
                new_user = getattr(created, "user", None)
                if not new_user:
                    raise RuntimeError("Supabase n’a pas retourné le nouvel utilisateur.")
                admin_client.table("merchants").insert({
                    "owner_id": str(new_user.id),
                    "shop_name": shop,
                }).execute()
                temporary_credentials = {"email": email, "password": temporary_password}
            except Exception:
                app.logger.exception("Admin account creation failed")
                flash("La création a échoué. Vérifie la configuration Supabase et que cette adresse n’existe pas déjà.", "error")
    return render_template("admin.html", secret_ready=secret_ready, temporary_credentials=temporary_credentials)

@app.route("/admin/payments", methods=["GET", "POST"])
@admin_required
def admin_payments():
    from supabase_client import create_supabase_admin_client
    admin_client = create_supabase_admin_client()
    if request.method == "POST":
        submission_id = request.form.get("submission_id", "").strip()
        decision = request.form.get("decision", "").strip()
        note = request.form.get("admin_note", "").strip()[:500]
        if decision not in ("confirmed", "rejected") or not submission_id:
            flash("Action invalide.", "error")
        else:
            try:
                admin_client.rpc("admin_review_payment_submission", {
                    "p_submission_id": submission_id,
                    "p_decision": decision,
                    "p_admin_note": note or None,
                }).execute()
                flash("Paiement confirmé et abonnement activé." if decision == "confirmed" else "Demande de paiement refusée.", "success")
            except Exception:
                app.logger.exception("Manual payment review failed")
                flash("Impossible de traiter cette demande. Vérifie son statut puis réessaie.", "error")
        return redirect(url_for("admin_payments"))

    try:
        submissions = (admin_client.table("payment_submissions")
            .select("id,merchant_id,plan_code,provider,amount_xof,payer_phone,transaction_reference,status,submitted_at,admin_note")
            .order("submitted_at", desc=True).limit(100).execute().data)
        merchant_ids = list({row["merchant_id"] for row in submissions})
        merchant_names = {}
        if merchant_ids:
            merchants = (admin_client.table("merchants").select("id,shop_name")
                .in_("id", merchant_ids).execute().data)
            merchant_names = {row["id"]: row["shop_name"] for row in merchants}
        for row in submissions:
            row["shop_name"] = merchant_names.get(row["merchant_id"], "Boutique")
    except Exception:
        app.logger.exception("Could not load payment submissions")
        submissions = []
        flash("Impossible de charger les demandes de paiement.", "error")
    return render_template("admin_payments.html", submissions=submissions)



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


@app.route("/admin/subscriptions", methods=["GET", "POST"])
@admin_required
def admin_subscriptions():
    from supabase_client import create_supabase_admin_client
    admin_client = create_supabase_admin_client()
    if request.method == "POST":
        merchant_id = request.form.get("merchant_id", "").strip()
        action = request.form.get("action", "").strip()
        if action not in ("activate", "suspend") or not merchant_id:
            flash("Action invalide.", "error")
        else:
            try:
                admin_client.rpc("admin_set_merchant_subscription", {
                    "p_merchant_id": merchant_id,
                    "p_action": action,
                }).execute()
                flash("Abonnement activé pour un mois." if action == "activate" else "Abonnement suspendu.", "success")
            except Exception:
                app.logger.exception("Manual subscription action failed")
                flash("Impossible de modifier cet abonnement. Vérifie le compte puis réessaie.", "error")
        return redirect(url_for("admin_subscriptions"))

    try:
        merchants = admin_client.table("merchants").select("id,shop_name").order("shop_name").limit(500).execute().data
        subscriptions = admin_client.table("subscriptions").select("merchant_id,plan_code,status,current_period_start,current_period_end").execute().data
        subscription_by_merchant = {row["merchant_id"]: row for row in subscriptions}
        for merchant in merchants:
            merchant["subscription"] = subscription_by_merchant.get(merchant["id"])
    except Exception:
        app.logger.exception("Could not load merchant subscriptions")
        merchants = []
        flash("Impossible de charger les abonnements.", "error")
    return render_template("admin_subscriptions.html", merchants=merchants)


@app.route("/subscription", methods=["GET", "POST"])
@login_required
def subscription():
    from supabase_client import create_supabase_client
    client = create_supabase_client(access_token=g.auth_record["access_token"])
    merchant_id = session["merchant_id"]
    if request.method == "POST":
        provider = request.form.get("provider", "").strip()
        reference = request.form.get("transaction_reference", "").strip()[:120]
        payer_phone = request.form.get("payer_phone", "").strip()[:30]
        if provider not in ("wave", "orange_money") or not reference:
            flash("Choisis le moyen de paiement et saisis la référence de transaction.", "error")
        else:
            try:
                client.table("payment_submissions").insert({
                    "merchant_id": merchant_id, "plan_code": "mensuel",
                    "provider": provider, "amount_xof": 2000,
                    "payer_phone": payer_phone or None,
                    "transaction_reference": reference, "status": "pending",
                }).execute()
                flash("Demande envoyée. Activation après vérification manuelle.", "success")
                return redirect(url_for("subscription"))
            except Exception:
                app.logger.exception("Subscription payment submission failed")
                flash("Demande non enregistrée. Vérifie la référence puis réessaie.", "error")
    try:
        submissions = (client.table("payment_submissions").select("provider,amount_xof,transaction_reference,status,submitted_at").eq("merchant_id", merchant_id).order("submitted_at", desc=True).limit(20).execute().data)
        subscriptions = client.table("subscriptions").select("plan_code,status,current_period_end").eq("merchant_id", merchant_id).limit(1).execute().data
        current_subscription = subscriptions[0] if subscriptions else None
    except Exception:
        app.logger.exception("Could not load merchant subscription")
        submissions, current_subscription = [], None
        flash("Impossible de charger les informations d’abonnement.", "error")
    return render_template("subscription.html", submissions=submissions, current_subscription=current_subscription)

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


@app.get("/api/offline-bootstrap")
@login_required
def offline_bootstrap():
    if not supabase_auth_enabled():
        return jsonify({"error": "offline_sync_requires_supabase"}), 503
    merchant_id = session["merchant_id"]
    try:
        return jsonify({
            "merchant_id": merchant_id,
            "shop_name": session.get("shop_name", "Ma boutique"),
            "products": list_products(g.auth_record["access_token"], merchant_id),
            "movements": list_stock_movements(g.auth_record["access_token"], merchant_id),
            "sales": list_sales(g.auth_record["access_token"], merchant_id),
            "csrf_token": generate_csrf(),
        })
    except Exception:
        app.logger.exception("Offline bootstrap failed")
        return jsonify({"error": "offline_bootstrap_failed"}), 503


@app.post("/api/offline-sync")
@login_required
def offline_sync():
    if not supabase_auth_enabled():
        return jsonify({"error": "offline_sync_requires_supabase"}), 503
    body = request.get_json(silent=True) or {}
    operations = body.get("operations")
    if not isinstance(operations, list) or not 1 <= len(operations) <= 50:
        return jsonify({"error": "invalid_operations_batch"}), 400
    from supabase_client import create_supabase_client
    client = create_supabase_client(access_token=g.auth_record["access_token"])
    merchant_id = session["merchant_id"]
    results = []
    for operation in operations:
        if not isinstance(operation, dict):
            results.append({"operation_id": None, "ok": False, "error": "invalid_operation"})
            continue
        try:
            result = client.rpc("sync_offline_operation", {
                "p_merchant_id": merchant_id,
                "p_operation_id": operation.get("operation_id"),
                "p_operation_type": operation.get("type"),
                "p_payload": operation.get("payload"),
            }).execute().data
            results.append({"operation_id": operation.get("operation_id"), "ok": True, "result": result})
        except Exception:
            app.logger.exception("Offline operation sync failed")
            results.append({"operation_id": operation.get("operation_id"), "ok": False, "error": "sync_failed"})
    return jsonify({"results": results})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "NDIAYE DIGITAL PRO",
        "phase": 2,
        "auth_mode": "supabase" if supabase_auth_enabled() else "local_sqlite",
        "supabase": check_supabase_connection(),
    }


# Phase 3 commerce pages: all queries use the signed-in merchant's Supabase token.
from commerce_routes import register_commerce_routes
register_commerce_routes(app, login_required)


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=debug)
