"""Connexion Supabase côté serveur, sans clé service_role.

Le client est créé à la demande. Les secrets restent dans les variables
d'environnement et ne sont jamais renvoyés par les routes HTTP.
"""
import os


def supabase_configuration():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    if not url or not key or key.startswith("replace-with-"):
        return None
    return url, key


def create_supabase_client(access_token=None):
    config = supabase_configuration()
    if not config:
        return None

    from supabase import create_client

    client = create_client(*config)
    if access_token:
        client.postgrest.auth(access_token)
    return client


def check_supabase_connection():
    """Vérifie le Data API en lecture seule via la table publique des offres."""
    client = create_supabase_client()
    if client is None:
        return "not_configured"

    try:
        client.table("subscription_plans").select("code").limit(1).execute()
        return "connected"
    except Exception:
        # Ne jamais exposer les détails d'erreur ou les identifiants au navigateur.
        return "unavailable"
