"""Fatiamento (chunking) de texto para recuperação semântica no GraphRAG."""

from __future__ import annotations

import re
from typing import List

from crawler.config import settings


def split_into_chunks(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> List[str]:
    """
    Divide um texto em janelas de ~`chunk_size` caracteres com `overlap` de sobreposição,
    respeitando fronteiras de sentença sempre que possível (corte "suave").

    A sobreposição preserva contexto entre chunks vizinhos, o que melhora a
    recuperação vetorial (evita cortar uma ideia exatamente na fronteira).
    """
    chunk_size = chunk_size or settings.chunk_size_chars
    overlap = overlap if overlap is not None else settings.chunk_overlap_chars
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            # tenta terminar em fim de sentença dentro da janela
            janela = text[start:end]
            corte = max(janela.rfind(". "), janela.rfind("! "), janela.rfind("? "))
            if corte > chunk_size * 0.5:
                end = start + corte + 1
        chunks.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]
