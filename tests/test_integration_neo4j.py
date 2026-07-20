"""
Testes de INTEGRAÇÃO com Neo4j real. Auto-pulam se o banco não estiver acessível.
Rodam o ciclo completo: semear ontologia -> ingerir corpus -> GraphRAG.

Pré-requisito: `docker compose up -d` (Neo4j em bolt://localhost:7687).
"""

import pytest

from crawler.database import Neo4jRepository
from crawler.embeddings import get_embedding_provider
from crawler.pipeline import NeuroCrawlerPipeline
from graphrag.retriever import GraphRAGRetriever


@pytest.fixture(scope="module")
def repo():
    r = Neo4jRepository()
    try:
        r.connect()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Neo4j indisponível ({e}). Rode `docker compose up -d`.")
    yield r
    r.close()


def test_ciclo_completo(repo):
    pipeline = NeuroCrawlerPipeline(use_embeddings=True)
    summary = pipeline.ingest_samples(seed_first=True)
    assert summary.totalSalvosNeo4j >= 8

    # o grafo deve ter conceitos, artigos e chunks
    nos = {r["label"]: r["total"] for r in repo.run_read(
        "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS total")}
    assert nos.get("Conceito", 0) >= 30
    assert nos.get("Artigo", 0) >= 8
    assert nos.get("Chunk", 0) >= 8

    # GraphRAG deve recuperar TDAH e trazer evidências textuais
    retriever = GraphRAGRetriever(repo=repo, embedder=get_embedding_provider())
    resultado = retriever.retrieve("Quais as comorbidades do TDAH?")
    ids = {c.id for c in resultado.conceitos}
    assert "nd:tdah" in ids
    assert resultado.chunks, "esperava evidências (chunks) do índice vetorial"


def test_indices_criados(repo):
    idx = repo.run_read("SHOW INDEXES YIELD name, type RETURN name, type")
    nomes = {i["name"] for i in idx}
    assert "conceito_embedding" in nomes
    assert "chunk_embedding" in nomes
    assert "conceito_fulltext" in nomes
