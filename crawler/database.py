import logging
from typing import Optional, Dict, Any, List
from neo4j import GraphDatabase, Driver

from crawler.config import settings
from crawler.models import CrawledArticle
from crawler.ontology import OntologyManager

logger = logging.getLogger("neuromcp.database")


class Neo4jRepository:
    """
    Gerenciador do banco de dados Neo4j local.
    Executa o ETL da ontologia e grava os artigos coletados e rotulados.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self._driver: Optional[Driver] = None

    def connect(self) -> Driver:
        """Conecta ao Neo4j e retorna o driver."""
        if not self._driver:
            logger.info(f"Conectando ao Neo4j em {self.uri} como '{self.user}'...")
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            self._driver.verify_connectivity()
            logger.info("Conexão com Neo4j estabelecida com sucesso!")
        return self._driver

    def close(self) -> None:
        """Fecha a conexão com o banco de dados."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Conexão com Neo4j encerrada.")

    def create_constraints(self) -> None:
        """Cria as restrições de unicidade e índices no Neo4j."""
        driver = self.connect()
        constraints = [
            "CREATE CONSTRAINT conceito_id IF NOT EXISTS FOR (c:Conceito) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT categoria_id IF NOT EXISTS FOR (c:Categoria) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT dominio_id IF NOT EXISTS FOR (d:DominioCognitivo) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT artigo_url IF NOT EXISTS FOR (a:Artigo) REQUIRE a.url IS UNIQUE",
            "CREATE CONSTRAINT fonte_dominio IF NOT EXISTS FOR (f:Fonte) REQUIRE f.dominio IS UNIQUE"
        ]
        with driver.session() as session:
            for query in constraints:
                session.run(query)
        logger.info("Restrições e índices do Neo4j validados.")

    def seed_ontology(self, ontology_mgr: OntologyManager) -> None:
        """
        Importa a estrutura completa da ontologia JSON para o Neo4j.
        Cria os nós de Conceito, Categoria, DominioCognitivo e Codigo, além de todas as arestas.
        """
        self.create_constraints()
        driver = self.connect()
        logger.info("Semeando ontologia de neurodivergência no Neo4j...")

        with driver.session() as session:
            # 1. Domínios Cognitivos
            for d in ontology_mgr.dominios.values():
                session.run(
                    """
                    MERGE (d:DominioCognitivo {id: $id})
                    SET d.rotuloPt = $rotuloPt,
                        d.rotuloEn = $rotuloEn,
                        d.descricao = $descricao
                    """,
                    id=d.id, rotuloPt=d.rotuloPt, rotuloEn=d.rotuloEn, descricao=d.descricao
                )

            # 2. Categorias
            for c in ontology_mgr.categorias.values():
                session.run(
                    """
                    MERGE (cat:Categoria {id: $id})
                    SET cat.rotuloPt = $rotuloPt,
                        cat.rotuloEn = $rotuloEn,
                        cat.descricao = $descricao
                    """,
                    id=c.id, rotuloPt=c.rotuloPt, rotuloEn=c.rotuloEn, descricao=c.descricao
                )
                if c.superClasse:
                    session.run(
                        """
                        MATCH (cat:Categoria {id: $id}), (super:Categoria {id: $superId})
                        MERGE (cat)-[:IS_A]->(super)
                        """,
                        id=c.id, superId=c.superClasse
                    )

            # 3. Conceitos e Códigos
            for conc in ontology_mgr.conceitos.values():
                session.run(
                    """
                    MERGE (c:Conceito {id: $id})
                    SET c.tipoNo = $tipoNo,
                        c.rotuloPt = $rotuloPt,
                        c.rotuloEn = $rotuloEn,
                        c.statusInclusao = $statusInclusao,
                        c.definicao = $definicao,
                        c.sigla = $sigla,
                        c.sinonimos = $sinonimos,
                        c.caracteristicas = $caracteristicas,
                        c.pontosFortes = $pontosFortes,
                        c.beneficiaDe = $beneficiaDe,
                        c.hashtags = $hashtags,
                        c.fontes = $fontes
                    """,
                    id=conc.id, tipoNo=conc.tipoNo, rotuloPt=conc.rotuloPt, rotuloEn=conc.rotuloEn,
                    statusInclusao=conc.statusInclusao, definicao=conc.definicao, sigla=conc.sigla,
                    sinonimos=conc.sinonimos, caracteristicas=conc.caracteristicas,
                    pontosFortes=conc.pontosFortes, beneficiaDe=conc.beneficiaDe,
                    hashtags=conc.hashtags, fontes=conc.fontes
                )

                # Relaciona com Categoria
                if conc.categoria:
                    session.run(
                        """
                        MATCH (c:Conceito {id: $concId}), (cat:Categoria {id: $catId})
                        MERGE (c)-[:IN_CATEGORY]->(cat)
                        """,
                        concId=conc.id, catId=conc.categoria
                    )

                # Relaciona com SuperClasse
                if conc.superClasse:
                    query_rel = "IS_A" if conc.superClasse.startswith("cat:") else "SUBTYPE_OF"
                    session.run(
                        f"""
                        MATCH (c:Conceito {{id: $concId}})
                        MATCH (target {{id: $targetId}})
                        MERGE (c)-[:{query_rel}]->(target)
                        """,
                        concId=conc.id, targetId=conc.superClasse
                    )

                # Relaciona com Domínios Afetados
                for dom_id in conc.dominiosAfetados:
                    session.run(
                        """
                        MATCH (c:Conceito {id: $concId}), (d:DominioCognitivo {id: $domId})
                        MERGE (c)-[:AFFECTS_DOMAIN]->(d)
                        """,
                        concId=conc.id, domId=dom_id
                    )

                # Códigos Clínicos (DSM / CID)
                for sistema, valor in conc.codigos.items():
                    codigo_id = f"cod:{sistema}:{valor}"
                    session.run(
                        """
                        MERGE (cod:Codigo {id: $codigoId})
                        SET cod.sistema = $sistema, cod.valor = $valor
                        WITH cod
                        MATCH (c:Conceito {id: $concId})
                        MERGE (c)-[:CODED_AS]->(cod)
                        """,
                        codigoId=codigo_id, sistema=sistema, valor=valor, concId=conc.id
                    )

            # 4. Relações explícitas (COMORBIDO_COM, DIAG_DIFERENCIAL)
            for rel in ontology_mgr.relacoes:
                tipo_aresta = "COMORBID_WITH" if "COMORBIDO" in rel.tipo else "DIFFERENTIAL_DX"
                session.run(
                    f"""
                    MATCH (origem:Conceito {{id: $origemId}}), (destino:Conceito {{id: $destinoId}})
                    MERGE (origem)-[r:{tipo_aresta}]->(destino)
                    SET r.forca = $forca,
                        r.prevalenciaAprox = $prevalencia,
                        r.nota = $nota
                    """,
                    origemId=rel.origem, destinoId=rel.destino, forca=rel.forca,
                    prevalencia=rel.prevalenciaAprox, nota=rel.nota
                )

        logger.info("Ontologia semeada no Neo4j com sucesso!")

    def save_article(self, article: CrawledArticle) -> bool:
        """
        Salva o artigo lido e suas relações com os conceitos da ontologia no Neo4j.
        """
        if not article.matchesOntologia:
            logger.info(f"Ignorando artigo sem correspondências com ontologia: {article.url}")
            return False

        driver = self.connect()
        with driver.session() as session:
            # Mergear nó da Fonte
            session.run(
                """
                MERGE (f:Fonte {dominio: $dominio})
                SET f.tipoFonte = $tipoFonte
                """,
                dominio=article.dominioFonte, tipoFonte=article.tipoFonte.value
            )

            # Mergear nó do Artigo
            session.run(
                """
                MERGE (a:Artigo {url: $url})
                SET a.titulo = $titulo,
                    a.tipoFonte = $tipoFonte,
                    a.resumo = $resumo,
                    a.dataPublicacao = $dataPublicacao,
                    a.dataColeta = $dataColeta,
                    a.autores = $autores,
                    a.contextosDetectados = $contextos,
                    a.queryBusca = $queryBusca
                WITH a
                MATCH (f:Fonte {dominio: $dominio})
                MERGE (a)-[:PUBLICADO_EM]->(f)
                """,
                url=article.url, titulo=article.titulo, tipoFonte=article.tipoFonte.value,
                resumo=article.resumo, dataPublicacao=article.dataPublicacao,
                dataColeta=article.dataColeta, autores=article.autores,
                contextos=article.contextosDetectados, queryBusca=article.queryBuscaUtilizada,
                dominio=article.dominioFonte
            )

            # Criar conexões com Conceitos Mencionados
            for match in article.matchesOntologia:
                session.run(
                    """
                    MATCH (a:Artigo {url: $url})
                    MATCH (c:Conceito {id: $conceitoId})
                    MERGE (a)-[r:MENCIONA]->(c)
                    SET r.confianca = $confianca,
                        r.termosEncontrados = $termos,
                        r.trechosEvidencia = $snippets
                    """,
                    url=article.url, conceitoId=match.conceitoId,
                    confianca=match.confianca, termos=match.termosEncontrados,
                    snippets=match.trechosEvidencia
                )

                # Conecta também aos Domínios Cognitivos associados a este conceito
                for dom_id in match.dominiosAssociados:
                    session.run(
                        """
                        MATCH (a:Artigo {url: $url})
                        MATCH (d:DominioCognitivo {id: $domId})
                        MERGE (a)-[:RELACIONADO_A_DOMINIO]->(d)
                        """,
                        url=article.url, domId=dom_id
                    )

        logger.info(f"Artigo salvo no Neo4j com {len(article.matchesOntologia)} menções a conceitos: {article.titulo[:50]}...")
        return True
