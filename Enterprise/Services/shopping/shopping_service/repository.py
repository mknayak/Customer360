from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from .models import Cart, CartItem, CartView, Order, OrderItem

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "shopping.sqlite3"


class ShoppingRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS carts (cart_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, site_id TEXT, status TEXT NOT NULL, payment_status TEXT NOT NULL DEFAULT 'pending', payment_method TEXT, transaction_id TEXT, failure_reason TEXT, paid_at TEXT, store_id TEXT, delivery_mode TEXT NOT NULL DEFAULT 'collect_at_store', delivery_address TEXT, fulfillment_status TEXT NOT NULL DEFAULT 'not_started', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cart_items (cart_item_id TEXT PRIMARY KEY, cart_id TEXT NOT NULL, product_id TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, site_id TEXT, promotion_id TEXT, total_amount REAL NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL, payment_status TEXT NOT NULL DEFAULT 'pending', payment_method TEXT, transaction_id TEXT, failure_reason TEXT, paid_at TEXT, store_id TEXT, delivery_mode TEXT NOT NULL DEFAULT 'collect_at_store', delivery_address TEXT, fulfillment_status TEXT NOT NULL DEFAULT 'not_started', created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS order_items (order_item_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, product_id TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price REAL NOT NULL, discount_amount REAL NOT NULL);
            """)
            self._ensure_column("carts", "payment_status", "TEXT NOT NULL DEFAULT 'pending'")
            self._ensure_column("carts", "payment_method", "TEXT")
            self._ensure_column("carts", "transaction_id", "TEXT")
            self._ensure_column("carts", "failure_reason", "TEXT")
            self._ensure_column("carts", "paid_at", "TEXT")
            self._ensure_column("carts", "store_id", "TEXT")
            self._ensure_column("carts", "delivery_mode", "TEXT NOT NULL DEFAULT 'collect_at_store'")
            self._ensure_column("carts", "delivery_address", "TEXT")
            self._ensure_column("carts", "fulfillment_status", "TEXT NOT NULL DEFAULT 'not_started'")
            self._ensure_column("orders", "payment_status", "TEXT NOT NULL DEFAULT 'pending'")
            self._ensure_column("orders", "payment_method", "TEXT")
            self._ensure_column("orders", "transaction_id", "TEXT")
            self._ensure_column("orders", "failure_reason", "TEXT")
            self._ensure_column("orders", "paid_at", "TEXT")
            self._ensure_column("orders", "store_id", "TEXT")
            self._ensure_column("orders", "delivery_mode", "TEXT NOT NULL DEFAULT 'collect_at_store'")
            self._ensure_column("orders", "delivery_address", "TEXT")
            self._ensure_column("orders", "fulfillment_status", "TEXT NOT NULL DEFAULT 'not_started'")

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def cart(row: sqlite3.Row) -> Cart:
        return Cart(**dict(row))

    @staticmethod
    def cart_item(row: sqlite3.Row) -> CartItem:
        return CartItem(**dict(row))

    def save_cart(self, item: Cart) -> Cart:
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO carts (cart_id, customer_id, site_id, status, payment_status, payment_method, transaction_id, failure_reason, paid_at, store_id, delivery_mode, delivery_address, fulfillment_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(cart_id) DO UPDATE SET site_id=excluded.site_id, status=excluded.status, payment_status=excluded.payment_status, payment_method=excluded.payment_method, transaction_id=excluded.transaction_id, failure_reason=excluded.failure_reason, paid_at=excluded.paid_at, store_id=excluded.store_id, delivery_mode=excluded.delivery_mode, delivery_address=excluded.delivery_address, fulfillment_status=excluded.fulfillment_status, updated_at=excluded.updated_at", (item.cart_id, item.customer_id, item.site_id, item.status, item.payment_status, item.payment_method, item.transaction_id, item.failure_reason, item.paid_at.isoformat() if item.paid_at else None, item.store_id, item.delivery_mode, item.delivery_address, item.fulfillment_status, item.created_at.isoformat(), item.updated_at.isoformat()))
        return item

    def get_cart(self, cart_id: str) -> CartView | None:
        with self.lock:
            cart_row = self.connection.execute("SELECT * FROM carts WHERE cart_id = ?", (cart_id,)).fetchone()
            item_rows = self.connection.execute("SELECT * FROM cart_items WHERE cart_id = ? ORDER BY rowid", (cart_id,)).fetchall()
        if not cart_row:
            return None
        return CartView(**self.cart(cart_row).model_dump(), items=[self.cart_item(row) for row in item_rows])

    def save_item(self, item: CartItem) -> CartItem:
        with self.lock, self.connection:
            self.connection.execute("INSERT OR REPLACE INTO cart_items VALUES (?, ?, ?, ?, ?)", (item.cart_item_id, item.cart_id, item.product_id, item.quantity, item.unit_price))
        return item

    def delete_item(self, cart_id: str, item_id: str) -> bool:
        with self.lock, self.connection:
            result = self.connection.execute("DELETE FROM cart_items WHERE cart_id = ? AND cart_item_id = ?", (cart_id, item_id))
        return result.rowcount > 0

    def save_order(self, item: Order) -> Order:
        with self.lock, self.connection:
            self.connection.execute("INSERT INTO orders (order_id, customer_id, site_id, promotion_id, total_amount, currency, status, payment_status, payment_method, transaction_id, failure_reason, paid_at, store_id, delivery_mode, delivery_address, fulfillment_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (item.order_id, item.customer_id, item.site_id, item.promotion_id, item.total_amount, item.currency, item.status, item.payment_status, item.payment_method, item.transaction_id, item.failure_reason, item.paid_at.isoformat() if item.paid_at else None, item.store_id, item.delivery_mode, item.delivery_address, item.fulfillment_status, item.created_at.isoformat()))
            self.connection.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?)", [(line.order_item_id, item.order_id, line.product_id, line.quantity, line.unit_price, line.discount_amount) for line in item.items])
        return item

    def get_order(self, order_id: str) -> Order | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            item_rows = self.connection.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        if not row:
            return None
        data = dict(row)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["items"] = [OrderItem(**dict(item_row)) for item_row in item_rows]
        return Order(**data)

    def list_orders(self) -> list[Order]:
        with self.lock:
            ids = [row[0] for row in self.connection.execute("SELECT order_id FROM orders ORDER BY created_at")]
        return [self.get_order(order_id) for order_id in ids]

    def update_order(self, order_id: str, status: str) -> Order | None:
        with self.lock, self.connection:
            self.connection.execute("UPDATE orders SET status = ? WHERE order_id = ?", (status, order_id))
        return self.get_order(order_id)

    def close(self) -> None:
        self.connection.close()
