import re
import logging
from typing import List, Dict, Tuple, Set, Any
from unidecode import unidecode

from crawler.models import Concept, CrawledArticle, MatchEvidence
from crawler.ontology import OntologyManager, normalize_text
from crawler.config import settings

logger = logging.getLogger("neuromcp.classifier")


class ConceptClassifier:
    """
    Classificador de texto baseado na ontologia de neurodivergência.
    Aplica as regras de pontuação ponderada, extração de evidências e desambiguação
    definidas em crawler.estrategiaDeMatch do arquivo ontologia_neurodivergencia.json.
    """

    def __init__(self, ontology_mgr: OntologyManager):
        self.ontology_mgr = ontology_mgr
        self.pesos = ontology_mgr.pesos_match
        self.min_confidence = ontology_mgr.estrategia_match.get("limiteConfiancaMinima", settings.default_confidence_threshold)
        self.sinais_contexto = ontology_mgr.sinais_contexto

    def detect_context_signals(self, text_normalized: str) -> List[str]:
        """Detecta sinais de contexto no texto (clinico, educacional, identidade)."""
        contexts = []
        for ctx_name, signal_words in self.sinais_contexto.items():
            count = sum(1 for word in signal_words if normalize_text(word) in text_normalized)
            if count >= 1:
                contexts.append(ctx_name)
        return contexts

    def extract_evidence_snippets(self, text_raw: str, terms: Set[str], max_snippets: int = 3) -> List[str]:
        """Extrai trechos do texto original contendo as palavras-chave para evidência."""
        snippets = []
        lines = [line.strip() for line in re.split(r'[\n\.\?!]+', text_raw) if len(line.strip()) > 30]
        
        for line in lines:
            line_norm = normalize_text(line)
            for term in terms:
                term_norm = normalize_text(term)
                if term_norm in line_norm:
                    snippets.append(line[:250].strip() + ("..." if len(line) > 250 else ""))
                    break
            if len(snippets) >= max_snippets:
                break
        return snippets

    def classify_article(self, article: CrawledArticle) -> CrawledArticle:
        """
        Analisa o título e o conteúdo do artigo e calcula os matches com a ontologia.
        """
        full_text = f"{article.titulo}\n{article.conteudoTexto}"
        full_text_norm = normalize_text(full_text)
        title_norm = normalize_text(article.titulo)

        matches: List[MatchEvidence] = []
        detected_contexts = self.detect_context_signals(full_text_norm)
        article.contextosDetectados = detected_contexts

        for concept in self.ontology_mgr.conceitos.values():
            termos_encontrados = set()
            score_acumulado = 0.0

            # 1. Siglas (peso: 1.0)
            peso_sigla = 0.0
            for sigla in concept.sigla:
                sigla_norm = normalize_text(sigla)
                if len(sigla_norm) >= 2:
                    # Usa busca por limite de palavra para siglas exatas
                    pattern = r'\b' + re.escape(sigla_norm) + r'\b'
                    if re.search(pattern, full_text_norm):
                        termos_encontrados.add(sigla)
                        peso_sigla = self.pesos.get("sigla", 1.0)
                        # Bônus se a sigla aparece no título
                        if re.search(pattern, title_norm):
                            peso_sigla *= 1.2
                        break
            score_acumulado += peso_sigla

            # 2. Rótulo Português (peso: 0.9)
            peso_rotulo = 0.0
            rotulo_norm = normalize_text(concept.rotuloPt)
            if rotulo_norm and rotulo_norm in full_text_norm:
                termos_encontrados.add(concept.rotuloPt)
                peso_rotulo = self.pesos.get("rotuloPt", 0.9)
                if rotulo_norm in title_norm:
                    peso_rotulo *= 1.2
            score_acumulado += peso_rotulo

            # 3. Sinônimos (peso: 0.8)
            peso_sinonimo = 0.0
            for sin in concept.sinonimos:
                sin_norm = normalize_text(sin)
                if sin_norm and sin_norm in full_text_norm:
                    termos_encontrados.add(sin)
                    peso_sinonimo = max(peso_sinonimo, self.pesos.get("sinonimos", 0.8))
            score_acumulado += peso_sinonimo

            # 4. Palavras-chave (peso: 0.7)
            peso_kw = 0.0
            kws = concept.palavrasChave.get("pt", []) + concept.palavrasChave.get("en", [])
            matched_kws = 0
            for kw in kws:
                kw_norm = normalize_text(kw)
                if kw_norm and kw_norm in full_text_norm:
                    termos_encontrados.add(kw)
                    matched_kws += 1
            if matched_kws > 0:
                peso_kw = self.pesos.get("palavrasChave", 0.7) * min(1.3, 0.7 + (matched_kws * 0.1))
            score_acumulado += peso_kw

            # 5. Hashtags (peso: 0.6)
            peso_tag = 0.0
            for tag in concept.hashtags:
                tag_norm = normalize_text(tag)
                if tag_norm and tag_norm in full_text_norm:
                    termos_encontrados.add(tag)
                    peso_tag = self.pesos.get("hashtags", 0.6)
                    break
            score_acumulado += peso_tag

            # 6. Grafias comuns (peso: 0.5)
            for g in concept.grafiasComuns:
                g_norm = normalize_text(g)
                if g_norm and g_norm in full_text_norm:
                    termos_encontrados.add(g)
                    score_acumulado += self.pesos.get("grafiasComuns", 0.5)

            # Normaliza a confiança para uma escala de [0.0, 1.0]
            # O score máximo possível é em torno de 3.5 a 4.0
            confianca_calculada = min(1.0, score_acumulado / 2.2)

            if confianca_calculada >= self.min_confidence and len(termos_encontrados) > 0:
                snippets = self.extract_evidence_snippets(article.conteudoTexto, termos_encontrados)
                
                evidence = MatchEvidence(
                    conceitoId=concept.id,
                    rotuloConceito=concept.rotuloPt,
                    confianca=round(confianca_calculada, 3),
                    pesoSigla=peso_sigla,
                    pesoRotulo=peso_rotulo,
                    pesoSinonimo=peso_sinonimo,
                    pesoPalavrasChave=peso_kw,
                    pesoHashtag=peso_tag,
                    termosEncontrados=list(termos_encontrados),
                    trechosEvidencia=snippets,
                    dominiosAssociados=concept.dominiosAfetados
                )
                matches.append(evidence)

        # Ordena matches por confiança decrescente
        matches.sort(key=lambda x: x.confianca, reverse=True)
        article.matchesOntologia = matches
        return article
