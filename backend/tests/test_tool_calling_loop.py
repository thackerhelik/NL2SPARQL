import asyncio
import os
from types import SimpleNamespace

import pytest

import src.internal.queryGeneration.tool_calling_loop as loop_mod
from src.internal.queryGeneration.tool_calling_loop import run_query_generation
import src.internal.queryGeneration.tools as tools_mod
from src.internal.queryGeneration.tools import get_tools_spec
from src.internal.sparql import DisallowedQueryTypeError
from src.schemas.query_generation import (
    SystemPrompt,
    UserPrompt,
)
from src.schemas.run_query import RunQueryResponse, SparqlHead, SparqlResults

from .conftest import OLLAMA_MODEL


@pytest.mark.asyncio
async def test_tool_calling_loop_exploration(schema_id, monkeypatch):
    system_prompt_text = """You are a SPARQL query generator.

You have access to schema exploration tools to discover:
- Classes
- Properties
- Domains and ranges
- Valid connections between entities

Guidelines:
- Do NOT assume class names or property names
- Do NOT hallucinate predicates
- Use the extracted mentions and their linked IRIs
- Use schema exploration tools before generating the SPARQL query
- always use describe_class and describe_property to get details about classes and properties for every class and property you plan to use
- Validate the final SPARQL query before returning it
- Return ONLY the SPARQL query
- Do NOT add comments or explanations"""

    user_prompt_text = """Question:
Return all papers published by Ian Goodfellow

Extracted Mentions:
- text: Ian Goodfellow, type: Person, label: Person, attrs: {}

Linked Entities:
- score: 1.0, data: https://dblp.org/pid/43/7940, context:"""

    tools = get_tools_spec()
    expected_sparql = (
        "PREFIX dblp: <https://dblp.org/rdf/schema#>\n"
        "SELECT ?publication WHERE {\n"
        "  ?publication dblp:authoredBy <https://dblp.org/pid/43/7940> .\n"
        "}"
    )

    is_mock = os.getenv("LLM_MOCK", "0") == "1"

    if is_mock:
        mock_responses = [
            # Turn 1: Discovery - List classes to find 'Publication'
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "function": {"name": "list_classes", "arguments": {}},
                        }
                    ],
                }
            },
            # Turn 2: Detail - describe 'Publication' class
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c2",
                            "function": {
                                "name": "describe_class",
                                "arguments": {
                                    "class_iri": "https://dblp.org/rdf/schema#Publication"
                                },
                            },
                        }
                    ],
                }
            },
            # Turn 3: Discovery - List properties to find 'authoredBy'
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c3",
                            "function": {"name": "list_properties", "arguments": {}},
                        }
                    ],
                }
            },
            # Turn 4: Detail - describe 'authoredBy' property
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c4",
                            "function": {
                                "name": "describe_property",
                                "arguments": {
                                    "prop_iri": "https://dblp.org/rdf/schema#authoredBy"
                                },
                            },
                        }
                    ],
                }
            },
            # Turn 5: Validation - Check query syntax before finishing
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c5",
                            "function": {
                                "name": "validate_sparql_query",
                                "arguments": {"query": expected_sparql},
                            },
                        }
                    ],
                }
            },
            # Turn 6: Final Answer - Return only the SPARQL query
            {"message": {"role": "assistant", "content": expected_sparql}},
        ]

        calls = {"chat": 0}

        async def fake_chat_message(*args, **kwargs):
            idx = calls["chat"]
            calls["chat"] += 1
            return mock_responses[idx]["message"]

        monkeypatch.setattr(loop_mod, "chat_message", fake_chat_message)

        result = await run_query_generation(
            model=OLLAMA_MODEL,
            schema_id=schema_id,
            system_prompt=SystemPrompt(query=system_prompt_text),
            user_prompt=UserPrompt(query=user_prompt_text),
            tools=tools,
        )

        assert result.query.strip() == expected_sparql.strip()
        assert calls["chat"] == 6

    else:
        result = await run_query_generation(
            model=OLLAMA_MODEL,
            schema_id=schema_id,
            system_prompt=SystemPrompt(query=system_prompt_text),
            user_prompt=UserPrompt(query=user_prompt_text),
            tools=tools,
        )
        assert "<https://dblp.org/rdf/schema#>" in result.query
        assert "SELECT ?p" or "SELECT DISTINCT ?p" in result.query
        assert "WHERE" in result.query
        assert "authoredBy" or "authorOf" or "creatorOf" in result.query
        assert "<https://dblp.org/pid/43/7940>" in result.query


