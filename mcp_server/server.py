"""
Servidor MCP (Model Context Protocol) que expõe o GraphRAG de neurodivergência.

Ferramentas (todas somente-leitura sobre o Neo4j):
  - responder_com_graphrag : recupera contexto híbrido (grafo + vetor + fulltext)
  - buscar_conceito        : resolve um termo e devolve a vizinhança ontológica
  - comorbidades           : comorbidades frequentes de um conceito
  - listar_conceitos       : lista conceitos (opcionalmente por categoria)
  - artigos_do_conceito    : artigos coletados que mencionam um conceito
  - estatisticas_grafo     : contagens de nós e arestas

Execução:
    uv sync --extra mcp
    uv run neuro-mcp                 # transporte stdio (para clientes MCP)

Conexão via variáveis de ambiente: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
NEURO_EMBEDDING_PROVIDER (auto|sentence-transformers|ollama|hashing).
"""

from __future__ import annotations

import logging
import os
import sys
from io import TextIOWrapper
from typing import Any, Dict, List, Optional

from crawler.database import Neo4jRepository
from crawler.ontology import OntologyManager, normalize_text
from graphrag.retriever import GraphRAGRetriever

logger = logging.getLogger("neuromcp.mcp")

try:
    import anyio
    from mcp.server.fastmcp import FastMCP
    from mcp.server.stdio import stdio_server
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "Pacote MCP ausente. Instale o extra: `uv sync --extra mcp`."
    ) from e


mcp = FastMCP("neuromcp-graphrag")

# Recursos compartilhados (conexão preguiçosa: o servidor sobe mesmo com Neo4j offline)
_repo: Optional[Neo4jRepository] = None
_ontology: Optional[OntologyManager] = None
_retriever: Optional[GraphRAGRetriever] = None


def _get_retriever() -> GraphRAGRetriever:
    global _repo, _ontology, _retriever
    if _retriever is None:
        _repo = Neo4jRepository()
        _ontology = OntologyManager()
        _retriever = GraphRAGRetriever(repo=_repo, ontology_mgr=_ontology)
    return _retriever


def _resolve_concept_id(termo: str) -> Optional[str]:
    """Resolve um termo livre (id, rótulo, sigla ou sinônimo) para um id de conceito."""
    ont = _get_retriever().ontology_mgr
    if termo in ont.conceitos:
        return termo
    alvo = normalize_text(termo)
    for cid, c in ont.conceitos.items():
        candidatos = [c.rotuloPt, c.rotuloEn, *c.sigla, *c.sinonimos]
        if any(alvo == normalize_text(x) for x in candidatos if x):
            return cid
    # fallback: contido no rótulo
    for cid, c in ont.conceitos.items():
        if alvo and alvo in normalize_text(c.rotuloPt):
            return cid
    return None


@mcp.tool()
def responder_com_graphrag(
    pergunta: str,
    top_k_chunks: int = 6,
    top_k_conceitos: int = 5,
) -> Dict[str, Any]:
    """
    Recupera contexto para responder uma pergunta sobre neurodivergência usando GraphRAG
    (ancoragem na ontologia + busca vetorial + fulltext + expansão no grafo de conhecimento).

    Retorna os conceitos relevantes com sua vizinhança (comorbidades, domínios, diagnóstico
    diferencial), as evidências textuais dos artigos coletados e um 'contextoFormatado'
    pronto para o modelo redigir a resposta final citando as fontes.
    """
    try:
        result = _get_retriever().retrieve(
            pergunta, top_k_chunks=top_k_chunks, top_k_concepts=top_k_conceitos
        )
        return result.model_dump()
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e), "dica": "Neo4j está no ar? Ontologia semeada? (docker compose up -d)"}


