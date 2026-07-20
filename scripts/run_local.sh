#!/usr/bin/env bash
# Sobe o Neo4j, instala deps, popula o grafo (corpus offline) e faz uma consulta GraphRAG.
# Uso: ./scripts/run_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/4 Subindo Neo4j (docker compose)"
docker compose up -d

echo "==> 2/4 Aguardando Neo4j ficar saudável..."
for i in $(seq 1 30); do
  if docker compose exec -T neo4j cypher-shell -u neo4j -p neurodivergencia123 "RETURN 1" >/dev/null 2>&1; then
    echo "    Neo4j pronto."
    break
  fi
  sleep 3
  [ "$i" = "30" ] && { echo "    Timeout aguardando Neo4j"; exit 1; }
done

echo "==> 3/4 Instalando dependências (com extras mcp)"
uv sync --extra mcp
# Para embeddings semânticos (opcional, baixa torch/modelo):
#   uv sync --extra embeddings && export NEURO_EMBEDDING_PROVIDER=sentence-transformers

echo "==> 4/4 Semeando ontologia + ingerindo corpus de amostra"
uv run crawler --ingest-samples

echo
echo "==> Consulta GraphRAG de exemplo:"
uv run crawler --graphrag "Quais as comorbidades do TDAH e como diferenciar de bipolaridade?"

echo
echo "Pronto. Neo4j Browser: http://localhost:7474  (neo4j / neurodivergencia123)"
echo "Servidor MCP: uv run neuro-mcp"
