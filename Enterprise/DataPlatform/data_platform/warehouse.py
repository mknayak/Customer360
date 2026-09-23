"""SQLite-backed raw event ingestion and curated KPI models."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .semantic_query import CompiledQuery


DEFAULT_DATABASE_PATH = Path(os.getenv("ANALYTICS_DATABASE", Path(__file__).resolve().parents[1] / "data" / "analytics.sqlite3"))


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
                CREATE TABLE IF NOT EXISTS curated_content_activity (
                    event_id TEXT PRIMARY KEY, session_id TEXT, customer_id TEXT, content_id TEXT,
                    event_type TEXT NOT NULL, occurred_at TEXT NOT NULL, duration_seconds REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS curated_finance (
                    order_id TEXT PRIMARY KEY, customer_id TEXT, site_id TEXT, promotion_id TEXT,
                    revenue REAL NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0,
                    margin REAL NOT NULL DEFAULT 0, occurred_at TEXT NOT NULL
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

    def ingest_event_service(self, origin: str, *, limit: int = 1000, max_batches: int = 100, consumer_id: str = "data-platform") -> dict[str, int]:
        received = stored = duplicates = batches = 0
        for _ in range(max_batches):
            query = urlencode({"limit": limit})
            with urlopen(f"{origin.rstrip('/')}/api/consumers/{consumer_id}/poll?{query}", timeout=10) as response:
                envelope = json.loads(response.read())
            events = envelope.get("events", [])
            if not events:
                break
            result = self.ingest(events)
            received += result["received"]
            stored += result["stored"]
            duplicates += result["duplicates"]
            batches += 1
            acknowledgement = Request(
                f"{origin.rstrip('/')}/api/consumers/{consumer_id}/ack",
                data=json.dumps({"event_id": events[-1]["event_id"]}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(acknowledgement, timeout=10):
                pass
            if len(events) < limit:
                break
        return {"received": received, "stored": stored, "duplicates": duplicates, "batches": batches}

    def backfill_shopping_orders(self, origin: str, *, page_size: int = 100) -> dict[str, int]:
        """Backfill item-level facts when older events predate item payloads."""
        page = 1
        received = 0
        stored = 0
        while True:
            query = urlencode({"page": page, "page_size": page_size})
            with urlopen(f"{origin.rstrip('/')}/api/orders?{query}", timeout=10) as response:
                result = json.loads(response.read())
            orders = result.get("items", [])
            if not orders:
                break
            events = [
                {
                    "event_id": f"shopping-order-backfill:{order['order_id']}",
                    "source_service": "shopping",
                    "event_type": "OrderCreated",
                    "aggregate_type": "order",
                    "aggregate_id": order["order_id"],
                    "payload": order,
                    "occurred_at": order.get("created_at", ""),
                    "correlation_id": None,
                }
                for order in orders
            ]
            ingest_result = self.ingest(events)
            received += ingest_result["received"]
            stored += ingest_result["stored"]
            if page >= result.get("total_pages", page) or len(orders) < page_size:
                break
            page += 1
        return {"received": received, "stored": stored}

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
            if metric == "retention":
                customers = self.connection.execute(
                    "SELECT COUNT(DISTINCT customer_id) AS value FROM curated_orders WHERE payment_status = 'succeeded' AND customer_id IS NOT NULL"
                ).fetchone()["value"]
                repeat_customers = self.connection.execute(
                    "SELECT COUNT(*) AS value FROM (SELECT customer_id FROM curated_orders WHERE payment_status = 'succeeded' AND customer_id IS NOT NULL GROUP BY customer_id HAVING COUNT(*) > 1)"
                ).fetchone()["value"]
                return {"metric": metric, "value": round(repeat_customers / customers, 4) if customers else 0, "numerator": repeat_customers, "denominator": customers, "source": "curated_orders"}
            if metric == "segment_conversion":
                return {"metric": metric, "value": [], "source": "curated_customer_segments", "limitations": ("No customer segment assignments have been ingested",)}
            if metric == "product_performance":
                rows = self.connection.execute("SELECT product_id, SUM(quantity) AS units, ROUND(SUM(revenue), 2) AS revenue FROM curated_order_items GROUP BY product_id ORDER BY units DESC, revenue DESC").fetchall()
                return {"metric": metric, "value": [{"product_id": row["product_id"], "units": row["units"], "revenue": row["revenue"]} for row in rows], "source": "curated_order_items"}
            if metric == "content_views":
                row = self.connection.execute("SELECT COUNT(*) AS value FROM curated_content_activity WHERE event_type = 'ContentView'").fetchone()
                return {"metric": metric, "value": row["value"], "source": "curated_content_activity"}
            if metric == "page_popularity":
                rows = self.connection.execute(
                    "SELECT COALESCE(content_id, '(unknown)') AS page, COUNT(*) AS views FROM curated_content_activity WHERE event_type = 'ContentView' GROUP BY page ORDER BY views DESC, page"
                ).fetchall()
                return {"metric": metric, "value": [{"page": row["page"], "views": row["views"]} for row in rows], "source": "curated_content_activity", "definition": "ContentView events grouped by content page"}
            if metric == "content_sessions":
                row = self.connection.execute("SELECT COUNT(DISTINCT session_id) AS value FROM curated_content_activity WHERE event_type = 'PageVisit'").fetchone()
                return {"metric": metric, "value": row["value"], "source": "curated_content_activity"}
            if metric == "average_time_on_page":
                row = self.connection.execute("SELECT COALESCE(AVG(duration_seconds), 0) AS value FROM curated_content_activity WHERE event_type = 'TimeOnPage'").fetchone()
                return {"metric": metric, "value": round(row["value"], 2), "unit": "seconds", "source": "curated_content_activity"}
            if metric == "page_dropoff":
                rows = self.connection.execute(
                    "SELECT COALESCE(content_id, '(unknown)') AS page, COUNT(*) AS exits FROM curated_content_activity WHERE event_type = 'Exit' GROUP BY page ORDER BY exits DESC, page"
                ).fetchall()
                return {"metric": metric, "value": [{"page": row["page"], "exits": row["exits"]} for row in rows], "source": "curated_content_activity", "definition": "Exit events grouped by the last page recorded for the session"}
            if metric in {"gross_margin", "profit", "promotion_economics"}:
                row = self.connection.execute("SELECT COALESCE(SUM(revenue), 0) AS revenue, COALESCE(SUM(cost), 0) AS cost, COALESCE(SUM(margin), 0) AS margin FROM curated_finance").fetchone()
                if metric == "gross_margin":
                    value = round(row["margin"] / row["revenue"], 4) if row["revenue"] else 0
                elif metric == "profit":
                    value = round(row["margin"], 2)
                else:
                    value = {"revenue": round(row["revenue"], 2), "cost": round(row["cost"], 2), "margin": round(row["margin"], 2)}
                return {"metric": metric, "value": value, "source": "curated_finance", "limitations": ("Cost values default to zero when order payloads do not provide cost_amount.",) if row["cost"] == 0 else ()}
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
            self.connection.execute("DELETE FROM curated_order_items WHERE order_id = ?", (order_id,))
            self.connection.execute("INSERT OR REPLACE INTO curated_orders VALUES (?, ?, ?, ?, ?)", (order_id, payload.get("customer_id"), occurred_at, payload.get("payment_status"), float(total)))
            for item in payload.get("items", []):
                quantity = int(item.get("quantity", 0))
                revenue = quantity * float(item.get("unit_price", 0)) - float(item.get("discount_amount", 0))
                self.connection.execute("INSERT OR REPLACE INTO curated_order_items VALUES (?, ?, ?, ?)", (order_id, item["product_id"], quantity, revenue))
            cost = float(payload.get("cost_amount", 0) or 0)
            self.connection.execute(
                "INSERT OR REPLACE INTO curated_finance VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (order_id, payload.get("customer_id"), payload.get("site_id"), payload.get("promotion_id"), float(total), cost, float(total) - cost, occurred_at),
            )
        elif event_type in {"PageVisit", "ContentView", "Search", "TimeOnPage", "Exit"}:
            self.connection.execute(
                "INSERT OR REPLACE INTO curated_content_activity VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, payload.get("session_id", event.get("correlation_id")), payload.get("customer_id"), payload.get("content_id", payload.get("last_page")), event_type, occurred_at, float(payload.get("duration_seconds", 0) or 0)),
            )

    def quality(self) -> dict[str, Any]:
        with self.lock:
            raw_count = self.connection.execute("SELECT COUNT(*) AS value FROM raw_events").fetchone()["value"]
            latest = self.connection.execute("SELECT MAX(occurred_at) AS value FROM raw_events").fetchone()["value"]
            missing_times = self.connection.execute("SELECT COUNT(*) AS value FROM raw_events WHERE occurred_at = ''").fetchone()["value"]
            return {"raw_events": raw_count, "latest_occurred_at": latest, "checks": {"missing_occurred_at": missing_times, "passed": missing_times == 0}, "curated_tables": {"visits": self.connection.execute("SELECT COUNT(*) AS value FROM curated_visits").fetchone()["value"], "content_activity": self.connection.execute("SELECT COUNT(*) AS value FROM curated_content_activity").fetchone()["value"], "finance": self.connection.execute("SELECT COUNT(*) AS value FROM curated_finance").fetchone()["value"]}}

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {"metric": "revenue", "definition": "Succeeded order total", "source": "curated_orders", "grain": "order", "lineage": "OrderCreated -> curated_orders", "owner": "finance"},
            {"metric": "conversion", "definition": "Succeeded orders divided by visits", "source": "curated_visits+curated_orders", "grain": "period", "lineage": "VisitStarted + OrderCreated", "owner": "digital"},
            {"metric": "content_views", "definition": "Count of content view events", "source": "curated_content_activity", "grain": "content event", "lineage": "ContentView -> curated_content_activity", "owner": "digital"},
            {"metric": "gross_margin", "definition": "Revenue less cost divided by revenue", "source": "curated_finance", "grain": "order", "lineage": "OrderCreated -> curated_finance", "owner": "finance"},
        ]

    def reconcile(self, operational: Mapping[str, Any]) -> dict[str, Any]:
        checks = {}
        for metric in ("revenue", "visits"):
            analytical = self.kpi(metric)["value"]
            expected = operational.get(metric)
            checks[metric] = {"analytical": analytical, "operational": expected, "delta": None if expected is None else analytical - expected, "matched": expected is None or analytical == expected}
        return {"status": "matched" if all(item["matched"] for item in checks.values()) else "mismatch", "checks": checks}

    def execute_semantic(self, compiled: CompiledQuery) -> dict[str, Any]:
        if not compiled.sql.lstrip().upper().startswith("SELECT ") or ";" in compiled.sql:
            raise ValueError("Semantic query compiler produced non-read-only SQL")
        with self.lock:
            rows = self.connection.execute(compiled.sql, compiled.parameters).fetchall()
        return {
            "metric": compiled.metric.metric_id,
            "rows": [dict(row) for row in rows],
            "query": {"sql": compiled.sql, "parameters": compiled.parameters},
            "lineage": compiled.metric.lineage,
            "source_model": compiled.metric.model,
            "definition": compiled.metric.description,
            "dimensions": compiled.dimensions,
            "security_classification": compiled.metric.security_classification,
        }

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