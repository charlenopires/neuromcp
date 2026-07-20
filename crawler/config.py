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

    # Search Limits
    max_results_per_query: int = 10
    default_confidence_threshold: float = 0.6


settings = Settings()
