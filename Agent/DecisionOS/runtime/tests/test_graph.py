import pytest

from decision_os.graph import GraphStore, graph_tool_handlers


@pytest.fixture
def graph():
    store = GraphStore()
    store.sync(
        [
            {"entity_type": "customer", "entity_id": "c-1", "attributes": {"name": "Ada", "segment": "gold"}, "source": "crm:customers"},
            {"entity_type": "segment", "entity_id": "gold", "attributes": {"name": "Gold"}, "source": "crm:segments"},
            {"entity_type": "order", "entity_id": "o-1", "source": "shopping:orders"},
            {"entity_type": "cart", "entity_id": "cart-1", "source": "shopping:carts"},
            {"entity_type": "item", "entity_id": "item-1", "source": "shopping:order-items"},
            {"entity_type": "product", "entity_id": "p-1", "attributes": {"name": "Trail shoe"}, "source": "product:products"},
            {"entity_type": "category", "entity_id": "footwear", "source": "product:categories"},
        ],
        [
            {"from_type": "customer", "from_id": "c-1", "relationship_type": "customer_segment", "to_type": "segment", "to_id": "gold", "source": "crm:customer-segments"},
            {"from_type": "customer", "from_id": "c-1", "relationship_type": "customer_order", "to_type": "order", "to_id": "o-1", "source": "shopping:orders"},
            {"from_type": "order", "from_id": "o-1", "relationship_type": "order_cart", "to_type": "cart", "to_id": "cart-1", "source": "shopping:carts"},
            {"from_type": "cart", "from_id": "cart-1", "relationship_type": "cart_item", "to_type": "item", "to_id": "item-1", "source": "shopping:cart-items"},
            {"from_type": "item", "from_id": "item-1", "relationship_type": "item_product", "to_type": "product", "to_id": "p-1", "source": "shopping:items"},
            {"from_type": "product", "from_id": "p-1", "relationship_type": "product_category", "to_type": "category", "to_id": "footwear", "source": "product:categories"},
        ],
    )
    return store


def test_graph_answers_multi_hop_relationship_question(graph):
    result = graph.paths("c-1", "p-1")

    assert result.data["found"] is True
    assert [edge["relationship_type"] for edge in result.data["path"]] == [
        "customer_order",
        "order_cart",
        "cart_item",
        "item_product",
    ]
    assert result.source == ("customer360.knowledge_graph",)
    assert result.evidence_references[0].startswith("graph-edge:")
    assert result.freshness["graph_version"] > 0

    reverse_result = graph.paths("gold", "p-1")
    assert reverse_result.data["found"] is True
    assert reverse_result.data["path"][0]["relationship_type"] == "customer_segment"


def test_graph_neighbors_and_search_return_entity_relationship_context(graph):
    neighbors = graph.neighbors("customer", "c-1", ("customer_segment",))
    assert neighbors.data["neighbors"][0]["entity_id"] == "gold"
    assert len(neighbors.data["edges"]) == 1

    search = graph.search("trail shoe")
    assert [entity["entity_id"] for entity in search.data["entities"]] == ["p-1"]


def test_graph_rejects_unapproved_relationships_and_ambiguous_paths(graph):
    with pytest.raises(ValueError, match="Unsupported relationship type"):
        graph.add_edge("customer", "c-1", "invented_edge", "product", "p-1")

    graph.upsert_node("site", "p-1")
    with pytest.raises(ValueError, match="Ambiguous graph entity ID"):
        graph.paths("c-1", "p-1")


def test_graph_handlers_are_catalog_ready(graph):
    handlers = graph_tool_handlers(graph)
    assert set(handlers) == {
        "graph.search",
        "graph.neighbors",
        "graph.paths",
        "graph.relationship_summary",
    }
    assert handlers["graph.relationship_summary"]({"entity_type": "customer", "entity_id": "c-1"}).data["relationship_counts"] == {
        "customer_order": 1,
        "customer_segment": 1,
    }


def test_graph_can_export_a_deterministic_mermaid_diagram(graph):
    diagram = graph.to_mermaid()

    assert diagram.startswith("```mermaid\nflowchart LR\n")
    assert 'customer: c-1' in diagram
    assert "customer_order" in diagram
    assert diagram.index("customer: c-1") < diagram.index("product: p-1")
    assert graph.to_mermaid() == diagram
