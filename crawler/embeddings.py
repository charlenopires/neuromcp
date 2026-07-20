"""
Camada de embeddings plugável para o GraphRAG.

Decisão de arquitetura (ver README > "GraphRAG e a questão do banco vetorial"):
o Neo4j 5.x possui índice vetorial NATIVO (HNSW via Lucene), então NÃO usamos
um banco vetorial separado (Qdrant/Pinecone/etc.). Os vetores são gravados como
propriedade dos próprios nós do grafo e consultados com `db.index.vector.queryNodes`.

Este módulo abstrai o provedor de embeddings por trás de uma interface única para
que o resto do sistema não dependa de um modelo específico:

- SentenceTransformerProvider  -> local, multilíngue, ótimo p/ PT-BR (recomendado)
- OllamaProvider               -> local via Ollama (nomic-embed-text)
- HashingProvider              -> fallback DETERMINÍSTICO e OFFLINE (feature hashing).
                                  NÃO é semântico — serve para testar o encanamento
                                  do GraphRAG sem rede nem download de modelos.

Todos os vetores são L2-normalizados, então similaridade de cosseno == produto interno.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from abc import ABC, abstractmethod
from typing import List, Optional

from unidecode import unidecode

logger = logging.getLogger("neuromcp.embeddings")


def _l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


class EmbeddingProvider(ABC):
    """Interface comum para provedores de embedding."""

    name: str = "abstract"

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionalidade dos vetores gerados (usada para criar o índice vetorial)."""

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Gera embeddings (L2-normalizados) para uma lista de textos."""

    def embed_text(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]


class HashingProvider(EmbeddingProvider):
    """
    Embedding determinístico offline via *feature hashing* (hashing trick) sobre
    uni e bigramas de palavras normalizadas. É um vetor lexical estável — captura
    sobreposição de vocabulário, mas NÃO significado. Uso: testes/CI e demonstração
    do fluxo GraphRAG quando não há modelo semântico disponível.
    """

    name = "hashing"

    def __init__(self, dimension: int = 384):
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    @staticmethod
    def _tokens(text: str) -> List[str]:
        text = unidecode((text or "").lower())
        words = re.findall(r"[a-z0-9]+", text)
        grams = list(words)
        grams += [f"{a}_{b}" for a, b in zip(words, words[1:])]  # bigramas
        return grams

    def _embed_one(self, text: str) -> List[float]:
        vec = [0.0] * self._dim
        for tok in self._tokens(text):
            h = hashlib.md5(tok.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "little") % self._dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[idx] += sign
        return _l2_normalize(vec)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]


class SentenceTransformerProvider(EmbeddingProvider):
    """
    Embedding semântico local via sentence-transformers. Modelo padrão multilíngue
    com forte suporte a português. Requer o extra opcional:
        uv sync --extra embeddings      (instala sentence-transformers/torch)
    """

    name = "sentence-transformers"

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        try:
            from sentence_transformers import SentenceTransformer  # import tardio
        except ImportError as e:  # pragma: no cover - depende de extra opcional
            raise ImportError(
                "sentence-transformers não está instalado. Rode `uv sync --extra embeddings` "
                "ou defina NEURO_EMBEDDING_PROVIDER=ollama|hashing."
            ) from e
        self._model = SentenceTransformer(model_name)
        self._dim = int(self._model.get_sentence_embedding_dimension())
        logger.info("SentenceTransformer '%s' carregado (dim=%d)", model_name, self._dim)

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return [v.tolist() for v in vecs]


class OllamaProvider(EmbeddingProvider):
    """Embedding semântico local via Ollama (padrão: nomic-embed-text, 768 dims)."""

    name = "ollama"

    def __init__(self, model: str = "nomic-embed-text", host: Optional[str] = None, dimension: int = 768):
        self._model = model
        self._host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        import httpx  # import tardio

        out: List[List[float]] = []
        with httpx.Client(timeout=60.0) as client:
            for t in texts:
                resp = client.post(
                    f"{self._host}/api/embeddings",
                    json={"model": self._model, "prompt": t or " "},
                )
                resp.raise_for_status()
                emb = resp.json()["embedding"]
                self._dim = len(emb)
                out.append(_l2_normalize(emb))
        return out


def get_embedding_provider(name: Optional[str] = None) -> EmbeddingProvider:
    """
    Fábrica de provedores. Ordem de resolução:
      1. argumento explícito `name`
      2. env NEURO_EMBEDDING_PROVIDER
      3. "auto": tenta sentence-transformers -> ollama -> hashing (fallback)
    """
    name = (name or os.getenv("NEURO_EMBEDDING_PROVIDER", "auto")).lower()

    if name in ("sentence-transformers", "st"):
        return SentenceTransformerProvider()
    if name == "ollama":
        return OllamaProvider()
    if name == "hashing":
        return HashingProvider()

    # auto
    try:
        return SentenceTransformerProvider()
    except Exception as e:  # noqa: BLE001
        logger.warning("sentence-transformers indisponível (%s); tentando fallback.", e)
    logger.warning(
        "Usando HashingProvider (embedding lexical NÃO-semântico). "
        "Para GraphRAG semântico, instale o extra `embeddings` ou use Ollama."
    )
    return HashingProvider()
