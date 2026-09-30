"""Schema retrieval and guarded execution for LLM-generated SQL.

Offline: crawl warehouse metadata and index table/column documents as vectors.
Runtime: retrieve candidate tables, link them through declared join paths, inject
business rules, and return a pruned schema context. Generated SQL is executed on a
read-only connection behind an authorizer that allows SELECT on granted tables only.
"""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import time
import uuid
from collections import deque
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .semantic_query import MetricSpec, QueryPolicyGate, SemanticCatalog


@dataclass(frozen=True)
class ColumnMeta:
    name: str
    data_type: str
    description: str = ""
    sample_values: tuple[Any, ...] = ()
    value_range: tuple[Any, Any] | None = None
    null_fraction: float | None = None


@dataclass(frozen=True)
class TableMeta:
    name: str
    domain: str
    description: str
    columns: tuple[ColumnMeta, ...]
    row_count: int
    grain: str = ""


@dataclass(frozen=True)
class Relationship:
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    description: str = ""


@dataclass(frozen=True)
class BusinessRule:
    rule_id: str
    text: str
    triggers: tuple[str, ...]
    tables: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaCatalogSnapshot:
    tables: Mapping[str, TableMeta]
    relationships: tuple[Relationship, ...]
    crawled_at: str


TABLE_ANNOTATIONS: Mapping[str, Mapping[str, Any]] = {
    "raw_events": {
        "domain": "commerce",
        "grain": "one row per ingested business event",
        "description": "Immutable raw event log from all services. Use for event types without a curated table, e.g. PaymentFailed, PaymentCompleted, FeedbackSubmitted, CampaignInteractionRecorded, Search.",
        "columns": {
            "event_type": "Business event name",
            "source_service": "Emitting service",
            "aggregate_type": "Entity type the event is about (order, cart, visit, product)",
            "aggregate_id": "Identifier of the entity the event is about",
            "payload": "JSON event body; read fields with json_extract(payload, '$.field')",
            "occurred_at": "ISO-8601 event timestamp text",
            "correlation_id": "Journey or session correlation identifier",
        },
    },
    "curated_visits": {
        "domain": "digital",
        "grain": "one row per site visit",
        "description": "Site visits and traffic sessions by customer and site.",
        "columns": {"visit_id": "Visit identifier", "customer_id": "Visiting customer", "site_id": "Site or store visited", "occurred_at": "ISO-8601 visit start"},
    },
    "curated_carts": {
        "domain": "commerce",
        "grain": "one row per shopping cart",
        "description": "Shopping carts created and whether they were abandoned.",
        "columns": {"cart_id": "Cart identifier", "customer_id": "Cart owner", "occurred_at": "ISO-8601 cart creation", "abandoned": "1 when the cart was abandoned, else 0"},
    },
    "curated_orders": {
        "domain": "commerce",
        "grain": "one row per order",
        "description": "Customer orders with payment outcome and order total amount (sales, revenue, purchases).",
        "columns": {"order_id": "Order identifier", "customer_id": "Purchasing customer", "occurred_at": "ISO-8601 order timestamp", "payment_status": "Payment outcome of the order", "total_amount": "Order total amount in USD (order revenue)"},
    },
    "curated_order_items": {
        "domain": "commerce",
        "grain": "one row per order and product",
        "description": "Order line items: units sold and line revenue per product (sales by product, category, brand).",
        "columns": {"order_id": "Parent order", "product_id": "Product sold", "quantity": "Units sold", "revenue": "Line revenue in USD after line discount"},
    },
    "curated_content_activity": {
        "domain": "digital",
        "grain": "one row per content interaction event",
        "description": "Website content activity: page visits, content views, searches, time on page and exits.",
        "columns": {"event_id": "Event identifier", "session_id": "Browsing session", "customer_id": "Customer if known", "content_id": "Page or content identifier", "event_type": "Interaction type", "occurred_at": "ISO-8601 timestamp", "duration_seconds": "Time on page in seconds"},
    },
    "curated_finance": {
        "domain": "finance",
        "grain": "one row per order",
        "description": "Order-level finance facts: revenue, cost, margin and profit by site and promotion.",
        "columns": {"order_id": "Order identifier", "customer_id": "Customer", "site_id": "Selling site", "promotion_id": "Applied promotion", "revenue": "Order revenue in USD", "cost": "Order cost in USD; zero when the source did not provide cost", "margin": "Revenue minus cost (gross profit)", "occurred_at": "ISO-8601 order timestamp"},
    },
    "dim_products": {
        "domain": "commerce",
        "grain": "one row per product",
        "description": "Product master data: product name, SKU, brand, status and category assignment.",
        "columns": {"product_id": "Product identifier", "sku": "Stock keeping unit", "name": "Product display name", "description": "Product description", "category_id": "Assigned product category", "brand": "Product brand", "status": "Product lifecycle status", "updated_at": "Last product update"},
    },
    "dim_categories": {
        "domain": "commerce",
        "grain": "one row per product category",
        "description": "Product category hierarchy (category, department, product group).",
        "columns": {"category_id": "Category identifier", "name": "Category display name", "parent_category_id": "Parent category in the hierarchy"},
    },
    "dim_customer_profiles": {
        "domain": "customer",
        "grain": "one row per customer",
        "description": "Current non-PII customer profile attributes for governed demographic segmentation.",
        "columns": {"customer_id": "Customer identifier", "age_group": "Coarse age band", "city": "Customer city", "country": "Customer country", "preferred_channel": "Preferred contact channel", "status": "Customer lifecycle status", "updated_at": "Profile snapshot freshness"},
    },
    "curated_feedback": {
        "domain": "customer",
        "grain": "one row per customer feedback record",
        "description": "Customer feedback and ratings from the feedback simulator. Complaint candidates are low-rated or negative/mixed-sentiment feedback; comments provide qualitative evidence for complaint themes.",
        "columns": {
            "feedback_id": "Feedback identifier", "customer_id": "Customer who submitted feedback", "source": "Feedback channel",
            "rating": "Customer rating from 1 to 5", "comment": "Customer's written feedback or complaint text",
            "product_id": "Referenced product if provided", "order_id": "Referenced order if provided", "campaign_id": "Referenced campaign if provided", "site_id": "Referenced site if provided",
            "sentiment": "Classified sentiment: positive, neutral, negative, mixed or unknown", "status": "Feedback review status", "occurred_at": "ISO-8601 submission or update timestamp",
        },
    },
}

