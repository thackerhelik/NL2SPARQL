from __future__ import annotations

from pathlib import Path

import pytest

from src.internal.schema_cache import SchemaCache, preload_from_env


def test_preload_from_env_loads_persons_schema(tmp_path, monkeypatch):
    schema_path = Path(__file__).parent / "data" / "persons_schema.ttl"

    monkeypatch.setenv("PRELOAD_SCHEMAS", "PERSONS")
    monkeypatch.setenv("PERSONS_SCHEMA_PATH", str(schema_path))
    monkeypatch.setenv("PERSONS_ENDPOINT_URL", "http://example.org/sparql")

    cache = SchemaCache(max_items=5, persist_dir=tmp_path)
    metas = preload_from_env(cache)

    assert any(m.schema_id == "PERSONS" for m in metas)
    assert "PERSONS" in cache.pinned_ids
    assert cache.get("PERSONS") is not None


def test_put_with_stable_schema_id_is_idempotent(tmp_path):
    schema_path = Path(__file__).parent / "data" / "persons_schema.ttl"
    data = schema_path.read_bytes()

    cache = SchemaCache(max_items=5, persist_dir=tmp_path)

    m1 = cache.put(
        data,
        schema_id="PERSONS",
        name="Persons",
        endpoint="http://example.org/sparql",
        rdf_format="turtle",
    )
    m2 = cache.put(
        data,
        schema_id="PERSONS",
        name="Persons",
        endpoint="http://example.org/sparql",
        rdf_format="turtle",
    )

    assert m1.schema_id == m2.schema_id == "PERSONS"
    # Second call is a no-op unless overwrite is requested.
    assert cache.get_meta("PERSONS") is not None


@pytest.mark.parametrize("bad_id", ["", "a/b", "a b", "..", "a" * 100])
def test_put_rejects_invalid_schema_ids(tmp_path, bad_id):
    schema_path = Path(__file__).parent / "data" / "persons_schema.ttl"
    data = schema_path.read_bytes()

    cache = SchemaCache(max_items=5, persist_dir=tmp_path)
    with pytest.raises(ValueError):
        cache.put(
            data,
            schema_id=bad_id,
            name="Bad",
            endpoint="http://example.org/sparql",
            rdf_format="turtle",
        )
