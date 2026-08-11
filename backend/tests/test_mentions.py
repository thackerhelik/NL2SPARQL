import os

import pytest
from rdflib import URIRef

from src.internal.mentions import context as context_mod
from src.internal.mentions import extraction as extraction_mod
from src.internal.mentions import generation as generation_mod
from src.internal.mentions import ranking as ranking_mod
from src.internal.mentions.agent import (
    MentionState,
    _state_to_detailed_mentions,
    create_mention,
    delete_mention,
    edit_mention,
    mention_status,
)
from src.internal.schema_cache import SCHEMA_CACHE
from src.routers import mentions as mentions_router
from src.schemas.mentions import Candidate, CandidateVariant, Mention, OneHopTriple
from src.schemas.schema_index import SchemaIndex

from .conftest import OLLAMA_MODEL


@pytest.mark.asyncio
async def test_mentions_extraction(client, persons_schema_id, monkeypatch):
    index = SCHEMA_CACHE.get(persons_schema_id)
    assert index is not None

    type_iri = "http://schema.org/Person"
    pred_iri = "http://schema.org/givenName"

    calls = {"chat": 0, "process": 0}

    async def fake_chat_message(*args, **kwargs):
        calls["chat"] += 1
        return type(
            "MentionResponse",
            (),
            {
                "mentions": [
                    Mention(text="Marie", type=type_iri, label_pred=pred_iri, attrs={})
                ]
            },
        )()

    if os.getenv("LLM_MOCK", "1") != "0":
        monkeypatch.setattr(extraction_mod, "chat_message", fake_chat_message)

    async def fake_process(*args, **kwargs):
        calls["process"] += 1

    monkeypatch.setattr(mentions_router, "process_mention", fake_process)

    payload = {
        "query": "Who is the son of Marie?",
        "schema_id": persons_schema_id,
        "model": OLLAMA_MODEL,
        "limit": 5,
    }
    resp = client.post("/mentions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["text"] == "Marie"
    assert data[0]["type"] == type_iri
    assert data[0]["label_pred"] == pred_iri
    if os.getenv("LLM_MOCK", "1") != "0":
        assert calls["chat"] == 1
        assert calls["process"] == 1


@pytest.mark.asyncio
async def test_get_candidates_groups_variants(kg_graph, persons_schema_id):
    idx = SCHEMA_CACHE.get(persons_schema_id)
    assert idx is not None

    type_iri = "http://schema.org/Person"
    pred_iri = "http://schema.org/givenName"

    mention = Mention(text="Marie", type=type_iri, label_pred=pred_iri)
    candidates = await generation_mod.get_candidates_with_fallback(
        idx, mention, limit=10
    )

    assert any(c.uri == "http://mydb.org/id/1" for c in candidates)
    assert len(candidates[0].variants) == 1


@pytest.mark.asyncio
async def test_onehop_readable_parses_rows():
    idx = SchemaIndex(endpoint="http://example.org/sparql")
    entity_iri = URIRef("http://mydb.org/id/1")

    triples = await context_mod.onehop_readable(idx, str(entity_iri), limit_each=200)

    assert any(
        t.p == "http://schema.org/givenName" and t.value == "Marie" for t in triples
    )
    assert any(
        t.p == "http://www.w3.org/2000/01/rdf-schema#label"
        and t.value == "Mirzan Marie"
        for t in triples
    )


def test_bm25_score_orders_candidates():
    idx = SchemaIndex(namespaces={"ex": "http://example.org/"})
    c1 = Candidate(
        uri="http://example.org/a",
        variants=[
            CandidateVariant(uri="http://example.org/a", pred="p", label="Graph")
        ],
        context=[OneHopTriple(p="ex:label", value="Graph database")],
    )
    c2 = Candidate(
        uri="http://example.org/b",
        variants=[
            CandidateVariant(uri="http://example.org/b", pred="p", label="Other")
        ],
        context=[OneHopTriple(p="ex:label", value="Unrelated")],
    )
    c3 = Candidate(
        uri="http://example.org/c",
        variants=[
            CandidateVariant(uri="http://example.org/c", pred="p", label="Extra")
        ],
        context=[OneHopTriple(p="ex:label", value="Nothing")],
    )

    ranked = ranking_mod.bm25_score(idx, ["graph", "database"], [c2, c1, c3])
    assert ranked[0].uri == "http://example.org/a"
    assert ranked[0].score is not None


@pytest.mark.asyncio
async def test_flat_mention_tools_and_status_indexes():
    state = MentionState()

    created = await create_mention(
        state=state,
        text="Marie",
        type_curie="schema:Person",
        label_pred="schema:givenName",
    )
    assert created["mention_id"] == 0
    assert created["status"]["mention_indexes"] == [0]

    created_second = await create_mention(
        state=state,
        text="Bob",
        type_curie="schema:Person",
        label_pred="schema:givenName",
        attrs={"lang": "en"},
    )
    assert created_second["status"]["mention_indexes"] == [0, 1]

    edited = await edit_mention(
        state=state,
        mention_id=0,
        text="Marie Curie",
        type_curie="schema:Person",
        label_pred="schema:name",
    )
    assert edited["mention_id"] == 0
    assert edited["status"]["mention_indexes"] == [0, 1]
    assert edited["status"]["mentions"][0]["text"] == "Marie Curie"

    status = await mention_status(state=state)
    assert status["mention_indexes"] == [0, 1]
    assert [row["mention_id"] for row in status["mentions"]] == [0, 1]
    assert status["mentions"][0]["text"] == "Marie Curie"

    detailed_mentions = _state_to_detailed_mentions(state)
    assert detailed_mentions[1].attrs == {"lang": "en"}


@pytest.mark.asyncio
async def test_delete_mention_reindexes_candidates_and_normalizes_null_label_pred():
    state = MentionState(
        mentions=[
            {"text": "drop", "type": "schema:Person", "label_pred": "schema:name"},
            {
                "text": "keep",
                "type": "schema:Person",
                "label_pred": None,
                "attrs": None,
            },
        ],
        candidates_by_mention_id={1: [{"idx": 0, "uri": "schema:Keep"}]},
    )

    deleted = await delete_mention(state=state, mention_id=0)
    assert deleted["deleted"] is True
    assert deleted["mention_id"] == 0
    assert deleted["status"]["mention_indexes"] == [0]
    assert state.candidates_by_mention_id == {0: [{"idx": 0, "uri": "schema:Keep"}]}

    status = await mention_status(state=state)
    assert status["mention_indexes"] == [0]
    assert status["mentions"][0]["mention_id"] == 0
    assert status["mentions"][0]["label_pred"] == ""

    detailed_mentions = _state_to_detailed_mentions(state)
    assert detailed_mentions[0].label_pred == ""
