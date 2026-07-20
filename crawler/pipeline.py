import asyncio
import logging
from typing import List, Optional, Dict, Any

from crawler.config import settings
from crawler.models import SourceType, CrawlingSummary
from crawler.ontology import OntologyManager
from crawler.search import SearchEngine
from crawler.fetcher import WebFetcher
from crawler.classifier import ConceptClassifier
from crawler.database import Neo4jRepository

logger = logging.getLogger("neuromcp.pipeline")


class NeuroCrawlerPipeline:
    """
    Pipeline principal que coordena Busca Otimizada -> Raspagem -> Classificação -> Neo4j.
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None
    ):
        self.ontology_mgr = OntologyManager()
        self.search_engine = SearchEngine(self.ontology_mgr)
        self.fetcher = WebFetcher()
        self.classifier = ConceptClassifier(self.ontology_mgr)
        self.db = Neo4jRepository(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)

    def seed_ontology_to_db(self) -> None:
        """Garante a sincronização da ontologia JSON com o Neo4j."""
        self.db.seed_ontology(self.ontology_mgr)

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

                    # 4. Salvar no Neo4j
                    if classified_article.matchesOntologia:
                        saved = self.db.save_article(classified_article)
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
