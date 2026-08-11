from pathlib import Path

from src.internal.mentions.extraction import validate_types
from src.internal.schema_index import is_string_label_pred, load_schema_bytes
from src.schemas.mentions import Mention
from src.schemas.schema_index import SchemaIndex


def _load_idx() -> SchemaIndex:
    data = (Path(__file__).resolve().parent / "data" / "dblp_schema.xml").read_bytes()
    return load_schema_bytes(
        data, base_iri="https://dblp.org/rdf/schema#", rdf_format="xml"
    )


def test_is_string_label_pred_returns_effective_type_for_ancestor_domain():
    idx = _load_idx()

    ok, resolved = is_string_label_pred(idx, "dblp:Person", "dblp:creatorName")
    assert ok is True
    assert resolved == "https://dblp.org/rdf/schema#Creator"


def test_validate_types_updates_type_to_effective_domain_type():
    idx = _load_idx()

    mentions = [
        Mention(
            text="Alice",
            type="dblp:Person",
            label_pred="dblp:creatorName",
            attrs={},
        )
    ]
    out = validate_types(mentions, idx)
    assert len(out) == 1
    assert out[0].type == "https://dblp.org/rdf/schema#Creator"
