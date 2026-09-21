"""Small SQLite adapters for semantic, graph, decision, and audit durability."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .graph import GraphEdge, GraphNode, GraphStore
from .semantic import MetricDefinition, SemanticRegistry


class SQLiteSemanticRegistry(SemanticRegistry):
    """Persist versioned metric definitions while retaining registry behavior."""

    def __init__(self, database_path: str | Path, definitions: tuple[MetricDefinition, ...] | None = None) -> None:
        super().__init__(definitions)
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS metric_definitions (metric_id TEXT PRIMARY KEY, definition TEXT NOT NULL, version TEXT NOT NULL, effective_from TEXT NOT NULL, updated_at TEXT NOT NULL)")
        self.persist()

    def persist(self) -> None:
        with self.connection:
            for definition in self.definitions():
                self.connection.execute(
                    "INSERT OR REPLACE INTO metric_definitions VALUES (?, ?, ?, ?, ?)",
                    (definition.metric_id, json.dumps(_metric_dict(definition), sort_keys=True), definition.version, definition.effective_from, datetime.now(timezone.utc).isoformat()),
                )

    def close(self) -> None:
        self.connection.close()


class SQLiteGraphStore(GraphStore):
    """Durable graph adapter using the same bounded GraphStore query port."""

    def __init__(self, database_path: str | Path) -> None:
        super().__init__()
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS graph_nodes (entity_type TEXT, entity_id TEXT, attributes TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(entity_type, entity_id))")
        self.connection.execute("CREATE TABLE IF NOT EXISTS graph_edges (from_type TEXT, from_id TEXT, relationship_type TEXT, to_type TEXT, to_id TEXT, source TEXT NOT NULL, PRIMARY KEY(from_type, from_id, relationship_type, to_type, to_id))")
        self._load()

    def sync(self, entities: Iterable[Mapping[str, Any]], relationships: Iterable[Mapping[str, Any]] = ()) -> int:
        version = super().sync(entities, relationships)
        with self.connection:
            self.connection.execute("DELETE FROM graph_nodes")
            self.connection.execute("DELETE FROM graph_edges")
            self.connection.executemany("INSERT INTO graph_nodes VALUES (?, ?, ?, ?)", [(node.entity_type, node.entity_id, json.dumps(dict(node.attributes), sort_keys=True), node.source) for node in self._nodes.values()])
            self.connection.executemany("INSERT INTO graph_edges VALUES (?, ?, ?, ?, ?, ?)", [(edge.from_key[0], edge.from_key[1], edge.relationship_type, edge.to_key[0], edge.to_key[1], edge.source) for edge in self._edges])
        return version

    def _load(self) -> None:
        for entity_type, entity_id, attributes, source in self.connection.execute("SELECT entity_type, entity_id, attributes, source FROM graph_nodes"):
            super().upsert_node(entity_type, entity_id, json.loads(attributes), source)
        for from_type, from_id, relationship, to_type, to_id, source in self.connection.execute("SELECT from_type, from_id, relationship_type, to_type, to_id, source FROM graph_edges"):
            super().add_edge(from_type, from_id, relationship, to_type, to_id, source)

    def close(self) -> None:
        self.connection.close()


def _metric_dict(definition: MetricDefinition) -> dict[str, Any]:
    value = asdict(definition)
    value["source"] = list(definition.source)
    value["aliases"] = list(definition.aliases)
    value["exclusions"] = list(definition.exclusions)
    return value
