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
