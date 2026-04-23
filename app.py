import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "kimara_data.sqlite"
INDEX_PATH = BASE_DIR / "index.html"
STATIC_DIR = BASE_DIR / "static"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
SESSION_COOKIE = "kimara_admin_session"
SESSION_DURATION = timedelta(hours=12)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS_HASH = hashlib.sha256(os.environ.get("ADMIN_PASS", "1234").encode("utf-8")).hexdigest()


DEFAULT_SETTINGS = {
    "name": "Lanchonete Kimara",
    "slogan": "Coxinhas e enrolados top",
    "whatsapp": "5531983059830",
    "phoneDisplay": "(31) 98305-9830",
    "address": "Rua Santa Clara, 15 - Mantiqueira, Belo Horizonte - MG, 31652-383",
    "hours": "Segunda a sabado, 08:00 as 20:00",
    "instagram": "@lanchonetekimara",
    "promoTitle": "Combo Kimara",
    "promoText": "2 coxinhas + 2 enrolados + refrigerante por preco especial.",
    "promoPrice": 24.9,
}

DEFAULT_PRODUCTS = [
    ("Coxinha Tradicional", "Frango bem temperado, massa macia e crocante por fora.", 7.0, "Coxinhas", "Mais pedida", 1),
    ("Coxinha com Catupiry", "Recheio cremoso e sabor marcante para quem gosta de capricho.", 8.5, "Coxinhas", "Cremosa", 1),
    ("Enrolado de Presunto e Queijo", "Assado douradinho com recheio generoso e muito sabor.", 6.5, "Enrolados", "Assado", 1),
    ("Enrolado de Salsicha", "Classico da lanchonete, ideal para qualquer hora do dia.", 6.0, "Enrolados", "Favorito", 1),
    ("Mini Salgados - Cento", "Ideal para festas, reunioes e encomendas especiais.", 65.0, "Encomendas", "Encomenda", 1),
]

DEFAULT_DELIVERY_AREAS = [
    ("Mantiqueira", 4.0, "20-30 min"),
    ("Venda Nova", 6.0, "25-35 min"),
    ("Serra Verde", 7.0, "30-40 min"),
    ("Jardim Europa", 8.0, "35-45 min"),
]

TESTIMONIALS = [
    {"id": 1, "name": "Juliana", "text": "A melhor coxinha da regiao. Sempre chega quentinha e muito recheada."},
    {"id": 2, "name": "Carlos", "text": "Os enrolados sao muito bons e os combos valem demais a pena."},
    {"id": 3, "name": "Fernanda", "text": "Pedi para aniversario e foi sucesso. Todo mundo elogiou."},
]


def utc_now():
    return datetime.now(timezone.utc)


def db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    return conn