RELATIONSHIPS: tuple[Relationship, ...] = (
    Relationship("curated_order_items", "order_id", "curated_orders", "order_id", "line items belong to an order"),
    Relationship("curated_order_items", "product_id", "dim_products", "product_id", "line item references a product"),
    Relationship("curated_orders", "customer_id", "dim_customer_profiles", "customer_id", "order belongs to a profiled customer"),
    Relationship("dim_products", "category_id", "dim_categories", "category_id", "product is assigned to a category"),
    Relationship("curated_finance", "order_id", "curated_orders", "order_id", "finance fact for an order"),
    Relationship("raw_events", "aggregate_id", "curated_orders", "order_id", "order events; also filter raw_events.aggregate_type = 'order'"),
    Relationship("curated_feedback", "customer_id", "dim_customer_profiles", "customer_id", "feedback belongs to a profiled customer"),
)

BUSINESS_RULES: tuple[BusinessRule, ...] = (
    BusinessRule("revenue", "Revenue counts only orders with curated_orders.payment_status = 'succeeded'. Order-level revenue is SUM(curated_orders.total_amount); product-, brand- or category-level revenue is SUM(curated_order_items.revenue) joined to curated_orders with payment_status = 'succeeded'.", ("revenue", "sales", "turnover", "income", "contribute", "contribution"), ("curated_orders", "curated_order_items")),
    BusinessRule("category", "Category comes from dim_categories.name via curated_order_items.product_id -> dim_products.product_id -> dim_products.category_id -> dim_categories.category_id. Use LEFT JOINs and report products without a category as 'Uncategorized' so totals reconcile; disclose the uncategorized share.", ("category", "categories", "department", "product group"), ("curated_order_items", "dim_products", "dim_categories")),
    BusinessRule("brand", "Brand comes from dim_products.brand via curated_order_items.product_id. Report missing brands as 'Unknown'.", ("brand", "brands"), ("curated_order_items", "dim_products")),
    BusinessRule("product_name", "Report products by dim_products.name (LEFT JOIN on product_id, fall back to product_id), never by raw identifier alone.", ("product", "products", "sku", "item"), ("curated_order_items", "dim_products")),
    BusinessRule("customer_age", "Customer age segmentation comes from dim_customer_profiles.age_group joined through curated_orders.customer_id. Available bands are 18-24, 25-34, 35-44, 45-54, and 55-64. An exact 40+ cohort is not derivable because 35-44 crosses the threshold; do not silently include or exclude that band. Mark an exact 40+ request unanswerable unless the user accepts a 45+ approximation.", ("age", "older", "generation", "40+", "45+", "demographic"), ("curated_orders", "dim_customer_profiles")),
    BusinessRule("time", "Timestamps are ISO-8601 TEXT. Use date(occurred_at) for day, substr(occurred_at, 1, 7) for month, and exclude occurred_at = ''. For relative periods such as 'last N days' use a rolling window that includes today: occurred_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-N days'). Never hard-code calendar dates for relative periods.", ("last", "past", "recent", "day", "daily", "week", "weekly", "month", "monthly", "year", "trend", "period", "when", "date", "time"), ()),
    BusinessRule("conversion", "Conversion = succeeded orders / visits for the same period (curated_orders with payment_status = 'succeeded' over curated_visits).", ("conversion", "convert", "funnel"), ("curated_orders", "curated_visits")),
    BusinessRule("cart_abandonment", "Cart abandonment = SUM(curated_carts.abandoned) / COUNT(*) of curated_carts.", ("abandon", "abandonment", "cart"), ("curated_carts",)),
    BusinessRule("payment_failure", "Payment failures are raw_events rows with event_type = 'PaymentFailed'; the reason is json_extract(payload, '$.failure_reason'). This is a count, not a rate, unless divided by payment attempts.", ("payment", "fail", "failure", "declined"), ("raw_events",)),
    BusinessRule("customer_complaints", "Customer complaints are observed feedback records where rating <= 2 or sentiment IN ('negative', 'mixed'). For 'top complaints', rank complaint records or explicit dimensions such as product, site, source or month; use comment text as qualitative evidence and do not invent themes from absent labels.", ("complaint", "complaints", "feedback", "dissatisfaction", "negative review", "customer voice"), ("curated_feedback",)),
    BusinessRule("margin", "Gross margin = SUM(margin) / SUM(revenue) from curated_finance. Cost defaults to zero when the source omitted it, so margin may be overstated; disclose this.", ("margin", "profit", "cost", "profitability"), ("curated_finance",)),
    BusinessRule("ratios", "Guard ratios against division by zero with NULLIF and round monetary results to 2 decimals.", ("rate", "ratio", "share", "percent", "percentage", "average", "avg"), ()),
)

