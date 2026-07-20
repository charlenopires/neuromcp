"""Testes da ontologia: carga e integridade referencial."""

from crawler.ontology import OntologyManager, normalize_text


def test_carga_basica():
    om = OntologyManager()
    assert len(om.conceitos) >= 30
    assert len(om.categorias) >= 10
    assert len(om.dominios) >= 10
    assert "nd:tdah" in om.conceitos
    assert om.pesos_match["sigla"] == 1.0


def test_normalizacao():
    assert normalize_text("  TDAH   é   Déficit ") == "tdah e deficit"


def test_integridade_referencial():
    om = OntologyManager()
    cids = set(om.conceitos)
    catids = set(om.categorias)
    domids = set(om.dominios)
    for c in om.conceitos.values():
        if c.categoria:
            assert c.categoria in catids, f"{c.id} categoria órfã"
        if c.superClasse:
            assert c.superClasse in cids or c.superClasse in catids, f"{c.id} superClasse órfã"
        for d in c.dominiosAfetados:
            assert d in domids, f"{c.id} domínio órfão {d}"
        for ref in c.comorbidadesComuns + c.diagnosticoDiferencial:
            assert ref in cids, f"{c.id} referência órfã {ref}"
    for r in om.relacoes:
        assert r.origem in cids and r.destino in cids
