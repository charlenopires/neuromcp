"""
Testes do servidor MCP — foco na robustez do transporte stdio a linhas em branco.

Regressão do erro: `Invalid JSON: EOF while parsing a value ... input_value='\\n'`
seguido de `Internal Server Error`, causado por linhas vazias no stdin.
Requer o extra `mcp` (auto-skip se ausente).
"""

import asyncio
import json
import subprocess
import sys

import pytest

pytest.importorskip("mcp")  # servidor MCP requer `uv sync --extra mcp`

from mcp_server.server import _StdinSemLinhasVazias  # noqa: E402


def test_registra_tools_resources_prompts():
    """O servidor deve expor os 3 primitivos MCP: tools, resources (+template) e prompts."""
    from mcp_server import server as srv

    async def _coletar():
        return (
            await srv.mcp.list_tools(),
            await srv.mcp.list_resources(),
            await srv.mcp.list_resource_templates(),
            await srv.mcp.list_prompts(),
        )

    tools, resources, templates, prompts = asyncio.run(_coletar())
    assert {
        "responder_com_graphrag", "buscar_conceito", "comorbidades",
        "listar_conceitos", "artigos_do_conceito", "estatisticas_grafo",
    } <= {t.name for t in tools}
    assert len(resources) >= 4
    assert any("{concept_id}" in t.uriTemplate for t in templates)
    assert {"explicar_neurodivergencia", "comparar_neurodivergencias"} <= {p.name for p in prompts}


def test_filtro_descarta_linhas_vazias():
    async def fonte():
        for linha in ["\n", "   \n", '{"a":1}\n', "\t\n", '{"b":2}\n']:
            yield linha

    async def coletar():
        return [linha async for linha in _StdinSemLinhasVazias(fonte())]

    assert asyncio.run(coletar()) == ['{"a":1}\n', '{"b":2}\n']


def test_stdio_ignora_linhas_em_branco_no_handshake():
    """Linhas em branco antes do initialize não podem gerar 'Invalid JSON'."""
    init = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "teste", "version": "0"},
        },
    }
    payload = "\n\n   \n" + json.dumps(init) + "\n"

    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        out, err = proc.communicate(payload, timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()

    assert "Invalid JSON" not in err
    assert "Internal Server Error" not in err

    linhas = [l for l in out.splitlines() if l.strip()]
    assert linhas, "servidor não respondeu ao initialize"
    for l in linhas:  # stdout deve ser 100% JSON válido (sem poluição)
        json.loads(l)
    assert "result" in json.loads(linhas[0])
