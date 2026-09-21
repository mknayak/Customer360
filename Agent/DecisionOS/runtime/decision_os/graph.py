"""Dependency-free knowledge graph primitives for governed relationship queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .adapters import validate_identifier
from .tools import ToolExecution

ENTITY_TYPES = frozenset(
    {
        "customer",
        "segment",
        "product",
        "category",
        "promotion",
        "campaign",
        "site",
        "visit",
        "order",
        "cart",
        "feedback",
        "region",
        "item",
    }
)

RELATIONSHIP_TYPES = frozenset(
    {
        "customer_segment",
        "customer_order",
        "customer_visit",
        "customer_feedback",
        "product_category",
        "product_promotion",
        "site_visit",
        "campaign_audience",
        "campaign_interaction",
        "order_cart",
        "cart_item",
        "item_product",
    }
)


@dataclass(frozen=True)
class GraphNode:
    entity_type: str
    entity_id: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""


@dataclass(frozen=True)
class GraphEdge:
    from_key: tuple[str, str]
    to_key: tuple[str, str]
    relationship_type: str
    source: str = ""


class GraphStore:
    """Small replaceable graph port used until a persistent graph adapter exists."""

    def __init__(self) -> None:
        self._nodes: dict[tuple[str, str], GraphNode] = {}
        self._edges: set[GraphEdge] = set()
        self._version = 0
        self._synced_at: str | None = None

    @property
    def version(self) -> int:
        return self._version

    def upsert_node(
        self,
        entity_type: str,
        entity_id: str,
        attributes: Mapping[str, Any] | None = None,
        source: str = "",
    ) -> GraphNode:
        key = self._validate_key(entity_type, entity_id)
        node = GraphNode(entity_type, entity_id, dict(attributes or {}), source)
        if self._nodes.get(key) != node:
            self._nodes[key] = node
            self._version += 1
        return node

    def add_edge(
        self,
        from_type: str,
        from_id: str,
        relationship_type: str,
        to_type: str,
        to_id: str,
        source: str = "",
    ) -> GraphEdge:
        from_key = self._validate_key(from_type, from_id)
        to_key = self._validate_key(to_type, to_id)
        if relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unsupported relationship type: {relationship_type}")
        edge = GraphEdge(from_key, to_key, relationship_type, source)
        if edge not in self._edges:
            self._edges.add(edge)
            self._version += 1
        return edge

    def sync(
        self,
        entities: Iterable[Mapping[str, Any]],
        relationships: Iterable[Mapping[str, Any]] = (),
    ) -> int:
        """Refresh graph records from service-shaped entity and relationship rows."""
        for entity in entities:
            self.upsert_node(
                str(entity["entity_type"]),
                str(entity["entity_id"]),
                entity.get("attributes", {}),
                str(entity.get("source", "")),
            )
        for relationship in relationships:
            self.add_edge(
                str(relationship["from_type"]),
                str(relationship["from_id"]),
                str(relationship["relationship_type"]),
                str(relationship["to_type"]),
                str(relationship["to_id"]),
                str(relationship.get("source", "")),
            )
        self._synced_at = datetime.now(timezone.utc).isoformat()
        return self._version

    def search(self, query: str, max_results: int = 100) -> ToolExecution:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Graph search query must not be empty")
        if not 1 <= max_results <= 1000:
            raise ValueError("Graph result limit must be between 1 and 1000")
        terms = query.casefold().split()
        matches = [
            node for node in self._nodes.values()
            if all(term in self._node_text(node) for term in terms)
        ][:max_results]
        return self._execution(
            data={"entities": [self._node_data(node) for node in matches], "edges": []},
            operation="search",
            filters={"query": query, "limit": max_results},
            evidence=tuple(self._node_ref(node) for node in matches),
        )

    def neighbors(
        self,
        entity_type: str,
        entity_id: str,
        relationship_types: Iterable[str] = (),
        max_results: int = 100,
    ) -> ToolExecution:
        key = self._validate_key(entity_type, entity_id)
        allowed = self._validate_relationship_filter(relationship_types)
        if not 1 <= max_results <= 1000:
            raise ValueError("Graph result limit must be between 1 and 1000")
        edges = [
            edge for edge in self._edges
            if key in (edge.from_key, edge.to_key) and (not allowed or edge.relationship_type in allowed)
        ][:max_results]
        neighbor_keys = [edge.to_key if edge.from_key == key else edge.from_key for edge in edges]
        nodes = [self._nodes[neighbor_key] for neighbor_key in neighbor_keys if neighbor_key in self._nodes]
        return self._execution(
            data={"entity": self._node_data(self._nodes[key]), "neighbors": [self._node_data(node) for node in nodes], "edges": [self._edge_data(edge) for edge in edges]},
            operation="neighbors",
            filters={"entity_type": entity_type, "entity_id": entity_id},
            evidence=(self._node_ref(self._nodes[key]),) + tuple(self._edge_ref(edge) for edge in edges),
        )

    def paths(self, from_id: str, to_id: str, max_depth: int = 6) -> ToolExecution:
        start = self._resolve_id(from_id)
        target = self._resolve_id(to_id)
        if not 1 <= max_depth <= 8:
            raise ValueError("Graph path depth must be between 1 and 8")
        queue: list[tuple[tuple[str, str], tuple[GraphEdge, ...]]] = [(start, ())]
        visited = {start}
        found: tuple[GraphEdge, ...] | None = None
        while queue:
            current, path = queue.pop(0)
            if current == target:
                found = path
                break
            if len(path) >= max_depth:
                continue
            for edge, next_key in self._incident(current):
                if next_key not in visited:
                    visited.add(next_key)
                    queue.append((next_key, path + (edge,)))
        path_data = [self._edge_data(edge) for edge in (found or ())]
        return self._execution(
            data={"from_id": from_id, "to_id": to_id, "found": found is not None, "path": path_data},
            operation="paths",
            filters={"from_id": from_id, "to_id": to_id, "max_depth": max_depth},
            warnings=() if found else ("No approved relationship path found",),
            evidence=tuple(self._edge_ref(edge) for edge in (found or ())),
        )

    def relationship_summary(self, entity_type: str, entity_id: str) -> ToolExecution:
        key = self._validate_key(entity_type, entity_id)
        edges = [edge for edge in self._edges if key in (edge.from_key, edge.to_key)]
        counts: dict[str, int] = {}
        for edge in edges:
            counts[edge.relationship_type] = counts.get(edge.relationship_type, 0) + 1
        return self._execution(
            data={"entity": self._node_data(self._nodes[key]), "relationship_counts": counts},
            operation="relationship_summary",
            filters={"entity_type": entity_type, "entity_id": entity_id},
            evidence=(self._node_ref(self._nodes[key]),) + tuple(self._edge_ref(edge) for edge in edges),
        )

    def to_mermaid(self, max_nodes: int = 1000) -> str:
        """Export a bounded, deterministic graph diagram for Markdown viewers."""
        if not 1 <= max_nodes <= 5000:
            raise ValueError("Graph visualization limit must be between 1 and 5000")

        nodes = sorted(self._nodes.values(), key=lambda node: (node.entity_type, node.entity_id))[:max_nodes]
        node_keys = {(node.entity_type, node.entity_id) for node in nodes}
        ordered_keys = [(node.entity_type, node.entity_id) for node in nodes]
        edges = sorted(
            (
                edge for edge in self._edges
                if edge.from_key in node_keys and edge.to_key in node_keys
            ),
            key=lambda edge: (edge.from_key, edge.relationship_type, edge.to_key),
        )
        node_ids = {key: f"n{index}" for index, key in enumerate(ordered_keys)}
        lines = ["```mermaid", "flowchart LR"]
        for node in nodes:
            key = (node.entity_type, node.entity_id)
            label = self._mermaid_text(f"{node.entity_type}: {node.entity_id}")
            lines.append(f'    {node_ids[key]}["{label}"]')
        for edge in edges:
            relationship = self._mermaid_text(edge.relationship_type)
            lines.append(f"    {node_ids[edge.from_key]} -->|{relationship}| {node_ids[edge.to_key]}")
        lines.append("```")
        return "\n".join(lines)

    def _execution(self, data: Any, operation: str, filters: Mapping[str, Any], evidence: tuple[str, ...], warnings: tuple[str, ...] = ()) -> ToolExecution:
        return ToolExecution(
            data=data,
            source=("customer360.knowledge_graph",),
            filters=filters,
            freshness={"synced_at": self._synced_at, "graph_version": self._version},
            query_metadata={"operation": operation, "graph_version": self._version},
            evidence_references=evidence,
            warnings=warnings,
        )

    def _validate_key(self, entity_type: str, entity_id: str) -> tuple[str, str]:
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        return entity_type, validate_identifier(entity_id, f"{entity_type} ID")

    def _resolve_id(self, entity_id: str) -> tuple[str, str]:
        validate_identifier(entity_id)
        matches = [key for key in self._nodes if key[1] == entity_id]
        if not matches:
            raise ValueError(f"Unknown graph entity ID: {entity_id}")
        if len(matches) > 1:
            raise ValueError(f"Ambiguous graph entity ID: {entity_id}")
        return matches[0]

    @staticmethod
    def _validate_relationship_filter(relationship_types: Iterable[str]) -> frozenset[str]:
        selected = frozenset(relationship_types)
        unknown = selected - RELATIONSHIP_TYPES
        if unknown:
            raise ValueError(f"Unsupported relationship type: {', '.join(sorted(unknown))}")
        return selected

    def _incident(self, key: tuple[str, str]) -> list[tuple[GraphEdge, tuple[str, str]]]:
        incident = [
            (edge, edge.to_key if edge.from_key == key else edge.from_key)
            for edge in self._edges
            if key in (edge.from_key, edge.to_key)
        ]
        return sorted(incident, key=lambda item: (item[0].relationship_type, item[1]))

    @staticmethod
    def _node_text(node: GraphNode) -> str:
        return " ".join((node.entity_type, node.entity_id, repr(dict(node.attributes)))).casefold()

    @staticmethod
    def _node_data(node: GraphNode) -> dict[str, Any]:
        return {"entity_type": node.entity_type, "entity_id": node.entity_id, "attributes": dict(node.attributes), "source": node.source}

    @staticmethod
    def _edge_data(edge: GraphEdge) -> dict[str, Any]:
        return {"from": {"entity_type": edge.from_key[0], "entity_id": edge.from_key[1]}, "to": {"entity_type": edge.to_key[0], "entity_id": edge.to_key[1]}, "relationship_type": edge.relationship_type, "source": edge.source}

    @staticmethod
    def _node_ref(node: GraphNode) -> str:
        return f"graph-node:{node.entity_type}:{node.entity_id}"

    @staticmethod
    def _edge_ref(edge: GraphEdge) -> str:
        return f"graph-edge:{edge.from_key[0]}:{edge.from_key[1]}:{edge.relationship_type}:{edge.to_key[0]}:{edge.to_key[1]}"

    @staticmethod
    def _mermaid_text(value: str) -> str:
        return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def graph_tool_handlers(graph: GraphStore) -> dict[str, Any]:
    """Return catalog-compatible handlers for the graph capability."""
    return {
        "graph.search": lambda inputs: graph.search(inputs["query"], inputs.get("max_results", 100)),
        "graph.neighbors": lambda inputs: graph.neighbors(inputs["entity_type"], inputs["entity_id"], inputs.get("relationship_types", ()), inputs.get("max_results", 100)),
        "graph.paths": lambda inputs: graph.paths(inputs["from_id"], inputs["to_id"], inputs.get("max_depth", 6)),
        "graph.relationship_summary": lambda inputs: graph.relationship_summary(inputs["entity_type"], inputs["entity_id"]),
    }
