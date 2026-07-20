import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from unidecode import unidecode

from crawler.models import Concept, Category, CognitiveDomain, OntologyRelation
from crawler.config import settings


def normalize_text(text: str) -> str:
    """
    Aplica as regras de normalização especificadas na ontologia:
    - minusculizar
    - remover acentos (unidecode)
    - colapsar espacos
    """
    if not text:
        return ""
    text = text.lower()
    text = unidecode(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class OntologyManager:
    def __init__(self, json_path: Optional[Path] = None):
        self.json_path = json_path or settings.ontology_path
        self.data: Dict[str, Any] = {}
        self.conceitos: Dict[str, Concept] = {}
        self.categorias: Dict[str, Category] = {}
        self.dominios: Dict[str, CognitiveDomain] = {}
        self.relacoes: List[OntologyRelation] = []
        self.estrategia_match: Dict[str, Any] = {}
        self.sinais_contexto: Dict[str, List[str]] = {}
        self.pesos_match: Dict[str, float] = {}
        
        self.load_ontology()

    def load_ontology(self) -> None:
        """Carrega e indexa o arquivo de ontologia JSON."""
        if not self.json_path.exists():
            raise FileNotFoundError(f"Ontologia não encontrada no caminho: {self.json_path}")

        with open(self.json_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        # Domínios Cognitivos
        for dom in self.data.get("dominiosCognitivos", []):
            cd = CognitiveDomain(**dom)
            self.dominios[cd.id] = cd

        # Categorias
        for cat in self.data.get("categorias", []):
            c = Category(**cat)
            self.categorias[c.id] = c

        # Conceitos
        for conc in self.data.get("conceitos", []):
            c = Concept(**conc)
            self.conceitos[c.id] = c

        # Relações
        for rel in self.data.get("relacoes", []):
            self.relacoes.append(OntologyRelation(**rel))

        # Configurações do Crawler
        crawler_cfg = self.data.get("crawler", {})
        self.estrategia_match = crawler_cfg.get("estrategiaDeMatch", {})
        self.sinais_contexto = crawler_cfg.get("sinaisDeContexto", {})
        self.pesos_match = self.estrategia_match.get("pesos", {
            "sigla": 1.0,
            "rotuloPt": 0.9,
            "sinonimos": 0.8,
            "palavrasChave": 0.7,
            "hashtags": 0.6,
            "grafiasComuns": 0.5
        })

    def get_search_keywords(self) -> List[str]:
        """Retorna termos otimizados para dorks de busca no Google/Search engines."""
        keywords = set()
        for c in self.conceitos.values():
            if c.rotuloPt:
                keywords.add(c.rotuloPt)
            for s in c.sigla:
                if len(s) >= 3:  # Evita siglas curtas demais que gerem ruído
                    keywords.add(s)
            pt_kw = c.palavrasChave.get("pt", [])
            for kw in pt_kw[:3]:
                keywords.add(kw)
        return list(keywords)
