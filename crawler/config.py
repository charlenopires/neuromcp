import os
from pathlib import Path
from pydantic import BaseModel, Field


class Settings(BaseModel):
    # Neo4j Settings
    neo4j_uri: str = Field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = Field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = Field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "neurodivergencia123"))

    # Paths
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    ontology_path: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "ontologia" / "ontologia_neurodivergencia.json"
    )

    # Crawler Settings
    max_concurrent_requests: int = 5
    request_timeout_seconds: float = 15.0
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (NeuroMCP Research Bot/1.0)"
    )
    # Verificação TLS LIGADA por padrão. Só desative via NEURO_ALLOW_INSECURE_TLS=1
    # (inseguro — expõe a ataques MITM; use apenas para hosts com certificado problemático).
    tls_verify: bool = Field(
        default_factory=lambda: os.getenv("NEURO_ALLOW_INSECURE_TLS", "0") != "1"
    )

    # Search Limits
    max_results_per_query: int = 10
    default_confidence_threshold: float = 0.6

    # Embeddings / GraphRAG
    # Provedor: "auto" | "sentence-transformers" | "ollama" | "hashing"
    embedding_provider: str = Field(default_factory=lambda: os.getenv("NEURO_EMBEDDING_PROVIDER", "auto"))
    # Dimensão do índice vetorial no Neo4j. DEVE bater com a dim. do provedor escolhido
    # (MiniLM multilíngue=384, nomic-embed-text=768, hashing=384). Ver README.
    embedding_dimension: int = Field(default_factory=lambda: int(os.getenv("NEURO_EMBEDDING_DIM", "384")))
    embedding_similarity: str = "cosine"  # função do índice vetorial nativo do Neo4j

    # Chunking de artigos para recuperação semântica
    chunk_size_chars: int = 900
    chunk_overlap_chars: int = 150

    # Recuperação GraphRAG
    graphrag_top_k_chunks: int = 6
    graphrag_top_k_concepts: int = 5


settings = Settings()
