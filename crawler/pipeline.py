import asyncio
import logging
from typing import List, Optional, Dict, Any

from crawler.config import settings
from crawler.models import SourceType, CrawlingSummary, CrawledArticle
from crawler.ontology import OntologyManager
from crawler.search import SearchEngine
from crawler.fetcher import WebFetcher
from crawler.classifier import ConceptClassifier
from crawler.database import Neo4jRepository
from crawler.embeddings import get_embedding_provider

logger = logging.getLogger("neuromcp.pipeline")


class NeuroCrawlerPipeline:
    """
    Pipeline principal que coordena Busca Otimizada -> Raspagem -> Classificação -> Neo4j.
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        use_embeddings: bool = True,
    ):
        self.ontology_mgr = OntologyManager()
        self.search_engine = SearchEngine(self.ontology_mgr)
        self.fetcher = WebFetcher()
        self.classifier = ConceptClassifier(self.ontology_mgr)
        self.db = Neo4jRepository(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)
        self._use_embeddings = use_embeddings
        self._embedder = None

    @property
    def embedder(self):
        """Embedder preguiçoso (só é criado quando de fato usado)."""
        if self._use_embeddings and self._embedder is None:
            self._embedder = get_embedding_provider()
        return self._embedder

    def seed_ontology_to_db(self) -> None:
        """Garante a sincronização da ontologia JSON com o Neo4j (com embeddings de conceito)."""
        self.db.seed_ontology(self.ontology_mgr, embedder=self.embedder)

    def ingest_articles(self, articles: List[CrawledArticle]) -> CrawlingSummary:
        """
        Classifica e persiste uma lista de artigos já coletados (sem rede).
        Base do modo offline `--ingest-samples` e reutilizável para qualquer fonte local.
        """
        summary = CrawlingSummary()
        summary.totalBuscados = len(articles)
        for article in articles:
            try:
                summary.totalProcessados += 1
                classified = self.classifier.classify_article(article)
                if classified.matchesOntologia and self.db.save_article(classified, embedder=self.embedder):
                    summary.totalSalvosNeo4j += 1
                    st = article.tipoFonte.value
                    summary.fontesPorTipo[st] = summary.fontesPorTipo.get(st, 0) + 1
                    for m in classified.matchesOntologia:
                        summary.conceitosMaisMencionados[m.rotuloConceito] = (
                            summary.conceitosMaisMencionados.get(m.rotuloConceito, 0) + 1
                        )
            except Exception as e:  # noqa: BLE001
                logger.error("Erro ao ingerir artigo %s: %s", article.url, e)
                summary.totalErros += 1
        return summary

    def ingest_samples(self, seed_first: bool = True) -> CrawlingSummary:
        """Popula o grafo com o corpus de amostra offline (demonstração/testes)."""
        from crawler.sample_corpus import load_sample_articles

        if seed_first:
            self.seed_ontology_to_db()
        return self.ingest_articles(load_sample_articles())

    async def run(
        self,
        source_types: Optional[List[SourceType]] = None,
        custom_queries: Optional[List[str]] = None,
        max_results_per_query: int = 5,
        seed_first: bool = True
    ) -> CrawlingSummary:
        """
        Executa o pipeline completo do crawler.
        """
        summary = CrawlingSummary()
        
        if seed_first:
            try:
                self.seed_ontology_to_db()
            except Exception as e:
                logger.warning(f"Não foi possível semear a ontologia no Neo4j (verifique se o Docker/Neo4j está rodando): {e}")

        # 1. Descoberta de URLs candidatas via Dorks de Busca Otimizados
        candidates = self.search_engine.discover_urls(
            source_types=source_types,
            custom_queries=custom_queries,
            max_results_per_query=max_results_per_query
        )
        summary.totalBuscados = len(candidates)

        # Semaphore para controlar simultaneidade de conexões
        semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

        async def process_candidate(candidate: Dict[str, Any]):
            async with semaphore:
                try:
                    # 2. Raspagem e Leitura da Página
                    article = await self.fetcher.fetch_and_extract(candidate)
                    if not article:
                        return
                    
                    summary.totalProcessados += 1

                    # 3. Classificação e Match Ontológico
                    classified_article = self.classifier.classify_article(article)

                    # 4. Salvar no Neo4j (com chunks + embeddings para o GraphRAG)
                    if classified_article.matchesOntologia:
                        saved = self.db.save_article(classified_article, embedder=self.embedder)
                        if saved:
                            summary.totalSalvosNeo4j += 1
                            st_val = candidate["tipoFonte"].value if hasattr(candidate["tipoFonte"], "value") else str(candidate["tipoFonte"])
                            summary.fontesPorTipo[st_val] = summary.fontesPorTipo.get(st_val, 0) + 1
                            
                            for m in classified_article.matchesOntologia:
                                summary.conceitosMaisMencionados[m.rotuloConceito] = summary.conceitosMaisMencionados.get(m.rotuloConceito, 0) + 1

                except Exception as e:
                    logger.error(f"Erro ao processar candidato {candidate.get('url')}: {e}")
                    summary.totalErros += 1

        # Executa requisições de forma concorrente respeitando o semáforo
        tasks = [process_candidate(c) for c in candidates]
        await asyncio.gather(*tasks)

        logger.info(f"Execução finalizada. Processados: {summary.totalProcessados}, Salvos Neo4j: {summary.totalSalvosNeo4j}")
        return summary