_STOPWORDS = frozenset(
    "a an the is are was were be of by to for in on at and or with which what who whom how many much most least top "
    "does do did has have had show me give list tell our we i it its this that these those per from vs versus than "
    "contributes contribute contributing highest lowest best worst".split()
)
_WORD = re.compile(r"[a-z0-9]+")


def normalize_terms(text: str) -> list[str]:
    terms = []
    for word in _WORD.findall(text.casefold().replace("_", " ")):
        if word in _STOPWORDS:
            continue
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        terms.append(word)
    return terms


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Dependency-free lexical embedding; swap for a model embedder via the Embedder protocol."""

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature, weight in self._features(text):
            digest = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
            vector[digest % self.dimensions] += weight if digest >> 63 else -weight
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    @staticmethod
    def _features(text: str) -> Iterable[tuple[str, float]]:
        for term in normalize_terms(text):
            yield f"w:{term}", 1.0
            if len(term) >= 5:
                for index in range(len(term) - 2):
                    yield f"c:{term[index:index + 3]}", 0.25


class SchemaCrawler:
    """Extract table, column, relationship and profile metadata from the warehouse."""

    def __init__(self, annotations: Mapping[str, Mapping[str, Any]] = TABLE_ANNOTATIONS, relationships: Sequence[Relationship] = RELATIONSHIPS, sample_limit: int = 12) -> None:
        self.annotations = annotations
        self.relationships = tuple(relationships)
        self.sample_limit = sample_limit

    def crawl(self, connection: sqlite3.Connection) -> SchemaCatalogSnapshot:
        table_names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        # Only annotated tables are exposed; unannotated tables have no governed domain.
        tables = {name: self._table(connection, name) for name in table_names if name in self.annotations}
        declared = {(r.left_table, r.left_column, r.right_table, r.right_column) for r in self.relationships}
        relationships = list(self.relationships)
        for name in tables:
            for row in connection.execute(f'PRAGMA foreign_key_list("{name}")'):
                key = (name, row[3], row[2], row[4])
                if row[2] in tables and key not in declared:
                    relationships.append(Relationship(*key, "declared foreign key"))
        relationships = [r for r in relationships if r.left_table in tables and r.right_table in tables]
        return SchemaCatalogSnapshot(tables, tuple(relationships), datetime.now(timezone.utc).isoformat())

    def _table(self, connection: sqlite3.Connection, name: str) -> TableMeta:
        annotation = self.annotations[name]
        descriptions = annotation.get("columns", {})
        row_count = connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        fk_columns = {r.left_column for r in self.relationships if r.left_table == name}
        columns = []
        for _, column, data_type, *_ in connection.execute(f'PRAGMA table_info("{name}")'):
            samples: tuple[Any, ...] = ()
            value_range = None
            null_fraction = None
            if row_count and column == "occurred_at":
                value_range = tuple(connection.execute(f'SELECT MIN("{column}"), MAX("{column}") FROM "{name}" WHERE "{column}" != \'\'').fetchone())
            elif row_count and data_type.upper() == "TEXT" and not column.endswith("_id") and column not in {"payload", "description"}:
                values = connection.execute(f'SELECT DISTINCT "{column}" FROM "{name}" WHERE "{column}" IS NOT NULL LIMIT ?', (self.sample_limit + 1,)).fetchall()
                if len(values) <= self.sample_limit:
                    samples = tuple(value[0] for value in values)
            if row_count and column in fk_columns:
                nulls = connection.execute(f'SELECT COUNT(*) FROM "{name}" WHERE "{column}" IS NULL OR "{column}" = \'\'').fetchone()[0]
                null_fraction = round(nulls / row_count, 4)
            columns.append(ColumnMeta(column, data_type, descriptions.get(column, ""), samples, value_range, null_fraction))
        return TableMeta(name, annotation["domain"], annotation["description"], tuple(columns), row_count, annotation.get("grain", ""))


class SchemaVectorIndex:
    """In-memory vector index over table and column documents."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or HashingEmbedder()
        self._entries: list[tuple[str, str | None, list[float]]] = []

    def build(self, snapshot: SchemaCatalogSnapshot) -> None:
        entries = []
        for table in snapshot.tables.values():
            table_document = f"{table.name} {table.description} {table.grain} columns: {' '.join(column.name for column in table.columns)}"
            entries.append((table.name, None, self.embedder.embed(table_document)))
            for column in table.columns:
                entries.append((table.name, column.name, self.embedder.embed(f"{table.name} {column.name} {column.description}")))
        self._entries = entries

    def search(self, question: str, allowed_tables: Iterable[str], limit: int) -> list[tuple[str, float, tuple[str, ...]]]:
        query = self.embedder.embed(question)
        allowed = set(allowed_tables)
        table_scores: dict[str, float] = {}
        best_columns: dict[str, list[tuple[float, str]]] = {}
        for table, column, vector in self._entries:
            if table not in allowed:
                continue
            score = sum(left * right for left, right in zip(query, vector))
            if column is None:
                table_scores[table] = table_scores.get(table, 0.0) + score
            else:
                best_columns.setdefault(table, []).append((score, column))
        ranked = []
        for table in allowed:
            columns = sorted(best_columns.get(table, []), reverse=True)
            column_score = columns[0][0] if columns else 0.0
            score = table_scores.get(table, 0.0) + column_score
            ranked.append((table, round(score, 4), tuple(name for value, name in columns[:3] if value > 0.1)))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return [item for item in ranked[:limit] if item[1] > 0.15]


