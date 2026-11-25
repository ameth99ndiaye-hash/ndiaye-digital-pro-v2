"""Supabase-backed merchant product, stock and sales routes."""
from flask import flash, g, redirect, render_template, request, session, url_for

from merchant_auth import (
    list_products, create_product, adjust_stock,
    list_stock_movements, create_sale, list_sales,
)


def register_commerce_routes(app, login_required):
    @app.route("/products", methods=["GET", "POST"])
    @login_required
    def products():
        token = g.auth_record["access_token"]
        merchant_id = session["merchant_id"]
        if request.method == "POST":
            try:
                name = request.form.get("name", "").strip()
                sku = request.form.get("sku", "").strip()
                quantity = int(request.form.get("quantity", "0"))
                minimum = int(request.form.get("min_quantity", "0"))
                price = int(request.form.get("unit_price", "0"))
                if not name or min(quantity, minimum, price) < 0:
                    raise ValueError("Vérifie les valeurs saisies.")
                create_product(token, merchant_id, name, sku, quantity, minimum, price)
                flash("Produit enregistré.", "success")
                return redirect(url_for("products"))
            except (ValueError, TypeError):
                flash("Données invalides : vérifie le nom, les quantités et le prix.", "error")
            except Exception:
                app.logger.exception("Product creation failed")
                flash("Impossible d'enregistrer le produit. Réessaie.", "error")
        try:
            rows = list_products(token, merchant_id)
        except Exception:
            app.logger.exception("Product listing failed")
            rows = []
            flash("Impossible de charger les produits pour le moment.", "error")
        return render_template("products.html", products=rows)

    @app.route("/stock", methods=["GET", "POST"])
    @login_required
    def stock():
        token = g.auth_record["access_token"]
        merchant_id = session["merchant_id"]
        if request.method == "POST":
            try:
                product_id = request.form.get("product_id", "")
                movement_type = request.form.get("movement_type", "")
                quantity = int(request.form.get("quantity", "0"))
                note = request.form.get("note", "").strip()[:250]
                if movement_type not in ("IN", "OUT") or quantity <= 0 or not product_id:
                    raise ValueError("Mouvement invalide.")
                adjust_stock(token, merchant_id, product_id, movement_type, quantity, note)
                flash("Mouvement de stock enregistré.", "success")
                return redirect(url_for("stock"))
            except (ValueError, TypeError):
                flash("Vérifie le produit, le type et la quantité.", "error")
            except Exception:
                app.logger.exception("Stock movement failed")
                flash("Mouvement refusé : stock insuffisant ou produit introuvable.", "error")
        try:
            rows = list_products(token, merchant_id)
            movements = list_stock_movements(token, merchant_id)
        except Exception:
            app.logger.exception("Stock page load failed")
            rows, movements = [], []
            flash("Impossible de charger le stock.", "error")
        return render_template("stock.html", products=rows, movements=movements)

    @app.route("/sales", methods=["GET", "POST"])
    @login_required
    def sales():
        token = g.auth_record["access_token"]
        merchant_id = session["merchant_id"]
        if request.method == "POST":
            try:
                product_id = request.form.get("product_id", "")
                quantity = int(request.form.get("quantity", "0"))
                if not product_id or quantity <= 0:
                    raise ValueError("Vente invalide.")
                create_sale(token, merchant_id, [{"product_id": product_id, "quantity": quantity}])
                flash("Vente enregistrée et stock mis à jour.", "success")
                return redirect(url_for("sales"))
            except (ValueError, TypeError):
                flash("Vérifie le produit et la quantité.", "error")
            except Exception:
                app.logger.exception("Sale creation failed")
                flash("Vente refusée : vérifie le stock disponible et réessaie.", "error")
        try:
            rows = list_products(token, merchant_id)
            history = list_sales(token, merchant_id)
        except Exception:
            app.logger.exception("Sales page load failed")
            rows, history = [], []
            flash("Impossible de charger les ventes.", "error")
        return render_template("sales.html", products=rows, sales=history)
