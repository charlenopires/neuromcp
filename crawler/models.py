from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    SCIENTIFIC_ARTICLE = "artigo_cientifico"
    BLOG = "blog"
    FORUM = "forum"
    WEBSITE = "website"


class CognitiveDomain(BaseModel):
    id: str
    rotuloPt: str
    rotuloEn: str
    descricao: Optional[str] = None


class Category(BaseModel):
    id: str
    rotuloPt: str
    rotuloEn: str
    superClasse: Optional[str] = None
    descricao: Optional[str] = None


class Concept(BaseModel):
    id: str
    tipoNo: str = "Neurodivergencia"
    rotuloPt: str
    rotuloEn: str
    sigla: List[str] = Field(default_factory=list)
    sinonimos: List[str] = Field(default_factory=list)
    grafiasComuns: List[str] = Field(default_factory=list)
    categoria: Optional[str] = None
    superClasse: Optional[str] = None
    subClasses: List[str] = Field(default_factory=list)
    statusInclusao: str = "nucleo"
    definicao: Optional[str] = None
    codigos: Dict[str, str] = Field(default_factory=dict)
    dominiosAfetados: List[str] = Field(default_factory=list)
    caracteristicas: List[str] = Field(default_factory=list)
    pontosFortes: List[str] = Field(default_factory=list)
    comorbidadesComuns: List[str] = Field(default_factory=list)
    diagnosticoDiferencial: List[str] = Field(default_factory=list)
    beneficiaDe: List[str] = Field(default_factory=list)
    palavrasChave: Dict[str, List[str]] = Field(default_factory=dict)
    hashtags: List[str] = Field(default_factory=list)
    fontes: List[str] = Field(default_factory=list)


class OntologyRelation(BaseModel):
    origem: str
    tipo: str
    destino: str
    forca: Optional[str] = None
    prevalenciaAprox: Optional[str] = None
    nota: Optional[str] = None


class MatchEvidence(BaseModel):
    conceitoId: str
    rotuloConceito: str
    confianca: float
    pesoSigla: float = 0.0
    pesoRotulo: float = 0.0
    pesoSinonimo: float = 0.0
    pesoPalavrasChave: float = 0.0
    pesoHashtag: float = 0.0
    termosEncontrados: List[str] = Field(default_factory=list)
    trechosEvidencia: List[str] = Field(default_factory=list)
    dominiosAssociados: List[str] = Field(default_factory=list)


class CrawledArticle(BaseModel):
    url: str
    titulo: str
    tipoFonte: SourceType
    dominioFonte: str
    conteudoTexto: str
    resumo: Optional[str] = None
    dataPublicacao: Optional[str] = None
    dataColeta: str
    autores: List[str] = Field(default_factory=list)
    matchesOntologia: List[MatchEvidence] = Field(default_factory=list)
    contextosDetectados: List[str] = Field(default_factory=list) # clinico, educacional, identidade
    queryBuscaUtilizada: Optional[str] = None


class CrawlingSummary(BaseModel):
    totalBuscados: int = 0
    totalProcessados: int = 0
    totalSalvosNeo4j: int = 0
    totalErros: int = 0
    fontesPorTipo: Dict[str, int] = Field(default_factory=dict)
    conceitosMaisMencionados: Dict[str, int] = Field(default_factory=dict)