class JoinGraphLinker:
    """Connect candidate tables through the shortest declared join paths."""

    def __init__(self, relationships: Sequence[Relationship]) -> None:
        self._edges: dict[str, list[tuple[str, Relationship]]] = {}
        for relationship in relationships:
            if relationship.left_table == relationship.right_table:
                continue
            self._edges.setdefault(relationship.left_table, []).append((relationship.right_table, relationship))
            self._edges.setdefault(relationship.right_table, []).append((relationship.left_table, relationship))

    def link(self, tables: Sequence[str], allowed: Iterable[str], max_depth: int = 4) -> tuple[list[str], list[Relationship], list[str]]:
        allowed_set = set(allowed)
        ordered = [table for table in dict.fromkeys(tables) if table in allowed_set]
        if not ordered:
            return [], [], []
        connected = [ordered[0]]
        edges: list[Relationship] = []
        unreachable: list[str] = []
        for target in ordered[1:]:
            if target in connected:
                continue
            path = self._shortest_path(set(connected), target, allowed_set, max_depth)
            if path is None:
                unreachable.append(target)
                connected.append(target)
                continue
            for node, relationship in path:
                if node not in connected:
                    connected.append(node)
                if relationship not in edges:
                    edges.append(relationship)
        return connected, edges, unreachable

    def _shortest_path(self, sources: set[str], target: str, allowed: set[str], max_depth: int) -> list[tuple[str, Relationship]] | None:
        queue: deque[tuple[str, list[tuple[str, Relationship]]]] = deque((source, []) for source in sources)
        seen = set(sources)
        while queue:
            node, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for neighbor, relationship in self._edges.get(node, ()):
                if neighbor in seen or neighbor not in allowed:
                    continue
                next_path = path + [(neighbor, relationship)]
                if neighbor == target:
                    return next_path
                seen.add(neighbor)
                queue.append((neighbor, next_path))
        return None


