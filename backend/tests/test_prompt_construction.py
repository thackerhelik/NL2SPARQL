from types import SimpleNamespace

import src.internal.queryGeneration.prompt_construction as prompt_mod
from src.internal.queryGeneration.prompt_construction import prompt_construction
from src.schemas.query_generation import (
    LinkedMention,
    LinkedMentions,
    PromptExample,
    RequestQueryGeneration,
    SystemPrompt,
    UserPrompt,
)


def test_prompt_construction_basic():
    mention = LinkedMention(
        text="The Hobbit",
        type="book",
        label_pred="title",
        iri="http://example.org/book/TheHobbit",
    )
    mentions = LinkedMentions(mentions=[mention])
    request = RequestQueryGeneration(
        question="Who wrote The Hobbit?",
        mentions=mentions,
        schema_id="",
    )

    user_prompt, system_prompt = prompt_construction(request)

    assert isinstance(system_prompt, SystemPrompt)
    assert isinstance(user_prompt, UserPrompt)
    assert "You are a SPARQL query generator" in system_prompt.query
    assert (
        "You have access to schema exploration tools to discover:"
        in system_prompt.query
    )
    assert "## Guidelines" in system_prompt.query
    assert "Who wrote The Hobbit?" in user_prompt.query
    assert "The Hobbit" in user_prompt.query


def test_prompt_construction_includes_schema_and_additional_examples(monkeypatch):
    mention = LinkedMention(
        text="Attention Is All You Need",
        type="https://dblp.org/rdf/schema#Publication",
        label_pred="https://dblp.org/rdf/schema#title",
        iri="https://dblp.org/rec/journals/corr/VaswaniSPUJGKP17",
    )
    mentions = LinkedMentions(mentions=[mention])

    schema_examples = [
        {
            "question": "Schema example question",
            "sparql": "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1",
        }
    ]
    monkeypatch.setattr(
        prompt_mod.SCHEMA_CACHE,
        "get_meta",
        lambda _schema_id: SimpleNamespace(examples=schema_examples),
    )

    request = RequestQueryGeneration(
        question="Who are the authors of Attention Is All You Need?",
        mentions=mentions,
        schema_id="DBLP",
        examples=[
            PromptExample(
                question="Request example question",
                sparql="ASK { ?s ?p ?o }",
            )
        ],
    )

    user_prompt, system_prompt = prompt_construction(request)

    assert "Schema example question" in system_prompt.query
    assert "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1" in system_prompt.query
    assert "Request example question" in system_prompt.query
    assert "ASK { ?s ?p ?o }" in system_prompt.query
    assert "Attention Is All You Need" in user_prompt.query
