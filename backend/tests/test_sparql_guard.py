import pytest

from src.internal.sparql import DisallowedQueryTypeError, validate_query
from src.routers import run_query as run_query_router
from src.schemas.run_query import RunQueryResponse, SparqlHead, SparqlResults


def test_validate_query_accepts_select():
    query = "SELECT ?s WHERE { ?s ?p ?o }"
    assert validate_query(query) == query


def test_validate_query_rejects_construct():
    query = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
    with pytest.raises(DisallowedQueryTypeError):
        validate_query(query)


def test_validate_query_rejects_delete_as_disallowed_form():
    query = "PREFIX ex: <http://example.org/>\nDELETE WHERE { ?s ?p ?o }"
    with pytest.raises(DisallowedQueryTypeError) as exc_info:
        validate_query(query)
    assert "DELETE" in str(exc_info.value)


def test_run_query_rejects_construct_form(client):
    response = client.post(
        "/queries/run",
        json={
            "endpoint_url": "https://sparql.dblp.org/sparql",
            "query": "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
        },
    )

    assert response.status_code == 403
    assert "CONSTRUCT" in response.json()["detail"]


def test_run_query_rejects_delete_form(client):
    response = client.post(
        "/queries/run",
        json={
            "endpoint_url": "https://sparql.dblp.org/sparql",
            "query": ("PREFIX ex: <http://example.org/>\nDELETE WHERE { ?s ?p ?o }"),
        },
    )

    assert response.status_code == 403
    assert "DELETE" in response.json()["detail"]


def test_run_query_keeps_malformed_select_as_syntax_error(client):
    response = client.post(
        "/queries/run",
        json={
            "endpoint_url": "https://sparql.dblp.org/sparql",
            "query": "SELECT WHERE { ?s ?p ?o }",
        },
    )

    assert response.status_code == 400
    assert "SPARQL Syntax Error" in response.json()["detail"]


def test_run_query_accepts_allowed_form(client, monkeypatch):
    async def _mock_run(*args, **kwargs):
        return RunQueryResponse(
            head=SparqlHead(vars=["s"]),
            results=SparqlResults(
                bindings=[{"s": {"type": "uri", "value": "http://x"}}]
            ),
        )

    monkeypatch.setattr(run_query_router, "run", _mock_run)

    response = client.post(
        "/queries/run",
        json={
            "endpoint_url": "https://sparql.dblp.org/sparql",
            "query": "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1",
        },
    )

    assert response.status_code == 200