class BusinessRuleFilter:
    """Inject domain rules and governed metric definitions that apply to a question."""

    def __init__(self, rules: Sequence[BusinessRule] = BUSINESS_RULES, catalog: SemanticCatalog | None = None) -> None:
        self.rules = tuple(rules)
        self.catalog = catalog or SemanticCatalog()

    def select(self, question: str) -> tuple[list[BusinessRule], list[MetricSpec]]:
        normalized = question.casefold()
        terms = set(normalize_terms(question))
        rules = [rule for rule in self.rules if any(self._matches(trigger, normalized, terms) for trigger in rule.triggers)]
        metrics = [metric for metric in self.catalog.metrics() if any(self._matches(term, normalized, terms) for term in (metric.name, *metric.aliases, metric.metric_id.replace("_", " ")))]
        return rules, metrics

    @staticmethod
    def _matches(trigger: str, normalized: str, terms: set[str]) -> bool:
        trigger = trigger.casefold()
        if " " in trigger:
            return trigger in normalized
        trigger_terms = normalize_terms(trigger)
        return bool(trigger_terms) and any(term.startswith(trigger_terms[0]) for term in terms)


class SQLValidationError(ValueError):
    pass


_READ_ONLY_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_TRAILING_NOISE = re.compile(r"(?:\s|;|--[^\n]*$)+\Z", re.MULTILINE)
_CTE_NAME = re.compile(r"(?:\bwith(?:\s+recursive)?|,)\s*\"?([A-Za-z_]\w*)\"?\s*(?:\([^()]*\))?\s*as\s*(?:not\s+)?(?:materialized\s*)?\(", re.IGNORECASE)
_DENIED_FUNCTIONS = frozenset({"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer", "sqlite_offset"})


