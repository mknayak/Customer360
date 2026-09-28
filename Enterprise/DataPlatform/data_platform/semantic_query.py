"""Retrieval-driven semantic query planning and deterministic SQL compilation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


_TOKEN = re.compile(r"[A-Za-z0-9_-]+")


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in _TOKEN.findall(value))


@dataclass(frozen=True)
class JoinSpec:
    name: str
    table: str
    alias: str
    left_alias: str
    left_column: str
    right_column: str
    join_type: str = "JOIN"


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    name: str
    domain: str
    description: str
    aliases: tuple[str, ...]
    model: str
    measure_sql: str
    value_alias: str
    dimensions: Mapping[str, str]
    filters: Mapping[str, str]
    default_dimensions: tuple[str, ...] = ()
    default_order: str = "desc"
    security_classification: str = "internal_aggregate"
    owner: str = "data-platform"
    lineage: tuple[str, ...] = ()
    base_predicates: tuple[str, ...] = ()
    joins: Mapping[str, JoinSpec] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticQueryIR:
    metric: str
    dimensions: tuple[str, ...] = ()
    filters: Mapping[str, Any] = field(default_factory=dict)
    order: str = "desc"
    limit: int = 25
    joins: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    parameters: tuple[Any, ...]
    metric: MetricSpec
    dimensions: tuple[str, ...]


class SemanticCatalog:
    def __init__(self, metrics: Iterable[MetricSpec] | None = None) -> None:
        self._metrics = {metric.metric_id: metric for metric in metrics or default_metrics()}

    def get(self, metric_id: str) -> MetricSpec:
        try:
            return self._metrics[metric_id]
        except KeyError as error:
            raise ValueError(f"Unknown semantic metric: {metric_id}") from error

    def metrics(self) -> tuple[MetricSpec, ...]:
        return tuple(self._metrics.values())


class DomainRouter:
    DOMAINS = {
        "digital": ("page", "visit", "traffic", "drop", "exit", "content", "session", "website"),
        "commerce": ("product", "order", "cart", "purchase", "sales", "units", "payment", "failed"),
        "finance": ("revenue", "margin", "profit", "cost", "finance"),
    }

    def route(self, question: str) -> tuple[str, ...]:
        normalized = question.casefold()
        matches = tuple(domain for domain, terms in self.DOMAINS.items() if any(term in normalized for term in terms))
        return matches or ("digital", "commerce", "finance")


class MetadataRetriever:
    def __init__(self, catalog: SemanticCatalog, router: DomainRouter | None = None) -> None:
        self.catalog = catalog
        self.router = router or DomainRouter()

    def retrieve(self, question: str, limit: int = 5) -> tuple[MetricSpec, ...]:
        if not question.strip():
            raise ValueError("Semantic query question cannot be empty")
        domains = set(self.router.route(question))
        tokens = set(_tokens(question.casefold()))
        ranked: list[tuple[int, MetricSpec]] = []
        for metric in self.catalog.metrics():
            if metric.domain not in domains:
                continue
            searchable = " ".join((metric.metric_id, metric.name, metric.description, *metric.aliases)).casefold()
            score = sum(1 for token in tokens if token in searchable)
            phrase_bonus = sum(3 for alias in metric.aliases if alias.casefold() in question.casefold())
            ranked.append((score + phrase_bonus, metric))
        ranked.sort(key=lambda item: (-item[0], item[1].metric_id))
        return tuple(metric for score, metric in ranked[:limit] if score > 0)


class SchemaGraph:
    def context(self, metric: MetricSpec) -> dict[str, Any]:
        return {
            "metric": metric.metric_id,
            "domain": metric.domain,
            "model": metric.model,
            "dimensions": tuple(metric.dimensions),
            "filters": tuple(metric.filters),
            "lineage": metric.lineage,
            "security_classification": metric.security_classification,
            "owner": metric.owner,
        }


class QueryIRValidator:
    def validate(self, query: SemanticQueryIR, metric: MetricSpec) -> SemanticQueryIR:
        dimensions = query.dimensions or metric.default_dimensions
        unknown_dimensions = set(dimensions) - set(metric.dimensions)
        if unknown_dimensions:
            raise ValueError(f"Unsupported dimensions for {metric.metric_id}: {', '.join(sorted(unknown_dimensions))}")
        unknown_filters = set(query.filters) - set(metric.filters)
        if unknown_filters:
            raise ValueError(f"Unsupported filters for {metric.metric_id}: {', '.join(sorted(unknown_filters))}")
        unknown_joins = set(query.joins) - set(metric.joins)
        if unknown_joins:
            raise ValueError(f"Unsupported joins for {metric.metric_id}: {', '.join(sorted(unknown_joins))}")
        if query.order not in {"asc", "desc"}:
            raise ValueError("Semantic query order must be asc or desc")
        if not 1 <= query.limit <= 1000:
            raise ValueError("Semantic query limit must be between 1 and 1000")
        return SemanticQueryIR(query.metric, tuple(dimensions), dict(query.filters), query.order, query.limit, tuple(query.joins))


class QueryPolicyGate:
    """Fail closed before compilation when the principal cannot query a domain."""

    def __init__(self, grants: Mapping[str, Iterable[str]] | None = None) -> None:
        grants = grants or {"cfo-1": ("digital", "commerce", "finance"), "executive-1": ("digital", "commerce", "finance")}
        self._grants = {principal: frozenset(domains) for principal, domains in grants.items()}

    def domains(self, principal_id: str) -> frozenset[str]:
        return self._grants.get(principal_id, frozenset())

    def authorize(self, principal_id: str, metric: MetricSpec) -> None:
        domains = self._grants.get(principal_id, frozenset())
        if metric.domain not in domains and "*" not in domains:
            raise PermissionError(f"{principal_id} is not authorized for {metric.domain} semantic queries")


class SQLCompiler:
    def compile(self, query: SemanticQueryIR, metric: MetricSpec) -> CompiledQuery:
        selected_dimensions = [f"{metric.dimensions[name]} AS {name}" for name in query.dimensions]
        select = selected_dimensions + [f"{metric.measure_sql} AS {metric.value_alias}"]
        clauses: list[str] = list(metric.base_predicates)
        parameters: list[Any] = []
        for name, value in query.filters.items():
            clauses.append(f"{metric.filters[name]} = ?")
            parameters.append(value)
        sql = f"SELECT {', '.join(select)} FROM {metric.model}"
        aliases = {"base"}
        for join_name in query.joins:
            join = metric.joins.get(join_name)
            if join is None:
                raise ValueError(f"Unsupported join for {metric.metric_id}: {join_name}")
            if join.alias in aliases or join.left_alias not in aliases:
                raise ValueError(f"Invalid join path for {metric.metric_id}: {join_name}")
            if join.join_type not in {"JOIN", "INNER JOIN", "LEFT JOIN"}:
                raise ValueError(f"Unsupported join type for {join_name}: {join.join_type}")
            sql += f" {join.join_type} {join.table} AS {join.alias} ON {join.left_alias}.{join.left_column} = {join.alias}.{join.right_column}"
            aliases.add(join.alias)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        if selected_dimensions:
            sql += " GROUP BY " + ", ".join(metric.dimensions[name] for name in query.dimensions)
        sql += f" ORDER BY {metric.value_alias} {query.order.upper()} LIMIT ?"
        parameters.append(query.limit)
        return CompiledQuery(sql, tuple(parameters), metric, query.dimensions)


class SemanticQueryPlanner:
    def __init__(self, catalog: SemanticCatalog | None = None, policy: QueryPolicyGate | None = None) -> None:
        self.catalog = catalog or SemanticCatalog()
        self.retriever = MetadataRetriever(self.catalog)
        self.graph = SchemaGraph()
        self.validator = QueryIRValidator()
        self.compiler = SQLCompiler()
        self.policy = policy or QueryPolicyGate()

    def context(self, question: str, limit: int = 5) -> dict[str, Any]:
        candidates = self.retriever.retrieve(question, limit)
        return {
            "question": question,
            "domains": self.retriever.router.route(question),
            "candidates": [self.graph.context(metric) | {"name": metric.name, "description": metric.description} for metric in candidates],
        }

    def plan(self, query: SemanticQueryIR, principal_id: str) -> CompiledQuery:
        metric = self.catalog.get(query.metric)
        self.policy.authorize(principal_id, metric)
        validated = self.validator.validate(query, metric)
        return self.compiler.compile(validated, metric)


def default_metrics() -> tuple[MetricSpec, ...]:
    return (
        MetricSpec("revenue", "Revenue", "finance", "Succeeded order revenue", ("sales", "net sales"), "curated_orders", "ROUND(SUM(total_amount), 2)", "value", {"customer": "customer_id", "period": "substr(occurred_at, 1, 10)"}, {"customer": "customer_id", "payment_status": "payment_status"}, lineage=("OrderCreated", "curated_orders")),
        MetricSpec("average_cart_value", "Average cart value", "commerce", "Average total amount of successful orders", ("average order value", "average cart", "avg cart value", "cart value"), "curated_orders", "ROUND(AVG(total_amount), 2)", "value", {"period": "substr(occurred_at, 1, 10)"}, {}, lineage=("OrderCreated", "curated_orders"), base_predicates=("payment_status = 'succeeded'",)),
        MetricSpec("payment_failures", "Payment failures", "commerce", "Count of PaymentFailed events", ("payment failed", "failed payment", "payment failure", "declined payment"), "raw_events", "COUNT(*)", "value", {"period": "substr(occurred_at, 1, 10)", "customer": "json_extract(payload, '$.customer_id')", "failure_reason": "json_extract(payload, '$.failure_reason')"}, {}, lineage=("PaymentFailed", "raw_events"), base_predicates=("event_type = 'PaymentFailed'",)),
        MetricSpec("visits", "Visits", "digital", "Count of site visits", ("traffic", "visit volume"), "curated_visits", "COUNT(*)", "value", {"site": "site_id", "customer": "customer_id", "period": "substr(occurred_at, 1, 10)"}, {"site": "site_id", "customer": "customer_id"}, lineage=("VisitStarted", "curated_visits")),
        MetricSpec("content_views", "Content views", "digital", "Count of content view events", ("page views", "content viewed"), "curated_content_activity", "COUNT(*)", "value", {"page": "content_id", "customer": "customer_id", "period": "substr(occurred_at, 1, 10)"}, {"page": "content_id", "customer": "customer_id"}, ("page",), lineage=("ContentView", "curated_content_activity"), base_predicates=("event_type = 'ContentView'",)),
        MetricSpec("page_popularity", "Page popularity", "digital", "Content views grouped by page", ("most visited page", "popular page", "top page", "most viewed page"), "curated_content_activity", "COUNT(*)", "views", {"page": "content_id", "period": "substr(occurred_at, 1, 10)"}, {"page": "content_id"}, ("page",), lineage=("ContentView", "curated_content_activity"), base_predicates=("event_type = 'ContentView'",)),
        MetricSpec("average_time_on_page", "Average time on page", "digital", "Average content dwell time in seconds", ("dwell time", "time on page"), "curated_content_activity", "ROUND(AVG(duration_seconds), 2)", "value", {"page": "content_id", "period": "substr(occurred_at, 1, 10)"}, {"page": "content_id"}, ("page",), lineage=("TimeOnPage", "curated_content_activity"), base_predicates=("event_type = 'TimeOnPage'",)),
        MetricSpec("page_dropoff", "Page dropoff", "digital", "Sessions ending on each page", ("most dropped page", "page exits", "drop off page", "dropoff"), "curated_content_activity", "COUNT(*)", "exits", {"page": "content_id", "period": "substr(occurred_at, 1, 10)"}, {"page": "content_id"}, ("page",), lineage=("Exit", "curated_content_activity"), base_predicates=("event_type = 'Exit'",)),
        MetricSpec("product_performance", "Product performance", "commerce", "Units and revenue by product", ("top product", "selling product", "units sold"), "curated_order_items", "SUM(quantity)", "units", {"product": "base.product_id", "customer": "orders.customer_id"}, {"product": "base.product_id", "customer": "orders.customer_id"}, ("product",), lineage=("OrderCreated.items", "curated_order_items"), joins={"orders": JoinSpec("orders", "curated_orders", "orders", "base", "order_id", "order_id")}),
    )
