"""Dependency-free document retrieval and graph-augmented context."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .graph import GraphStore
from .tools import ToolExecution

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in _TOKEN.findall(value))


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


@dataclass(frozen=True)
class Document:
    document_id: str
    title: str
    content: str
    source: str
    version: str = "1"
    document_type: str = "document"
    author: str = ""
    updated_at: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    authorized_principals: tuple[str, ...] = ("*",)
    superseded: bool = False


@dataclass(frozen=True)
class DocumentChunk:
    document_id: str
    chunk_id: str
    text: str
    start_token: int
    end_token: int
    embedding: Counter[str]


class DocumentStore:
    """In-memory document port with deterministic term-vector retrieval."""

    def __init__(self, chunk_size: int = 120, overlap: int = 20) -> None:
        if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("Chunk overlap must be non-negative and smaller than chunk size")
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._documents: dict[str, Document] = {}
        self._chunks: dict[str, tuple[DocumentChunk, ...]] = {}

    def ingest(self, document: Document) -> tuple[DocumentChunk, ...]:
        if not document.document_id or not document.title or not document.content.strip():
            raise ValueError("Documents require an ID, title, and non-empty content")
        words = document.content.split()
        step = self.chunk_size - self.overlap
        chunks: list[DocumentChunk] = []
        for start in range(0, len(words), step):
            end = min(start + self.chunk_size, len(words))
            text = " ".join(words[start:end])
            chunk_id = f"{document.document_id}:chunk-{len(chunks) + 1}"
            chunks.append(DocumentChunk(document.document_id, chunk_id, text, start, end, Counter(_tokens(text))))
            if end == len(words):
                break
        self._documents[document.document_id] = document
        self._chunks[document.document_id] = tuple(chunks)
        return tuple(chunks)

    def document_lookup(self, document_id: str, principal_id: str = "system") -> ToolExecution:
        document = self._authorized_document(document_id, principal_id)
        return self._execution(
            data=self._document_data(document),
            operation="document_lookup",
            document=document,
            evidence=(f"document:{document.document_id}:v{document.version}",),
        )

    def search(
        self,
        query: str,
        principal_id: str = "system",
        max_results: int = 10,
        document_type: str | None = None,
        entity_ids: Iterable[str] = (),
    ) -> ToolExecution:
        if not query.strip():
            raise ValueError("RAG query must not be empty")
        if not 1 <= max_results <= 100:
            raise ValueError("RAG result limit must be between 1 and 100")
        query_vector = Counter(_tokens(query))
        entity_set = set(entity_ids)
        scored: list[tuple[float, Document, DocumentChunk]] = []
        for document in self._documents.values():
            if not self._is_authorized(document, principal_id) or (document_type and document.document_type != document_type):
                continue
            for chunk in self._chunks[document.document_id]:
                score = _cosine(query_vector, chunk.embedding)
                metadata_text = repr(dict(document.metadata))
                if entity_set & set(_tokens(metadata_text)):
                    score += 0.1
                if score > 0:
                    scored.append((score, document, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].document_id, item[2].chunk_id))
        passages = [self._passage(score, document, chunk) for score, document, chunk in scored[:max_results]]
        selected_documents = [document for _, document, _ in scored[:max_results]]
        warnings = ()
        if not passages:
            warnings = ("No matching authorized document passages",)
        elif any(document.superseded for document in selected_documents):
            warnings = ("Document is superseded",)
        return ToolExecution(
            data={"passages": passages, "retrieval_rationale": "Deterministic term-vector similarity; score is not a truth value."},
            source=tuple(sorted({document.source for _, document, _ in scored[:max_results]})),
            filters={"query": query, "document_type": document_type, "entity_ids": tuple(entity_ids), "limit": max_results},
            freshness={"retrieved_at": datetime.now(timezone.utc).isoformat()},
            query_metadata={"operation": "search", "embedding": "normalized-term-frequency"},
            evidence_references=tuple(f"document-chunk:{chunk.chunk_id}" for _, _, chunk in scored[:max_results]),
            warnings=warnings,
        )

    def policy_retrieve(self, policy: str, principal_id: str = "system", max_results: int = 10) -> ToolExecution:
        return self.search(policy, principal_id, max_results, document_type="policy")

    def _authorized_document(self, document_id: str, principal_id: str) -> Document:
        try:
            document = self._documents[document_id]
        except KeyError as error:
            raise ValueError(f"Unknown document ID: {document_id}") from error
        if not self._is_authorized(document, principal_id):
            raise PermissionError(f"{principal_id} is not authorized for document {document_id}")
        return document

    @staticmethod
    def _is_authorized(document: Document, principal_id: str) -> bool:
        return "*" in document.authorized_principals or principal_id in document.authorized_principals

    def _execution(self, data: Any, operation: str, document: Document, evidence: tuple[str, ...]) -> ToolExecution:
        return ToolExecution(
            data=data,
            source=(document.source,),
            freshness={"updated_at": document.updated_at, "superseded": document.superseded},
            query_metadata={"operation": operation, "document_id": document.document_id, "version": document.version},
            evidence_references=evidence,
            warnings=("Document is superseded",) if document.superseded else (),
        )

    @staticmethod
    def _document_data(document: Document) -> dict[str, Any]:
        return {
            "document_id": document.document_id,
            "title": document.title,
            "content": document.content,
            "source": document.source,
            "version": document.version,
            "document_type": document.document_type,
            "author": document.author,
            "updated_at": document.updated_at,
            "metadata": dict(document.metadata),
            "superseded": document.superseded,
        }

    @staticmethod
    def _passage(score: float, document: Document, chunk: DocumentChunk) -> dict[str, Any]:
        return {
            "document_id": document.document_id,
            "chunk_id": chunk.chunk_id,
            "title": document.title,
            "version": document.version,
            "author": document.author,
            "updated_at": document.updated_at,
            "source": document.source,
            "document_type": document.document_type,
            "passage": chunk.text,
            "location": {"start_token": chunk.start_token, "end_token": chunk.end_token},
            "retrieval_score": round(score, 6),
            "superseded": document.superseded,
        }


class GraphRAGRetriever:
    """Combine authorized document passages with bounded graph context."""

    def __init__(self, documents: DocumentStore, graph: GraphStore) -> None:
        self.documents = documents
        self.graph = graph

    def search(
        self,
        query: str,
        principal_id: str = "system",
        entity_type: str | None = None,
        entity_id: str | None = None,
        max_results: int = 10,
    ) -> ToolExecution:
        document_result = self.documents.search(query, principal_id, max_results, entity_ids=(entity_id,) if entity_id else ())
        graph_context: dict[str, Any] | None = None
        graph_evidence: tuple[str, ...] = ()
        if entity_type and entity_id:
            graph_result = self.graph.neighbors(entity_type, entity_id, max_results=max_results)
            graph_context = graph_result.data
            graph_evidence = graph_result.evidence_references
        data = dict(document_result.data)
        data["graph_context"] = graph_context
        return ToolExecution(
            data=data,
            source=document_result.source + (("customer360.knowledge_graph",) if graph_context else ()),
            filters={**document_result.filters, "entity_type": entity_type, "entity_id": entity_id},
            freshness={**document_result.freshness, "graph_version": self.graph.version if graph_context else None},
            query_metadata={"operation": "hybrid_search", "document_query": document_result.query_metadata},
            evidence_references=document_result.evidence_references + graph_evidence,
            warnings=document_result.warnings,
        )


def rag_tool_handlers(retriever: GraphRAGRetriever) -> dict[str, Any]:
    return {
        "rag.search": lambda inputs: retriever.search(
            inputs["query"], inputs.get("principal_id", "system"), inputs.get("entity_type"), inputs.get("entity_id"), inputs.get("max_results", 10)
        ),
        "rag.document_lookup": lambda inputs: retriever.documents.document_lookup(inputs["document_id"], inputs.get("principal_id", "system")),
        "rag.policy_retrieve": lambda inputs: retriever.documents.policy_retrieve(inputs["policy"], inputs.get("principal_id", "system"), inputs.get("max_results", 10)),
    }