"""
Corpus de amostra (offline) para popular o grafo sem depender de crawl ao vivo.

Serve para: (1) demonstrar o pipeline classificação -> chunks -> Neo4j de ponta a
ponta; (2) testar o GraphRAG; (3) dar dados iniciais ao servidor MCP. Os textos são
sínteses informativas em PT-BR sobre cada neurodivergência (não são artigos reais;
as URLs são ilustrativas com o domínio exemplo `neuro.exemplo.org`).
"""

from __future__ import annotations

import datetime
from typing import List

from crawler.models import CrawledArticle, SourceType


def _art(url: str, titulo: str, tipo: SourceType, dominio: str, texto: str,
         autores: List[str] | None = None) -> CrawledArticle:
    return CrawledArticle(
        url=url, titulo=titulo, tipoFonte=tipo, dominioFonte=dominio,
        conteudoTexto=" ".join(texto.split()),
        dataColeta=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        autores=autores or [],
        queryBuscaUtilizada="corpus_offline",
    )


_DOCS = [
    (
        "https://neuro.exemplo.org/tdah-funcoes-executivas",
        "TDAH e funções executivas: desatenção, hiperatividade e impulsividade",
        SourceType.SCIENTIFIC_ARTICLE, "neuro.exemplo.org",
        """O Transtorno do Déficit de Atenção e Hiperatividade (TDAH) é uma condição do
        neurodesenvolvimento marcada por desatenção, hiperatividade e impulsividade. A
        disfunção executiva compromete planejamento, memória de trabalho e inibição, o que
        explica a procrastinação e a desregulação emocional relatadas. O diagnóstico é clínico
        e o tratamento costuma ser multimodal. Muitas pessoas com TDAH também apresentam
        autismo (TEA) e dislexia como comorbidades, exigindo avaliação abrangente.""",
    ),
    (
        "https://neuro.exemplo.org/autismo-espectro",
        "Transtorno do Espectro Autista (TEA): comunicação, interesses restritos e sensorial",
        SourceType.SCIENTIFIC_ARTICLE, "neuro.exemplo.org",
        """O autismo, ou Transtorno do Espectro Autista (TEA), envolve diferenças persistentes
        na comunicação social e padrões restritos e repetitivos de comportamento. É comum a
        hiper ou hipossensibilidade sensorial, o stimming e a necessidade de previsibilidade.
        Entre os pontos fortes estão a atenção a detalhes e o pensamento sistemático. O TEA
        frequentemente coocorre com TDAH e com o transtorno do processamento sensorial. A
        avaliação clínica considera os níveis de suporte.""",
    ),
    (
        "https://neuro.exemplo.org/dislexia-leitura",
        "Dislexia: consciência fonológica e dificuldades de leitura",
        SourceType.WEBSITE, "neuro.exemplo.org",
        """A dislexia é um transtorno específico de aprendizagem que afeta a leitura, a
        decodificação e a ortografia, apesar de inteligência preservada. A consciência
        fonológica costuma estar reduzida, com trocas de letras e leitura lenta. Estratégias de
        apoio incluem texto-para-fala, audiolivros e instrução fonológica estruturada. A
        dislexia frequentemente coocorre com discalculia, disgrafia e TDAH.""",
    ),
    (
        "https://neuro.exemplo.org/discalculia-matematica",
        "Discalculia: quando a matemática e o senso numérico falham",
        SourceType.BLOG, "neuro.exemplo.org",
        """A discalculia é um transtorno específico de aprendizagem com prejuízo na matemática.
        Afeta o senso numérico, a memorização de fatos aritméticos e o cálculo. Crianças com
        discalculia confundem símbolos e têm dificuldade com sequências, tempo e dinheiro. O
        uso de manipulativos concretos, calculadora e representações visuais ajuda muito.
        Costuma estar associada à dislexia e ao TDAH.""",
    ),
    (
        "https://neuro.exemplo.org/bipolaridade",
        "Transtorno bipolar: mania, hipomania e episódios depressivos",
        SourceType.SCIENTIFIC_ARTICLE, "neuro.exemplo.org",
        """O transtorno bipolar é um transtorno do humor caracterizado por episódios de mania ou
        hipomania que alternam com episódios depressivos. A regularidade do sono e o
        monitoramento de humor são centrais no manejo. É importante o diagnóstico diferencial
        com o transtorno de personalidade borderline e com o TDAH, pois há sobreposição de
        impulsividade e desregulação emocional. A ansiedade é comorbidade frequente.""",
    ),
    (
        "https://neuro.exemplo.org/borderline-dbt",
        "Personalidade borderline: desregulação emocional e a terapia DBT",
        SourceType.FORUM, "neuro.exemplo.org",
        """O transtorno de personalidade borderline (TPB) envolve desregulação emocional intensa,
        medo de abandono, relações instáveis e impulsividade. A terapia comportamental dialética
        (DBT) e a validação emocional são eficazes. O diagnóstico diferencial inclui transtorno
        bipolar e TEPT complexo. Muitas pessoas relatam empatia intensa e profundidade emocional
        como pontos fortes.""",
    ),
    (
        "https://neuro.exemplo.org/toc-obsessoes",
        "TOC: obsessões, compulsões e a exposição com prevenção de resposta",
        SourceType.WEBSITE, "neuro.exemplo.org",
        """O Transtorno Obsessivo-Compulsivo (TOC) combina obsessões (pensamentos intrusivos) e
        compulsões (rituais repetitivos). O tratamento de referência é a exposição e prevenção
        de resposta (ERP). O TOC coocorre com autismo, TDAH e com a síndrome de Tourette. A
        necessidade de simetria e de certeza é comum.""",
    ),
    (
        "https://neuro.exemplo.org/tourette-tiques",
        "Síndrome de Tourette e transtornos de tique na infância",
        SourceType.SCIENTIFIC_ARTICLE, "neuro.exemplo.org",
        """A síndrome de Tourette é um transtorno do neurodesenvolvimento com múltiplos tiques
        motores e vocais. Há uma urgência premonitória antes do tique e supressão temporária
        possível. A terapia de reversão de hábitos (CBIT) ajuda. Tourette coocorre fortemente
        com TDAH e TOC.""",
    ),
    (
        "https://neuro.exemplo.org/superdotacao-2e",
        "Altas habilidades, superdotação e a dupla excepcionalidade (2e)",
        SourceType.BLOG, "neuro.exemplo.org",
        """As altas habilidades ou superdotação descrevem um potencial notavelmente elevado, com
        aprendizagem rápida, curiosidade intensa e perfeccionismo. Na dupla excepcionalidade (2e),
        a superdotação coexiste com TDAH, dislexia ou autismo, e um pode mascarar o outro. O
        enriquecimento curricular e a mentoria são apoios importantes.""",
    ),
    (
        "https://neuro.exemplo.org/dispraxia-coordenacao",
        "Dispraxia (TDC): coordenação motora e planejamento motor",
        SourceType.WEBSITE, "neuro.exemplo.org",
        """A dispraxia, ou transtorno do desenvolvimento da coordenação, afeta a coordenação
        motora e o planejamento motor. Há desajeitamento, dificuldade com caligrafia e atraso em
        habilidades motoras finas. A terapia ocupacional e a tecnologia assistiva ajudam. Coocorre
        com TDAH, dislexia e disgrafia.""",
    ),
    (
        "https://neuro.exemplo.org/tept-trauma",
        "TEPT: trauma, hipervigilância e terapias focadas no trauma",
        SourceType.SCIENTIFIC_ARTICLE, "neuro.exemplo.org",
        """O Transtorno de Estresse Pós-Traumático (TEPT) surge após um evento traumático, com
        flashbacks, hipervigilância e evitação. Terapias focadas no trauma como EMDR são
        recomendadas. O TEPT coocorre com depressão e ansiedade, e o TEPT complexo tem
        diagnóstico diferencial com o transtorno borderline.""",
    ),
    (
        "https://neuro.exemplo.org/sinestesia-percepcao",
        "Sinestesia: percepção cruzada entre os sentidos",
        SourceType.BLOG, "neuro.exemplo.org",
        """A sinestesia é uma variação perceptiva na qual um sentido evoca experiências em outra
        modalidade — como ver cores ao ouvir sons (sinestesia som-cor) ou associar cores a letras
        e números (grafema-cor). Não é uma doença; muitas pessoas relatam memória associativa e
        criatividade artística. Pode coocorrer com o autismo.""",
    ),
]


def load_sample_articles() -> List[CrawledArticle]:
    """Retorna o corpus de amostra como objetos CrawledArticle."""
    return [_art(url, titulo, tipo, dominio, texto) for url, titulo, tipo, dominio, texto in _DOCS]
