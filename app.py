import hashlib
import os
import re
import secrets
import sqlite3
from datetime import timedelta
from functools import wraps
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", ""),
        DATABASE=os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / "toniQ.sqlite3")),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    if test_config:
        app.config.update(test_config)
    elif not app.config["SECRET_KEY"]:
        if os.environ.get("APP_ENV") == "production":
            raise RuntimeError("Set a unique SECRET_KEY of at least 32 characters before starting in production.")
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning("Using an ephemeral development SECRET_KEY; set SECRET_KEY before deployment.")
    elif os.environ.get("APP_ENV") == "production" and len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Production SECRET_KEY must contain at least 32 characters.")
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "static" / "uploads").mkdir(parents=True, exist_ok=True)
    proxy_hops = int(os.environ.get("TRUSTED_PROXY_HOPS", "0"))
    if proxy_hops < 0 or proxy_hops > 5:
        raise RuntimeError("TRUSTED_PROXY_HOPS must be between 0 and 5.")
    if proxy_hops:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_hops, x_proto=proxy_hops)

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def csrf_token():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_urlsafe(32)
        return session["_csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_posts():
        if request.method == "POST":
            supplied = request.form.get("_csrf_token", "")
            expected = session.get("_csrf_token", "")
            if not expected or not secrets.compare_digest(supplied, expected):
                abort(400, description="Your form session expired. Please refresh and try again.")

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("admin_id"):
                return redirect(url_for("admin_login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def settings():
        return {row["key"]: row["value"] for row in get_db().execute("SELECT key, value FROM site_settings")}

    def public_products(featured=False):
        sql = """SELECT p.*, c.name AS category_name FROM products p
                 LEFT JOIN categories c ON c.id = p.category_id WHERE p.available = 1"""
        if featured:
            sql += " AND p.featured = 1"
        return get_db().execute(sql + " ORDER BY p.position, p.name").fetchall()

    @app.context_processor
    def inject_globals():
        return {"site": settings(), "admin_logged_in": bool(session.get("admin_id"))}

    @app.cli.command("init-db")
    def init_db_command():
        """Create tables and insert clearly labeled demo menu items."""
        db = get_db()
        db.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
        if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            categories = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM categories")}
            samples = [
                ("House Cappuccino", "A demo listing for a classic espresso-and-milk favorite.", 180, "Hot Coffee", "coffee"),
                ("Iced Latte", "A demo listing with chilled espresso and creamy milk.", 210, "Cold Coffee", "latte"),
                ("Caramel Cloud", "A demo specialty drink listing. Final recipe to be confirmed.", 240, "Specialty Drinks", "caramel"),
                ("Velvet Hot Chocolate", "A demo chocolate drink listing. Final recipe to be confirmed.", 220, "Chocolate Drinks", "chocolate"),
                ("Coconut Chill", "A demo iced beverage listing. Final recipe to be confirmed.", 230, "Other Beverages", "coconut"),
                ("Hazelnut Frappe", "A demo frappe listing. Final recipe to be confirmed.", 250, "Cold Coffee", "frappe"),
            ]
            for position, (name, description, price, category, artwork) in enumerate(samples, 1):
                db.execute(
                    """INSERT INTO products
                       (name, description, price, category_id, image, allergens, featured, available, demo, position)
                       VALUES (?, ?, ?, ?, ?, '', ?, 1, 1, ?)""",
                    (name, description, price, categories[category], artwork, int(position <= 3), position),
                )
        db.commit()
        print("Database initialized with demo items. Demo menu values must be confirmed by the cafe.")

    @app.cli.command("create-admin")
    def create_admin_command():
        """Create or update an admin account using interactive terminal prompts."""
        import getpass
        username = input("Admin username: ").strip()
        password = getpass.getpass("Admin password (12+ characters): ")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username) or len(password) < 12:
            raise SystemExit("Use a 3-40 character username and a password of at least 12 characters.")
        db = get_db()
        db.execute(
            "INSERT INTO admin_users(username, password_hash) VALUES (?, ?) "
            "ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash",
            (username, generate_password_hash(password)),
        )
        db.commit()
        print("Admin account saved.")

    def categories():
        return get_db().execute("SELECT * FROM categories ORDER BY position, name").fetchall()

    @app.get("/")
    def home():
        return render_template("home.html", products=public_products(featured=True))

    @app.get("/menu")
    def menu():
        return render_template(
            "menu.html", products=public_products(), categories=categories(),
            selected=request.args.get("category", ""), query=request.args.get("q", ""),
        )

    @app.get("/about")
    def about():
        images = get_db().execute("SELECT * FROM gallery_images ORDER BY position, id").fetchall()
        return render_template("about.html", images=images)

    @app.get("/contact")
    def contact():
        return render_template("contact.html")

    @app.post("/contact")
    def submit_contact():
        name = request.form.get("name", "").strip()
        contact_value = request.form.get("contact", "").strip()
        message = request.form.get("message", "").strip()
        if request.form.get("website", "").strip():
            abort(400, description="Unable to submit this form.")
        errors = []
        if not 1 <= len(name) <= 100:
            errors.append("Please enter your name (up to 100 characters).")
        if not 3 <= len(contact_value) <= 254 or not (
            re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact_value)
            or re.fullmatch(r"[+0-9() .-]{7,25}", contact_value)
        ):
            errors.append("Enter a valid email address or phone number.")
        if not 1 <= len(message) <= 3000:
            errors.append("Please add a message (up to 3,000 characters).")
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("contact.html", form=request.form), 400
        db = get_db()
        ip_hash = hashlib.sha256(
            (app.config["SECRET_KEY"] + request.remote_addr if request.remote_addr else app.config["SECRET_KEY"]).encode()
        ).hexdigest()
        recent = db.execute(
            "SELECT COUNT(*) FROM contact_enquiries WHERE ip_hash=? AND created_at >= datetime('now', '-1 hour')",
            (ip_hash,),
        ).fetchone()[0]
        if recent >= 5:
            flash("Please wait before sending another message.", "error")
            return render_template("contact.html", form=request.form), 429
        db.execute(
            "INSERT INTO contact_enquiries (name, contact, message, ip_hash) VALUES (?, ?, ?, ?)",
            (name, contact_value, message, ip_hash),
        )
        db.commit()
        flash("Thanks for reaching out. Your message has been recorded for the cafe.", "success")
        return redirect(url_for("contact"))

    @app.get("/admin")
    def admin_login():
        if session.get("admin_id"):
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html")

    @app.post("/admin/login")
    def admin_authenticate():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        ip_hash = hashlib.sha256(
            (app.config["SECRET_KEY"] + (request.remote_addr or "")).encode()
        ).hexdigest()
        db = get_db()
        recent = db.execute(
            "SELECT COUNT(*) FROM admin_login_attempts WHERE ip_hash=? AND created_at >= datetime('now', '-15 minutes')",
            (ip_hash,),
        ).fetchone()[0]
        if recent >= 10:
            flash("Too many sign-in attempts. Please wait before trying again.", "error")
            return render_template("admin_login.html"), 429
        user = get_db().execute("SELECT * FROM admin_users WHERE username=?", (username,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            db.execute("INSERT INTO admin_login_attempts (ip_hash) VALUES (?)", (ip_hash,))
            db.commit()
            flash("The username or password was not recognized.", "error")
            return render_template("admin_login.html"), 401
        db.execute("DELETE FROM admin_login_attempts WHERE ip_hash=?", (ip_hash,))
        db.commit()
        session.clear()
        session["admin_id"] = user["id"]
        session["admin_username"] = user["username"]
        session.permanent = True
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/logout")
    @admin_required
    def admin_logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("admin_login"))

    @app.get("/admin/dashboard")
    @admin_required
    def admin_dashboard():
        db = get_db()
        products = db.execute(
            """SELECT p.*, c.name AS category_name FROM products p
               LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.position, p.name"""
        ).fetchall()
        enquiries = db.execute("SELECT * FROM contact_enquiries ORDER BY created_at DESC LIMIT 100").fetchall()
        return render_template(
            "admin.html", products=products, categories=categories(), enquiries=enquiries,
            gallery=db.execute("SELECT * FROM gallery_images ORDER BY position, id").fetchall(),
            settings=settings(),
        )

    def form_value(key, limit, required=False):
        value = request.form.get(key, "").strip()
        if len(value) > limit or (required and not value):
            raise ValueError(f"Check the {key.replace('_', ' ')} field.")
        return value

    def save_upload(field):
        file = request.files.get(field)
        if not file or not file.filename:
            return None
        filename = secure_filename(file.filename)
        extension = Path(filename).suffix.lower()
        content = file.read(app.config["MAX_CONTENT_LENGTH"] + 1)
        expected_formats = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
        if len(content) > app.config["MAX_CONTENT_LENGTH"] or extension not in expected_formats:
            raise ValueError("Upload a valid JPG, PNG, or WebP image smaller than 5 MB.")
        try:
            with Image.open(BytesIO(content)) as uploaded:
                if uploaded.format != expected_formats[extension] or uploaded.width * uploaded.height > 40_000_000:
                    raise ValueError("Upload a valid JPG, PNG, or WebP image smaller than 5 MB.")
                uploaded.verify()
            with Image.open(BytesIO(content)) as uploaded:
                optimized = ImageOps.exif_transpose(uploaded)
                optimized.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
                optimized = optimized.convert("RGBA" if "A" in optimized.getbands() else "RGB")
                output = BytesIO()
                optimized.save(output, format="WEBP", quality=84, method=6)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError("That file is not a supported, readable image.") from error
        name = f"{uuid4().hex}.webp"
        destination = BASE_DIR / "static" / "uploads" / name
        destination.write_bytes(output.getvalue())
        return f"uploads/{name}"

    def delete_upload(path):
        if path and path.startswith("uploads/"):
            target = (BASE_DIR / "static" / path).resolve()
            if target.parent == (BASE_DIR / "static" / "uploads").resolve() and target.is_file():
                target.unlink()

    @app.post("/admin/products/save")
    @admin_required
    def save_product():
        db = get_db()
        product_id = request.form.get("id", "").strip()
        try:
            name = form_value("name", 120, True)
            description = form_value("description", 1000)
            allergens = form_value("allergens", 300)
            price_text = request.form.get("price", "").strip()
            if not re.fullmatch(r"\d{1,7}(?:\.\d{1,2})?", price_text):
                raise ValueError("Price must be a non-negative amount with up to two decimal places.")
            category_id = request.form.get("category_id", "").strip()
            category_id = int(category_id) if category_id else None
            if category_id and not db.execute("SELECT 1 FROM categories WHERE id=?", (category_id,)).fetchone():
                raise ValueError("Choose an existing category.")
            position_text = request.form.get("position", "0").strip()
            if not position_text.isdigit() or int(position_text) > 100000:
                raise ValueError("Sort order must be a whole number.")
            upload = save_upload("image")
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("admin_dashboard") + "#products")
        existing = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone() if product_id.isdigit() else None
        selected_image = request.form.get("image", "coffee").strip()
        allowed_art = {"coffee", "latte", "caramel", "chocolate", "coconut", "frappe"}
        if selected_image not in allowed_art and not (
            existing and selected_image == existing["image"] and selected_image.startswith("uploads/")
        ):
            if upload:
                delete_upload(upload)
            flash("Choose an available illustration style or keep the current uploaded image.", "error")
            return redirect(url_for("admin_dashboard") + "#products")
        image = upload or selected_image
        values = (
            name, description, float(price_text), category_id, image, allergens,
            int(request.form.get("featured") == "on"), int(request.form.get("available") == "on"),
            int(request.form.get("demo") == "on"), int(position_text),
        )
        if existing:
            db.execute(
                """UPDATE products SET name=?, description=?, price=?, category_id=?, image=?, allergens=?,
                   featured=?, available=?, demo=?, position=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (*values, existing["id"]),
            )
            if upload and existing["image"] != image:
                delete_upload(existing["image"])
        else:
            db.execute(
                """INSERT INTO products
                   (name, description, price, category_id, image, allergens, featured, available, demo, position)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", values,
            )
        db.commit()
        flash("Menu item saved.", "success")
        return redirect(url_for("admin_dashboard") + "#products")

    @app.post("/admin/products/<int:product_id>/delete")
    @admin_required
    def delete_product(product_id):
        db = get_db()
        product = db.execute("SELECT image FROM products WHERE id=?", (product_id,)).fetchone()
        if product is None:
            abort(404)
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
        db.commit()
        delete_upload(product["image"])
        flash("Menu item deleted.", "success")
        return redirect(url_for("admin_dashboard") + "#products")

    @app.post("/admin/categories/save")
    @admin_required
    def save_category():
        db = get_db()
        try:
            name = form_value("name", 80, True)
            position = request.form.get("position", "0")
            if not position.isdigit() or int(position) > 100000:
                raise ValueError("Sort order must be a whole number.")
            category_id = request.form.get("id", "").strip()
            if category_id.isdigit():
                db.execute("UPDATE categories SET name=?, position=? WHERE id=?", (name, int(position), int(category_id)))
            else:
                db.execute("INSERT INTO categories (name, position) VALUES (?, ?)", (name, int(position)))
            db.commit()
            flash("Category saved.", "success")
        except (ValueError, sqlite3.IntegrityError) as error:
            flash(str(error) or "That category already exists.", "error")
        return redirect(url_for("admin_dashboard") + "#categories")

    @app.post("/admin/categories/<int:category_id>/delete")
    @admin_required
    def delete_category(category_id):
        db = get_db()
        db.execute("DELETE FROM categories WHERE id=?", (category_id,))
        db.commit()
        flash("Category deleted. Its menu items remain uncategorized.", "success")
        return redirect(url_for("admin_dashboard") + "#categories")

    @app.post("/admin/gallery/save")
    @admin_required
    def save_gallery():
        try:
            title = form_value("title", 120, True)
            alt = form_value("alt_text", 200)
            position = request.form.get("position", "0")
            if not position.isdigit() or int(position) > 100000:
                raise ValueError("Sort order must be a whole number.")
            image = save_upload("image")
            if not image:
                raise ValueError("Choose an image to upload.")
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("admin_dashboard") + "#gallery")
        db = get_db()
        db.execute(
            "INSERT INTO gallery_images (title, alt_text, image, position) VALUES (?, ?, ?, ?)",
            (title, alt, image, int(position)),
        )
        db.commit()
        flash("Gallery image added.", "success")
        return redirect(url_for("admin_dashboard") + "#gallery")

    @app.post("/admin/gallery/<int:image_id>/delete")
    @admin_required
    def delete_gallery(image_id):
        db = get_db()
        image = db.execute("SELECT image FROM gallery_images WHERE id=?", (image_id,)).fetchone()
        if image is None:
            abort(404)
        db.execute("DELETE FROM gallery_images WHERE id=?", (image_id,))
        db.commit()
        delete_upload(image["image"])
        flash("Gallery image removed.", "success")
        return redirect(url_for("admin_dashboard") + "#gallery")

    @app.post("/admin/settings")
    @admin_required
    def update_settings():
        allowed = {
            "business_name": 100, "phone": 30, "address": 300, "instagram_url": 300,
            "about_text": 1200, "opening_hours": 500,
        }
        db = get_db()
        try:
            values = {key: form_value(key, limit, key in {"business_name", "phone", "address"})
                      for key, limit in allowed.items()}
            instagram = values["instagram_url"]
            if instagram and not re.fullmatch(r"https://(www\.)?instagram\.com/[A-Za-z0-9._]+/?", instagram):
                raise ValueError("Instagram link must be a valid https://instagram.com profile URL.")
            phone_digits = re.sub(r"\D", "", values["phone"])
            if not 7 <= len(phone_digits) <= 15:
                raise ValueError("Enter a valid phone number.")
            values["hours_confirmed"] = "1" if request.form.get("hours_confirmed") == "on" else "0"
            for key, value in values.items():
                db.execute(
                    "INSERT INTO site_settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                    (key, value),
                )
            db.commit()
            flash("Cafe details updated.", "success")
        except ValueError as error:
            flash(str(error), "error")
        return redirect(url_for("admin_dashboard") + "#settings")

    @app.post("/admin/enquiries/<int:enquiry_id>/status")
    @admin_required
    def update_enquiry(enquiry_id):
        status = request.form.get("status", "")
        if status not in {"new", "read", "resolved"}:
            abort(400, description="Invalid enquiry status.")
        db = get_db()
        cursor = db.execute("UPDATE contact_enquiries SET status=? WHERE id=?", (status, enquiry_id))
        if cursor.rowcount == 0:
            abort(404)
        db.commit()
        flash("Enquiry status updated.", "success")
        return redirect(url_for("admin_dashboard") + "#enquiries")

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", message=getattr(error, "description", "Please check your request and try again.")), 400

    @app.errorhandler(413)
    def upload_too_large(_error):
        return render_template("error.html", message="That upload is too large. Images must be smaller than 5 MB."), 413

    return app


app = create_app()

if __name__ == "__main__":
    app.run()