class TextToSQLService:
    """Offline schema indexing plus runtime schema pruning and guarded SQL execution."""

    def __init__(
        self,
        database_path: str | Path,
        policy: QueryPolicyGate | None = None,
        embedder: Embedder | None = None,
        crawler: SchemaCrawler | None = None,
        rules: BusinessRuleFilter | None = None,
        max_rows: int = 200,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.database_path = Path(database_path)
        self.policy = policy or QueryPolicyGate()
        self.crawler = crawler or SchemaCrawler()
        self.index = SchemaVectorIndex(embedder)
        self.rules = rules or BusinessRuleFilter()
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds
        self._lock = RLock()
        self._snapshot: SchemaCatalogSnapshot | None = None
        self._linker = JoinGraphLinker(())

    def refresh(self) -> dict[str, Any]:
        with self._connect() as connection:
            snapshot = self.crawler.crawl(connection)
        with self._lock:
            self.index.build(snapshot)
            self._snapshot = snapshot
            self._linker = JoinGraphLinker(snapshot.relationships)
        return {"tables": len(snapshot.tables), "relationships": len(snapshot.relationships), "crawled_at": snapshot.crawled_at}

    def snapshot(self) -> SchemaCatalogSnapshot:
        with self._lock:
            if self._snapshot is None:
                self.refresh()
            assert self._snapshot is not None
            return self._snapshot

    def allowed_tables(self, principal_id: str) -> set[str]:
        domains = self.policy.domains(principal_id)
        return {name for name, table in self.snapshot().tables.items() if "*" in domains or table.domain in domains}

    def context(self, question: str, principal_id: str, max_tables: int = 6) -> dict[str, Any]:
        if not question.strip():
            raise ValueError("Question cannot be empty")
        snapshot = self.snapshot()
        allowed = self.allowed_tables(principal_id)
        if not allowed:
            raise PermissionError(f"{principal_id} is not authorized for any warehouse domain")
        with self._lock:
            matches = self.index.search(question, allowed, max_tables)
            linker = self._linker
        rules, metrics = self.rules.select(question)
        seeds = [table for table, _, _ in matches]
        for rule in rules:
            seeds.extend(table for table in rule.tables if table in allowed)
        tables, joins, unreachable = linker.link(seeds, allowed)
        retrieval = {table: {"table": table, "score": score, "matched_columns": columns, "reason": "vector"} for table, score, columns in matches}
        for table in tables:
            if table not in retrieval:
                retrieval[table] = {"table": table, "score": None, "matched_columns": (), "reason": "business_rule" if any(table in rule.tables for rule in rules) else "join_path"}
        applicable_rules = [rule.text for rule in rules]
        applicable_rules += [
            f"Governed metric {metric.metric_id}: {metric.description} = {metric.measure_sql} FROM {metric.model}" + (f" WHERE {' AND '.join(metric.base_predicates)}" if metric.base_predicates else "")
            for metric in metrics if metric.model in allowed
        ]
        return {
            "question": question,
            "dialect": "sqlite",
            "tables": [self._table_context(snapshot.tables[table]) for table in tables],
            "join_paths": [{"left": f"{r.left_table}.{r.left_column}", "right": f"{r.right_table}.{r.right_column}", "description": r.description} for r in joins],
            "business_rules": applicable_rules,
            "unlinked_tables": unreachable,
            "retrieval": [retrieval[table] for table in tables],
            "withheld_table_count": len(snapshot.tables) - len(allowed),
            "max_rows": self.max_rows,
            "crawled_at": snapshot.crawled_at,
            "data_classification": "synthetic",
        }

    def execute(self, sql: str, principal_id: str, limit: int | None = None) -> dict[str, Any]:
        statement = _TRAILING_NOISE.sub("", sql.strip())
        if not statement:
            raise SQLValidationError("SQL cannot be empty")
        if not _READ_ONLY_START.match(statement):
            raise SQLValidationError("Only a single SELECT or WITH query is allowed")
        allowed = self.allowed_tables(principal_id)
        if not allowed:
            raise PermissionError(f"{principal_id} is not authorized for any warehouse domain")
        row_limit = min(limit or self.max_rows, self.max_rows)
        tables_read: set[str] = set()
        denied: list[str] = []
        cte_names: set[str] = set()

        def authorizer(action: int, arg1: str | None, arg2: str | None, database: str | None, source: str | None) -> int:
            if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ:
                if arg1 in allowed:
                    tables_read.add(arg1)
                    return sqlite3.SQLITE_OK
                if arg1 in cte_names:
                    return sqlite3.SQLITE_OK
                denied.append(str(arg1))
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION:
                return sqlite3.SQLITE_DENY if (arg2 or "").casefold() in _DENIED_FUNCTIONS else sqlite3.SQLITE_OK
            denied.append(f"action:{action}")
            return sqlite3.SQLITE_DENY

        # Newline guards against a trailing line comment swallowing the wrapper.
        wrapped = f"SELECT * FROM (\n{statement}\n) LIMIT ?"
        query_id = str(uuid.uuid4())
        started = time.perf_counter()
        deadline = time.monotonic() + self.timeout_seconds
        with self._connect() as connection:
            latest = connection.execute("SELECT MAX(occurred_at) FROM raw_events").fetchone()[0] if "raw_events" in self.snapshot().tables else None
            real_objects = {row[0].casefold() for row in connection.execute("SELECT name FROM sqlite_master")} | {"sqlite_master", "sqlite_schema", "sqlite_temp_master"}
            cte_names.update(name for name in _CTE_NAME.findall(statement) if name.casefold() not in real_objects)
            connection.set_authorizer(authorizer)
            connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
            try:
                cursor = connection.execute(wrapped, (row_limit + 1,))
                columns = [description[0] for description in cursor.description or ()]
                rows = cursor.fetchall()
            except sqlite3.DatabaseError as error:
                if denied:
                    raise PermissionError(f"Query references objects outside the authorized schema: {', '.join(sorted(set(denied)))}") from error
                if "interrupted" in str(error):
                    raise SQLValidationError(f"Query exceeded the {self.timeout_seconds:g}s time budget") from error
                raise SQLValidationError(f"SQL error: {error}") from error
            except sqlite3.ProgrammingError as error:
                raise SQLValidationError(f"SQL error: {error}") from error
        truncated = len(rows) > row_limit
        return {
            "query_id": query_id,
            "sql": statement,
            "columns": columns,
            "rows": [dict(zip(columns, row)) for row in rows[:row_limit]],
            "row_count": min(len(rows), row_limit),
            "truncated": truncated,
            "tables": sorted(tables_read),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "freshness": {"latest_event_at": latest, "queried_at": datetime.now(timezone.utc).isoformat()},
            "data_classification": "synthetic",
        }

    def _connect(self) -> closing[sqlite3.Connection]:
        return closing(sqlite3.connect(f"file:{self.database_path}?mode=ro", uri=True, check_same_thread=False))

    @staticmethod
    def _table_context(table: TableMeta) -> dict[str, Any]:
        columns = []
        for column in table.columns:
            item: dict[str, Any] = {"name": column.name, "type": column.data_type, "description": column.description}
            if column.sample_values:
                item["values"] = list(column.sample_values)
            if column.value_range:
                item["range"] = list(column.value_range)
            if column.null_fraction is not None:
                item["null_fraction"] = column.null_fraction
            columns.append(item)
        return {"name": table.name, "domain": table.domain, "grain": table.grain, "description": table.description, "row_count": table.row_count, "columns": columns}
