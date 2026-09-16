from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from .models import CatalogEntry, Category, Inventory, Price, Product, Promotion, Store

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "product.sqlite3"


class ProductRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS categories (category_id TEXT PRIMARY KEY, name TEXT NOT NULL, parent_category_id TEXT);
                CREATE TABLE IF NOT EXISTS products (product_id TEXT PRIMARY KEY, sku TEXT NOT NULL UNIQUE, name TEXT NOT NULL, description TEXT, category_id TEXT, brand TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prices (price_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, amount REAL NOT NULL, currency TEXT NOT NULL, effective_from TEXT NOT NULL, effective_to TEXT);
                CREATE TABLE IF NOT EXISTS promotions (promotion_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, discount_type TEXT NOT NULL, discount_value REAL NOT NULL, start_date TEXT NOT NULL, end_date TEXT, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS promotion_products (promotion_id TEXT NOT NULL, product_id TEXT NOT NULL, PRIMARY KEY (promotion_id, product_id));
                CREATE TABLE IF NOT EXISTS stores (store_id TEXT PRIMARY KEY, name TEXT NOT NULL, channel TEXT NOT NULL, city TEXT, country TEXT);
                CREATE TABLE IF NOT EXISTS catalog_entries (catalog_entry_id TEXT PRIMARY KEY, store_id TEXT NOT NULL, product_id TEXT NOT NULL, price_amount REAL NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL, UNIQUE(store_id, product_id));
                CREATE TABLE IF NOT EXISTS inventory (store_id TEXT NOT NULL, product_id TEXT NOT NULL, quantity INTEGER NOT NULL, reserved_quantity INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(store_id, product_id));
            """)

    @staticmethod
    def product(row: sqlite3.Row) -> Product:
        return Product(**dict(row))

    @staticmethod
    def category(row: sqlite3.Row) -> Category:
        return Category(**dict(row))

    @staticmethod
    def price(row: sqlite3.Row) -> Price:
        return Price(**dict(row))

    @staticmethod
    def store(row: sqlite3.Row) -> Store:
        return Store(**dict(row))

    @staticmethod
    def catalog_entry(row: sqlite3.Row) -> CatalogEntry:
        return CatalogEntry(**dict(row))

    @staticmethod
    def inventory(row: sqlite3.Row) -> Inventory:
        return Inventory(**dict(row))

    def save_product(self, item: Product) -> Product:
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(product_id) DO UPDATE SET sku=excluded.sku, name=excluded.name, description=excluded.description, category_id=excluded.category_id, brand=excluded.brand, status=excluded.status, updated_at=excluded.updated_at", (item.product_id, item.sku, item.name, item.description, item.category_id, item.brand, item.status, item.created_at.isoformat(), item.updated_at.isoformat()))
        return item

    def get_product(self, product_id: str) -> Product | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
        return self.product(row) if row else None

    def list_products(self) -> list[Product]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM products ORDER BY created_at").fetchall()
        return [self.product(row) for row in rows]

    def delete_product(self, product_id: str) -> None:
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM products WHERE product_id = ?", (product_id,))

    def save_category(self, item: Category) -> Category:
        with self.lock, self.connection:
            self.connection.execute("INSERT OR REPLACE INTO categories VALUES (?, ?, ?)", (item.category_id, item.name, item.parent_category_id))
        return item

    def list_categories(self) -> list[Category]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM categories ORDER BY name").fetchall()
        return [self.category(row) for row in rows]

    def save_store(self, item: Store) -> Store:
        with self.lock, self.connection:
            self.connection.execute("INSERT OR REPLACE INTO stores VALUES (?, ?, ?, ?, ?)", (item.store_id, item.name, item.channel, item.city, item.country))
        return item

    def list_stores(self) -> list[Store]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM stores ORDER BY name").fetchall()
        return [self.store(row) for row in rows]

    def save_catalog_entry(self, item: CatalogEntry) -> CatalogEntry:
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO catalog_entries VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(store_id, product_id) DO UPDATE SET price_amount=excluded.price_amount, currency=excluded.currency, status=excluded.status", (item.catalog_entry_id, item.store_id, item.product_id, item.price_amount, item.currency, item.status))
        return item

    def list_catalog(self, store_id: str) -> list[CatalogEntry]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM catalog_entries WHERE store_id = ? ORDER BY product_id", (store_id,)).fetchall()
        return [self.catalog_entry(row) for row in rows]

    def save_inventory(self, item: Inventory) -> Inventory:
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO inventory VALUES (?, ?, ?, ?) ON CONFLICT(store_id, product_id) DO UPDATE SET quantity=excluded.quantity, reserved_quantity=excluded.reserved_quantity", (item.store_id, item.product_id, item.quantity, item.reserved_quantity))
        return item

    def get_inventory(self, store_id: str, product_id: str) -> Inventory | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM inventory WHERE store_id = ? AND product_id = ?", (store_id, product_id)).fetchone()
        return self.inventory(row) if row else None

    def list_inventory(self, store_id: str) -> list[Inventory]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM inventory WHERE store_id = ? ORDER BY product_id", (store_id,)).fetchall()
        return [self.inventory(row) for row in rows]

    def add_price(self, item: Price) -> Price:
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?)", (item.price_id, item.product_id, item.amount, item.currency, item.effective_from.isoformat(), item.effective_to.isoformat() if item.effective_to else None))
        return item

    def list_prices(self, product_id: str) -> list[Price]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM prices WHERE product_id = ? ORDER BY effective_from", (product_id,)).fetchall()
        return [self.price(row) for row in rows]

    def save_promotion(self, item: Promotion) -> Promotion:
        with self.lock, self.connection:
            self.connection.execute("INSERT OR REPLACE INTO promotions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (item.promotion_id, item.name, item.description, item.discount_type, item.discount_value, item.start_date.isoformat(), item.end_date.isoformat() if item.end_date else None, item.status))
            self.connection.execute("DELETE FROM promotion_products WHERE promotion_id = ?", (item.promotion_id,))
            self.connection.executemany("INSERT INTO promotion_products VALUES (?, ?)", [(item.promotion_id, product_id) for product_id in item.product_ids])
        return item

    def get_promotion(self, promotion_id: str) -> Promotion | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM promotions WHERE promotion_id = ?", (promotion_id,)).fetchone()
            product_ids = [r[0] for r in self.connection.execute("SELECT product_id FROM promotion_products WHERE promotion_id = ?", (promotion_id,))]
        if not row:
            return None
        data = dict(row)
        data["product_ids"] = product_ids
        return Promotion(**data)

    def list_promotions(self) -> list[Promotion]:
        with self.lock:
            ids = [r[0] for r in self.connection.execute("SELECT promotion_id FROM promotions ORDER BY start_date")]
        return [self.get_promotion(promotion_id) for promotion_id in ids]

    def delete_promotion(self, promotion_id: str) -> None:
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM promotions WHERE promotion_id = ?", (promotion_id,))

    def close(self) -> None:
        self.connection.close()
