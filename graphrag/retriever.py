"""
Retriever GraphRAG sobre Neo4j (sem banco vetorial externo).

Estratégia híbrida em 4 sinais, tudo dentro do MESMO banco (Neo4j):

  1. ÂNCORA LEXICAL  — a pergunta é pontuada contra a ontologia (ConceptClassifier),
                       ancorando conceitos mesmo sem embeddings (robusto/offline).
  2. VETORIAL        — `db.index.vector.queryNodes` sobre embeddings de :Chunk e
                       :Conceito (índice HNSW nativo do Neo4j).
  3. FULLTEXT        — `db.index.fulltext.queryNodes` (Lucene/BM25) sobre conceitos.
  4. EXPANSÃO NO GRAFO — a partir dos conceitos-semente, percorre comorbidades,
                       diagnóstico diferencial, domínios cognitivos, categoria e
                       artigos que os mencionam. ESTA etapa é o "Graph" do GraphRAG.

O resultado é um contexto estruturado + um texto pronto para o LLM (no host MCP).
Degrada com elegância: se não houver índice vetorial/embeddings, ainda responde
via âncora lexical + expansão no grafo + fulltext.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from crawler.classifier import ConceptClassifier
from crawler.config import settings
from crawler.database import Neo4jRepository
from crawler.embeddings import EmbeddingProvider, get_embedding_provider
from crawler.ontology import OntologyManager

logger = logging.getLogger("neuromcp.graphrag")

_LUCENE_ESPECIAIS = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')


def _lucene_query(texto: str) -> str:
    """Constrói uma query Lucene OR a partir de palavras (com escaping)."""
    limpo = _LUCENE_ESPECIAIS.sub(r"\\\1", texto)
    termos = [t for t in re.split(r"\s+", limpo) if len(t) >= 3]
    return " OR ".join(termos) if termos else limpo.strip()


class ComorbidadeRef(BaseModel):
    id: str
    rotulo: Optional[str] = None
    forca: Optional[str] = None
    prevalencia: Optional[str] = None


class RetrievedConcept(BaseModel):
    id: str
    rotuloPt: str
    rotuloEn: Optional[str] = None
    definicao: Optional[str] = None
    statusInclusao: Optional[str] = None
    categoria: Optional[str] = None
    score: float = 0.0
    via: List[str] = Field(default_factory=list)  # ancora | vetor | fulltext | grafo
    dominios: List[str] = Field(default_factory=list)
    pontosFortes: List[str] = Field(default_factory=list)
    comorbidades: List[ComorbidadeRef] = Field(default_factory=list)
    diagnosticoDiferencial: List[ComorbidadeRef] = Field(default_factory=list)
    totalArtigos: int = 0


class RetrievedChunk(BaseModel):
    texto: str
    score: float
    artigoUrl: Optional[str] = None
    artigoTitulo: Optional[str] = None
    fonte: Optional[str] = None
    conceitos: List[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    pergunta: str
    conceitos: List[RetrievedConcept] = Field(default_factory=list)
    chunks: List[RetrievedChunk] = Field(default_factory=list)
    contextoFormatado: str = ""
    avisos: List[str] = Field(default_factory=list)


class GraphRAGRetriever:
    def __init__(
        self,
        repo: Optional[Neo4jRepository] = None,
        embedder: Optional[EmbeddingProvider] = None,
        ontology_mgr: Optional[OntologyManager] = None,
        lazy_embedder: bool = True,
    ):
        self.repo = repo or Neo4jRepository()
        self.ontology_mgr = ontology_mgr or OntologyManager()
        self.classifier = ConceptClassifier(self.ontology_mgr)
        self._embedder = embedder
        if not lazy_embedder and embedder is None:
            self._embedder = get_embedding_provider()

    @property
    def embedder(self) -> EmbeddingProvider:
        if self._embedder is None:
            self._embedder = get_embedding_provider()
        return self._embedder

    # ---------- sinais individuais ----------

    def anchor_concepts(self, query: str, min_confidence: float = 0.3) -> Dict[str, float]:
        """Ancoragem lexical da pergunta nos conceitos da ontologia (id -> score)."""
        matches = self.classifier.match_concepts_in_text(query, min_confidence=min_confidence)
        return {m.conceitoId: m.confianca for m in matches}

    def vector_search_chunks(self, query: str, k: int) -> List[RetrievedChunk]:
        try:
            vec = self.embedder.embed_text(query)
            rows = self.repo.run_read(
                """
                CALL db.index.vector.queryNodes('chunk_embedding', $k, $vec)
                YIELD node AS ch, score
                MATCH (a:Artigo)-[:HAS_CHUNK]->(ch)
                OPTIONAL MATCH (a)-[:PUBLICADO_EM]->(f:Fonte)
                OPTIONAL MATCH (a)-[:MENCIONA]->(c:Conceito)
                RETURN ch.texto AS texto, score,
                       a.url AS url, a.titulo AS titulo, f.dominio AS fonte,
                       collect(DISTINCT c.rotuloPt) AS conceitos
                ORDER BY score DESC
                """,
                k=k, vec=vec,
            )
            return [
                RetrievedChunk(
                    texto=r["texto"], score=r["score"], artigoUrl=r.get("url"),
                    artigoTitulo=r.get("titulo"), fonte=r.get("fonte"),
                    conceitos=[c for c in r.get("conceitos", []) if c],
                )
                for r in rows
            ]
        except Exception as e:  # noqa: BLE001 — índice/embeddings podem não existir ainda
            logger.warning("Busca vetorial de chunks indisponível (%s).", e)
            return []

    def vector_search_concepts(self, query: str, k: int) -> Dict[str, float]:
        try:
            vec = self.embedder.embed_text(query)
            rows = self.repo.run_read(
                """
                CALL db.index.vector.queryNodes('conceito_embedding', $k, $vec)
                YIELD node AS c, score
                RETURN c.id AS id, score ORDER BY score DESC
                """,
                k=k, vec=vec,
            )
            return {r["id"]: r["score"] for r in rows}
        except Exception as e:  # noqa: BLE001
            logger.warning("Busca vetorial de conceitos indisponível (%s).", e)
            return {}

    def fulltext_search_concepts(self, query: str, k: int) -> Dict[str, float]:
        try:
            rows = self.repo.run_read(
                """
                CALL db.index.fulltext.queryNodes('conceito_fulltext', $q)
                YIELD node AS c, score
                RETURN c.id AS id, score ORDER BY score DESC LIMIT $k
                """,
                q=_lucene_query(query), k=k,
            )
            return {r["id"]: r["score"] for r in rows}
        except Exception as e:  # noqa: BLE001
            logger.warning("Busca fulltext de conceitos indisponível (%s).", e)
            return {}

    def _local_expand(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Expansão a partir da ONTOLOGIA LOCAL (JSON), sem Neo4j. Garante que o GraphRAG
        degrade com elegância: mesmo com o banco fora, a vizinhança de conhecimento
        (comorbidades, domínios, diagnóstico diferencial) vem do arquivo de ontologia.
        """
        ont = self.ontology_mgr
        # lookup de força/prevalência das comorbidades (relação simétrica)
        forca: Dict[frozenset, Dict[str, Any]] = {}
        for r in ont.relacoes:
            if "COMORBIDO" in r.tipo:
                forca[frozenset((r.origem, r.destino))] = {"forca": r.forca, "prevalencia": r.prevalenciaAprox}

        def rotulo(cid: str) -> Optional[str]:
            c = ont.conceitos.get(cid)
            return c.rotuloPt if c else None

        out: Dict[str, Dict[str, Any]] = {}
        for cid in ids:
            c = ont.conceitos.get(cid)
            if not c:
                continue
            cat = ont.categorias.get(c.categoria) if c.categoria else None
            comorb = []
            for x in c.comorbidadesComuns:
                meta = forca.get(frozenset((cid, x)), {})
                comorb.append({"id": x, "rotulo": rotulo(x), "forca": meta.get("forca"),
                               "prevalencia": meta.get("prevalencia")})
            out[cid] = {
                "id": cid, "rotuloPt": c.rotuloPt, "rotuloEn": c.rotuloEn,
                "definicao": c.definicao, "statusInclusao": c.statusInclusao,
                "pontosFortes": c.pontosFortes,
                "categoria": cat.rotuloPt if cat else None,
                "dominios": [ont.dominios[d].rotuloPt for d in c.dominiosAfetados if d in ont.dominios],
                "comorbidades": comorb,
                "diagnosticoDiferencial": [{"id": x, "rotulo": rotulo(x)} for x in c.diagnosticoDiferencial],
                "totalArtigos": 0,
            }
        return out

    def expand_concepts(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Expansão no grafo Neo4j: vizinhança ontológica de cada conceito-semente."""
        if not ids:
            return {}
        rows = self.repo.run_read(
            """
            MATCH (c:Conceito) WHERE c.id IN $ids
            OPTIONAL MATCH (c)-[:IN_CATEGORY]->(cat:Categoria)
            OPTIONAL MATCH (c)-[:AFFECTS_DOMAIN]->(dom:DominioCognitivo)
            OPTIONAL MATCH (c)-[co:COMORBID_WITH]-(cm:Conceito)
            OPTIONAL MATCH (c)-[:DIFFERENTIAL_DX]-(dd:Conceito)
            OPTIONAL MATCH (art:Artigo)-[:MENCIONA]->(c)
            RETURN c.id AS id, c.rotuloPt AS rotuloPt, c.rotuloEn AS rotuloEn,
                   c.definicao AS definicao, c.statusInclusao AS statusInclusao,
                   c.pontosFortes AS pontosFortes,
                   cat.rotuloPt AS categoria,
                   collect(DISTINCT dom.rotuloPt) AS dominios,
                   collect(DISTINCT CASE WHEN cm IS NULL THEN NULL ELSE
                       {id: cm.id, rotulo: cm.rotuloPt, forca: co.forca, prevalencia: co.prevalenciaAprox} END) AS comorbidades,
                   collect(DISTINCT CASE WHEN dd IS NULL THEN NULL ELSE
                       {id: dd.id, rotulo: dd.rotuloPt} END) AS diagnosticoDiferencial,
                   count(DISTINCT art) AS totalArtigos
            """,
            ids=ids,
        )
        return {r["id"]: r for r in rows}

    # ---------- orquestração ----------

    def retrieve(
        self,
        query: str,
        top_k_chunks: Optional[int] = None,
        top_k_concepts: Optional[int] = None,
    ) -> RetrievalResult:
        top_k_chunks = top_k_chunks or settings.graphrag_top_k_chunks
        top_k_concepts = top_k_concepts or settings.graphrag_top_k_concepts
        avisos: List[str] = []

        # 1. sinais de conceito (ancora + vetor + fulltext), com proveniência
        via: Dict[str, set] = {}
        scores: Dict[str, float] = {}

        def registrar(fonte: str, mapa: Dict[str, float]):
            for cid, sc in mapa.items():
                scores[cid] = max(scores.get(cid, 0.0), float(sc))
                via.setdefault(cid, set()).add(fonte)

        registrar("ancora", self.anchor_concepts(query))
        registrar("vetor", self.vector_search_concepts(query, top_k_concepts))
        registrar("fulltext", self.fulltext_search_concepts(query, top_k_concepts))

        if not scores:
            avisos.append(
                "Nenhum conceito ancorado pela pergunta. Verifique se a ontologia foi semeada "
                "e/ou se os embeddings foram gerados."
            )

        seed_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[: top_k_concepts * 2]

        # 2. expansão no grafo (a etapa "Graph" do GraphRAG).
        #    Se o Neo4j estiver fora/vazio, completa com a ontologia local (degrada com elegância).
        expandido: Dict[str, Dict[str, Any]] = {}
        try:
            expandido = self.expand_concepts(seed_ids)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"Expansão no grafo Neo4j indisponível ({e}); usando a ontologia local (JSON).")
        faltantes = [cid for cid in seed_ids if cid not in expandido]
        if faltantes:
            if expandido == {} and not any("ontologia local" in a for a in avisos):
                avisos.append("Grafo Neo4j vazio/indisponível — usando a ontologia local (JSON) como grafo.")
            for k, v in self._local_expand(faltantes).items():
                expandido.setdefault(k, v)

        # inclui vizinhos de grafo (comorbidades/dif.) como conceitos de contexto
        conceitos: List[RetrievedConcept] = []
        for cid in seed_ids:
            data = expandido.get(cid)
            if not data:
                continue
            conceitos.append(
                RetrievedConcept(
                    id=data["id"], rotuloPt=data.get("rotuloPt") or cid,
                    rotuloEn=data.get("rotuloEn"), definicao=data.get("definicao"),
                    statusInclusao=data.get("statusInclusao"), categoria=data.get("categoria"),
                    score=round(scores.get(cid, 0.0), 3), via=sorted(via.get(cid, [])),
                    dominios=[d for d in data.get("dominios", []) if d],
                    pontosFortes=data.get("pontosFortes") or [],
                    comorbidades=[ComorbidadeRef(**c) for c in data.get("comorbidades", []) if c],
                    diagnosticoDiferencial=[ComorbidadeRef(**c) for c in data.get("diagnosticoDiferencial", []) if c],
                    totalArtigos=data.get("totalArtigos", 0),
                )
            )

        # 3. evidências textuais via busca vetorial de chunks
        chunks = self.vector_search_chunks(query, top_k_chunks)
        if not chunks:
            avisos.append(
                "Sem evidências textuais (chunks) — nenhum artigo com embeddings recuperado. "
                "Rode o crawler/ingestão com um embedder para popular :Chunk."
            )

        result = RetrievalResult(
            pergunta=query, conceitos=conceitos, chunks=chunks, avisos=avisos
        )
        result.contextoFormatado = self.build_context(result)
        return result

    def build_context(self, result: RetrievalResult) -> str:
        """Monta o contexto textual (pronto para o LLM do host MCP)."""
        linhas: List[str] = []
        linhas.append(f"# Pergunta\n{result.pergunta}\n")

        if result.conceitos:
            linhas.append("# Conceitos da ontologia (grafo de conhecimento)")
            for c in result.conceitos:
                cab = f"## {c.rotuloPt} ({c.id})"
                if c.statusInclusao:
                    cab += f" — inclusão: {c.statusInclusao}"
                linhas.append(cab)
                if c.definicao:
                    linhas.append(c.definicao)
                if c.categoria:
                    linhas.append(f"- Categoria: {c.categoria}")
                if c.dominios:
                    linhas.append(f"- Domínios cognitivos: {', '.join(c.dominios)}")
                if c.comorbidades:
                    com = ", ".join(
                        f"{x.rotulo or x.id}" + (f" (força {x.forca})" if x.forca else "")
                        for x in c.comorbidades
                    )
                    linhas.append(f"- Comorbidades frequentes: {com}")
                if c.diagnosticoDiferencial:
                    dd = ", ".join(x.rotulo or x.id for x in c.diagnosticoDiferencial)
                    linhas.append(f"- Diagnóstico diferencial: {dd}")
                if c.pontosFortes:
                    linhas.append(f"- Pontos fortes: {', '.join(c.pontosFortes)}")
                linhas.append("")

        if result.chunks:
            linhas.append("# Evidências de artigos coletados")
            for i, ch in enumerate(result.chunks, 1):
                origem = ch.artigoTitulo or ch.artigoUrl or ch.fonte or "fonte desconhecida"
                linhas.append(f"[{i}] ({origem}) {ch.texto}")
            linhas.append("")

        linhas.append(
            "# Instrução\nResponda à pergunta usando SOMENTE o contexto acima. Cite os conceitos "
            "e as fontes [n]. Se o contexto for insuficiente, diga isso. Rotule conteúdo, não pessoas; "
            "não faça diagnóstico de indivíduos."
        )
        return "\n".join(linhas)
