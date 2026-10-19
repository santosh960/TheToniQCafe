# The ToniQ Cafe

A responsive cafe website with four public pages, a Python/Flask backend, a SQLite database, and a protected content-management dashboard.

## Features

- Public pages: Home (`/`), Menu (`/menu`), About & Gallery (`/about`), and Contact (`/contact`).
- Admin dashboard (`/admin`) for menu products, categories, gallery images, business details, and private contact enquiries.
- SQLite schema and initial demo catalog via `schema.sql` and a Flask CLI command.
- Password-hashed admin accounts, signed sessions, CSRF tokens, login-attempt throttling, validated forms, honeypot spam field, and private enquiry management.
- Locally stored, size-limited JPG/PNG/WebP uploads with randomized names, decoded/validated and resized/optimized to WebP. SVG and executable uploads are not accepted.
- Demo products and prices are explicitly marked until confirmed; online ordering and payments are not implemented or advertised.
- Responsive layouts, accessible navigation, reduced-motion support, page metadata, and LocalBusiness structured data using the supplied business information.

## Requirements

- Python 3.10+
- pip
- A persistent local filesystem for SQLite and uploaded images (or migrate those assets to managed storage before using ephemeral hosting)

There are no required API keys or payment services. Google Maps directions are linked as a normal external URL, and Google Fonts are an optional external font resource with local system-font fallbacks.

## Local setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set a unique random `SECRET_KEY` in `.env` (or leave it blank during local development to use an ephemeral key). For a one-off local shell:

```sh
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export DATABASE_PATH="instance/toniQ.sqlite3"
```

The application loads a local `.env` file if present, without overriding already-set environment variables. The development server creates an ephemeral secret if `SECRET_KEY` is omitted; this invalidates sessions on restart and must never be used in production. With `APP_ENV=production`, a missing or too-short secret prevents startup. Set `COOKIE_SECURE=1` behind HTTPS.

Initialize the database and create the first administrator:

```sh
flask --app app init-db
flask --app app create-admin
```

The first command creates tables and inserts explicitly labeled demo products. The second prompts for a username and password (minimum 12 characters); there is no default admin account.

Run locally:

```sh
flask --app app run --debug
```

Open `http://127.0.0.1:5000`. Admin sign-in is at `/admin`.

## Production deployment

1. Deploy on a host that supports Python WSGI and persistent storage, install `requirements.txt`, and configure a strong `SECRET_KEY`, `APP_ENV=production`, `COOKIE_SECURE=1`, and an absolute persistent `DATABASE_PATH`.
2. Run `flask --app app init-db` once as a deployment/release step, then create the admin with `flask --app app create-admin` through a private console.
3. Serve the app behind HTTPS with a production WSGI server, for example `gunicorn --workers 2 --bind 0.0.0.0:8000 app:app`.
4. Back up the SQLite database and `static/uploads/`. The built-in SQLite/file-storage approach is appropriate for a single-host low-traffic deployment; use managed PostgreSQL and object storage for multi-instance or higher-traffic hosting.
5. Configure platform-level request limits and monitoring. If the app is behind a trusted reverse proxy, set `TRUSTED_PROXY_HOPS` to its exact hop count (normally `1`) and ensure that proxy overwrites forwarded IP/protocol headers. It defaults to `0`; never trust arbitrary client-provided forwarded headers. Contact submissions are retained in the admin dashboard; this application intentionally does not email, text, or otherwise transmit their contents to a third party.

Do not commit `.env`, the SQLite database, or uploaded customer/business files. Admin pages and enquiry endpoints depend on Flask session security, CSRF protection, and database checks—not merely hidden UI.

## Data and content notes

- The address, phone number, 4.8/5 rating from 50 reviews, and dine-in/kerbside pickup services are the facts supplied by the business brief.
- Opening hours are explicitly labeled as needing confirmation until verified in the dashboard.
- Demo menu entries/prices must be confirmed by the cafe. Edit each item in the dashboard and uncheck “Mark as demo” only after the cafe confirms its details and price.
- Gallery placeholders are original CSS illustrations, not photographs of this cafe. Authentic cafe images and descriptive alt text can be uploaded in the dashboard.
- No customer testimonials, founding date, owner biography, unverified awards, online ordering, or online payments are claimed.
- Instagram is omitted from the public site until the owner enters and verifies a profile URL.

## Database

`schema.sql` creates `admin_users`, `admin_login_attempts`, `categories`, `products`, `gallery_images`, `site_settings`, and `contact_enquiries`, including foreign keys, checks, and indexes. The database is SQLite and initializes with foreign-key enforcement. Product and gallery writes, enquiry storage, and site settings are implemented in Flask routes. Uploaded images are checked and optimized to WebP using Pillow. The dashboard is protected by authenticated sessions; enquiries are not exposed by public routes.

## Verification

Run the automated route and workflow tests with:

```sh
python3 -m unittest discover -s tests -v
```

No online ordering or payment workflow is included. Add either only after the cafe confirms operational support and a suitable payment/order provider is configured and tested.