def init_db():
    with db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price REAL NOT NULL,
                category TEXT NOT NULL,
                badge TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_areas (
                id INTEGER PRIMARY KEY,
                neighborhood TEXT NOT NULL,
                fee REAL NOT NULL,
                eta TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                customer TEXT NOT NULL,
                customer_neighborhood TEXT NOT NULL,
                items TEXT NOT NULL,
                items_label TEXT NOT NULL,
                subtotal REAL NOT NULL,
                delivery_fee REAL NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_sessions (
                token TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )

        if not conn.execute("SELECT id FROM settings WHERE id = 1").fetchone():
            conn.execute(
                "INSERT INTO settings (id, payload, updated_at) VALUES (1, ?, ?)",
                (json.dumps(DEFAULT_SETTINGS, ensure_ascii=False), utc_now().isoformat()),
            )
        if not conn.execute("SELECT id FROM products LIMIT 1").fetchone():
            conn.executemany(
                """
                INSERT INTO products (name, description, price, category, badge, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [(*item, utc_now().isoformat()) for item in DEFAULT_PRODUCTS],
            )
        if not conn.execute("SELECT id FROM delivery_areas LIMIT 1").fetchone():
            conn.executemany(
                "INSERT INTO delivery_areas (neighborhood, fee, eta) VALUES (?, ?, ?)",
                DEFAULT_DELIVERY_AREAS,
            )


def seed_defaults_if_empty():
    seeded = {"products": 0, "deliveryAreas": 0, "settings": 0}
    with db_connection() as conn:
        if not conn.execute("SELECT id FROM settings WHERE id = 1").fetchone():
            conn.execute(
                "INSERT INTO settings (id, payload, updated_at) VALUES (1, ?, ?)",
                (json.dumps(DEFAULT_SETTINGS, ensure_ascii=False), utc_now().isoformat()),
            )
            seeded["settings"] = 1
        if not conn.execute("SELECT id FROM products LIMIT 1").fetchone():
            conn.executemany(
                """
                INSERT INTO products (name, description, price, category, badge, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [(*item, utc_now().isoformat()) for item in DEFAULT_PRODUCTS],
            )
            seeded["products"] = len(DEFAULT_PRODUCTS)
        if not conn.execute("SELECT id FROM delivery_areas LIMIT 1").fetchone():
            conn.executemany(
                "INSERT INTO delivery_areas (neighborhood, fee, eta) VALUES (?, ?, ?)",
                DEFAULT_DELIVERY_AREAS,
            )
            seeded["deliveryAreas"] = len(DEFAULT_DELIVERY_AREAS)
    return seeded


def read_settings(conn):
    settings = DEFAULT_SETTINGS.copy()
    row = conn.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
    if row:
        settings.update(json.loads(row["payload"]))
    return settings


def read_products(conn, active_only=False):
    where = "WHERE active = 1" if active_only else ""
    return [
        dict(row)
        for row in conn.execute(
            f"SELECT id, name, description, price, category, badge, active FROM products {where} ORDER BY id"
        ).fetchall()
    ]


def read_delivery_areas(conn):
    return [dict(row) for row in conn.execute("SELECT id, neighborhood, fee, eta FROM delivery_areas ORDER BY id").fetchall()]


def read_orders(conn):
    rows = conn.execute(
        """
        SELECT id, customer, customer_neighborhood AS customerNeighborhood, items, items_label AS itemsLabel,
               subtotal, delivery_fee AS deliveryFee, total, status, created_at AS createdAt
        FROM orders
        ORDER BY id DESC
        """
    ).fetchall()
    orders = []
    for row in rows:
        item = dict(row)
        item["items"] = json.loads(item["items"])
        orders.append(item)
    return orders


def public_data(include_admin=False):
    with db_connection() as conn:
        payload = {
            "settings": read_settings(conn),
            "products": read_products(conn, active_only=not include_admin),
            "deliveryAreas": read_delivery_areas(conn),
            "testimonials": TESTIMONIALS,
        }
        if include_admin:
            payload["orders"] = read_orders(conn)
        return payload


def normalize_product(item):
    return {
        "id": int(item["id"]) if item.get("id") else None,
        "name": str(item.get("name", "")).strip() or "Produto sem nome",
        "description": str(item.get("description", "")).strip(),
        "price": float(item.get("price") or 0),
        "category": str(item.get("category", "Coxinhas")).strip() or "Coxinhas",
        "badge": str(item.get("badge", "")).strip(),
        "active": 1 if item.get("active") else 0,
    }


def normalize_area(item):
    return {
        "id": int(item["id"]) if item.get("id") else None,
        "neighborhood": str(item.get("neighborhood", "")).strip() or "Bairro",
        "fee": float(item.get("fee") or 0),
        "eta": str(item.get("eta", "")).strip() or "30-40 min",
    }


def save_admin_data(payload):
    settings = DEFAULT_SETTINGS.copy()
    raw_settings = payload.get("settings", {})
    for key in settings:
        value = raw_settings.get(key, settings[key])
        settings[key] = float(value) if key == "promoPrice" else str(value).strip()

    products = [normalize_product(item) for item in payload.get("products", [])]
    areas = [normalize_area(item) for item in payload.get("deliveryAreas", [])]

    with db_connection() as conn:
        conn.execute(
            "UPDATE settings SET payload = ?, updated_at = ? WHERE id = 1",
            (json.dumps(settings, ensure_ascii=False), utc_now().isoformat()),
        )
        product_ids = []
        for product in products:
            if product["id"]:
                conn.execute(
                    """
                    UPDATE products
                    SET name = ?, description = ?, price = ?, category = ?, badge = ?, active = ?
                    WHERE id = ?
                    """,
                    (
                        product["name"],
                        product["description"],
                        product["price"],
                        product["category"],
                        product["badge"],
                        product["active"],
                        product["id"],
                    ),
                )
                product_ids.append(product["id"])
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO products (name, description, price, category, badge, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product["name"],
                        product["description"],
                        product["price"],
                        product["category"],
                        product["badge"],
                        product["active"],
                        utc_now().isoformat(),
                    ),
                )
                product_ids.append(cursor.lastrowid)
        if product_ids:
            placeholders = ",".join("?" for _ in product_ids)
            conn.execute(f"DELETE FROM products WHERE id NOT IN ({placeholders})", product_ids)
        else:
            conn.execute("DELETE FROM products")

        area_ids = []
        for area in areas:
            if area["id"]:
                conn.execute(
                    "UPDATE delivery_areas SET neighborhood = ?, fee = ?, eta = ? WHERE id = ?",
                    (area["neighborhood"], area["fee"], area["eta"], area["id"]),
                )
                area_ids.append(area["id"])
            else:
                cursor = conn.execute(
                    "INSERT INTO delivery_areas (neighborhood, fee, eta) VALUES (?, ?, ?)",
                    (area["neighborhood"], area["fee"], area["eta"]),
                )
                area_ids.append(cursor.lastrowid)
        if area_ids:
            placeholders = ",".join("?" for _ in area_ids)
            conn.execute(f"DELETE FROM delivery_areas WHERE id NOT IN ({placeholders})", area_ids)
        else:
            conn.execute("DELETE FROM delivery_areas")


def create_order(payload):
    items = payload.get("items") or []
    if not items:
        raise ValueError("Carrinho vazio.")
    clean_items = []
    for item in items:
        clean_items.append(
            {
                "name": str(item.get("name", "")).strip() or "Produto",
                "qty": int(item.get("qty") or 1),
                "price": float(item.get("price") or 0),
            }
        )
    subtotal = sum(item["price"] * item["qty"] for item in clean_items)
    delivery_fee = float(payload.get("deliveryFee") or 0)
    total = subtotal + delivery_fee
    items_label = ", ".join(f"{item['name']} x{item['qty']}" for item in clean_items)
    with db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO orders
            (customer, customer_neighborhood, items, items_label, subtotal, delivery_fee, total, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("customer") or "Cliente sem nome").strip(),
                str(payload.get("customerNeighborhood") or "").strip(),
                json.dumps(clean_items, ensure_ascii=False),
                items_label,
                subtotal,
                delivery_fee,
                total,
                "Novo",
                utc_now().isoformat(),
            ),
        )
        return {"id": cursor.lastrowid, "itemsLabel": items_label, "total": total}


