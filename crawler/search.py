import asyncio
import logging
from typing import List, Dict, Any, Optional
from duckduckgo_search import DDGS

from crawler.models import SourceType
from crawler.ontology import OntologyManager, normalize_text

logger = logging.getLogger("neuromcp.search")


class SearchDorkBuilder:
    """
    Construtor de dorks de pesquisa otimizadas no Google / motores de busca
    com base nas regras da ontologia.
    """
    
    SITE_FILTERS = {
        SourceType.SCIENTIFIC_ARTICLE: [
            "site:ncbi.nlm.nih.gov/pmc",
            "site:scielo.br",
            "site:pubmed.ncbi.nlm.nih.gov",
            "site:arxiv.org",
            "filetype:pdf site:edu.br",
            "filetype:pdf site:org"
        ],
        SourceType.BLOG: [
            "site:medium.com",
            "site:wordpress.com",
            "inurl:blog",
            "inurl:artigo"
        ],
        SourceType.FORUM: [
            "site:reddit.com/r/autism",
            "site:reddit.com/r/ADHD",
            "site:reddit.com/r/neurodiversity",
            "site:quora.com",
            "inurl:forum"
        ],
        SourceType.WEBSITE: [
            "site:org.br",
            "site:gov.br",
            "site:abda.org.br"
        ]
    }

    @classmethod
    def build_dork_queries(
        cls,
        keywords: List[str],
        source_type: SourceType,
        max_queries: int = 5
    ) -> List[str]:
        """Gera uma lista de dorks otimizados para o motor de busca."""
        queries = []
        site_list = cls.SITE_FILTERS.get(source_type, [])
        
        # Agrupa palavras-chave em blocos
        for i, kw in enumerate(keywords[:max_queries]):
            clean_kw = f'"{kw}"' if " " in kw else kw
            
            if source_type == SourceType.SCIENTIFIC_ARTICLE:
                # Dork para artigos científicos
                site_filter = site_list[i % len(site_list)] if site_list else ""
                dork = f"{site_filter} {clean_kw} (pesquisa OR estudo OR artigo)"
                queries.append(dork.strip())

            elif source_type == SourceType.BLOG:
                site_filter = site_list[i % len(site_list)] if site_list else "inurl:blog"
                dork = f"{site_filter} {clean_kw} neurodivergente OR neurodiversidade"
                queries.append(dork.strip())

            elif source_type == SourceType.FORUM:
                site_filter = site_list[i % len(site_list)] if site_list else "site:reddit.com"
                dork = f"{site_filter} {clean_kw} experiencia OR relato"
                queries.append(dork.strip())

            else:
                dork = f'{clean_kw} neurodivergencia OR "neurodiversidade"'
                queries.append(dork.strip())

        return queries


class SearchEngine:
    """
    Executa pesquisas web com dorks otimizados usando DuckDuckGo Search
    (respeitando limites e fornecendo URLs candidatas para o crawler).
    """

    def __init__(self, ontology_mgr: OntologyManager):
        self.ontology_mgr = ontology_mgr

    def search_candidates(
        self,
        query: str,
        source_type: SourceType,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Executa uma busca individual e retorna a lista de resultados com URL, título e trecho.
        """
        logger.info(f"Executando busca otimizada ({source_type.value}): {query}")
        results = []
        try:
            with DDGS() as ddgs:
                ddg_gen = ddgs.text(
                    keywords=query,
                    region="br-pt",
                    safesearch="off",
                    max_results=max_results
                )
                for r in ddg_gen:
                    results.append({
                        "url": r.get("href") or r.get("link"),
                        "titulo": r.get("title"),
                        "snippet": r.get("body") or r.get("snippet"),
                        "tipoFonte": source_type,
                        "query": query
                    })
        except Exception as e:
            logger.warning(f"Erro ao buscar no motor de busca para query '{query}': {e}")
        
        return results

    def discover_urls(
        self,
        source_types: Optional[List[SourceType]] = None,
        custom_queries: Optional[List[str]] = None,
        max_results_per_query: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Gera dorks com base nos conceitos da ontologia e descobre candidatas a crawl.
        """
        source_types = source_types or [
            SourceType.SCIENTIFIC_ARTICLE,
            SourceType.BLOG,
            SourceType.FORUM,
            SourceType.WEBSITE
        ]

        keywords = self.ontology_mgr.get_search_keywords()
        discovered = []
        seen_urls = set()

        if custom_queries:
            for q in custom_queries:
                for st in source_types:
                    candidates = self.search_candidates(q, st, max_results=max_results_per_query)
                    for c in candidates:
                        if c["url"] and c["url"] not in seen_urls:
                            seen_urls.add(c["url"])
                            discovered.append(c)

        for st in source_types:
            dorks = SearchDorkBuilder.build_dork_queries(keywords, st, max_queries=3)
            for dork in dorks:
                candidates = self.search_candidates(dork, st, max_results=max_results_per_query)
                for c in candidates:
                    if c["url"] and c["url"] not in seen_urls:
                        seen_urls.add(c["url"])
                        discovered.append(c)

        logger.info(f"Total de {len(discovered)} URLs candidatas únicas descobertas.")
        return discovered
