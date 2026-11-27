import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as application


class NdiayeDigitalProTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        application.DB = Path(self.temp_dir.name) / "test.db"
        application.init_db()
        application.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            WTF_CSRF_ENABLED=False,
        )
        self.client = application.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def login_as_merchant(self):
        with self.client.session_transaction() as sess:
            sess["merchant_id"] = "merchant-uuid-test"
            sess["shop_name"] = "Boutique Test"
            sess["auth_sid"] = "sid-test"

    def supabase_session(self):
        return patch.object(application, "supabase_auth_enabled", return_value=True), patch.object(
            application, "load_auth_session", return_value={"access_token": "test-access-token"}
        )

    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Votre commerce", response.data)

    def test_public_registration_is_disabled(self):
        response = self.client.post(
            "/register",
            data={
                "shop_name": "Boutique Test",
                "owner_name": "Test User",
                "email": "test@example.com",
                "password": "motdepasse123",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_admin_payment_and_subscription_pages_require_admin(self):
        for path in ("/admin/payments", "/admin/subscriptions"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401, path)

    def test_subscription_page_requires_login(self):
        response = self.client.get("/subscription")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_commerce_pages_require_login(self):
        for path in ("/products", "/stock", "/sales"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401, path)

    def test_supabase_product_page_is_merchant_scoped(self):
        self.login_as_merchant()
        with patch.object(application, "supabase_auth_enabled", return_value=True), \
             patch.object(application, "load_auth_session", return_value={"access_token": "token"}), \
             patch("commerce_routes.list_products", return_value=[]) as list_mock:
            response = self.client.get("/products")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ajouter un produit", response.data)
        list_mock.assert_called_once_with("token", "merchant-uuid-test")

    def test_product_creation_uses_current_merchant(self):
        self.login_as_merchant()
        with patch.object(application, "supabase_auth_enabled", return_value=True), \
             patch.object(application, "load_auth_session", return_value={"access_token": "token"}), \
             patch("commerce_routes.create_product", return_value=[{"id": "product-1"}]) as create_mock, \
             patch("commerce_routes.list_products", return_value=[]):
            response = self.client.post("/products", data={
                "name": "Riz", "sku": "RIZ-1", "quantity": "10",
                "min_quantity": "2", "unit_price": "500",
            })
        self.assertEqual(response.status_code, 302)
        create_mock.assert_called_once_with("token", "merchant-uuid-test", "Riz", "RIZ-1", 10, 2, 500)

    def test_stock_page_loads_for_current_merchant(self):
        self.login_as_merchant()
        with patch.object(application, "supabase_auth_enabled", return_value=True), \
             patch.object(application, "load_auth_session", return_value={"access_token": "token"}), \
             patch("commerce_routes.list_products", return_value=[]), \
             patch("commerce_routes.list_stock_movements", return_value=[]) as movements_mock:
            response = self.client.get("/stock")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mouvements de stock", response.data)
        movements_mock.assert_called_once_with("token", "merchant-uuid-test")

    def test_stock_adjustment_uses_rpc_for_current_merchant(self):
        self.login_as_merchant()
        with patch.object(application, "supabase_auth_enabled", return_value=True), \
             patch.object(application, "load_auth_session", return_value={"access_token": "token"}), \
             patch("commerce_routes.adjust_stock", return_value=None) as adjust_mock, \
             patch("commerce_routes.list_products", return_value=[]), \
             patch("commerce_routes.list_stock_movements", return_value=[]):
            response = self.client.post("/stock", data={
                "product_id": "product-uuid", "movement_type": "IN",
                "quantity": "5", "note": "Réception",
            })
        self.assertEqual(response.status_code, 302)
        adjust_mock.assert_called_once_with("token", "merchant-uuid-test", "product-uuid", "IN", 5, "Réception")

    def test_sales_page_loads_for_current_merchant(self):
        self.login_as_merchant()
        with patch.object(application, "supabase_auth_enabled", return_value=True), \
             patch.object(application, "load_auth_session", return_value={"access_token": "token"}), \
             patch("commerce_routes.list_products", return_value=[]), \
             patch("commerce_routes.list_sales", return_value=[]) as sales_mock:
            response = self.client.get("/sales")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enregistrer une vente", response.data)
        sales_mock.assert_called_once_with("token", "merchant-uuid-test")

    def test_sale_creation_uses_current_merchant(self):
        self.login_as_merchant()
        with patch.object(application, "supabase_auth_enabled", return_value=True), \
             patch.object(application, "load_auth_session", return_value={"access_token": "token"}), \
             patch("commerce_routes.create_sale", return_value={"sale_id": "sale-1"}) as sale_mock, \
             patch("commerce_routes.list_products", return_value=[]), \
             patch("commerce_routes.list_sales", return_value=[]):
            response = self.client.post("/sales", data={
                "product_id": "product-uuid", "quantity": "2",
            })
        self.assertEqual(response.status_code, 302)
        sale_mock.assert_called_once_with("token", "merchant-uuid-test", [
            {"product_id": "product-uuid", "quantity": 2}
        ])

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")
        self.assertIn(response.json["supabase"], {"not_configured", "connected", "unavailable"})

    def test_offline_fallback_page_loads(self):
        response = self.client.get("/offline")
        self.assertEqual(response.status_code, 200)
        self.assertIn("hors connexion".encode(), response.data.lower())

    def test_pwa_manifest_is_available(self):
        response = self.client.get("/static/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'"display": "standalone"', response.data)

    def test_offline_workspace_is_available(self):
        response = self.client.get("/offline-workspace")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"MODE HORS LIGNE", response.data)

    def test_offline_api_requires_login(self):
        for path in ("/api/offline-bootstrap", "/api/offline-sync"):
            response = self.client.get(path) if path.endswith("bootstrap") else self.client.post(path, json={"operations": []})
            self.assertEqual(response.status_code, 401, path)

    def test_offline_bootstrap_returns_current_merchant_snapshot(self):
        self.login_as_merchant()
        with patch.object(application, "supabase_auth_enabled", return_value=True), patch.object(application, "load_auth_session", return_value={"access_token": "token"}), patch.object(application, "list_products", return_value=[{"id": "p1"}]), patch.object(application, "list_stock_movements", return_value=[]), patch.object(application, "list_sales", return_value=[]):
            response = self.client.get("/api/offline-bootstrap")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["merchant_id"], "merchant-uuid-test")
        self.assertEqual(response.json["products"], [{"id": "p1"}])
        self.assertTrue(response.json["csrf_token"])

    def test_offline_sync_uses_current_merchant_token_and_rpc(self):
        from types import SimpleNamespace
        self.login_as_merchant()
        class FakeRpc:
            def execute(self):
                return SimpleNamespace(data={"duplicate": False, "type": "product_create"})
        class FakeClient:
            def __init__(self):
                self.call = None
            def rpc(self, name, params):
                self.call = (name, params)
                return FakeRpc()
        fake = FakeClient()
        operation = {
            "operation_id": "11111111-1111-4111-8111-111111111111",
            "type": "product_create",
            "payload": {"product_id": "22222222-2222-4222-8222-222222222222", "name": "Riz", "sku": "", "quantity": 2, "min_quantity": 0, "unit_price": 500},
        }
        with patch.object(application, "supabase_auth_enabled", return_value=True), patch.object(application, "load_auth_session", return_value={"access_token": "token"}), patch("supabase_client.create_supabase_client", return_value=fake):
            response = self.client.post("/api/offline-sync", json={"operations": [operation]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["results"][0]["ok"])
        self.assertEqual(fake.call[0], "sync_offline_operation")
        self.assertEqual(fake.call[1]["p_merchant_id"], "merchant-uuid-test")

    def test_csrf_blocks_post_without_token(self):
        application.app.config["WTF_CSRF_ENABLED"] = True
        try:
            response = self.client.post(
                "/login", data={"email": "x@example.com", "password": "bad"}
            )
            self.assertEqual(response.status_code, 400)
        finally:
            application.app.config["WTF_CSRF_ENABLED"] = False


if __name__ == "__main__":
    unittest.main()
