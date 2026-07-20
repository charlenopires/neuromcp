"""Testes offline do GraphRAG: montagem de contexto e corpus (sem Neo4j)."""

from crawler.classifier import ConceptClassifier
from crawler.ontology import OntologyManager
from crawler.sample_corpus import load_sample_articles
from graphrag.retriever import (
    ComorbidadeRef,
    GraphRAGRetriever,
    RetrievalResult,
    RetrievedChunk,
    RetrievedConcept,
)


def test_build_context_formata_conceitos_e_chunks():
    r = GraphRAGRetriever(repo=None, ontology_mgr=OntologyManager())
    resultado = RetrievalResult(
        pergunta="O que é TDAH?",
        conceitos=[
            RetrievedConcept(
                id="nd:tdah", rotuloPt="TDAH", definicao="Transtorno do neurodesenvolvimento.",
                dominios=["Atenção", "Funções Executivas"],
                comorbidades=[ComorbidadeRef(id="nd:tea", rotulo="Autismo", forca="alta")],
                pontosFortes=["criatividade"],
            )
        ],
        chunks=[RetrievedChunk(texto="O TDAH afeta a atenção.", score=0.9, artigoTitulo="Artigo X")],
    )
    ctx = r.build_context(resultado)
    assert "TDAH" in ctx
    assert "Comorbidades frequentes" in ctx
    assert "Artigo X" in ctx
    assert "Rotule conteúdo, não pessoas" in ctx


def test_corpus_carrega_e_classifica():
    arts = load_sample_articles()
    assert len(arts) >= 10
    clf = ConceptClassifier(OntologyManager())
    # cada documento do corpus deve casar com ao menos um conceito
    for a in arts:
        a = clf.classify_article(a)
        assert a.matchesOntologia, f"corpus sem match: {a.url}"


def test_anchor_concepts_sem_db():
    r = GraphRAGRetriever(repo=None, ontology_mgr=OntologyManager())
    ancoras = r.anchor_concepts("dislexia e discalculia na escola")
    assert "nd:dislexia" in ancoras
    assert "nd:discalculia" in ancoras
