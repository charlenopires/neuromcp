#!/usr/bin/env bash
#
# Expõe o servidor MCP (transporte HTTP) via ngrok, gerando uma URL pública para
# ser usada como CONECTOR MCP remoto — por exemplo, no chat do Mistral AI.
#
# Por que HTTP e não stdio: o servidor MCP padrão fala por stdin/stdout (stdio),
# que NÃO tem porta de rede — o ngrok tuneliza portas HTTP. Por isso subimos o
# servidor em modo Streamable HTTP e apontamos o ngrok para essa porta.
#
# Uso:
#   ./scripts/mcp_ngrok.sh
#
# Variáveis opcionais:
#   NEURO_MCP_PORT   (padrão 8000)   porta local do servidor HTTP
#   NEURO_MCP_PATH   (padrão /mcp)   caminho do endpoint MCP
#   NEURO_MCP_TRANSPORT (padrão http) http (Streamable HTTP) | sse
#   NEURO_EMBEDDING_PROVIDER (padrão auto)
#
# Pré-requisitos:
#   - ngrok instalado e autenticado:  ngrok config add-authtoken <SEU_TOKEN>
#     (crie uma conta grátis em https://dashboard.ngrok.com)
#   - Neo4j no ar (docker compose up -d) e grafo populado (uv run crawler --ingest-samples)
#
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${NEURO_MCP_PORT:-8000}"
MCP_PATH="${NEURO_MCP_PATH:-/mcp}"
TRANSPORT="${NEURO_MCP_TRANSPORT:-http}"
NGROK_API="http://127.0.0.1:4040/api/tunnels"
LOG_SRV="$(mktemp -t neuromcp-http.XXXXXX.log)"
LOG_NGROK="$(mktemp -t neuromcp-ngrok.XXXXXX.log)"

SRV_PID=""
NGROK_PID=""
cleanup() {
  echo
  echo "==> Encerrando (servidor MCP + ngrok)..."
  [ -n "$NGROK_PID" ] && kill "$NGROK_PID" 2>/dev/null || true
  [ -n "$SRV_PID" ]   && kill "$SRV_PID"   2>/dev/null || true
}
trap cleanup EXIT INT TERM

# --- Checagens ---------------------------------------------------------------
command -v ngrok >/dev/null 2>&1 || {
  echo "❌ ngrok não encontrado. Instale: https://ngrok.com/download"
  echo "   e autentique: ngrok config add-authtoken <SEU_TOKEN>"
  exit 1
}
command -v uv >/dev/null 2>&1 || { echo "❌ uv não encontrado (https://astral.sh/uv)"; exit 1; }

# Neo4j no ar? (apenas aviso)
if ! (exec 3<>/dev/tcp/127.0.0.1/7687) 2>/dev/null; then
  echo "⚠️  Neo4j não parece estar no ar em 127.0.0.1:7687."
  echo "    Rode antes:  docker compose up -d   &&   uv run crawler --ingest-samples"
else
  exec 3>&- 2>/dev/null || true
fi

# --- 1) Sobe o servidor MCP em HTTP -----------------------------------------
echo "==> Iniciando servidor MCP (HTTP) em 127.0.0.1:${PORT}${MCP_PATH} ..."
uv run neuro-mcp --transport "$TRANSPORT" --host 127.0.0.1 --port "$PORT" --path "$MCP_PATH" \
  > "$LOG_SRV" 2>&1 &
SRV_PID=$!

# Espera a porta responder (até ~20s)
for _ in $(seq 1 40); do
  if curl -s -o /dev/null "http://127.0.0.1:${PORT}${MCP_PATH}"; then break; fi
  if ! kill -0 "$SRV_PID" 2>/dev/null; then
    echo "❌ O servidor MCP encerrou na inicialização. Log:"; tail -20 "$LOG_SRV"; exit 1
  fi
  sleep 0.5
done
echo "    Servidor no ar (PID $SRV_PID). Log: $LOG_SRV"

# --- 2) Sobe o ngrok apontando para a porta ---------------------------------
echo "==> Abrindo túnel ngrok para a porta ${PORT} ..."
ngrok http "$PORT" --log=stdout > "$LOG_NGROK" 2>&1 &
NGROK_PID=$!

# --- 3) Descobre a URL pública via API local do ngrok (porta 4040) ----------
PUBLIC_URL=""
for _ in $(seq 1 30); do
  PUBLIC_URL="$(curl -s "$NGROK_API" 2>/dev/null | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); sys.exit()
urls = [t.get("public_url","") for t in d.get("tunnels", [])]
https = [u for u in urls if u.startswith("https")]
print(https[0] if https else (urls[0] if urls else ""))
' 2>/dev/null || true)"
  [ -n "$PUBLIC_URL" ] && break
  if ! kill -0 "$NGROK_PID" 2>/dev/null; then break; fi
  sleep 1
done

if [ -z "$PUBLIC_URL" ]; then
  echo "❌ Não consegui obter a URL pública do ngrok. Log:"
  tail -20 "$LOG_NGROK"
  echo
  echo "   Causa comum: authtoken não configurado."
  echo "   Rode:  ngrok config add-authtoken <SEU_TOKEN>   (https://dashboard.ngrok.com)"
  exit 1
fi

MCP_URL="${PUBLIC_URL}${MCP_PATH}"

cat <<BANNER

============================================================================
 ✅ Servidor MCP exposto publicamente

   URL do conector MCP (use esta no Mistral):
       ${MCP_URL}

   Transporte : ${TRANSPORT} (Streamable HTTP)
   Local      : http://127.0.0.1:${PORT}${MCP_PATH}
   Painel ngrok: http://127.0.0.1:4040

 ▶ Como usar no Mistral (Le Chat / La Plateforme):
   1. Abra as configurações de Conectores/MCP.
   2. Adicione um servidor MCP remoto do tipo HTTP (Streamable HTTP).
   3. Cole a URL acima (${MCP_URL}).
   4. As ferramentas ficam disponíveis: responder_com_graphrag, buscar_conceito,
      comorbidades, listar_conceitos, artigos_do_conceito, estatisticas_grafo.

 ⚠️  SEGURANÇA: qualquer pessoa com esta URL pode consultar o servidor
     (que é somente-leitura sobre a ontologia/artigos). A URL do ngrok gratuito
     é pública e efêmera. Encerre o túnel (Ctrl+C) quando terminar.

 Pressione Ctrl+C para encerrar o túnel e o servidor.
============================================================================
BANNER

# Mantém em primeiro plano; o trap encerra tudo ao sair.
wait "$NGROK_PID"
