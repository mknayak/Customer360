"""SQLite-backed raw event ingestion and curated KPI models."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "analytics.sqlite3"


class EventWarehouse:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_events (
                    event_id TEXT PRIMARY KEY,
                    source_service TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT,
                    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_raw_events_type ON raw_events(event_type);
                CREATE INDEX IF NOT EXISTS idx_raw_events_occurred ON raw_events(occurred_at);
                CREATE TABLE IF NOT EXISTS curated_visits (
                    visit_id TEXT PRIMARY KEY, customer_id TEXT, site_id TEXT, occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS curated_carts (
                    cart_id TEXT PRIMARY KEY, customer_id TEXT, occurred_at TEXT NOT NULL, abandoned INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS curated_orders (
                    order_id TEXT PRIMARY KEY, customer_id TEXT, occurred_at TEXT NOT NULL,
                    payment_status TEXT, total_amount REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS curated_order_items (
                    order_id TEXT NOT NULL, product_id TEXT NOT NULL, quantity INTEGER NOT NULL,
                    revenue REAL NOT NULL DEFAULT 0, PRIMARY KEY (order_id, product_id)
                );
                """
            )

    def ingest(self, events: Iterable[Mapping[str, Any]]) -> dict[str, int]:
        received = stored = 0
        with self.lock, self.connection:
            for event in events:
                received += 1
                event_id = self._event_id(event)
                existing = self.connection.execute("SELECT 1 FROM raw_events WHERE event_id = ?", (event_id,)).fetchone()
                if existing:
                    continue
                self.connection.execute(
                    """
                    INSERT INTO raw_events (event_id, source_service, event_type, aggregate_type, aggregate_id, payload, occurred_at, correlation_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        str(event["source_service"]),
                        str(event["event_type"]),
                        str(event["aggregate_type"]),
                        str(event["aggregate_id"]),
                        json.dumps(event.get("payload", {}), sort_keys=True, separators=(",", ":")),
                        str(event.get("occurred_at", "")),
                        event.get("correlation_id"),
                    ),
                )
                self._curate(event, event_id)
                stored += 1
        return {"received": received, "stored": stored, "duplicates": received - stored}

    def ingest_event_service(self, origin: str, *, limit: int = 1000) -> dict[str, int]:
        query = urlencode({"limit": limit})
        with urlopen(f"{origin.rstrip('/')}/api/events?{query}", timeout=10) as response:
            return self.ingest(json.loads(response.read()))

    def kpi(self, metric: str) -> dict[str, Any]:
        with self.lock:
            if metric == "revenue":
                row = self.connection.execute("SELECT COALESCE(SUM(total_amount), 0) AS value FROM curated_orders WHERE payment_status = 'succeeded'").fetchone()
                return {"metric": metric, "value": round(row["value"], 2), "source": "curated_orders"}
            if metric == "visits":
                row = self.connection.execute("SELECT COUNT(*) AS value FROM curated_visits").fetchone()
                return {"metric": metric, "value": row["value"], "source": "curated_visits"}
            if metric == "conversion":
                visits = self.connection.execute("SELECT COUNT(*) AS value FROM curated_visits").fetchone()["value"]
                orders = self.connection.execute("SELECT COUNT(*) AS value FROM curated_orders WHERE payment_status = 'succeeded'").fetchone()["value"]
                return {"metric": metric, "value": round(orders / visits, 4) if visits else 0, "numerator": orders, "denominator": visits, "source": "curated_visits+curated_orders"}
            if metric == "cart_abandonment":
                carts = self.connection.execute("SELECT COUNT(*) AS value FROM curated_carts").fetchone()["value"]
                abandoned = self.connection.execute("SELECT COUNT(*) AS value FROM curated_carts WHERE abandoned = 1").fetchone()["value"]
                return {"metric": metric, "value": round(abandoned / carts, 4) if carts else 0, "numerator": abandoned, "denominator": carts, "source": "curated_carts"}
            if metric == "product_performance":
                rows = self.connection.execute("SELECT product_id, SUM(quantity) AS units, ROUND(SUM(revenue), 2) AS revenue FROM curated_order_items GROUP BY product_id ORDER BY revenue DESC").fetchall()
                return {"metric": metric, "value": [{"product_id": row["product_id"], "units": row["units"], "revenue": row["revenue"]} for row in rows], "source": "curated_order_items"}
        raise ValueError(f"Unsupported KPI: {metric}")

    def _curate(self, event: Mapping[str, Any], event_id: str) -> None:
        event_type = event["event_type"]
        payload = event.get("payload", {})
        occurred_at = str(event.get("occurred_at", ""))
        if event_type == "VisitStarted":
            self.connection.execute("INSERT OR IGNORE INTO curated_visits VALUES (?, ?, ?, ?)", (event["aggregate_id"], payload.get("customer_id"), payload.get("site_id"), occurred_at))
        elif event_type in {"CartCreated", "CartAbandoned"}:
            cart_id = event["aggregate_id"]
            self.connection.execute("INSERT OR IGNORE INTO curated_carts VALUES (?, ?, ?, ?)", (cart_id, payload.get("customer_id"), occurred_at, int(event_type == "CartAbandoned")))
            if event_type == "CartAbandoned":
                self.connection.execute("UPDATE curated_carts SET abandoned = 1 WHERE cart_id = ?", (cart_id,))
        elif event_type == "OrderCreated":
            order_id = event["aggregate_id"]
            total = payload.get("total_amount", payload.get("total", 0)) or 0
            self.connection.execute("INSERT OR IGNORE INTO curated_orders VALUES (?, ?, ?, ?, ?)", (order_id, payload.get("customer_id"), occurred_at, payload.get("payment_status"), float(total)))
            for item in payload.get("items", []):
                quantity = int(item.get("quantity", 0))
                revenue = quantity * float(item.get("unit_price", 0)) - float(item.get("discount_amount", 0))
                self.connection.execute("INSERT OR REPLACE INTO curated_order_items VALUES (?, ?, ?, ?)", (order_id, item["product_id"], quantity, revenue))

    @staticmethod
    def _event_id(event: Mapping[str, Any]) -> str:
        event_id = event.get("event_id") or event.get("idempotency_key")
        if event_id:
            return str(event_id)
        canonical = json.dumps(dict(event), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def close(self) -> None:
        with self.lock:
            self.connection.close()