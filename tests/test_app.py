import re
import sqlite3
import tempfile
from contextlib import closing
from io import BytesIO
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from werkzeug.security import generate_password_hash

from app import create_app


class CafeAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database = Path(self.temp_dir.name) / "test.sqlite3"
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key",
            "DATABASE": str(database),
            "SESSION_COOKIE_SECURE": False,
        })
        self.client = self.app.test_client()
        result = self.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        with closing(sqlite3.connect(database)) as db:
            db.execute(
                "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
                ("owner", generate_password_hash("a-long-test-password")),
            )
            db.commit()

    def tearDown(self):
        self.temp_dir.cleanup()

    def csrf_token(self):
        with self.client.session_transaction() as current:
            if "_csrf_token" not in current:
                current["_csrf_token"] = "test-csrf-token"
            return current["_csrf_token"]

    def post_form(self, path, data=None):
        return self.client.post(path, data={"_csrf_token": self.csrf_token(), **(data or {})})

    def sign_in(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        token = re.search(rb'name="_csrf_token" value="([^"]+)"', response.data).group(1).decode()
        return self.client.post("/admin/login", data={
            "_csrf_token": token,
            "username": "owner",
            "password": "a-long-test-password",
        })

    def test_exact_public_pages_render(self):
        for path in ("/", "/menu", "/about", "/contact"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"The ToniQ", response.data)
        self.assertEqual(self.client.get("/unlisted-page").status_code, 404)

    def test_menu_is_seeded_and_demo_pricing_is_labeled(self):
        response = self.client.get("/menu")
        self.assertIn(b"House Cappuccino", response.data)
        self.assertIn(b"DEMO", response.data)
        self.assertIn(b"PRICES NOT CONFIRMED", response.data)

    def test_admin_dashboard_requires_authentication_and_can_edit_menu(self):
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin?", response.headers["Location"])

        self.assertEqual(self.sign_in().status_code, 302)
        dashboard = self.client.get("/admin/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        response = self.post_form("/admin/products/save", {
            "name": "Test Mocha",
            "description": "A test item",
            "price": "175.50",
            "category_id": "4",
            "position": "1",
            "image": "chocolate",
            "demo": "on",
            "available": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(b"Test Mocha", self.client.get("/menu").data)
        with closing(sqlite3.connect(self.app.config["DATABASE"])) as db:
            product_id = db.execute(
                "SELECT id FROM products WHERE name=?", ("Test Mocha",)
            ).fetchone()[0]
        response = self.post_form("/admin/products/save", {
            "id": str(product_id),
            "name": "ToniQ Mocha",
            "description": "Confirmed cafe listing",
            "price": "199.95",
            "category_id": "4",
            "position": "2",
            "image": "chocolate",
            "available": "on",
        })
        self.assertEqual(response.status_code, 302)
        menu = self.client.get("/menu").data
        self.assertIn(b"ToniQ Mocha", menu)
        self.assertIn(b'data-price="\xe2\x82\xb9199.95"', menu)
        response = self.post_form(f"/admin/products/{product_id}/delete")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(b"ToniQ Mocha", self.client.get("/menu").data)

    def test_contact_form_validates_and_persists_enquiry(self):
        invalid = self.post_form("/contact", {
            "name": "Cafe visitor", "contact": "not a contact", "message": "Hello"
        })
        self.assertEqual(invalid.status_code, 400)
        valid = self.post_form("/contact", {
            "name": "Cafe visitor", "contact": "visitor@example.com",
            "message": "Could you share today's menu?",
        })
        self.assertEqual(valid.status_code, 302)
        with closing(sqlite3.connect(self.app.config["DATABASE"])) as db:
            db.row_factory = sqlite3.Row
            enquiry = db.execute("SELECT * FROM contact_enquiries").fetchone()
            self.assertEqual(enquiry["name"], "Cafe visitor")
            self.assertEqual(enquiry["status"], "new")
            self.assertNotIn("visitor@example.com", enquiry["ip_hash"])

    def test_admin_gallery_upload_is_converted_to_webp_and_deletable(self):
        self.assertEqual(self.sign_in().status_code, 302)
        original = BytesIO()
        Image.new("RGB", (80, 60), color="#b77b4a").save(original, format="PNG")
        response = self.post_form("/admin/gallery/save", {
            "title": "Cafe artwork",
            "alt_text": "A test cafe image",
            "position": "1",
            "image": (BytesIO(original.getvalue()), "sample.png"),
        })
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.app.config["DATABASE"])) as db:
            image_id, image_path = db.execute(
                "SELECT id, image FROM gallery_images WHERE title=?", ("Cafe artwork",)
            ).fetchone()
        self.assertTrue(image_path.endswith(".webp"))
        upload_path = Path(self.app.root_path) / "static" / image_path
        self.assertTrue(upload_path.is_file())
        self.assertIn(b"A test cafe image", self.client.get("/about").data)
        response = self.post_form(f"/admin/gallery/{image_id}/delete")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(upload_path.exists())

    def test_csrf_is_required_for_form_submissions(self):
        response = self.client.post("/contact", data={
            "name": "Visitor", "contact": "visitor@example.com", "message": "Hi"
        })
        self.assertEqual(response.status_code, 400)

    def test_production_startup_rejects_missing_or_short_secret(self):
        with patch.dict("os.environ", {"APP_ENV": "production", "SECRET_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "unique SECRET_KEY"):
                create_app()
        with patch.dict("os.environ", {"APP_ENV": "production", "SECRET_KEY": "too-short"}):
            with self.assertRaisesRegex(RuntimeError, "at least 32 characters"):
                create_app()


if __name__ == "__main__":
    unittest.main()
