"""Governed semantic definitions for the Customer360 domain pack."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .tools import ToolExecution


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    name: str
    definition: str
    formula: str
    numerator: str | None
    denominator: str | None
    source: tuple[str, ...]
    owner: str
    grain: str
    exclusions: tuple[str, ...]
    currency: str | None
    time_zone: str
    version: str
    effective_from: str
    freshness_sla_hours: int
    aliases: tuple[str, ...] = ()
    classification: str = "internal"
    null_handling: str = "Exclude null inputs from numerator and denominator."


@dataclass(frozen=True)
class SemanticLookup:
    status: str
    term: str
    definitions: tuple[MetricDefinition, ...] = ()
    warnings: tuple[str, ...] = ()
    context: Mapping[str, Any] = field(default_factory=dict)


class SemanticRegistry:
    """Resolve only approved definitions; never infer a metric from its name."""

    def __init__(self, definitions: tuple[MetricDefinition, ...] | None = None) -> None:
        definitions = definitions or default_metric_definitions()
        self._definitions = {definition.metric_id: definition for definition in definitions}

    def definitions(self) -> tuple[MetricDefinition, ...]:
        return tuple(self._definitions.values())

    def lookup(
        self,
        term: str,
        *,
        context: Mapping[str, Any] | None = None,
        as_of: datetime | None = None,
    ) -> SemanticLookup:
        normalized = self._normalize(term)
        if not normalized:
            raise ValueError("Semantic term cannot be empty")
        matches = tuple(
            definition
            for definition in self._definitions.values()
            if normalized in {
                self._normalize(definition.metric_id),
                self._normalize(definition.name),
                *(self._normalize(alias) for alias in definition.aliases),
            }
        )
        if not matches:
            return SemanticLookup("not_found", term, context=dict(context or {}), warnings=("No approved definition found",))
        if len(matches) > 1:
            return SemanticLookup(
                "ambiguous", term, matches, ("Multiple approved definitions match; resolve the ambiguity before querying",), dict(context or {})
            )
        definition = matches[0]
        if as_of and self._is_stale(definition, as_of):
            return SemanticLookup(
                "stale", term, (definition,),
                (f"Definition freshness SLA exceeded for {definition.metric_id}",), dict(context or {})
            )
        return SemanticLookup("resolved", term, (definition,), context=dict(context or {}))

    def lookup_execution(self, inputs: Mapping[str, Any]) -> ToolExecution:
        term = inputs.get("term") or inputs.get("terms")
        if isinstance(term, (list, tuple)):
            if len(term) != 1:
                return ToolExecution(data={"status": "ambiguous", "terms": tuple(term)}, warnings=("Resolve one semantic term at a time",))
            term = term[0]
        if not isinstance(term, str):
            raise ValueError("Semantic lookup requires a string term")
        as_of = inputs.get("as_of")
        if isinstance(as_of, str):
            as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if as_of is not None and not isinstance(as_of, datetime):
            raise ValueError("Semantic lookup as_of must be an ISO datetime")
        result = self.lookup(term, context=inputs.get("context"), as_of=as_of)
        data = {
            "status": result.status,
            "term": result.term,
            "definitions": tuple(self._as_dict(definition) for definition in result.definitions),
        }
        return ToolExecution(
            data=data,
            source=("customer360.semantic.metric_registry",),
            definition=tuple(definition.version for definition in result.definitions),
            warnings=result.warnings,
            query_metadata={"operation": "semantic.lookup", "context": result.context},
            evidence_references=tuple(f"metric-definition:{definition.metric_id}" for definition in result.definitions),
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())

    @staticmethod
    def _is_stale(definition: MetricDefinition, as_of: datetime) -> bool:
        effective = datetime.fromisoformat(definition.effective_from.replace("Z", "+00:00"))
        return (as_of.astimezone(timezone.utc) - effective).total_seconds() > definition.freshness_sla_hours * 3600

    @staticmethod
    def _as_dict(definition: MetricDefinition) -> dict[str, Any]:
        return {
            "metric_id": definition.metric_id,
            "name": definition.name,
            "definition": definition.definition,
            "formula": definition.formula,
            "numerator": definition.numerator,
            "denominator": definition.denominator,
            "sources": definition.source,
            "owner": definition.owner,
            "grain": definition.grain,
            "exclusions": definition.exclusions,
            "null_handling": definition.null_handling,
            "currency": definition.currency,
            "time_zone": definition.time_zone,
            "version": definition.version,
            "effective_from": definition.effective_from,
            "freshness_sla_hours": definition.freshness_sla_hours,
            "classification": definition.classification,
        }


def _metric(metric_id: str, name: str, definition: str, formula: str, numerator: str | None, denominator: str | None, source: tuple[str, ...], owner: str, grain: str, aliases: tuple[str, ...], *, currency: str | None = None, exclusions: tuple[str, ...] = (), freshness_sla_hours: int = 24) -> MetricDefinition:
    return MetricDefinition(metric_id, name, definition, formula, numerator, denominator, source, owner, grain, exclusions, currency, "UTC", "v1", "2026-09-20T00:00:00Z", freshness_sla_hours, aliases)


def default_metric_definitions() -> tuple[MetricDefinition, ...]:
    return (
        _metric("customer360.revenue", "Revenue", "Recognized order revenue after refunds.", "sum(order.total - refunds)", "order net total", None, ("shopping.orders",), "finance", "order", ("sales", "net sales"), currency="USD"),
        _metric("customer360.retention", "Customer Retention", "Customers active in both the comparison and measurement periods.", "retained customers / eligible customers", "retained customers", "eligible customers", ("crm.customers", "shopping.orders"), "customer", "customer-period", ("retention rate",)),
        _metric("customer360.conversion", "Conversion Rate", "Visits that produce an order divided by eligible visits.", "converted visits / eligible visits", "converted visits", "eligible visits", ("site.visits", "shopping.orders"), "digital", "site-period", ("conversion rate",)),
        _metric("customer360.cart-abandonment", "Cart Abandonment Rate", "Carts not converted to an order divided by eligible carts.", "abandoned carts / eligible carts", "abandoned carts", "eligible carts", ("shopping.carts", "shopping.orders"), "digital", "site-period", ("cart abandonment",)),
        _metric("customer360.customer-frequency", "Customer Purchase Frequency", "Completed orders per active customer in the measurement period.", "completed orders / active customers", "completed orders", "active customers", ("shopping.orders", "crm.customers"), "customer", "customer-period", ("purchase frequency", "frequency")),
        _metric("customer360.promotion-roi", "Promotion ROI", "Incremental gross profit attributable to a promotion divided by promotion cost.", "incremental gross profit / promotion cost", "incremental gross profit", "promotion cost", ("marketing.campaigns", "shopping.orders"), "marketing", "promotion-period", ("promotion return", "promo roi")),
        _metric("customer360.gross-margin", "Gross Margin", "Revenue less cost of goods sold, divided by revenue.", "(revenue - cogs) / revenue", "revenue - cogs", "revenue", ("shopping.orders", "product.costs"), "finance", "order-period", ("margin",), currency="USD"),
        _metric("customer360.product-performance", "Product Performance", "Units sold and net revenue for a product in a measurement period.", "units sold, net revenue", "units sold", None, ("shopping.order_items", "product.products"), "product", "product-period", ("product sales",)),
        _metric("customer360.basket-size", "Average Basket Size", "Average number of items per completed order.", "items / completed orders", "items", "completed orders", ("shopping.order_items", "shopping.orders"), "finance", "order-period", ("basket size", "average basket")),
        _metric("customer360.site-visit-volume", "Site Visit Volume", "Count of eligible site visits in a measurement period.", "count(eligible visits)", "eligible visits", None, ("site.visits",), "digital", "site-period", ("visits", "traffic")),
    )