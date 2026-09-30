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
                CREATE TABLE IF NOT EXISTS curated_cart_items (
                    cart_item_id TEXT PRIMARY KEY, cart_id TEXT NOT NULL, product_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL, unit_price REAL NOT NULL DEFAULT 0, value REAL NOT NULL DEFAULT 0
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
                CREATE TABLE IF NOT EXISTS dim_products (
                    product_id TEXT PRIMARY KEY, sku TEXT, name TEXT, description TEXT,
                    category_id TEXT, brand TEXT, status TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS dim_categories (
                    category_id TEXT PRIMARY KEY, name TEXT NOT NULL, parent_category_id TEXT
                );
                CREATE TABLE IF NOT EXISTS dim_customer_profiles (
                    customer_id TEXT PRIMARY KEY, age_group TEXT, city TEXT, country TEXT,
                    preferred_channel TEXT, status TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS curated_feedback (
                    feedback_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, source TEXT NOT NULL,
                    rating INTEGER NOT NULL, comment TEXT, product_id TEXT, order_id TEXT,
                    campaign_id TEXT, site_id TEXT, sentiment TEXT NOT NULL, status TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
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

    def backfill_product_catalog(self, origin: str) -> dict[str, int]:
        """Refresh product and category dimensions from the product service."""
        with urlopen(f"{origin.rstrip('/')}/api/categories", timeout=10) as response:
            categories = json.loads(response.read())
        with urlopen(f"{origin.rstrip('/')}/api/products", timeout=10) as response:
            products = json.loads(response.read())
        with self.lock, self.connection:
            for category in categories:
                self._upsert_category(category)
            for product in products:
                self._upsert_product(product)
        return {"categories": len(categories), "products": len(products)}

    def backfill_customer_profiles(self, origin: str, *, page_size: int = 100) -> dict[str, int]:
        """Refresh the non-PII customer profile dimension from the CRM directory."""
        page = 1
        profiles: list[Mapping[str, Any]] = []
        while True:
            query = urlencode({"page": page, "page_size": page_size})
            with urlopen(f"{origin.rstrip('/')}/api/customers?{query}", timeout=10) as response:
                result = json.loads(response.read())
            customers = result.get("items", [])
            profiles.extend(customers)
            if page >= result.get("total_pages", page) or len(customers) < page_size:
                break
            page += 1
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM dim_customer_profiles")
            self.connection.executemany(
                "INSERT INTO dim_customer_profiles VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        customer["customer_id"], customer.get("age_group"), customer.get("city"),
                        customer.get("country"), customer.get("preferred_channel"),
                        customer.get("status"), str(customer.get("updated_at", "")),
                    )
                    for customer in profiles
                ],
            )
        return {"profiles": len(profiles)}

    def _upsert_product(self, product: Mapping[str, Any]) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO dim_products VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (product["product_id"], product.get("sku"), product.get("name"), product.get("description"), product.get("category_id"), product.get("brand"), product.get("status"), str(product.get("updated_at", ""))),
        )

    def _upsert_category(self, category: Mapping[str, Any]) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO dim_categories VALUES (?, ?, ?)",
            (category["category_id"], category["name"], category.get("parent_category_id")),
        )

    def trend(self, metric: str, granularity: str) -> dict[str, Any]:
        if metric == "retention":
            return self.retention_trend(granularity)
        sources = {
            "revenue": ("curated_orders", "SUM(total_amount)", "payment_status = 'succeeded'", "Succeeded order revenue"),
            "visits": ("curated_visits", "COUNT(*)", "1 = 1", "Number of visits"),
            "payment_failures": ("raw_events", "COUNT(*)", "event_type = 'PaymentFailed'", "Number of PaymentFailed events"),
            "average_cart_value": ("curated_orders", "AVG(total_amount)", "payment_status = 'succeeded'", "Average successful order amount"),
            "conversion": ("curated_visits", "COUNT(*)", "1 = 1", "Succeeded orders divided by visits in each period"),
            "cart_abandonment": ("curated_carts", "AVG(abandoned)", "1 = 1", "Abandoned carts divided by carts created in each period"),
        }
        buckets = {
            "day": "date(occurred_at)",
            "week": "date(occurred_at, 'weekday 0', '-6 days')",
            "month": "substr(occurred_at, 1, 7)",
        }
        if metric not in sources or granularity not in buckets:
            raise ValueError(f"Unsupported trend metric or granularity: {metric}, {granularity}")
        table, measure, predicate, definition = sources[metric]
        bucket = buckets[granularity]
        with self.lock:
            rows = self.connection.execute(f"""
                SELECT {bucket} AS period, {measure} AS value FROM {table}
                WHERE {predicate} AND occurred_at != ''
                GROUP BY period ORDER BY period
            """).fetchall()
            if metric == "conversion":
                orders = self.connection.execute(f"""
                    SELECT {bucket} AS period, COUNT(*) AS value FROM curated_orders
                    WHERE payment_status = 'succeeded' AND occurred_at != ''
                    GROUP BY period
                """).fetchall()
                order_counts = {row["period"]: row["value"] for row in orders}
        points = []
        for row in rows:
            value = row["value"]
            point = {"period": row["period"], "value": round(value, 4) if value is not None else None}
            if metric == "conversion":
                numerator = order_counts.get(row["period"], 0)
                point.update(value=round(numerator / value, 4), numerator=numerator, denominator=value)
            points.append(point)
        return {"metric": metric, "granularity": granularity, "source": table, "definition": definition, "points": points}

    def retention_trend(self, granularity: str) -> dict[str, Any]:
        periods = {
            "day": ("date(occurred_at)", "date(periods.period, '-1 day')", "date(period, '+1 day')"),
            "week": ("date(occurred_at, 'weekday 0', '-6 days')", "date(periods.period, '-7 days')", "date(period, '+7 days')"),
            "month": ("substr(occurred_at, 1, 7)", "strftime('%Y-%m', date(periods.period || '-01', '-1 month'))", "strftime('%Y-%m', date(period || '-01', '+1 month'))"),
        }
        if granularity not in periods:
            raise ValueError(f"Unsupported trend granularity: {granularity}")
        bucket, previous, next_period = periods[granularity]
        with self.lock:
            rows = self.connection.execute(f"""
                WITH RECURSIVE activity AS (
                    SELECT DISTINCT customer_id, {bucket} AS period
                    FROM curated_orders
                    WHERE payment_status = 'succeeded' AND customer_id IS NOT NULL AND occurred_at != ''
                ), periods(period) AS (
                    SELECT MIN(period) FROM activity HAVING MIN(period) IS NOT NULL
                    UNION ALL
                    SELECT {next_period} FROM periods WHERE period < (SELECT MAX(period) FROM activity)
                )
                SELECT periods.period, COUNT(DISTINCT prior.customer_id) AS eligible,
                       COUNT(DISTINCT current.customer_id) AS retained
                FROM periods
                LEFT JOIN activity AS prior ON prior.period = {previous}
                LEFT JOIN activity AS current ON current.period = periods.period AND current.customer_id = prior.customer_id
                GROUP BY periods.period ORDER BY periods.period
            """).fetchall()
        return {
            "metric": "retention", "granularity": granularity, "source": "curated_orders",
            "definition": "Customers with successful orders in both this and the preceding calendar period / customers with successful orders in the preceding calendar period",
            "points": [{"period": row["period"], "value": round(row["retained"] / row["eligible"], 4) if row["eligible"] else None,
                        "numerator": row["retained"], "denominator": row["eligible"]} for row in rows],
        }

    def kpi(self, metric: str) -> dict[str, Any]:
        with self.lock:
            if metric == "revenue":
                row = self.connection.execute("SELECT COALESCE(SUM(total_amount), 0) AS value FROM curated_orders WHERE payment_status = 'succeeded'").fetchone()
                return {"metric": metric, "value": round(row["value"], 2), "source": "curated_orders"}
            if metric == "average_cart_value":
                row = self.connection.execute("SELECT COALESCE(AVG(total_amount), 0) AS value FROM curated_orders WHERE payment_status = 'succeeded'").fetchone()
                return {"metric": metric, "value": round(row["value"], 2), "source": "curated_orders", "definition": "Average total amount of successful orders"}
            if metric == "payment_failures":
                row = self.connection.execute("SELECT COUNT(*) AS value FROM raw_events WHERE event_type = 'PaymentFailed'").fetchone()
                return {"metric": metric, "value": row["value"], "source": "raw_events", "definition": "Count of PaymentFailed events"}
            if metric == "customer_complaints":
                row = self.connection.execute("SELECT COUNT(*) AS value FROM curated_feedback WHERE rating <= 2 OR sentiment IN ('negative', 'mixed')").fetchone()
                return {"metric": metric, "value": row["value"], "source": "curated_feedback", "definition": "Count of feedback records rated 1-2 or classified as negative/mixed"}
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
            if metric == "abandoned_cart_value":
                row = self.connection.execute(
                    """
                    SELECT COALESCE(SUM(CASE WHEN carts.abandoned = 1 THEN items.value ELSE 0 END), 0) AS abandoned_value,
                           COALESCE(SUM(items.value), 0) AS total_value
                    FROM curated_carts AS carts
                    LEFT JOIN curated_cart_items AS items ON items.cart_id = carts.cart_id
                    """
                ).fetchone()
                abandoned_value = round(row["abandoned_value"], 2)
                total_value = round(row["total_value"], 2)
                return {
                    "metric": metric,
                    "value": {"abandoned_value": abandoned_value, "total_value": total_value, "missed_opportunity_rate": round(abandoned_value / total_value, 4) if total_value else 0},
                    "source": "curated_carts+curated_cart_items",
                    "definition": "Abandoned cart item value; missed opportunity rate = abandoned cart value / total cart value",
                }
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
        elif event_type in {"CartItemAdded", "CartItemUpdated"}:
            quantity = int(payload.get("quantity", 0) or 0)
            unit_price = float(payload.get("unit_price", 0) or 0)
            self.connection.execute(
                "INSERT OR REPLACE INTO curated_cart_items (cart_item_id, cart_id, product_id, quantity, unit_price, value) VALUES (?, ?, ?, ?, ?, ?)",
                (payload["cart_item_id"], payload["cart_id"], payload["product_id"], quantity, unit_price, quantity * unit_price),
            )
        elif event_type == "CartItemRemoved":
            self.connection.execute("DELETE FROM curated_cart_items WHERE cart_item_id = ?", (payload["cart_item_id"],))
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
        elif event_type in {"ProductCreated", "ProductUpdated"} and payload.get("product_id"):
            self._upsert_product(payload)
        elif event_type == "CategoryCreated" and payload.get("category_id") and payload.get("name"):
            self._upsert_category(payload)
        elif event_type in {"PageVisit", "ContentView", "Search", "TimeOnPage", "Exit"}:
            self.connection.execute(
                "INSERT OR REPLACE INTO curated_content_activity VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, payload.get("session_id", event.get("correlation_id")), payload.get("customer_id"), payload.get("content_id", payload.get("last_page")), event_type, occurred_at, float(payload.get("duration_seconds", 0) or 0)),
            )
        elif event_type in {"FeedbackSubmitted", "FeedbackUpdated"}:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO curated_feedback
                (feedback_id, customer_id, source, rating, comment, product_id, order_id,
                 campaign_id, site_id, sentiment, status, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("feedback_id", event["aggregate_id"]), payload["customer_id"],
                    payload.get("source", "unknown"), int(payload.get("rating", 0) or 0),
                    payload.get("comment"), payload.get("product_id"), payload.get("order_id"),
                    payload.get("campaign_id"), payload.get("site_id"),
                    payload.get("sentiment", "unknown"), payload.get("status", "submitted"), occurred_at,
                ),
            )
        elif event_type == "FeedbackDeleted":
            self.connection.execute("DELETE FROM curated_feedback WHERE feedback_id = ?", (payload.get("feedback_id", event["aggregate_id"]),))

    def quality(self) -> dict[str, Any]:
        with self.lock:
            raw_count = self.connection.execute("SELECT COUNT(*) AS value FROM raw_events").fetchone()["value"]
            latest = self.connection.execute("SELECT MAX(occurred_at) AS value FROM raw_events").fetchone()["value"]
            missing_times = self.connection.execute("SELECT COUNT(*) AS value FROM raw_events WHERE occurred_at = ''").fetchone()["value"]
            return {"raw_events": raw_count, "latest_occurred_at": latest, "checks": {"missing_occurred_at": missing_times, "passed": missing_times == 0}, "curated_tables": {"visits": self.connection.execute("SELECT COUNT(*) AS value FROM curated_visits").fetchone()["value"], "content_activity": self.connection.execute("SELECT COUNT(*) AS value FROM curated_content_activity").fetchone()["value"], "finance": self.connection.execute("SELECT COUNT(*) AS value FROM curated_finance").fetchone()["value"]}}

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {"metric": "revenue", "definition": "Succeeded order total", "source": "curated_orders", "grain": "order", "lineage": "OrderCreated -> curated_orders", "owner": "finance"},
            {"metric": "average_cart_value", "definition": "Average total amount of successful orders", "source": "curated_orders", "grain": "order", "lineage": "OrderCreated -> curated_orders", "owner": "commerce"},
            {"metric": "payment_failures", "definition": "Count of PaymentFailed events", "source": "raw_events", "grain": "payment event", "lineage": "PaymentFailed -> raw_events", "owner": "commerce"},
            {"metric": "customer_complaints", "definition": "Count of low-rated or negative/mixed-sentiment feedback", "source": "curated_feedback", "grain": "feedback record", "lineage": "FeedbackSubmitted/FeedbackUpdated -> curated_feedback", "owner": "customer"},
            {"metric": "conversion", "definition": "Succeeded orders divided by visits", "source": "curated_visits+curated_orders", "grain": "period", "lineage": "VisitStarted + OrderCreated", "owner": "digital"},
            {"metric": "abandoned_cart_value", "definition": "Abandoned cart value and share of total cart value", "source": "curated_carts+curated_cart_items", "grain": "cart item", "lineage": "CartCreated + CartItemAdded + CartAbandoned", "owner": "commerce"},
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

    def payment_failures_by_profile(self, dimension: str, profiles: Mapping[str, str | None]) -> dict[str, Any]:
        if dimension not in {"country", "age_group"}:
            raise ValueError("Unsupported customer profile dimension")
        with self.lock:
            rows = self.connection.execute("""
                SELECT COALESCE(json_extract(events.payload, '$.customer_id'), orders.customer_id) AS customer_id,
                       COUNT(*) AS failures
                FROM raw_events AS events
                LEFT JOIN curated_orders AS orders ON orders.order_id = events.aggregate_id
                WHERE events.event_type = 'PaymentFailed'
                GROUP BY COALESCE(json_extract(events.payload, '$.customer_id'), orders.customer_id)
            """).fetchall()
        totals: dict[str, int] = {}
        members: dict[str, set[str]] = {}
        unmatched = 0
        for row in rows:
            group = profiles.get(row["customer_id"]) if row["customer_id"] else None
            if group:
                totals[group] = totals.get(group, 0) + row["failures"]
                members.setdefault(group, set()).add(row["customer_id"])
            else:
                unmatched += row["failures"]
        return {
            "dimension": dimension,
            "rows": [{"group": group, "value": count} for group, count in sorted(totals.items(), key=lambda item: (-item[1], item[0])) if len(members[group]) >= 3],
            "unmatched_events": unmatched,
            "suppressed_groups": sum(len(members[group]) < 3 for group in totals),
            "definition": "Count of PaymentFailed events grouped by current CRM customer profile; not a failure rate",
            "source": "raw_events + curated_orders + CRM customer profiles",
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