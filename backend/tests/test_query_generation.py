import json
import os
from pathlib import Path

import pytest

import src.internal.queryGeneration.tool_calling_loop as loop_mod
from src.schemas.query_generation import (
    LinkedMention,
    LinkedMentions,
    RequestQueryGeneration,
)


@pytest.mark.asyncio
async def test_full_query_generation_flow(client, persons_schema_id, monkeypatch):
    """
    Testet den kompletten Flow:
    Request -> Prompt Construction -> Tool Loop Mock -> Final SPARQL Query
    """

    # Mock the shared chat_message helper used by the tool loop.
    async def fake_chat_message(*args, **kwargs):
        return {
            "role": "assistant",
            "content": "SELECT ?s WHERE { ?s <http://schema.org/givenName> 'Marie' }",
            "tool_calls": None,
        }

    monkeypatch.setattr(loop_mod, "chat_message", fake_chat_message)

    # 2. Payload bauen (deine Struktur)
    mention = LinkedMention(
        text="Marie",
        type="http://schema.org/Person",
        label_pred="http://schema.org/givenName",
        attrs={},
        iri="http://mydb.org/id/1",
    )

    mentions = LinkedMentions(mentions=[mention])

    request_data = RequestQueryGeneration(
        question="Find Marie in the database.",
        mentions=mentions,
        schema_id=persons_schema_id,  # Wichtig für den Cache-Lookup deines Partners
        model="gpt-oss:120b",
    )

    # 3. Request an den Router schicken
    payload = request_data.model_dump(mode="json")

    # Wir nutzen den Pfad /generation/ (wie vorhin besprochen)
    response = client.post("/generation", json=payload)

    # 4. Assertions
    assert response.status_code == 200
    data = response.json()

    # Prüfen, ob das "generierte" SPARQL ankommt
    assert "SELECT ?s" in data["query"]
    assert "Marie" in data["query"]


@pytest.mark.asyncio
async def test_generation_router_integration(client, schema_id, monkeypatch):
    # 0. Load data from JSON
    file_path = Path(__file__).parent / "data" / "query_generation_test_data.json"
    with open(file_path) as f:
        data_list = json.load(f)

    test_entry = data_list[0]
    json_mention = test_entry["mentions"][0]

    # 1. The expected result
    expected_sparql = (
        "PREFIX dblp: <https://dblp.org/rdf/schema#>\n"
        "SELECT ?publication WHERE {\n"
        "  ?publication dblp:authoredBy <https://dblp.org/pid/43/7940> .\n"
        "}"
    )

    # 2. Setup Mocking or Real Execution check
    is_mock = os.getenv("LLM_MOCK", "0") == "1"
    calls = {"ollama": 0}

    if is_mock:
        mock_responses = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "list_classes", "arguments": {}},
                    }
                ],
            },
            {
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
            },
            {"role": "assistant", "content": expected_sparql},
        ]

        async def fake_chat_message(*args, **kwargs):
            idx = calls["ollama"]
            calls["ollama"] += 1
            return mock_responses[min(idx, len(mock_responses) - 1)]

        monkeypatch.setattr(loop_mod, "chat_message", fake_chat_message)

    # 3. Build Payload from JSON data
    mention = LinkedMention(
        text=json_mention["text"],
        type=json_mention["type"],
        label_pred=json_mention["label_pred"],
        attrs=json_mention.get("attrs", {}),
        iri=json_mention.get("iri"),
    )

    mentions = LinkedMentions(mentions=[mention])

    request_payload = RequestQueryGeneration(
        question=test_entry["question"],
        mentions=mentions,
        schema_id=schema_id,
        model="gpt-oss:120b",
    )

    # 4. Send the Request to the ROUTER
    response = client.post("/generation", json=request_payload.model_dump(mode="json"))

    # 5. Verification
    assert response.status_code == 200
    data = response.json()

    if is_mock:
        assert data["query"].strip() == expected_sparql.strip()
        assert calls["ollama"] > 0
    else:
        # Generic assertions for real LLM output
        generated_query = data["query"]
        assert "SELECT" in generated_query
        assert "WHERE" in generated_query
        assert "https://dblp.org/pid/43/7940" in generated_query
