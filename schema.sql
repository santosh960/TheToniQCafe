PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_login_attempts (
    id INTEGER PRIMARY KEY,
    ip_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS admin_login_rate_idx ON admin_login_attempts(ip_hash, created_at);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK(length(name) BETWEEN 1 AND 80),
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
    description TEXT NOT NULL DEFAULT '' CHECK(length(description) <= 1000),
    price REAL NOT NULL DEFAULT 0 CHECK(price >= 0),
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    image TEXT NOT NULL DEFAULT '',
    allergens TEXT NOT NULL DEFAULT '' CHECK(length(allergens) <= 300),
    featured INTEGER NOT NULL DEFAULT 0 CHECK(featured IN (0, 1)),
    available INTEGER NOT NULL DEFAULT 0 CHECK(available IN (0, 1)),
    demo INTEGER NOT NULL DEFAULT 1 CHECK(demo IN (0, 1)),
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS products_public_idx ON products(available, featured, position);
CREATE INDEX IF NOT EXISTS products_category_idx ON products(category_id);

CREATE TABLE IF NOT EXISTS gallery_images (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 120),
    alt_text TEXT NOT NULL DEFAULT '' CHECK(length(alt_text) <= 200),
    image TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS site_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_enquiries (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    contact TEXT NOT NULL CHECK(length(contact) BETWEEN 3 AND 254),
    message TEXT NOT NULL CHECK(length(message) BETWEEN 1 AND 3000),
    ip_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'read', 'resolved')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS enquiries_recent_idx ON contact_enquiries(created_at DESC);
CREATE INDEX IF NOT EXISTS enquiries_rate_idx ON contact_enquiries(ip_hash, created_at);

INSERT OR IGNORE INTO site_settings (key, value) VALUES
    ('business_name', 'The ToniQ Cafe'),
    ('phone', '077090 98221'),
    ('address', 'DP Road, opposite Aamchi Hotel, United Western Co-Operative Society, Ganesh Nagar, Karvenagar, Pune, Maharashtra 411052'),
    ('instagram_url', ''),
    ('about_text', 'A neighborhood cafe for good coffee, crafted beverages, and a cozy pause in your day. Come by, settle in, and find your own ToniQ.'),
    ('opening_hours', 'Please contact the cafe to confirm current opening hours.'),
    ('hours_confirmed', '0'),
    ('ordering_enabled', '0');

INSERT OR IGNORE INTO categories (name, position) VALUES
    ('Hot Coffee', 1),
    ('Cold Coffee', 2),
    ('Specialty Drinks', 3),
    ('Chocolate Drinks', 4),
    ('Other Beverages', 5);
