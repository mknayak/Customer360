import pytest

from decision_os.graph import GraphStore
from decision_os.rag import Document, DocumentStore, GraphRAGRetriever, rag_tool_handlers


def test_document_store_chunks_searches_and_cites_authorized_passages():
    store = DocumentStore(chunk_size=5, overlap=1)
    chunks = store.ingest(
        Document(
            "brief-1",
            "Mobile campaign brief",
            "Mobile visitors received a free shipping offer during the spring campaign.",
            "marketing:briefs",
            version="2",
            document_type="brief",
            author="marketing",
            updated_at="2026-09-18T00:00:00Z",
            authorized_principals=("executive",),
            metadata={"campaign_id": "camp-1"},
        )
    )

    result = store.search("free shipping mobile campaign", "executive")

    assert len(chunks) > 1
    assert result.data["passages"][0]["document_id"] == "brief-1"
    assert result.data["passages"][0]["version"] == "2"
    assert result.data["passages"][0]["location"]["start_token"] == 0
    assert result.evidence_references[0].startswith("document-chunk:brief-1")
    assert result.query_metadata["embedding"] == "normalized-term-frequency"

    with pytest.raises(PermissionError, match="not authorized"):
        store.document_lookup("brief-1", "analyst")


def test_policy_retrieval_filters_documents_and_marks_superseded_content():
    store = DocumentStore()
    store.ingest(Document("policy-1", "Returns policy", "Returns are accepted within thirty days.", "legal:policy", document_type="policy", superseded=True))
    store.ingest(Document("brief-1", "Returns brief", "Returns campaign messaging for customers.", "marketing:briefs", document_type="brief"))

    result = store.policy_retrieve("returns", max_results=10)

    assert [passage["document_id"] for passage in result.data["passages"]] == ["policy-1"]
    assert result.data["passages"][0]["superseded"] is True
    assert result.warnings == ("Document is superseded",)


def test_graph_rag_returns_document_and_bounded_graph_evidence():
    documents = DocumentStore()
    documents.ingest(Document("launch-1", "Product launch", "Trail shoe launch notes for gold customers.", "product:briefs", metadata={"product_id": "p-1"}))
    graph = GraphStore()
    graph.sync(
        [
            {"entity_type": "product", "entity_id": "p-1", "attributes": {"name": "Trail shoe"}},
            {"entity_type": "category", "entity_id": "footwear"},
        ],
        [{"from_type": "product", "from_id": "p-1", "relationship_type": "product_category", "to_type": "category", "to_id": "footwear"}],
    )

    result = GraphRAGRetriever(documents, graph).search("trail shoe launch", entity_type="product", entity_id="p-1")

    assert result.data["passages"][0]["document_id"] == "launch-1"
    assert result.data["graph_context"]["neighbors"][0]["entity_id"] == "footwear"
    assert "customer360.knowledge_graph" in result.source
    assert any(reference.startswith("graph-edge:") for reference in result.evidence_references)


def test_rag_handlers_are_catalog_ready():
    store = DocumentStore()
    store.ingest(Document("policy-1", "Returns", "Returns are accepted.", "legal:policy", document_type="policy"))
    handlers = rag_tool_handlers(GraphRAGRetriever(store, GraphStore()))

    assert set(handlers) == {"rag.search", "rag.document_lookup", "rag.policy_retrieve"}
    assert handlers["rag.document_lookup"]({"document_id": "policy-1"}).data["title"] == "Returns"