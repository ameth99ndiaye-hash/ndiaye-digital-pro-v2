import re
import tempfile
import unittest
from pathlib import Path

import app as application


class NdiayeDigitalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        application.DB = Path(self.tmp.name) / "test.db"
        application.app.config.update(TESTING=True, SECRET_KEY="test-secret-key")
        application.init_db()
        self.client = application.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def csrf(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="_csrf" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def register(self, email, shop):
        token = self.csrf("/register")
        return self.client.post("/register", data={
            "_csrf": token, "shop_name": shop, "owner_name": "Test Owner",
            "email": email, "password": "StrongPass123!"
        }, follow_redirects=True)

    def test_registration_login_and_private_dashboard(self):
        response = self.register("one@example.com", "Shop One")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Shop One", response.data)
        self.client.get("/logout")
        token = self.csrf("/login")
        response = self.client.post("/login", data={
            "_csrf": token, "email": "one@example.com", "password": "StrongPass123!"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Shop One", response.data)

    def test_csrf_rejects_missing_token(self):
        response = self.client.post("/login", data={"email": "x", "password": "y"})
        self.assertEqual(response.status_code, 400)

    def test_products_and_sale_reduce_only_own_stock(self):
        self.register("one@example.com", "Shop One")
        token = self.csrf("/products")
        response = self.client.post("/products", data={
            "_csrf": token, "name": "Test item", "sku": "SKU1",
            "quantity": "5", "min_quantity": "1", "unit_price": "2500"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with application.db() as con:
            product_id = con.execute("SELECT id FROM products").fetchone()[0]
        token = self.csrf("/sales")
        response = self.client.post("/sales", data={
            "_csrf": token, "product_id": str(product_id), "quantity": "2"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with application.db() as con:
            quantity = con.execute("SELECT quantity FROM products WHERE id=?", (product_id,)).fetchone()[0]
            total = con.execute("SELECT total FROM sales").fetchone()[0]
        self.assertEqual(quantity, 3)
        self.assertEqual(total, 5000)


if __name__ == "__main__":
    unittest.main()
