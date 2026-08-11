import io
from pathlib import Path
from uuid import uuid4

from src.internal.schema_cache import SCHEMA_CACHE
from src.internal.schema_index import render_prefixes_for_query
from src.schemas.schema_index import SchemaIndex


def _create_temp_schema() -> str:
    schema_path = Path(__file__).parent / "data" / "dblp_schema.xml"
    schema_id = f"TMP_{uuid4().hex[:10]}"
    meta = SCHEMA_CACHE.put(
        schema_path.read_bytes(),
        schema_id=schema_id,
        name="Temp Schema",
        endpoint="http://example.org/sparql",
        base_iri="https://dblp.org/rdf/schema#",
        rdf_format="xml",
    )
    return meta.schema_id


def test_schema_upload(client):
    schema_path = Path(__file__).parent / "data" / "dblp_schema.xml"
    files = {
        "schema_file": (
            "dblp_schema.xml",
            io.BytesIO(schema_path.read_bytes()),
            "application/rdf+xml",
        ),
    }
    data = {
        "endpoint_url": "http://example.org/sparql",
        "name": "DBLP",
        "base_iri": "https://dblp.org/rdf/schema#",
        "rdf_format": "xml",
        "examples_json": '[{"question":"Q1","sparql":"ASK { ?s ?p ?o }"}]',
    }

    resp = client.post("/schema/upload", files=files, data=data)
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["name"] == "DBLP"
    assert "schema_id" in payload
    schema_id = payload["schema_id"]
    settings_resp = client.get(f"/schema/{schema_id}")
    assert settings_resp.status_code == 200
    assert settings_resp.json()["examples"] == [
        {"question": "Q1", "sparql": "ASK { ?s ?p ?o }"}
    ]
    SCHEMA_CACHE.delete(schema_id)


def test_schema_upload_invalid_examples_json_returns_400(client):
    schema_path = Path(__file__).parent / "data" / "dblp_schema.xml"
    files = {
        "schema_file": (
            "dblp_schema.xml",
            io.BytesIO(schema_path.read_bytes()),
            "application/xml",
        )
    }
    data = {
        "endpoint": "https://sparql.dblp.org/sparql",
        "name": "DBLP",
        "base_iri": "https://dblp.org/rdf/schema#",
        "rdf_format": "xml",
        "examples_json": '[{"question":"","sparql":"ASK { ?s ?p ?o }"}]',
    }

    resp = client.post("/schema/upload", files=files, data=data)
    assert resp.status_code == 400
    assert "Invalid example payload" in resp.json()["detail"]


def test_schema_list(client, schema_id):
    list_resp = client.get("/schema")
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert any(item["schema_id"] == schema_id for item in listed)


def test_schema_get(client, schema_id):
    get_resp = client.get(f"/schema/{schema_id}")
    assert get_resp.status_code == 200
    payload = get_resp.json()
    assert payload["schema_id"] == schema_id
    assert payload["name"] == "DBLP"
    assert payload["endpoint"] == "https://sparql.dblp.org/sparql"
    assert isinstance(payload["examples"], list)


def test_schema_data_get(client, schema_id):
    resp = client.get(f"/schema/{schema_id}/data")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["endpoint"] == "https://sparql.dblp.org/sparql"
    assert "namespaces" in payload


def test_schema_get_with_examples(client):
    schema_id = _create_temp_schema()
    try:
        patch_resp = client.patch(
            f"/schema/{schema_id}",
            json={
                "examples": [
                    {
                        "question": "Q",
                        "sparql": "ASK { ?s ?p ?o }",
                    }
                ]
            },
        )
        assert patch_resp.status_code == 200

        resp = client.get(f"/schema/{schema_id}")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["schema_id"] == schema_id
        assert payload["name"] == "Temp Schema"
        assert payload["endpoint"] == "http://example.org/sparql"
        assert payload["examples"] == [{"question": "Q", "sparql": "ASK { ?s ?p ?o }"}]
    finally:
        SCHEMA_CACHE.delete(schema_id)


def test_schema_patch_updates_metadata_and_examples(client):
    schema_id = _create_temp_schema()
    try:
        patch_payload = {
            "name": "Updated Temp",
            "endpoint": "http://localhost:3030/test/query",
            "examples": [
                {
                    "question": "Which creators exist?",
                    "sparql": "SELECT ?creator WHERE { ?pub <https://dblp.org/rdf/schema#authoredBy> ?creator } LIMIT 5",
                }
            ],
        }
        resp = client.patch(f"/schema/{schema_id}", json=patch_payload)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["name"] == "Updated Temp"
        assert payload["endpoint"] == "http://localhost:3030/test/query"
        assert len(payload["examples"]) == 1
        assert payload["examples"][0]["question"] == "Which creators exist?"

        list_resp = client.get("/schema")
        assert list_resp.status_code == 200
        listed = list_resp.json()
        updated = next(item for item in listed if item["schema_id"] == schema_id)
        assert updated["endpoint"] == "http://localhost:3030/test/query"
    finally:
        SCHEMA_CACHE.delete(schema_id)


def test_schema_delete_and_not_found(client):
    schema_id = _create_temp_schema()

    delete_resp = client.delete(f"/schema/{schema_id}")
    assert delete_resp.status_code == 204

    settings_resp = client.get(f"/schema/{schema_id}")
    assert settings_resp.status_code == 404


def test_pinned_schema_delete_returns_403(client):
    schema_path = Path(__file__).parent / "data" / "dblp_schema.xml"

    SCHEMA_CACHE.pin("DBLP")
    SCHEMA_CACHE.put(
        schema_path.read_bytes(),
        schema_id="DBLP",
        name="DBLP",
        endpoint="https://sparql.dblp.org/sparql",
        base_iri="https://dblp.org/rdf/schema#",
        rdf_format="xml",
    )

    delete_resp = client.delete("/schema/DBLP")
    assert delete_resp.status_code == 403
    assert "pinned" in delete_resp.json()["detail"].lower()


def test_render_prefixes_for_query_includes_default_prefix():
    ctx = SchemaIndex(
        namespaces={
            "": "https://pokemonkg.org/ontology#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        }
    )

    prefixes = render_prefixes_for_query(
        ctx,
        "SELECT * WHERE { VALUES ?cls { :Species } VALUES ?p { rdfs:label } }",
    )

    assert "PREFIX : <https://pokemonkg.org/ontology#>" in prefixes
    assert "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>" in prefixes
