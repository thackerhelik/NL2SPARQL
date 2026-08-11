from pathlib import Path

from src.internal.queryGeneration import tools as qg_tools
from src.internal.schema_index import (
    expr_to_compact_string,
    load_schema_bytes,
    schema_to_context_string,
)
from src.schemas.schema_index import ClassExpr


def test_load_schema_parses_owl_class_expressions():
    schema_path = Path(__file__).parent / "data" / "owl_logic.ttl"
    idx = load_schema_bytes(schema_path.read_bytes(), rdf_format="turtle")

    ex = "http://example.org/"
    d = idx.classes[ex + "D"]
    e = idx.classes[ex + "E"]
    f = idx.classes[ex + "F"]
    g = idx.classes[ex + "G"]
    h = idx.classes[ex + "H"]
    i = idx.classes[ex + "I"]
    j = idx.classes[ex + "J"]

    assert any(x.kind == "intersection" for x in d.equivalent_class_exprs)
    assert any(x.kind == "union" for x in e.super_class_exprs)
    assert any(x.kind == "complement" for x in f.super_class_exprs)
    assert any(x.kind == "iri" and x.iri == ex + "B" for x in g.disjoint_union_of)
    assert any(x.kind == "iri" and x.iri == ex + "C" for x in g.disjoint_union_of)
    assert any(x.kind == "iri" and x.iri == ex + "A" for x in h.union_of)
    assert any(x.kind == "iri" and x.iri == ex + "A" for x in i.intersection_of)
    assert any(x.kind == "iri" and x.iri == ex + "indiv1" for x in j.one_of)


def test_schema_context_prints_owl_expressions_compact():
    schema_path = Path(__file__).parent / "data" / "owl_logic.ttl"
    idx = load_schema_bytes(schema_path.read_bytes(), rdf_format="turtle")

    ctx = schema_to_context_string(
        idx,
        include_prefixes=False,
        include_predicates=False,
        include_notes=False,
        max_types=None,
        max_preds_per_type=0,
        include_class_relations=True,
    )

    assert "unionOf(" in ctx
    assert "intersectionOf(" in ctx
    assert "complementOf(" in ctx
    assert "disjointUnionOf:" in ctx
    assert "unionOf:" in ctx
    assert "intersectionOf:" in ctx
    assert "oneOf:" in ctx


def test_describe_class_includes_owl_fields():
    schema_path = Path(__file__).parent / "data" / "owl_logic.ttl"
    idx = load_schema_bytes(schema_path.read_bytes(), rdf_format="turtle")

    ex_d = "http://example.org/D"
    desc = qg_tools.describe_class(idx, ex_d)
    assert desc is not None
    assert any("intersectionOf(" in s for s in desc.get("equivalent_class_exprs", []))


def test_expr_compact_oneof_format():
    ns = {"ex": "http://example.org/"}
    expr = ClassExpr(
        kind="oneOf",
        items=[ClassExpr(kind="iri", iri="http://example.org/a")],
    )
    assert expr_to_compact_string(expr, ns) == "oneOf(ex:a)"