def create_session():
    token = secrets.token_urlsafe(32)
    now = utc_now()
    expires_at = now + SESSION_DURATION
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO admin_sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
            (token, now.isoformat(), expires_at.isoformat()),
        )
    return token, expires_at


def session_is_valid(token):
    if not token:
        return False
    with db_connection() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (utc_now().isoformat(),))
        return conn.execute("SELECT token FROM admin_sessions WHERE token = ?", (token,)).fetchone() is not None


def delete_session(token):
    if token:
        with db_connection() as conn:
            conn.execute("DELETE FROM admin_sessions WHERE token = ?", (token,))


class AppHandler(BaseHTTPRequestHandler):
    server_version = "Kimara/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html", "/admin"}:
            return self.serve_file(INDEX_PATH, "text/html; charset=utf-8")
        if parsed.path.startswith("/static/"):
            return self.serve_static(parsed.path)
        if parsed.path == "/api/public-data":
            return self.send_json(HTTPStatus.OK, public_data(include_admin=False))
        if parsed.path == "/api/admin/session":
            return self.send_json(HTTPStatus.OK, {"logged": self.is_authenticated()})
        if parsed.path == "/api/admin/data":
            if not self.require_auth():
                return
            return self.send_json(HTTPStatus.OK, public_data(include_admin=True))
        if parsed.path == "/api/admin/export":
            if not self.require_auth():
                return
            return self.send_download(public_data(include_admin=True))
        return self.send_error_json(HTTPStatus.NOT_FOUND, "Rota nao encontrada.")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/orders":
            return self.handle_create_order()
        if parsed.path == "/api/admin/login":
            return self.handle_login()
        if parsed.path == "/api/admin/logout":
            return self.handle_logout()
        if parsed.path == "/api/admin/seed":
            if not self.require_auth():
                return
            return self.handle_seed()
        if parsed.path == "/api/admin/save":
            if not self.require_auth():
                return
            return self.handle_save()
        if parsed.path == "/api/admin/order-status":
            if not self.require_auth():
                return
            return self.handle_order_status()
        return self.send_error_json(HTTPStatus.NOT_FOUND, "Rota nao encontrada.")

    def serve_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, request_path):
        relative = request_path.removeprefix("/static/").replace("/", os.sep)
        path = (STATIC_DIR / relative).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.exists():
            return self.send_error_json(HTTPStatus.NOT_FOUND, "Arquivo nao encontrado.")
        content_type = "application/octet-stream"
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            content_type = "image/jpeg"
        elif path.suffix.lower() == ".png":
            content_type = "image/png"
        elif path.suffix.lower() == ".css":
            content_type = "text/css; charset=utf-8"
        return self.serve_file(path, content_type)

    def handle_create_order(self):
        payload = self.read_json_body()
        if payload is None:
            return
        try:
            order = create_order(payload)
        except ValueError as exc:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        return self.send_json(HTTPStatus.CREATED, {"order": order})

    def handle_login(self):
        payload = self.read_json_body()
        if payload is None:
            return
        user = str(payload.get("user", "")).strip()
        password = str(payload.get("pass", "")).strip()
        if user != ADMIN_USER or hashlib.sha256(password.encode("utf-8")).hexdigest() != ADMIN_PASS_HASH:
            return self.send_error_json(HTTPStatus.UNAUTHORIZED, "Login invalido.")
        token, expires_at = create_session()
        body = json.dumps({"logged": True}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_cookie(token, expires_at)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_logout(self):
        delete_session(self.get_session_token())
        body = json.dumps({"logged": False}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.clear_cookie()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_save(self):
        payload = self.read_json_body()
        if payload is None:
            return
        save_admin_data(payload)
        return self.send_json(HTTPStatus.OK, public_data(include_admin=True))

    def handle_seed(self):
        seeded = seed_defaults_if_empty()
        data = public_data(include_admin=True)
        data["seeded"] = seeded
        return self.send_json(HTTPStatus.OK, data)

    def handle_order_status(self):
        payload = self.read_json_body()
        if payload is None:
            return
        status = str(payload.get("status", "")).strip()
        if status not in {"Novo", "Em preparo", "Saiu para entrega", "Entregue"}:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, "Status invalido.")
        with db_connection() as conn:
            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, int(payload.get("id") or 0)))
        return self.send_json(HTTPStatus.OK, public_data(include_admin=True))

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "JSON invalido.")
            return None

    def get_session_token(self):
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def is_authenticated(self):
        return session_is_valid(self.get_session_token())

    def require_auth(self):
        if self.is_authenticated():
            return True
        self.send_error_json(HTTPStatus.UNAUTHORIZED, "Sessao expirada ou nao autenticada.")
        return False

    def send_cookie(self, token, expires_at):
        expires_http = expires_at.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Expires={expires_http}")

    def clear_cookie(self):
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json(status, {"error": message})

    def send_download(self, payload):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="lanchonete-kimara-dados.json"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def run():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Servidor pronto em http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