@mcp.tool()
def buscar_conceito(termo: str) -> Dict[str, Any]:
    """
    Resolve um termo (id, rótulo, sigla ou sinônimo — ex.: 'TDAH', 'autismo', 'nd:dislexia')
    e devolve o conceito com sua vizinhança no grafo ontológico.
    """
    cid = _resolve_concept_id(termo)
    if not cid:
        return {"encontrado": False, "termo": termo}
    dados = _get_retriever().expand_concepts([cid]).get(cid)
    if not dados:
        # sem DB: devolve ao menos o que a ontologia local sabe
        c = _get_retriever().ontology_mgr.conceitos[cid]
        return {"encontrado": True, "id": cid, "rotuloPt": c.rotuloPt,
                "definicao": c.definicao, "aviso": "vizinhança do grafo indisponível (Neo4j offline?)"}
    return {"encontrado": True, **dados}


@mcp.tool()
def comorbidades(conceito_id: str) -> List[Dict[str, Any]]:
    """Lista as comorbidades frequentes de um conceito (id ou termo)."""
    cid = _resolve_concept_id(conceito_id) or conceito_id
    dados = _get_retriever().expand_concepts([cid]).get(cid, {})
    return [c for c in dados.get("comorbidades", []) if c]


@mcp.tool()
def listar_conceitos(categoria: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista os conceitos da ontologia, opcionalmente filtrando por id de categoria (ex.: 'cat:aprendizagem')."""
    ont = _get_retriever().ontology_mgr
    saida = []
    for cid, c in ont.conceitos.items():
        if categoria and c.categoria != categoria:
            continue
        saida.append({"id": cid, "rotuloPt": c.rotuloPt, "categoria": c.categoria,
                      "statusInclusao": c.statusInclusao})
    return saida


@mcp.tool()
def artigos_do_conceito(conceito_id: str, limite: int = 10) -> List[Dict[str, Any]]:
    """Artigos coletados pelo crawler que mencionam um conceito, ordenados por confiança."""
    cid = _resolve_concept_id(conceito_id) or conceito_id
    try:
        return _get_retriever().repo.run_read(
            """
            MATCH (a:Artigo)-[r:MENCIONA]->(c:Conceito {id: $cid})
            RETURN a.titulo AS titulo, a.url AS url, r.confianca AS confianca,
                   r.trechosEvidencia AS evidencias
            ORDER BY r.confianca DESC LIMIT $limite
            """,
            cid=cid, limite=limite,
        )
    except Exception as e:  # noqa: BLE001
        return [{"erro": str(e)}]


@mcp.tool()
def estatisticas_grafo() -> Dict[str, Any]:
    """Contagens de nós (Conceito, Categoria, Artigo, Chunk...) e arestas do grafo."""
    try:
        repo = _get_retriever().repo
        nos = repo.run_read(
            "MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS total ORDER BY total DESC"
        )
        arestas = repo.run_read(
            "MATCH ()-[r]->() RETURN type(r) AS tipo, count(*) AS total ORDER BY total DESC"
        )
        return {"nos": nos, "arestas": arestas}
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e), "dica": "Neo4j está no ar? (docker compose up -d)"}


# ---------------------------------------------------------------------------
# Rotas HTTP auxiliares (usadas apenas no modo --transport http/sse).
# Objetivo: evitar 404 confusos quando um NAVEGADOR ou um BOT de varredura
# acessa a raiz. O endpoint MCP real é sempre o de --path (padrão /mcp).
# Requisições a /.git/*, /security.txt etc. são scanners automáticos da internet
# e DEVEM continuar recebendo 404 (o servidor não expõe nada nesses caminhos).
# ---------------------------------------------------------------------------

@mcp.custom_route("/", methods=["GET"])
async def _raiz(request: Request) -> Response:
    caminho = mcp.settings.streamable_http_path
    return JSONResponse({
        "servico": "neuromcp-graphrag",
        "tipo": "Servidor MCP (Model Context Protocol) — Streamable HTTP",
        "observacao": (
            "Isto é um endpoint de API MCP, não um site. Configure a URL "
            f"terminada em '{caminho}' no seu cliente MCP (ex.: Mistral Le Chat)."
        ),
        "endpoint_mcp": caminho,
        "health": "/health",
        "ferramentas": [
            "responder_com_graphrag", "buscar_conceito", "comorbidades",
            "listar_conceitos", "artigos_do_conceito", "estatisticas_grafo",
        ],
    })


@mcp.custom_route("/health", methods=["GET"])
async def _health(request: Request) -> Response:
    return JSONResponse({"status": "ok", "servico": "neuromcp-graphrag"})


@mcp.custom_route("/favicon.ico", methods=["GET"])
async def _favicon(request: Request) -> Response:
    return Response(status_code=204)  # sem conteúdo — evita 404 de favicon


class _StdinSemLinhasVazias:
    """
    Envolve o stdin assíncrono e descarta linhas em branco / só-espaço.

    Por quê: no transporte stdio, o parser JSON-RPC do SDK (mcp/server/stdio.py)
    tenta `JSONRPCMessage.model_validate_json(line)` em CADA linha. Uma linha em
    branco ('\\n') vira `Invalid JSON: EOF while parsing a value` e o servidor
    reporta `Internal Server Error`. Filtrar aqui elimina esse erro sem afetar
    nenhuma mensagem válida (JSON-RPC nunca é uma linha vazia).
    """

    def __init__(self, stream: Any):
        self._stream = stream

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        async for line in self._stream:
            if line.strip():
                yield line


def _configurar_logging() -> None:
    """
    TODO log vai para STDERR — NUNCA stdout, que é o canal do protocolo JSON-RPC.
    Escrever qualquer coisa não-JSON no stdout corromperia a comunicação MCP.
    """
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, force=True)
    for ruidoso in ("neuromcp", "neo4j", "httpx", "httpcore"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    # Evita que bibliotecas de embeddings escrevam barras de progresso no stdout.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")


async def _run_stdio() -> None:
    """Roda o servidor sobre stdio com stdin resiliente a linhas em branco."""
    stdin = anyio.wrap_file(TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace"))
    async with stdio_server(stdin=_StdinSemLinhasVazias(stdin)) as (read_stream, write_stream):
        await mcp._mcp_server.run(
            read_stream,
            write_stream,
            mcp._mcp_server.create_initialization_options(),
        )


def _run_http(host: str, port: int, path: str, transport: str) -> None:
    """
    Roda o servidor via HTTP (Streamable HTTP ou SSE) — necessário para acesso
    REMOTO (ex.: túnel ngrok + conector MCP do Mistral). Em HTTP o stdout NÃO é o
    canal do protocolo, então logs normais são seguros.

    Desliga a proteção contra DNS-rebinding porque o Host de entrada é o domínio
    dinâmico do ngrok (não localhost). O servidor é somente-leitura; ainda assim,
    exponha apenas enquanto necessário (ver aviso de segurança no README/script).
    """
    from mcp.server.transport_security import TransportSecuritySettings

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, force=True)
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

    mcp.settings.host = host
    mcp.settings.port = port
    mcp.settings.streamable_http_path = path
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
    logger.warning(
        "MCP HTTP em http://%s:%s%s — proteção DNS-rebinding DESLIGADA (túnel dinâmico). "
        "Servidor read-only; exponha apenas enquanto necessário.",
        host, port, path,
    )
    mcp.run(transport=transport)


def main() -> None:
    """Ponto de entrada do servidor MCP. Padrão: stdio (local). `--transport http` p/ acesso remoto."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="neuro-mcp",
        description="Servidor MCP GraphRAG de neurodivergência (stdio local ou HTTP remoto).",
    )
    parser.add_argument(
        "--transport", choices=["stdio", "http", "sse"],
        default=os.getenv("NEURO_MCP_TRANSPORT", "stdio"),
        help="stdio (padrão, local) | http (Streamable HTTP, p/ ngrok/Mistral) | sse",
    )
    parser.add_argument("--host", default=os.getenv("NEURO_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("NEURO_MCP_PORT", "8000")))
    parser.add_argument("--path", default=os.getenv("NEURO_MCP_PATH", "/mcp"),
                        help="Caminho do endpoint HTTP (padrão /mcp).")
    args = parser.parse_args()

    if args.transport == "stdio":
        _configurar_logging()
        anyio.run(_run_stdio)
    else:
        transporte = "streamable-http" if args.transport == "http" else "sse"
        _run_http(args.host, args.port, args.path, transporte)


if __name__ == "__main__":
    main()
