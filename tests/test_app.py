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


if __name__ == "__main__":
    unittest.main()
