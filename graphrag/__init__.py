"""GraphRAG sobre Neo4j para a ontologia de neurodivergência.

Sem banco vetorial externo: usa o índice vetorial NATIVO do Neo4j (HNSW) +
fulltext (Lucene) + travessia de grafo, tudo no mesmo banco.
"""

from graphrag.retriever import (
    GraphRAGRetriever,
    RetrievalResult,
    RetrievedChunk,
    RetrievedConcept,
)

__all__ = [
    "GraphRAGRetriever",
    "RetrievalResult",
    "RetrievedChunk",
    "RetrievedConcept",
]
