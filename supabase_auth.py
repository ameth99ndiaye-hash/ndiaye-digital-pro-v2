"""Helpers for Supabase Auth and merchant-scoped data access."""
import os

from supabase_client import create_supabase_client


def supabase_auth_enabled():
    return os.getenv("SUPABASE_AUTH_ENABLED", "0") == "1"


def _session(response):
    return getattr(response, "session", None)


def _user(response):
    return getattr(response, "user", None)


def sign_up(email, password, shop_name, owner_name):
    client = create_supabase_client()
    if client is None:
        raise RuntimeError("Supabase is not configured")
    response = client.auth.sign_up({
        "email": email,
        "password": password,
        "options": {"data": {"shop_name": shop_name, "owner_name": owner_name}},
    })
    return client, _user(response), _session(response)


def sign_in(email, password):
    client = create_supabase_client()
    if client is None:
        raise RuntimeError("Supabase is not configured")
    response = client.auth.sign_in_with_password({"email": email, "password": password})
    return client, _user(response), _session(response)


def merchant_for_user(client, user, access_token):
    """Read or create the merchant profile under the authenticated user's RLS scope."""
    client.postgrest.auth(access_token)
    rows = (
        client.table("merchants")
        .select("id,shop_name")
        .eq("owner_id", str(user.id))
        .limit(1)
        .execute()
        .data
    )
    if rows:
        return rows[0]

    metadata = getattr(user, "user_metadata", None) or {}
    shop_name = (metadata.get("shop_name") or "Ma boutique").strip()[:120]
    created = client.table("merchants").insert({
        "owner_id": str(user.id),
        "shop_name": shop_name,
    }).execute().data
    if not created:
        raise RuntimeError("Merchant profile could not be created")
    return created[0]


def refresh_auth_session(refresh_token):
    client = create_supabase_client()
    if client is None:
        raise RuntimeError("Supabase is not configured")
    response = client.auth.refresh_session(refresh_token)
    session = _session(response)
    if session is None:
        raise RuntimeError("Supabase session refresh failed")
    return session


def merchant_counts(access_token, merchant_id):
    client = create_supabase_client(access_token=access_token)
    if client is None:
        return {"products": 0, "sales": 0}
    products = (
        client.table("products").select("id")
        .eq("merchant_id", str(merchant_id)).execute().data
    )
    sales = (
        client.table("sales").select("id")
        .eq("merchant_id", str(merchant_id)).execute().data
    )
    return {"products": len(products), "sales": len(sales)}


def list_products(access_token, merchant_id):
    client = create_supabase_client(access_token=access_token)
    return (client.table("products").select("id,name,sku,quantity,min_quantity,unit_price,created_at")
            .eq("merchant_id", str(merchant_id)).order("created_at", desc=True).execute().data)


def create_product(access_token, merchant_id, name, sku, quantity, min_quantity, unit_price):
    client = create_supabase_client(access_token=access_token)
    return client.table("products").insert({
        "merchant_id": str(merchant_id), "name": name, "sku": sku or None,
        "quantity": quantity, "min_quantity": min_quantity, "unit_price": unit_price,
    }).execute().data


def adjust_stock(access_token, merchant_id, product_id, movement_type, quantity, note):
    client = create_supabase_client(access_token=access_token)
    return client.rpc("adjust_merchant_stock", {
        "p_merchant_id": str(merchant_id),
        "p_product_id": str(product_id),
        "p_movement_type": movement_type,
        "p_quantity": quantity,
        "p_note": note or "",
    }).execute().data


def list_stock_movements(access_token, merchant_id):
    client = create_supabase_client(access_token=access_token)
    return (client.table("stock_movements")
            .select("id,product_id,movement_type,quantity,note,created_at,products(name)")
            .eq("merchant_id", str(merchant_id)).order("created_at", desc=True).limit(50).execute().data)


def create_sale(access_token, merchant_id, items):
    client = create_supabase_client(access_token=access_token)
    return client.rpc("create_merchant_sale", {
        "p_merchant_id": str(merchant_id), "p_items": items
    }).execute().data


def list_sales(access_token, merchant_id):
    client = create_supabase_client(access_token=access_token)
    return (client.table("sales").select("id,total,currency,status,created_at")
            .eq("merchant_id", str(merchant_id)).order("created_at", desc=True).limit(50).execute().data)
