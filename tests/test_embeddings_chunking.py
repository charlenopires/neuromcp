"""Testes de embeddings (fallback determinístico) e chunking."""

import math

from crawler.chunking import split_into_chunks
from crawler.embeddings import HashingProvider, get_embedding_provider


def test_hashing_determinismo_e_norma():
    p = HashingProvider(dimension=384)
    a = p.embed_text("TDAH e autismo")
    b = p.embed_text("TDAH e autismo")
    assert a == b  # determinístico
    assert p.dimension == 384
    assert abs(math.sqrt(sum(x * x for x in a)) - 1.0) < 1e-6  # L2-normalizado


def test_hashing_similaridade_lexical():
    p = HashingProvider()
    def cos(u, v):
        return sum(x * y for x, y in zip(u, v))
    tdah = p.embed_text("tdah deficit de atencao hiperatividade")
    tdah2 = p.embed_text("tdah e atencao")
    bolo = p.embed_text("receita de bolo com farinha e ovos")
    assert cos(tdah, tdah2) > cos(tdah, bolo)


def test_provider_factory_fallback():
    p = get_embedding_provider("hashing")
    assert p.name == "hashing"
    assert len(p.embed_texts(["a", "b", "c"])) == 3


def test_chunking_overlap():
    texto = "Frase de teste. " * 200  # ~3200 chars
    chunks = split_into_chunks(texto, chunk_size=500, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 600 for c in chunks)


def test_chunking_texto_curto():
    assert split_into_chunks("curto") == ["curto"]
    assert split_into_chunks("") == []
