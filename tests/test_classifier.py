"""Testes do classificador ponderado e da ancoragem de perguntas."""

import datetime

from crawler.classifier import ConceptClassifier
from crawler.models import CrawledArticle, SourceType
from crawler.ontology import OntologyManager

OM = OntologyManager()
CLF = ConceptClassifier(OM)


def _artigo(titulo, texto, tipo=SourceType.BLOG):
    return CrawledArticle(
        url="https://ex.org/x", titulo=titulo, tipoFonte=tipo, dominioFonte="ex.org",
        conteudoTexto=texto,
        dataColeta=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


def test_classifica_tdah_tea_dislexia():
    art = _artigo(
        "TDAH, autismo e dislexia",
        "O TDAH está ligado à disfunção executiva. Pessoas autistas (TEA) e com dislexia "
        "apresentam diferenças de leitura e atenção. Diagnóstico e tratamento clínicos.",
    )
    art = CLF.classify_article(art)
    ids = {m.conceitoId for m in art.matchesOntologia}
    assert {"nd:tdah", "nd:tea", "nd:dislexia"}.issubset(ids)
    assert "clinico" in art.contextosDetectados


def test_confianca_ordenada_e_limiar():
    art = CLF.classify_article(_artigo("Discalculia", "A discalculia afeta o senso numérico e o cálculo."))
    assert art.matchesOntologia
    confs = [m.confianca for m in art.matchesOntologia]
    assert confs == sorted(confs, reverse=True)
    assert all(c >= CLF.min_confidence for c in confs)


def test_ancoragem_pergunta():
    scores = {m.conceitoId: m.confianca
              for m in CLF.match_concepts_in_text("quais comorbidades do TDAH?", min_confidence=0.3)}
    assert "nd:tdah" in scores


def test_texto_irrelevante_nao_casa():
    art = CLF.classify_article(_artigo("Receita de bolo", "Misture farinha, ovos e açúcar e asse por 40 minutos."))
    assert art.matchesOntologia == []
