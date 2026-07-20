import argparse
import asyncio
import logging
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from crawler.models import SourceType
from crawler.pipeline import NeuroCrawlerPipeline
from crawler.config import settings

console = Console()


def configure_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )


def main():
    parser = argparse.ArgumentParser(
        description="NeuroMCP Crawler - Coletor e Classificador de Ontologia de Neurodivergência para Neo4j",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--seed-ontology",
        action="store_true",
        help="Importa/Semeia os nós e relações da ontologia JSON no banco Neo4j local."
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        help="Executa a descoberta de URLs via Dorks do Google e raspa as páginas."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Executa a semeadura da ontologia e o crawling completo."
    )
    parser.add_argument(
        "--ingest-samples",
        action="store_true",
        help="Popula o grafo com o corpus de amostra OFFLINE (sem rede) — semeia ontologia + artigos + chunks/embeddings."
    )
    parser.add_argument(
        "--graphrag",
        type=str,
        metavar="PERGUNTA",
        help="Faz uma consulta GraphRAG (recuperação híbrida) e imprime o contexto recuperado."
    )
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Desativa a geração de embeddings/chunks (grafo sem busca vetorial)."
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Consulta/Dork personalizada para buscar conteúdos específicos (ex.: 'autismo feminino')."
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Número máximo de resultados por dork de busca."
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["artigo_cientifico", "blog", "forum", "website"],
        help="Filtra os tipos de fontes a serem buscadas."
    )
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=settings.neo4j_uri,
        help="URI de conexão do Neo4j (ex.: bolt://localhost:7687)."
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=settings.neo4j_user,
        help="Usuário do Neo4j."
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=settings.neo4j_password,
        help="Senha do Neo4j."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Modo detalhado/debug."
    )

    args = parser.parse_args()
    configure_logging(args.verbose)

    console.print(Panel.fit(
        "[bold cyan]NeuroMCP - Crawler de Neurodivergência[/bold cyan]\n"
        "[dim]Busca Otimizada + Ontologia JSON + Neo4j Graph DB[/dim]",
        border_style="cyan"
    ))

    pipeline = NeuroCrawlerPipeline(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        use_embeddings=not args.no_embeddings,
    )

    # --- Modo GraphRAG: recupera contexto e encerra ---
    if args.graphrag:
        from graphrag.retriever import GraphRAGRetriever

        retriever = GraphRAGRetriever(repo=pipeline.db, ontology_mgr=pipeline.ontology_mgr,
                                      embedder=pipeline.embedder)
        result = retriever.retrieve(args.graphrag)
        console.print(Panel.fit(f"[bold]Pergunta:[/bold] {args.graphrag}", border_style="magenta"))
        if result.avisos:
            for av in result.avisos:
                console.print(f"[yellow]Aviso:[/yellow] {av}")
        console.print(f"[bold cyan]Conceitos recuperados:[/bold cyan] "
                      f"{', '.join(f'{c.rotuloPt} ({c.score})' for c in result.conceitos) or '—'}")
        console.print(f"[bold cyan]Evidências (chunks):[/bold cyan] {len(result.chunks)}")
        console.print(Panel(result.contextoFormatado, title="Contexto GraphRAG", border_style="green"))
        return

    # --- Modo ingestão offline (corpus de amostra) ---
    if args.ingest_samples:
        console.print("[bold green]Ingerindo corpus de amostra OFFLINE no Neo4j...[/bold green]")
        try:
            summary = pipeline.ingest_samples(seed_first=True)
        except Exception as e:
            console.print(f"[bold red]Erro na ingestão:[/bold red] {e}")
            console.print("[yellow]Verifique se o Neo4j está no ar: docker compose up -d[/yellow]")
            sys.exit(1)
        table = Table(title="Ingestão Offline (corpus de amostra)", border_style="bright_blue")
        table.add_column("Métrica", style="bold"); table.add_column("Valor", style="cyan")
        table.add_row("Artigos no corpus", str(summary.totalBuscados))
        table.add_row("Processados", str(summary.totalProcessados))
        table.add_row("Salvos no Neo4j", str(summary.totalSalvosNeo4j))
        table.add_row("Erros", str(summary.totalErros))
        console.print(table)
        if summary.conceitosMaisMencionados:
            c_table = Table(title="Conceitos identificados", border_style="green")
            c_table.add_column("Conceito", style="bold magenta"); c_table.add_column("Menções", style="bold green")
            for conceito, count in sorted(summary.conceitosMaisMencionados.items(), key=lambda x: x[1], reverse=True)[:15]:
                c_table.add_row(conceito, str(count))
            console.print(c_table)
        return

    if args.seed_ontology or (args.full and not args.crawl):
        console.print("[bold green]Semeando Ontologia no Neo4j...[/bold green]")
        try:
            pipeline.seed_ontology_to_db()
            console.print("[bold green]Ontologia semeada com sucesso no Neo4j![/bold green]")
        except Exception as e:
            console.print(f"[bold red]Erro ao semear ontologia no Neo4j:[/bold red] {e}")
            console.print("[yellow]Verifique se o Docker Compose está ativo: docker compose up -d[/yellow]")
            sys.exit(1)
            
        if not args.crawl and not args.full:
            return

    if args.crawl or args.full or args.query:
        source_types = None
        if args.sources:
            source_types = [SourceType(s) for s in args.sources]

        custom_queries = [args.query] if args.query else None

        console.print("[bold cyan]Iniciando ciclo de Crawling e Classificação...[/bold cyan]")
        
        summary = asyncio.run(pipeline.run(
            source_types=source_types,
            custom_queries=custom_queries,
            max_results_per_query=args.max_results,
            seed_first=args.full
        ))

        # Tabela de Resultados
        table = Table(title="Resumo do Crawling e Armazenamento Neo4j", border_style="bright_blue")
        table.add_column("Métrica", style="bold")
        table.add_column("Valor", style="cyan")

        table.add_row("URLs Descobertas", str(summary.totalBuscados))
        table.add_row("Páginas Processadas", str(summary.totalProcessados))
        table.add_row("Artigos Salvos no Neo4j", str(summary.totalSalvosNeo4j))
        table.add_row("Erros de Coleta", str(summary.totalErros))

        console.print(table)

        if summary.conceitosMaisMencionados:
            c_table = Table(title="Principais Conceitos da Ontologia Identificados", border_style="green")
            c_table.add_column("Conceito Ontológico", style="bold magenta")
            c_table.add_column("Total Menções Salvas", style="bold green")

            for conceito, count in sorted(summary.conceitosMaisMencionados.items(), key=lambda x: x[1], reverse=True)[:10]:
                c_table.add_row(conceito, str(count))

            console.print(c_table)

    elif not args.seed_ontology:
        parser.print_help()


if __name__ == "__main__":
    main()