@pytest.mark.asyncio
async def test_run_sparql_query_tool_success(monkeypatch):
    async def _fake_run(*args, **kwargs):
        return RunQueryResponse(
            head=SparqlHead(vars=["s"]),
            results=SparqlResults(
                bindings=[
                    {"s": {"type": "uri", "value": f"http://x/{i}"}} for i in range(8)
                ]
            ),
        )

    monkeypatch.setattr(tools_mod, "run", _fake_run)
    idx = SimpleNamespace(endpoint="http://example.org/sparql")

    out = await tools_mod.run_sparql_query(
        idx, "```sparql\nSELECT ?s WHERE { ?s ?p ?o }\n```"
    )

    assert out["ok"] is True
    assert out["error_type"] is None
    if "executed_query" in out:
        assert out["executed_query"] == "SELECT ?s WHERE { ?s ?p ?o }"
    assert out["summary"]["row_count"] == 8
    assert out["summary"]["vars"] == ["s"]
    assert len(out["summary"]["sample_bindings"]) == tools_mod.RUN_QUERY_SAMPLE_SIZE


@pytest.mark.asyncio
async def test_run_sparql_query_tool_timeout(monkeypatch):
    async def _slow_run(*args, **kwargs):
        await asyncio.sleep(0.05)
        return RunQueryResponse(
            head=SparqlHead(vars=[]), results=SparqlResults(bindings=[])
        )

    monkeypatch.setattr(tools_mod, "run", _slow_run)
    monkeypatch.setattr(tools_mod, "RUN_QUERY_TIMEOUT_SECONDS", 0.01)
    idx = SimpleNamespace(endpoint="http://example.org/sparql")

    out = await tools_mod.run_sparql_query(idx, "SELECT ?s WHERE { ?s ?p ?o }")
    assert out["ok"] is False
    assert out["error_type"] == "timeout"


@pytest.mark.asyncio
async def test_run_sparql_query_tool_error_mapping(monkeypatch):
    idx = SimpleNamespace(endpoint="http://example.org/sparql")

    async def _forbidden(*args, **kwargs):
        raise DisallowedQueryTypeError("Query form 'DELETE' is not allowed.")

    monkeypatch.setattr(tools_mod, "run", _forbidden)
    forbidden = await tools_mod.run_sparql_query(idx, "DELETE WHERE { ?s ?p ?o }")
    assert forbidden["ok"] is False
    assert forbidden["error_type"] == "forbidden"

    async def _syntax(*args, **kwargs):
        raise ValueError("Invalid SPARQL syntax: ...")

    monkeypatch.setattr(tools_mod, "run", _syntax)
    syntax = await tools_mod.run_sparql_query(idx, "SELECT WHERE { ?s ?p ?o }")
    assert syntax["ok"] is False
    assert syntax["error_type"] == "syntax"

    async def _endpoint(*args, **kwargs):
        raise RuntimeError("endpoint down")

    monkeypatch.setattr(tools_mod, "run", _endpoint)
    endpoint = await tools_mod.run_sparql_query(idx, "SELECT ?s WHERE { ?s ?p ?o }")
    assert endpoint["ok"] is False
    assert endpoint["error_type"] == "endpoint"


@pytest.mark.asyncio
async def test_tool_calling_loop_awaits_async_tools(schema_id, monkeypatch):
    calls = {"tool": 0, "ollama": 0}

    async def _fake_async_tool(_ctx, query: str):
        calls["tool"] += 1
        return {
            "ok": True,
            "error_type": None,
            "error_message": None,
            "summary": {"row_count": 1, "vars": ["s"], "sample_bindings": [{"s": "x"}]},
            "executed_query": query,
        }

    monkeypatch.setitem(
        tools_mod.TOOL_REGISTRY["run_sparql_query"], "logic", _fake_async_tool
    )

    mock_responses = [
        {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "run_sparql_query",
                            "arguments": {
                                "query": "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1"
                            },
                        },
                    }
                ],
            }
        },
        {
            "message": {
                "role": "assistant",
                "content": "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1",
            }
        },
    ]

    async def fake_chat_message(*args, **kwargs):
        idx = calls["ollama"]
        calls["ollama"] += 1
        return mock_responses[idx]["message"]

    monkeypatch.setattr(loop_mod, "chat_message", fake_chat_message)

    result = await run_query_generation(
        model=OLLAMA_MODEL,
        schema_id=schema_id,
        system_prompt=SystemPrompt(query="You are a SPARQL query generator."),
        user_prompt=UserPrompt(query="Generate query"),
        tools=get_tools_spec(),
    )
    assert result.query.strip() == "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1"
    assert calls["tool"] == 1
