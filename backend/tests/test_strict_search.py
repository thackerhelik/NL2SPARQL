import pytest

from src.internal.mentions import generation as generation_mod
from src.internal.schema_cache import SCHEMA_CACHE
from src.schemas.mentions import Mention


@pytest.mark.asyncio
async def test_name_search(persons_schema_id):
    idx = SCHEMA_CACHE.get(persons_schema_id)
    assert idx is not None

    type_iri = "http://schema.org/Person"
    pred_iri = "http://www.w3.org/2000/01/rdf-schema#label"

    mention = Mention(text="Mirzan Marie", type=type_iri, label_pred=pred_iri)
    candidates = await generation_mod.get_candidates_with_fallback(
        idx, mention, limit=10
    )

    # This is expected to FAIL with current implementation because "S. C. Ewing" is not in "Rev'd Dr. S C Ewing"
    assert any("Mirzan Marie" in c.variants[0].label for c in candidates), (
        f"Should find Mirzan Marie for 'Mirzan Marie', found: {[c.variants[0].label for c in candidates]}"
    )


@pytest.mark.asyncio
async def test_abbreviated_name_search(persons_schema_id):
    idx = SCHEMA_CACHE.get(persons_schema_id)
    assert idx is not None

    type_iri = "http://schema.org/Person"
    pred_iri = "http://www.w3.org/2000/01/rdf-schema#label"

    # Case 1: Search "S. C. Ewing" for "Rev'd Dr. S C Ewing"
    mention = Mention(text="S. C. Ewing", type=type_iri, label_pred=pred_iri)
    candidates = await generation_mod.get_candidates_with_fallback(
        idx, mention, limit=10
    )

    # This is expected to FAIL with current implementation because "S. C. Ewing" is not in "Rev'd Dr. S C Ewing"
    assert any("Ewing" in c.variants[0].label for c in candidates), (
        f"Should find Ewing for 'S. C. Ewing', found: {[c.variants[0].label for c in candidates]}"
    )


@pytest.mark.asyncio
async def test_reversed_name_search(persons_schema_id):
    idx = SCHEMA_CACHE.get(persons_schema_id)
    assert idx is not None

    type_iri = "http://schema.org/Person"
    pred_iri = "http://www.w3.org/2000/01/rdf-schema#label"

    # Case 2: Search "Marie Mirzan" for "Mirzan Marie"
    mention = Mention(text="Marie Mirzan", type=type_iri, label_pred=pred_iri)
    candidates = await generation_mod.get_candidates_with_fallback(
        idx, mention, limit=10
    )

    # This might also fail if it's strict CONTAINS on the whole string
    assert any("Mirzan Marie" in c.variants[0].label for c in candidates), (
        f"Should find 'Mirzan Marie' for 'Marie Mirzan', found: {[c.variants[0].label for c in candidates]}"
    )
