import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import app as application
from supabase_client import check_supabase_connection


class NdiayeDigitalProTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        application.DB = Path(self.temp_dir.name) / "test.db"
        application.init_db()
        application.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = application.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def register(self, email="test@example.com"):
        return self.client.post(
            "/register",
            data={
                "shop_name": "Boutique Test",
                "owner_name": "Test User",
                "email": email,
                "password": "motdepasse123",
            },
            follow_redirects=True,
        )

    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Votre commerce", response.data)

    def test_registration_creates_private_dashboard_session(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Boutique Test", response.data)
        self.assertIn(b"PHASE 1", response.data)

    def test_duplicate_email_is_rejected(self):
        self.register()
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertIn("possède déjà un compte".encode(), response.data)

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_and_logout(self):
        self.register()
        self.client.get("/logout")
        response = self.client.post(
            "/login",
            data={"email": "test@example.com", "password": "motdepasse123"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Boutique Test", response.data)
        self.client.get("/logout")
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")
        self.assertIn(response.json["supabase"], {"not_configured", "connected", "unavailable"})

    def test_supabase_reports_missing_environment_configuration(self):
        with patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_PUBLISHABLE_KEY": ""}):
            self.assertEqual(check_supabase_connection(), "not_configured")


    def test_supabase_auth_session_keeps_tokens_out_of_flask_cookie(self):
        from types import SimpleNamespace
        with application.app.test_request_context("/"):
            fake_auth = SimpleNamespace(
                access_token="access-token-private",
                refresh_token="refresh-token-private",
                expires_at=4102444800,
            )
            merchant = {"id": "merchant-uuid", "shop_name": "Boutique Secure"}
            application.save_auth_session(fake_auth, merchant, "owner@example.com")
            from flask import session
            self.assertNotIn("access_token", session)
            self.assertNotIn("refresh_token", session)
            sid = session["auth_sid"]
            with application.db() as con:
                row = con.execute("SELECT * FROM auth_sessions WHERE sid=?", (sid,)).fetchone()
            self.assertEqual(row["access_token"], "access-token-private")
            self.assertEqual(row["merchant_id"], "merchant-uuid")


    def test_supabase_product_page_is_merchant_scoped(self):
        from unittest.mock import patch
        with self.client.session_transaction() as sess:
            sess["merchant_id"] = "merchant-1"
            sess["shop_name"] = "Boutique Test"
            sess["auth_sid"] = "sid-test"
        with patch.object(application, "supabase_auth_enabled", return_value=True), \
             patch.object(application, "load_auth_session", return_value={"access_token": "token"}), \
             patch.object(application, "list_products", return_value=[]):
            response = self.client.get("/products")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ajouter un produit", response.data)

    def test_supabase_stock_page_loads(self):
        from unittest.mock import patch
        with self.client.session_transaction() as sess:
            sess["merchant_id"] = "merchant-1"
            sess["shop_name"] = "Boutique Test"
            sess["auth_sid"] = "sid-test"
        with patch.object(application, "supabase_auth_enabled", return_value=True), \
             patch.object(application, "load_auth_session", return_value={"access_token": "token"}), \
             patch.object(application, "list_products", return_value=[]), \
             patch.object(application, "list_stock_movements", return_value=[]):
            response = self.client.get("/stock")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mouvements de stock", response.data)

    def test_supabase_sales_page_loads(self):
        from unittest.mock import patch
        with self.client.session_transaction() as sess:
            sess["merchant_id"] = "merchant-1"
            sess["shop_name"] = "Boutique Test"
            sess["auth_sid"] = "sid-test"
        with patch.object(application, "supabase_auth_enabled", return_value=True), \
             patch.object(application, "load_auth_session", return_value={"access_token": "token"}), \
             patch.object(application, "list_products", return_value=[]), \
             patch.object(application, "list_sales", return_value=[]):
            response = self.client.get("/sales")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enregistrer une vente", response.data)


if __name__ == "__main__":
    unittest.main()
