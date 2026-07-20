import datetime
import logging
from urllib.parse import urlparse
from typing import Optional, Dict, Any
import httpx
import trafilatura
from bs4 import BeautifulSoup

from crawler.config import settings
from crawler.models import CrawledArticle, SourceType

logger = logging.getLogger("neuromcp.fetcher")


class WebFetcher:
    """
    Cliente HTTP assíncrono avançado para raspagem e extração limpa de conteúdo web.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if not settings.tls_verify:
            logger.warning(
                "NEURO_ALLOW_INSECURE_TLS ativo: verificação TLS DESATIVADA (inseguro, sujeito a MITM)."
            )

    def _extract_domain(self, url: str) -> str:
        """Extrai o nome do domínio principal da URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    async def fetch_and_extract(
        self,
        candidate: Dict[str, Any]
    ) -> Optional[CrawledArticle]:
        """
        Baixa o conteúdo HTML da URL e extrai o texto principal e metadados.
        """
        url = candidate["url"]
        tipo_fonte: SourceType = candidate.get("tipoFonte", SourceType.WEBSITE)
        query_busca = candidate.get("query")
        
        logger.info(f"Lendo página: {url}")
        
        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=settings.request_timeout_seconds,
                follow_redirects=True,
                verify=settings.tls_verify  # verificação TLS ligada por padrão (ver config)
            ) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    logger.warning(f"Status HTTP {response.status_code} para {url}")
                    return None

                html_content = response.text
                if not html_content or len(html_content) < 100:
                    return None

                # Tenta extração de alta qualidade com Trafilatura (bare_extraction)
                extracted_data = trafilatura.bare_extraction(
                    html_content,
                    include_comments=True if tipo_fonte == SourceType.FORUM else False,
                    include_tables=True,
                    as_dict=True
                )

                titulo = candidate.get("titulo")
                conteudo_texto = ""
                resumo = candidate.get("snippet")
                autores = []
                data_pub = None

                if isinstance(extracted_data, dict):
                    conteudo_texto = extracted_data.get("text") or ""
                    if not titulo and extracted_data.get("title"):
                        titulo = extracted_data.get("title")
                    if extracted_data.get("author"):
                        autores = [extracted_data.get("author")]
                    if extracted_data.get("date"):
                        data_pub = extracted_data.get("date")

                if not conteudo_texto:
                    conteudo_texto = trafilatura.extract(html_content) or ""
                
                # Fallback para BeautifulSoup se trafilatura não extrair texto suficiente
                if not conteudo_texto or len(conteudo_texto) < 150:
                    soup = BeautifulSoup(html_content, "lxml")
                    
                    # Remove tags de script, estilo e navegação
                    for elem in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                        elem.decompose()
                        
                    if not titulo and soup.title:
                        titulo = soup.title.get_text(strip=True)
                        
                    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]
                    conteudo_texto = "\n\n".join(paragraphs)

                if not titulo:
                    titulo = f"Página em {self._extract_domain(url)}"

                if not conteudo_texto or len(conteudo_texto.strip()) < 80:
                    logger.warning(f"Conteúdo insuficiente extraído de {url}")
                    return None

                dominio = self._extract_domain(url)
                data_hoje = datetime.datetime.now(datetime.timezone.utc).isoformat()

                article = CrawledArticle(
                    url=url,
                    titulo=titulo.strip(),
                    tipoFonte=tipo_fonte,
                    dominioFonte=dominio,
                    conteudoTexto=conteudo_texto.strip(),
                    resumo=resumo,
                    dataPublicacao=data_pub,
                    dataColeta=data_hoje,
                    autores=autores,
                    queryBuscaUtilizada=query_busca
                )
                
                return article

        except Exception as e:
            logger.error(f"Falha ao ler página {url}: {e}")
            return None
